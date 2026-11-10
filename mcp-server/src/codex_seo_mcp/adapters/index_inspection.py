from __future__ import annotations

from typing import Protocol
from urllib.parse import urlparse

from codex_seo_mcp.clients.gsc import GscClient, GscInspectionResponse
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.index_inspection import IndexInspection


class GscInspectionLike(Protocol):
    async def inspect_url(
        self,
        *,
        property_url: str,
        inspection_url: str,
        language_code: str,
    ) -> GscInspectionResponse: ...


class IndexInspectionAdapter:
    """把 GSC URL Inspection 映射为稳定的索引诊断事实。

    当前 API 只描述 Google 索引中的版本，不是 live URL test；实时 HTTP/HTML 事实仍由
    PageInspection 负责，二者不能互相替代。
    """

    capability = "IndexInspection"

    def __init__(self, client: GscInspectionLike | None = None) -> None:
        self.client = client or GscClient()

    async def inspect(
        self,
        *,
        property_url: str,
        inspection_url: str,
        language_code: str = "en-US",
    ) -> CapabilityResult[IndexInspection]:
        if not _valid_property(property_url):
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GSC property 必须是 sc-domain: 或 HTTP/HTTPS URL-prefix")
        parsed = urlparse(inspection_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "IndexInspection inspection_url 必须是完整 HTTP/HTTPS URL")
        language = language_code.strip() or "en-US"

        response = await self.client.inspect_url(
            property_url=property_url.strip(),
            inspection_url=inspection_url.strip(),
            language_code=language,
        )
        inspection_result = response.payload.get("inspectionResult")
        if not isinstance(inspection_result, dict):
            inspection_result = {}
        index_status = inspection_result.get("indexStatusResult")
        has_index_status = isinstance(index_status, dict)
        if not has_index_status:
            index_status = {}

        data = IndexInspection(
            property_url=property_url.strip(),
            inspection_url=inspection_url.strip(),
            inspection_result_link=_text(inspection_result.get("inspectionResultLink")),
            verdict=_text(index_status.get("verdict")),
            coverage_state=_text(index_status.get("coverageState")),
            robots_txt_state=_text(index_status.get("robotsTxtState")),
            indexing_state=_text(index_status.get("indexingState")),
            last_crawl_time=_text(index_status.get("lastCrawlTime")),
            page_fetch_state=_text(index_status.get("pageFetchState")),
            google_canonical=_text(index_status.get("googleCanonical")),
            user_canonical=_text(index_status.get("userCanonical")),
            crawled_as=_text(index_status.get("crawledAs")),
            sitemaps=_strings(index_status.get("sitemap")),
            referring_urls=_strings(index_status.get("referringUrls")),
        )
        warnings = [
            "IndexInspection 只描述 Google 索引中的版本，不是 live URL test；实时页面事实请使用 PageInspection。"
        ]
        if not has_index_status:
            warnings.append("GSC 没有返回 indexStatusResult；不能解释为 URL 未索引。")
            factory = CapabilityResult.partial
        else:
            factory = CapabilityResult.complete
        return factory(
            capability=self.capability,
            provider="gsc",
            source_kind=CapabilitySourceKind.FIRST_PARTY,
            data=data,
            warnings=warnings,
        )


def _valid_property(value: str) -> bool:
    text = value.strip()
    return text.startswith("sc-domain:") or text.startswith("https://") or text.startswith("http://")


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for raw in value if (text := str(raw or "").strip())]
