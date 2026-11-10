from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class OrganicVisibilityKeywordStatus(StrEnum):
    LOST = "lost"
    NEW = "new"
    RISE = "rise"
    FALL = "fall"
    STABLE = "stable"


@dataclass(slots=True)
class OrganicVisibilityMarket:
    """Provider-neutral market context for organic visibility evidence."""

    country: str
    language: str


@dataclass(slots=True)
class OrganicVisibilityObservation:
    """Freshness/comparison metadata that affects how visibility evidence is interpreted."""

    data_updated_at: str | None = None
    current_date: str | None = None
    compare_date: str | None = None
    coverage_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OrganicVisibilityOverview:
    total_keywords: int | None = None
    top3_keywords: int | None = None
    top10_keywords: int | None = None
    top100_keywords: int | None = None
    estimated_traffic: float | None = None
    new_keywords: int | None = None
    up_keywords: int | None = None
    down_keywords: int | None = None
    lost_keywords: int | None = None


@dataclass(slots=True)
class OrganicVisibilityKeyword:
    query: str
    current_position: int | None
    previous_position: int | None
    current_url: str | None
    previous_url: str | None
    status: OrganicVisibilityKeywordStatus
    search_volume: float | None = None
    estimated_traffic: float | None = None
    serp_features: list[str] = field(default_factory=list)
    last_updated_at: str | None = None
    previous_updated_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, OrganicVisibilityKeywordStatus):
            self.status = OrganicVisibilityKeywordStatus(str(self.status))


@dataclass(slots=True)
class OrganicVisibilityPage:
    url: str
    keyword_count: int | None = None
    estimated_traffic: float | None = None
    new_keywords: int | None = None
    up_keywords: int | None = None
    down_keywords: int | None = None
    lost_keywords: int | None = None


@dataclass(slots=True)
class OrganicVisibilityHistoryPoint:
    date: str
    total_keywords: int | None = None
    top3_keywords: int | None = None
    top10_keywords: int | None = None
    top100_keywords: int | None = None
    estimated_traffic: float | None = None
    new_keywords: int | None = None
    up_keywords: int | None = None
    down_keywords: int | None = None
    lost_keywords: int | None = None


@dataclass(slots=True)
class OrganicVisibilitySnapshot:
    """Locally observed weekly aggregate for report/trend continuity.

    This is a local observation record, not a claim that the upstream provider exposed a weekly
    historical row for the same date.
    """

    week: str
    observed_at: str
    provider: str
    provider_data_updated_at: str | None = None
    total_keywords: int | None = None
    top3_keywords: int | None = None
    top10_keywords: int | None = None
    top100_keywords: int | None = None
    estimated_traffic: float | None = None
    new_keywords: int | None = None
    up_keywords: int | None = None
    down_keywords: int | None = None
    lost_keywords: int | None = None


@dataclass(slots=True)
class OrganicVisibility:
    """Third-party organic ranking/visibility observations for any public domain or URL.

    This contract deliberately does not contain GSC clicks, impressions or CTR. Provider identity,
    source kind, fetched_at and top-level warnings live in CapabilityResult to avoid a second source
    of truth inside this payload.
    """

    target: str
    target_scope: str
    market: OrganicVisibilityMarket
    search_engine: str
    observation: OrganicVisibilityObservation
    overview: OrganicVisibilityOverview | None = None
    keywords: list[OrganicVisibilityKeyword] = field(default_factory=list)
    pages: list[OrganicVisibilityPage] = field(default_factory=list)
    history: list[OrganicVisibilityHistoryPoint] = field(default_factory=list)
    snapshots: list[OrganicVisibilitySnapshot] = field(default_factory=list)
