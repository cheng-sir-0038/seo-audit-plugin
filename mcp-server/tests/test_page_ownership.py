from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_seo_mcp.diagnosis.page_ownership import (
    PAGE_OWNERSHIP_SCHEMA_ID,
    assess_page_ownership,
    observations_from_ranking_comparison,
)
from codex_seo_mcp.diagnosis.ranking import build_ranking_comparison
from codex_seo_mcp.models.page_ownership import (
    ContentOverlap,
    PageOwnershipAction,
    PageOwnershipObservation,
    PageOwnershipPairEvidence,
    PageOwnershipState,
    PageRoleRelation,
    TargetPageOwnershipState,
    VisibilityImpact,
)
from codex_seo_mcp.models.search_performance import SearchPerformance, SearchPerformanceRow


ROOT = Path(__file__).resolve().parents[2]


class PageOwnershipAssessmentTests(unittest.TestCase):
    def test_gsc_ranking_comparison_converts_to_page_observations(self) -> None:
        prior = SearchPerformance(
            property_url="sc-domain:example.com",
            start_date="2026-07-01",
            end_date="2026-07-31",
            dimensions=["query", "page"],
            rows=[
                SearchPerformanceRow(
                    query="seo audit",
                    page="https://example.com/a",
                    clicks=10,
                    impressions=100,
                    ctr=0.1,
                    position=4,
                )
            ],
        )
        current = SearchPerformance(
            property_url="sc-domain:example.com",
            start_date="2026-08-01",
            end_date="2026-08-31",
            dimensions=["query", "page"],
            rows=[
                SearchPerformanceRow(
                    query="seo audit",
                    page="https://example.com/b",
                    clicks=8,
                    impressions=100,
                    ctr=0.08,
                    position=6,
                )
            ],
        )

        comparison = build_ranking_comparison(prior, current, query="seo audit")
        observations = observations_from_ranking_comparison(comparison)

        by_url = {item.url: item for item in observations}
        self.assertTrue(by_url["https://example.com/a"].previous_observed)
        self.assertFalse(by_url["https://example.com/a"].current_observed)
        self.assertEqual(by_url["https://example.com/a"].previous_position, 4)
        self.assertTrue(by_url["https://example.com/b"].current_observed)
        self.assertFalse(by_url["https://example.com/b"].previous_observed)
        self.assertEqual(by_url["https://example.com/b"].current_position, 6)

    def test_stable_single_owner_and_target_match(self) -> None:
        result = assess_page_ownership(
            query="seo audit",
            market="us",
            target_page="https://example.com/seo-audit",
            observations=[
                PageOwnershipObservation(
                    url="https://example.com/seo-audit",
                    current_position=8,
                    previous_position=9,
                    current_observed=True,
                    previous_observed=True,
                )
            ],
            visibility_impact=VisibilityImpact.NEUTRAL,
        )

        self.assertEqual(result.ownership_state, PageOwnershipState.STABLE_OWNER)
        self.assertEqual(result.target_page_state, TargetPageOwnershipState.MATCHED)
        self.assertEqual(result.current_owner, "https://example.com/seo-audit")
        self.assertFalse(result.switching_observed)
        self.assertEqual(result.recommended_action, PageOwnershipAction.KEEP_OR_STRENGTHEN_OWNER)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.to_dict()["recommendedAction"], "keep_or_strengthen_owner")

    def test_target_mismatch_is_not_automatically_cannibalization(self) -> None:
        result = assess_page_ownership(
            query="seo audit",
            market="US",
            target_page="https://example.com/product",
            observations=[
                PageOwnershipObservation(
                    url="https://example.com/blog/seo-audit",
                    current_position=7,
                    previous_position=8,
                )
            ],
        )

        self.assertEqual(result.ownership_state, PageOwnershipState.STABLE_OWNER)
        self.assertEqual(result.target_page_state, TargetPageOwnershipState.MISMATCHED)
        self.assertEqual(result.recommended_action, PageOwnershipAction.REASSESS_TARGET_PAGE)
        self.assertTrue(any("不能" in reason and "canonical/redirect" in reason for reason in result.reasons))

    def test_multiple_pages_with_distinct_roles_are_intent_split(self) -> None:
        page_a = "https://example.com/guide"
        page_b = "https://example.com/product"
        result = assess_page_ownership(
            query="seo audit",
            market="US",
            observations=[
                PageOwnershipObservation(url=page_a, current_position=2),
                PageOwnershipObservation(url=page_b, current_position=5),
            ],
            pair_evidence=[
                PageOwnershipPairEvidence(
                    page_a=page_a,
                    page_b=page_b,
                    role_relation=PageRoleRelation.DISTINCT,
                    content_overlap=ContentOverlap.LOW,
                )
            ],
            visibility_impact=VisibilityImpact.POSITIVE,
        )

        self.assertEqual(result.ownership_state, PageOwnershipState.INTENT_SPLIT)
        self.assertEqual(result.recommended_action, PageOwnershipAction.KEEP_ROLES_DISTINCT)
        self.assertNotIn("visibility_impact", result.unknowns)

    def test_switching_without_role_evidence_is_not_called_cannibalization(self) -> None:
        page_a = "https://example.com/a"
        page_b = "https://example.com/b"
        result = assess_page_ownership(
            query="seo audit",
            market="US",
            observations=[
                PageOwnershipObservation(
                    url=page_a,
                    current_position=12,
                    previous_position=4,
                ),
                PageOwnershipObservation(
                    url=page_b,
                    current_position=5,
                    previous_position=15,
                ),
            ],
        )

        self.assertEqual(result.ownership_state, PageOwnershipState.PAGE_SWITCHING)
        self.assertTrue(result.switching_observed)
        self.assertEqual(result.previous_owner, page_a)
        self.assertEqual(result.current_owner, page_b)
        self.assertEqual(result.recommended_action, PageOwnershipAction.CLARIFY_PAGE_ROLES)
        self.assertIn("page_role_relationship", result.unknowns)

    def test_switching_same_role_high_overlap_is_probable_cannibalization(self) -> None:
        page_a = "https://example.com/a"
        page_b = "https://example.com/b"
        result = assess_page_ownership(
            query="seo audit",
            market="US",
            observations=[
                PageOwnershipObservation(url=page_a, current_position=14, previous_position=5),
                PageOwnershipObservation(url=page_b, current_position=6, previous_position=16),
            ],
            pair_evidence=[
                PageOwnershipPairEvidence(
                    page_a=page_a,
                    page_b=page_b,
                    role_relation=PageRoleRelation.SAME,
                    content_overlap=ContentOverlap.HIGH,
                )
            ],
            visibility_impact=VisibilityImpact.NEGATIVE,
        )

        self.assertEqual(result.ownership_state, PageOwnershipState.PROBABLE_CANNIBALIZATION)
        self.assertEqual(result.recommended_action, PageOwnershipAction.CONSOLIDATE_OR_DIFFERENTIATE)
        self.assertEqual(result.confidence, "high")

    def test_negative_visibility_plus_conflict_can_be_probable_without_owner_switch(self) -> None:
        page_a = "https://example.com/a"
        page_b = "https://example.com/b"
        result = assess_page_ownership(
            query="seo audit",
            market="US",
            observations=[
                PageOwnershipObservation(url=page_a, current_position=8, previous_position=7),
                PageOwnershipObservation(url=page_b, current_position=13, previous_position=12),
            ],
            pair_evidence=[
                PageOwnershipPairEvidence(
                    page_a=page_a,
                    page_b=page_b,
                    role_relation=PageRoleRelation.SAME,
                    content_overlap=ContentOverlap.HIGH,
                )
            ],
            visibility_impact=VisibilityImpact.NEGATIVE,
        )

        self.assertFalse(result.switching_observed)
        self.assertEqual(result.ownership_state, PageOwnershipState.PROBABLE_CANNIBALIZATION)

    def test_two_top_pages_without_harm_are_not_auto_cannibalization(self) -> None:
        page_a = "https://example.com/a"
        page_b = "https://example.com/b"
        result = assess_page_ownership(
            query="seo audit",
            market="US",
            observations=[
                PageOwnershipObservation(url=page_a, current_position=1, previous_position=1),
                PageOwnershipObservation(url=page_b, current_position=2, previous_position=2),
            ],
            pair_evidence=[
                PageOwnershipPairEvidence(
                    page_a=page_a,
                    page_b=page_b,
                    role_relation=PageRoleRelation.SAME,
                    content_overlap=ContentOverlap.HIGH,
                )
            ],
            visibility_impact=VisibilityImpact.POSITIVE,
        )

        self.assertEqual(result.ownership_state, PageOwnershipState.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.recommended_action, PageOwnershipAction.MONITOR)
        self.assertTrue(any("暂不升级" in reason for reason in result.reasons))

    def test_no_ranking_page_evidence_stays_insufficient(self) -> None:
        result = assess_page_ownership(
            query="seo audit",
            market="US",
            observations=[],
        )

        self.assertEqual(result.ownership_state, PageOwnershipState.INSUFFICIENT_EVIDENCE)
        self.assertIn("ranking_pages", result.unknowns)
        self.assertEqual(result.confidence, "low")

    def test_wire_contract_matches_versioned_schema_required_order(self) -> None:
        result = assess_page_ownership(
            query="seo audit",
            market="US",
            observations=[PageOwnershipObservation(url="https://example.com/a", current_position=5)],
        )
        payload = result.to_dict()
        schema = json.loads((ROOT / "schemas" / "page-ownership-assessment.v1.schema.json").read_text())

        self.assertEqual(schema["$id"], PAGE_OWNERSHIP_SCHEMA_ID)
        self.assertEqual(tuple(payload), tuple(schema["required"]))
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
