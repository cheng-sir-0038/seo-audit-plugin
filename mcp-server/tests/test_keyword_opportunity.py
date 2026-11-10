from __future__ import annotations

import unittest

from codex_seo_mcp.diagnosis.keyword_opportunity import (
    classify_relative_demand,
    evaluate_keyword_opportunity,
    missing_scenario_inputs,
)
from codex_seo_mcp.models.keyword_opportunity import (
    KeywordDemandLevel,
    KeywordFitState,
    KeywordOpportunityAction,
    KeywordOpportunityLevel,
    KeywordOpportunityScenario,
    KeywordOpportunitySignals,
    KeywordOpportunityStatus,
    KeywordOpportunityTiming,
    KeywordSignalState,
)


class KeywordOpportunityScenarioTests(unittest.TestCase):
    def test_required_inputs_are_scenario_specific(self) -> None:
        self.assertEqual(
            missing_scenario_inputs("metric_lookup", market=None),
            ["keyword", "market"],
        )
        self.assertEqual(
            missing_scenario_inputs("metric_lookup", keyword="seo", market=None),
            ["market"],
        )
        self.assertEqual(
            missing_scenario_inputs("site_research", market="US"),
            ["target_domain"],
        )
        self.assertEqual(
            missing_scenario_inputs(
                "page_research",
                market="US",
                target_domain="example.com",
            ),
            ["target_page"],
        )
        self.assertEqual(
            missing_scenario_inputs(
                "competitor_gap",
                market="US",
                target_domain="example.com",
            ),
            ["competitor_domains"],
        )

    def test_metric_lookup_does_not_invent_site_opportunity(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="metric_lookup",
            keyword="seo tools",
            market="US",
            signals=KeywordOpportunitySignals(
                search_volume=1000,
                keyword_difficulty=9,
                intents=["COMMERCIAL"],
            ),
        )

        self.assertEqual(result.status, "facts_only")
        self.assertEqual(result.feasibility_level, "high")
        self.assertIsNone(result.opportunity_level)
        self.assertIsNone(result.recommended_action)

    def test_relative_demand_uses_candidate_set_not_global_cutoff(self) -> None:
        cohort = [10, 20, 40, 100, 400, 800, 1200, 5000, 8000, 10000]
        self.assertEqual(classify_relative_demand(8000, cohort), "high")
        self.assertEqual(classify_relative_demand(100, cohort), "medium")
        self.assertEqual(classify_relative_demand(10, cohort), "low")
        self.assertEqual(classify_relative_demand(40, [40, 40]), "unknown")

    def test_string_inputs_normalize_to_domain_enums_without_changing_wire_values(self) -> None:
        signals = KeywordOpportunitySignals(
            search_volume=1000,
            keyword_difficulty=20,
            business_fit="strong",
            demand_level="high",
            intent_fit="medium",
            page_fit="weak",
            existing_signal="none",
            gap_signal="strong",
            serp_fit="strong",
        )

        self.assertIs(signals.business_fit, KeywordFitState.STRONG)
        self.assertIs(signals.demand_level, KeywordDemandLevel.HIGH)
        self.assertIs(signals.existing_signal, KeywordSignalState.NONE)

        result = evaluate_keyword_opportunity(
            scenario="site_research",
            keyword="seo platform",
            market="US",
            target_domain="example.com",
            signals=signals,
        )
        self.assertIs(result.scenario, KeywordOpportunityScenario.SITE_RESEARCH)
        self.assertIs(result.status, KeywordOpportunityStatus.ASSESSED)
        self.assertIsInstance(result.value_level, KeywordOpportunityLevel)
        self.assertIsInstance(result.recommended_timing, KeywordOpportunityTiming)
        self.assertIsInstance(result.recommended_action, KeywordOpportunityAction)
        payload = result.to_dict()
        self.assertEqual(payload["scenario"], "site_research")
        self.assertEqual(payload["status"], "assessed")


