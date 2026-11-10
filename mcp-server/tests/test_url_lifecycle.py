from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_seo_mcp.diagnosis.url_lifecycle import (
    URL_LIFECYCLE_SCHEMA_ID,
    assess_url_lifecycle,
)
from codex_seo_mcp.models.page_inspection import PageInspection, PageRedirectHop
from codex_seo_mcp.models.url_lifecycle import (
    ErrorPageSignal,
    RedirectState,
    Soft404State,
    TargetState,
    UrlLifecycleState,
)

ROOT = Path(__file__).resolve().parents[2]


def page(
    *,
    requested: str = "https://example.com/old",
    final: str = "https://example.com/old",
    status: int = 200,
    redirects: list[PageRedirectHop] | None = None,
    canonical: str | None = None,
    meta_refresh: str | None = None,
) -> PageInspection:
    return PageInspection(
        requested_url=requested,
        final_url=final,
        status_code=status,
        content_type="text/html",
        content_length_bytes=100,
        redirects=list(redirects or []),
        title="Title",
        title_count=1,
        meta_description="Description",
        meta_description_count=1,
        canonical=canonical,
        canonical_count=1 if canonical else 0,
        robots_meta_tags=[],
        googlebot_meta_tags=[],
        declared_noindex=False,
        h1=["Title"],
        lang="en",
        charset="utf-8",
        meta_refresh_url=meta_refresh,
        x_robots_tags=[],
        hreflang_alternates=[],
        anchor_links=[],
        rel_next_urls=[],
        rel_prev_urls=[],
        structured_data=[],
    )


def hop(from_url: str, code: int, to_url: str) -> PageRedirectHop:
    return PageRedirectHop(
        from_url=from_url,
        status_code=code,
        location=to_url,
        to_url=to_url,
    )


