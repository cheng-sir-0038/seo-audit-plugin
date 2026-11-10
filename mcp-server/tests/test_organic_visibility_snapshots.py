from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from codex_seo_mcp.models.common import CapabilityResult
from codex_seo_mcp.models.organic_visibility import (
    OrganicVisibility,
    OrganicVisibilityMarket,
    OrganicVisibilityObservation,
    OrganicVisibilityOverview,
)
from codex_seo_mcp.snapshots import (
    OrganicVisibilitySnapshotConfig,
    OrganicVisibilitySnapshotStore,
)


def _result(
    *,
    target: str = "example.com",
    provider: str = "dataforseo",
    country: str = "US",
    total: int = 100,
    top10: int = 20,
    traffic: float = 55.5,
) -> CapabilityResult[OrganicVisibility]:
    return CapabilityResult.complete(
        capability="OrganicVisibility",
        provider=provider,
        source_kind="third_party",
        data=OrganicVisibility(
            target=target,
            target_scope="domain",
            market=OrganicVisibilityMarket(country=country, language="en"),
            search_engine="google",
            observation=OrganicVisibilityObservation(data_updated_at="2026-09-01T00:00:00Z"),
            overview=OrganicVisibilityOverview(
                total_keywords=total,
                top3_keywords=5,
                top10_keywords=top10,
                top100_keywords=total,
                estimated_traffic=traffic,
                new_keywords=4,
                up_keywords=10,
                down_keywords=3,
                lost_keywords=1,
            ),
        ),
    )


class OrganicVisibilitySnapshotStoreTests(unittest.TestCase):
    def test_same_iso_week_overwrites_with_latest_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OrganicVisibilitySnapshotStore(
                OrganicVisibilitySnapshotConfig(root=Path(temp_dir), retention_weeks=8)
            )
            store.record(
                _result(total=100),
                observed_at=datetime(2026, 9, 1, 8, tzinfo=UTC),
            )
            store.record(
                _result(total=120),
                observed_at=datetime(2026, 9, 4, 8, tzinfo=UTC),
            )

            snapshots = store.recent(
                target="example.com",
                target_scope="domain",
                country="US",
                language="en",
                provider="dataforseo",
                weeks=8,
            )

            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0].week, "2026-W36")
            self.assertEqual(snapshots[0].total_keywords, 120)
            self.assertEqual(snapshots[0].provider_data_updated_at, "2026-09-01T00:00:00Z")

    def test_recent_returns_only_observed_weeks_without_filling_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OrganicVisibilitySnapshotStore(
                OrganicVisibilitySnapshotConfig(root=Path(temp_dir), retention_weeks=8)
            )
            store.record(
                _result(total=80),
                observed_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
            )
            store.record(
                _result(total=100),
                observed_at=datetime(2026, 8, 24, 8, tzinfo=UTC),
            )

            snapshots = store.recent(
                target="example.com",
                target_scope="domain",
                country="US",
                language="en",
                provider="dataforseo",
                weeks=8,
            )

            self.assertEqual([item.week for item in snapshots], ["2026-W33", "2026-W35"])
            self.assertEqual([item.total_keywords for item in snapshots], [80, 100])

    def test_provider_and_market_are_separate_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OrganicVisibilitySnapshotStore(
                OrganicVisibilitySnapshotConfig(root=Path(temp_dir), retention_weeks=8)
            )
            observed = datetime(2026, 9, 4, 8, tzinfo=UTC)
            store.record(_result(provider="dataforseo", country="US", total=100), observed_at=observed)
            store.record(_result(provider="ahrefs", country="US", total=200), observed_at=observed)
            store.record(_result(provider="dataforseo", country="GB", total=300), observed_at=observed)

            us_dataforseo = store.recent(
                target="example.com",
                target_scope="domain",
                country="US",
                language="en",
                provider="dataforseo",
            )
            us_ahrefs = store.recent(
                target="example.com",
                target_scope="domain",
                country="US",
                language="en",
                provider="ahrefs",
            )
            gb_dataforseo = store.recent(
                target="example.com",
                target_scope="domain",
                country="GB",
                language="en",
                provider="dataforseo",
            )

            self.assertEqual(us_dataforseo[0].total_keywords, 100)
            self.assertEqual(us_ahrefs[0].total_keywords, 200)
            self.assertEqual(gb_dataforseo[0].total_keywords, 300)

    def test_disabled_store_does_not_persist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = OrganicVisibilitySnapshotStore(
                OrganicVisibilitySnapshotConfig(root=root, enabled=False)
            )

            self.assertIsNone(store.record(_result()))
            self.assertEqual(list(root.rglob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
