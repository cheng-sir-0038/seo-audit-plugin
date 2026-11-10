from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_seo_mcp.diagnosis.template_regression import TEMPLATE_REGRESSION_SCHEMA_ID, assess_template_regression, snapshot_from_page_inspection
from codex_seo_mcp.models.page_inspection import PageHreflangAlternate, PageInspection, PageStructuredDataBlock
from codex_seo_mcp.models.template_regression import (
    TemplateRegressionSeverity,
    TemplateRegressionState,
    TemplateSeoSnapshot,
)

ROOT = Path(__file__).resolve().parents[2]


def snap(url="https://example.com/p", **kwargs):
    data=dict(
        url=url,
        status_code=200,
        final_url=url,
        canonical=url,
        declared_noindex=False,
        title="Title",
        title_count=1,
        meta_description="Description",
        h1_count=1,
        lang="en",
        hreflang_pairs=[("en",url)],
        structured_data_types=["Article"],
    )
    data.update(kwargs)
    return TemplateSeoSnapshot(**data)


class TemplateRegressionTests(unittest.TestCase):

    def test_snapshot_from_page_inspection_uses_current_contract(self) -> None:
        url="https://example.com/p"
        page=PageInspection(
            requested_url=url, final_url=url, status_code=200, content_type="text/html",
            content_length_bytes=100, redirects=[], title="Title", title_count=1,
            meta_description="Description", meta_description_count=1, canonical=url, canonical_count=1,
            robots_meta_tags=[], googlebot_meta_tags=[], declared_noindex=False, h1=["Title"],
            lang="en", charset="utf-8", meta_refresh_url=None, x_robots_tags=[],
            hreflang_alternates=[PageHreflangAlternate("en",url,"html")],
            anchor_links=[], rel_next_urls=[], rel_prev_urls=[],
            structured_data=[PageStructuredDataBlock("json_ld",True,["Article"],None)],
        )
        snapshot=snapshot_from_page_inspection(page)
        self.assertEqual(snapshot.hreflang_pairs, [("en",url)])
        self.assertEqual(snapshot.structured_data_types, ["Article"])

    def test_stable_samples_are_stable(self) -> None:
        result=assess_template_regression([(snap(),snap())])
        self.assertEqual(result.state, TemplateRegressionState.STABLE)
        self.assertEqual(result.regression_pages,0)

    def test_noindex_introduced_is_high_regression(self) -> None:
        result=assess_template_regression([(snap(),snap(declared_noindex=True))])
        self.assertEqual(result.state, TemplateRegressionState.REGRESSION_DETECTED)
        self.assertIn("noindex_introduced", [i.code for i in result.issues])

    def test_status_regression_is_detected(self) -> None:
        result=assess_template_regression([(snap(),snap(status_code=500))])
        self.assertIn("status_regression", [i.code for i in result.issues])

    def test_canonical_change_is_detected(self) -> None:
        result=assess_template_regression([(snap(),snap(canonical="https://example.com/other"))])
        self.assertIn("canonical_changed", [i.code for i in result.issues])

    def test_title_wording_change_is_changed_not_automatic_regression(self) -> None:
        result=assess_template_regression([(snap(),snap(title="New title"))])
        self.assertEqual(result.state, TemplateRegressionState.CHANGED)
        self.assertEqual(result.regression_pages,0)

    def test_hreflang_removal_is_regression(self) -> None:
        result=assess_template_regression([(snap(),snap(hreflang_pairs=[]))])
        self.assertIn("hreflang_removed", [i.code for i in result.issues])

    def test_structured_data_type_removal_is_regression(self) -> None:
        result=assess_template_regression([(snap(),snap(structured_data_types=[]))])
        self.assertIn("structured_data_type_removed", [i.code for i in result.issues])

    def test_empty_input_is_insufficient(self) -> None:
        result=assess_template_regression([])
        self.assertEqual(result.state, TemplateRegressionState.INSUFFICIENT_EVIDENCE)


    def test_title_structure_regression_preserves_medium_severity(self) -> None:
        result=assess_template_regression([(snap(),snap(title_count=0,title=None))])
        issue=next(item for item in result.issues if item.code == "title_structure_regression")
        self.assertEqual(issue.severity, TemplateRegressionSeverity.MEDIUM)
        self.assertEqual(result.state, TemplateRegressionState.REGRESSION_DETECTED)

    def test_description_and_h1_removal_are_regressions(self) -> None:
        result=assess_template_regression([(snap(),snap(meta_description=None,h1_count=0))])
        codes=[item.code for item in result.issues]
        self.assertIn("description_removed", codes)
        self.assertIn("h1_removed", codes)
        self.assertEqual(result.state, TemplateRegressionState.REGRESSION_DETECTED)

    def test_lang_change_is_changed_but_not_automatic_regression(self) -> None:
        result=assess_template_regression([(snap(),snap(lang="de"))])
        self.assertEqual(result.state, TemplateRegressionState.CHANGED)
        self.assertIn("lang_changed", [item.code for item in result.issues])
        self.assertEqual(result.regression_pages, 0)

    def test_hreflang_reduction_and_final_url_change_are_preserved(self) -> None:
        before=snap(hreflang_pairs=[("en","https://example.com/p"),("de","https://example.com/de/p")])
        after=snap(hreflang_pairs=[("en","https://example.com/p")],final_url="https://example.com/new")
        result=assess_template_regression([(before,after)])
        codes=[item.code for item in result.issues]
        self.assertIn("hreflang_reduced", codes)
        self.assertIn("final_url_changed", codes)

    def test_missing_status_and_robots_remain_unknown_evidence(self) -> None:
        result=assess_template_regression([(snap(status_code=None,declared_noindex=None),snap(status_code=None,declared_noindex=None))])
        self.assertIn("status:https://example.com/p", result.unknowns)
        self.assertIn("robots:https://example.com/p", result.unknowns)
        self.assertEqual(result.confidence, "medium")

    def test_wire_schema_required_order(self) -> None:
        payload=assess_template_regression([(snap(),snap())]).to_dict()
        schema=json.loads((ROOT/"schemas"/"template-regression-assessment.v1.schema.json").read_text())
        self.assertEqual(schema["$id"], TEMPLATE_REGRESSION_SCHEMA_ID)
        self.assertEqual(tuple(payload), tuple(schema["required"]))


if __name__ == "__main__":
    unittest.main()
