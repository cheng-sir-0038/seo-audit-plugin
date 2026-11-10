from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from codex_seo_mcp.diagnosis.contracts import (
    ActionCategory,
    Confidence,
    DiagnosisResult,
    Finding,
    FindingStatus,
    Hypothesis,
    HypothesisStatus,
    RankingPremiseStatus,
)
from codex_seo_mcp.diagnosis.content_lifecycle import (
    CONTENT_LIFECYCLE_SCHEMA_ID,
    assess_content_lifecycle,
)
from codex_seo_mcp.diagnosis.hreflang import HREFLANG_SCHEMA_ID, assess_hreflang_cluster
from codex_seo_mcp.diagnosis.ranking import (
    RANKING_COMPARISON_SCHEMA_ID,
    build_ranking_comparison,
)
from codex_seo_mcp.diagnosis.page_ownership import (
    PAGE_OWNERSHIP_SCHEMA_ID,
    assess_page_ownership,
)
from codex_seo_mcp.diagnosis.url_lifecycle import (
    URL_LIFECYCLE_SCHEMA_ID,
    assess_url_lifecycle,
)
from codex_seo_mcp.diagnosis.search_appearance import (
    SEARCH_APPEARANCE_SCHEMA_ID,
    assess_search_appearance,
)
from codex_seo_mcp.diagnosis.site_migration import SITE_MIGRATION_SCHEMA_ID, assess_site_migration
from codex_seo_mcp.diagnosis.structured_data import STRUCTURED_DATA_SCHEMA_ID, assess_structured_data
from codex_seo_mcp.diagnosis.template_regression import TEMPLATE_REGRESSION_SCHEMA_ID, assess_template_regression
from codex_seo_mcp.models.content_lifecycle import ContentLifecycleSignals
from codex_seo_mcp.models.page_inspection import (
    PageHreflangAlternate,
    PageInspection,
    PageRedirectHop,
    PageStructuredDataBlock,
)
from codex_seo_mcp.models.page_ownership import PageOwnershipObservation
from codex_seo_mcp.models.search_appearance import SearchAppearanceSignals
from codex_seo_mcp.models.search_performance import SearchPerformance, SearchPerformanceRow
from codex_seo_mcp.models.template_regression import TemplateSeoSnapshot

ROOT = Path(__file__).resolve().parents[2]
RANKING_SCHEMA = ROOT / "schemas" / "ranking-comparison.v1.schema.json"
PAGE_OWNERSHIP_SCHEMA = ROOT / "schemas" / "page-ownership-assessment.v1.schema.json"
URL_LIFECYCLE_SCHEMA = ROOT / "schemas" / "url-lifecycle-assessment.v1.schema.json"
CONTENT_LIFECYCLE_SCHEMA = ROOT / "schemas" / "content-lifecycle-assessment.v1.schema.json"
SEARCH_APPEARANCE_SCHEMA = ROOT / "schemas" / "search-appearance-assessment.v1.schema.json"
HREFLANG_SCHEMA = ROOT / "schemas" / "hreflang-assessment.v1.schema.json"
STRUCTURED_DATA_SCHEMA = ROOT / "schemas" / "structured-data-assessment.v1.schema.json"
SITE_MIGRATION_SCHEMA = ROOT / "schemas" / "site-migration-assessment.v1.schema.json"
TEMPLATE_REGRESSION_SCHEMA = ROOT / "schemas" / "template-regression-assessment.v1.schema.json"


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


