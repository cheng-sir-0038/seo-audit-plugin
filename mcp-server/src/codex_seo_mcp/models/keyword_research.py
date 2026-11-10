from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class KeywordResearch:
    """Semrush 关键词研究结果。

    业务说明：这里同时保留 SEO 难度与 PPC 商业信号，但不把它们混成一个“竞争度”。
    `keyword_difficulty` 表示自然搜索 Top 10 难度；`competitive_density` 表示广告主
    PPC 竞价强度；`cpc_usd` 是广告点击平均价格。它们都不能替代 GSC 的本站排名事实。

    v4 当前只稳定提供 Keyword Metrics，因此 `related/questions` 使用 None 表示“本次未
    获取/当前 v4 未提供”，而不是错误地表达成“没有相关词/问题词”。
    """

    keyword: str
    market: str
    language: str
    search_engine: str
    month: str | None
    search_volume: int | None
    keyword_difficulty: float | None
    intents: list[str]
    cpc_usd: float | None
    competitive_density: float | None
    trends: list[float]
    number_of_results: int | None
    serp_features: list[str]
    related: list[str] | None = None
    questions: list[str] | None = None
