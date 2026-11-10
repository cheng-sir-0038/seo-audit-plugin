from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.web_analytics import (
    WebAnalyticsPeriod,
    WebAnalyticsRow,
)


@dataclass(frozen=True, slots=True)
class WebAnalyticsMetadata:
    currency_code: str | None
    time_zone: str | None
    warnings: tuple[str, ...] = ()
    has_data_gaps: bool = False


class WebAnalyticsMapper:
    """Convert GA4 report JSON into the plugin's stable analytics models."""

    def map_period(
        self,
        payload: dict[str, object],
        *,
        start_date: str,
        end_date: str,
        expected_dimensions: tuple[str, ...],
        expected_metrics: tuple[str, ...],
    ) -> WebAnalyticsPeriod:
        dimension_headers = _headers(
            payload,
            "dimensionHeaders",
            expected_dimensions,
        )
        metric_headers = _headers(
            payload,
            "metricHeaders",
            expected_metrics,
        )

        rows: list[WebAnalyticsRow] = []
        raw_rows = _optional_list(payload, "rows")
        for row_index, raw in enumerate(raw_rows):
            if not isinstance(raw, dict):
                raise _invalid_response(f"GA4 rows[{row_index}] 不是对象")
            dimension_values = _row_values(
                raw,
                "dimensionValues",
                len(dimension_headers),
                row_index=row_index,
            )
            metric_values = _row_values(
                raw,
                "metricValues",
                len(metric_headers),
                row_index=row_index,
            )
            rows.append(
                WebAnalyticsRow(
                    dimensions={
                        name: _text_value(
                            dimension_values[index],
                            label=f"rows[{row_index}].dimensionValues[{index}]",
                        )
                        for index, name in enumerate(dimension_headers)
                        if name
                    },
                    metrics={
                        name: _number_value(
                            metric_values[index],
                            label=f"rows[{row_index}].metricValues[{index}]",
                        )
                        for index, name in enumerate(metric_headers)
                        if name
                    },
                )
            )

        totals: dict[str, float] = {}
        total_rows = _optional_list(payload, "totals")
        if total_rows:
            if len(total_rows) != 1 or not isinstance(total_rows[0], dict):
                raise _invalid_response("GA4 totals 结构无效")
            metric_values = _row_values(
                total_rows[0],
                "metricValues",
                len(metric_headers),
                row_index=None,
            )
            totals = {
                name: _number_value(
                    metric_values[index],
                    label=f"totals.metricValues[{index}]",
                )
                for index, name in enumerate(metric_headers)
                if name
            }

        row_count = _row_count(payload, rows)
        return WebAnalyticsPeriod(
            start_date=start_date,
            end_date=end_date,
            row_count=row_count,
            rows=rows,
            totals=totals,
        )

    def map_metadata(self, payload: dict[str, object]) -> WebAnalyticsMetadata:
        metadata = payload.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise _invalid_response("GA4 metadata 不是对象")

        for field in ("dataLossFromOtherRow", "subjectToThresholding"):
            if metadata.get(field) is not None and not isinstance(metadata[field], bool):
                raise _invalid_response(f"GA4 metadata.{field} 不是布尔值")
        warnings: list[str] = []
        has_data_gaps = False
        for field, warning in (
            ("samplingMetadatas", "返回的是采样数据，不能当作全量精确统计。"),
            ("dataTruncationReasons", "数据存在截断，不能当作完整日期范围的数据。"),
        ):
            entries = _optional_list(metadata, field)
            if any(not isinstance(item, dict) for item in entries):
                raise _invalid_response(f"GA4 metadata.{field} 必须是对象数组")
            if entries:
                warnings.append(warning)
                has_data_gaps = True
        if metadata.get("dataLossFromOtherRow"):
            warnings.append("部分维度组合被合并至 (other)，不能当作完整明细。")
            has_data_gaps = True
        if metadata.get("subjectToThresholding"):
            # 受阈值限制不等于一定丢失数据，只能提示可能受影响。
            warnings.append("受隐私阈值限制，可能隐藏部分数据；该标记不代表一定有数据缺失。")
        return WebAnalyticsMetadata(
            currency_code=_text(metadata.get("currencyCode")),
            time_zone=_text(metadata.get("timeZone")),
            warnings=tuple(warnings),
            has_data_gaps=has_data_gaps,
        )


def _headers(
    payload: dict[str, object],
    field: str,
    expected: tuple[str, ...],
) -> list[str]:
    raw = payload.get(field)
    if raw is None and not expected:
        return []
    if not isinstance(raw, list):
        raise _invalid_response(f"GA4 {field} 不是数组")

    headers: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise _invalid_response(f"GA4 {field}[{index}] 不是对象")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise _invalid_response(f"GA4 {field}[{index}].name 缺失或不是非空字符串")
        headers.append(name)

    if tuple(headers) != expected:
        # 原始表头属于供应商输入；仅报告出错字段，不把未知名称带回 Host。
        raise _invalid_response(
            f"GA4 {field} 名称或顺序与请求不一致"
        )
    return headers


def _optional_list(payload: dict[str, object], field: str) -> list[object]:
    raw = payload.get(field)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise _invalid_response(f"GA4 {field} 不是数组")
    return raw


def _row_values(
    row: dict[str, object],
    field: str,
    expected_count: int,
    *,
    row_index: int | None,
) -> list[object]:
    raw = row.get(field)
    if raw is None and expected_count == 0:
        return []
    if not isinstance(raw, list):
        prefix = "totals" if row_index is None else f"rows[{row_index}]"
        raise _invalid_response(f"GA4 {prefix}.{field} 不是数组")
    if len(raw) != expected_count:
        prefix = "totals" if row_index is None else f"rows[{row_index}]"
        raise _invalid_response(
            f"GA4 {prefix}.{field} 数量异常：expected={expected_count} actual={len(raw)}"
        )
    return raw


def _text_value(value: object, *, label: str) -> str:
    raw = value.get("value") if isinstance(value, dict) else None
    if not isinstance(raw, str):
        raise _invalid_response(f"GA4 {label}.value 缺失或不是字符串")
    return raw


def _number_value(value: object, *, label: str) -> float:
    raw = value.get("value") if isinstance(value, dict) else None
    if not isinstance(raw, str):
        raise _invalid_response(f"GA4 {label}.value 缺失或不是数值字符串")
    text = raw.strip()
    if not text:
        raise _invalid_response(f"GA4 {label} 为空，不能当作 0")
    try:
        number = float(text)
    except ValueError as exc:
        raise _invalid_response(f"GA4 {label} 不是数值") from exc
    # GA4 指标用字符串传输；NaN、无穷大和溢出不能作为流量或转化观测。
    if not isfinite(number):
        raise _invalid_response(f"GA4 {label} 不是有限数值")
    return number


def _row_count(payload: dict[str, object], rows: list[WebAnalyticsRow]) -> int:
    raw = payload.get("rowCount")
    if raw is None:
        if rows:
            raise _invalid_response("GA4 rowCount 缺失")
        return 0
    # 总行数不能靠取整推算；布尔值虽然是 Python int 的子类，也不是报告行数。
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise _invalid_response("GA4 rowCount 不是整数")
    if raw < len(rows):
        raise _invalid_response(
            f"GA4 rowCount 小于当前返回行数：rowCount={raw} rows={len(rows)}"
        )
    return raw


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _invalid_response(message: str) -> SeoDataError:
    return SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, message)
