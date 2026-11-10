from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SerpSitelink:
    """Organic result 下的一个站内链接。"""

    title: str
    url: str


@dataclass(slots=True)
class OrganicResult:
    """当前 SERP 中的一条自然搜索结果。"""

    position: int | None
    title: str | None
    url: str | None
    snippet: str | None
    date: str | None
    sitelinks: list[SerpSitelink]


@dataclass(slots=True)
class PeopleAlsoAskItem:
    """Google People Also Ask 中的一条问题结果。"""

    question: str
    snippet: str | None
    title: str | None
    url: str | None


@dataclass(slots=True)
class KnowledgeGraphSummary:
    """SERP Knowledge Graph 的轻量摘要。"""

    title: str | None
    type: str | None
    website: str | None
    description: str | None


@dataclass(slots=True)
class SerpResearch:
    """当前 Google SERP 的第三方实时研究结果。

    这里描述的是“搜索结果页当前展示了什么”，不是页面源 HTML，也不是 GSC 本站
    SearchPerformance。Google 可能改写 SERP title/snippet，因此 Skill 必须把它和
    `PageInspection` 分开使用。
    """

    query: str
    market: str
    language: str
    search_engine: str
    organic: list[OrganicResult]
    people_also_ask: list[PeopleAlsoAskItem]
    features: list[str]
    knowledge_graph: KnowledgeGraphSummary | None
