from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from codex_seo_mcp.clients.semrush import SemrushClient, SemrushReport
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.market import MarketContext, SemrushMarketResolver
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.keyword_research import KeywordResearch


class SemrushKeywordLike(Protocol):
    """KeywordResearch 对 Semrush Client 的最小依赖面。"""

    async def keyword_metrics(
        self, keyword: str, country: str, month: str | None = None
    ) -> dict[str, object]: ...

    async def keyword_overview_v3(
        self, keyword: str, database: str, month: str | None = None
    ) -> SemrushReport: ...

    async def related_keywords_v3(
        self, keyword: str, database: str, limit: int
    ) -> SemrushReport: ...

    async def keyword_questions_v3(
        self, keyword: str, database: str, limit: int
    ) -> SemrushReport: ...


@dataclass(frozen=True, slots=True)
class _KeywordResearchRequest:
    keyword: str
    market: MarketContext
    v4_country: str
    month: str | None
    include_related: bool
    include_questions: bool
    idea_limit: int

    @classmethod
    def from_input(
        cls,
        *,
        keyword: str,
        country: str,
        language: str,
        search_engine: str,
        month: str | None,
        include_related: bool,
        include_questions: bool,
        idea_limit: int | None,
        default_idea_limit: int,
        market_resolver: SemrushMarketResolver,
    ) -> "_KeywordResearchRequest":
        clean_keyword = keyword.strip()
        if not clean_keyword or len(clean_keyword) > 255:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "KeywordResearch keyword 长度必须为 1-255",
            )
        market = MarketContext.from_values(
            country=country,
            language=language,
            search_engine=search_engine,
        )
        if market.search_engine != "google":
            raise SeoDataError(
                SeoDataErrorCode.UNSUPPORTED_FOR_CAPABILITY,
                "当前 KeywordResearch Provider 是 Semrush/Google，不能把结果当作其他搜索引擎关键词数据",
            )
        if month and not re.fullmatch(r"\d{4}-\d{2}", month):
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "KeywordResearch month 必须是 YYYY-MM",
            )
        resolved_limit = idea_limit if idea_limit is not None else default_idea_limit
        if not 1 <= resolved_limit <= 100:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "KeywordResearch idea_limit 必须为 1-100",
            )
        return cls(
            keyword=clean_keyword,
            market=market,
            v4_country=market_resolver.v4_country(market.country),
            month=month,
            include_related=include_related,
            include_questions=include_questions,
            idea_limit=resolved_limit,
        )


@dataclass(slots=True)
class _KeywordResearchResult:
    data: KeywordResearch
    provider: str
    warnings: list[str] = field(default_factory=list)


_V4_FALLBACK_ERRORS = {
    SeoDataErrorCode.AUTHORIZATION_REQUIRED,
    SeoDataErrorCode.PERMISSION_DENIED,
    SeoDataErrorCode.NOT_CONFIGURED,
}


class KeywordResearchAdapter:
    """把 Semrush v4/v3 关键词数据转成稳定的 `KeywordResearch`。

    Core research 优先使用 v4 Keyword Metrics；v3 只作为同一 Provider 的兼容 fallback。
    Related / Questions 是显式 opt-in enrichment，不影响核心研究结果的完整性定义。
    """

    capability = "KeywordResearch"

    def __init__(
        self,
        client: SemrushKeywordLike | None = None,
        market_resolver: SemrushMarketResolver | None = None,
    ) -> None:
        self.client = client or SemrushClient()
        self.market_resolver = market_resolver or SemrushMarketResolver()

    async def research(
        self,
        keyword: str,
        *,
        country: str,
        language: str,
        search_engine: str,
        month: str | None = None,
        include_related: bool = False,
        include_questions: bool = False,
        idea_limit: int | None = None,
    ) -> CapabilityResult[KeywordResearch]:
        request = _KeywordResearchRequest.from_input(
            keyword=keyword,
            country=country,
            language=language,
            search_engine=search_engine,
            month=month,
            include_related=include_related,
            include_questions=include_questions,
            idea_limit=idea_limit,
            default_idea_limit=int(getattr(self.client, "default_keyword_limit", 20)),
            market_resolver=self.market_resolver,
        )
        result = await self._load_core(request)
        related_failed = await self._enrich_related(request, result)
        questions_failed = await self._enrich_questions(request, result)

        factory = (
            CapabilityResult.partial
            if related_failed or questions_failed
            else CapabilityResult.complete
        )
        return factory(
            capability=self.capability,
            provider=result.provider,
            source_kind=CapabilitySourceKind.THIRD_PARTY,
            data=result.data,
            warnings=result.warnings,
        )

    async def _load_core(self, request: _KeywordResearchRequest) -> _KeywordResearchResult:
        try:
            payload = await self.client.keyword_metrics(
                request.keyword,
                request.v4_country,
                request.month,
            )
            return _KeywordResearchResult(
                data=_map_v4(
                    payload,
                    request.keyword,
                    request.market.country,
                    request.market.language,
                ),
                provider="semrush-v4",
            )
        except SeoDataError as exc:
            if exc.code not in _V4_FALLBACK_ERRORS:
                raise

        report = await self.client.keyword_overview_v3(
            request.keyword,
            self.market_resolver.v3_database(request.market.country),
            request.month,
        )
        return _KeywordResearchResult(
            data=_map_v3_overview(
                report,
                request.keyword,
                request.market.country,
                request.market.language,
                request.month,
            ),
            provider="semrush-v3",
            warnings=["Semrush v4 Keyword Metrics 不可用，当前使用 v3 fallback"],
        )

    async def _enrich_related(
        self,
        request: _KeywordResearchRequest,
        result: _KeywordResearchResult,
    ) -> bool:
        if not request.include_related:
            return False
        try:
            report = await self.client.related_keywords_v3(
                request.keyword,
                self.market_resolver.v3_database(request.market.country),
                request.idea_limit,
            )
            result.data.related = _keyword_list(report)
            if len(result.data.related) >= request.idea_limit:
                result.warnings.append(
                    "Semrush 相关关键词已达到本次关键词返回上限，仅表示 Top-N 调研结果"
                )
            return False
        except SeoDataError as exc:
            result.data.related = None
            result.warnings.append(f"Semrush Related Keywords 不可用：{exc.code}")
            return True

    async def _enrich_questions(
        self,
        request: _KeywordResearchRequest,
        result: _KeywordResearchResult,
    ) -> bool:
        if not request.include_questions:
            return False
        try:
            report = await self.client.keyword_questions_v3(
                request.keyword,
                self.market_resolver.v3_database(request.market.country),
                request.idea_limit,
            )
            result.data.questions = _keyword_list(report)
            if len(result.data.questions) >= request.idea_limit:
                result.warnings.append(
                    "Semrush 问题关键词已达到本次关键词返回上限，仅表示 Top-N 调研结果"
                )
            return False
        except SeoDataError as exc:
            result.data.questions = None
            result.warnings.append(f"Semrush Questions 不可用：{exc.code}")
            return True


