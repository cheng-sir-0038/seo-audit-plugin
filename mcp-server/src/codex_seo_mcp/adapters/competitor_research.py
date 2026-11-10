from __future__ import annotations

import re
from typing import Protocol

from codex_seo_mcp.clients.semrush import SemrushClient, SemrushReport
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.market import MarketContext, SemrushMarketResolver
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.competitor_research import (
    CompetitorDomain,
    CompetitorResearch,
    DomainOverview,
    KeywordGapRow,
    OrganicPage,
)


class SemrushCompetitorLike(Protocol):
    """CompetitorResearch 对 Semrush v3 Client 的最小依赖面。"""

    async def domain_overview(self, domain: str, database: str) -> SemrushReport: ...
    async def organic_competitors(self, domain: str, database: str, limit: int) -> SemrushReport: ...
    async def organic_pages(self, domain: str, database: str, limit: int) -> SemrushReport: ...
    async def keyword_gap(self, domains: list[str], database: str, limit: int) -> SemrushReport: ...


class CompetitorResearchAdapter:
    """组合 Semrush v3 Domain Reports 成稳定的 `CompetitorResearch`。

    Keyword Gap 的单位成本明显高于普通 Domain report，因此只有调用方明确给出比较域名
    时才请求，避免 Agent 为了“报告更丰富”自动消耗大量 API units。
    """

    capability = "CompetitorResearch"

    def __init__(
        self,
        client: SemrushCompetitorLike | None = None,
        market_resolver: SemrushMarketResolver | None = None,
    ) -> None:
        self.client = client or SemrushClient()
        self.market_resolver = market_resolver or SemrushMarketResolver()

    async def research(
        self,
        domain: str,
        *,
        country: str,
        language: str,
        search_engine: str,
        compare_domains: list[str] | None = None,
        limit: int = 10,
        keyword_limit: int | None = None,
    ) -> CapabilityResult[CompetitorResearch]:
        clean_domain = _normalize_domain(domain)
        market_context = MarketContext.from_values(
            country=country,
            language=language,
            search_engine=search_engine,
        )
        if market_context.search_engine != "google":
            raise SeoDataError(SeoDataErrorCode.UNSUPPORTED_FOR_CAPABILITY,
                "当前 CompetitorResearch Provider 是 Semrush/Google，不能把结果当作其他搜索引擎竞品数据",
            )
        market = market_context.country
        database = self.market_resolver.v3_database(market)
        if not 1 <= limit <= 100:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "CompetitorResearch limit 必须在 1-100")
        resolved_keyword_limit = (
            keyword_limit
            if keyword_limit is not None
            else int(getattr(self.client, "default_keyword_limit", 20))
        )
        if not 1 <= resolved_keyword_limit <= 100:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "CompetitorResearch keyword_limit 必须在 1-100")

        compares = [_normalize_domain(item) for item in (compare_domains or [])]
        compares = [item for item in compares if item != clean_domain]
        if len(compares) > 4:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "Keyword Gap 最多比较 5 个域名（含主域名）")

        overview_report = await self.client.domain_overview(clean_domain, database)
        competitors_report = await self.client.organic_competitors(clean_domain, database, limit)
        pages_report = await self.client.organic_pages(clean_domain, database, limit)
        gap_report = (
            await self.client.keyword_gap(
                [clean_domain, *compares], database, resolved_keyword_limit
            )
            if compares
            else SemrushReport(rows=[])
        )

        result = CompetitorResearch(
            domain=clean_domain,
            market=market,
            language=market_context.language,
            search_engine="google",
            overview=_map_overview(overview_report),
            competitors=[_map_competitor(row) for row in competitors_report.rows],
            organic_pages=[_map_page(row) for row in pages_report.rows],
            keyword_gap=[_map_gap(row, [clean_domain, *compares]) for row in gap_report.rows],
        )
        warnings: list[str] = []
        if len(competitors_report.rows) >= limit:
            warnings.append("Semrush 竞争域名结果达到 limit，当前只表示 Top-N 竞争背景")
        if len(pages_report.rows) >= limit:
            warnings.append("Semrush Organic Pages 达到 limit，当前只表示 Top-N 页面")
        if compares and len(gap_report.rows) >= resolved_keyword_limit:
            warnings.append("Semrush Keyword Gap 已达到本次关键词返回上限，当前只表示 Top-N Gap 关键词")

        return CapabilityResult.complete(
            capability=self.capability,
            provider="semrush",
            source_kind=CapabilitySourceKind.THIRD_PARTY,
            data=result,
            warnings=warnings,
        )


def _normalize_domain(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = text.split("/", 1)[0].strip(".")
    if not text or "." not in text or any(ch.isspace() for ch in text):
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "CompetitorResearch domain 必须是有效域名")
    return text


def _map_overview(report: SemrushReport) -> DomainOverview | None:
    if not report.rows:
        return None
    row = report.rows[0]
    return DomainOverview(
        domain=row.get("Domain", ""),
        semrush_rank=_int(row.get("Rank")),
        organic_keywords=_int(row.get("Organic Keywords")),
        organic_traffic=_int(row.get("Organic Traffic")),
        organic_cost=_float(row.get("Organic Cost")),
        paid_keywords=_int(row.get("Adwords Keywords")),
        paid_traffic=_int(row.get("Adwords Traffic")),
        paid_cost=_float(row.get("Adwords Cost")),
    )


def _map_competitor(row: dict[str, str]) -> CompetitorDomain:
    return CompetitorDomain(
        domain=row.get("Domain", ""),
        relevance=_float(row.get("Competitor Relevance")),
        common_keywords=_int(row.get("Common Keywords")),
        organic_keywords=_int(row.get("Organic Keywords")),
        organic_traffic=_int(row.get("Organic Traffic")),
        organic_cost=_float(row.get("Organic Cost")),
        paid_keywords=_int(row.get("Adwords Keywords")),
    )


def _map_page(row: dict[str, str]) -> OrganicPage:
    return OrganicPage(
        url=row.get("Url", ""),
        organic_keywords=_int(row.get("Number of Keywords")),
        traffic=_int(row.get("Traffic")),
        traffic_percent=_float(row.get("Traffic (%)")),
    )


def _map_gap(row: dict[str, str], domains: list[str]) -> KeywordGapRow:
    return KeywordGapRow(
        keyword=row.get("Keyword", ""),
        positions={domain: _int(row.get(domain)) for domain in domains},
        competition=_float(row.get("Competition")),
        search_volume=_int(row.get("Search Volume")),
        cpc_usd=_float(row.get("CPC")),
    )


def _int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
