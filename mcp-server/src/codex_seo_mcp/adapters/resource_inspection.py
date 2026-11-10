from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Protocol
from urllib.parse import urlparse

from codex_seo_mcp.clients.resource_http import FetchedResource, ResourceHttpClient
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.resource_inspection import (
    ResourceInspection,
    RobotsGroup,
    RobotsResource,
    RobotsRule,
    SitemapEntry,
    SitemapResource,
)

_RESOURCE_TYPES = {"auto", "robots", "sitemap"}
_MAX_SITEMAP_ENTRIES = 50_000


class ResourceHttpLike(Protocol):
    async def fetch(self, url: str) -> FetchedResource: ...


class ResourceInspectionAdapter:
    """检查 robots.txt / sitemap 的运行时 SEO 资源事实。

    这是 SEO 专属资源解析能力，不是通用 HTTP downloader。PageInspection 继续只负责 HTML。
    """

    capability = "ResourceInspection"

    def __init__(self, client: ResourceHttpLike | None = None) -> None:
        self.client = client or ResourceHttpClient()

    async def inspect(
        self,
        url: str,
        *,
        resource_type: str = "auto",
    ) -> CapabilityResult[ResourceInspection]:
        selected = resource_type.strip().lower()
        if selected not in _RESOURCE_TYPES:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "ResourceInspection resource_type 只支持 auto/robots/sitemap")

        resource = await self.client.fetch(url)
        detected = _detect_resource_type(resource, selected)
        warnings: list[str] = []
        if not 200 <= resource.status_code < 300:
            warnings.append(f"SEO resource 返回 HTTP {resource.status_code}。")

        robots: RobotsResource | None = None
        sitemap: SitemapResource | None = None
        if detected == "robots":
            robots = _parse_robots(resource.text)
            if _media_type(resource.content_type) not in {"", "text/plain"}:
                warnings.append("robots.txt Content-Type 不是 text/plain；仍按 UTF-8 文本规则解析。")
        else:
            sitemap = _parse_sitemap(resource.text)
            if len(sitemap.entries) >= _MAX_SITEMAP_ENTRIES:
                warnings.append("sitemap 达到单文件 50,000 URL 上限；请确认是否需要拆分或使用 sitemap index。")

        data = ResourceInspection(
            requested_url=resource.requested_url,
            final_url=resource.final_url,
            status_code=resource.status_code,
            content_type=resource.content_type,
            content_length_bytes=resource.content_length_bytes,
            redirect_chain=resource.redirect_chain,
            resource_type=detected,
            robots=robots,
            sitemap=sitemap,
        )
        return CapabilityResult.complete(
            capability=self.capability,
            provider="http-resource",
            source_kind=CapabilitySourceKind.RUNTIME,
            data=data,
            warnings=warnings,
        )


def _detect_resource_type(resource: FetchedResource, selected: str) -> str:
    if selected != "auto":
        return selected
    path = urlparse(resource.final_url).path.lower()
    if path.endswith("/robots.txt") or path == "/robots.txt":
        return "robots"
    text = resource.text.lstrip()
    if re.search(r"<(?:\w+:)?(?:urlset|sitemapindex)\b", text, re.I):
        return "sitemap"
    raise SeoDataError(SeoDataErrorCode.DATA_UNAVAILABLE, "目标 URL 不是 robots.txt 或 sitemap SEO resource")


def _parse_robots(text: str) -> RobotsResource:
    groups: list[RobotsGroup] = []
    current: RobotsGroup | None = None
    sitemaps: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, raw_value = line.split(":", 1)
        directive = name.strip().lower()
        value = raw_value.strip()
        if directive == "sitemap":
            if value:
                sitemaps.append(value)
            continue
        if directive == "user-agent":
            if current is None or current.rules:
                current = RobotsGroup()
                groups.append(current)
            if value:
                current.user_agents.append(value)
            continue
        if directive in {"allow", "disallow"} and current is not None:
            current.rules.append(RobotsRule(directive=directive, path=value))

    return RobotsResource(groups=groups, sitemaps=sitemaps)


def _parse_sitemap(text: str) -> SitemapResource:
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "sitemap XML 不允许 DTD/ENTITY")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "sitemap XML 解析失败") from exc

    root_name = _local_name(root.tag)
    if root_name not in {"urlset", "sitemapindex"}:
        raise SeoDataError(SeoDataErrorCode.DATA_UNAVAILABLE, "XML 根节点不是 urlset 或 sitemapindex")
    child_name = "url" if root_name == "urlset" else "sitemap"
    entries: list[SitemapEntry] = []
    for child in root:
        if _local_name(child.tag) != child_name:
            continue
        loc = _child_text(child, "loc")
        if not loc:
            continue
        entries.append(SitemapEntry(loc=loc, lastmod=_child_text(child, "lastmod")))
        if len(entries) >= _MAX_SITEMAP_ENTRIES:
            break
    return SitemapResource(kind=root_name, entries=entries)


def _child_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == name:
            text = str(child.text or "").strip()
            return text or None
    return None


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()


def _media_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()
