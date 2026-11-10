from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from urllib.parse import urlparse

from codex_seo_mcp.clients.dataforseo import DataForSEOClient, DataForSEOReport
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.market import (
    DataForSEOLabsMarketResolver,
    MarketContext,
    ProviderMarket,
)
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.organic_visibility import (
    OrganicVisibility,
    OrganicVisibilityHistoryPoint,
    OrganicVisibilityKeyword,
    OrganicVisibilityKeywordStatus,
    OrganicVisibilityMarket,
    OrganicVisibilityObservation,
    OrganicVisibilityOverview,
    OrganicVisibilityPage,
)

_VIEWS = {"overview", "keywords", "pages", "history"}
_SCOPES = {"domain", "exact"}


@dataclass(frozen=True, slots=True)
class OrganicVisibilityProviderDescriptor:
    provider: str
    supported_view_scopes: frozenset[tuple[str, str]]


@dataclass(frozen=True, slots=True)
class _OrganicVisibilityRequest:
    target: str
    market: MarketContext
    view: str
    target_scope: str
    limit: int
    offset: int
    historical_serp_mode: str
    date_from: str | None
    date_to: str | None

    @classmethod
    def from_input(
        cls,
        *,
        target: str,
        country: str,
        language: str,
        search_engine: str,
        view: str,
        target_scope: str,
        limit: int,
        offset: int,
        historical_serp_mode: str,
        date_from: str | None,
        date_to: str | None,
    ) -> "_OrganicVisibilityRequest":
        selected_view = view.strip().lower()
        if selected_view not in _VIEWS:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                f"OrganicVisibility view 不支持：{selected_view}",
            )
        selected_scope = target_scope.strip().lower()
        if selected_scope not in _SCOPES:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "DataForSEO OrganicVisibility 当前 target_scope 只支持 domain/exact",
            )
        if selected_scope == "exact" and selected_view != "keywords":
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "DataForSEO exact URL scope 当前只支持 keywords view",
            )
        if not 1 <= limit <= 1000:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "OrganicVisibility limit 必须在 1 到 1000 之间",
            )
        if offset < 0:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "OrganicVisibility offset 不能小于 0",
            )
        if historical_serp_mode not in {"live", "lost", "all"}:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "OrganicVisibility historical_serp_mode 只支持 live/lost/all",
            )
        _validate_history_dates(date_from, date_to)
        return cls(
            target=_normalize_target(target, selected_scope),
            market=MarketContext.from_values(
                country=country,
                language=language,
                search_engine=search_engine,
            ),
            view=selected_view,
            target_scope=selected_scope,
            limit=limit,
            offset=offset,
            historical_serp_mode=historical_serp_mode,
            date_from=date_from,
            date_to=date_to,
        )

    def provider_task(self, provider_market: ProviderMarket) -> dict[str, object]:
        task: dict[str, object] = {
            "target": self.target,
            "location_code": provider_market.location_code,
            "language_code": provider_market.language_code,
        }
        if self.view in {"keywords", "pages"}:
            task.update(
                {
                    "limit": self.limit,
                    "offset": self.offset,
                    "historical_serp_mode": self.historical_serp_mode,
                    "item_types": ["organic"],
                }
            )
        elif self.view == "history":
            if self.date_from:
                task["date_from"] = self.date_from
            if self.date_to:
                task["date_to"] = self.date_to
        return task


class DataForSEOLike(Protocol):
    @property
    def is_sandbox(self) -> bool: ...

    async def locations_and_languages(self) -> list[dict[str, object]]: ...

    async def ranked_keywords(self, task: dict[str, object]) -> DataForSEOReport: ...

    async def relevant_pages(self, task: dict[str, object]) -> DataForSEOReport: ...

    async def domain_rank_overview(self, task: dict[str, object]) -> DataForSEOReport: ...

    async def historical_rank_overview(self, task: dict[str, object]) -> DataForSEOReport: ...


