from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.page_ownership import TargetPageOwnershipState

class SearchAppearanceAction(StrEnum):
    FIX_SOURCE_METADATA = "fix_source_metadata"
    INVESTIGATE_PAGE_OWNERSHIP = "investigate_page_ownership"
    DIAGNOSE_RANKING_DECLINE = "diagnose_ranking_decline"
    COMPARE_SERP_COPY_AND_QUERY_INTENT = "compare_serp_copy_and_query_intent"
    MONITOR_SERP_PRESENTATION = "monitor_serp_presentation"
    COLLECT_SERP_QUERY_EVIDENCE = "collect_serp_query_evidence"
    KEEP_CURRENT_PRESENTATION = "keep_current_presentation"


class PresentationState(StrEnum):
    MATCHES_SOURCE = "matches_source"
    DIFFERENT = "different"
    SOURCE_MISSING = "source_missing"
    UNKNOWN = "unknown"


class MetricTrend(StrEnum):
    DECLINING = "declining"
    STABLE = "stable"
    IMPROVING = "improving"
    UNKNOWN = "unknown"


class SearchAppearanceState(StrEnum):
    SOURCE_METADATA_ISSUE = "source_metadata_issue"
    TARGET_PAGE_MISMATCH = "target_page_mismatch"
    RANKING_CHANGE_PRESENT = "ranking_change_present"
    PRESENTATION_CHANGE_CANDIDATE = "presentation_change_candidate"
    REWRITE_OBSERVED = "rewrite_observed"
    NO_MATERIAL_ISSUE = "no_material_issue"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(slots=True)
class SearchAppearanceSignals:
    source_title: str | None = None
    source_title_count: int = 0
    source_description: str | None = None
    source_description_count: int = 0
    serp_title: str | None = None
    serp_snippet: str | None = None
    serp_url: str | None = None
    target_page: str | None = None
    previous_position: float | None = None
    current_position: float | None = None
    previous_ctr: float | None = None
    current_ctr: float | None = None


@dataclass(slots=True)
class SearchAppearanceAssessment:
    query: str
    market: str
    state: SearchAppearanceState
    title_state: PresentationState
    snippet_state: PresentationState
    position_trend: MetricTrend
    ctr_trend: MetricTrend
    ranking_page_state: TargetPageOwnershipState
    reasons: list[str] = field(default_factory=list)
    recommended_action: SearchAppearanceAction = SearchAppearanceAction.COLLECT_SERP_QUERY_EVIDENCE
    unknowns: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "market": self.market,
            "state": self.state.value,
            "titleState": self.title_state.value,
            "snippetState": self.snippet_state.value,
            "positionTrend": self.position_trend.value,
            "ctrTrend": self.ctr_trend.value,
            "rankingPageState": self.ranking_page_state.value,
            "reasons": list(self.reasons),
            "recommendedAction": self.recommended_action.value,
            "unknowns": list(self.unknowns),
            "confidence": self.confidence.value,
        }
