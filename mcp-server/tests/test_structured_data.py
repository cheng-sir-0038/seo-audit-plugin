from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_seo_mcp.diagnosis.rich_results import (
    RICH_RESULT_RULES_VERSION,
    assess_rich_results,
)
from codex_seo_mcp.diagnosis.structured_data import (
    STRUCTURED_DATA_SCHEMA_ID,
    assess_structured_data,
)
from codex_seo_mcp.models.page_inspection import (
    PageInspection,
    PageStructuredDataBlock,
    PageStructuredDataNode,
)
from codex_seo_mcp.models.structured_data import (
    RichResultRuleStatus,
    RichResultState,
    StructuredDataState,
)

ROOT = Path(__file__).resolve().parents[2]


def page(*, blocks=None, status=200, noindex=False, canonical="https://example.com/p") -> PageInspection:
    return PageInspection(
        requested_url="https://example.com/p",
        final_url="https://example.com/p",
        status_code=status,
        content_type="text/html",
        content_length_bytes=100,
        redirects=[],
        title="P",
        title_count=1,
        meta_description="D",
        meta_description_count=1,
        canonical=canonical,
        canonical_count=1 if canonical else 0,
        robots_meta_tags=["noindex"] if noindex else [],
        googlebot_meta_tags=[],
        declared_noindex=noindex,
        h1=["P"],
        lang="en",
        charset="utf-8",
        meta_refresh_url=None,
        x_robots_tags=[],
        hreflang_alternates=[],
        anchor_links=[],
        rel_next_urls=[],
        rel_prev_urls=[],
        structured_data=list(blocks or []),
    )


class StructuredDataAssessmentTests(unittest.TestCase):
    def test_valid_expected_type_is_markup_present(self) -> None:
        result = assess_structured_data(page(blocks=[PageStructuredDataBlock("json_ld", True, ["Product"], None)]), expected_types=["Product"])
        self.assertEqual(result.state, StructuredDataState.MARKUP_PRESENT)
        self.assertEqual(result.observed_types, ["Product"])

    def test_invalid_json_ld_is_issue(self) -> None:
        result = assess_structured_data(page(blocks=[PageStructuredDataBlock("json_ld", False, [], "bad json")]))
        self.assertEqual(result.state, StructuredDataState.ISSUES_FOUND)
        self.assertIn("invalid_json_ld", [item.code for item in result.issues])

    def test_expected_type_missing_is_issue(self) -> None:
        result = assess_structured_data(page(blocks=[PageStructuredDataBlock("json_ld", True, ["Article"], None)]), expected_types=["Product"])
        self.assertIn("expected_schema_type_missing", [item.code for item in result.issues])

    def test_no_markup_is_not_automatically_an_error(self) -> None:
        result = assess_structured_data(page())
        self.assertEqual(result.state, StructuredDataState.NO_MARKUP)

    def test_rich_result_eligibility_stays_incomplete_without_type_rules_and_visible_content(self) -> None:
        result = assess_structured_data(page(blocks=[PageStructuredDataBlock("json_ld", True, ["Product"], None)]), expected_types=["Product"], check_rich_result_eligibility=True)
        self.assertEqual(result.state, StructuredDataState.INSUFFICIENT_EVIDENCE)
        self.assertIn("type_specific_google_requirements", result.unknowns)
        self.assertIn("visible_content_consistency", result.unknowns)

    def test_noindex_and_canonical_conflict_are_issues(self) -> None:
        result = assess_structured_data(page(blocks=[PageStructuredDataBlock("json_ld", True, ["Article"], None)], noindex=True, canonical="https://example.com/other"))
        codes=[item.code for item in result.issues]
        self.assertIn("page_noindex", codes)
        self.assertIn("canonical_points_elsewhere", codes)

    def test_wire_schema_required_order(self) -> None:
        payload=assess_structured_data(page()).to_dict()
        schema=json.loads((ROOT/"schemas"/"structured-data-assessment.v1.schema.json").read_text())
        self.assertEqual(schema["$id"], STRUCTURED_DATA_SCHEMA_ID)
        self.assertEqual(tuple(payload), tuple(schema["required"]))


