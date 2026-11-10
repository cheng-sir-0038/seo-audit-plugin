from __future__ import annotations

import unittest

from codex_seo_mcp.diagnosis.contracts import (
    ActionCategory,
    Confidence,
    Finding,
    FindingStatus,
    Hypothesis,
    HypothesisStatus,
)
from codex_seo_mcp.diagnosis.ranking import TargetPageState, build_ranking_comparison
from codex_seo_mcp.models.search_performance import SearchPerformance, SearchPerformanceRow


def _performance(
    start: str,
    end: str,
    rows: list[SearchPerformanceRow],
) -> SearchPerformance:
    return SearchPerformance(
        property_url="sc-domain:example.com",
        start_date=start,
        end_date=end,
        dimensions=["query", "page"],
        rows=rows,
    )


class DiagnosisContractTests(unittest.TestCase):
    def test_finding_and_hypothesis_use_stable_enums(self) -> None:
        """跨 Host 的诊断状态不能散落成随意字符串。"""

        finding = Finding(
            type="canonical_mismatch",
            subject="https://example.com/a",
            status=FindingStatus.CONFIRMED,
            confidence=Confidence.HIGH,
            summary="Canonical 指向其他页面",
            rationale="最终 HTML canonical 与预期不一致",
            action_category=ActionCategory.TECHNICAL,
            source_refs=["PageInspection:https://example.com/a"],
        )
        hypothesis = Hypothesis(
            type="canonical-regression",
            status=HypothesisStatus.SUPPORTED,
            rationale="时间窗口与页面事实一致",
        )

        self.assertEqual(finding.status.value, "confirmed")
        self.assertEqual(finding.action_category.value, "technical")
        self.assertEqual(hypothesis.status.value, "supported")

    def test_ranking_comparison_preserves_multiple_pages_and_target_mismatch(self) -> None:
        """同一 Query 多页面不能被合成一个排名，Target Page 也不能覆盖 Ranking Page。"""

        prior = _performance(
            "2026-07-01",
            "2026-07-31",
            [
                SearchPerformanceRow(
                    query="seo tools",
                    page="https://example.com/target",
                    clicks=40,
                    impressions=400,
                    ctr=0.10,
                    position=4.0,
                ),
                SearchPerformanceRow(
                    query="seo tools",
                    page="https://example.com/blog",
                    clicks=10,
                    impressions=100,
                    ctr=0.10,
                    position=9.0,
                ),
            ],
        )
        current = _performance(
            "2026-08-01",
            "2026-08-31",
            [
                SearchPerformanceRow(
                    query="seo tools",
                    page="https://example.com/blog",
                    clicks=20,
                    impressions=300,
                    ctr=0.066,
                    position=6.0,
                ),
                SearchPerformanceRow(
                    query="seo tools",
                    page="https://example.com/other",
                    clicks=5,
                    impressions=80,
                    ctr=0.0625,
                    position=12.0,
                ),
            ],
        )

        result = build_ranking_comparison(
            prior,
            current,
            query="seo tools",
            target_page="https://example.com/target",
        )

        self.assertEqual(result.prior_ranking_pages, [
            "https://example.com/blog",
            "https://example.com/target",
        ])
        self.assertEqual(result.current_ranking_pages, [
            "https://example.com/blog",
            "https://example.com/other",
        ])
        self.assertEqual(result.target_page_prior_state, TargetPageState.OBSERVED)
        self.assertEqual(result.target_page_current_state, TargetPageState.NOT_OBSERVED)
        self.assertEqual(len(result.pages), 3)
        target_change = next(item for item in result.pages if item.page.endswith("/target"))
        self.assertIsNotNone(target_change.prior)
        self.assertIsNone(target_change.current)
        self.assertIn("多个 Ranking Page", " ".join(result.warnings))

    def test_no_data_stays_none_instead_of_becoming_zero(self) -> None:
        """GSC 空行只表示 No Data，不得生成 clicks=0/position=0 的虚假历史。"""

        prior = _performance("2026-07-01", "2026-07-31", [])
        current = _performance(
            "2026-08-01",
            "2026-08-31",
            [
                SearchPerformanceRow(
                    query="seo tools",
                    page="https://example.com/page",
                    clicks=2,
                    impressions=20,
                    ctr=0.1,
                    position=8.0,
                )
            ],
        )

        result = build_ranking_comparison(prior, current, query="seo tools")

        self.assertIsNone(result.prior)
        self.assertIsNotNone(result.current)
        self.assertIsNone(result.pages[0].prior)
        self.assertEqual(result.target_page_prior_state, TargetPageState.UNKNOWN)
        self.assertIn("不能解释为此前未排名", result.warnings[0])

    def test_weighted_summary_uses_impressions_for_position(self) -> None:
        """多页面汇总 position 按 impressions 加权，避免简单平均产生错误比较。"""

        prior = _performance(
            "2026-07-01",
            "2026-07-31",
            [
                SearchPerformanceRow(query="q", page="https://e.com/a", impressions=100, position=2),
                SearchPerformanceRow(query="q", page="https://e.com/b", impressions=300, position=10),
            ],
        )
        current = _performance(
            "2026-08-01",
            "2026-08-31",
            [SearchPerformanceRow(query="q", page="https://e.com/a", impressions=10, position=5)],
        )

        result = build_ranking_comparison(prior, current, query="q")

        self.assertAlmostEqual(result.prior.position, 8.0)
        self.assertAlmostEqual(result.current.position, 5.0)


if __name__ == "__main__":
    unittest.main()
