from __future__ import annotations

from datetime import date
from typing import Protocol

from codex_seo_mcp.adapters.web_analytics.mapper import WebAnalyticsMapper
from codex_seo_mcp.adapters.web_analytics.query_builder import (
    WebAnalyticsQueryBuilder,
    WebAnalyticsReportSpec,
)
from codex_seo_mcp.clients.ga4 import Ga4Client, Ga4ReportResponse
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.web_analytics import (
    WebAnalytics,
    WebAnalyticsPeriod,
)


class Ga4ReportClient(Protocol):
    async def run_report(
        self,
        property_id: str,
        body: dict[str, object],
    ) -> Ga4ReportResponse: ...


class WebAnalyticsAdapter:
    """Coordinate one analytics job without owning GA4 request or mapping details."""

    capability = "WebAnalytics"

    def __init__(
        self,
        client: Ga4ReportClient | None = None,
        *,
        query_builder: WebAnalyticsQueryBuilder | None = None,
        mapper: WebAnalyticsMapper | None = None,
    ) -> None:
        self.client = client or Ga4Client()
        self.query_builder = query_builder or WebAnalyticsQueryBuilder()
        self.mapper = mapper or WebAnalyticsMapper()

    async def analyze(
        self,
        *,
        property_id: str,
        start_date: str,
        end_date: str,
        view: str = "overview",
        compare_start_date: str | None = None,
        compare_end_date: str | None = None,
        country_codes: list[str] | None = None,
        site_domain: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> CapabilityResult[WebAnalytics]:
        clean_property = _property_id(property_id)
        _validate_dates(start_date, end_date, label="current")
        previous_period = _comparison_period(
            compare_start_date,
            compare_end_date,
        )
        report_spec = self.query_builder.build(
            view=view,
            country_codes=country_codes or [],
            site_domain=site_domain,
            limit=limit,
            offset=offset,
        )

        current_response, current = await self._load_period(
            clean_property,
            report_spec,
            (start_date, end_date),
        )
        metadata = self.mapper.map_metadata(current_response.payload)
        period_metadata = [("当前", metadata)]

        previous: WebAnalyticsPeriod | None = None
        if previous_period is not None:
            previous_response, previous = await self._load_period(
                clean_property,
                report_spec,
                previous_period,
            )
            period_metadata.append(("对比", self.mapper.map_metadata(previous_response.payload)))

        data = WebAnalytics(
            property_id=clean_property,
            scope="organic_search",
            view=report_spec.view,
            site_domain=report_spec.site_domain,
            dimensions=list(report_spec.dimensions),
            metrics=list(report_spec.metrics),
            current=current,
            previous=previous,
            currency_code=metadata.currency_code,
            time_zone=metadata.time_zone,
        )

        factory = (
            CapabilityResult.partial
            if any(item.has_data_gaps for _, item in period_metadata)
            else CapabilityResult.complete
        )
        return factory(
            capability=self.capability,
            provider="ga4",
            source_kind=CapabilitySourceKind.FIRST_PARTY,
            data=data,
            warnings=_pagination_warnings(current, previous, offset=report_spec.offset) + [
                f"GA4 {label}报表：{warning}"
                for label, item in period_metadata for warning in item.warnings
            ],
        )

    async def _load_period(
        self,
        property_id: str,
        report_spec: WebAnalyticsReportSpec,
        period: tuple[str, str],
    ) -> tuple[Ga4ReportResponse, WebAnalyticsPeriod]:
        response = await self.client.run_report(
            property_id,
            report_spec.body(period),
        )
        start_date, end_date = period
        return (
            response,
            self.mapper.map_period(
                response.payload,
                start_date=start_date,
                end_date=end_date,
                expected_dimensions=report_spec.dimensions,
                expected_metrics=report_spec.metrics,
            ),
        )


def _comparison_period(
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str] | None:
    if (start_date is None) != (end_date is None):
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "compare_start_date 和 compare_end_date 必须同时提供",
        )
    if start_date is not None and end_date is not None:
        _validate_dates(start_date, end_date, label="compare")
        return start_date, end_date
    return None


def _property_id(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("properties/"):
        text = text.split("/", 1)[1]
    if not text.isdigit():
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "WebAnalytics property_id 必须是数字 GA4 Property ID",
        )
    return text


def _validate_dates(start: str, end: str, *, label: str) -> None:
    try:
        start_value = date.fromisoformat(start)
        end_value = date.fromisoformat(end)
        if start_value.isoformat() != start or end_value.isoformat() != end:
            raise ValueError("noncanonical date")
    except (TypeError, ValueError) as exc:
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            f"WebAnalytics {label} 日期必须使用 YYYY-MM-DD",
        ) from exc
    if start_value > end_value:
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            f"WebAnalytics {label} start_date 不能晚于 end_date",
        )


def _pagination_warnings(
    current: WebAnalyticsPeriod,
    previous: WebAnalyticsPeriod | None,
    *,
    offset: int,
) -> list[str]:
    warnings: list[str] = []
    for label, period in (("当前", current), ("对比", previous)):
        if period is None:
            continue
        if offset > 0:
            warnings.append(
                f"GA4 {label} report row_count={period.row_count}，offset={offset}，"
                f"已跳过前 {offset} 行，本页返回 {len(period.rows)} 行。"
                "这是后续分页，不是前 N 条结果；空页需结合总行数判断，不能直接当作查询无数据。"
            )
        elif period.row_count > len(period.rows):
            warnings.append(
                f"GA4 {label} report row_count={period.row_count}，"
                f"本次只返回 {len(period.rows)} 行 Top-N 数据。"
            )
    return warnings
