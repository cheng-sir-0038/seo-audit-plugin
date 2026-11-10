from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_seo_mcp.diagnosis.search_appearance import (
    SEARCH_APPEARANCE_SCHEMA_ID,
    assess_search_appearance,
)
from codex_seo_mcp.models.page_ownership import TargetPageOwnershipState
from codex_seo_mcp.models.search_appearance import (
    MetricTrend,
    PresentationState,
    SearchAppearanceAction,
    SearchAppearanceSignals,
    SearchAppearanceState,
)

ROOT = Path(__file__).resolve().parents[2]


class SearchAppearanceTests(unittest.TestCase):
    def test_missing_source_title_is_source_metadata_issue(self) -> None:
        result = assess_search_appearance(
            query="seo audit",
            market="US",
            signals=SearchAppearanceSignals(
                source_title=None,
                source_title_count=0,
                serp_title="SEO Audit Tool",
                serp_snippet="Snippet",
            ),
        )
        self.assertEqual(result.state, SearchAppearanceState.SOURCE_METADATA_ISSUE)
        self.assertEqual(result.recommended_action, SearchAppearanceAction.FIX_SOURCE_METADATA)

    def test_serp_rewrite_alone_is_not_an_error(self) -> None:
        result = assess_search_appearance(
            query="seo audit",
            market="US",
            signals=SearchAppearanceSignals(
                source_title="SEO Audit",
                source_title_count=1,
                source_description="Run an SEO audit",
                source_description_count=1,
                serp_title="SEO Audit Tool - Example",
                serp_snippet="Run a technical SEO audit",
                previous_position=4,
                current_position=4.1,
                previous_ctr=0.10,
                current_ctr=0.099,
            ),
        )
        self.assertEqual(result.state, SearchAppearanceState.REWRITE_OBSERVED)
        self.assertEqual(result.title_state, PresentationState.DIFFERENT)
        self.assertEqual(result.ctr_trend, MetricTrend.STABLE)

    def test_ctr_decline_with_ranking_decline_does_not_blame_rewrite(self) -> None:
        result = assess_search_appearance(
            query="seo audit",
            market="US",
            signals=SearchAppearanceSignals(
                source_title="SEO Audit",
                source_title_count=1,
                source_description="Audit your site",
                source_description_count=1,
                serp_title="SEO Audit Tool",
                serp_snippet="Audit your website",
                previous_position=3,
                current_position=7,
                previous_ctr=0.12,
                current_ctr=0.06,
            ),
        )
        self.assertEqual(result.state, SearchAppearanceState.RANKING_CHANGE_PRESENT)
        self.assertEqual(result.position_trend, MetricTrend.DECLINING)
        self.assertEqual(result.recommended_action, SearchAppearanceAction.DIAGNOSE_RANKING_DECLINE)

    def test_ctr_decline_with_stable_ranking_and_rewrite_is_candidate(self) -> None:
        result = assess_search_appearance(
            query="seo audit",
            market="US",
            signals=SearchAppearanceSignals(
                source_title="SEO Audit",
                source_title_count=1,
                source_description="Audit your site",
                source_description_count=1,
                serp_title="Free SEO Audit Tool",
                serp_snippet="Check your website SEO",
                previous_position=4,
                current_position=4.1,
                previous_ctr=0.12,
                current_ctr=0.08,
            ),
        )
        self.assertEqual(result.state, SearchAppearanceState.PRESENTATION_CHANGE_CANDIDATE)
        self.assertEqual(result.position_trend, MetricTrend.STABLE)
        self.assertEqual(result.ctr_trend, MetricTrend.DECLINING)

    def test_target_page_mismatch_takes_precedence_over_copy_tweaks(self) -> None:
        result = assess_search_appearance(
            query="seo audit",
            market="US",
            signals=SearchAppearanceSignals(
                source_title="SEO Audit",
                source_title_count=1,
                source_description="Audit your site",
                source_description_count=1,
                serp_title="SEO Audit",
                serp_snippet="Audit your site",
                serp_url="https://example.com/blog/a",
                target_page="https://example.com/product",
                previous_position=4,
                current_position=4,
                previous_ctr=0.1,
                current_ctr=0.1,
            ),
        )
        self.assertEqual(result.state, SearchAppearanceState.TARGET_PAGE_MISMATCH)
        self.assertEqual(result.recommended_action, SearchAppearanceAction.INVESTIGATE_PAGE_OWNERSHIP)
        self.assertIs(result.ranking_page_state, TargetPageOwnershipState.MISMATCHED)
        self.assertEqual(result.to_dict()["rankingPageState"], "mismatched")
        self.assertEqual(result.to_dict()["recommendedAction"], "investigate_page_ownership")

    def test_missing_serp_evidence_is_insufficient(self) -> None:
        result = assess_search_appearance(
            query="seo audit",
            market="US",
            signals=SearchAppearanceSignals(
                source_title="SEO Audit",
                source_title_count=1,
                source_description="Audit your site",
                source_description_count=1,
            ),
        )
        self.assertEqual(result.state, SearchAppearanceState.INSUFFICIENT_EVIDENCE)
        self.assertIn("serp_presentation", result.unknowns)

    def test_matching_presentation_with_stable_metrics_has_no_material_issue(self) -> None:
        result = assess_search_appearance(
            query="seo audit",
            market="US",
            signals=SearchAppearanceSignals(
                source_title="SEO Audit",
                source_title_count=1,
                source_description="Audit your site",
                source_description_count=1,
                serp_title="SEO Audit",
                serp_snippet="Audit your site",
                previous_position=4,
                current_position=4.1,
                previous_ctr=0.1,
                current_ctr=0.101,
            ),
        )
        self.assertEqual(result.state, SearchAppearanceState.NO_MATERIAL_ISSUE)

    def test_wire_contract_matches_schema_required_order(self) -> None:
        payload = assess_search_appearance(
            query="seo audit",
            market="US",
            signals=SearchAppearanceSignals(
                source_title="SEO Audit",
                source_title_count=1,
                serp_title="SEO Audit",
            ),
        ).to_dict()
        schema = json.loads((ROOT / "schemas" / "search-appearance-assessment.v1.schema.json").read_text())
        self.assertEqual(schema["$id"], SEARCH_APPEARANCE_SCHEMA_ID)
        self.assertEqual(tuple(payload), tuple(schema["required"]))
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
