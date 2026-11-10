from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchPerformanceRow:
    """GSC Search Analytics 的一行维度组合与指标。

    业务说明：`position` 是 Search Console 返回的平均位置，不是一个固定的“绝对排名”。
    Query × Page 等关系由调用时 dimensions 决定，不需要额外创建另一种 Capability。
    """

    date: str | None = None
    query: str | None = None
    page: str | None = None
    country: str | None = None
    device: str | None = None
    clicks: float = 0.0
    impressions: float = 0.0
    ctr: float = 0.0
    position: float = 0.0


@dataclass(slots=True)
class SearchPerformance:
    """本站第一方 Search Console 搜索表现。

    空 `rows` 只表示当前请求没有返回记录，不能自动解释成“没有排名”或“未收录”。
    Search Console API 本身也不保证返回所有长尾行，因此诊断层必须保留数据边界。
    start/end date 使用的是 Search Console 报表日期语义（Pacific Time），Adapter 不擅自
    把用户输入的 YYYY-MM-DD 再转换成 UTC 日期。
    """

    property_url: str
    start_date: str
    end_date: str
    dimensions: list[str]
    rows: list[SearchPerformanceRow] = field(default_factory=list)
    response_aggregation_type: str | None = None
    first_incomplete_date: str | None = None
    first_incomplete_hour: str | None = None
