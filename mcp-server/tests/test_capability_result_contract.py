from __future__ import annotations

import unittest

from codex_seo_mcp.models.common import (
    CapabilityResult,
    CapabilitySourceKind,
    CapabilityStatus,
)


class CapabilityResultContractTests(unittest.TestCase):
    def test_complete_result_uses_typed_status_and_source_kind(self) -> None:
        result = CapabilityResult.complete(
            capability="PageInspection",
            provider="http",
            source_kind=CapabilitySourceKind.RUNTIME,
            data={"ok": True},
        )

        self.assertIs(result.status, CapabilityStatus.COMPLETE)
        self.assertIs(result.source_kind, CapabilitySourceKind.RUNTIME)
        self.assertEqual(result.to_dict()["status"], "complete")
        self.assertEqual(result.to_dict()["source_kind"], "runtime")

    def test_partial_result_normalizes_legacy_source_kind_string(self) -> None:
        result = CapabilityResult.partial(
            capability="SearchPerformance",
            provider="gsc",
            source_kind="first_party",
            data={},
        )

        self.assertIs(result.status, CapabilityStatus.PARTIAL)
        self.assertIs(result.source_kind, CapabilitySourceKind.FIRST_PARTY)
        self.assertEqual(result.status, "partial")


if __name__ == "__main__":
    unittest.main()
