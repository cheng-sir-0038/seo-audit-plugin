from __future__ import annotations

import unittest

from codex_seo_mcp.adapters.search_performance import SearchPerformanceAdapter
from codex_seo_mcp.clients.gsc import GscQueryResponse


class FakeGscClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def query(self, property_url: str, body: dict[str, object]) -> GscQueryResponse:
        self.calls.append({"property_url": property_url, "body": body})
        return GscQueryResponse(payload=self.payload)


class SearchPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_page_is_a_dimension_view_not_a_separate_capability(self) -> None:
        """Query × Page 只是 SearchPerformance 的维度组合，结果必须保留两者关系。"""

        client = FakeGscClient(
            {
                "rows": [
                    {
                        "keys": ["seo agent", "https://example.com/seo-agent"],
                        "clicks": 12,
                        "impressions": 240,
                        "ctr": 0.05,
                        "position": 8.4,
                    }
                ],
                "responseAggregationType": "byPage",
            }
        )
        adapter = SearchPerformanceAdapter(client=client)

        result = await adapter.query(
            property_url="sc-domain:example.com",
            start_date="2026-08-01",
            end_date="2026-08-31",
            dimensions=("query", "page"),
            query="seo agent",
        )

        self.assertEqual(result.capability, "SearchPerformance")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.rows[0].query, "seo agent")
        self.assertEqual(result.data.rows[0].page, "https://example.com/seo-agent")
        self.assertEqual(result.data.rows[0].position, 8.4)
        body = client.calls[0]["body"]
        self.assertEqual(body["dimensions"], ["query", "page"])
        self.assertEqual(
            body["dimensionFilterGroups"][0]["filters"][0],
            {"dimension": "query", "operator": "equals", "expression": "seo agent"},
        )


    async def test_request_body_preserves_filters_paging_and_data_state(self) -> None:
        client = FakeGscClient({})
        adapter = SearchPerformanceAdapter(client=client)

        await adapter.query(
            property_url="sc-domain:example.com",
            start_date="2026-08-01",
            end_date="2026-08-31",
            dimensions=("date", "query", "page", "country", "device"),
            query="seo agent",
            page="https://example.com/seo-agent",
            country="USA",
            device="mobile",
            data_state="all",
            search_type="image",
            row_limit=250,
            start_row=500,
        )

        call = client.calls[0]
        self.assertEqual(call["property_url"], "sc-domain:example.com")
        body = call["body"]
        self.assertEqual(body["startDate"], "2026-08-01")
        self.assertEqual(body["endDate"], "2026-08-31")
        self.assertEqual(body["dimensions"], ["date", "query", "page", "country", "device"])
        self.assertEqual(body["type"], "image")
        self.assertEqual(body["dataState"], "all")
        self.assertEqual(body["rowLimit"], 250)
        self.assertEqual(body["startRow"], 500)
        self.assertEqual(
            body["dimensionFilterGroups"],
            [
                {
                    "groupType": "and",
                    "filters": [
                        {"dimension": "query", "operator": "equals", "expression": "seo agent"},
                        {"dimension": "page", "operator": "equals", "expression": "https://example.com/seo-agent"},
                        {"dimension": "country", "operator": "equals", "expression": "USA"},
                        {"dimension": "device", "operator": "equals", "expression": "MOBILE"},
                    ],
                }
            ],
        )

    async def test_empty_rows_stay_empty_instead_of_becoming_not_ranked(self) -> None:
        """GSC 没返回行只能表示当前请求无记录，不能自动生成“未排名”。"""

        adapter = SearchPerformanceAdapter(client=FakeGscClient({}))

        result = await adapter.query(
            property_url="sc-domain:example.com",
            start_date="2026-08-01",
            end_date="2026-08-31",
            dimensions=("query", "page"),
        )

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.rows, [])
        self.assertEqual(result.warnings, [])

    async def test_fresh_incomplete_data_returns_partial(self) -> None:
        """请求 fresh data 时，GSC 标记未完成日期应映射为 partial，而不是 complete。"""

        client = FakeGscClient(
            {
                "rows": [],
                "metadata": {"first_incomplete_date": "2026-09-02"},
            }
        )
        adapter = SearchPerformanceAdapter(client=client)

        result = await adapter.query(
            property_url="sc-domain:example.com",
            start_date="2026-09-01",
            end_date="2026-09-03",
            dimensions=("date",),
            data_state="all",
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data.first_incomplete_date, "2026-09-02")
        self.assertIn("2026-09-02", result.warnings[0])

    async def test_invalid_dimension_stops_before_gsc_call(self) -> None:
        """V1 只开放稳定维度集合，未知维度不透传给 Google 再碰运气。"""

        client = FakeGscClient({})
        adapter = SearchPerformanceAdapter(client=client)

        with self.assertRaisesRegex(Exception, "不支持的 SearchPerformance dimension"):
            await adapter.query(
                property_url="sc-domain:example.com",
                start_date="2026-08-01",
                end_date="2026-08-31",
                dimensions=("keyword",),
            )

        self.assertEqual(client.calls, [])

    async def test_country_filter_requires_three_letter_code(self) -> None:
        """国家过滤使用 GSC 的三位国家代码，避免把 2 位代码误判成“该市场没数据”。"""

        client = FakeGscClient({})
        adapter = SearchPerformanceAdapter(client=client)

        with self.assertRaisesRegex(Exception, "3 位国家代码"):
            await adapter.query(
                property_url="sc-domain:example.com",
                start_date="2026-08-01",
                end_date="2026-08-31",
                country="US",
            )

        self.assertEqual(client.calls, [])
