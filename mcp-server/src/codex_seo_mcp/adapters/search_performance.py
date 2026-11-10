from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Protocol

from codex_seo_mcp.clients.gsc import GscClient, GscQueryResponse
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.search_performance import (
    SearchPerformance,
    SearchPerformanceRow,
)

_DIMENSIONS = {"date", "query", "page", "country", "device"}
_DATA_STATES = {"final", "all"}
_SEARCH_TYPES = {"web", "image", "video", "news", "discover", "googleNews"}


class GscLike(Protocol):
    """SearchPerformance 对 GSC Client 的最小依赖面，不把 Google SDK 类型传进领域层。"""

    async def query(
        self, property_url: str, body: dict[str, object]
    ) -> GscQueryResponse: ...


@dataclass(frozen=True, slots=True)
class _SearchPerformanceQuery:
    property_url: str
    start_date: str
    end_date: str
    dimensions: tuple[str, ...]
    data_state: str
    search_type: str
    row_limit: int
    start_row: int
    filters: tuple[dict[str, str], ...]

    @classmethod
    def from_input(
        cls,
        *,
        property_url: str,
        start_date: str,
        end_date: str,
        dimensions: tuple[str, ...],
        query: str | None,
        page: str | None,
        country: str | None,
        device: str | None,
        data_state: str,
        search_type: str,
        row_limit: int,
        start_row: int,
    ) -> "_SearchPerformanceQuery":
        normalized_dimensions = tuple(_validate_dimensions(dimensions))
        _validate_dates(start_date, end_date)
        selected_data_state = data_state.strip()
        if selected_data_state not in _DATA_STATES:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "SearchPerformance data_state 只支持 final 或 all",
            )
        selected_search_type = search_type.strip()
        if selected_search_type not in _SEARCH_TYPES:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "SearchPerformance search_type 不受支持",
            )
        if not 1 <= row_limit <= 25_000:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "SearchPerformance row_limit 必须在 1 到 25000 之间",
            )
        if start_row < 0:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "SearchPerformance start_row 不能小于 0",
            )
        clean_property = property_url.strip()
        if not _valid_property(clean_property):
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                "GSC property 必须是 sc-domain: 或 HTTP/HTTPS URL-prefix",
            )
        return cls(
            property_url=clean_property,
            start_date=start_date,
            end_date=end_date,
            dimensions=normalized_dimensions,
            data_state=selected_data_state,
            search_type=selected_search_type,
            row_limit=row_limit,
            start_row=start_row,
            filters=tuple(
                _filters(
                    query=query,
                    page=page,
                    country=country,
                    device=device,
                )
            ),
        )

    def body(self) -> dict[str, object]:
        body: dict[str, object] = {
            "startDate": self.start_date,
            "endDate": self.end_date,
            "dimensions": list(self.dimensions),
            "type": self.search_type,
            "dataState": self.data_state,
            "rowLimit": self.row_limit,
            "startRow": self.start_row,
        }
        if self.filters:
            body["dimensionFilterGroups"] = [
                {"groupType": "and", "filters": list(self.filters)}
            ]
        return body


class SearchPerformanceAdapter:
    """把 GSC Search Analytics 转换为本站 `SearchPerformance`。

    业务边界：这是本站排名和搜索表现的唯一第一方来源。空结果不等于“未排名”；
    Semrush 等第三方数据也不能在这里作为 fallback 覆盖 GSC 事实。
    """

    capability = "SearchPerformance"

    def __init__(self, client: GscLike | None = None) -> None:
        self.client = client or GscClient()

    async def query(
        self,
        *,
        property_url: str,
        start_date: str,
        end_date: str,
        dimensions: tuple[str, ...] = ("query", "page"),
        query: str | None = None,
        page: str | None = None,
        country: str | None = None,
        device: str | None = None,
        data_state: str = "final",
        search_type: str = "web",
        row_limit: int = 1000,
        start_row: int = 0,
    ) -> CapabilityResult[SearchPerformance]:
        request = _SearchPerformanceQuery.from_input(
            property_url=property_url,
            start_date=start_date,
            end_date=end_date,
            dimensions=dimensions,
            query=query,
            page=page,
            country=country,
            device=device,
            data_state=data_state,
            search_type=search_type,
            row_limit=row_limit,
            start_row=start_row,
        )
        response = await self.client.query(request.property_url, request.body())
        data = _map_response(
            response.payload,
            property_url=request.property_url,
            start_date=request.start_date,
            end_date=request.end_date,
            dimensions=list(request.dimensions),
        )
        warnings = _search_performance_warnings(data, row_limit=request.row_limit)
        factory = (
            CapabilityResult.partial
            if data.first_incomplete_date or data.first_incomplete_hour
            else CapabilityResult.complete
        )
        return factory(
            capability=self.capability,
            provider="gsc",
            source_kind=CapabilitySourceKind.FIRST_PARTY,
            data=data,
            warnings=warnings,
        )



