from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_seo_mcp.clients.crux import CruxClient, CruxConfig, CruxResponse
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class StubCruxClient(CruxClient):
    def __init__(self, *, response: CruxResponse | None, cache: ProviderCache) -> None:
        super().__init__(
            CruxConfig(api_key="test-key", cache_ttl_seconds=86400),
            cache=cache,
        )
        self.response = response
        self.remote_calls = 0

    def _query_sync(self, key: str, body: dict[str, object]) -> CruxResponse | None:
        self.remote_calls += 1
        return self.response


class CruxClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_cached_success_for_same_url_form_factor_and_metrics(self) -> None:
        payload = {"record": {"key": {"url": "https://example.com/page", "formFactor": "PHONE"}}}
        with tempfile.TemporaryDirectory() as temp_dir:
            client = StubCruxClient(
                response=CruxResponse(payload),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )
            first = await client.query_url(
                "https://example.com/page",
                form_factor="PHONE",
                metrics=("largest_contentful_paint",),
            )
            second = await client.query_url(
                "https://example.com/page",
                form_factor="PHONE",
                metrics=("largest_contentful_paint",),
            )
            await client.query_url(
                "https://example.com/page",
                form_factor="DESKTOP",
                metrics=("largest_contentful_paint",),
            )

        self.assertEqual(client.remote_calls, 2)
        self.assertIsNotNone(first)
        self.assertEqual(first.payload, second.payload)

    async def test_caches_no_sample_result_to_avoid_repeating_404_equivalent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = StubCruxClient(
                response=None,
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )
            first = await client.query_origin(
                "https://example.com",
                form_factor="DESKTOP",
                metrics=("largest_contentful_paint",),
            )
            second = await client.query_origin(
                "https://example.com",
                form_factor="DESKTOP",
                metrics=("largest_contentful_paint",),
            )

        self.assertEqual(client.remote_calls, 1)
        self.assertIsNone(first)
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
