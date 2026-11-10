from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WebAnalyticsRow:
    """One GA4 report row with stable dimension/metric names."""

    dimensions: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class WebAnalyticsPeriod:
    """One explicit analytics observation window."""

    start_date: str
    end_date: str
    row_count: int
    rows: list[WebAnalyticsRow] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class WebAnalytics:
    """First-party GA4 behavior/conversion evidence for organic-search traffic.

    This contract describes what users did after arriving on the site. It does not contain keyword
    rankings, Search Console impressions/position, or index state.
    """

    property_id: str
    scope: str
    view: str
    site_domain: str | None
    dimensions: list[str]
    metrics: list[str]
    current: WebAnalyticsPeriod
    previous: WebAnalyticsPeriod | None = None
    currency_code: str | None = None
    time_zone: str | None = None