class RichResultAssessmentTests(unittest.TestCase):
    def test_breadcrumb_required_properties_pass_without_claiming_google_display(self) -> None:
        block = PageStructuredDataBlock(
            "json_ld",
            True,
            ["BreadcrumbList"],
            None,
            nodes=[
                PageStructuredDataNode(
                    types=["BreadcrumbList"],
                    property_paths=[
                        "itemListElement",
                        "itemListElement[0].position",
                        "itemListElement[0].name",
                        "itemListElement[0].item",
                        "itemListElement[1].position",
                        "itemListElement[1].name",
                    ],
                )
            ],
        )

        result = assess_rich_results(page(blocks=[block]))

        self.assertEqual(result.rules_version, RICH_RESULT_RULES_VERSION)
        self.assertEqual(result.checks[0].feature, "breadcrumb")
        self.assertEqual(result.checks[0].rule_status, RichResultRuleStatus.REQUIRED_PROPERTY_PRESENCE_PASSED)
        self.assertEqual(result.checks[0].missing_required_properties, [])
        self.assertEqual(result.state, RichResultState.INSUFFICIENT_EVIDENCE)
        self.assertIn("visible_content_consistency", result.unknowns)

    def test_breadcrumb_requires_two_items_and_nonfinal_item_url(self) -> None:
        block = PageStructuredDataBlock(
            "json_ld",
            True,
            ["BreadcrumbList"],
            None,
            nodes=[
                PageStructuredDataNode(
                    types=["BreadcrumbList"],
                    property_paths=[
                        "itemListElement",
                        "itemListElement[0].position",
                        "itemListElement[0].name",
                    ],
                )
            ],
        )

        result = assess_rich_results(page(blocks=[block]))

        self.assertEqual(result.state, RichResultState.ISSUES_FOUND)
        self.assertIn("itemListElement(minItems=2)", result.checks[0].missing_required_properties)

    def test_product_snippet_requires_name_and_one_value_surface(self) -> None:
        block = PageStructuredDataBlock(
            "json_ld",
            True,
            ["Product"],
            None,
            nodes=[PageStructuredDataNode(types=["Product"], property_paths=["name"])],
        )

        result = assess_rich_results(page(blocks=[block]))

        self.assertEqual(result.state, RichResultState.ISSUES_FOUND)
        self.assertIn(
            "one_of(review,aggregateRating,offers)",
            result.checks[0].missing_required_properties,
        )

    def test_article_has_no_google_required_properties_in_current_profile(self) -> None:
        block = PageStructuredDataBlock(
            "json_ld",
            True,
            ["Article"],
            None,
            nodes=[PageStructuredDataNode(types=["Article"], property_paths=["headline", "author"])],
        )

        result = assess_rich_results(page(blocks=[block]))

        self.assertEqual(result.checks[0].rule_status, RichResultRuleStatus.NO_REQUIRED_PROPERTIES)
        self.assertIn("article_recommended_properties", result.unknowns)

    def test_unprofiled_schema_type_is_reported_without_inventing_rich_result_rules(self) -> None:
        block = PageStructuredDataBlock(
            "json_ld",
            True,
            ["Organization"],
            None,
            nodes=[PageStructuredDataNode(types=["Organization"], property_paths=["name", "url"])],
        )

        result = assess_rich_results(page(blocks=[block]))

        self.assertEqual(result.state, RichResultState.NO_SUPPORTED_MARKUP)
        self.assertEqual(result.checks[0].rule_status, RichResultRuleStatus.NOT_CHECKED)
        self.assertTrue(any("Organization" in reason for reason in result.reasons))
        self.assertFalse(any("当前 HTML 没有发现 JSON-LD" in reason for reason in result.reasons))

    def test_empty_markup_preserves_observation_and_inspection_limits(self) -> None:
        result = assess_rich_results(page())

        self.assertEqual(result.state, RichResultState.NO_SUPPORTED_MARKUP)
        self.assertEqual(result.issues, [])
        self.assertTrue(any("当前 HTML 没有发现 JSON-LD" in reason for reason in result.reasons))
        self.assertTrue(any("不一定是 SEO 错误" in reason for reason in result.reasons))
        self.assertIn("rendered_only_markup", result.unknowns)
        self.assertIn("microdata_rdfa", result.unknowns)

    def test_rich_result_enums_keep_existing_wire_values(self) -> None:
        result = assess_rich_results(page())
        payload = result.to_dict()

        self.assertIs(result.state, RichResultState.NO_SUPPORTED_MARKUP)
        self.assertEqual(payload["state"], "no_supported_markup")


if __name__ == "__main__":
    unittest.main()
