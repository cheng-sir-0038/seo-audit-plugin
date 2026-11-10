from __future__ import annotations

import re
from dataclasses import dataclass, field

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.page_ownership import TargetPageOwnershipState
from codex_seo_mcp.models.search_appearance import (
    MetricTrend,
    PresentationState,
    SearchAppearanceAction,
    SearchAppearanceAssessment,
    SearchAppearanceSignals,
    SearchAppearanceState,
)

SEARCH_APPEARANCE_SCHEMA_ID = "urn:codex-seo:search-appearance-assessment:v1"


@dataclass(frozen=True, slots=True)
class _SearchAppearanceContext:
    signals: SearchAppearanceSignals
    title_state: PresentationState
    snippet_state: PresentationState
    position_trend: MetricTrend
    ctr_trend: MetricTrend
    ranking_page_state: TargetPageOwnershipState

    @classmethod
    def from_signals(cls, signals: SearchAppearanceSignals) -> "_SearchAppearanceContext":
        return cls(
            signals=signals,
            title_state=_presentation_state(signals.source_title, signals.serp_title),
            snippet_state=_presentation_state(
                signals.source_description, signals.serp_snippet
            ),
            position_trend=_position_trend(
                signals.previous_position, signals.current_position
            ),
            ctr_trend=_ctr_trend(signals.previous_ctr, signals.current_ctr),
            ranking_page_state=_ranking_page_state(signals.target_page, signals.serp_url),
        )


@dataclass(slots=True)
class _SearchAppearanceDecision:
    state: SearchAppearanceState
    action: SearchAppearanceAction
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


def assess_search_appearance(
    *,
    query: str,
    market: str,
    signals: SearchAppearanceSignals,
) -> SearchAppearanceAssessment:
    """Compare source metadata, observed SERP presentation and optional CTR/position facts."""

    clean_query = str(query or "").strip()
    clean_market = str(market or "").strip().upper()
    if not clean_query:
        raise ValueError("search appearance query is required")
    if not clean_market:
        raise ValueError("search appearance market is required")

    context = _SearchAppearanceContext.from_signals(signals)
    decision = _decide_search_appearance(context)
    _append_search_appearance_evidence(context, decision)
    decision.unknowns = _dedupe(decision.unknowns)

    return SearchAppearanceAssessment(
        query=clean_query,
        market=clean_market,
        state=decision.state,
        title_state=context.title_state,
        snippet_state=context.snippet_state,
        position_trend=context.position_trend,
        ctr_trend=context.ctr_trend,
        ranking_page_state=context.ranking_page_state,
        reasons=decision.reasons,
        recommended_action=decision.action,
        unknowns=decision.unknowns,
        confidence=_search_appearance_confidence(decision),
    )


def _decide_search_appearance(
    context: _SearchAppearanceContext,
) -> _SearchAppearanceDecision:
    signals = context.signals
    if signals.source_title_count == 0 or not _clean(signals.source_title):
        return _SearchAppearanceDecision(
            state=SearchAppearanceState.SOURCE_METADATA_ISSUE,
            action=SearchAppearanceAction.FIX_SOURCE_METADATA,
            reasons=["页面当前没有可用的源码 Title；这是页面声明问题，不需要用 SERP 改写来解释。"],
        )
    if signals.source_title_count > 1:
        return _SearchAppearanceDecision(
            state=SearchAppearanceState.SOURCE_METADATA_ISSUE,
            action=SearchAppearanceAction.FIX_SOURCE_METADATA,
            reasons=["页面当前存在多个 Title 声明，需要先统一页面真实标题来源。"],
        )
    if context.ranking_page_state is TargetPageOwnershipState.MISMATCHED:
        return _SearchAppearanceDecision(
            state=SearchAppearanceState.TARGET_PAGE_MISMATCH,
            action=SearchAppearanceAction.INVESTIGATE_PAGE_OWNERSHIP,
            reasons=["当前 SERP 展示的 Ranking URL 与预期 Target Page 不一致；应先处理页面职责，而不是只改标题文案。"],
        )
    if (
        context.ctr_trend is MetricTrend.DECLINING
        and context.position_trend is MetricTrend.DECLINING
    ):
        return _SearchAppearanceDecision(
            state=SearchAppearanceState.RANKING_CHANGE_PRESENT,
            action=SearchAppearanceAction.DIAGNOSE_RANKING_DECLINE,
            reasons=["CTR 与排名位置同时恶化，排名变化本身已经是重要解释因素；不能把 CTR 下降直接归因于标题/摘要改写。"],
        )
    if (
        context.ctr_trend is MetricTrend.DECLINING
        and context.position_trend in {MetricTrend.STABLE, MetricTrend.IMPROVING}
        and (
            context.title_state is PresentationState.DIFFERENT
            or context.snippet_state is PresentationState.DIFFERENT
        )
    ):
        return _SearchAppearanceDecision(
            state=SearchAppearanceState.PRESENTATION_CHANGE_CANDIDATE,
            action=SearchAppearanceAction.COMPARE_SERP_COPY_AND_QUERY_INTENT,
            reasons=["排名基本稳定/改善但 CTR 下滑，同时当前 SERP 展示与页面声明不同；搜索展示是值得调查的候选原因，但还不是已确认因果。"],
        )
    if (
        context.title_state is PresentationState.DIFFERENT
        or context.snippet_state is PresentationState.DIFFERENT
    ):
        return _SearchAppearanceDecision(
            state=SearchAppearanceState.REWRITE_OBSERVED,
            action=SearchAppearanceAction.MONITOR_SERP_PRESENTATION,
            reasons=["可以确认 Google 当前展示与页面源码声明不同；改写本身不是 SEO 错误，也不能单独证明 CTR/排名受损。"],
        )
    if (
        context.title_state is PresentationState.UNKNOWN
        and context.snippet_state is PresentationState.UNKNOWN
    ):
        return _SearchAppearanceDecision(
            state=SearchAppearanceState.INSUFFICIENT_EVIDENCE,
            action=SearchAppearanceAction.COLLECT_SERP_QUERY_EVIDENCE,
            reasons=["当前缺少 Query 级 SERP 展示证据，无法判断 Google 是否改写标题/摘要。"],
            unknowns=["serp_presentation"],
        )
    return _SearchAppearanceDecision(
        state=SearchAppearanceState.NO_MATERIAL_ISSUE,
        action=SearchAppearanceAction.KEEP_CURRENT_PRESENTATION,
        reasons=["当前源码与已观察 SERP 展示没有发现需要处理的明显冲突。"],
    )


