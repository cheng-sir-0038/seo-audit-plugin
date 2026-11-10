from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from mcp import Client
from requests import Response
from requests.exceptions import ConnectionError, ConnectTimeout, ReadTimeout, SSLError, Timeout

from codex_seo_mcp import server as server_module
from codex_seo_mcp.adapters.web_analytics import WebAnalyticsAdapter
from codex_seo_mcp.auth.ga4_oauth import Ga4AuthManager, Ga4OAuthConfig
from codex_seo_mcp.clients.ga4 import Ga4Client, Ga4ClientConfig
from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class Ga4FailureBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        token_path = root / "synthetic-token.json"
        token_path.write_text(json.dumps({
            "token": "synthetic-access-token",
            "refresh_token": "synthetic-refresh-token",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-client-secret",
            "expiry": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }), encoding="utf-8")
        auth = Ga4AuthManager(Ga4OAuthConfig(
            client_id="synthetic-client",
            client_secret="synthetic-client-secret",
            token_path=token_path,
        ))
        self.ga4 = Ga4Client(
            auth=auth,
            config=Ga4ClientConfig(cache_ttl_seconds=1800),
            cache=ProviderCache(ProviderCacheConfig(root=root / "cache")),
        )

    async def call_operation(self, operation: str) -> object:
        if operation == "report":
            return (await self.ga4.run_report("222", {
                "dateRanges": [{"startDate": "2026-08-01", "endDate": "2026-08-28"}],
                "metrics": [{"name": "sessions"}],
            })).payload
        if operation == "properties":
            return await self.ga4.list_properties()
        if operation == "streams":
            return await self.ga4.list_data_streams("222")
        raise AssertionError(f"Unknown test operation: {operation}")

    @staticmethod
    def response(payload: dict[str, object], status: int = 200) -> Response:
        response = Response()
        response.status_code = status
        response._content = json.dumps(payload).encode("utf-8")
        response.encoding = "utf-8"
        return response

    @staticmethod
    def admin_payload(operation: str) -> dict[str, object]:
        if operation == "properties":
            return {"accountSummaries": [{
                "account": "accounts/111", "displayName": "Example account",
                "propertySummaries": [{"property": "properties/222", "displayName": "Example site"}],
            }]}
        if operation == "streams":
            return {"dataStreams": [{
                "name": "properties/222/dataStreams/333", "type": "WEB_DATA_STREAM",
                "displayName": "Example web stream",
                "webStreamData": {"measurementId": "G-EXAMPLE", "defaultUri": "https://example.com/"},
            }]}
        raise AssertionError("Unknown admin operation in test")

    async def test_invalid_resource_identifiers_never_become_accessible_candidates(self) -> None:
        for field in ("account", "property", "stream"):
            for value in (123, True, {"private-resource": 1}, "123", "unknown/123", "properties/not-an-id", "accounts/111/extra", "properties/１２３"):
                operation = "streams" if field == "stream" else "properties"
                with self.subTest(field=field, value=value):
                    self.ga4.cache.clear(provider="ga4")
                    payload = self.admin_payload(operation)
                    if field == "account":
                        payload["accountSummaries"][0]["account"] = value
                    elif field == "property":
                        payload["accountSummaries"][0]["propertySummaries"][0]["property"] = value
                    else:
                        payload["dataStreams"][0]["name"] = value
                    with patch(
                        "google.auth.transport.requests.AuthorizedSession.request",
                        return_value=self.response(payload),
                    ) as provider:
                        for _ in range(2):
                            with self.assertRaises(SeoDataError) as caught:
                                await self.call_operation(operation)
                            self.assertEqual(caught.exception.code, "invalid_response")
                            self.assertNotIn("private-resource", caught.exception.message)
                        self.assertEqual(provider.call_count, 2)

    async def test_valid_admin_resources_keep_their_identifiers_and_reuse_cache(self) -> None:
        for operation, expected in (
            ("properties", [{"account_id": "111", "account_name": "Example account", "property_id": "222", "property_name": "Example site"}]),
            ("streams", [{"data_stream_id": "333", "display_name": "Example web stream", "type": "WEB_DATA_STREAM", "measurement_id": "G-EXAMPLE", "default_uri": "https://example.com/"}]),
        ):
            with self.subTest(operation=operation), patch(
                "google.auth.transport.requests.AuthorizedSession.request",
                return_value=self.response(self.admin_payload(operation)),
            ) as provider:
                self.assertEqual(await self.call_operation(operation), expected)
                self.assertEqual(await self.call_operation(operation), expected)
                self.assertEqual(provider.call_count, 1)

    async def test_corrupt_admin_cache_is_refetched_without_silently_dropping_entries(self) -> None:
        for operation, id_field, text_field in (
            ("properties", "property_id", "property_name"),
            ("streams", "data_stream_id", "default_uri"),
        ):
            for corruption in ("non_object", "mixed", "missing_id", "bad_id", "bad_text"):
                with self.subTest(operation=operation, corruption=corruption):
                    self.ga4.cache.clear(provider="ga4")
                    with patch(
                        "google.auth.transport.requests.AuthorizedSession.request",
                        return_value=self.response(self.admin_payload(operation)),
                    ):
                        expected = await self.call_operation(operation)

                    # 故意破坏刚由公共入口写入的缓存文件，而非替换缓存类。
                    files = list(self.ga4.cache.config.root.rglob("*.json"))
                    self.assertEqual(len(files), 1)
                    saved = json.loads(files[0].read_text(encoding="utf-8"))
                    row = dict(expected[0])
                    if corruption == "non_object":
                        saved["value"] = [None]
                    elif corruption == "mixed":
                        saved["value"] = [row, None]
                    else:
                        if corruption == "missing_id":
                            del row[id_field]
                        elif corruption == "bad_id":
                            row[id_field] = "private-invalid-id"
                        else:
                            row[text_field] = None
                        saved["value"] = [row]
                    files[0].write_text(json.dumps(saved), encoding="utf-8")

                    with patch(
                        "google.auth.transport.requests.AuthorizedSession.request",
                        return_value=self.response(self.admin_payload(operation)),
                    ) as provider:
                        self.assertEqual(await self.call_operation(operation), expected)
                        self.assertEqual(await self.call_operation(operation), expected)
                        self.assertEqual(provider.call_count, 1)

    async def test_valid_empty_admin_cache_remains_a_cache_hit(self) -> None:
        for operation in ("properties", "streams"):
            with self.subTest(operation=operation), patch(
                "google.auth.transport.requests.AuthorizedSession.request",
                return_value=self.response({}),
            ) as provider:
                self.assertEqual(await self.call_operation(operation), [])
                self.assertEqual(await self.call_operation(operation), [])
                self.assertEqual(provider.call_count, 1)

    async def test_network_failures_return_stable_errors_without_caching_or_retrying(self) -> None:
        for operation in ("report", "properties", "streams"):
            for error_type in (Timeout, ReadTimeout, ConnectTimeout, ConnectionError, SSLError):
                with self.subTest(operation=operation, error=error_type.__name__):
                    # 只替换第三方 HTTP；授权加载、Client、Transport 与磁盘缓存照常运行。
                    with patch(
                        "google.auth.transport.requests.AuthorizedSession.request",
                        side_effect=error_type("provider-private-url?token=private-value"),
                    ) as provider:
                        for _ in range(2):
                            with self.assertRaises(SeoDataError) as caught:
                                await self.call_operation(operation)
                            self.assertEqual(caught.exception.code, "provider_unavailable")
                            self.assertNotIn("private", caught.exception.message)
                        self.assertEqual(provider.call_count, 2)

    async def test_http_success_with_error_body_is_not_returned_or_cached_as_success(self) -> None:
        for operation in ("report", "properties", "streams"):
            for error in ({"message": "private-provider-error", "code": 503}, None):
                with self.subTest(operation=operation, error=error):
                    self.ga4.cache.clear(provider="ga4")
                    with patch(
                        "google.auth.transport.requests.AuthorizedSession.request",
                        return_value=self.response({"error": error}),
                    ) as provider:
                        for _ in range(2):
                            with self.assertRaises(SeoDataError) as caught:
                                await self.call_operation(operation)
                            self.assertEqual(caught.exception.code, "invalid_response")
                            self.assertNotIn("private-provider-error", caught.exception.message)
                        self.assertEqual(provider.call_count, 2)

        with patch(
            "google.auth.transport.requests.AuthorizedSession.request",
            return_value=self.response({}),
        ):
            self.ga4.cache.clear(provider="ga4")
            self.assertEqual(await self.call_operation("properties"), [])
            self.assertEqual(await self.call_operation("streams"), [])

    async def test_invalid_page_tokens_fail_before_requesting_another_page_or_caching(self) -> None:
        for operation in ("properties", "streams"):
            for token in (False, 0, True, 12, [], {"private-cursor": 1}):
                with self.subTest(operation=operation, token=token):
                    self.ga4.cache.clear(provider="ga4")
                    for _ in range(2):
                        with patch(
                            "google.auth.transport.requests.AuthorizedSession.request",
                            side_effect=[self.response({"nextPageToken": token}), self.response({})],
                        ) as provider:
                            with self.assertRaises(SeoDataError) as caught:
                                await self.call_operation(operation)
                            self.assertEqual(caught.exception.code, "invalid_response")
                            self.assertNotIn("private-cursor", caught.exception.message)
                            self.assertEqual(provider.call_count, 1)

    async def test_page_tokens_are_forwarded_unchanged_even_after_an_empty_page(self) -> None:
        token = " opaque+cursor/== "
        for operation in ("properties", "streams"):
            with self.subTest(operation=operation):
                self.ga4.cache.clear(provider="ga4")
                with patch(
                    "google.auth.transport.requests.AuthorizedSession.request",
                    side_effect=[self.response({"nextPageToken": token}), self.response({})],
                ) as provider:
                    self.assertEqual(await self.call_operation(operation), [])
                self.assertEqual(provider.call_count, 2)
                self.assertEqual(provider.call_args_list[1].kwargs["params"]["pageToken"], token)

    async def test_http_session_is_closed_on_success_http_errors_and_exceptions(self) -> None:
        from google.auth.transport.requests import AuthorizedSession

        real_close = AuthorizedSession.close
        bad_json = self.response({})
        bad_json._content = b"not-json"
        cases = [
            (self.response({}), None),
            (self.response({}, status=403), "permission_denied"),
            (ReadTimeout("private-network-error"), "provider_unavailable"),
            (bad_json, "invalid_response"),
            (RuntimeError("test-programming-error"), "programming_error"),
        ]
        for operation in ("report", "properties", "streams"):
            for outcome, expected_error in cases:
                with self.subTest(operation=operation, error=expected_error):
                    self.ga4.cache.clear(provider="ga4")
                    closed_sessions = []

                    def close(session):
                        closed_sessions.append(session)
                        return real_close(session)

                    with (
                        patch.object(AuthorizedSession, "close", new=close),
                        patch.object(AuthorizedSession, "request", side_effect=outcome if isinstance(outcome, Exception) else None, return_value=outcome) as provider,
                    ):
                        if expected_error == "programming_error":
                            with self.assertRaises(RuntimeError):
                                await self.call_operation(operation)
                        elif expected_error:
                            with self.assertRaises(SeoDataError) as caught:
                                await self.call_operation(operation)
                            self.assertEqual(caught.exception.code, expected_error)
                        else:
                            await self.call_operation(operation)
                    self.assertEqual(provider.call_count, 1)
                    self.assertEqual(len(closed_sessions), 1)

    async def test_network_failure_can_recover_on_an_explicit_new_call(self) -> None:
        with patch(
            "google.auth.transport.requests.AuthorizedSession.request",
            side_effect=[ReadTimeout("private-network-error"), self.response({"rowCount": 0})],
        ) as provider:
            with self.assertRaises(SeoDataError):
                await self.call_operation("report")
            self.assertEqual(await self.call_operation("report"), {"rowCount": 0})
            self.assertEqual(await self.call_operation("report"), {"rowCount": 0})
            self.assertEqual(provider.call_count, 2)

    async def test_unexpected_programming_error_is_not_mislabeled_as_network_failure(self) -> None:
        for operation in ("report", "properties", "streams"):
            with self.subTest(operation=operation), patch(
                "google.auth.transport.requests.AuthorizedSession.request",
                side_effect=RuntimeError("test-programming-error"),
            ) as provider:
                with self.assertRaisesRegex(RuntimeError, "test-programming-error"):
                    await self.call_operation(operation)
                self.assertEqual(provider.call_count, 1)

    async def test_mcp_stops_before_report_when_admin_metadata_is_invalid(self) -> None:
        malformed_resource = self.admin_payload("properties")
        malformed_resource["accountSummaries"][0]["propertySummaries"][0]["property"] = "private-invalid-resource"
        malformed_stream = self.admin_payload("streams")
        malformed_stream["dataStreams"][0]["name"] = "private-invalid-stream"
        cases = [
            ("properties", {"error": {"message": "private-error"}}),
            ("properties", {"nextPageToken": False}),
            ("properties", malformed_resource),
            ("streams", malformed_stream),
        ]
        ga4 = Ga4Client(auth=self.ga4.auth, cache=self.ga4.cache, config=Ga4ClientConfig(cache_ttl_seconds=0))
        stderr = io.StringIO()
        with (
            patch.object(server_module, "_ga4", ga4),
            patch.object(server_module, "_web_analytics", WebAnalyticsAdapter(client=ga4)),
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            async with Client(server_module.mcp, mode="2026-07-28") as client:
                for bad_operation, payload in cases:
                    with self.subTest(operation=bad_operation):
                        def respond(method: str, url: str, **kwargs) -> Response:
                            if method == "GET" and url.endswith("/accountSummaries"):
                                return self.response(payload if bad_operation == "properties" else self.admin_payload("properties"))
                            if method == "GET" and url.endswith("/properties/222/dataStreams"):
                                return self.response(payload if bad_operation == "streams" else self.admin_payload("streams"))
                            raise AssertionError("Report must not run when identity is invalid")

                        with patch(
                            "google.auth.transport.requests.AuthorizedSession.request",
                            side_effect=respond,
                        ) as provider:
                            result = await client.call_tool("analyze_organic_traffic", {
                                "target": "example.com", "start_date": "2026-08-01", "end_date": "2026-08-28",
                            })
                        self.assertTrue(result.is_error)
                        self.assertIsNone(result.structured_content)
                        self.assertIn("[invalid_response]", result.content[0].text)
                        self.assertNotIn("private-", result.content[0].text)
                        self.assertTrue(all(call.args[0] == "GET" for call in provider.call_args_list))
        self.assertNotIn("private-", stderr.getvalue())

    async def test_mcp_keeps_network_and_invalid_report_errors_distinct(self) -> None:
        properties = {"accountSummaries": [{
            "account": "accounts/111",
            "propertySummaries": [{"property": "properties/222", "displayName": "Example"}],
        }]}
        valid_report = {
            "dimensionHeaders": [{"name": "deviceCategory"}],
            "metricHeaders": [{"name": name} for name in (
                "sessions", "activeUsers", "engagedSessions", "engagementRate",
                "keyEvents", "sessionKeyEventRate", "totalRevenue",
            )],
            "rows": [{
                "dimensionValues": [{"value": "mobile"}],
                "metricValues": [{"value": value} for value in (
                    "10", "8", "6", "0.6", "1", "0.1", "12.5",
                )],
            }],
            "rowCount": 1,
        }
        malformed = deepcopy(valid_report)
        malformed["rows"][0]["metricValues"][0]["value"] = "private-report-value"
        not_finite = deepcopy(valid_report)
        not_finite["rows"][0]["metricValues"][0]["value"] = "NaN"
        invalid_total = deepcopy(valid_report)
        invalid_total["totals"] = deepcopy(valid_report["rows"])
        invalid_total["totals"][0]["metricValues"][6]["value"] = "Infinity"
        invalid_dimension = deepcopy(valid_report)
        invalid_dimension["rows"][0]["dimensionValues"][0]["value"] = {"private-dimension-value": 1}
        invalid_dimension_header = deepcopy(valid_report)
        invalid_dimension_header["dimensionHeaders"][0]["name"] = "private-dimension-header"
        invalid_metric_header = deepcopy(valid_report)
        invalid_metric_header["metricHeaders"][0]["name"] = "private-metric-header"
        cases = [
            (ReadTimeout("private-network-error"), "provider_unavailable"),
            (self.response(malformed), "invalid_response"),
            (self.response(not_finite), "invalid_response"),
            (self.response(invalid_total), "invalid_response"),
            (self.response({**valid_report, "rowCount": 1.5}), "invalid_response"),
            (self.response({**valid_report, "rowCount": True}), "invalid_response"),
            (self.response(invalid_dimension), "invalid_response"),
            (self.response(invalid_dimension_header), "invalid_response"),
            (self.response(invalid_metric_header), "invalid_response"),
            (self.response({}, status=401), "authorization_required"),
            (self.response({}, status=403), "permission_denied"),
            (self.response({}, status=429), "quota_exceeded"),
            (self.response(valid_report), None),
        ]
        # 每次供应商响应都不同，显式关闭测试客户端缓存；不替换插件内部实现。
        ga4 = Ga4Client(auth=self.ga4.auth, cache=self.ga4.cache, config=Ga4ClientConfig(cache_ttl_seconds=0))
        stderr = io.StringIO()
        with (
            patch.object(server_module, "_ga4", ga4),
            patch.object(server_module, "_web_analytics", WebAnalyticsAdapter(client=ga4)),
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            async with Client(server_module.mcp, mode="2026-07-28") as client:
                for outcome, expected_code in cases:
                    with self.subTest(error=expected_code):
                        def respond(method: str, url: str, **kwargs) -> Response:
                            if method == "GET" and url.endswith("/accountSummaries"):
                                return self.response(properties)
                            if method == "POST" and url.endswith("/properties/222:runReport"):
                                if isinstance(outcome, Exception):
                                    raise outcome
                                return outcome
                            raise AssertionError("Unexpected provider request in test")

                        with patch(
                            "google.auth.transport.requests.AuthorizedSession.request",
                            side_effect=respond,
                        ) as provider:
                            result = await client.call_tool("analyze_organic_traffic", {
                                "target": "222", "start_date": "2026-08-01", "end_date": "2026-08-28",
                                "view": "devices",
                            })
                        report_calls = [call for call in provider.call_args_list if call.args[0] == "POST"]
                        self.assertEqual(len(report_calls), 1)
                        self.assertEqual(result.is_error, expected_code is not None)
                        if expected_code:
                            self.assertIsNone(result.structured_content)
                            self.assertIn(f"[{expected_code}]", result.content[0].text)
                            self.assertNotIn("private-", result.content[0].text)
                        else:
                            self.assertEqual(result.structured_content["status"], "complete")
                            self.assertEqual(result.structured_content["data"]["current"]["rows"][0]["metrics"]["sessions"], 10.0)
                            self.assertEqual(result.structured_content["data"]["current"]["rows"][0]["dimensions"], {"deviceCategory": "mobile"})
                            json.dumps(result.structured_content, allow_nan=False)
        self.assertNotIn("private-", stderr.getvalue())
