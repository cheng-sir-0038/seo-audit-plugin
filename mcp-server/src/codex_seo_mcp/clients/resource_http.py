from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from codex_seo_mcp.clients.page_html import (
    HttpTransport,
    PageHtmlConfig,
    UrllibTransport,
    _charset_from_content_type,
    _normalize_url,
    default_resolver,
    validate_public_target,
)
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


@dataclass(slots=True)
class FetchedResource:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str | None
    content_length_bytes: int
    redirect_chain: list[str]
    headers: dict[str, str]
    text: str


class ResourceHttpClient:
    """只服务 SEO robots/sitemap 资源的公开 HTTP 客户端。

    它复用 PageInspection 的 transport、大小限制和 SSRF 边界，但不承担 HTML 页面解析。
    """

    def __init__(
        self,
        *,
        config: PageHtmlConfig | None = None,
        resolver=default_resolver,
        transport: HttpTransport | None = None,
    ) -> None:
        self.config = config or PageHtmlConfig()
        self.resolver = resolver
        self.transport = transport or UrllibTransport()

    async def fetch(self, url: str) -> FetchedResource:
        requested = _normalize_url(url)
        current = requested
        redirect_chain = [requested]

        for redirect_count in range(self.config.max_redirects + 1):
            pinned = await self._assert_public_target(current)
            response = await self.transport.get(current, config=self.config, pinned_addresses=pinned)

            location = response.headers.get("location")
            if 300 <= response.status_code < 400 and location:
                if redirect_count >= self.config.max_redirects:
                    raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "SEO resource 重定向次数超过限制")
                current = _normalize_url(urljoin(current, location))
                redirect_chain.append(current)
                continue

            content_type = response.headers.get("content-type")
            charset = _charset_from_content_type(content_type) or "utf-8"
            try:
                text = response.body.decode(charset, errors="replace")
            except LookupError:
                text = response.body.decode("utf-8", errors="replace")

            return FetchedResource(
                requested_url=requested,
                final_url=current,
                status_code=response.status_code,
                content_type=content_type,
                content_length_bytes=len(response.body),
                redirect_chain=redirect_chain,
                headers=response.headers,
                text=text,
            )

        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "SEO resource 重定向处理失败")

    async def _assert_public_target(self, url: str) -> list[str]:
        return await validate_public_target(url, self.resolver, capability="ResourceInspection")