def _map_v4(
    payload: dict[str, object], clean_keyword: str, market: str, language: str
) -> KeywordResearch:
    meta = payload.get("meta") if isinstance(payload, dict) else None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(meta, dict) or not isinstance(data, dict):
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "Semrush Keyword Metrics 缺少 meta/data")
    return KeywordResearch(
        keyword=str(meta.get("keyword") or clean_keyword),
        market=str(meta.get("country") or market).upper(),
        language=language,
        search_engine="google",
        month=_text(meta.get("month")),
        search_volume=_int(data.get("search_volume")),
        keyword_difficulty=_float(data.get("keyword_difficulty")),
        intents=_string_list(data.get("intents")),
        cpc_usd=_cents_to_usd(data.get("cpc")),
        competitive_density=_float(data.get("competitive_density")),
        trends=_float_list(data.get("trends")),
        number_of_results=_int(data.get("number_of_results")),
        serp_features=_string_list(data.get("serp_features")),
        related=None,
        questions=None,
    )


def _map_v3_overview(
    report: SemrushReport,
    clean_keyword: str,
    market: str,
    language: str,
    month: str | None,
) -> KeywordResearch:
    row = report.rows[0] if report.rows else {}
    return KeywordResearch(
        keyword=_row(row, "Keyword") or clean_keyword,
        market=market,
        language=language,
        search_engine="google",
        month=month,
        search_volume=_int(_row(row, "Search Volume")),
        keyword_difficulty=_float(_row(row, "Keyword Difficulty Index", "Keyword Difficulty")),
        intents=_v3_intents(_row(row, "Intent")),
        # v3 CPC 本身就是 USD；不要再套 v4 cents 转换。
        cpc_usd=_float(_row(row, "CPC")),
        # v3 Competition 是 0-1，领域层统一成与 v4 competitive_density 相同的 0-100。
        competitive_density=_scale_100(_row(row, "Competition")),
        # v3 Trends 也是 0-1 归一化值，统一成 0-100 后再交给 Product Skill。
        trends=[value * 100 for value in _csv_float_list(_row(row, "Trends"))],
        number_of_results=_int(_row(row, "Number of Results")),
        serp_features=[],
        related=None,
        questions=None,
    )


def _keyword_list(report: SemrushReport) -> list[str]:
    result: list[str] = []
    for row in report.rows:
        value = _row(row, "Keyword")
        if value and value not in result:
            result.append(value)
    return result


def _v3_intents(value: str | None) -> list[str]:
    if not value:
        return []
    mapping = {
        "0": "COMMERCIAL",
        "1": "INFORMATIONAL",
        "2": "NAVIGATIONAL",
        "3": "TRANSACTIONAL",
        "c": "COMMERCIAL",
        "i": "INFORMATIONAL",
        "n": "NAVIGATIONAL",
        "t": "TRANSACTIONAL",
    }
    result: list[str] = []
    for raw in re.split(r"[,\s]+", value.strip().lower()):
        mapped = mapping.get(raw)
        if mapped and mapped not in result:
            result.append(mapped)
    return result


def _row(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = str(row.get(name) or "").strip()
        if value:
            return value
    return None


def _cents_to_usd(value: object) -> float | None:
    amount = _float(value)
    return round(amount / 100.0, 2) if amount is not None else None


def _scale_100(value: object) -> float | None:
    amount = _float(value)
    return round(amount * 100, 4) if amount is not None else None


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _float_list(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    result: list[float] = []
    for item in value:
        parsed = _float(item)
        if parsed is not None:
            result.append(parsed)
    return result


def _csv_float_list(value: str | None) -> list[float]:
    if not value:
        return []
    result: list[float] = []
    for item in value.split(","):
        parsed = _float(item)
        if parsed is not None:
            result.append(parsed)
    return result