class WireContractTests(unittest.TestCase):
    def test_diagnosis_result_has_stable_host_neutral_wire_format(self) -> None:
        """DiagnosisResult 自己就是 wire 真源，不依赖 Handoff 私有 serializer。"""

        result = DiagnosisResult(
            diagnosis_type="ranking-drop-diagnosis",
            summary="排名下降已确认",
            premise_status=RankingPremiseStatus.DECLINE_CONFIRMED,
            findings=[
                Finding(
                    type="canonical_mismatch",
                    subject="https://example.com/a",
                    status=FindingStatus.CONFIRMED,
                    confidence=Confidence.HIGH,
                    summary="Canonical 与目标页不一致",
                    rationale="最终 HTML 指向其他 URL",
                    action_category=ActionCategory.TECHNICAL,
                    source_refs=["page:1"],
                )
            ],
            hypotheses=[
                Hypothesis(
                    type="canonical-regression",
                    status=HypothesisStatus.SUPPORTED,
                    rationale="时间与页面事实一致",
                    source_refs=["page:1"],
                )
            ],
            source_refs=["gsc:1"],
        )

        payload = result.to_dict()

        self.assertEqual(
            tuple(payload),
            (
                "diagnosisType",
                "summary",
                "findings",
                "hypotheses",
                "unknowns",
                "sourceRefs",
                "premiseStatus",
            ),
        )
        self.assertEqual(payload["premiseStatus"], "decline-confirmed")
        self.assertEqual(payload["findings"][0]["actionCategory"], "technical")
        self.assertEqual(payload["hypotheses"][0]["status"], "supported")
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)

    def test_ranking_comparison_wire_format_matches_versioned_schema(self) -> None:
        """RankingComparison 必须保持 Query × Page 结构，并可被非 Python Host 校验。"""

        prior = _performance(
            "2026-07-01",
            "2026-07-31",
            [],
        )
        current = _performance(
            "2026-08-01",
            "2026-08-31",
            [
                SearchPerformanceRow(
                    query="seo tools",
                    page="https://example.com/a",
                    clicks=10,
                    impressions=100,
                    ctr=0.1,
                    position=4.0,
                ),
                SearchPerformanceRow(
                    query="seo tools",
                    page="https://example.com/b",
                    clicks=5,
                    impressions=50,
                    ctr=0.1,
                    position=8.0,
                ),
            ],
        )

        payload = build_ranking_comparison(
            prior,
            current,
            query="seo tools",
            target_page="https://example.com/a",
        ).to_dict()

        self.assertIsNone(payload["prior"])
        self.assertEqual(len(payload["pages"]), 2)
        self.assertEqual(
            payload["currentRankingPages"],
            ["https://example.com/a", "https://example.com/b"],
        )
        self.assertEqual(payload["targetPageCurrentState"], "observed")
        self.assertEqual(
            payload["priorWindow"],
            {"startDate": "2026-07-01", "endDate": "2026-07-31"},
        )

        schema = json.loads(RANKING_SCHEMA.read_text())
        self.assertEqual(schema["$id"], RANKING_COMPARISON_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)

    def test_ranking_comparison_wire_format_contains_no_presentation_contract(self) -> None:
        """Core 只提供事实结构，表格/卡片/Markdown 由 Host 决定。"""

        result = build_ranking_comparison(
            _performance("2026-07-01", "2026-07-31", []),
            _performance("2026-08-01", "2026-08-31", []),
            query="seo tools",
        ).to_dict()

        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, result)

    def test_page_ownership_wire_format_matches_versioned_schema(self) -> None:
        payload = assess_page_ownership(
            query="seo audit",
            market="US",
            observations=[
                PageOwnershipObservation(
                    url="https://example.com/a",
                    current_position=5,
                    previous_position=6,
                )
            ],
        ).to_dict()

        schema = json.loads(PAGE_OWNERSHIP_SCHEMA.read_text())
        self.assertEqual(schema["$id"], PAGE_OWNERSHIP_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)

    def test_url_lifecycle_wire_format_matches_versioned_schema(self) -> None:
        page = PageInspection(
            requested_url="https://example.com/old",
            final_url="https://example.com/new",
            status_code=200,
            content_type="text/html",
            content_length_bytes=100,
            redirects=[
                PageRedirectHop(
                    from_url="https://example.com/old",
                    status_code=301,
                    location="/new",
                    to_url="https://example.com/new",
                )
            ],
            title="Title",
            title_count=1,
            meta_description="Description",
            meta_description_count=1,
            canonical="https://example.com/new",
            canonical_count=1,
            robots_meta_tags=[],
            googlebot_meta_tags=[],
            declared_noindex=False,
            h1=["Title"],
            lang="en",
            charset="utf-8",
            meta_refresh_url=None,
            x_robots_tags=[],
            hreflang_alternates=[],
            anchor_links=[],
            rel_next_urls=[],
            rel_prev_urls=[],
            structured_data=[],
        )
        payload = assess_url_lifecycle(
            page,
            intent="permanent_move",
            expected_target="https://example.com/new",
        ).to_dict()

        schema = json.loads(URL_LIFECYCLE_SCHEMA.read_text())
        self.assertEqual(schema["$id"], URL_LIFECYCLE_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)

    def test_content_lifecycle_wire_format_matches_versioned_schema(self) -> None:
        payload = assess_content_lifecycle(
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
        ).to_dict()
        schema = json.loads(CONTENT_LIFECYCLE_SCHEMA.read_text())
        self.assertEqual(schema["$id"], CONTENT_LIFECYCLE_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)

    def test_search_appearance_wire_format_matches_versioned_schema(self) -> None:
        payload = assess_search_appearance(
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
        ).to_dict()
        schema = json.loads(SEARCH_APPEARANCE_SCHEMA.read_text())
        self.assertEqual(schema["$id"], SEARCH_APPEARANCE_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)

    def test_hreflang_wire_format_matches_versioned_schema(self) -> None:
        en = "https://example.com/en/page"
        de = "https://example.com/de/page"
        pages: list[PageInspection] = []
        for url in (en, de):
            pages.append(
                PageInspection(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    content_type="text/html",
                    content_length_bytes=100,
                    redirects=[],
                    title="Title",
                    title_count=1,
                    meta_description="Description",
                    meta_description_count=1,
                    canonical=url,
                    canonical_count=1,
                    robots_meta_tags=[],
                    googlebot_meta_tags=[],
                    declared_noindex=False,
                    h1=["Title"],
                    lang="en",
                    charset="utf-8",
                    meta_refresh_url=None,
                    x_robots_tags=[],
                    hreflang_alternates=[
                        PageHreflangAlternate("en", en, "html"),
                        PageHreflangAlternate("de", de, "html"),
                    ],
                    anchor_links=[],
                    rel_next_urls=[],
                    rel_prev_urls=[],
                    structured_data=[],
                )
            )
        payload = assess_hreflang_cluster(pages).to_dict()
        schema = json.loads(HREFLANG_SCHEMA.read_text())
        self.assertEqual(schema["$id"], HREFLANG_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)


    def test_structured_data_wire_format_matches_versioned_schema(self) -> None:
        url = "https://example.com/product"
        page = PageInspection(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            content_length_bytes=100,
            redirects=[],
            title="Product",
            title_count=1,
            meta_description="Description",
            meta_description_count=1,
            canonical=url,
            canonical_count=1,
            robots_meta_tags=[],
            googlebot_meta_tags=[],
            declared_noindex=False,
            h1=["Product"],
            lang="en",
            charset="utf-8",
            meta_refresh_url=None,
            x_robots_tags=[],
            hreflang_alternates=[],
            anchor_links=[],
            rel_next_urls=[],
            rel_prev_urls=[],
            structured_data=[
                PageStructuredDataBlock(
                    format="json_ld",
                    valid=True,
                    types=["Product"],
                    parse_error=None,
                )
            ],
        )
        payload = assess_structured_data(page, expected_types=["Product"]).to_dict()
        schema = json.loads(STRUCTURED_DATA_SCHEMA.read_text())
        self.assertEqual(schema["$id"], STRUCTURED_DATA_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)

    def test_site_migration_wire_format_matches_versioned_schema(self) -> None:
        old = "https://old.com/a"
        new = "https://new.com/a"
        page = PageInspection(
            requested_url=old,
            final_url=new,
            status_code=200,
            content_type="text/html",
            content_length_bytes=100,
            redirects=[PageRedirectHop(old, 301, new, new)],
            title="A",
            title_count=1,
            meta_description="Description",
            meta_description_count=1,
            canonical=new,
            canonical_count=1,
            robots_meta_tags=[],
            googlebot_meta_tags=[],
            declared_noindex=False,
            h1=["A"],
            lang="en",
            charset="utf-8",
            meta_refresh_url=None,
            x_robots_tags=[],
            hreflang_alternates=[],
            anchor_links=[],
            rel_next_urls=[],
            rel_prev_urls=[],
            structured_data=[],
        )
        lifecycle = assess_url_lifecycle(page, intent="permanent_move", expected_target=new)
        payload = assess_site_migration(
            [lifecycle],
            expected_mapping_count=1,
            new_sitemap_urls={new},
            hreflang_state="healthy",
        ).to_dict()
        schema = json.loads(SITE_MIGRATION_SCHEMA.read_text())
        self.assertEqual(schema["$id"], SITE_MIGRATION_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)

    def test_template_regression_wire_format_matches_versioned_schema(self) -> None:
        before = TemplateSeoSnapshot(
            url="https://example.com/p",
            status_code=200,
            final_url="https://example.com/p",
            canonical="https://example.com/p",
            declared_noindex=False,
            title="Title",
            title_count=1,
            meta_description="Description",
            h1_count=1,
            lang="en",
            hreflang_pairs=[["en", "https://example.com/p"]],
            structured_data_types=["Article"],
        )
        after = TemplateSeoSnapshot(
            url="https://example.com/p",
            status_code=200,
            final_url="https://example.com/p",
            canonical="https://example.com/p",
            declared_noindex=True,
            title="Title",
            title_count=1,
            meta_description="Description",
            h1_count=1,
            lang="en",
            hreflang_pairs=[["en", "https://example.com/p"]],
            structured_data_types=["Article"],
        )
        payload = assess_template_regression([(before, after)]).to_dict()
        schema = json.loads(TEMPLATE_REGRESSION_SCHEMA.read_text())
        self.assertEqual(schema["$id"], TEMPLATE_REGRESSION_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        for presentation_key in ("markdown", "html", "table", "view", "recommendedView"):
            self.assertNotIn(presentation_key, payload)


if __name__ == "__main__":
    unittest.main()
