from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class ProviderCacheTests(unittest.TestCase):
    def test_expiry_timezone_overflow_is_a_cache_miss(self) -> None:
        for expiry in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            with self.subTest(expiry=expiry), tempfile.TemporaryDirectory() as directory:
                cache = ProviderCache(ProviderCacheConfig(root=Path(directory)))
                arguments = {"provider": "ga4", "operation": "run-report", "request_key": {"property_id": "222"}}
                cache.set(**arguments, value={"rowCount": 1}, ttl_seconds=60)
                path = next(Path(directory).rglob("*.json"))
                saved = json.loads(path.read_text())
                saved["expires_at"] = expiry
                path.write_text(json.dumps(saved))
                self.assertIsNone(cache.get(**arguments))
                cache.set(**arguments, value={"rowCount": 2}, ttl_seconds=60)
                self.assertEqual(cache.get(**arguments), {"rowCount": 2})

    def test_round_trip_and_ttl_expiration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ProviderCache(ProviderCacheConfig(root=Path(temp_dir)))
            start = datetime(2026, 9, 4, 4, tzinfo=UTC)
            request = {"domain": "example.com", "market": "US"}
            cache.set(
                provider="dataforseo",
                operation="ranked-keywords",
                request_key=request,
                value={"rows": [1, 2, 3]},
                ttl_seconds=3600,
                now=start,
            )

            self.assertEqual(
                cache.get(
                    provider="dataforseo",
                    operation="ranked-keywords",
                    request_key=request,
                    now=start + timedelta(minutes=30),
                ),
                {"rows": [1, 2, 3]},
            )
            self.assertIsNone(
                cache.get(
                    provider="dataforseo",
                    operation="ranked-keywords",
                    request_key=request,
                    now=start + timedelta(hours=2),
                )
            )

    def test_provider_operation_and_request_are_separate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ProviderCache(ProviderCacheConfig(root=Path(temp_dir)))
            cache.set(
                provider="semrush",
                operation="domain-rank",
                request_key={"domain": "a.example"},
                value={"value": 1},
                ttl_seconds=3600,
            )

            self.assertIsNone(
                cache.get(
                    provider="semrush",
                    operation="domain-rank",
                    request_key={"domain": "b.example"},
                )
            )
            self.assertIsNone(
                cache.get(
                    provider="dataforseo",
                    operation="domain-rank",
                    request_key={"domain": "a.example"},
                )
            )

    def test_disabled_cache_never_reads_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache = ProviderCache(ProviderCacheConfig(root=root, enabled=False))
            cache.set(
                provider="semrush",
                operation="keyword",
                request_key={"keyword": "seo"},
                value={"value": 1},
                ttl_seconds=3600,
            )
            self.assertIsNone(
                cache.get(
                    provider="semrush",
                    operation="keyword",
                    request_key={"keyword": "seo"},
                )
            )
            self.assertEqual(list(root.rglob("*.json")), [])

    def test_clear_can_invalidate_one_provider_without_touching_others(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ProviderCache(ProviderCacheConfig(root=Path(temp_dir)))
            cache.set(
                provider="ga4",
                operation="run-report",
                request_key={"property_id": "123"},
                value={"rowCount": 1},
                ttl_seconds=3600,
            )
            cache.set(
                provider="semrush",
                operation="keyword",
                request_key={"keyword": "seo"},
                value={"volume": 10},
                ttl_seconds=3600,
            )

            cache.clear(provider="ga4")

            self.assertIsNone(
                cache.get(
                    provider="ga4",
                    operation="run-report",
                    request_key={"property_id": "123"},
                )
            )
            self.assertEqual(
                cache.get(
                    provider="semrush",
                    operation="keyword",
                    request_key={"keyword": "seo"},
                ),
                {"volume": 10},
            )


if __name__ == "__main__":
    unittest.main()
