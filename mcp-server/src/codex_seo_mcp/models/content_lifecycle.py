from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.page_ownership import PageOwnershipState

class ContentLifecycleState(StrEnum):
    ACTIONABLE = "actionable"
    NEEDS_TARGET = "needs_target"
    DEMAND_DECLINE = "demand_decline"
    INTENT_MISMATCH = "intent_mismatch"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    HEALTHY = "healthy"


class ContentLifecycleAction(StrEnum):
    REFRESH = "refresh"
    EXPAND = "expand"
    MERGE = "merge"
    KEEP = "keep"
    REMOVE = "remove"
    REDIRECT = "redirect"
    MONITOR = "monitor"


class TrendState(StrEnum):
    DECLINING = "declining"
    STABLE = "stable"
    GROWING = "growing"
    UNKNOWN = "unknown"


class FitState(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    UNKNOWN = "unknown"


class FreshnessState(StrEnum):
    CURRENT = "current"
    OUTDATED = "outdated"
    UNKNOWN = "unknown"


class GapState(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class PurposeState(StrEnum):
    DISTINCT = "distinct"
    NOT_DISTINCT = "not_distinct"
    UNKNOWN = "unknown"


class ValueState(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class ContentLifecycleSignals:
    visibility_trend: TrendState = TrendState.UNKNOWN
    demand_trend: TrendState = TrendState.UNKNOWN
    intent_fit: FitState = FitState.UNKNOWN
    freshness: FreshnessState = FreshnessState.UNKNOWN
    coverage_gap: GapState = GapState.UNKNOWN
    content_value: ValueState = ValueState.UNKNOWN
    distinct_purpose: PurposeState = PurposeState.UNKNOWN
    page_ownership_state: PageOwnershipState | None = None
    replacement_url: str | None = None

    def __post_init__(self) -> None:
        self.visibility_trend = _enum(self.visibility_trend, TrendState)
        self.demand_trend = _enum(self.demand_trend, TrendState)
        self.intent_fit = _enum(self.intent_fit, FitState)
        self.freshness = _enum(self.freshness, FreshnessState)
        self.coverage_gap = _enum(self.coverage_gap, GapState)
        self.content_value = _enum(self.content_value, ValueState)
        self.distinct_purpose = _enum(self.distinct_purpose, PurposeState)
        self.page_ownership_state = _page_ownership_state(self.page_ownership_state)


@dataclass(slots=True)
class ContentLifecycleAssessment:
    page_url: str
    market: str
    action: ContentLifecycleAction
    merge_target: str | None
    state: ContentLifecycleState
    signals: ContentLifecycleSignals
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, object]:
        return {
            "pageUrl": self.page_url,
            "market": self.market,
            "action": self.action.value,
            "mergeTarget": self.merge_target,
            "state": self.state.value,
            "signals": {
                "visibilityTrend": self.signals.visibility_trend.value,
                "demandTrend": self.signals.demand_trend.value,
                "intentFit": self.signals.intent_fit.value,
                "freshness": self.signals.freshness.value,
                "coverageGap": self.signals.coverage_gap.value,
                "contentValue": self.signals.content_value.value,
                "distinctPurpose": self.signals.distinct_purpose.value,
                "pageOwnershipState": (
                    self.signals.page_ownership_state.value
                    if self.signals.page_ownership_state is not None
                    else "unknown"
                ),
                "replacementUrl": self.signals.replacement_url,
            },
            "reasons": list(self.reasons),
            "unknowns": list(self.unknowns),
            "confidence": self.confidence.value,
        }


def _enum(value, enum_type):  # noqa: ANN001, ANN202
    return value if isinstance(value, enum_type) else enum_type(str(value))


def _page_ownership_state(value: PageOwnershipState | str | None) -> PageOwnershipState | None:
    if value is None or value == "unknown":
        return None
    return value if isinstance(value, PageOwnershipState) else PageOwnershipState(str(value))
