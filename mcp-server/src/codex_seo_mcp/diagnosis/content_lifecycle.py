from __future__ import annotations

from dataclasses import dataclass, field

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.content_lifecycle import (
    ContentLifecycleAction,
    ContentLifecycleAssessment,
    ContentLifecycleSignals,
    ContentLifecycleState,
    FitState,
    FreshnessState,
    GapState,
    PurposeState,
    TrendState,
    ValueState,
)
from codex_seo_mcp.models.page_ownership import PageOwnershipState

CONTENT_LIFECYCLE_SCHEMA_ID = "urn:codex-seo:content-lifecycle-assessment:v1"


@dataclass(frozen=True, slots=True)
class _ContentLifecycleContext:
    page_url: str
    market: str
    signals: ContentLifecycleSignals
    merge_target: str | None
    unknowns: tuple[str, ...]

    @classmethod
    def from_input(
        cls,
        *,
        page_url: str,
        market: str,
        signals: ContentLifecycleSignals,
    ) -> "_ContentLifecycleContext":
        page = str(page_url or "").strip()
        clean_market = str(market or "").strip().upper()
        if not page:
            raise ValueError("content lifecycle page_url is required")
        if not clean_market:
            raise ValueError("content lifecycle market is required")
        return cls(
            page_url=page,
            market=clean_market,
            signals=signals,
            merge_target=(
                signals.replacement_url.strip() if signals.replacement_url else None
            ),
            unknowns=tuple(_unknowns(signals)),
        )


@dataclass(slots=True)
class _ContentLifecycleDecision:
    action: ContentLifecycleAction
    state: ContentLifecycleState
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


def assess_content_lifecycle(
    *,
    page_url: str,
    market: str,
    signals: ContentLifecycleSignals,
) -> ContentLifecycleAssessment:
    """Choose a content lifecycle action from normalized SEO evidence."""

    context = _ContentLifecycleContext.from_input(
        page_url=page_url,
        market=market,
        signals=signals,
    )
    decision = _decide_content_lifecycle(context)
    _append_content_investment_warning(context, decision)
    unknowns = _dedupe([*context.unknowns, *decision.unknowns])

    return ContentLifecycleAssessment(
        page_url=context.page_url,
        market=context.market,
        action=decision.action,
        merge_target=(
            context.merge_target
            if decision.action
            in {ContentLifecycleAction.MERGE, ContentLifecycleAction.REDIRECT}
            else None
        ),
        state=decision.state,
        signals=context.signals,
        reasons=decision.reasons,
        unknowns=unknowns,
        confidence=_content_lifecycle_confidence(decision.state, unknowns),
    )


def _decide_content_lifecycle(
    context: _ContentLifecycleContext,
) -> _ContentLifecycleDecision:
    signals = context.signals
    if (
        signals.page_ownership_state is PageOwnershipState.PROBABLE_CANNIBALIZATION
        and signals.distinct_purpose is PurposeState.NOT_DISTINCT
    ):
        if context.merge_target:
            return _ContentLifecycleDecision(
                action=ContentLifecycleAction.MERGE,
                state=ContentLifecycleState.ACTIONABLE,
                reasons=[
                    "页面职责证据已支持明显内耗，且当前页面没有独立用户目的；优先合并到更合适的主页面。"
                ],
            )
        return _ContentLifecycleDecision(
            action=ContentLifecycleAction.MONITOR,
            state=ContentLifecycleState.NEEDS_TARGET,
            reasons=["页面职责证据支持合并方向，但还没有明确合并目标，不能直接删除或重定向。"],
            unknowns=["merge_target"],
        )

    if (
        signals.content_value is ValueState.LOW
        and signals.distinct_purpose is PurposeState.NOT_DISTINCT
    ):
        if context.merge_target:
            return _ContentLifecycleDecision(
                action=ContentLifecycleAction.REDIRECT,
                state=ContentLifecycleState.ACTIONABLE,
                reasons=[
                    "当前页面价值低且没有独立用户目的，并存在更合适的替代页面；建议移除旧页并重定向到替代页。"
                ],
            )
        return _ContentLifecycleDecision(
            action=ContentLifecycleAction.REMOVE,
            state=ContentLifecycleState.ACTIONABLE,
            reasons=[
                "当前页面价值低且没有独立用户目的，也没有已知替代页面；可考虑直接移除并返回正确的删除状态。"
            ],
        )

    if signals.visibility_trend is TrendState.DECLINING:
        return _declining_visibility_decision(signals)

    if (
        signals.freshness is FreshnessState.OUTDATED
        and signals.content_value in {ValueState.HIGH, ValueState.MEDIUM}
        and signals.intent_fit in {FitState.STRONG, FitState.MEDIUM}
    ):
        return _ContentLifecycleDecision(
            action=ContentLifecycleAction.REFRESH,
            state=ContentLifecycleState.ACTIONABLE,
            reasons=[
                "页面仍有业务/搜索价值且职责匹配，但内容事实已经过时；建议主动刷新，不需要等到排名明显下跌。"
            ],
        )

    if (
        signals.visibility_trend in {TrendState.STABLE, TrendState.GROWING}
        and signals.freshness is FreshnessState.CURRENT
        and signals.coverage_gap in {GapState.LOW, GapState.UNKNOWN}
        and signals.intent_fit in {FitState.STRONG, FitState.MEDIUM}
    ):
        return _ContentLifecycleDecision(
            action=ContentLifecycleAction.KEEP,
            state=ContentLifecycleState.HEALTHY,
            reasons=[
                "当前页面表现稳定/增长，内容仍新且页面职责匹配，没有证据支持为了“保持新鲜”而重写或删除。"
            ],
        )

    return _ContentLifecycleDecision(
        action=ContentLifecycleAction.MONITOR,
        state=ContentLifecycleState.INSUFFICIENT_EVIDENCE,
        reasons=[
            "当前证据不足以支持 refresh/expand/merge/remove 等高成本动作，先保持并补齐关键证据。"
        ],
    )