def _append_search_appearance_evidence(
    context: _SearchAppearanceContext,
    decision: _SearchAppearanceDecision,
) -> None:
    signals = context.signals
    if signals.source_description_count > 1:
        decision.reasons.append(
            "页面存在多个 Meta Description；即使 Google 可以动态生成 snippet，也建议先统一页面自己的描述声明。"
        )
    if context.ctr_trend is MetricTrend.UNKNOWN:
        decision.unknowns.append("ctr_trend")
    if context.position_trend is MetricTrend.UNKNOWN:
        decision.unknowns.append("position_trend")
    if (
        context.ranking_page_state is TargetPageOwnershipState.UNKNOWN
        and signals.target_page
    ):
        decision.unknowns.append("ranking_url")


def _search_appearance_confidence(
    decision: _SearchAppearanceDecision,
) -> Confidence:
    if decision.state is SearchAppearanceState.INSUFFICIENT_EVIDENCE:
        return Confidence.LOW
    if not decision.unknowns and decision.state in {
        SearchAppearanceState.SOURCE_METADATA_ISSUE,
        SearchAppearanceState.TARGET_PAGE_MISMATCH,
        SearchAppearanceState.REWRITE_OBSERVED,
        SearchAppearanceState.NO_MATERIAL_ISSUE,
    }:
        return Confidence.HIGH
    return Confidence.MEDIUM



def _presentation_state(source: str | None, serp: str | None) -> PresentationState:
    source_clean = _normalize_text(source)
    serp_clean = _normalize_text(serp)
    if not source_clean:
        return PresentationState.SOURCE_MISSING
    if not serp_clean:
        return PresentationState.UNKNOWN
    return PresentationState.MATCHES_SOURCE if source_clean == serp_clean else PresentationState.DIFFERENT


def _position_trend(previous: float | None, current: float | None) -> MetricTrend:
    if previous is None or current is None:
        return MetricTrend.UNKNOWN
    delta = float(current) - float(previous)
    if delta >= 0.5:
        return MetricTrend.DECLINING
    if delta <= -0.5:
        return MetricTrend.IMPROVING
    return MetricTrend.STABLE


def _ctr_trend(previous: float | None, current: float | None) -> MetricTrend:
    if previous is None or current is None:
        return MetricTrend.UNKNOWN
    delta = float(current) - float(previous)
    # CTR is expressed as 0..1; 0.005 means a 0.5 percentage-point movement.
    if delta <= -0.005:
        return MetricTrend.DECLINING
    if delta >= 0.005:
        return MetricTrend.IMPROVING
    return MetricTrend.STABLE


def _ranking_page_state(
    target_page: str | None, serp_url: str | None
) -> TargetPageOwnershipState:
    target = _clean(target_page)
    observed = _clean(serp_url)
    if not target or not observed:
        return TargetPageOwnershipState.UNKNOWN
    return (
        TargetPageOwnershipState.MATCHED
        if _normalize_url(target) == _normalize_url(observed)
        else TargetPageOwnershipState.MISMATCHED
    )


def _normalize_text(value: str | None) -> str:
    text = _clean(value)
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _normalize_url(value: str) -> str:
    return value.rstrip("/").casefold()


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        if item not in result:
            result.append(item)
    return result