class UrlLifecycleAssessmentTests(unittest.TestCase):
    def test_direct_permanent_move_to_expected_target_is_healthy(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/new",
                redirects=[hop("https://example.com/old", 301, "https://example.com/new")],
                canonical="https://example.com/new",
            ),
            intent="permanent_move",
            expected_target="https://example.com/new",
        )

        self.assertEqual(result.state, UrlLifecycleState.HEALTHY)
        self.assertEqual(result.redirect_state, RedirectState.DIRECT_PERMANENT)
        self.assertEqual(result.target_state, TargetState.MATCHED)
        self.assertEqual(result.issue_codes, [])

    def test_temporary_redirect_for_permanent_move_needs_attention(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/new",
                redirects=[hop("https://example.com/old", 302, "https://example.com/new")],
                canonical="https://example.com/new",
            ),
            intent="permanent_move",
            expected_target="https://example.com/new",
        )

        self.assertEqual(result.state, UrlLifecycleState.NEEDS_ATTENTION)
        self.assertEqual(result.redirect_state, RedirectState.DIRECT_TEMPORARY)
        self.assertIn("non_permanent_redirect_in_permanent_move", result.issue_codes)

    def test_permanent_redirect_for_temporary_move_needs_attention(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/new",
                redirects=[hop("https://example.com/old", 301, "https://example.com/new")],
                canonical="https://example.com/new",
            ),
            intent="temporary_move",
            expected_target="https://example.com/new",
        )

        self.assertEqual(result.state, UrlLifecycleState.NEEDS_ATTENTION)
        self.assertEqual(result.redirect_state, RedirectState.DIRECT_PERMANENT)
        self.assertEqual(
            result.issue_codes,
            ["permanent_redirect_for_temporary_move"],
        )

    def test_move_without_expected_target_is_insufficient_evidence(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/new",
                redirects=[hop("https://example.com/old", 301, "https://example.com/new")],
                canonical="https://example.com/new",
            ),
            intent="permanent_move",
        )

        self.assertEqual(result.state, UrlLifecycleState.INSUFFICIENT_EVIDENCE)
        self.assertIn("expected_target", result.unknowns)
        self.assertEqual(result.confidence, "low")

    def test_redirect_chain_is_not_hidden(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/new",
                redirects=[
                    hop("https://example.com/old", 301, "https://example.com/middle"),
                    hop("https://example.com/middle", 308, "https://example.com/new"),
                ],
                canonical="https://example.com/new",
            ),
            intent="permanent_move",
            expected_target="https://example.com/new",
        )

        self.assertEqual(result.state, UrlLifecycleState.NEEDS_ATTENTION)
        self.assertEqual(result.redirect_state, RedirectState.CHAIN)
        self.assertIn("redirect_chain", result.issue_codes)

    def test_long_redirect_chain_is_misconfigured(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/new",
                redirects=[
                    hop("https://example.com/old", 301, "https://example.com/a"),
                    hop("https://example.com/a", 301, "https://example.com/b"),
                    hop("https://example.com/b", 301, "https://example.com/c"),
                    hop("https://example.com/c", 301, "https://example.com/new"),
                ],
                canonical="https://example.com/new",
            ),
            intent="permanent_move",
            expected_target="https://example.com/new",
        )

        self.assertEqual(result.state, UrlLifecycleState.MISCONFIGURED)
        self.assertEqual(
            result.issue_codes,
            ["redirect_chain", "long_redirect_chain"],
        )

    def test_wrong_redirect_target_is_misconfigured(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/wrong",
                redirects=[hop("https://example.com/old", 301, "https://example.com/wrong")],
                canonical="https://example.com/wrong",
            ),
            intent="permanent_move",
            expected_target="https://example.com/new",
        )

        self.assertEqual(result.state, UrlLifecycleState.MISCONFIGURED)
        self.assertEqual(result.target_state, TargetState.MISMATCHED)
        self.assertIn("redirect_target_mismatch", result.issue_codes)

    def test_destination_canonical_conflict_is_misconfigured(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/new",
                redirects=[hop("https://example.com/old", 301, "https://example.com/new")],
                canonical="https://example.com/third",
            ),
            intent="permanent_move",
            expected_target="https://example.com/new",
        )

        self.assertEqual(result.state, UrlLifecycleState.MISCONFIGURED)
        self.assertIn("destination_canonical_conflict", result.issue_codes)

    def test_removed_url_404_is_valid_removal(self) -> None:
        result = assess_url_lifecycle(page(status=404), intent="remove")

        self.assertEqual(result.state, UrlLifecycleState.REMOVED)
        self.assertEqual(result.issue_codes, [])

    def test_removed_url_returning_200_is_misconfigured(self) -> None:
        result = assess_url_lifecycle(page(status=200), intent="remove")

        self.assertEqual(result.state, UrlLifecycleState.MISCONFIGURED)
        self.assertIn("removal_not_effective", result.issue_codes)

    def test_soft404_requires_body_evidence(self) -> None:
        result = assess_url_lifecycle(
            page(status=200),
            check_soft404=True,
            error_page_signal=ErrorPageSignal.PRESENT,
        )

        self.assertEqual(result.soft404_state, Soft404State.SUSPECTED)
        self.assertEqual(result.state, UrlLifecycleState.NEEDS_ATTENTION)
        self.assertIn("soft404_suspected", result.issue_codes)

    def test_soft404_without_body_evidence_stays_unknown(self) -> None:
        result = assess_url_lifecycle(page(status=200), check_soft404=True)

        self.assertEqual(result.soft404_state, Soft404State.UNKNOWN)
        self.assertEqual(result.state, UrlLifecycleState.INSUFFICIENT_EVIDENCE)
        self.assertIn("error_page_signal", result.unknowns)

    def test_observe_canonical_other_is_attention_not_automatic_error(self) -> None:
        result = assess_url_lifecycle(
            page(status=200, canonical="https://example.com/canonical"),
            intent="observe",
        )

        self.assertEqual(result.state, UrlLifecycleState.NEEDS_ATTENTION)
        self.assertIn("canonical_points_elsewhere", result.issue_codes)

    def test_observe_server_error_is_misconfigured(self) -> None:
        result = assess_url_lifecycle(page(status=503), intent="observe")

        self.assertEqual(result.state, UrlLifecycleState.MISCONFIGURED)
        self.assertEqual(result.issue_codes, ["server_error"])

    def test_healthy_observe_adds_monitoring_action(self) -> None:
        result = assess_url_lifecycle(page(), intent="observe")

        self.assertEqual(result.state, UrlLifecycleState.HEALTHY)
        self.assertEqual(result.issue_codes, [])
        self.assertEqual(
            result.recommended_actions,
            ["保持当前 URL 生命周期配置，并按业务变更继续监控。"],
        )

    def test_keep_intent_with_redirect_is_misconfigured(self) -> None:
        result = assess_url_lifecycle(
            page(
                final="https://example.com/new",
                redirects=[hop("https://example.com/old", 301, "https://example.com/new")],
            ),
            intent="keep",
        )

        self.assertEqual(result.state, UrlLifecycleState.MISCONFIGURED)
        self.assertIn("unexpected_redirect", result.issue_codes)

    def test_wire_contract_matches_schema_required_order(self) -> None:
        payload = assess_url_lifecycle(page()).to_dict()
        schema = json.loads((ROOT / "schemas" / "url-lifecycle-assessment.v1.schema.json").read_text())

        self.assertEqual(schema["$id"], URL_LIFECYCLE_SCHEMA_ID)
        self.assertEqual(tuple(payload), tuple(schema["required"]))
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
