from __future__ import annotations

import unittest

from codex_seo_mcp.runtime import build_runtime


class RuntimeCompositionTests(unittest.TestCase):
    def test_runtime_is_the_single_composition_root_for_shared_provider_clients(self) -> None:
        runtime = build_runtime()

        self.assertIs(runtime.index_inspection.client, runtime.gsc)
        self.assertIs(runtime.search_performance.client, runtime.gsc)
        self.assertIs(runtime.web_analytics.client, runtime.ga4)

    def test_runtime_registry_binds_the_same_adapter_instances(self) -> None:
        runtime = build_runtime()

        self.assertIs(runtime.registry.get("PageInspection"), runtime.page_inspection)
        self.assertIs(runtime.registry.get("SearchPerformance"), runtime.search_performance)
        self.assertIs(runtime.registry.get("OrganicVisibility"), runtime.organic_visibility)
        self.assertEqual(
            runtime.registry.capabilities(),
            [
                "CompetitorResearch",
                "IndexInspection",
                "KeywordResearch",
                "OrganicVisibility",
                "PageInspection",
                "PageQuality",
                "ResourceInspection",
                "SearchPerformance",
                "SerpResearch",
                "SiteSafety",
                "WebAnalytics",
            ],
        )


if __name__ == "__main__":
    unittest.main()
