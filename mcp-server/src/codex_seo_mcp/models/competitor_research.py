from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DomainOverview:
    """Semrush 对域名整体搜索可见性的第三方估算摘要。"""

    domain: str
    semrush_rank: int | None
    organic_keywords: int | None
    organic_traffic: int | None
    organic_cost: float | None
    paid_keywords: int | None
    paid_traffic: int | None
    paid_cost: float | None


@dataclass(slots=True)
class CompetitorDomain:
    """Semrush Organic Research 识别出的一个竞争域名。"""

    domain: str
    relevance: float | None
    common_keywords: int | None
    organic_keywords: int | None
    organic_traffic: int | None
    organic_cost: float | None
    paid_keywords: int | None


@dataclass(slots=True)
class OrganicPage:
    """Semrush 估算的域名自然搜索页面表现，仅用于竞争研究。"""

    url: str
    organic_keywords: int | None
    traffic: int | None
    traffic_percent: float | None


@dataclass(slots=True)
class KeywordGapRow:
    """多个域名在同一关键词上的 Semrush 第三方位置对比。"""

    keyword: str
    positions: dict[str, int | None]
    competition: float | None
    search_volume: int | None
    cpc_usd: float | None


@dataclass(slots=True)
class CompetitorResearch:
    """域名与竞品研究结果。

    这里出现的 position/rank 全部属于 Semrush 第三方数据库视角，只用于理解竞争条件，
    不能覆盖 `SearchPerformance` 中 GSC 的本站第一方搜索表现。
    """

    domain: str
    market: str
    language: str
    search_engine: str
    overview: DomainOverview | None
    competitors: list[CompetitorDomain]
    organic_pages: list[OrganicPage]
    keyword_gap: list[KeywordGapRow]
