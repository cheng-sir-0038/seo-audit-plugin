from __future__ import annotations

import inspect
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout, suppress
from dataclasses import dataclass
from unittest.mock import patch

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.common import CapabilityResult
from codex_seo_mcp.observability import emit_event, observe_tool
from codex_seo_mcp.tool_boundary import SeoToolError, map_seo_data_errors


class ObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_closed_stderr_does_not_skip_tool_or_replace_success(self) -> None:
        for close_before_call in (True, False):
            with self.subTest(close_before_call=close_before_call):
                stderr = io.StringIO()
                stdout = io.StringIO()
                expected = {"status": "complete", "data": {"count": 3}}
                calls = 0

                async def sample() -> dict[str, object]:
                    nonlocal calls
                    calls += 1
                    stderr.close()
                    return expected

                wrapped = observe_tool(tool="sample")(sample)
                if close_before_call:
                    stderr.close()
                with (
                    patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
                    redirect_stderr(stderr),
                    redirect_stdout(stdout),
                ):
                    result = await wrapped()

                self.assertIs(result, expected)
                self.assertEqual(calls, 1)
                self.assertEqual(stdout.getvalue(), "")

    async def test_broken_stderr_pipe_preserves_the_original_tool_error(self) -> None:
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        stderr = os.fdopen(write_fd, "w", encoding="utf-8")
        stdout = io.StringIO()
        calls = 0

        @map_seo_data_errors
        async def sample() -> dict[str, object]:
            nonlocal calls
            calls += 1
            raise SeoDataError(SeoDataErrorCode.QUOTA_EXCEEDED, "provider quota exceeded")

        wrapped = observe_tool(tool="sample")(sample)
        try:
            with (
                patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
                redirect_stderr(stderr),
                redirect_stdout(stdout),
            ):
                with self.assertRaises(SeoToolError) as caught:
                    await wrapped()
        finally:
            with suppress(OSError):
                stderr.close()

        self.assertEqual(caught.exception.seo_code, "quota_exceeded")
        self.assertEqual(calls, 1)
        self.assertEqual(stdout.getvalue(), "")

    async def test_observe_tool_preserves_signature_and_logs_only_safe_metadata(self) -> None:
        async def sample(url: str, strategy: str, locale: str = "zh-CN") -> dict[str, object]:
            return {
                "status": "complete",
                "provider": "pagespeed+crux",
                "warnings": ["one"],
                "data": {"raw": "must-not-be-logged"},
            }

        wrapped = observe_tool(
            tool="check_page_performance",
            capability="PageQuality",
            target_arg="url",
            strategy_arg="strategy",
        )(sample)
        self.assertEqual(inspect.signature(wrapped), inspect.signature(sample))

        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            result = await wrapped(
                "https://example.com/private?token=secret",
                "mobile",
            )

        self.assertEqual(result["status"], "complete")
        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        self.assertEqual([item["event"] for item in events], ["tool_call_started", "tool_call_completed"])
        self.assertEqual(events[0]["target_host"], "example.com")
        self.assertEqual(events[0]["strategy"], "mobile")
        self.assertEqual(events[1]["provider"], "pagespeed+crux")
        self.assertEqual(events[1]["warning_count"], 1)
        self.assertEqual(events[1]["result_status"], "complete")

        text = stderr.getvalue()
        self.assertNotIn("token=secret", text)
        self.assertNotIn("/private", text)
        self.assertNotIn("must-not-be-logged", text)

    async def test_native_tool_error_event_keeps_stable_code_without_error_message(self) -> None:
        @map_seo_data_errors
        async def sample(query: str) -> dict[str, object]:
            del query
            raise SeoDataError(
                SeoDataErrorCode.QUOTA_EXCEEDED,
                "secret-provider-message",
            )

        wrapped = observe_tool(
            tool="research_serp",
            capability="SerpResearch",
            target_arg="query",
        )(sample)
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SeoToolError):
                await wrapped("private query text")

        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        self.assertEqual(events[-1]["event"], "tool_call_failed")
        self.assertEqual(events[-1]["error_code"], "quota_exceeded")
        self.assertEqual(
            events[0]["request_fingerprint"],
            events[-1]["request_fingerprint"],
        )
        self.assertNotIn("secret-provider-message", stderr.getvalue())
        self.assertNotIn("private query text", stderr.getvalue())

    async def test_fingerprints_are_stable_without_logging_raw_arguments_or_results(self) -> None:
        async def sample(query: str, api_key: str) -> dict[str, object]:
            return {
                "status": "complete",
                "data": {"query": query, "secret": api_key},
            }

        wrapped = observe_tool(
            tool="research_keywords",
            capability="KeywordResearch",
        )(sample)
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            await wrapped("private keyword", "key-one")
            await wrapped("private keyword", "key-two")

        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        starts = [event for event in events if event["event"] == "tool_call_started"]
        completed = [event for event in events if event["event"] == "tool_call_completed"]

        # Secret-like values are redacted before hashing, so rotating only a secret does not
        # change either logical fingerprint. Only the hashes are emitted.
        self.assertEqual(starts[0]["request_fingerprint"], starts[1]["request_fingerprint"])
        self.assertEqual(
            completed[0]["result_fingerprint"],
            completed[1]["result_fingerprint"],
        )
        self.assertEqual(
            starts[0]["request_fingerprint"],
            completed[0]["request_fingerprint"],
        )
        text = stderr.getvalue()
        self.assertNotIn("private keyword", text)
        self.assertNotIn("key-one", text)
        self.assertNotIn("key-two", text)

    async def test_result_fingerprint_ignores_fetch_time_but_keeps_data_timestamps(self) -> None:
        observations = iter([
            ("2026-09-18T01:00:00+00:00", "2026-09-17T00:00:00+00:00"),
            ("2026-09-18T01:01:00+00:00", "2026-09-17T00:00:00+00:00"),
            ("2026-09-18T01:02:00+00:00", "2026-09-18T00:00:00+00:00"),
        ])

        async def sample(url: str) -> dict[str, object]:
            fetched_at, observed_at = next(observations)
            result = CapabilityResult.complete(
                capability="SiteSafety",
                provider="google-safe-browsing-v4",
                source_kind="third_party",
                data={"url": url, "status": "no_known_threats", "observed_at": observed_at},
            )
            result.fetched_at = fetched_at
            return result.to_dict()

        wrapped = observe_tool(tool="check_site_safety", capability="SiteSafety")(sample)
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            first = await wrapped("https://example.com/")
            second = await wrapped("https://example.com/")
            await wrapped("https://example.com/")

        completed = [
            event for line in stderr.getvalue().splitlines()
            if (event := json.loads(line))["event"] == "tool_call_completed"
        ]
        # Keep fetch metadata in the result, but do not mistake it for new evidence.
        self.assertNotEqual(first["fetched_at"], second["fetched_at"])
        self.assertEqual(completed[0]["result_fingerprint"], completed[1]["result_fingerprint"])
        self.assertNotEqual(completed[1]["result_fingerprint"], completed[2]["result_fingerprint"])

    async def test_resolved_dataclass_scope_changes_request_fingerprint(self) -> None:
        @dataclass(frozen=True)
        class Scope:
            property_id: str

        async def sample(target: str, scope: Scope) -> dict[str, object]:
            del target, scope
            return {"status": "complete"}

        wrapped = observe_tool(tool="analyze_organic_traffic")(sample)
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            await wrapped("example.com", Scope("101"))
            await wrapped("example.com", Scope("202"))

        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        starts = [event for event in events if event["event"] == "tool_call_started"]
        self.assertNotEqual(
            starts[0]["request_fingerprint"],
            starts[1]["request_fingerprint"],
        )

    async def test_observability_can_be_disabled_without_affecting_tool_result(self) -> None:
        async def sample() -> dict[str, object]:
            return {"status": "complete"}

        wrapped = observe_tool(tool="check_search_console_connection")(sample)
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "0"}, clear=False),
            redirect_stderr(stderr),
        ):
            result = await wrapped()

        self.assertEqual(result, {"status": "complete"})
        self.assertEqual(stderr.getvalue(), "")

    async def test_event_sink_drops_complex_values_instead_of_stringifying_payloads(self) -> None:
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            emit_event(
                "tool_call_completed",
                tool="check_page_performance",
                raw_payload={"token": "secret"},
                raw_rows=[{"query": "private"}],
            )

        event = json.loads(stderr.getvalue())
        self.assertEqual(event["tool"], "check_page_performance")
        self.assertNotIn("raw_payload", event)
        self.assertNotIn("raw_rows", event)
        self.assertNotIn("secret", stderr.getvalue())
        self.assertNotIn("private", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
