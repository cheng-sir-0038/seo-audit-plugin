from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_seo_mcp.clients.ga4 import Ga4Client, Ga4ClientConfig, Ga4ReportResponse
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class FakeAuth:
    async def connection_details(self) -> dict[str, str]:
        return {"status": "connected"}

    async def authorize(self) -> dict[str, str]:
        return {"status": "connected"}

    async def credentials(self):
        return object()

    def cache_generation(self) -> str:
        return "auth-a"


class FakeAdminClient:
    def __init__(self) -> None:
        self.stream_property_ids: list[str] = []

    async def list_properties(self) -> list[dict[str, str]]:
        return [{"property_id": "222", "property_name": "example.com"}]

    async def list_data_streams(self, property_id: str) -> list[dict[str, str]]:
        self.stream_property_ids.append(property_id)
        return [{"data_stream_id": "333", "default_uri": "https://example.com"}]


class FakeDataClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def run_report(
        self,
        property_id: str,
        body: dict[str, object],
    ) -> Ga4ReportResponse:
        self.calls.append((property_id, body))
        return Ga4ReportResponse(payload={"rowCount": 0})


class Ga4ClientFacadeTests(unittest.IsolatedAsyncioTestCase):
    async def test_facade_delegates_without_reimplementing_admin_or_data_logic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            admin = FakeAdminClient()
            data = FakeDataClient()
            client = Ga4Client(
                auth=FakeAuth(),
                config=Ga4ClientConfig(cache_ttl_seconds=1800, request_timeout_seconds=5),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
                admin=admin,
                data=data,
            )

            properties = await client.list_properties()
            streams = await client.list_data_streams("properties/222")
            report = await client.run_report("properties/222", {"metrics": []})

        self.assertEqual(properties[0]["property_id"], "222")
        self.assertEqual(streams[0]["data_stream_id"], "333")
        self.assertEqual(report.payload, {"rowCount": 0})
        self.assertEqual(admin.stream_property_ids, ["222"])
        self.assertEqual(data.calls, [("222", {"metrics": []})])

    async def test_facade_keeps_oauth_status_and_authorize_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ProviderCache(ProviderCacheConfig(root=Path(temp_dir)))
            cache.set(
                provider="ga4",
                operation="run-report",
                request_key={"property_id": "222"},
                value={"rowCount": 1},
                ttl_seconds=3600,
            )
            client = Ga4Client(
                auth=FakeAuth(),
                config=Ga4ClientConfig(),
                cache=cache,
                admin=FakeAdminClient(),
                data=FakeDataClient(),
            )

            status = await client.connection_status()
            authorized = await client.authorize()

        self.assertEqual(status, {"status": "connected"})
        self.assertEqual(authorized, {"status": "connected"})
        self.assertIsNone(
            cache.get(
                provider="ga4",
                operation="run-report",
                request_key={"property_id": "222"},
            )
        )


if __name__ == "__main__":
    unittest.main()
