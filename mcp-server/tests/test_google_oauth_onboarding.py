from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from codex_seo_mcp.auth.google_desktop_oauth import (
    GoogleDesktopOAuthManager,
    GoogleOAuthProviderProfile,
)
from codex_seo_mcp.errors import SeoDataError


@dataclass(slots=True)
class FakeConfig:
    client_file: Path | None
    client_id: str | None
    client_secret: str | None
    token_path: Path
    loopback_host: str = "127.0.0.1"
    loopback_timeout_seconds: int = 120


PROFILE = GoogleOAuthProviderProfile(
    short_name="TEST",
    account_name="Google Test",
    scope="scope:test",
)


class GoogleOAuthOnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_desktop_client_returns_actionable_setup_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client_file = Path(tmp) / "credentials" / "google-oauth-client.json"
            manager = GoogleDesktopOAuthManager(
                FakeConfig(
                    client_file=client_file,
                    client_id=None,
                    client_secret=None,
                    token_path=Path(tmp) / "credentials" / "test.json",
                ),
                PROFILE,
            )

            status = await manager.connection_details()

        self.assertEqual(status["status"], "not_configured")
        self.assertEqual(status["next_action"], "configure_google_desktop_oauth_client")
        self.assertEqual(status["client_type"], "Desktop app")
        self.assertEqual(status["client_file"], str(client_file))
        self.assertIn("Google Cloud", status["message"])
        self.assertIn("Desktop app", status["message"])
        self.assertIn(str(client_file), status["message"])

    async def test_missing_user_token_points_to_authorization_not_manual_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client_file = Path(tmp) / "google-oauth-client.json"
            client_file.write_text("{}", encoding="utf-8")
            manager = GoogleDesktopOAuthManager(
                FakeConfig(
                    client_file=client_file,
                    client_id=None,
                    client_secret=None,
                    token_path=Path(tmp) / "test.json",
                ),
                PROFILE,
            )

            status = await manager.connection_details()

        self.assertEqual(status["status"], "authorization_required")
        self.assertEqual(status["next_action"], "authorize_google_account")
        self.assertIn("Google Test", status["message"])
        self.assertNotIn("test.json", status["message"])

    async def test_connect_without_client_uses_same_actionable_setup_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client_file = Path(tmp) / "credentials" / "google-oauth-client.json"
            manager = GoogleDesktopOAuthManager(
                FakeConfig(
                    client_file=client_file,
                    client_id=None,
                    client_secret=None,
                    token_path=Path(tmp) / "credentials" / "test.json",
                ),
                PROFILE,
            )

            with self.assertRaises(SeoDataError) as caught:
                await manager.authorize()

        self.assertEqual(caught.exception.code, "not_configured")
        self.assertIn("Google Cloud", caught.exception.message)
        self.assertIn("Desktop app", caught.exception.message)
        self.assertIn(str(client_file), caught.exception.message)


if __name__ == "__main__":
    unittest.main()