class DataForSEOOrganicVisibilityAdapter:
    """First provider adapter for provider-neutral `OrganicVisibility`.

    V1 of this adapter uses DataForSEO Labs Google endpoints and keeps provider-specific location
    codes, task envelopes and ETV semantics out of Product Skills.
    """

    capability = "OrganicVisibility"
    provider = "dataforseo"

    def __init__(
        self,
        client: DataForSEOLike | None = None,
        market_resolver: DataForSEOLabsMarketResolver | None = None,
    ) -> None:
        self.client = client or DataForSEOClient()
        self.market_resolver = market_resolver or DataForSEOLabsMarketResolver(self.client)

    @property
    def descriptor(self) -> OrganicVisibilityProviderDescriptor:
        return OrganicVisibilityProviderDescriptor(
            provider=self.provider,
            supported_view_scopes=frozenset(
                {
                    ("overview", "domain"),
                    ("keywords", "domain"),
                    ("keywords", "exact"),
                    ("pages", "domain"),
                    ("history", "domain"),
                }
            ),
        )

    async def inspect(
        self,
        target: str,
        *,
        country: str,
        language: str,
        search_engine: str,
        view: str = "keywords",
        target_scope: str = "domain",
        limit: int = 100,
        offset: int = 0,
        historical_serp_mode: str = "live",
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> CapabilityResult[OrganicVisibility]:
        request = _OrganicVisibilityRequest.from_input(
            target=target,
            country=country,
            language=language,
            search_engine=search_engine,
            view=view,
            target_scope=target_scope,
            limit=limit,
            offset=offset,
            historical_serp_mode=historical_serp_mode,
            date_from=date_from,
            date_to=date_to,
        )
        provider_market = await self.market_resolver.resolve(
            request.market,
            capability=self.capability,
            source="google",
        )
        report = await self._fetch(
            request.view,
            request.provider_task(provider_market),
        )
        sandbox = bool(getattr(self.client, "is_sandbox", False))
        visibility = _map_visibility(
            report,
            target=request.target,
            target_scope=request.target_scope,
            country=request.market.country,
            language=request.market.language,
            search_engine=request.market.search_engine,
            view=request.view,
            location_name=provider_market.location_name or request.market.country,
            historical_serp_mode=request.historical_serp_mode,
            sandbox=sandbox,
        )
        factory = CapabilityResult.partial if report.partial else CapabilityResult.complete
        return factory(
            capability=self.capability,
            provider=self.provider,
            source_kind=CapabilitySourceKind.THIRD_PARTY,
            data=visibility,
            warnings=_visibility_warnings(report, sandbox=sandbox),
        )

    async def _fetch(self, view: str, task: dict[str, object]) -> DataForSEOReport:
        if view == "keywords":
            return await self.client.ranked_keywords(task)
        if view == "pages":
            return await self.client.relevant_pages(task)
        if view == "overview":
            return await self.client.domain_rank_overview(task)
        return await self.client.historical_rank_overview(task)


def _visibility_warnings(
    report: DataForSEOReport,
    *,
    sandbox: bool,
) -> list[str]:
    warnings: list[str] = []
    if report.partial:
        warnings.append(report.status_message or "DataForSEO 返回 partial result")
    if not report.result:
        warnings.append(
            "DataForSEO 当前请求没有返回记录；这表示第三方数据库 No Data，不能证明目标没有 Google 排名。"
        )
    if sandbox:
        warnings.append("DataForSEO Sandbox 只返回 dummy data，不能作为真实 SEO 诊断证据。")
    return warnings

def _map_visibility(
    report: DataForSEOReport,
    *,
    target: str,
    target_scope: str,
    country: str,
    language: str,
    search_engine: str,
    view: str,
    location_name: str,
    historical_serp_mode: str,
    sandbox: bool,
) -> OrganicVisibility:
    root = report.result[0] if report.result else {}
    coverage_notes = [
        "third-party DataForSEO Labs visibility; not GSC clicks/impressions/CTR",
        f"market={country}/{language} ({location_name})",
        "DataForSEO Labs visibility data is provider-observed and updated on its own database cadence",
    ]
    if view == "keywords":
        coverage_notes.extend(
            [
                "DataForSEO current/previous keyword positions use rank_absolute so both values stay on the same provider axis",
                "DataForSEO Ranked Keywords exposes one ranked_serp_element per returned keyword item; do not treat it as an exhaustive list of every ranking page for that query",
            ]
        )
        coverage_notes.append(f"historical_serp_mode={historical_serp_mode}")
        if historical_serp_mode == "live":
            coverage_notes.append(
                "live mode excludes keywords that disappeared from the latest SERP; lost keyword count is therefore unknown, not zero"
            )
    if sandbox:
        coverage_notes.append("sandbox dummy data")

    overview = (
        _overview_from_metrics(
            _organic_metrics(root.get("metrics")),
            include_lost=historical_serp_mode != "live",
        )
        if view == "keywords"
        else None
    )
    keywords = _map_keywords(root.get("items")) if view == "keywords" else []
    pages = _map_pages(root.get("items")) if view == "pages" else []
    history = _map_history(root.get("items")) if view == "history" else []
    if view == "overview":
        overview_item = _first_dict(root.get("items"))
        overview = _overview_from_metrics(_organic_metrics(overview_item.get("metrics")))

    current_date, compare_date, data_updated_at = _observation_dates(keywords)
    return OrganicVisibility(
        target=target,
        target_scope=target_scope,
        market=OrganicVisibilityMarket(country=country, language=language),
        search_engine=search_engine,
        observation=OrganicVisibilityObservation(
            data_updated_at=data_updated_at,
            current_date=current_date,
            compare_date=compare_date,
            coverage_notes=coverage_notes,
        ),
        overview=overview,
        keywords=keywords,
        pages=pages,
        history=history,
    )


def _map_keywords(value: object) -> list[OrganicVisibilityKeyword]:
    if not isinstance(value, list):
        return []
    results: list[OrganicVisibilityKeyword] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        keyword_data = raw.get("keyword_data") if isinstance(raw.get("keyword_data"), dict) else {}
        ranked = (
            raw.get("ranked_serp_element")
            if isinstance(raw.get("ranked_serp_element"), dict)
            else {}
        )
        serp_item = ranked.get("serp_item") if isinstance(ranked.get("serp_item"), dict) else {}
        if str(serp_item.get("type") or "organic") != "organic":
            continue
        query = str(keyword_data.get("keyword") or "").strip()
        if not query:
            continue
        rank_changes = (
            serp_item.get("rank_changes") if isinstance(serp_item.get("rank_changes"), dict) else {}
        )
        lost = bool(ranked.get("is_lost"))
        url = _text(serp_item.get("url"))
        current_position = None if lost else _int(serp_item.get("rank_absolute"))
        previous_position = _int(rank_changes.get("previous_rank_absolute"))
        status = _keyword_status(lost=lost, rank_changes=rank_changes)
        keyword_info = (
            keyword_data.get("keyword_info") if isinstance(keyword_data.get("keyword_info"), dict) else {}
        )
        serp_info = keyword_data.get("serp_info") if isinstance(keyword_data.get("serp_info"), dict) else {}
        features = [
            str(item)
            for item in (serp_info.get("serp_item_types") or [])
            if str(item) != "organic"
        ]
        results.append(
            OrganicVisibilityKeyword(
                query=query,
                current_position=current_position,
                previous_position=previous_position,
                current_url=None if lost else url,
                previous_url=url if lost else None,
                status=status,
                search_volume=_float(keyword_info.get("search_volume")),
                estimated_traffic=_float(serp_item.get("etv")),
                serp_features=features,
                last_updated_at=_text(ranked.get("last_updated_time"))
                or _text(serp_info.get("last_updated_time")),
                previous_updated_at=_text(ranked.get("previous_updated_time"))
                or _text(serp_info.get("previous_updated_time")),
            )
        )
    return results


def _map_pages(value: object) -> list[OrganicVisibilityPage]:
    if not isinstance(value, list):
        return []
    results: list[OrganicVisibilityPage] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        url = _text(raw.get("page_address"))
        if not url:
            continue
        metrics = _organic_metrics(raw.get("metrics"))
        results.append(
            OrganicVisibilityPage(
                url=url,
                keyword_count=_int(metrics.get("count")),
                estimated_traffic=_float(metrics.get("etv")),
                new_keywords=_int(metrics.get("is_new")),
                up_keywords=_int(metrics.get("is_up")),
                down_keywords=_int(metrics.get("is_down")),
                lost_keywords=_int(metrics.get("is_lost")),
            )
        )
    return results


def _map_history(value: object) -> list[OrganicVisibilityHistoryPoint]:
    if not isinstance(value, list):
        return []
    results: list[OrganicVisibilityHistoryPoint] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        year = _int(raw.get("year"))
        month = _int(raw.get("month"))
        if not year or not month or not 1 <= month <= 12:
            continue
        metrics = _organic_metrics(raw.get("metrics"))
        overview = _overview_from_metrics(metrics)
        if overview is None:
            continue
        results.append(
            OrganicVisibilityHistoryPoint(
                date=f"{year:04d}-{month:02d}-01",
                total_keywords=overview.total_keywords,
                top3_keywords=overview.top3_keywords,
                top10_keywords=overview.top10_keywords,
                top100_keywords=overview.top100_keywords,
                estimated_traffic=overview.estimated_traffic,
                new_keywords=overview.new_keywords,
                up_keywords=overview.up_keywords,
                down_keywords=overview.down_keywords,
                lost_keywords=overview.lost_keywords,
            )
        )
    return results


def _overview_from_metrics(
    metrics: dict[str, object], *, include_lost: bool = True
) -> OrganicVisibilityOverview | None:
    if not metrics:
        return None
    pos1 = _int(metrics.get("pos_1")) or 0
    pos23 = _int(metrics.get("pos_2_3")) or 0
    pos410 = _int(metrics.get("pos_4_10")) or 0
    total = _int(metrics.get("count"))
    return OrganicVisibilityOverview(
        total_keywords=total,
        top3_keywords=pos1 + pos23,
        top10_keywords=pos1 + pos23 + pos410,
        top100_keywords=total,
        estimated_traffic=_float(metrics.get("etv")),
        new_keywords=_int(metrics.get("is_new")),
        up_keywords=_int(metrics.get("is_up")),
        down_keywords=_int(metrics.get("is_down")),
        lost_keywords=_int(metrics.get("is_lost")) if include_lost else None,
    )


def _organic_metrics(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    organic = value.get("organic")
    return organic if isinstance(organic, dict) else {}


def _keyword_status(
    *, lost: bool, rank_changes: dict[str, object]
) -> OrganicVisibilityKeywordStatus:
    if lost:
        return OrganicVisibilityKeywordStatus.LOST
    if bool(rank_changes.get("is_new")):
        return OrganicVisibilityKeywordStatus.NEW
    if bool(rank_changes.get("is_up")):
        return OrganicVisibilityKeywordStatus.RISE
    if bool(rank_changes.get("is_down")):
        return OrganicVisibilityKeywordStatus.FALL
    return OrganicVisibilityKeywordStatus.STABLE


def _observation_dates(
    keywords: list[OrganicVisibilityKeyword],
) -> tuple[str | None, str | None, str | None]:
    current_times = sorted(item.last_updated_at for item in keywords if item.last_updated_at)
    previous_times = sorted(item.previous_updated_at for item in keywords if item.previous_updated_at)
    current_time = current_times[-1] if current_times else None
    previous_time = previous_times[-1] if previous_times else None
    return (
        current_time[:10] if current_time else None,
        previous_time[:10] if previous_time else None,
        current_time,
    )


def _normalize_target(value: str, scope: str) -> str:
    text = value.strip()
    if not text:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "OrganicVisibility target 不能为空")
    parsed = urlparse(text if "://" in text else f"https://{text}")
    if not parsed.hostname:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "OrganicVisibility target 必须是有效 domain 或 URL")
    if scope == "exact":
        if parsed.scheme not in {"http", "https"}:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "OrganicVisibility exact target 必须是 HTTP/HTTPS URL")
        return parsed._replace(fragment="").geturl()
    host = parsed.hostname.lower()
    return host[4:] if host.startswith("www.") else host


def _validate_history_dates(date_from: str | None, date_to: str | None) -> None:
    values: list[date] = []
    for raw in (date_from, date_to):
        if not raw:
            continue
        try:
            values.append(date.fromisoformat(raw))
        except ValueError as exc:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "OrganicVisibility 日期必须使用 YYYY-MM-DD") from exc
    if len(values) == 2 and values[0] > values[1]:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "OrganicVisibility date_from 不能晚于 date_to")


def _first_dict(value: object) -> dict[str, object]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
