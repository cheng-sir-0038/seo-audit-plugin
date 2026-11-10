from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp import Client

from codex_seo_mcp import server as server_module
from codex_seo_mcp.adapters.search_performance import SearchPerformanceAdapter
from codex_seo_mcp.auth.google_oauth import GoogleOAuthConfig, GscAuthManager
from codex_seo_mcp.clients.gsc import GscClient
from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.models.common import CapabilityResult
from codex_seo_mcp.models.search_performance import SearchPerformance


class GscResponseValidationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        token_path = Path(directory.name) / "synthetic-token.json"
        token_path.write_text(json.dumps({
            "token": "synthetic-access-token",
            "refresh_token": "synthetic-refresh-token",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-client-secret",
            "expiry": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }), encoding="utf-8")
        auth = GscAuthManager(GoogleOAuthConfig(
            client_file=None,
            client_id="synthetic-client",
            client_secret="synthetic-client-secret",
            token_path=token_path,
        ))
        self.gsc = GscClient(auth=auth)
        self.adapter = SearchPerformanceAdapter(client=self.gsc)
        self.provider = MagicMock()
        # 只替换第三方 SDK；凭据加载、Client、适配器和结果对象均走真实代码。
        sdk = patch("googleapiclient.discovery.build", return_value=self.provider)
        sdk.start()
        self.addCleanup(sdk.stop)
        self.row = {
            "keys": ["seo agent", "https://example.com/seo-agent"],
            "clicks": 12,
            "impressions": 240,
            "ctr": 0.05,
            "position": 8.4,
        }

    async def query_payload(
        self,
        payload: dict[str, object],
        *,
        dimensions: tuple[str, ...] = ("query", "page"),
    ) -> CapabilityResult[SearchPerformance]:
        self.provider.searchanalytics().query().execute.return_value = payload
        return await self.adapter.query(
            property_url="sc-domain:example.com",
            start_date="2026-08-01",
            end_date="2026-08-28",
            dimensions=dimensions,
        )

    async def test_noncanonical_dates_are_rejected_before_the_google_request(self) -> None:
        self.provider.searchanalytics().query().execute.return_value = {"rows": [self.row]}
        for field, value in (("start_date", "20260801"), ("end_date", "20260828"), ("start_date", "2026-W31-6")):
            with self.subTest(field=field, value=value):
                arguments = {"start_date": "2026-08-01", "end_date": "2026-08-28", field: value}
                with self.assertRaises(SeoDataError) as caught:
                    await self.adapter.query(property_url="sc-domain:example.com", **arguments)
                self.assertEqual(caught.exception.code, "invalid_request")
        self.provider.searchanalytics().query().execute.assert_not_called()

    async def test_invalid_metrics_are_rejected_instead_of_becoming_numbers(self) -> None:
        invalid_values = {
            "null": None,
            "text": "provider-private-value",
            "empty_text": "",
            "numeric_text": "12.5",
            "true": True,
            "false": False,
            "object": {},
            "array": [],
            "nan": float("nan"),
            "infinity": float("inf"),
            "negative_infinity": float("-inf"),
            "overflow": 10 ** 400,
        }
        for metric in ("clicks", "impressions", "ctr", "position"):
            for label, value in invalid_values.items():
                with self.subTest(metric=metric, value=label):
                    row = {**self.row, metric: value}
                    with self.assertRaises(SeoDataError) as caught:
                        await self.query_payload({"rows": [row]})
                    self.assertEqual(caught.exception.code, "invalid_response")
                    self.assertIn(f"rows[0].{metric}", caught.exception.message)
                    self.assertNotIn("provider-private-value", caught.exception.message)

    async def test_missing_metric_is_not_filled_with_zero(self) -> None:
        for metric in ("clicks", "impressions", "ctr", "position"):
            with self.subTest(metric=metric):
                row = dict(self.row)
                del row[metric]
                with self.assertRaises(SeoDataError) as caught:
                    await self.query_payload({"rows": [row]})
                self.assertEqual(caught.exception.code, "invalid_response")
                self.assertIn(f"rows[0].{metric}", caught.exception.message)

    async def test_finite_metrics_and_explicit_zero_values_are_preserved(self) -> None:
        zero_row = {**self.row, "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
        result = await self.query_payload({"rows": [self.row, zero_row]})
        rows = result.to_dict()["data"]["rows"]
        self.assertEqual(result.status, "complete")
        self.assertEqual(
            [(row["clicks"], row["impressions"], row["ctr"], row["position"]) for row in rows],
            [(12.0, 240.0, 0.05, 8.4), (0.0, 0.0, 0.0, 0.0)],
        )
        json.dumps(result.to_dict(), allow_nan=False)

    async def test_malformed_rows_are_not_reported_as_an_empty_success(self) -> None:
        payloads = {
            "error_body": {"error": {"message": "provider-private-value"}},
            "error_with_rows": {"error": {}, "rows": [self.row]},
            "null_rows": {"rows": None},
            "text_rows": {"rows": "provider-private-value"},
            "object_rows": {"rows": {"unexpected": self.row}},
            "false_rows": {"rows": False},
            "number_rows": {"rows": 12},
            "non_object_row": {"rows": ["provider-private-value"]},
            "mixed_valid_and_invalid": {"rows": [self.row, None]},
        }
        for label, payload in payloads.items():
            with self.subTest(payload=label):
                with self.assertRaises(SeoDataError) as caught:
                    await self.query_payload(payload)
                self.assertEqual(caught.exception.code, "invalid_response")
                self.assertNotIn("provider-private-value", caught.exception.message)

    async def test_dimension_keys_must_match_the_requested_view(self) -> None:
        invalid_keys = {
            "null": None,
            "text": "ab",
            "object": {"query": "seo agent", "page": "provider-private-value"},
            "empty": [],
            "missing_page": ["seo agent"],
            "extra_dimension": ["seo agent", "https://example.com/", "mobile"],
            "null_value": ["seo agent", None],
            "numeric_value": [12, "https://example.com/"],
            "object_value": ["seo agent", {"url": "provider-private-value"}],
        }
        for label, keys in invalid_keys.items():
            with self.subTest(keys=label):
                with self.assertRaises(SeoDataError) as caught:
                    await self.query_payload({"rows": [{**self.row, "keys": keys}]})
                self.assertEqual(caught.exception.code, "invalid_response")
                self.assertIn("rows[0].keys", caught.exception.message)
                self.assertNotIn("provider-private-value", caught.exception.message)

        row_without_keys = dict(self.row)
        del row_without_keys["keys"]
        with self.assertRaises(SeoDataError) as caught:
            await self.query_payload({"rows": [row_without_keys]})
        self.assertEqual(caught.exception.code, "invalid_response")

    async def test_valid_empty_results_stay_empty(self) -> None:
        for payload in ({}, {"rows": []}, {"responseAggregationType": "byProperty"}):
            with self.subTest(payload=payload):
                result = await self.query_payload(payload)
                self.assertEqual(result.status, "complete")
                self.assertEqual(result.data.rows, [])

    async def test_dimension_order_and_original_values_are_preserved(self) -> None:
        keys = ["https://example.com/seo-agent?a=1", " seo agent "]
        result = await self.query_payload(
            {"rows": [{**self.row, "keys": keys}]}, dimensions=("page", "query"),
        )
        row = result.data.rows[0]
        self.assertEqual(row.page, "https://example.com/seo-agent?a=1")
        self.assertEqual(row.query, " seo agent ")
        self.assertIsNone(row.country)
        self.assertIsNone(row.device)

    async def test_ungrouped_totals_allow_empty_or_omitted_keys(self) -> None:
        row_without_keys = {key: value for key, value in self.row.items() if key != "keys"}
        for row in (row_without_keys, {**row_without_keys, "keys": []}):
            with self.subTest(keys_present="keys" in row):
                result = await self.query_payload({"rows": [row]}, dimensions=())
                self.assertEqual(result.status, "complete")
                self.assertEqual(len(result.data.rows), 1)
                self.assertIsNone(result.data.rows[0].query)
                self.assertIsNone(result.data.rows[0].page)
                self.assertEqual(result.data.rows[0].clicks, 12.0)

    async def test_mcp_preserves_explicit_empty_dimensions_and_default_grouping(self) -> None:
        self.provider.sites().list().execute.return_value = {
            "siteEntry": [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}],
        }
        cases = [
            ({}, ["query", "page"], dict(self.row)),
            ({"dimensions": None}, ["query", "page"], dict(self.row)),
            (
                {"dimensions": []}, [],
                {"clicks": 30, "impressions": 500, "ctr": 0.06, "position": 9.2},
            ),
            (
                {"dimensions": ["page"]}, ["page"],
                {**self.row, "keys": ["https://example.com/seo-agent"]},
            ),
        ]
        with (
            patch.object(server_module, "_gsc", self.gsc),
            patch.object(server_module, "_search_performance", self.adapter),
        ):
            async with Client(server_module.mcp, mode="2026-07-28") as client:
                for arguments, expected_dimensions, row in cases:
                    with self.subTest(arguments=arguments):
                        self.provider.searchanalytics().query().execute.return_value = {"rows": [row]}
                        result = await client.call_tool("analyze_search_console", {
                            "target": "example.com",
                            "start_date": "2026-08-01",
                            "end_date": "2026-08-28",
                            **arguments,
                        })
                        body = self.provider.searchanalytics().query.call_args.kwargs["body"]
                        self.assertEqual(body["dimensions"], expected_dimensions)
                        self.assertFalse(result.is_error)
                        data = result.structured_content["data"]
                        self.assertEqual(data["dimensions"], expected_dimensions)
                        self.assertEqual(data["rows"][0]["clicks"], row["clicks"])
                        if not expected_dimensions:
                            self.assertIsNone(data["rows"][0]["query"])
                            self.assertIsNone(data["rows"][0]["page"])

        self.assertEqual(self.provider.searchanalytics().query().execute.call_count, 4)

    async def test_mcp_returns_native_error_without_exposing_invalid_provider_values(self) -> None:
        self.provider.sites().list().execute.return_value = {
            "siteEntry": [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}],
        }
        stderr = io.StringIO()
        cases = [
            ({"rows": [{**self.row, "clicks": "provider-private-value"}]}, True),
            ({"rows": [{**self.row, "keys": ["provider-private-value"]}]}, True),
            ({"rows": [self.row]}, False),
            ({}, False),
        ]
        # 注入真实 Client/Adapter，让身份解析、错误转换和 MCP 输出均参与验证。
        with (
            patch.object(server_module, "_gsc", self.gsc),
            patch.object(server_module, "_search_performance", self.adapter),
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            async with Client(server_module.mcp, mode="2026-07-28") as client:
                for payload, is_error in cases:
                    with self.subTest(payload=payload):
                        self.provider.searchanalytics().query().execute.return_value = payload
                        result = await client.call_tool("analyze_search_console", {
                            "target": "example.com",
                            "start_date": "2026-08-01",
                            "end_date": "2026-08-28",
                        })
                        self.assertEqual(result.is_error, is_error)
                        if is_error:
                            self.assertIsNone(result.structured_content)
                            self.assertIn("[invalid_response]", result.content[0].text)
                            self.assertNotIn("provider-private-value", result.content[0].text)
                        else:
                            self.assertEqual(result.structured_content["status"], "complete")
                            self.assertEqual(
                                len(result.structured_content["data"]["rows"]),
                                len(payload.get("rows", [])),
                            )

        # 每次请求只调用一次第三方，失败不能被自动重试成一个假成功。
        self.assertEqual(self.provider.searchanalytics().query().execute.call_count, 4)
        self.assertNotIn("provider-private-value", stderr.getvalue())