def _declining_visibility_decision(
    signals: ContentLifecycleSignals,
) -> _ContentLifecycleDecision:
    if signals.demand_trend is TrendState.DECLINING:
        return _ContentLifecycleDecision(
            action=ContentLifecycleAction.MONITOR,
            state=ContentLifecycleState.DEMAND_DECLINE,
            reasons=[
                "页面可见性与主题需求同时下降，优先确认市场需求变化；单纯刷新内容未必能恢复表现。"
            ],
        )
    if signals.intent_fit is FitState.WEAK:
        return _ContentLifecycleDecision(
            action=ContentLifecycleAction.MONITOR,
            state=ContentLifecycleState.INTENT_MISMATCH,
            reasons=[
                "当前页面与搜索意图匹配较弱，先确认页面职责/承接方式，不建议只靠增加内容长度解决。"
            ],
        )
    if signals.freshness is FreshnessState.OUTDATED:
        return _ContentLifecycleDecision(
            action=ContentLifecycleAction.REFRESH,
            state=ContentLifecycleState.ACTIONABLE,
            reasons=[
                "搜索需求没有同步下滑，而页面内容已过时；优先更新失效事实、示例、产品信息或用户任务步骤。"
            ],
        )
    if signals.coverage_gap in {GapState.HIGH, GapState.MEDIUM}:
        return _ContentLifecycleDecision(
            action=ContentLifecycleAction.EXPAND,
            state=ContentLifecycleState.ACTIONABLE,
            reasons=[
                "需求仍在且页面方向基本匹配，但当前页面存在明显覆盖缺口；优先扩充现有页面而不是新建重复内容。"
            ],
        )
    return _ContentLifecycleDecision(
        action=ContentLifecycleAction.MONITOR,
        state=ContentLifecycleState.INSUFFICIENT_EVIDENCE,
        reasons=[
            "已经观察到可见性下降，但现有证据还不能区分内容过时、覆盖不足、竞争变化或其他原因。"
        ],
    )

def _append_content_investment_warning(
    context: _ContentLifecycleContext,
    decision: _ContentLifecycleDecision,
) -> None:
    if (
        decision.action in {ContentLifecycleAction.REFRESH, ContentLifecycleAction.EXPAND}
        and context.signals.content_value is ValueState.LOW
    ):
        decision.reasons.append(
            "注意：当前业务价值信号偏低，执行内容投入前应再次确认这个页面仍值得维护。"
        )


def _content_lifecycle_confidence(
    state: ContentLifecycleState,
    unknowns: list[str],
) -> Confidence:
    if state in {
        ContentLifecycleState.INSUFFICIENT_EVIDENCE,
        ContentLifecycleState.NEEDS_TARGET,
    }:
        return Confidence.LOW
    if not unknowns and state in {
        ContentLifecycleState.ACTIONABLE,
        ContentLifecycleState.HEALTHY,
    }:
        return Confidence.HIGH
    return Confidence.MEDIUM



def _unknowns(signals: ContentLifecycleSignals) -> list[str]:
    pairs = (
        ("visibility_trend", signals.visibility_trend.value),
        ("demand_trend", signals.demand_trend.value),
        ("intent_fit", signals.intent_fit.value),
        ("freshness", signals.freshness.value),
        ("coverage_gap", signals.coverage_gap.value),
        ("content_value", signals.content_value.value),
        ("distinct_purpose", signals.distinct_purpose.value),
    )
    return [name for name, value in pairs if value == "unknown"]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        if item not in result:
            result.append(item)
    return result
