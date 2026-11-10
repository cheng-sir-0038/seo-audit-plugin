from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum

from codex_seo_mcp.models.common import Confidence


class KeywordOpportunityScenario(StrEnum):
    METRIC_LOOKUP = "metric_lookup"
    SITE_RESEARCH = "site_research"
    PAGE_RESEARCH = "page_research"
    OPPORTUNITY_DISCOVERY = "opportunity_discovery"
    COMPETITOR_GAP = "competitor_gap"


class KeywordOpportunityStatus(StrEnum):
    NEEDS_INPUT = "needs_input"
    FACTS_ONLY = "facts_only"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ASSESSED = "assessed"


class KeywordFitState(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    UNKNOWN = "unknown"


class KeywordDemandLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class KeywordSignalState(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    NONE = "none"
    UNKNOWN = "unknown"


class KeywordOpportunityLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class KeywordOpportunityTiming(StrEnum):
    NOW = "now"
    LATER = "later"
    TEST = "test"
    IGNORE = "ignore"


class KeywordOpportunityAction(StrEnum):
    IGNORE = "ignore"
    LATER = "later"
    OPTIMIZE_EXISTING_PAGE = "optimize_existing_page"
    EXPAND_EXISTING_PAGE = "expand_existing_page"
    MONITOR = "monitor"
    CREATE_NEW_LANDING_PAGE = "create_new_landing_page"
    CREATE_NEW_ARTICLE = "create_new_article"


KEYWORD_OPPORTUNITY_SCENARIOS = frozenset(item.value for item in KeywordOpportunityScenario)


@dataclass(slots=True)
class KeywordOpportunitySignals:
    """Normalized diagnosis-layer signals used to judge a keyword opportunity."""

    search_volume: int | None = None
    keyword_difficulty: float | None = None
    intents: list[str] = field(default_factory=list)
    business_fit: KeywordFitState = KeywordFitState.UNKNOWN
    demand_level: KeywordDemandLevel = KeywordDemandLevel.UNKNOWN
    intent_fit: KeywordFitState = KeywordFitState.UNKNOWN
    page_fit: KeywordFitState = KeywordFitState.UNKNOWN
    existing_signal: KeywordSignalState = KeywordSignalState.UNKNOWN
    gap_signal: KeywordSignalState = KeywordSignalState.UNKNOWN
    serp_fit: KeywordFitState = KeywordFitState.UNKNOWN
    current_position: int | None = None
    current_ranking_url: str | None = None

    def __post_init__(self) -> None:
        self.business_fit = _enum(self.business_fit, KeywordFitState)
        self.demand_level = _enum(self.demand_level, KeywordDemandLevel)
        self.intent_fit = _enum(self.intent_fit, KeywordFitState)
        self.page_fit = _enum(self.page_fit, KeywordFitState)
        self.existing_signal = _enum(self.existing_signal, KeywordSignalState)
        self.gap_signal = _enum(self.gap_signal, KeywordSignalState)
        self.serp_fit = _enum(self.serp_fit, KeywordFitState)


@dataclass(slots=True)
class KeywordOpportunityAssessment:
    """Provider-neutral derived keyword decision."""

    scenario: KeywordOpportunityScenario
    keyword: str
    market: str
    status: KeywordOpportunityStatus
    value_level: KeywordOpportunityLevel | None
    feasibility_level: KeywordOpportunityLevel | None
    opportunity_level: KeywordOpportunityLevel | None
    recommended_timing: KeywordOpportunityTiming | None
    recommended_action: KeywordOpportunityAction | None
    target_domain: str | None = None
    target_page: str | None = None
    competitor_domains: list[str] = field(default_factory=list)
    signals: KeywordOpportunitySignals = field(default_factory=KeywordOpportunitySignals)
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def __post_init__(self) -> None:
        self.scenario = _enum(self.scenario, KeywordOpportunityScenario)
        self.status = _enum(self.status, KeywordOpportunityStatus)
        self.value_level = _optional_enum(self.value_level, KeywordOpportunityLevel)
        self.feasibility_level = _optional_enum(self.feasibility_level, KeywordOpportunityLevel)
        self.opportunity_level = _optional_enum(self.opportunity_level, KeywordOpportunityLevel)
        self.recommended_timing = _optional_enum(self.recommended_timing, KeywordOpportunityTiming)
        self.recommended_action = _optional_enum(self.recommended_action, KeywordOpportunityAction)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _enum(value, enum_type):  # noqa: ANN001, ANN202
    return value if isinstance(value, enum_type) else enum_type(str(value))


def _optional_enum(value, enum_type):  # noqa: ANN001, ANN202
    return None if value is None else _enum(value, enum_type)
