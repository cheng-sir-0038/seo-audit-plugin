from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_seo_mcp.diagnosis.hreflang import HREFLANG_SCHEMA_ID, assess_hreflang_cluster
from codex_seo_mcp.models.hreflang import HreflangIssueCode, HreflangState
from codex_seo_mcp.models.page_inspection import PageHreflangAlternate, PageInspection

ROOT = Path(__file__).resolve().parents[2]


def page(
    url: str,
    *,
    status: int = 200,
    canonical: str | None = None,
    noindex: bool = False,
    alternates: list[tuple[str, str]] | None = None,
) -> PageInspection:
    return PageInspection(
        requested_url=url,
        final_url=url,
        status_code=status,
        content_type="text/html",
        content_length_bytes=100,
        redirects=[],
        title="Title",
        title_count=1,
        meta_description="Description",
        meta_description_count=1,
        canonical=canonical or url,
        canonical_count=1,
        robots_meta_tags=["noindex"] if noindex else [],
        googlebot_meta_tags=[],
        declared_noindex=noindex,
        h1=["Title"],
        lang="en",
        charset="utf-8",
        meta_refresh_url=None,
        x_robots_tags=[],
        hreflang_alternates=[
            PageHreflangAlternate(hreflang=code, url=target, source="html")
            for code, target in (alternates or [])
        ],
        anchor_links=[],
        rel_next_urls=[],
        rel_prev_urls=[],
        structured_data=[],
    )


class HreflangAssessmentTests(unittest.TestCase):
    def test_reciprocal_self_referencing_cluster_is_healthy(self) -> None:
        en = "https://example.com/en/page"
        de = "https://example.com/de/page"
        result = assess_hreflang_cluster(
            [
                page(en, alternates=[("en", en), ("de-DE", de)]),
                page(de, alternates=[("en", en), ("de-DE", de)]),
            ]
        )
        self.assertEqual(result.state, HreflangState.HEALTHY)
        self.assertEqual(result.issues, [])
        self.assertEqual(result.unknown_targets, [])
        self.assertFalse(result.x_default_present)

    def test_missing_return_link_is_issue(self) -> None:
        en = "https://example.com/en/page"
        de = "https://example.com/de/page"
        result = assess_hreflang_cluster(
            [
                page(en, alternates=[("en", en), ("de", de)]),
                page(de, alternates=[("de", de)]),
            ]
        )
        self.assertEqual(result.state, HreflangState.ISSUES_FOUND)
        self.assertIn("return_link_missing", [item.code for item in result.issues])

    def test_missing_self_reference_is_issue(self) -> None:
        en = "https://example.com/en/page"
        de = "https://example.com/de/page"
        result = assess_hreflang_cluster(
            [
                page(en, alternates=[("de", de)]),
                page(de, alternates=[("en", en), ("de", de)]),
            ]
        )
        self.assertIn("missing_self_reference", [item.code for item in result.issues])

    def test_invalid_code_and_duplicate_targets_are_reported(self) -> None:
        en = "https://example.com/en/page"
        result = assess_hreflang_cluster(
            [
                page(
                    en,
                    alternates=[
                        ("en_US", en),
                        ("en_US", "https://example.com/en/other"),
                    ],
                )
            ]
        )
        codes = [item.code for item in result.issues]
        self.assertIn("invalid_hreflang_code", codes)
        self.assertIn("duplicate_hreflang_target", codes)

    def test_noindex_and_error_alternate_are_issues(self) -> None:
        en = "https://example.com/en/page"
        de = "https://example.com/de/page"
        result = assess_hreflang_cluster(
            [
                page(en, alternates=[("en", en), ("de", de)]),
                page(de, status=404, noindex=True, alternates=[("en", en), ("de", de)]),
            ]
        )
        codes = [item.code for item in result.issues]
        self.assertIn("alternate_not_successful", codes)
        self.assertIn("alternate_noindex", codes)

    def test_uninspected_target_keeps_insufficient_evidence(self) -> None:
        en = "https://example.com/en/page"
        de = "https://example.com/de/page"
        result = assess_hreflang_cluster(
            [page(en, alternates=[("en", en), ("de", de)])]
        )
        self.assertEqual(result.state, HreflangState.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.unknown_targets, [de])
        self.assertEqual(result.confidence, "low")

    def test_canonical_to_other_page_is_issue(self) -> None:
        en = "https://example.com/en/page"
        result = assess_hreflang_cluster(
            [page(en, canonical="https://example.com/", alternates=[("en", en)])]
        )
        self.assertIn("canonical_points_elsewhere", [item.code for item in result.issues])

    def test_x_default_is_detected_but_not_required(self) -> None:
        en = "https://example.com/en/page"
        home = "https://example.com/"
        result = assess_hreflang_cluster(
            [
                page(en, alternates=[("en", en), ("x-default", home)]),
                page(home, alternates=[("en", en), ("x-default", home)]),
            ]
        )
        self.assertTrue(result.x_default_present)
        self.assertEqual(result.state, HreflangState.HEALTHY)


    def test_issue_codes_are_typed_domain_values(self) -> None:
        en = "https://example.com/en/page"
        result = assess_hreflang_cluster([page(en, alternates=[])])
        self.assertIsInstance(result.issues[0].code, HreflangIssueCode)
        self.assertEqual(result.issues[0].code, HreflangIssueCode.HREFLANG_MISSING)

    def test_repeated_uninspected_target_is_reported_once(self) -> None:
        en = "https://example.com/en/page"
        fr = "https://example.com/fr/page"
        missing = "https://example.com/de/page"
        result = assess_hreflang_cluster(
            [
                page(en, alternates=[("en", en), ("fr", fr), ("de", missing)]),
                page(fr, alternates=[("en", en), ("fr", fr), ("de", missing)]),
            ]
        )
        self.assertEqual(result.unknown_targets, [missing])
        self.assertEqual(result.confidence, "low")

    def test_missing_alternates_does_not_fabricate_secondary_issues(self) -> None:
        en = "https://example.com/en/page"
        result = assess_hreflang_cluster([page(en, alternates=[])])
        self.assertEqual([item.code for item in result.issues], [HreflangIssueCode.HREFLANG_MISSING])

    def test_wire_contract_matches_schema_required_order(self) -> None:
        en = "https://example.com/en/page"
        payload = assess_hreflang_cluster([page(en, alternates=[("en", en)])]).to_dict()
        schema = json.loads((ROOT / "schemas" / "hreflang-assessment.v1.schema.json").read_text())
        self.assertEqual(schema["$id"], HREFLANG_SCHEMA_ID)
        self.assertEqual(tuple(payload), tuple(schema["required"]))
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