class KeywordOpportunityDecisionTests(unittest.TestCase):
    def test_kd_nine_can_still_be_low_opportunity_when_value_is_low(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="opportunity_discovery",
            keyword="unrelated easy keyword",
            market="US",
            target_domain="example.com",
            signals=KeywordOpportunitySignals(
                search_volume=10,
                keyword_difficulty=9,
                intents=["INFORMATIONAL"],
                business_fit="weak",
                demand_level="low",
                intent_fit="weak",
                existing_signal="none",
                serp_fit="medium",
            ),
        )

        self.assertEqual(result.feasibility_level, "high")
        self.assertEqual(result.value_level, "low")
        self.assertEqual(result.opportunity_level, "low")
        self.assertEqual(result.recommended_timing, "ignore")
        self.assertEqual(result.recommended_action, "ignore")
        self.assertTrue(any("0–14" in reason for reason in result.reasons))

    def test_low_volume_high_b2b_fit_can_remain_high_value(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="site_research",
            keyword="enterprise seo audit platform",
            market="US",
            target_domain="example.com",
            signals=KeywordOpportunitySignals(
                search_volume=40,
                keyword_difficulty=12,
                intents=["COMMERCIAL"],
                business_fit="strong",
                demand_level="low",
                intent_fit="strong",
                existing_signal="none",
                serp_fit="strong",
            ),
        )

        self.assertEqual(result.value_level, "high")
        self.assertEqual(result.feasibility_level, "high")
        self.assertEqual(result.opportunity_level, "high")
        self.assertEqual(result.recommended_timing, "now")
        self.assertEqual(result.recommended_action, "create_new_landing_page")

    def test_high_value_high_kd_is_later_not_ignore(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="site_research",
            keyword="enterprise seo platform",
            market="US",
            target_domain="example.com",
            signals=KeywordOpportunitySignals(
                search_volume=3000,
                keyword_difficulty=78,
                intents=["COMMERCIAL"],
                business_fit="strong",
                demand_level="high",
                intent_fit="strong",
                existing_signal="none",
                serp_fit="strong",
            ),
        )

        self.assertEqual(result.value_level, "high")
        self.assertEqual(result.feasibility_level, "low")
        self.assertEqual(result.opportunity_level, "medium")
        self.assertEqual(result.recommended_timing, "later")
        self.assertEqual(result.recommended_action, "later")

    def test_existing_top20_signal_promotes_existing_page_optimization(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="opportunity_discovery",
            keyword="technical seo audit",
            market="US",
            target_domain="example.com",
            signals=KeywordOpportunitySignals(
                search_volume=900,
                keyword_difficulty=54,
                intents=["COMMERCIAL", "INFORMATIONAL"],
                business_fit="strong",
                demand_level="medium",
                intent_fit="strong",
                existing_signal="medium",
                serp_fit="strong",
                current_position=14,
                current_ranking_url="https://example.com/seo-audit",
            ),
        )

        self.assertEqual(result.feasibility_level, "medium")
        self.assertEqual(result.recommended_timing, "now")
        self.assertEqual(result.recommended_action, "optimize_existing_page")


    def test_strong_existing_signal_without_kd_still_produces_high_feasibility(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="opportunity_discovery",
            keyword="technical seo audit",
            market="US",
            target_domain="example.com",
            signals=KeywordOpportunitySignals(
                search_volume=900,
                keyword_difficulty=None,
                intents=["COMMERCIAL"],
                business_fit="strong",
                demand_level="medium",
                intent_fit="strong",
                existing_signal="strong",
                serp_fit="strong",
                current_ranking_url="https://example.com/seo-audit",
            ),
        )

        self.assertIs(result.feasibility_level, KeywordOpportunityLevel.HIGH)
        self.assertIs(result.recommended_timing, KeywordOpportunityTiming.NOW)
        self.assertIs(result.recommended_action, KeywordOpportunityAction.OPTIMIZE_EXISTING_PAGE)

    def test_page_intent_mismatch_creates_new_page_instead_of_stuffing_old_page(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="page_research",
            keyword="seo audit software",
            market="US",
            target_domain="example.com",
            target_page="https://example.com/blog/how-seo-works",
            signals=KeywordOpportunitySignals(
                search_volume=1600,
                keyword_difficulty=18,
                intents=["COMMERCIAL"],
                business_fit="strong",
                demand_level="high",
                intent_fit="strong",
                page_fit="weak",
                existing_signal="none",
                serp_fit="strong",
            ),
        )

        self.assertEqual(result.opportunity_level, "high")
        self.assertEqual(result.recommended_action, "create_new_landing_page")
        self.assertTrue(any("不建议把关键词硬塞进现有页面" in reason for reason in result.reasons))

    def test_competitor_gap_is_only_a_signal(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="competitor_gap",
            keyword="generic competitor keyword",
            market="US",
            target_domain="example.com",
            competitor_domains=["competitor.example"],
            signals=KeywordOpportunitySignals(
                search_volume=5000,
                keyword_difficulty=22,
                intents=["INFORMATIONAL"],
                business_fit="weak",
                demand_level="high",
                intent_fit="weak",
                existing_signal="none",
                gap_signal="strong",
                serp_fit="strong",
            ),
        )

        self.assertEqual(result.opportunity_level, "low")
        self.assertEqual(result.recommended_action, "ignore")
        self.assertTrue(any("Gap 只作为候选信号" in reason for reason in result.reasons))


    def test_unknown_demand_level_stops_before_fake_opportunity(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="opportunity_discovery",
            keyword="seo tools",
            market="US",
            target_domain="example.com",
            signals=KeywordOpportunitySignals(
                search_volume=1000,
                keyword_difficulty=20,
                business_fit="strong",
                demand_level="unknown",
                intent_fit="strong",
                existing_signal="strong",
                serp_fit="strong",
            ),
        )

        self.assertEqual(result.status, KeywordOpportunityStatus.INSUFFICIENT_EVIDENCE)
        self.assertIn("demand_level", result.unknowns)
        self.assertIsNone(result.opportunity_level)
        self.assertIsNone(result.recommended_action)

    def test_unknown_business_fit_stops_before_fake_opportunity(self) -> None:
        result = evaluate_keyword_opportunity(
            scenario="site_research",
            keyword="seo tools",
            market="US",
            target_domain="example.com",
            signals=KeywordOpportunitySignals(
                search_volume=2000,
                keyword_difficulty=9,
                intents=["COMMERCIAL"],
                business_fit="unknown",
                demand_level="high",
                intent_fit="strong",
            ),
        )

        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.opportunity_level)
        self.assertIn("business_fit", result.unknowns)


if __name__ == "__main__":
    unittest.main()
