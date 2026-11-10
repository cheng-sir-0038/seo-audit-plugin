from __future__ import annotations

import unittest

from codex_seo_mcp.diagnosis.contracts import Confidence as ContractConfidence
from codex_seo_mcp.diagnosis.site_migration import assess_site_migration
from codex_seo_mcp.diagnosis.template_regression import assess_template_regression
from codex_seo_mcp.models.common import Confidence


class SharedConfidenceTests(unittest.TestCase):
    def test_diagnosis_contract_reexports_model_confidence(self) -> None:
        self.assertIs(ContractConfidence, Confidence)

    def test_assessments_use_shared_confidence_enum(self) -> None:
        self.assertIsInstance(assess_template_regression([]).confidence, Confidence)
        self.assertIsInstance(assess_site_migration([]).confidence, Confidence)


if __name__ == "__main__":
    unittest.main()
