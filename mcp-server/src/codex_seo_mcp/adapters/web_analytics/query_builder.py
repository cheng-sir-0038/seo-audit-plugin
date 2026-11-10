from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


_SESSION_METRICS = (
    "sessions",
    "activeUsers",
    "engagedSessions",
    "engagementRate",
    "keyEvents",
    "sessionKeyEventRate",
    "totalRevenue",
)
_PAGE_METRICS = (
    "activeUsers",
    "screenPageViews",
    "userEngagementDuration",
    "keyEvents",
    "userKeyEventRate",
)
_VIEW_CONFIG: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "overview": ((), _SESSION_METRICS, "sessions"),
    "landing_pages": (("hostName", "landingPage"), _SESSION_METRICS, "sessions"),
    "countries": (("country", "countryId"), _SESSION_METRICS, "sessions"),
    "country_pages": (
        ("country", "countryId", "hostName", "pagePath"),
        _PAGE_METRICS,
        "screenPageViews",
    ),
    "devices": (("deviceCategory",), _SESSION_METRICS, "sessions"),
    "daily": (("date",), _SESSION_METRICS, "sessions"),
}


@dataclass(frozen=True, slots=True)
class WebAnalyticsReportSpec:
    """Stable GA4 report shape shared by current and comparison periods."""

    view: str
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    order_metric: str
    countries: tuple[str, ...]
    site_domain: str | None
    limit: int
    offset: int

    def body(self, period: tuple[str, str]) -> dict[str, object]:
        start_date, end_date = period
        return {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": name} for name in self.dimensions],
            "metrics": [{"name": name} for name in self.metrics],
            "metricAggregations": ["TOTAL"],
            "dimensionFilter": _dimension_filter(
                list(self.countries),
                site_domain=self.site_domain,
            ),
            "orderBys": [
                {
                    "metric": {"metricName": self.order_metric},
                    "desc": True,
                }
            ],
            "limit": str(self.limit),
            "offset": str(self.offset),
            "keepEmptyRows": False,
        }


class WebAnalyticsQueryBuilder:
    """Validate user-facing report options and build the GA4 request shape."""

    def build(
        self,
        *,
        view: str,
        country_codes: list[str],
        site_domain: str | None,
        limit: int,
        offset: int,
    ) -> WebAnalyticsReportSpec:
        selected_view = str(view or "").strip().lower()
        if selected_view not in _VIEW_CONFIG:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                f"WebAnalytics view 不支持：{selected_view}",
            )
        if not 1 <= limit <= 10_000:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "WebAnalytics limit 必须在 1-10000",
            )
        if offset < 0:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "WebAnalytics offset 不能小于 0",
            )

        dimensions, metrics, order_metric = _VIEW_CONFIG[selected_view]
        return WebAnalyticsReportSpec(
            view=selected_view,
            dimensions=dimensions,
            metrics=metrics,
            order_metric=order_metric,
            countries=tuple(_country_codes(country_codes)),
            site_domain=_site_domain(site_domain),
            limit=limit,
            offset=offset,
        )


def _dimension_filter(
    countries: list[str],
    *,
    site_domain: str | None,
) -> dict[str, object]:
    expressions: list[dict[str, object]] = [
        {
            "filter": {
                "fieldName": "sessionDefaultChannelGroup",
                "stringFilter": {
                    "matchType": "EXACT",
                    "value": "Organic Search",
                },
            }
        }
    ]

    if site_domain:
        expressions.append(
            {
                "filter": {
                    "fieldName": "hostName",
                    "stringFilter": {
                        "matchType": "FULL_REGEXP",
                        "value": rf"(^|.*\.){re.escape(site_domain)}$",
                        "caseSensitive": False,
                    },
                }
            }
        )

    if countries:
        expressions.append(
            {
                "filter": {
                    "fieldName": "countryId",
                    "inListFilter": {
                        "values": countries,
                        "caseSensitive": False,
                    },
                }
            }
        )

    if len(expressions) == 1:
        return expressions[0]
    return {"andGroup": {"expressions": expressions}}


def _site_domain(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text if "://" in text else f"https://{text}"
    host = (urlsplit(candidate).hostname or "").lower().rstrip(".")
    if not host:
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "WebAnalytics site_domain 必须包含有效主机名",
        )
    return host[4:] if host.startswith("www.") else host


def _country_codes(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip().upper()
        if len(value) != 2 or not value.isalpha():
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "WebAnalytics country_codes 必须使用 ISO alpha-2，例如 IN/TR",
            )
        if value not in result:
            result.append(value)
    return result
