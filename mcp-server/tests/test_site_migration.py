from __future__ import annotations

import json
import unittest
from pathlib import Path

from codex_seo_mcp.diagnosis.site_migration import SITE_MIGRATION_SCHEMA_ID, assess_site_migration
from codex_seo_mcp.diagnosis.url_lifecycle import assess_url_lifecycle
from codex_seo_mcp.models.page_inspection import PageInspection, PageRedirectHop
from codex_seo_mcp.models.hreflang import HreflangState
from codex_seo_mcp.models.site_migration import (
    InternalLinksMigrationState,
    SiteMigrationCoverage,
    SiteMigrationState,
)
from codex_seo_mcp.models.url_lifecycle import (
    CanonicalState,
    RedirectState,
    TargetState,
    UrlLifecycleState,
)

ROOT = Path(__file__).resolve().parents[2]


def lifecycle(old: str, new: str, *, code: int = 301, canonical: str | None = None, wrong: str | None = None):
    final = wrong or new
    page = PageInspection(
        requested_url=old,
        final_url=final,
        status_code=200,
        content_type="text/html",
        content_length_bytes=100,
        redirects=[PageRedirectHop(old, code, final, final)],
        title="T",
        title_count=1,
        meta_description="D",
        meta_description_count=1,
        canonical=canonical if canonical is not None else final,
        canonical_count=1,
        robots_meta_tags=[],
        googlebot_meta_tags=[],
        declared_noindex=False,
        h1=["T"],
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
    return assess_url_lifecycle(page, intent="permanent_move", expected_target=new)


class SiteMigrationAssessmentTests(unittest.TestCase):
    def test_full_mapping_pass_requires_complete_coverage_and_supporting_evidence(self) -> None:
        a=lifecycle("https://old.com/a","https://new.com/a")
        b=lifecycle("https://old.com/b","https://new.com/b")
        result=assess_site_migration(
            [a,b],
            expected_mapping_count=2,
            new_sitemap_urls={"https://new.com/a","https://new.com/b"},
            internal_links_state=InternalLinksMigrationState.UPDATED,
            hreflang_state=HreflangState.HEALTHY,
        )
        self.assertEqual(result.state, SiteMigrationState.PASSED)
        self.assertEqual(result.coverage, SiteMigrationCoverage.COMPLETE)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.mappings[0].lifecycle_state, UrlLifecycleState.HEALTHY)
        self.assertEqual(result.mappings[0].target_state, TargetState.MATCHED)
        self.assertEqual(result.mappings[0].redirect_state, RedirectState.DIRECT_PERMANENT)
        self.assertEqual(result.mappings[0].canonical_state, CanonicalState.FINAL_URL)

    def test_samples_never_become_full_site_pass_without_mapping_count(self) -> None:
        result=assess_site_migration(
            [lifecycle("https://old.com/a","https://new.com/a")],
            new_sitemap_urls={"https://new.com/a"},
            internal_links_state=InternalLinksMigrationState.UPDATED,
            hreflang_state=HreflangState.HEALTHY,
        )
        self.assertEqual(result.state, SiteMigrationState.SAMPLE_PASSED)
        self.assertIn("full_mapping_count", result.unknowns)

    def test_misconfigured_url_fails_migration(self) -> None:
        result=assess_site_migration(
            [lifecycle("https://old.com/a","https://new.com/a",wrong="https://new.com/wrong")],
            expected_mapping_count=1,
            new_sitemap_urls={"https://new.com/a"},
            internal_links_state=InternalLinksMigrationState.UPDATED,
            hreflang_state=HreflangState.HEALTHY,
        )
        self.assertEqual(result.state, SiteMigrationState.FAILED)
        self.assertGreater(result.failed_mappings,0)

    def test_temporary_redirect_needs_attention(self) -> None:
        result=assess_site_migration(
            [lifecycle("https://old.com/a","https://new.com/a",code=302)],
            expected_mapping_count=1,
            new_sitemap_urls={"https://new.com/a"},
            internal_links_state=InternalLinksMigrationState.UPDATED,
            hreflang_state=HreflangState.HEALTHY,
        )
        self.assertEqual(result.state, SiteMigrationState.NEEDS_ATTENTION)

    def test_missing_new_sitemap_target_needs_attention(self) -> None:
        result=assess_site_migration(
            [lifecycle("https://old.com/a","https://new.com/a")],
            expected_mapping_count=1,
            new_sitemap_urls=set(),
            internal_links_state=InternalLinksMigrationState.UPDATED,
            hreflang_state=HreflangState.HEALTHY,
        )
        self.assertEqual(result.state, SiteMigrationState.NEEDS_ATTENTION)
        self.assertEqual(result.attention_mappings, 0)
        self.assertIn("mapped_targets_missing_from_new_sitemap", result.issue_codes)

    def test_multilingual_hreflang_issue_is_visible(self) -> None:
        result=assess_site_migration(
            [lifecycle("https://old.com/a","https://new.com/a")],
            expected_mapping_count=1,
            new_sitemap_urls={"https://new.com/a"},
            internal_links_state=InternalLinksMigrationState.UPDATED,
            multilingual=True,
            hreflang_state=HreflangState.ISSUES_FOUND,
        )
        self.assertEqual(result.state, SiteMigrationState.NEEDS_ATTENTION)
        self.assertIn("hreflang_migration_issues", result.issue_codes)



    def test_complete_mapping_without_internal_link_evidence_is_insufficient(self) -> None:
        result=assess_site_migration(
            [lifecycle("https://old.com/a","https://new.com/a")],
            expected_mapping_count=1,
            new_sitemap_urls={"https://new.com/a"},
        )
        self.assertEqual(result.state, SiteMigrationState.INSUFFICIENT_EVIDENCE)
        self.assertIn("internal_link_migration", result.unknowns)

    def test_multilingual_full_mapping_without_hreflang_evidence_is_insufficient(self) -> None:
        result=assess_site_migration(
            [lifecycle("https://old.com/a","https://new.com/a")],
            expected_mapping_count=1,
            new_sitemap_urls={"https://new.com/a"},
            internal_links_state=InternalLinksMigrationState.UPDATED,
            multilingual=True,
        )
        self.assertEqual(result.state, SiteMigrationState.INSUFFICIENT_EVIDENCE)
        self.assertIn("hreflang_migration", result.unknowns)

    def test_no_mapping_evidence_is_insufficient(self) -> None:
        result=assess_site_migration([])
        self.assertEqual(result.state, SiteMigrationState.INSUFFICIENT_EVIDENCE)

    def test_wire_schema_required_order(self) -> None:
        payload=assess_site_migration([]).to_dict()
        schema=json.loads((ROOT/"schemas"/"site-migration-assessment.v1.schema.json").read_text())
        self.assertEqual(schema["$id"], SITE_MIGRATION_SCHEMA_ID)
        self.assertEqual(tuple(payload), tuple(schema["required"]))


if __name__ == "__main__":
    unittest.main()
