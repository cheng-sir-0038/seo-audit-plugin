from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_seo_mcp.diagnosis.content_lifecycle import (
    CONTENT_LIFECYCLE_SCHEMA_ID,
    assess_content_lifecycle,
)
from codex_seo_mcp.models.content_lifecycle import (
    ContentLifecycleAction,
    ContentLifecycleSignals,
    ContentLifecycleState,
    FitState,
    FreshnessState,
    GapState,
    PurposeState,
    TrendState,
    ValueState,
)
from codex_seo_mcp.models.page_ownership import PageOwnershipState

ROOT = Path(__file__).resolve().parents[2]


class ContentLifecycleTests(unittest.TestCase):
    def test_wire_string_signals_are_normalized_to_enums(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/guide",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend="declining",
                demand_trend="stable",
                intent_fit="strong",
                freshness="outdated",
                coverage_gap="medium",
                content_value="high",
                distinct_purpose="distinct",
            ),
        )
        self.assertEqual(result.action, ContentLifecycleAction.REFRESH)

    def test_decline_with_stable_demand_and_outdated_content_refreshes(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/guide",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend=TrendState.DECLINING,
                demand_trend=TrendState.STABLE,
                intent_fit=FitState.STRONG,
                freshness=FreshnessState.OUTDATED,
                coverage_gap=GapState.MEDIUM,
                content_value=ValueState.HIGH,
                distinct_purpose=PurposeState.DISTINCT,
            ),
        )
        self.assertEqual(result.action, ContentLifecycleAction.REFRESH)
        self.assertEqual(result.state, ContentLifecycleState.ACTIONABLE)

    def test_decline_with_current_content_and_gap_expands_existing_page(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/guide",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend=TrendState.DECLINING,
                demand_trend=TrendState.STABLE,
                intent_fit=FitState.STRONG,
                freshness=FreshnessState.CURRENT,
                coverage_gap=GapState.HIGH,
                content_value=ValueState.HIGH,
                distinct_purpose=PurposeState.DISTINCT,
            ),
        )
        self.assertEqual(result.action, ContentLifecycleAction.EXPAND)

    def test_demand_decline_does_not_trigger_fake_refresh(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/guide",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend=TrendState.DECLINING,
                demand_trend=TrendState.DECLINING,
                intent_fit=FitState.STRONG,
                freshness=FreshnessState.OUTDATED,
                coverage_gap=GapState.HIGH,
                content_value=ValueState.MEDIUM,
                distinct_purpose=PurposeState.DISTINCT,
            ),
        )
        self.assertEqual(result.action, ContentLifecycleAction.MONITOR)
        self.assertEqual(result.state, ContentLifecycleState.DEMAND_DECLINE)

    def test_probable_cannibalization_without_distinct_purpose_merges(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/old-guide",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend=TrendState.DECLINING,
                demand_trend=TrendState.STABLE,
                intent_fit=FitState.STRONG,
                freshness=FreshnessState.CURRENT,
                coverage_gap=GapState.LOW,
                content_value=ValueState.MEDIUM,
                distinct_purpose=PurposeState.NOT_DISTINCT,
                page_ownership_state="probable_cannibalization",
                replacement_url="https://example.com/main-guide",
            ),
        )
        self.assertEqual(result.action, ContentLifecycleAction.MERGE)
        self.assertEqual(result.merge_target, "https://example.com/main-guide")

    def test_low_value_no_purpose_with_replacement_redirects(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/obsolete",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend=TrendState.STABLE,
                demand_trend=TrendState.STABLE,
                intent_fit=FitState.WEAK,
                freshness=FreshnessState.OUTDATED,
                coverage_gap=GapState.LOW,
                content_value=ValueState.LOW,
                distinct_purpose=PurposeState.NOT_DISTINCT,
                replacement_url="https://example.com/current",
            ),
        )
        self.assertEqual(result.action, ContentLifecycleAction.REDIRECT)
        self.assertEqual(result.merge_target, "https://example.com/current")

    def test_low_value_no_purpose_without_replacement_removes(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/obsolete",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend=TrendState.STABLE,
                demand_trend=TrendState.DECLINING,
                intent_fit=FitState.WEAK,
                freshness=FreshnessState.OUTDATED,
                coverage_gap=GapState.LOW,
                content_value=ValueState.LOW,
                distinct_purpose=PurposeState.NOT_DISTINCT,
            ),
        )
        self.assertEqual(result.action, ContentLifecycleAction.REMOVE)

    def test_healthy_current_page_keeps(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/guide",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend=TrendState.GROWING,
                demand_trend=TrendState.STABLE,
                intent_fit=FitState.STRONG,
                freshness=FreshnessState.CURRENT,
                coverage_gap=GapState.LOW,
                content_value=ValueState.HIGH,
                distinct_purpose=PurposeState.DISTINCT,
            ),
        )
        self.assertEqual(result.action, ContentLifecycleAction.KEEP)
        self.assertEqual(result.state, ContentLifecycleState.HEALTHY)

    def test_unknown_evidence_monitors_instead_of_destructive_action(self) -> None:
        result = assess_content_lifecycle(
            page_url="https://example.com/guide",
            market="US",
            signals=ContentLifecycleSignals(),
        )
        self.assertEqual(result.action, ContentLifecycleAction.MONITOR)
        self.assertEqual(result.state, ContentLifecycleState.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.confidence, "low")

    def test_page_ownership_string_is_normalized_to_existing_domain_enum(self) -> None:
        signals = ContentLifecycleSignals(page_ownership_state="probable_cannibalization")

        self.assertIs(signals.page_ownership_state, PageOwnershipState.PROBABLE_CANNIBALIZATION)

    def test_unknown_page_ownership_stays_unknown_on_wire_without_duplicate_enum(self) -> None:
        signals = ContentLifecycleSignals(page_ownership_state="unknown")
        result = assess_content_lifecycle(
            page_url="https://example.com/guide",
            market="US",
            signals=signals,
        )

        self.assertIsNone(signals.page_ownership_state)
        self.assertEqual(result.to_dict()["signals"]["pageOwnershipState"], "unknown")

    def test_wire_contract_matches_schema_required_order(self) -> None:
        payload = assess_content_lifecycle(
            page_url="https://example.com/guide",
            market="US",
            signals=ContentLifecycleSignals(
                visibility_trend=TrendState.STABLE,
                demand_trend=TrendState.STABLE,
                intent_fit=FitState.STRONG,
                freshness=FreshnessState.CURRENT,
                coverage_gap=GapState.LOW,
                content_value=ValueState.HIGH,
                distinct_purpose=PurposeState.DISTINCT,
            ),
        ).to_dict()
        schema = json.loads((ROOT / "schemas" / "content-lifecycle-assessment.v1.schema.json").read_text())
        self.assertEqual(schema["$id"], CONTENT_LIFECYCLE_SCHEMA_ID)
        self.assertEqual(tuple(payload), tuple(schema["required"]))
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
