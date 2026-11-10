from __future__ import annotations

import unittest

from codex_seo_mcp import models


class ModelExportTests(unittest.TestCase):
    def test_public_model_barrel_exports_stable_domain_types(self) -> None:
        expected = {
            "CapabilitySourceKind",
            "CapabilityStatus",
            "Confidence",
            "ContentLifecycleState",
            "HreflangIssueCode",
            "InternalLinksMigrationState",
            "KeywordOpportunityStatus",
            "KeywordOpportunityScenario",
            "OrganicVisibilityKeywordStatus",
            "RichResultRuleStatus",
            "RichResultState",
            "SiteMigrationCoverage",
            "SiteSafetyStatus",
            "TemplateRegressionIssueCode",
            "TemplateRegressionSeverity",
        }

        self.assertTrue(expected <= set(models.__all__))
        for name in expected:
            self.assertTrue(hasattr(models, name), name)


if __name__ == "__main__":
    unittest.main()
