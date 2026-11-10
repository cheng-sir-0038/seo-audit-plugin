from __future__ import annotations

from typing import Protocol

from codex_seo_mcp.clients.serper import SerperClient
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.market import MarketContext
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.serp_research import (
    KnowledgeGraphSummary,
    OrganicResult,
    PeopleAlsoAskItem,
    SerpResearch,
    SerpSitelink,
)


class SerperLike(Protocol):
    """SerpResearch 对实时 SERP Provider 的最小依赖面。"""

    async def search(
        self,
        query: str,
        *,
        country: str,
        language: str,
        num: int,
        location: str | None = None,
    ) -> dict[str, object]: ...


class SerpResearchAdapter:
    """把 Serper 原始 JSON 转成稳定的 `SerpResearch`。"""

    capability = "SerpResearch"

    def __init__(self, client: SerperLike | None = None) -> None:
        self.client = client or SerperClient()

    async def research(
        self,
        query: str,
        *,
        country: str,
        language: str,
        search_engine: str,
        num: int = 10,
        location: str | None = None,
    ) -> CapabilityResult[SerpResearch]:
        clean_query = query.strip()
        if not clean_query:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "SerpResearch query 不能为空")
        market = MarketContext.from_values(
            country=country,
            language=language,
            search_engine=search_engine,
            location=location,
        )
        if market.search_engine != "google":
            raise SeoDataError(SeoDataErrorCode.UNSUPPORTED_FOR_CAPABILITY,
                "当前 SerpResearch Provider 是 Serper/Google，不能把结果当作其他搜索引擎 SERP",
            )
        if not 1 <= num <= 100:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "SerpResearch num 必须在 1-100")

        payload = await self.client.search(
            clean_query,
            country=market.country,
            language=market.language.lower(),
            num=num,
            location=market.location,
        )
        research = SerpResearch(
            query=clean_query,
            market=market.country,
            language=market.language,
            search_engine=market.search_engine,
            organic=_map_organic(payload.get("organic")),
            people_also_ask=_map_paa(payload.get("peopleAlsoAsk")),
            features=_detect_features(payload),
            knowledge_graph=_map_knowledge_graph(payload.get("knowledgeGraph")),
        )
        return CapabilityResult.complete(
            capability=self.capability,
            provider="serper",
            source_kind=CapabilitySourceKind.THIRD_PARTY,
            data=research,
        )


def _map_organic(value: object) -> list[OrganicResult]:
    if not isinstance(value, list):
        return []
    results: list[OrganicResult] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        sitelinks: list[SerpSitelink] = []
        for item in raw.get("sitelinks") or []:
            if isinstance(item, dict):
                title = _text(item.get("title"))
                url = _text(item.get("link"))
                if title and url:
                    sitelinks.append(SerpSitelink(title=title, url=url))
        results.append(
            OrganicResult(
                position=_int(raw.get("position")),
                title=_text(raw.get("title")),
                url=_text(raw.get("link")),
                snippet=_text(raw.get("snippet")),
                date=_text(raw.get("date")),
                sitelinks=sitelinks,
            )
        )
    return results


def _map_paa(value: object) -> list[PeopleAlsoAskItem]:
    if not isinstance(value, list):
        return []
    results: list[PeopleAlsoAskItem] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        question = _text(raw.get("question"))
        if not question:
            continue
        results.append(
            PeopleAlsoAskItem(
                question=question,
                snippet=_text(raw.get("snippet")),
                title=_text(raw.get("title")),
                url=_text(raw.get("link")),
            )
        )
    return results


def _map_knowledge_graph(value: object) -> KnowledgeGraphSummary | None:
    if not isinstance(value, dict):
        return None
    return KnowledgeGraphSummary(
        title=_text(value.get("title")),
        type=_text(value.get("type")),
        website=_text(value.get("website")),
        description=_text(value.get("description")),
    )


def _detect_features(payload: dict[str, object]) -> list[str]:
    mapping = {
        "knowledgeGraph": "knowledge_graph",
        "answerBox": "answer_box",
        "peopleAlsoAsk": "people_also_ask",
        "topStories": "top_stories",
        "places": "places",
        "shopping": "shopping",
        "images": "images",
        "videos": "videos",
        "relatedSearches": "related_searches",
    }
    return [name for key, name in mapping.items() if payload.get(key)]


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
