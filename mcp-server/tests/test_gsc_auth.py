from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_seo_mcp.auth.google_oauth import (
    ConnectionStatus,
    GoogleOAuthConfig,
    GscAuthManager,
    GSC_READONLY_SCOPE,
)
from codex_seo_mcp.errors import SeoDataError


class GscAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_installed_plugin_imports_only_matching_local_consent(self) -> None:
        for case in ("matching", "existing", "explicit_token", "explicit_root",
                     "wrong_client", "wrong_scope", "invalid", "missing"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "gsc.json"
                token = {"token": "test-token", "refresh_token": "test-refresh",
                         "client_id": "other" if case == "wrong_client" else "desktop-client",
                         "client_secret": "test-secret", "expiry": "2099-01-01T00:00:00Z",
                         "scopes": [] if case == "wrong_scope" else [GSC_READONLY_SCOPE]}
                if case != "missing":
                    source.write_text("invalid" if case == "invalid" else json.dumps(token))
                original = source.read_bytes() if source.exists() else None
                client = {"installed": {"client_id": "desktop-client", "client_secret": "test-secret"}}
                (root / "google-oauth-client.json").write_text(json.dumps(client))
                target = root / "host/credentials/gsc.json"
                env = {"PLUGIN_DATA": str(root / "host"),
                       "GOOGLE_OAUTH_CLIENT_ID": "env-fallback", "GOOGLE_OAUTH_CLIENT_SECRET": "fallback"}
                if case == "existing":
                    target.parent.mkdir(parents=True)
                    target.write_text("existing consent")
                if case == "explicit_token":
                    env["GSC_TOKEN_PATH"] = str(root / "explicit.json")
                if case == "explicit_root":
                    env["CODEX_SEO_DATA_DIR"] = str(root / "explicit")
                with patch.dict("os.environ", env, clear=True), patch(
                    "codex_seo_mcp.auth.google_oauth._LOCAL_TOKEN_PATH", source, create=True
                ), patch("webbrowser.get") as browser:
                    manager = GscAuthManager()
                    if case == "matching":
                        self.assertEqual(await manager.connection_status(), {"status": "connected"})
                        self.assertEqual((await manager.credentials()).token, "test-token")
                        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                        self.assertEqual(json.loads(manager.config.client_file.read_text()), client)
                        self.assertEqual(manager.config.client_file.stat().st_mode & 0o777, 0o600)
                    elif case == "existing":
                        self.assertEqual(target.read_text(), "existing consent")
                    else:
                        self.assertFalse(manager.config.token_path.exists())
                    browser.assert_not_called()
                self.assertEqual(source.read_bytes() if source.exists() else None, original)

    async def test_reports_not_configured_without_oauth_client(self) -> None:
        """没有 OAuth Client 配置时应明确是未配置，而不是误报用户未授权。"""

        manager = GscAuthManager(
            GoogleOAuthConfig(
                client_file=None,
                client_id=None,
                client_secret=None,
                token_path=Path("unused"),
            )
        )
        self.assertEqual(
            await manager.connection_status(),
            {"status": ConnectionStatus.NOT_CONFIGURED.value},
        )

    async def test_configured_client_without_token_requires_authorization(self) -> None:
        """有应用配置但没有用户 token 时，下一步是用户授权。"""

        with tempfile.TemporaryDirectory() as tmp:
            manager = GscAuthManager(
                GoogleOAuthConfig(
                    client_file=None,
                    client_id="client-id",
                    client_secret="secret",
                    token_path=Path(tmp) / "gsc.json",
                )
            )
            self.assertEqual(
                await manager.connection_status(),
                {"status": ConnectionStatus.AUTHORIZATION_REQUIRED.value},
            )

    async def test_query_credentials_do_not_open_browser_implicitly(self) -> None:
        """数据查询缺 token 时只报 authorization_required，不应后台偷偷弹 OAuth 浏览器。"""

        with tempfile.TemporaryDirectory() as tmp:
            manager = GscAuthManager(
                GoogleOAuthConfig(
                    client_file=None,
                    client_id="client-id",
                    client_secret="secret",
                    token_path=Path(tmp) / "gsc.json",
                )
            )
            with self.assertRaises(SeoDataError) as context:
                await manager.credentials()
            self.assertEqual(context.exception.code, "authorization_required")

    async def test_desktop_client_json_is_enough_configuration(self) -> None:
        """下载的 Desktop OAuth JSON 应直接可用，不要求再拆 Client ID/Secret。"""

        with tempfile.TemporaryDirectory() as tmp:
            client_file = Path(tmp) / "google-oauth-client.json"
            client_file.write_text("{}")
            manager = GscAuthManager(
                GoogleOAuthConfig(
                    client_file=client_file,
                    client_id=None,
                    client_secret=None,
                    token_path=Path(tmp) / "gsc.json",
                )
            )
            self.assertEqual(
                await manager.connection_status(),
                {"status": ConnectionStatus.AUTHORIZATION_REQUIRED.value},
            )

    async def test_loopback_timeout_becomes_stable_public_error(self) -> None:
        """容器/远程环境收不到 localhost 回调时不能无限挂起。"""

        from google_auth_oauthlib.flow import WSGITimeoutError

        with tempfile.TemporaryDirectory() as tmp:
            manager = GscAuthManager(
                GoogleOAuthConfig(
                    client_file=None,
                    client_id="client-id",
                    client_secret="client-secret",
                    token_path=Path(tmp) / "gsc.json",
                    loopback_timeout_seconds=30,
                )
            )
            with patch(
                "codex_seo_mcp.auth.google_desktop_oauth.run_google_oauth_callback",
                side_effect=WSGITimeoutError(),
            ):
                with self.assertRaises(SeoDataError) as context:
                    await manager.authorize()
            self.assertEqual(context.exception.code, "authorization_timeout")

    def test_loopback_defaults_to_explicit_ipv4_address(self) -> None:
        """Desktop OAuth 使用 127.0.0.1，避免 localhost 地址族/防火墙差异。"""

        config = GoogleOAuthConfig(
            client_file=None,
            client_id=None,
            client_secret=None,
            token_path=Path("unused"),
        )
        self.assertEqual(config.loopback_host, "127.0.0.1")
        self.assertEqual(config.loopback_timeout_seconds, 120)
