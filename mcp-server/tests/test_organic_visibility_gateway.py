from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_seo_mcp.adapters.organic_visibility import OrganicVisibilityProviderDescriptor
from codex_seo_mcp.adapters.organic_visibility_gateway import OrganicVisibilityGateway
from codex_seo_mcp.adapters.organic_visibility_snapshotting import SnapshottingOrganicVisibility
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
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


class FakeProvider:
    capability = "OrganicVisibility"

    def __init__(
        self,
        provider: str,
        *,
        error: SeoDataError | None = None,
        supported: frozenset[tuple[str, str]] | None = None,
        overview_total: int | None = None,
    ) -> None:
        self.provider = provider
        self.error = error
        self.overview_total = overview_total
        self.calls = 0
        self._descriptor = OrganicVisibilityProviderDescriptor(
            provider=provider,
            supported_view_scopes=supported
            or frozenset({("keywords", "domain")}),
        )

    @property
    def descriptor(self) -> OrganicVisibilityProviderDescriptor:
        return self._descriptor

    async def inspect(self, target: str, **_kwargs) -> CapabilityResult[OrganicVisibility]:
        self.calls += 1
        if self.error:
            raise self.error
        return CapabilityResult.complete(
            capability=self.capability,
            provider=self.provider,
            source_kind="third_party",
            data=OrganicVisibility(
                target=target,
                target_scope="domain",
                market=OrganicVisibilityMarket(country="US", language="en"),
                search_engine="google",
                observation=OrganicVisibilityObservation(),
                overview=(
                    OrganicVisibilityOverview(
                        total_keywords=self.overview_total,
                        top3_keywords=3,
                        top10_keywords=10,
                        top100_keywords=self.overview_total,
                        estimated_traffic=88.0,
                    )
                    if self.overview_total is not None
                    else None
                ),
            ),
        )


class OrganicVisibilityGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_and_returns_local_weekly_snapshots_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OrganicVisibilitySnapshotStore(
                OrganicVisibilitySnapshotConfig(root=Path(temp_dir), retention_weeks=8)
            )
            gateway = SnapshottingOrganicVisibility(
                OrganicVisibilityGateway([FakeProvider("dataforseo", overview_total=120)]),
                snapshot_store=store,
            )

            result = await gateway.inspect(
                "example.com",
                country="US",
                language="en-US",
                search_engine="google",
                include_snapshots=True,
                snapshot_weeks=8,
            )

            self.assertEqual(len(result.data.snapshots), 1)
            self.assertEqual(result.data.snapshots[0].total_keywords, 120)
            self.assertTrue(any("实际观测点" in warning for warning in result.warnings))

    async def test_snapshot_failure_does_not_hide_successful_provider_result(self) -> None:
        class FailingSnapshotStore:
            def record(self, _result) -> None:  # noqa: ANN001
                raise OSError("disk unavailable")

        adapter = SnapshottingOrganicVisibility(
            OrganicVisibilityGateway([FakeProvider("dataforseo", overview_total=120)]),
            snapshot_store=FailingSnapshotStore(),  # type: ignore[arg-type]
        )

        result = await adapter.inspect(
            "example.com",
            country="US",
            language="en-US",
            search_engine="google",
        )

        self.assertEqual(result.provider, "dataforseo")
        self.assertTrue(any("本地周趋势暂时无法保存" in warning for warning in result.warnings))

    async def test_single_provider_preserves_not_configured_error(self) -> None:
        gateway = OrganicVisibilityGateway(
            [FakeProvider("dataforseo", error=SeoDataError(SeoDataErrorCode.NOT_CONFIGURED, "missing"))]
        )

        with self.assertRaises(SeoDataError) as caught:
            await gateway.inspect("example.com", country="US", language="en-US", search_engine="google")

        self.assertEqual(caught.exception.code, "not_configured")

    async def test_falls_back_in_order_without_fanning_out(self) -> None:
        first = FakeProvider(
            "dataforseo",
            error=SeoDataError(SeoDataErrorCode.NOT_CONFIGURED, "missing credential"),
        )
        second = FakeProvider("ahrefs")
        third = FakeProvider("semrush")
        gateway = OrganicVisibilityGateway([first, second, third])

        result = await gateway.inspect(
            "example.com",
            country="US",
            language="en-US",
            search_engine="google",
            view="keywords",
            target_scope="domain",
        )

        self.assertEqual(result.provider, "ahrefs")
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 1)
        self.assertEqual(third.calls, 0)
        self.assertTrue(any("fallback" in warning for warning in result.warnings))

    async def test_invalid_request_does_not_fallback(self) -> None:
        first = FakeProvider(
            "dataforseo",
            error=SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "bad market"),
        )
        second = FakeProvider("ahrefs")
        gateway = OrganicVisibilityGateway([first, second])

        with self.assertRaises(SeoDataError) as caught:
            await gateway.inspect("example.com", country="US", language="en-US", search_engine="google")

        self.assertEqual(caught.exception.code, "invalid_request")
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 0)

    async def test_skips_provider_that_does_not_support_view_scope(self) -> None:
        first = FakeProvider(
            "dataforseo",
            supported=frozenset({("keywords", "domain")}),
        )
        second = FakeProvider(
            "ahrefs",
            supported=frozenset({("pages", "exact")}),
        )
        gateway = OrganicVisibilityGateway([first, second])

        result = await gateway.inspect(
            "https://example.com/a",
            country="US",
            language="en-US",
            search_engine="google",
            view="pages",
            target_scope="exact",
        )

        self.assertEqual(result.provider, "ahrefs")
        self.assertEqual(first.calls, 0)
        self.assertEqual(second.calls, 1)


if __name__ == "__main__":
    unittest.main()
