from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from googleapiclient.errors import HttpError
from httplib2 import Response
from mcp import Client

from codex_seo_mcp import server as server_module
from codex_seo_mcp.adapters.page_quality import PageQualityAdapter
from codex_seo_mcp.clients.crux import CruxClient, CruxConfig
from codex_seo_mcp.clients.pagespeed import PageSpeedClient, PageSpeedConfig
from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class PageQualityBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = ProviderCache(ProviderCacheConfig(root=Path(directory.name)))
        self.lab_payload = {
            "lighthouseResult": {
                "requestedUrl": "https://example.com/page",
                "finalUrl": "https://example.com/page",
                "lighthouseVersion": "13.0.0",
                "categories": {"performance": {"score": 0.9}},
                "audits": {
                    "largest-contentful-paint": {"numericValue": 2300, "score": 0.8},
                    "cumulative-layout-shift": {"numericValue": 0.0, "score": 1.0},
                },
                "runWarnings": [],
            },
        }
        self.field_payloads = {"url": self.field_payload(), "origin": None}
        self.pagespeed = PageSpeedClient(
            PageSpeedConfig(api_key="synthetic-key", cache_ttl_seconds=0), cache=self.cache,
        )
        self.crux = CruxClient(CruxConfig(api_key="synthetic-key", cache_ttl_seconds=0), cache=self.cache)
        self.adapter = PageQualityAdapter(pagespeed=self.pagespeed, crux=self.crux)
        self.service = MagicMock()
        self.execute = self.service.records.return_value.queryRecord.return_value.execute
        self.execute.side_effect = self.serve_crux
        sdk = patch("googleapiclient.discovery.build", return_value=self.service)
        sdk.start()
        self.addCleanup(sdk.stop)
        http = patch(
            "codex_seo_mcp.clients.pagespeed.urlopen",
            side_effect=lambda *args, **kwargs: io.BytesIO(json.dumps(self.lab_payload).encode("utf-8")),
        )
        self.http = http.start()
        self.addCleanup(http.stop)

    @staticmethod
    def field_payload(scope: str = "url", key: str = "https://example.com/page", device: str = "PHONE") -> dict:
        return {"record": {
            "key": {scope: key, "formFactor": device},
            "metrics": {
                "largest_contentful_paint": {
                    "percentiles": {"p75": 2400},
                    "histogram": [{"start": 0, "end": 2500, "density": 0.8},
                                  {"start": 2500, "density": 0.2}],
                },
                "cumulative_layout_shift": {"percentiles": {"p75": "0.00"}},
            },
        }}

    def serve_crux(self) -> dict:
        body = self.service.records.return_value.queryRecord.call_args.kwargs["body"]
        scope = "url" if "url" in body else "origin"
        payload = self.field_payloads[scope]
        if payload is None:
            raise HttpError(Response({"status": "404"}), b'{"error":{"message":"No sample"}}')
        return deepcopy(payload)

    async def test_invalid_numbers_only_invalidate_the_affected_provider(self) -> None:
        valid_lab = deepcopy(self.lab_payload)
        invalid_values = (float("nan"), float("inf"), "NaN", "Infinity", 10 ** 400,
                          True, "private-invalid-metric", {})
        for source in ("lab_score", "lab_metric", "field_p75", "field_density"):
            for value in invalid_values:
                with self.subTest(source=source, value=value):
                    self.lab_payload = deepcopy(valid_lab)
                    self.field_payloads = {"url": self.field_payload(), "origin": None}
                    if source == "lab_score":
                        self.lab_payload["lighthouseResult"]["categories"]["performance"]["score"] = value
                    elif source == "lab_metric":
                        self.lab_payload["lighthouseResult"]["audits"]["largest-contentful-paint"]["numericValue"] = value
                    else:
                        metric = self.field_payloads["url"]["record"]["metrics"]["largest_contentful_paint"]
                        if source == "field_p75":
                            metric["percentiles"]["p75"] = value
                        else:
                            metric["histogram"][0]["density"] = value
                    result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
                    self.assertEqual(result.status, "partial")
                    self.assertEqual(result.provider, "crux" if source.startswith("lab") else "pagespeed")
                    self.assertTrue(any("invalid_response" in warning for warning in result.warnings))
                    self.assertNotIn("private-invalid-metric", str(result.to_dict()))
                    json.dumps(result.to_dict(), allow_nan=False)

    async def test_scores_and_density_cannot_be_clamped_into_valid_measurements(self) -> None:
        for source in ("score", "density"):
            for value in (-0.1, 1.2):
                with self.subTest(source=source, value=value):
                    self.lab_payload["lighthouseResult"]["categories"]["performance"]["score"] = 0.9
                    self.field_payloads = {"url": self.field_payload(), "origin": None}
                    if source == "score":
                        self.lab_payload["lighthouseResult"]["categories"]["performance"]["score"] = value
                    else:
                        self.field_payloads["url"]["record"]["metrics"]["largest_contentful_paint"]["histogram"][0]["density"] = value
                    result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
                    self.assertEqual(result.status, "partial")
                    self.assertEqual(result.provider, "crux" if source == "score" else "pagespeed")

    async def test_overflow_in_savings_sum_keeps_valid_field_measurements(self) -> None:
        self.lab_payload["lighthouseResult"]["audits"]["unused-javascript"] = {
            "score": 0.2, "details": {"items": [{"wastedBytes": 1e308}, {"wastedBytes": 1e308}]},
        }
        result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.provider, "crux")

    async def test_real_zero_and_unavailable_optional_measurements_remain_distinct(self) -> None:
        result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
        self.assertEqual(result.data.lab.metrics["cls"].numeric_value, 0.0)
        self.assertEqual(result.data.field.metrics["cls"].p75, 0.0)
        self.assertEqual(result.data.lab.category_scores["performance"], 90)
        self.assertIsNone(result.data.lab.category_scores["accessibility"])
        self.assertIsNone(result.data.lab.metrics["tbt"].numeric_value)
        self.assertEqual(result.status, "complete")

    async def test_result_shell_without_measurements_is_not_a_successful_provider(self) -> None:
        valid_lab = deepcopy(self.lab_payload)
        for source in ("lab", "field"):
            for shape in ("missing", "empty", "null_only"):
                with self.subTest(source=source, shape=shape):
                    self.lab_payload = deepcopy(valid_lab)
                    self.field_payloads = {"url": self.field_payload(), "origin": None}
                    if source == "lab":
                        self.lab_payload = {"lighthouseResult": {"lighthouseVersion": "13.0.0"}}
                        if shape != "missing":
                            self.lab_payload["lighthouseResult"].update({"categories": {}, "audits": {}})
                        if shape == "null_only":
                            self.lab_payload["lighthouseResult"]["categories"] = {"performance": {"score": None}}
                    else:
                        record = self.field_payloads["url"]["record"]
                        del record["metrics"]
                        if shape != "missing":
                            record["metrics"] = {}
                        if shape == "null_only":
                            record["metrics"] = {"largest_contentful_paint": {"percentiles": {"p75": None}}}
                    result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
                    self.assertEqual(result.status, "partial")
                    self.assertEqual(result.provider, "crux" if source == "lab" else "pagespeed")
                    self.assertTrue(any("invalid_response" in item for item in result.warnings))

    async def test_two_empty_shells_fail_instead_of_claiming_complete_measurement(self) -> None:
        self.lab_payload = {"lighthouseResult": {"lighthouseVersion": "13.0.0"}}
        self.field_payloads["url"] = {"record": {"key": {"url": "https://example.com/page", "formFactor": "PHONE"}}}
        with self.assertRaises(SeoDataError) as caught:
            await self.adapter.inspect("https://example.com/page", strategy="mobile")
        self.assertEqual(caught.exception.code, "invalid_response")

    async def test_real_zero_score_and_histogram_without_percentile_are_usable(self) -> None:
        self.lab_payload = {"lighthouseResult": {"categories": {"performance": {"score": 0.0}}}}
        metric = self.field_payloads["url"]["record"]["metrics"]["largest_contentful_paint"]
        del metric["percentiles"]
        del self.field_payloads["url"]["record"]["metrics"]["cumulative_layout_shift"]
        result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.lab.category_scores["performance"], 0)
        self.assertIsNone(result.data.field.metrics["lcp"].p75)
        self.assertEqual(len(result.data.field.metrics["lcp"].histogram), 2)

    async def test_crux_record_must_match_requested_device_scope_and_target(self) -> None:
        invalid_keys = [
            {"url": "https://example.com/page", "formFactor": "DESKTOP"},
            {"url": "https://example.com/page"},
            {"origin": "https://example.com", "formFactor": "PHONE"},
            {"url": "https://example.com/page", "origin": "https://example.com", "formFactor": "PHONE"},
            {"url": "https://other.example/page", "formFactor": "PHONE"},
            {"url": "", "formFactor": "PHONE"},
        ]
        for key in invalid_keys:
            with self.subTest(key=key):
                self.field_payloads["url"] = self.field_payload()
                self.field_payloads["url"]["record"]["key"] = key
                self.execute.reset_mock()
                result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
                self.assertEqual(result.status, "partial")
                self.assertEqual(result.provider, "pagespeed")
                self.assertIsNone(result.data.field)
                self.assertEqual(self.execute.call_count, 1)

    async def test_crux_origin_fallback_must_stay_on_the_requested_site(self) -> None:
        for key in ({"origin": "https://other.example", "formFactor": "PHONE"},
                    {"url": "https://example.com/page", "formFactor": "PHONE"},
                    {"origin": "https://example.com", "formFactor": "DESKTOP"}):
            with self.subTest(key=key):
                record = self.field_payload("origin", "https://example.com")
                record["record"]["key"] = key
                self.field_payloads = {"url": None, "origin": record}
                result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
                self.assertEqual(result.provider, "pagespeed")
                self.assertIsNone(result.data.field)

    async def test_crux_explicit_normalization_links_the_requested_url_to_the_record(self) -> None:
        requested = "https://example.com/page?tracking=1"
        normalized = "https://example.com/page"
        for original, normalized_url, valid in ((requested, normalized, True),
                                               ("https://other.example/", normalized, False),
                                               (requested, "https://other.example/", False)):
            with self.subTest(original=original, normalized=normalized_url):
                self.field_payloads["url"] = self.field_payload(key=normalized)
                self.field_payloads["url"]["urlNormalizationDetails"] = {
                    "originalUrl": original, "normalizedUrl": normalized_url,
                }
                result = await self.adapter.inspect(requested, strategy="mobile")
                self.assertEqual(result.status, "complete" if valid else "partial")
                if valid:
                    self.assertEqual(result.data.field.key, normalized)
                else:
                    self.assertIsNone(result.data.field)

    async def test_matching_desktop_record_remains_a_desktop_measurement(self) -> None:
        self.field_payloads["url"] = self.field_payload(device="DESKTOP")
        result = await self.adapter.inspect("https://example.com/page", strategy="desktop")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.strategy, "desktop")
        self.assertEqual(result.data.field.form_factor, "DESKTOP")

    async def test_failed_lighthouse_runs_are_not_cached_and_can_recover(self) -> None:
        valid = deepcopy(self.lab_payload)
        failures = [
            {"lighthouseResult": {"runtimeError": {"code": "NO_FCP", "message": "private-runtime-detail"}}},
            {"lighthouseResult": {"runtimeError": "private-runtime-detail"}},
            {"error": {"message": "private-provider-detail"}},
            {},
        ]
        self.pagespeed.config.cache_ttl_seconds = 1800
        for failed_payload in failures:
            with self.subTest(payload=failed_payload):
                self.cache.clear(provider="pagespeed")
                self.http.reset_mock()
                self.lab_payload = failed_payload
                for _ in range(2):
                    result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
                    self.assertEqual(result.status, "partial")
                    self.assertEqual(result.provider, "crux")
                self.assertEqual(self.http.call_count, 2)
                self.lab_payload = deepcopy(valid)
                for _ in range(2):
                    result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
                    self.assertEqual(result.status, "complete")
                self.assertEqual(self.http.call_count, 3)

    async def test_preexisting_failed_lighthouse_cache_is_refetched(self) -> None:
        self.pagespeed.config.cache_ttl_seconds = 1800
        await self.adapter.inspect("https://example.com/page", strategy="mobile")
        path = next((self.cache.config.root / "pagespeed").rglob("*.json"))
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved["value"] = {"lighthouseResult": {"runtimeError": {"code": "NO_FCP"}}}
        path.write_text(json.dumps(saved), encoding="utf-8")
        for _ in range(2):
            result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
            self.assertEqual(result.status, "complete")
        self.assertEqual(self.http.call_count, 2)

    async def test_runtime_failure_does_not_return_provider_message_without_field_data(self) -> None:
        self.lab_payload = {"lighthouseResult": {"runtimeError": {
            "code": "private-runtime-code", "message": "private-runtime-detail",
        }}}
        self.field_payloads = {"url": None, "origin": None}
        with self.assertRaises(SeoDataError) as caught:
            await self.adapter.inspect("https://example.com/page", strategy="mobile")
        self.assertEqual(caught.exception.code, "invalid_response")
        self.assertNotIn("private-", caught.exception.message)

    async def test_explicit_no_error_runtime_status_remains_usable(self) -> None:
        self.lab_payload["lighthouseResult"]["runtimeError"] = {"code": "NO_ERROR"}
        result = await self.adapter.inspect("https://example.com/page", strategy="mobile")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.lab.metrics["lcp"].numeric_value, 2300)

    async def test_mcp_preserves_each_failure_boundary_and_safe_structured_results(self) -> None:
        valid_lab = deepcopy(self.lab_payload)
        cases = (
            ("invalid_url", "invalid_request", None),
            ("bad_number", None, "crux"),
            ("empty_both", "invalid_response", None),
            ("wrong_device", None, "pagespeed"),
            ("runtime_failed", None, "crux"),
            ("runtime_without_field", "invalid_response", None),
            ("valid", None, "pagespeed+crux"),
        )
        stderr = io.StringIO()
        with (
            patch.object(server_module, "_page_quality", self.adapter),
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            async with Client(server_module.mcp, mode="2026-07-28") as client:
                for case, error, provider in cases:
                    with self.subTest(case=case):
                        self.lab_payload = deepcopy(valid_lab)
                        self.field_payloads = {"url": self.field_payload(), "origin": None}
                        target = "https://example.com/page"
                        if case == "invalid_url":
                            target = "https://user:private-password@example.com/"
                        elif case == "bad_number":
                            self.lab_payload["lighthouseResult"]["categories"]["performance"]["score"] = float("nan")
                        elif case == "empty_both":
                            self.lab_payload = {"lighthouseResult": {"lighthouseVersion": "13.0.0"}}
                            self.field_payloads["url"]["record"]["metrics"] = {}
                        elif case == "wrong_device":
                            self.field_payloads["url"]["record"]["key"]["formFactor"] = "DESKTOP"
                        elif case.startswith("runtime"):
                            self.lab_payload = {"lighthouseResult": {"runtimeError": {
                                "code": "NO_FCP", "message": "private-runtime-detail",
                            }}}
                            if case == "runtime_without_field":
                                self.field_payloads = {"url": None, "origin": None}
                        self.http.reset_mock()
                        self.execute.reset_mock()
                        result = await client.call_tool("check_page_performance", {"url": target, "strategy": "mobile"})
                        self.assertEqual(result.is_error, error is not None)
                        if error:
                            self.assertIsNone(result.structured_content)
                            self.assertIn(f"[{error}]", result.content[0].text)
                            self.assertNotIn("private-", result.content[0].text)
                        else:
                            output = result.structured_content
                            self.assertEqual(output["provider"], provider)
                            self.assertEqual(output["status"], "complete" if case == "valid" else "partial")
                            json.dumps(output, allow_nan=False)
                        self.assertEqual(self.http.call_count, 0 if case == "invalid_url" else 1)
                        self.assertEqual(self.execute.call_count, 0 if case == "invalid_url" else 2 if case == "runtime_without_field" else 1)
        self.assertNotIn("private-", stderr.getvalue())
        self.assertNotIn("synthetic-key", stderr.getvalue())

    async def test_invalid_target_never_reaches_either_provider(self) -> None:
        for target in ("", "ftp://example.com/", "https://user:private-password@example.com/",
                       "https://[broken", "https://example.com:99999/", "https://example.com:bad/",
                       "https://exa mple.com/"):
            with self.subTest(target=target):
                self.http.reset_mock()
                self.execute.reset_mock()
                with self.assertRaises(SeoDataError) as caught:
                    await self.adapter.inspect(target, strategy="mobile")
                self.assertEqual(caught.exception.code, "invalid_request")
                self.assertNotIn("private-password", caught.exception.message)
                self.assertEqual(self.http.call_count, 0)
                self.assertEqual(self.execute.call_count, 0)

    async def test_both_providers_receive_the_same_normalized_url(self) -> None:
        target = "https://example.com/page?x=1"
        self.field_payloads["url"] = self.field_payload(key=target)
        result = await self.adapter.inspect("example.com/page?x=1#section", strategy="mobile")
        request = self.http.call_args.args[0]
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)["url"], [target])
        self.assertEqual(self.service.records.return_value.queryRecord.call_args.kwargs["body"]["url"], target)
        self.assertEqual(result.status, "complete")

    async def test_origin_fallback_handles_bare_hosts_and_ipv6_authorities(self) -> None:
        for target, origin in (("example.com/page", "https://example.com"),
                               ("https://[2001:4860:4860::8888]:8443/page", "https://[2001:4860:4860::8888]:8443")):
            with self.subTest(target=target):
                self.field_payloads = {"url": None, "origin": self.field_payload("origin", origin)}
                result = await self.adapter.inspect(target, strategy="mobile")
                self.assertIsNotNone(result.data.field)
                body = self.service.records.return_value.queryRecord.call_args.kwargs["body"]
                self.assertEqual(body["origin"], origin)
                self.assertEqual(result.data.field.scope, "origin")
                self.assertEqual(result.status, "complete")
