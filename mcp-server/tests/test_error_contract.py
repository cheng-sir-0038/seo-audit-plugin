from __future__ import annotations

import unittest

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class SeoDataErrorContractTests(unittest.TestCase):
    def test_error_code_is_typed_but_wire_value_is_stable(self) -> None:
        error = SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, "reconnect")

        self.assertIs(error.code, SeoDataErrorCode.AUTHORIZATION_REQUIRED)
        self.assertEqual(
            error.to_dict(),
            {"code": "authorization_required", "message": "reconnect"},
        )

    def test_string_error_code_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            SeoDataError("invalid_request", "bad input")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
