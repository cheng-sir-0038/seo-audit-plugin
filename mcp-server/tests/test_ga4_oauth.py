from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_seo_mcp.auth.ga4_oauth import GA4_READONLY_SCOPE, Ga4OAuthConfig, Ga4AuthManager
from codex_seo_mcp.errors import SeoDataError


class Ga4OAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_import_preserves_local_client_file_precedence_over_env_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ga4.json"
            source.write_text(json.dumps({"token": "test-token", "refresh_token": "test-refresh",
                "client_id": "desktop-client", "client_secret": "test-secret",
                "scopes": [GA4_READONLY_SCOPE], "expiry": "2099-01-01T00:00:00Z"}))
            client = {"installed": {"client_id": "desktop-client", "client_secret": "test-secret"}}
            (root / "google-oauth-client.json").write_text(json.dumps(client))
            with patch.dict("os.environ", {"PLUGIN_DATA": str(root / "host"),
                "GOOGLE_GA4_CLIENT_ID": "env-fallback", "GOOGLE_GA4_CLIENT_SECRET": "fallback"},
                clear=True), patch("codex_seo_mcp.auth.ga4_oauth._LOCAL_TOKEN_PATH", source):
                manager = Ga4AuthManager()
                self.assertEqual(await manager.connection_status(), {"status": "connected"})
                self.assertEqual(json.loads(manager.config.client_file.read_text()), client)
                self.assertEqual(manager.config.client_file.stat().st_mode & 0o777, 0o600)

    async def test_installed_plugin_imports_matching_local_token_without_browser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "local-ga4.json"
            token = {"token": "test-token", "refresh_token": "test-refresh",
                     "client_id": "client-id", "client_secret": "test-secret",
                     "scopes": [GA4_READONLY_SCOPE], "expiry": "2099-01-01T00:00:00Z"}
            source.write_text(json.dumps(token))
            with patch.dict("os.environ", {"PLUGIN_DATA": str(root / "host"),
                            "GOOGLE_GA4_CLIENT_ID": "client-id",
                            "GOOGLE_GA4_CLIENT_SECRET": "test-secret"}, clear=True), patch(
                "codex_seo_mcp.auth.ga4_oauth._LOCAL_TOKEN_PATH", source, create=True
            ), patch("webbrowser.get") as browser:
                manager = Ga4AuthManager()
                self.assertEqual(await manager.connection_status(), {"status": "connected"})
                self.assertEqual((await manager.credentials()).token, "test-token")
                self.assertEqual(manager.config.token_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(source.read_text()), token)
                # An existing destination must win, even when the local token changes.
                source.write_text("invalid json")
                self.assertEqual(await Ga4AuthManager().connection_status(), {"status": "connected"})
                browser.assert_not_called()

    async def test_import_respects_explicit_paths_and_rejects_unrelated_tokens(self) -> None:
        for case in ("explicit_token", "explicit_root", "wrong_client", "wrong_scope", "invalid"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "local-ga4.json"
                token = {"refresh_token": "test-refresh", "client_secret": "test-secret",
                         "client_id": "other" if case == "wrong_client" else "client-id",
                         "scopes": [] if case == "wrong_scope" else [GA4_READONLY_SCOPE]}
                source.write_text("invalid" if case == "invalid" else json.dumps(token))
                env = {"PLUGIN_DATA": str(root / "host"), "GOOGLE_GA4_CLIENT_ID": "client-id",
                       "GOOGLE_GA4_CLIENT_SECRET": "test-secret"}
                if case == "explicit_token":
                    env["GA4_TOKEN_PATH"] = str(root / "explicit.json")
                if case == "explicit_root":
                    env["CODEX_SEO_DATA_DIR"] = str(root / "explicit")
                with patch.dict("os.environ", env, clear=True), patch(
                    "codex_seo_mcp.auth.ga4_oauth._LOCAL_TOKEN_PATH", source, create=True
                ):
                    manager = Ga4AuthManager()
                    self.assertEqual(await manager.connection_status(), {"status": "authorization_required"})
                    self.assertFalse(manager.config.token_path.exists())

    def test_from_env_keeps_id_secret_fallback_and_separate_ga4_token_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                "PLUGIN_DATA": temp_dir,
                "GOOGLE_GA4_CLIENT_ID": "client-id",
                "GOOGLE_GA4_CLIENT_SECRET": "client-secret",
                "GA4_OAUTH_LOOPBACK_HOST": "127.0.0.1",
                "GA4_OAUTH_TIMEOUT_SECONDS": "180",
            },
            clear=True,
        ):
            config = Ga4OAuthConfig.from_env()

        self.assertEqual(config.client_id, "client-id")
        self.assertEqual(config.client_secret, "client-secret")
        self.assertEqual(config.token_path, Path(temp_dir) / "credentials" / "ga4.json")
        self.assertEqual(config.loopback_host, "127.0.0.1")
        self.assertEqual(config.loopback_timeout_seconds, 180)
        self.assertEqual(GA4_READONLY_SCOPE, "https://www.googleapis.com/auth/analytics.readonly")

    async def test_from_env_reuses_default_desktop_client_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            client_file = data_root / "credentials" / "google-oauth-client.json"
            client_file.parent.mkdir(parents=True)
            client_file.write_text('{"installed": {}}', encoding="utf-8")
            with patch.dict("os.environ", {"PLUGIN_DATA": temp_dir}, clear=True):
                config = Ga4OAuthConfig.from_env()
                manager = Ga4AuthManager(config)

                self.assertEqual(config.client_file, client_file)
                self.assertEqual(
                    await manager.connection_status(),
                    {"status": "authorization_required"},
                )

    async def test_connection_status_is_not_configured_without_client_credentials(self) -> None:
        manager = Ga4AuthManager(
            Ga4OAuthConfig(
                client_id=None,
                client_secret=None,
                token_path=Path("/tmp/ga4-test-token.json"),
            )
        )

        self.assertEqual(await manager.connection_status(), {"status": "not_configured"})

    async def test_configured_client_without_token_requires_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = Ga4AuthManager(
                Ga4OAuthConfig(
                    client_id="client-id",
                    client_secret="client-secret",
                    token_path=Path(temp_dir) / "ga4.json",
                )
            )

            self.assertEqual(
                await manager.connection_status(),
                {"status": "authorization_required"},
            )

    async def test_credentials_without_token_never_open_browser(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = Ga4AuthManager(
                Ga4OAuthConfig(
                    client_id="client-id",
                    client_secret="client-secret",
                    token_path=Path(temp_dir) / "ga4.json",
                )
            )

            with patch("webbrowser.get") as browser:
                with self.assertRaises(SeoDataError) as caught:
                    await manager.credentials()

            self.assertEqual(caught.exception.code, "authorization_required")
            browser.assert_not_called()

    def test_cache_generation_changes_when_authorization_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "ga4.json"
            token_path.write_text("first", encoding="utf-8")
            manager = Ga4AuthManager(
                Ga4OAuthConfig(
                    client_id="client-id",
                    client_secret="client-secret",
                    token_path=token_path,
                )
            )

            first = manager.cache_generation()
            token_path.write_text("second-version", encoding="utf-8")
            second = manager.cache_generation()

        self.assertNotEqual(first, second)

    async def test_loopback_timeout_becomes_stable_public_error(self) -> None:
        from google_auth_oauthlib.flow import WSGITimeoutError

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = Ga4AuthManager(
                Ga4OAuthConfig(
                    client_id="client-id",
                    client_secret="client-secret",
                    token_path=Path(temp_dir) / "ga4.json",
                    loopback_timeout_seconds=30,
                )
            )

            with patch(
                "codex_seo_mcp.auth.google_desktop_oauth.run_google_oauth_callback",
                side_effect=WSGITimeoutError(),
            ):
                with self.assertRaises(SeoDataError) as caught:
                    await manager.authorize()

            self.assertEqual(caught.exception.code, "authorization_timeout")


if __name__ == "__main__":
    unittest.main()
