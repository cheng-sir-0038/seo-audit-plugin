from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from codex_seo_mcp.clients.page_html import FetchedPage, PageHtmlClient
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.page_inspection import (
    PageHreflangAlternate,
    PageInspection,
    PageRedirectHop,
    PageStructuredDataBlock,
    PageStructuredDataNode,
)


class PageInspectionAdapter:
    """把 HTTP/HTML 原始结果转换成稳定的 `PageInspection` 页面事实。

    业务边界：Adapter 负责“页面实际上交付了什么”，不负责判断这些事实最终是不是
    SEO 问题。例如 noindex、多个 H1、Meta Refresh 都可能有合法业务场景，最终判断
    交给 Product Skill。
    """

    capability = "PageInspection"

    def __init__(self, client: PageHtmlClient | None = None) -> None:
        self.client = client or PageHtmlClient()

    async def inspect(self, url: str) -> CapabilityResult[PageInspection]:
        page = await self.client.fetch(url)
        data, warnings = _parse_page(page)
        return CapabilityResult.complete(
            capability=self.capability,
            provider="page-html",
            source_kind=CapabilitySourceKind.RUNTIME,
            data=data,
            warnings=warnings,
        )


class _SeoHtmlParser(HTMLParser):
    """从当前 HTML 中抽取 SEO 相关声明，不模拟搜索引擎或浏览器业务判断。

    Parser 只收集声明及出现次数。多个 Title/Canonical/H1 等异常形态仍完整保留，
    避免在解析阶段“帮用户修正”后丢失真正需要诊断的页面事实。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self.descriptions: list[str] = []
        self.canonicals: list[str] = []
        self.robots: list[str] = []
        self.googlebot: list[str] = []
        self.hreflang_alternates: list[tuple[str, str]] = []
        self.anchor_hrefs: list[str] = []
        self.rel_next_hrefs: list[str] = []
        self.rel_prev_hrefs: list[str] = []
        self.json_ld_blocks: list[str] = []
        self._json_ld_buffer: list[str] | None = None
        self.h1: list[str] = []
        self.lang: str | None = None
        self.charset: str | None = None
        self.meta_refresh: str | None = None
        self._title_buffer: list[str] | None = None
        self._h1_buffer: list[str] | None = None
        self._h1_depth = 0
        self._head_depth = 0
        self._svg_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {str(key).lower(): (value or "") for key, value in attrs}
        if tag == "head":
            self._head_depth += 1
        if tag == "svg":
            self._svg_depth += 1

        if tag == "html" and not self.lang:
            self.lang = _clean(values.get("lang"))
        elif tag == "title" and self._head_depth > 0 and self._svg_depth == 0:
            # SEO document title is the HTML <head><title>. Inline SVG <title> is an
            # accessibility label/tooltip and must not inflate title_count.
            self._title_buffer = []
        elif tag == "script" and values.get("type", "").strip().lower() == "application/ld+json":
            self._json_ld_buffer = []
        elif tag == "h1":
            if self._h1_depth == 0:
                self._h1_buffer = []
            self._h1_depth += 1
        elif tag == "meta":
            self._handle_meta(values)
        elif tag == "link":
            rel = {item.lower() for item in values.get("rel", "").split()}
            href = _clean(values.get("href"))
            if "canonical" in rel and href:
                self.canonicals.append(href)
            if "alternate" in rel and href:
                hreflang = _clean(values.get("hreflang"))
                if hreflang:
                    self.hreflang_alternates.append((hreflang, href))
            self._collect_rel_navigation(rel, href)
        elif tag == "a":
            rel = {item.lower() for item in values.get("rel", "").split()}
            href = _clean(values.get("href"))
            if href:
                self.anchor_hrefs.append(href)
            self._collect_rel_navigation(rel, href)

    def _collect_rel_navigation(self, rel: set[str], href: str | None) -> None:
        if not href:
            return
        if "next" in rel:
            self.rel_next_hrefs.append(href)
        if "prev" in rel or "previous" in rel:
            self.rel_prev_hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._json_ld_buffer is not None:
            self.json_ld_blocks.append("".join(self._json_ld_buffer).strip())
            self._json_ld_buffer = None
        elif tag == "title" and self._title_buffer is not None:
            value = _clean("".join(self._title_buffer))
            if value:
                self.titles.append(value)
            self._title_buffer = None
        elif tag == "h1" and self._h1_depth > 0:
            self._h1_depth -= 1
            if self._h1_depth == 0 and self._h1_buffer is not None:
                value = _clean("".join(self._h1_buffer))
                if value:
                    self.h1.append(value)
                self._h1_buffer = None

        if tag == "svg" and self._svg_depth > 0:
            self._svg_depth -= 1
        if tag == "head" and self._head_depth > 0:
            self._head_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._json_ld_buffer is not None:
            self._json_ld_buffer.append(data)
        if self._title_buffer is not None:
            self._title_buffer.append(data)
        if self._h1_buffer is not None:
            self._h1_buffer.append(data)

    def _handle_meta(self, values: dict[str, str]) -> None:
        if not self.charset:
            self.charset = _clean(values.get("charset"))
        name = values.get("name", "").strip().lower()
        content = _clean(values.get("content"))
        if name == "description" and content:
            self.descriptions.append(content)
        elif name == "robots" and content:
            self.robots.append(content)
        elif name == "googlebot" and content:
            self.googlebot.append(content)

        if values.get("http-equiv", "").strip().lower() == "refresh" and content:
            match = re.search(r"(?:^|;)\s*url\s*=\s*['\"]?([^;'\"]+)", content, re.I)
            if match:
                self.meta_refresh = _clean(match.group(1))


def _parse_page(page: FetchedPage) -> tuple[PageInspection, list[str]]:
    """Parse delivered HTML into stable facts, then derive investigation hints from those facts."""

    parser = _SeoHtmlParser()
    parser.feed(page.html)
    parser.close()
    inspection = _map_page_inspection(page, parser)
    return inspection, _inspection_warnings(inspection)


def _map_page_inspection(page: FetchedPage, parser: _SeoHtmlParser) -> PageInspection:
    title = _first(parser.titles)
    description = _first(parser.descriptions)
    canonical = _first(parser.canonicals)
    canonical = urljoin(page.final_url, canonical) if canonical else None
    x_robots_values = list(page.header_values.get("x-robots-tag") or [])
    if not x_robots_values and page.headers.get("x-robots-tag"):
        x_robots_values = [page.headers["x-robots-tag"]]
    declared_noindex = _contains_noindex(
        *parser.robots,
        *parser.googlebot,
        *x_robots_values,
    )
    meta_refresh = (
        urljoin(page.final_url, parser.meta_refresh) if parser.meta_refresh else None
    )
    hreflang_alternates = [
        PageHreflangAlternate(
            hreflang=hreflang,
            url=urljoin(page.final_url, href),
            source="html",
        )
        for hreflang, href in parser.hreflang_alternates
    ]
    hreflang_alternates.extend(
        _parse_http_link_hreflang(
            page.header_values.get("link") or [],
            base_url=page.final_url,
        )
    )
    anchor_links = _resolve_crawlable_urls(parser.anchor_hrefs, base_url=page.final_url)
    rel_next_urls = _resolve_crawlable_urls(parser.rel_next_hrefs, base_url=page.final_url)
    rel_prev_urls = _resolve_crawlable_urls(parser.rel_prev_hrefs, base_url=page.final_url)

    return PageInspection(
        requested_url=page.requested_url,
        final_url=page.final_url,
        status_code=page.status_code,
        content_type=page.content_type,
        content_length_bytes=page.content_length_bytes,
        redirects=[
            PageRedirectHop(
                from_url=item.from_url,
                status_code=item.status_code,
                location=item.location,
                to_url=item.to_url,
            )
            for item in page.redirects
        ],
        title=title,
        title_count=len(parser.titles),
        meta_description=description,
        meta_description_count=len(parser.descriptions),
        canonical=canonical,
        canonical_count=len(parser.canonicals),
        robots_meta_tags=list(parser.robots),
        googlebot_meta_tags=list(parser.googlebot),
        declared_noindex=declared_noindex,
        h1=list(parser.h1),
        lang=parser.lang,
        charset=parser.charset,
        meta_refresh_url=meta_refresh,
        x_robots_tags=x_robots_values,
        hreflang_alternates=hreflang_alternates,
        anchor_links=anchor_links,
        rel_next_urls=rel_next_urls,
        rel_prev_urls=rel_prev_urls,
        structured_data=[_parse_json_ld_block(raw) for raw in parser.json_ld_blocks],
    )


def _inspection_warnings(inspection: PageInspection) -> list[str]:
    """Return factual investigation hints without turning them into final SEO judgements."""

    warnings: list[str] = []
    if not 200 <= inspection.status_code < 300:
        warnings.append(
            f"页面返回 HTTP {inspection.status_code}，当前 HTML 可能是错误页或中间页。"
        )
    if not inspection.title:
        warnings.append("页面 HTML 中没有非空 Title。")
    if inspection.title_count > 1:
        warnings.append("页面存在多个 Title，需要确认最终主标题来源。")
    if not inspection.meta_description:
        warnings.append("页面 HTML 中没有非空 Meta Description。")
    if inspection.meta_description_count > 1:
        warnings.append("页面存在多个 Meta Description。")
    if inspection.canonical_count > 1:
        warnings.append("页面存在多个 Canonical 声明。")
    if not inspection.h1:
        warnings.append("页面 HTML 中没有 H1。")
    elif len(inspection.h1) > 1:
        warnings.append("页面存在多个 H1，需要结合页面结构确认是否符合预期。")
    if inspection.declared_noindex:
        warnings.append("页面声明了 noindex，需要确认该页面是否本来就不应被索引。")
    if inspection.meta_refresh_url:
        warnings.append("页面存在 Meta Refresh，需要确认是否应该改为服务端重定向或保留现状。")
    return warnings


def _contains_noindex(*values: str | None) -> bool:
    """聚合检查所有适用 directive；`none` 等价于 `noindex,nofollow`。"""

    return any(
        re.search(r"(?:^|[,\s])(?:noindex|none)(?:$|[,\s])", value or "", re.I)
        for value in values
    )


def _first(values: list[str]) -> str | None:
    # 页面出现重复声明时仍需要给调用方一个主要展示值；同时 count 会保留重复事实，
    # 因此这里取第一项不会把“存在多个声明”这个诊断信号吞掉。
    return values[0] if values else None


def _clean(value: str | None) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or None


def _resolve_crawlable_urls(values: list[str], *, base_url: str) -> list[str]:
    """Resolve ordinary HTTP(S) links without guessing navigation semantics."""

    resolved: list[str] = []
    for raw in values:
        href = _clean(raw)
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlsplit(absolute)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            continue
        normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if normalized not in resolved:
            resolved.append(normalized)
    return resolved


def _parse_http_link_hreflang(
    values: list[str],
    *,
    base_url: str,
) -> list[PageHreflangAlternate]:
    """Extract RFC-style Link header hreflang alternates without flattening repeated headers."""

    result: list[PageHreflangAlternate] = []
    for raw in values:
        for segment in _split_link_header(raw):
            match = re.match(r"\s*<([^>]+)>\s*(.*)$", segment)
            if not match:
                continue
            href = _clean(match.group(1))
            params = _link_params(match.group(2))
            rel = {item.lower() for item in params.get("rel", "").split()}
            hreflang = _clean(params.get("hreflang"))
            if href and hreflang and "alternate" in rel:
                result.append(
                    PageHreflangAlternate(
                        hreflang=hreflang,
                        url=urljoin(base_url, href),
                        source="http_header",
                    )
                )
    return result


def _split_link_header(value: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    in_quotes = False
    in_angle = False
    for char in str(value):
        if char == '"' and not in_angle:
            in_quotes = not in_quotes
        elif char == "<" and not in_quotes:
            in_angle = True
        elif char == ">" and not in_quotes:
            in_angle = False
        if char == "," and not in_quotes and not in_angle:
            part = "".join(buffer).strip()
            if part:
                parts.append(part)
            buffer = []
            continue
        buffer.append(char)
    part = "".join(buffer).strip()
    if part:
        parts.append(part)
    return parts


def _link_params(value: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in str(value).split(";"):
        text = item.strip()
        if not text or "=" not in text:
            continue
        key, raw = text.split("=", 1)
        params[key.strip().lower()] = raw.strip().strip('"')
    return params


def _parse_json_ld_block(raw: str) -> PageStructuredDataBlock:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return PageStructuredDataBlock(format="json_ld", valid=False, types=[], parse_error=str(exc))
    nodes = _json_ld_nodes(data)
    return PageStructuredDataBlock(
        format="json_ld",
        valid=True,
        types=_dedupe([schema_type for node in nodes for schema_type in node.types]),
        parse_error=None,
        nodes=nodes,
    )


def _json_ld_nodes(value: object) -> list[PageStructuredDataNode]:
    """Extract top-level JSON-LD entities without retaining the full source payload.

    Root objects, root arrays, and `@graph` entries become independent nodes. Nested Offer/Review/
    ListItem objects stay inside their owning node as property paths, which prevents a nested type
    from being mistaken for another page-level rich-result entity.
    """

    result: list[PageStructuredDataNode] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            types = _schema_types(item.get("@type"))
            if types:
                result.append(
                    PageStructuredDataNode(
                        types=types,
                        property_paths=_json_ld_property_paths(item),
                    )
                )
            graph = item.get("@graph")
            if isinstance(graph, list):
                for child in graph:
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return result


def _schema_types(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return _dedupe(
        [
            candidate.strip()
            for candidate in values
            if isinstance(candidate, str) and candidate.strip()
        ]
    )


def _json_ld_property_paths(node: dict[str, object]) -> list[str]:
    paths: list[str] = []

    def add(path: str) -> None:
        if path and path not in paths:
            paths.append(path)

    def walk(value: object, prefix: str) -> None:
        if isinstance(value, dict):
            for raw_key, child in value.items():
                key = str(raw_key)
                if key in {"@context", "@type"}:
                    continue
                path = f"{prefix}.{key}" if prefix else key
                add(path)
                walk(child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                path = f"{prefix}[{index}]"
                add(path)
                walk(child, path)

    walk(node, "")
    return paths


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
