from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_seo_mcp.clients.ga4_admin import Ga4AdminClient
from codex_seo_mcp.clients.ga4_mapper import Ga4AdminMapper
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
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
    def __init__(self, pages: dict[tuple[str, str | None], dict[str, object]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, object]]] = []

    def admin_get(
        self,
        credentials,
        path: str,
        *,
        params: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append((path, dict(params)))
        token = str(params.get("pageToken") or "").strip() or None
        return self.pages[(path, token)]


class Ga4AdminClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_properties_across_account_summary_pages(self) -> None:
        pages = {
            ("/accountSummaries", None): {
                "accountSummaries": [
                    {
                        "account": "accounts/111",
                        "displayName": "Main Account",
                        "propertySummaries": [
                            {"property": "properties/222", "displayName": "example.com"}
                        ],
                    }
                ],
                "nextPageToken": "page-2",
            },
            ("/accountSummaries", "page-2"): {
                "accountSummaries": [
                    {
                        "account": "accounts/333",
                        "displayName": "Second Account",
                        "propertySummaries": [
                            {"property": "properties/444", "displayName": "shop.example.com"}
                        ],
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            transport = FakeTransport(pages)
            client = Ga4AdminClient(
                auth=FakeAuth(),
                transport=transport,
                mapper=Ga4AdminMapper(),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
                cache_ttl_seconds=1800,
            )

            properties = await client.list_properties()

        self.assertEqual([item["property_id"] for item in properties], ["222", "444"])
        self.assertEqual(
            [call[1].get("pageToken") for call in transport.calls],
            [None, "page-2"],
        )
        self.assertTrue(all(call[1]["pageSize"] == 200 for call in transport.calls))


    async def test_property_cache_still_checks_current_credentials(self) -> None:
        pages = {
            ("/accountSummaries", None): {
                "accountSummaries": [
                    {
                        "account": "accounts/111",
                        "displayName": "Main",
                        "propertySummaries": [
                            {"property": "properties/222", "displayName": "example.com"}
                        ],
                    }
                ]
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            auth = FakeAuth()
            transport = FakeTransport(pages)
            client = Ga4AdminClient(
                auth=auth,
                transport=transport,
                mapper=Ga4AdminMapper(),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
                cache_ttl_seconds=1800,
            )

            first = await client.list_properties()
            second = await client.list_properties()

        self.assertEqual(first, second)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(auth.calls, 2)

    async def test_duplicate_next_page_token_fails_instead_of_looping(self) -> None:
        pages = {
            ("/accountSummaries", None): {
                "accountSummaries": [],
                "nextPageToken": "same-token",
            },
            ("/accountSummaries", "same-token"): {
                "accountSummaries": [],
                "nextPageToken": "same-token",
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            client = Ga4AdminClient(
                auth=FakeAuth(),
                transport=FakeTransport(pages),
                mapper=Ga4AdminMapper(),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
                cache_ttl_seconds=1800,
            )

            with self.assertRaises(SeoDataError) as caught:
                await client.list_properties()

        self.assertEqual(caught.exception.code, SeoDataErrorCode.INVALID_RESPONSE)

    async def test_lists_web_data_streams(self) -> None:
        pages = {
            ("/properties/333/dataStreams", None): {
                "dataStreams": [
                    {
                        "name": "properties/333/dataStreams/999",
                        "displayName": "Web",
                        "type": "WEB_DATA_STREAM",
                        "webStreamData": {
                            "measurementId": "G-TEST",
                            "defaultUri": "https://www.site.example",
                        },
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            client = Ga4AdminClient(
                auth=FakeAuth(),
                transport=FakeTransport(pages),
                mapper=Ga4AdminMapper(),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
                cache_ttl_seconds=1800,
            )

            streams = await client.list_data_streams("333")

        self.assertEqual(streams[0]["data_stream_id"], "999")
        self.assertEqual(streams[0]["default_uri"], "https://www.site.example")


if __name__ == "__main__":
    unittest.main()
