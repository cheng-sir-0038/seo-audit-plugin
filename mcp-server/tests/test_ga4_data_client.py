from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_seo_mcp.clients.ga4_data import Ga4DataClient, Ga4ReportResponse
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class FakeAuth:
    def __init__(self, generation: str = "auth-a") -> None:
        self.calls = 0
        self.generation = generation

    async def credentials(self):
        self.calls += 1
        return object()

    def cache_generation(self) -> str:
        return self.generation


class FakeTransport:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def data_post(
        self,
        credentials,
        path: str,
        *,
        body: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append((path, body))
        return self.payload


class Ga4DataClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_report_reuses_short_lived_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            auth = FakeAuth()
            transport = FakeTransport({"rowCount": 1, "rows": []})
            client = Ga4DataClient(
                auth=auth,
                transport=transport,
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
                cache_ttl_seconds=1800,
            )
            body = {
                "dateRanges": [{"startDate": "2026-08-01", "endDate": "2026-08-31"}],
                "metrics": [{"name": "sessions"}],
            }

            first = await client.run_report("222", body)
            second = await client.run_report("222", body)

        self.assertIsInstance(first, Ga4ReportResponse)
        self.assertEqual(first.payload, second.payload)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(auth.calls, 2)
        self.assertEqual(transport.calls[0][0], "/properties/222:runReport")

    async def test_cache_does_not_cross_authorization_generations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            auth = FakeAuth("auth-a")
            transport = FakeTransport({"rowCount": 1, "rows": []})
            client = Ga4DataClient(
                auth=auth,
                transport=transport,
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
                cache_ttl_seconds=1800,
            )
            body = {"metrics": [{"name": "sessions"}]}

            await client.run_report("222", body)
            auth.generation = "auth-b"
            await client.run_report("222", body)

        self.assertEqual(len(transport.calls), 2)


if __name__ == "__main__":
    unittest.main()
