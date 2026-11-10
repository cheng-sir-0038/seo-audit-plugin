from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from codex_seo_mcp.clients.dataforseo import DataForSEOClient, DataForSEOConfig
from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


def _success(result: list[dict[str, object]] | None = None, *, task_code: int = 20000) -> dict[str, object]:
    return {
        "status_code": 20000,
        "status_message": "Ok.",
        "tasks": [
            {
                "status_code": task_code,
                "status_message": "Ok." if task_code == 20000 else "No Search Results.",
                "cost": 0.01,
                "result": result or [],
            }
        ],
    }


class DataForSEOClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_locations_and_languages_reuses_cached_get_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = DataForSEOClient(
                DataForSEOConfig(
                    api_base_url="https://api.example",
                    sandbox_base_url="https://sandbox.example",
                    login="u",
                    password="p",
                    cache_ttl_seconds=86400,
                ),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )
            calls = 0

            def fake_request(_request):  # noqa: ANN001
                nonlocal calls
                calls += 1
                return _success([{"location_code": 2840, "location_name": "United States"}])

            client._request_json = fake_request  # type: ignore[method-assign]

            first = await client.locations_and_languages()
            second = await client.locations_and_languages()

        self.assertEqual(first, second)
        self.assertEqual(calls, 1)

    async def test_emits_actual_provider_cost_and_cache_hit_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = DataForSEOClient(
                DataForSEOConfig(
                    api_base_url="https://api.example",
                    sandbox_base_url="https://sandbox.example",
                    login="u",
                    password="p",
                    cache_ttl_seconds=86400,
                ),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )
            client._request_json = lambda _request: _success([{"target": "example.com"}])  # type: ignore[method-assign]
            stderr = io.StringIO()

            with (
                patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
                redirect_stderr(stderr),
            ):
                await client.ranked_keywords({"target": "example.com"})
                await client.ranked_keywords({"target": "example.com"})

            events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
            self.assertEqual(events[0]["event"], "provider_request_completed")
            self.assertEqual(events[0]["operation"], "ranked_keywords")
            self.assertEqual(events[0]["cost_usd"], 0.01)
            self.assertEqual(events[1]["event"], "provider_request_cache_hit")
            self.assertEqual(events[1]["operation"], "ranked_keywords")
            self.assertNotIn("cost_usd", events[1])

    async def test_reuses_cached_identical_paid_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = DataForSEOClient(
                DataForSEOConfig(
                    api_base_url="https://api.example",
                    sandbox_base_url="https://sandbox.example",
                    login="u",
                    password="p",
                    cache_ttl_seconds=86400,
                ),
                cache=ProviderCache(
                    ProviderCacheConfig(root=Path(temp_dir))
                ),
            )
            calls = 0

            def fake_request(_request):  # noqa: ANN001
                nonlocal calls
                calls += 1
                return _success([{"target": "example.com"}])

            client._request_json = fake_request  # type: ignore[method-assign]

            first = await client.ranked_keywords({"target": "example.com"})
            second = await client.ranked_keywords({"target": "example.com"})
            await client.ranked_keywords({"target": "other.example"})

            self.assertEqual(first.result, second.result)
            self.assertEqual(calls, 2)

    async def test_uses_basic_auth_and_sandbox_base_url(self) -> None:
        client = DataForSEOClient(
            DataForSEOConfig(
                api_base_url="https://api.example",
                sandbox_base_url="https://sandbox.example",
                login="user@example.com",
                password="secret",
                use_sandbox=True,
                cache_ttl_seconds=0,
            )
        )
        captured = {}

        def fake_request(request):  # noqa: ANN001
            captured["url"] = request.full_url
            captured["authorization"] = request.get_header("Authorization")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _success([{"target": "example.com"}])

        client._request_json = fake_request  # type: ignore[method-assign]
        report = await client.ranked_keywords({"target": "example.com"})

        self.assertTrue(client.is_sandbox)
        self.assertEqual(
            captured["url"],
            "https://sandbox.example/v3/dataforseo_labs/google/ranked_keywords/live",
        )
        encoded = captured["authorization"].split(" ", 1)[1]
        self.assertEqual(base64.b64decode(encoded).decode(), "user@example.com:secret")
        self.assertEqual(captured["body"], [{"target": "example.com"}])
        self.assertEqual(report.result[0]["target"], "example.com")

    async def test_no_search_results_is_empty_data_not_provider_failure(self) -> None:
        client = DataForSEOClient(
            DataForSEOConfig(
                api_base_url="https://api.example",
                sandbox_base_url="https://sandbox.example",
                login="u",
                password="p",
                cache_ttl_seconds=0,
            )
        )
        client._request_json = lambda _request: _success(task_code=40102)  # type: ignore[method-assign]

        report = await client.ranked_keywords({"target": "example.com"})

        self.assertEqual(report.result, [])
        self.assertFalse(report.partial)

    async def test_provider_rate_limit_maps_to_stable_error(self) -> None:
        client = DataForSEOClient(
            DataForSEOConfig(
                api_base_url="https://api.example",
                sandbox_base_url="https://sandbox.example",
                login="u",
                password="p",
                cache_ttl_seconds=0,
            )
        )
        client._request_json = lambda _request: {  # type: ignore[method-assign]
            "status_code": 20000,
            "status_message": "Ok.",
            "tasks": [
                {
                    "status_code": 40202,
                    "status_message": "The rate-limit per minute has been exceeded.",
                    "result": [],
                }
            ],
        }

        with self.assertRaises(SeoDataError) as caught:
            await client.ranked_keywords({"target": "example.com"})

        self.assertEqual(caught.exception.code, "rate_limited")

    async def test_missing_credentials_stops_before_network(self) -> None:
        client = DataForSEOClient(
            DataForSEOConfig(
                api_base_url="https://api.example",
                sandbox_base_url="https://sandbox.example",
                login=None,
                password=None,
                cache_ttl_seconds=0,
            )
        )

        with self.assertRaises(SeoDataError) as caught:
            await client.ranked_keywords({"target": "example.com"})

        self.assertEqual(caught.exception.code, "not_configured")


if __name__ == "__main__":
    unittest.main()
