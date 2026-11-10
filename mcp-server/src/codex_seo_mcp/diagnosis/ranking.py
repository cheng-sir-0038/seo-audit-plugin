from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.search_performance import SearchPerformance, SearchPerformanceRow


RANKING_COMPARISON_SCHEMA_ID = "urn:codex-seo:ranking-comparison:v1"


class TargetPageState(StrEnum):
    """Target Page 在当前 SearchPerformance 窗口中的观测状态。"""

    OBSERVED = "observed"
    NOT_OBSERVED = "not-observed"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class PerformanceSummary:
    """一个窗口内的可加总搜索表现。

    `position` 使用 impressions 加权，仍然只是 GSC average position 的汇总近似事实；
    没有可观测行时整个 summary 为 None，而不是构造零值。
    """

    clicks: float
    impressions: float
    ctr: float | None
    position: float | None


@dataclass(slots=True)
class QueryPageChange:
    """同一 Query × Page 在前后窗口中的观测结果。"""

    page: str
    prior: PerformanceSummary | None
    current: PerformanceSummary | None


@dataclass(slots=True)
class RankingComparison:
    """排名诊断的确定性比较事实，不包含因果结论。

    这个对象只回答“前后窗口发生了什么、哪些页面被观察到、Target Page 是否出现”。
    `decline-confirmed`、算法更新、内容质量等解释由 Product Skill 在更多证据下判断。
    """

    property_url: str
    query: str
    prior_window: tuple[str, str]
    current_window: tuple[str, str]
    prior: PerformanceSummary | None
    current: PerformanceSummary | None
    pages: list[QueryPageChange]
    prior_ranking_pages: list[str]
    current_ranking_pages: list[str]
    target_page: str | None
    target_page_prior_state: TargetPageState
    target_page_current_state: TargetPageState
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """返回可由任意 Host 渲染的稳定 RankingComparison wire payload。"""

        return {
            "propertyUrl": self.property_url,
            "query": self.query,
            "priorWindow": _window_payload(self.prior_window),
            "currentWindow": _window_payload(self.current_window),
            "prior": _summary_payload(self.prior),
            "current": _summary_payload(self.current),
            "pages": [
                {
                    "page": item.page,
                    "prior": _summary_payload(item.prior),
                    "current": _summary_payload(item.current),
                }
                for item in self.pages
            ],
            "priorRankingPages": list(self.prior_ranking_pages),
            "currentRankingPages": list(self.current_ranking_pages),
            "targetPage": self.target_page,
            "targetPagePriorState": self.target_page_prior_state.value,
            "targetPageCurrentState": self.target_page_current_state.value,
            "warnings": list(self.warnings),
        }


def build_ranking_comparison(
    prior: SearchPerformance,
    current: SearchPerformance,
    *,
    query: str,
    target_page: str | None = None,
) -> RankingComparison:
    """构建 Query × Page 前后窗口事实，严格保留 No Data 和多页面语义。"""

    if prior.property_url != current.property_url:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "RankingComparison 前后窗口必须属于同一个 GSC Property")
    if "page" not in prior.dimensions or "page" not in current.dimensions:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "RankingComparison 需要包含 page 维度的 SearchPerformance")

    clean_query = query.strip()
    if not clean_query:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "RankingComparison query 不能为空")

    prior_rows = _rows_for_query(prior, clean_query)
    current_rows = _rows_for_query(current, clean_query)
    prior_by_page = _group_by_page(prior_rows)
    current_by_page = _group_by_page(current_rows)
    page_names = sorted(set(prior_by_page) | set(current_by_page))

    changes = [
        QueryPageChange(
            page=page,
            prior=_summary(prior_by_page.get(page, [])),
            current=_summary(current_by_page.get(page, [])),
        )
        for page in page_names
    ]

    warnings: list[str] = []
    if not prior_rows:
        warnings.append("Prior 窗口没有返回 Query × Page 行；不能解释为此前未排名")
    if not current_rows:
        warnings.append("Current 窗口没有返回 Query × Page 行；不能解释为当前未排名")
    if len(prior_by_page) > 1 or len(current_by_page) > 1:
        warnings.append("同一 Query 存在多个 Ranking Page，诊断必须保留页面维度")

    target = target_page.strip() if target_page else None
    return RankingComparison(
        property_url=prior.property_url,
        query=clean_query,
        prior_window=(prior.start_date, prior.end_date),
        current_window=(current.start_date, current.end_date),
        prior=_summary(prior_rows),
        current=_summary(current_rows),
        pages=changes,
        prior_ranking_pages=sorted(prior_by_page),
        current_ranking_pages=sorted(current_by_page),
        target_page=target,
        target_page_prior_state=_target_state(target, prior_by_page, bool(prior_rows)),
        target_page_current_state=_target_state(target, current_by_page, bool(current_rows)),
        warnings=warnings,
    )


def _rows_for_query(data: SearchPerformance, query: str) -> list[SearchPerformanceRow]:
    # 如果 query 不在 dimensions 中，说明调用方可能已经通过 GSC filter 固定了 Query；
    # 此时 row.query=None 仍属于当前请求，不能被错误丢弃。
    has_query_dimension = "query" in data.dimensions
    if not has_query_dimension:
        return list(data.rows)
    return [row for row in data.rows if row.query == query]


def _group_by_page(rows: list[SearchPerformanceRow]) -> dict[str, list[SearchPerformanceRow]]:
    grouped: dict[str, list[SearchPerformanceRow]] = {}
    for row in rows:
        if not row.page:
            continue
        grouped.setdefault(row.page, []).append(row)
    return grouped


def _summary(rows: list[SearchPerformanceRow]) -> PerformanceSummary | None:
    if not rows:
        return None
    clicks = sum(row.clicks for row in rows)
    impressions = sum(row.impressions for row in rows)
    ctr = clicks / impressions if impressions > 0 else None
    position_weight = sum(row.position * row.impressions for row in rows)
    position = position_weight / impressions if impressions > 0 else None
    return PerformanceSummary(
        clicks=clicks,
        impressions=impressions,
        ctr=ctr,
        position=position,
    )


def _window_payload(window: tuple[str, str]) -> dict[str, str]:
    return {"startDate": window[0], "endDate": window[1]}


def _summary_payload(summary: PerformanceSummary | None) -> dict[str, float | None] | None:
    if summary is None:
        return None
    return {
        "clicks": summary.clicks,
        "impressions": summary.impressions,
        "ctr": summary.ctr,
        "position": summary.position,
    }


def _target_state(
    target_page: str | None,
    pages: dict[str, list[SearchPerformanceRow]],
    has_rows: bool,
) -> TargetPageState:
    if not target_page or not has_rows:
        return TargetPageState.UNKNOWN
    return TargetPageState.OBSERVED if target_page in pages else TargetPageState.NOT_OBSERVED
