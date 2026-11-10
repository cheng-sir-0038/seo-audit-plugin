from __future__ import annotations

import unittest

from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.provider_cost import (
    ProviderCostAdmission,
    ProviderCostConfig,
    ProviderCostGuard,
)


class ProviderCostGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = ProviderCostGuard(
            ProviderCostConfig(
                auto_multiplier_limit=1.0,
                approval_multiplier_limit=10.0,
            )
        )

    def test_standard_cost_is_auto_allowed(self) -> None:
        result = self.guard.assess(
            provider="dataforseo",
            feature="standard_serp",
            estimated_multiplier=1.0,
        )
        self.assertIs(result.admission, ProviderCostAdmission.AUTO_ALLOWED)

    def test_material_cost_requires_user_approval_but_is_not_a_provider_error(self) -> None:
        result = self.guard.assess(
            provider="dataforseo",
            feature="direct_result_urls",
            estimated_multiplier=10.0,
        )
        self.assertIs(result.admission, ProviderCostAdmission.USER_APPROVAL_REQUIRED)

    def test_hard_limit_is_non_overridable_system_policy(self) -> None:
        result = self.guard.assess(
            provider="dataforseo",
            feature="combined_paid_features",
            estimated_multiplier=100.0,
        )
        self.assertIs(result.admission, ProviderCostAdmission.BLOCKED)
        with self.assertRaises(SeoDataError) as caught:
            self.guard.require_not_blocked(result)
        self.assertEqual(caught.exception.code, "cost_limit_exceeded")


if __name__ == "__main__":
    unittest.main()
