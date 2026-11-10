from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from mcp import Client
from requests import Response

from codex_seo_mcp import server as server_module
from codex_seo_mcp.adapters.web_analytics import WebAnalyticsAdapter
from codex_seo_mcp.auth.ga4_oauth import Ga4AuthManager, Ga4OAuthConfig
from codex_seo_mcp.clients.ga4 import Ga4Client, Ga4ClientConfig
from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class AnalyticsQueryIntegrityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        token = self.root / "synthetic-token.json"
        token.write_text(json.dumps({
            "token": "synthetic-access-token",
            "refresh_token": "synthetic-refresh-token",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-client-secret",
            "expiry": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }), encoding="utf-8")
        auth = Ga4AuthManager(Ga4OAuthConfig(
            client_id="synthetic-client", client_secret="synthetic-client-secret",
            token_path=token,
        ))
        self.ga4 = Ga4Client(
            auth=auth, config=Ga4ClientConfig(cache_ttl_seconds=0),
            cache=ProviderCache(ProviderCacheConfig(root=self.root / "cache")),
        )
        self.adapter = WebAnalyticsAdapter(client=self.ga4)
        self.query = {"property_id": "222", "start_date": "2026-08-01", "end_date": "2026-08-28"}
        # Literal provider fixture; do not derive expected data from the implementation.
        self.report = {
            "metricHeaders": [{"name": name} for name in (
                "sessions", "activeUsers", "engagedSessions", "engagementRate",
                "keyEvents", "sessionKeyEventRate", "totalRevenue",
            )],
            "rows": [{"metricValues": [{"value": value} for value in (
                "10", "8", "6", "0.6", "1", "0.1", "12.5",
            )]}],
            "rowCount": 1,
            "metadata": {"currencyCode": "USD", "timeZone": "Asia/Shanghai"},
        }

    @staticmethod
    def response(payload: dict[str, object]) -> Response:
        response = Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode("utf-8")
        response.encoding = "utf-8"
        return response

    async def test_noncanonical_dates_stop_before_any_report_request(self) -> None:
        cases = [
            {"start_date": "20260801"}, {"end_date": "20260828"},
            {"start_date": "2026-W31-6"}, {"start_date": "2026-02-30"},
            {"compare_start_date": "20260701", "compare_end_date": "2026-07-28"},
            {"compare_start_date": "2026-07-01", "compare_end_date": "20260728"},
            {"compare_start_date": "", "compare_end_date": ""},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), patch(
                "google.auth.transport.requests.AuthorizedSession.request",
                return_value=self.response(self.report),
            ) as provider:
                with self.assertRaises(SeoDataError) as caught:
                    await self.adapter.analyze(**{**self.query, **arguments})
                self.assertEqual(caught.exception.code, "invalid_request")
                provider.assert_not_called()

    async def test_valid_leap_day_and_explicit_windows_are_not_rewritten(self) -> None:
        with patch(
            "google.auth.transport.requests.AuthorizedSession.request",
            return_value=self.response(self.report),
        ) as provider:
            result = await self.adapter.analyze(
                property_id="222", start_date="2024-02-29", end_date="2024-03-01",
                compare_start_date="2024-02-27", compare_end_date="2024-02-28",
            )
        self.assertEqual(result.data.current.start_date, "2024-02-29")
        self.assertEqual(result.data.previous.end_date, "2024-02-28")
        self.assertEqual(provider.call_args_list[0].kwargs["json"]["dateRanges"], [
            {"startDate": "2024-02-29", "endDate": "2024-03-01"},
        ])
        self.assertEqual(provider.call_count, 2)

    async def test_foreign_property_stream_is_rejected_before_caching(self) -> None:
        ga4 = Ga4Client(auth=self.ga4.auth, cache=self.ga4.cache, config=Ga4ClientConfig())
        foreign = {"dataStreams": [{
            "name": "properties/999/dataStreams/333", "type": "WEB_DATA_STREAM",
            "webStreamData": {"defaultUri": "https://example.com/"},
        }]}
        with patch(
            "google.auth.transport.requests.AuthorizedSession.request",
            return_value=self.response(foreign),
        ) as provider:
            for _ in range(2):
                with self.assertRaises(SeoDataError) as caught:
                    await ga4.list_data_streams("222")
                self.assertEqual(caught.exception.code, "invalid_response")
                self.assertNotIn("999", caught.exception.message)
            self.assertEqual(provider.call_count, 2)

    async def test_pre_validation_stream_cache_is_not_trusted(self) -> None:
        ga4 = Ga4Client(auth=self.ga4.auth, cache=self.ga4.cache, config=Ga4ClientConfig())
        ga4.cache.set(
            provider="ga4", operation="list-data-streams",
            request_key={"auth_generation": ga4.auth.cache_generation(), "property_id": "222"},
            value=[{"data_stream_id": "999", "display_name": "", "type": "WEB_DATA_STREAM",
                    "measurement_id": "", "default_uri": "https://wrong.example/"}],
            ttl_seconds=1800,
        )
        valid = {"dataStreams": [{
            "name": "properties/222/dataStreams/333", "type": "WEB_DATA_STREAM",
            "webStreamData": {"defaultUri": "https://example.com/"},
        }]}
        with patch(
            "google.auth.transport.requests.AuthorizedSession.request",
            return_value=self.response(valid),
        ) as provider:
            first = await ga4.list_data_streams("222")
            second = await ga4.list_data_streams("properties/222")
        self.assertEqual(first[0]["data_stream_id"], "333")
        self.assertEqual(first, second)
        self.assertEqual(provider.call_count, 1)

    async def test_data_quality_warnings_keep_current_and_previous_periods_distinct(self) -> None:
        cases = [
            ({"samplingMetadatas": [{"samplesReadCount": "50", "samplingSpaceSize": "100"}]}, "partial", "采样"),
            ({"dataLossFromOtherRow": True}, "partial", "(other)"),
            ({"dataTruncationReasons": [{"dataTruncationMessage": "private-provider-message"}]}, "partial", "截断"),
            ({"subjectToThresholding": True}, "complete", "阈值"),
        ]
        for affected_period in ("当前", "对比"):
            for fields, expected_status, marker in cases:
                with self.subTest(period=affected_period, fields=fields):
                    current, previous = deepcopy(self.report), deepcopy(self.report)
                    target = current if affected_period == "当前" else previous
                    target["metadata"].update(fields)
                    with patch(
                        "google.auth.transport.requests.AuthorizedSession.request",
                        side_effect=[self.response(current), self.response(previous)],
                    ) as provider:
                        result = await self.adapter.analyze(
                            **self.query, compare_start_date="2026-07-01", compare_end_date="2026-07-28",
                        )
                    self.assertEqual(result.status, expected_status)
                    self.assertTrue(any(affected_period in warning and marker in warning for warning in result.warnings))
                    self.assertFalse(any(("对比" if affected_period == "当前" else "当前") in warning for warning in result.warnings))
                    self.assertNotIn("private-provider-message", " ".join(result.warnings))
                    self.assertEqual(result.data.current.rows[0].metrics["sessions"], 10.0)
                    self.assertEqual(result.data.previous.rows[0].metrics["sessions"], 10.0)
                    self.assertEqual(result.data.currency_code, "USD")
                    self.assertEqual(provider.call_count, 2)

    async def test_clean_metadata_keeps_complete_result_without_quality_warnings(self) -> None:
        clean = deepcopy(self.report)
        clean["metadata"].update({"subjectToThresholding": False, "dataLossFromOtherRow": False,
                                   "samplingMetadatas": [], "dataTruncationReasons": []})
        with patch("google.auth.transport.requests.AuthorizedSession.request", return_value=self.response(clean)):
            result = await self.adapter.analyze(**self.query)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.warnings, [])

    async def test_later_pages_are_not_labeled_top_n_or_an_empty_dataset(self) -> None:
        for offset, empty_page in ((100, False), (175, True)):
            with self.subTest(offset=offset):
                report = deepcopy(self.report)
                report["dimensionHeaders"] = [{"name": "deviceCategory"}]
                report["rows"][0]["dimensionValues"] = [{"value": "mobile"}]
                report["rowCount"] = 175
                if empty_page:
                    report["rows"] = []
                with patch(
                    "google.auth.transport.requests.AuthorizedSession.request",
                    return_value=self.response(report),
                ) as provider:
                    result = await self.adapter.analyze(
                        **self.query, view="devices", limit=1, offset=offset,
                        compare_start_date="2026-07-01", compare_end_date="2026-07-28",
                    )
                self.assertEqual(len(result.warnings), 2)
                for period in ("当前", "对比"):
                    warning = next(item for item in result.warnings if period in item)
                    self.assertNotIn("Top-N", warning)
                    self.assertIn(f"offset={offset}", warning)
                    self.assertIn("row_count=175", warning)
                self.assertEqual(result.data.current.row_count, 175)
                self.assertEqual(len(result.data.current.rows), 0 if empty_page else 1)
                self.assertEqual(provider.call_args.kwargs["json"]["offset"], str(offset))

    async def test_first_page_and_complete_result_keep_existing_meaning(self) -> None:
        with patch(
            "google.auth.transport.requests.AuthorizedSession.request",
            return_value=self.response({**self.report, "rowCount": 10}),
        ):
            first_page = await self.adapter.analyze(**self.query, limit=1)
        self.assertTrue(any("Top-N" in item for item in first_page.warnings))
        with patch(
            "google.auth.transport.requests.AuthorizedSession.request",
            return_value=self.response(self.report),
        ):
            complete = await self.adapter.analyze(**self.query)
        self.assertEqual(complete.warnings, [])

    async def test_cache_ttl_overflow_does_not_replace_successful_provider_results(self) -> None:
        for ttl in (10 ** 12, 10 ** 100):
            with self.subTest(ttl=ttl):
                ga4 = Ga4Client(auth=self.ga4.auth, cache=self.ga4.cache,
                                config=Ga4ClientConfig(cache_ttl_seconds=ttl))
                with patch(
                    "google.auth.transport.requests.AuthorizedSession.request",
                    return_value=self.response(self.report),
                ) as provider:
                    first = await ga4.run_report("222", {"metrics": [{"name": "sessions"}]})
                    second = await ga4.run_report("222", {"metrics": [{"name": "sessions"}]})
                self.assertEqual(first.payload, self.report)
                self.assertEqual(second.payload, self.report)
                self.assertEqual(provider.call_count, 2)
                self.assertEqual(list((self.root / "cache").rglob("*.json")), [])

    async def test_mcp_preserves_quality_scope_and_cache_failure_semantics(self) -> None:
        properties = {"accountSummaries": [{"account": "accounts/111", "propertySummaries": [
            {"property": "properties/222", "displayName": "Example site"},
        ]}]}
        for case, expected_error in (("quality", None), ("dates", "invalid_request"),
                                     ("parent", "invalid_response"), ("cache", None)):
            with self.subTest(case=case):
                report = deepcopy(self.report)
                arguments = {"target": "222", "start_date": "2026-08-01", "end_date": "2026-08-28"}
                if case == "quality":
                    report["dimensionHeaders"] = [{"name": "deviceCategory"}]
                    report["rows"][0]["dimensionValues"] = [{"value": "mobile"}]
                    report["rowCount"] = 175
                    report["metadata"]["samplingMetadatas"] = [{"samplesReadCount": "50", "samplingSpaceSize": "100"}]
                    arguments.update({"view": "devices", "offset": 100, "limit": 1})
                elif case == "dates":
                    arguments["start_date"] = "20260801"
                elif case == "parent":
                    arguments["target"] = "example.com"

                def respond(method: str, url: str, **kwargs) -> Response:
                    if method == "GET" and url.endswith("/accountSummaries"):
                        return self.response(properties)
                    if method == "GET" and url.endswith("/properties/222/dataStreams"):
                        return self.response({"dataStreams": [{
                            "name": "properties/999/dataStreams/333", "type": "WEB_DATA_STREAM",
                            "webStreamData": {"defaultUri": "https://example.com/"},
                        }]})
                    if method == "POST" and url.endswith("/properties/222:runReport"):
                        return self.response(report)
                    raise AssertionError("Unexpected provider call")

                ga4 = Ga4Client(auth=self.ga4.auth, cache=self.ga4.cache,
                                config=Ga4ClientConfig(cache_ttl_seconds=10 ** 100 if case == "cache" else 0))
                stderr = io.StringIO()
                with (
                    patch.object(server_module, "_ga4", ga4),
                    patch.object(server_module, "_web_analytics", WebAnalyticsAdapter(client=ga4)),
                    patch("google.auth.transport.requests.AuthorizedSession.request", side_effect=respond) as provider,
                    patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
                    redirect_stderr(stderr),
                ):
                    async with Client(server_module.mcp, mode="2026-07-28") as client:
                        result = await client.call_tool("analyze_organic_traffic", arguments)
                report_calls = [call for call in provider.call_args_list if call.args[0] == "POST"]
                self.assertEqual(len(report_calls), 0 if expected_error else 1)
                self.assertEqual(result.is_error, expected_error is not None)
                if expected_error:
                    self.assertIsNone(result.structured_content)
                    self.assertIn(f"[{expected_error}]", result.content[0].text)
                else:
                    self.assertEqual(result.structured_content["status"], "partial" if case == "quality" else "complete")
                    self.assertEqual(result.structured_content["data"]["current"]["rows"][0]["metrics"]["sessions"], 10.0)
                    if case == "quality":
                        warnings = result.structured_content["warnings"]
                        self.assertTrue(any("采样" in warning for warning in warnings))
                        self.assertTrue(any("offset=100" in warning for warning in warnings))
                    json.dumps(result.structured_content, allow_nan=False)
                self.assertNotIn("synthetic-access-token", stderr.getvalue())

    async def test_malformed_quality_flags_are_not_silently_ignored(self) -> None:
        for metadata in ({"dataLossFromOtherRow": "false"}, {"subjectToThresholding": 1},
                         {"samplingMetadatas": "broken"}, {"dataTruncationReasons": [False]}, "broken"):
            with self.subTest(metadata=metadata), patch(
                "google.auth.transport.requests.AuthorizedSession.request",
                return_value=self.response({**self.report, "metadata": metadata}),
            ):
                with self.assertRaises(SeoDataError) as caught:
                    await self.adapter.analyze(**self.query)
                self.assertEqual(caught.exception.code, "invalid_response")
