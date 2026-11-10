from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from requests import Response

from codex_seo_mcp.auth.ga4_oauth import Ga4AuthManager, Ga4OAuthConfig
from codex_seo_mcp.clients.ga4 import Ga4Client
from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class Ga4CacheControlsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.token_path = root / "synthetic-token.json"
        self.token_path.write_text(json.dumps({
            "token": "synthetic-access-token",
            "refresh_token": "synthetic-refresh-token",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-client-secret",
            "expiry": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }), encoding="utf-8")
        self.auth = Ga4AuthManager(Ga4OAuthConfig(
            client_id="synthetic-client",
            client_secret="synthetic-client-secret",
            token_path=self.token_path,
        ))
        self.cache = ProviderCache(ProviderCacheConfig(root=root / "cache"))

    def configured_client(self, ttl_seconds: int) -> Ga4Client:
        with patch.dict(os.environ, {"GA4_CACHE_TTL_SECONDS": str(ttl_seconds)}, clear=False):
            return Ga4Client(auth=self.auth, cache=self.cache)

    @staticmethod
    def response(payload: dict[str, object]) -> Response:
        response = Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode("utf-8")
        response.encoding = "utf-8"
        return response

    @staticmethod
    async def read_value(client: Ga4Client, operation: str) -> str:
        if operation == "report":
            report = await client.run_report("222", {
                "dateRanges": [{"startDate": "2026-08-01", "endDate": "2026-08-28"}],
                "metrics": [{"name": "sessions"}],
            })
            return report.payload["rows"][0]["metricValues"][0]["value"]
        if operation == "properties":
            return (await client.list_properties())[0]["property_name"]
        return (await client.list_data_streams("222"))[0]["default_uri"]

    async def test_zero_ttl_bypasses_existing_report_and_admin_caches(self) -> None:
        cases = [
            (
                "report",
                {"rows": [{"metricValues": [{"value": "10"}]}], "rowCount": 1},
                {"rows": [{"metricValues": [{"value": "20"}]}], "rowCount": 1},
                "10", "20",
            ),
            (
                "properties",
                {"accountSummaries": [{
                    "account": "accounts/111",
                    "propertySummaries": [{"property": "properties/222", "displayName": "Old site"}],
                }]},
                {"accountSummaries": [{
                    "account": "accounts/111",
                    "propertySummaries": [{"property": "properties/222", "displayName": "Current site"}],
                }]},
                "Old site", "Current site",
            ),
            (
                "streams",
                {"dataStreams": [{
                    "name": "properties/222/dataStreams/333", "type": "WEB_DATA_STREAM",
                    "webStreamData": {"defaultUri": "https://old.example.com"},
                }]},
                {"dataStreams": [{
                    "name": "properties/222/dataStreams/333", "type": "WEB_DATA_STREAM",
                    "webStreamData": {"defaultUri": "https://example.com"},
                }]},
                "https://old.example.com", "https://example.com",
            ),
        ]
        for operation, old_payload, fresh_payload, old_value, fresh_value in cases:
            with self.subTest(operation=operation):
                cached_client = self.configured_client(1800)
                # 只替换 Google 授权 HTTP 会话；真实凭据加载、配置、客户端和磁盘缓存参与测试。
                with patch(
                    "google.auth.transport.requests.AuthorizedSession.request",
                    return_value=self.response(old_payload),
                ) as provider:
                    self.assertEqual(await self.read_value(cached_client, operation), old_value)
                    self.assertEqual(await self.read_value(cached_client, operation), old_value)
                    self.assertEqual(provider.call_count, 1)

                uncached_client = self.configured_client(0)
                with patch(
                    "google.auth.transport.requests.AuthorizedSession.request",
                    return_value=self.response(fresh_payload),
                ) as provider:
                    self.assertEqual(await self.read_value(uncached_client, operation), fresh_value)
                    self.assertEqual(await self.read_value(uncached_client, operation), fresh_value)
                    self.assertEqual(provider.call_count, 2)
                    # 关闭缓存不改变共享缓存对象，也不删除或覆盖已有条目。
                    self.assertEqual(await self.read_value(cached_client, operation), old_value)
                    self.assertEqual(provider.call_count, 2)

    async def test_disabled_cache_still_requires_current_authorization(self) -> None:
        client = self.configured_client(0)
        self.token_path.unlink()
        with patch("google.auth.transport.requests.AuthorizedSession.request") as provider:
            for operation in ("report", "properties", "streams"):
                with self.subTest(operation=operation):
                    with self.assertRaises(SeoDataError) as caught:
                        await self.read_value(client, operation)
                    self.assertEqual(caught.exception.code, "authorization_required")
            provider.assert_not_called()
