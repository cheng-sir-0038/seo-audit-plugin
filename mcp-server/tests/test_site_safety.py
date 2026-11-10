from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_seo_mcp.adapters.site_safety import SiteSafetyAdapter
from codex_seo_mcp.clients.safe_browsing import (
    SafeBrowsingClient,
    SafeBrowsingConfig,
    SafeBrowsingResponse,
)
from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.models.site_safety import SiteSafetyStatus
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class StubSafeBrowsingClient(SafeBrowsingClient):
    def __init__(self, *, payload: dict[str, object], cache: ProviderCache) -> None:
        super().__init__(
            config=SafeBrowsingConfig(
                api_url="https://safebrowsing.test/v4/threatMatches:find",
                api_key="test-key",
                timeout_seconds=5,
                cache_max_ttl_seconds=86400,
            ),
            cache=cache,
        )
        self.payload = payload
        self.calls = 0
        self.targets: list[str] = []

    def _request_sync(self, target: str) -> SafeBrowsingResponse:
        self.calls += 1
        self.targets.append(target)
        return SafeBrowsingResponse(payload=self.payload)


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.raw


class SiteSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_matches_mean_no_known_threats_not_absolute_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = StubSafeBrowsingClient(
                payload={},
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )
            result = await SiteSafetyAdapter(client=client).check(
                "https://example.com/path"
            )

        self.assertEqual(result.capability, "SiteSafety")
        self.assertEqual(result.provider, "google-safe-browsing-v4")
        self.assertEqual(result.data.url, "https://example.com/path")
        self.assertEqual(result.data.status, SiteSafetyStatus.NO_KNOWN_THREATS)
        self.assertEqual(result.data.threats, [])
        self.assertTrue(any("不代表绝对安全" in warning for warning in result.warnings))

    async def test_known_threats_are_grouped_by_url_without_overstating_certainty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = StubSafeBrowsingClient(
                payload={
                    "matches": [
                        {
                            "threatType": "SOCIAL_ENGINEERING",
                            "platformType": "ANY_PLATFORM",
                            "threatEntryType": "URL",
                            "threat": {"url": "https://example.com/phish"},
                            "cacheDuration": "300s",
                        },
                        {
                            "threatType": "MALWARE",
                            "platformType": "ANY_PLATFORM",
                            "threatEntryType": "URL",
                            "threat": {"url": "https://example.com/phish"},
                            "cacheDuration": "600s",
                        },
                    ]
                },
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )
            result = await SiteSafetyAdapter(client=client).check(
                "https://example.com/phish"
            )

        self.assertEqual(result.data.status, SiteSafetyStatus.POTENTIAL_RISK)
        self.assertEqual(result.data.threats[0].matched_url, "https://example.com/phish")
        self.assertEqual(
            result.data.threats[0].threat_types,
            ["SOCIAL_ENGINEERING", "MALWARE"],
        )
        self.assertTrue(any("潜在" in warning for warning in result.warnings))

    async def test_no_match_response_uses_short_cache_to_prevent_duplicate_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = StubSafeBrowsingClient(
                payload={},
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )

            first = await client.search_url("https://example.com/")
            second = await client.search_url("https://example.com/")

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.payload, {"threats": []})
        self.assertEqual(client.calls, 1)

    async def test_zero_cache_ttl_bypasses_existing_results_without_writing_new_ones(self) -> None:
        url = "https://example.com/"
        risk_response = {
            "matches": [{
                "threatType": "MALWARE",
                "threatEntryType": "URL",
                "threat": {"url": url},
                "cacheDuration": "300s",
            }],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ProviderCache(ProviderCacheConfig(root=Path(temp_dir)))
            cached_adapter = SiteSafetyAdapter(client=SafeBrowsingClient(
                config=SafeBrowsingConfig(api_key="test-key", cache_max_ttl_seconds=300),
                cache=cache,
            ))
            with patch(
                "codex_seo_mcp.clients.safe_browsing.urlopen",
                return_value=FakeHttpResponse({}),
            ) as provider:
                initial = await cached_adapter.check(url)
                await cached_adapter.check(url)
            self.assertEqual(initial.data.status, SiteSafetyStatus.NO_KNOWN_THREATS)
            self.assertEqual(provider.call_count, 1)

            # 使用真实配置入口、缓存文件和适配器，只替换第三方 HTTP 响应。
            with patch.dict(os.environ, {
                "SAFE_BROWSING_API_KEY": "test-key",
                "SAFE_BROWSING_CACHE_MAX_TTL_SECONDS": "0",
            }, clear=False):
                uncached_adapter = SiteSafetyAdapter(client=SafeBrowsingClient(cache=cache))
            with patch(
                "codex_seo_mcp.clients.safe_browsing.urlopen",
                return_value=FakeHttpResponse(risk_response),
            ) as provider:
                first = await uncached_adapter.check(url)
                second = await uncached_adapter.check(url)

                self.assertEqual(first.data.status, SiteSafetyStatus.POTENTIAL_RISK)
                self.assertEqual(second.data.status, SiteSafetyStatus.POTENTIAL_RISK)
                self.assertEqual(provider.call_count, 2)

                # 关闭缓存只绕过读写，不删除或覆盖共享缓存里的已有结果。
                original = await cached_adapter.check(url)
                self.assertEqual(original.data.status, SiteSafetyStatus.NO_KNOWN_THREATS)
                self.assertEqual(provider.call_count, 2)

    async def test_http_request_uses_json_post_and_keeps_api_key_out_of_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = SafeBrowsingClient(
                config=SafeBrowsingConfig(
                    api_url="https://safebrowsing.test/v4/threatMatches:find",
                    api_key="test-key",
                    timeout_seconds=5,
                ),
                cache=ProviderCache(
                    ProviderCacheConfig(root=Path(temp_dir), enabled=False)
                ),
            )

            with patch(
                "codex_seo_mcp.clients.safe_browsing.urlopen",
                return_value=FakeHttpResponse({}),
            ) as mocked:
                response = await client.search_url("https://example.com/")

        request = mocked.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://safebrowsing.test/v4/threatMatches:find",
        )
        self.assertNotIn("test-key", request.full_url)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            payload["threatInfo"]["threatEntries"],
            [{"url": "https://example.com/"}],
        )
        self.assertIn("MALWARE", payload["threatInfo"]["threatTypes"])
        self.assertEqual(response.payload, {"threats": []})

    async def test_malformed_matches_are_invalid_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = StubSafeBrowsingClient(
                payload={"matches": "broken"},
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )

            with self.assertRaises(SeoDataError) as caught:
                await client.search_url("https://example.com/")

        self.assertEqual(caught.exception.code, "invalid_response")

    async def test_unexpected_provider_payload_never_becomes_a_cached_clean_result(self) -> None:
        payloads = [
            {"error": {"code": 503, "message": "provider unavailable"}},
            {"threats": [{"url": "https://example.com/", "threatTypes": ["MALWARE"]}]},
            {"matches": None},
            {"error": {"code": 503}, "matches": []},
        ]
        for payload in payloads:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp_dir:
                client = SafeBrowsingClient(
                    config=SafeBrowsingConfig(api_key="test-key"),
                    cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
                )
                adapter = SiteSafetyAdapter(client=client)
                with patch(
                    "codex_seo_mcp.clients.safe_browsing.urlopen",
                    return_value=FakeHttpResponse(payload),
                ) as provider:
                    for _ in range(2):
                        with self.assertRaises(SeoDataError) as caught:
                            await adapter.check("https://example.com/")
                        self.assertEqual(caught.exception.code, "invalid_response")

                # An invalid response must not be retained as a successful safety check.
                self.assertEqual(provider.call_count, 2)
                self.assertEqual(list(Path(temp_dir).rglob("*.json")), [])

    async def test_missing_api_key_is_not_configured(self) -> None:
        client = SafeBrowsingClient(
            config=SafeBrowsingConfig(api_key=None),
            cache=ProviderCache(
                ProviderCacheConfig(
                    root=Path("/tmp/codex-seo-safety-test"),
                    enabled=False,
                )
            ),
        )

        with self.assertRaises(SeoDataError) as caught:
            await client.search_url("https://example.com/")

        self.assertEqual(caught.exception.code, "not_configured")

    async def test_private_or_credential_url_is_rejected_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = StubSafeBrowsingClient(
                payload={},
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )

            with self.assertRaises(SeoDataError):
                await client.search_url("http://127.0.0.1/admin")
            with self.assertRaises(SeoDataError):
                await client.search_url("https://user:pass@example.com/")

        self.assertEqual(client.calls, 0)


if __name__ == "__main__":
    unittest.main()