def _search_performance_warnings(
    data: SearchPerformance,
    *,
    row_limit: int,
) -> list[str]:
    warnings: list[str] = []
    if data.first_incomplete_date:
        warnings.append(f"GSC 从 {data.first_incomplete_date} 起包含尚未完成的数据")
    if data.first_incomplete_hour:
        warnings.append(f"GSC 从 {data.first_incomplete_hour} 起包含尚未完成的小时数据")
    if len(data.rows) >= row_limit:
        warnings.append("GSC 返回行数达到 row_limit，当前结果可能不是完整长尾数据集")
    return warnings


def _validate_dimensions(dimensions: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for raw in dimensions:
        dimension = str(raw).strip()
        if dimension not in _DIMENSIONS:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, f"不支持的 SearchPerformance dimension：{dimension}")
        if dimension in result:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, f"SearchPerformance dimension 重复：{dimension}")
        result.append(dimension)
    return result


def _validate_dates(start: str, end: str) -> None:
    try:
        start_value = date.fromisoformat(start)
        end_value = date.fromisoformat(end)
        if start_value.isoformat() != start or end_value.isoformat() != end:
            raise ValueError("noncanonical date")
    except (TypeError, ValueError) as exc:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "SearchPerformance 日期必须使用 YYYY-MM-DD") from exc
    if start_value > end_value:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "SearchPerformance start_date 不能晚于 end_date")


def _filters(
    *,
    query: str | None,
    page: str | None,
    country: str | None,
    device: str | None,
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for dimension, raw in (("query", query), ("page", page)):
        value = (raw or "").strip()
        if value:
            result.append({"dimension": dimension, "operator": "equals", "expression": value})
    if country:
        value = country.strip().upper()
        # Search Console country filter 使用 ISO 3166-1 alpha-3；提前校验可以避免把供应商
        # 400 错误混成“这个国家没有搜索数据”。
        if len(value) != 3 or not value.isalpha():
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "SearchPerformance country 必须是 3 位国家代码")
        result.append({"dimension": "country", "operator": "equals", "expression": value})
    if device:
        value = device.strip().upper()
        if value not in {"DESKTOP", "MOBILE", "TABLET"}:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "SearchPerformance device 只支持 desktop/mobile/tablet")
        result.append({"dimension": "device", "operator": "equals", "expression": value})
    return result


def _map_response(
    payload: dict[str, object],
    *,
    property_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str],
) -> SearchPerformance:
    raw_rows = payload.get("rows", [])
    if "error" in payload or not isinstance(raw_rows, list):
        raise SeoDataError(
            SeoDataErrorCode.INVALID_RESPONSE,
            "GSC rows 返回结构无效",
        )
    rows: list[SearchPerformanceRow] = []
    for row_index, raw in enumerate(raw_rows):
        if not isinstance(raw, dict):
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                f"GSC rows[{row_index}] 不是对象",
            )
        # 未分组的汇总行允许省略 keys；分组结果必须逐项对应请求维度，不能猜测缺项。
        keys = raw.get("keys", [])
        if (
            not isinstance(keys, list)
            or len(keys) != len(dimensions)
            or any(not isinstance(value, str) for value in keys)
        ):
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                f"GSC rows[{row_index}].keys 必须是与请求维度数量相同的字符串数组",
            )
        dimension_values = dict(zip(dimensions, keys, strict=True))
        rows.append(
            SearchPerformanceRow(
                date=dimension_values.get("date"),
                query=dimension_values.get("query"),
                page=dimension_values.get("page"),
                country=dimension_values.get("country"),
                device=dimension_values.get("device"),
                clicks=_metric_number(raw.get("clicks"), field="clicks", row_index=row_index),
                impressions=_metric_number(raw.get("impressions"), field="impressions", row_index=row_index),
                ctr=_metric_number(raw.get("ctr"), field="ctr", row_index=row_index),
                position=_metric_number(raw.get("position"), field="position", row_index=row_index),
            )
        )

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return SearchPerformance(
        property_url=property_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=dimensions,
        rows=rows,
        response_aggregation_type=_optional_text(payload.get("responseAggregationType")),
        first_incomplete_date=_optional_text(metadata.get("first_incomplete_date")),
        first_incomplete_hour=_optional_text(metadata.get("first_incomplete_hour")),
    )


def _metric_number(value: object, *, field: str, row_index: int) -> float:
    # 只有供应商明确返回的数值才是观测；缺失、文本和非有限数不能补成零。
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            number = float(value)
        except OverflowError:
            pass
        else:
            if isfinite(number):
                return number
    raise SeoDataError(
        SeoDataErrorCode.INVALID_RESPONSE,
        f"GSC rows[{row_index}].{field} 缺失或不是有限数值",
    )


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _valid_property(value: str) -> bool:
    text = value.strip()
    return text.startswith("sc-domain:") or text.startswith("https://") or text.startswith("http://")
