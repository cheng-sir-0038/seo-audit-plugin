from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from codex_seo_mcp.auth.google_oauth_callback import (
    GoogleOAuthCallbackPage,
    run_google_oauth_callback,
)
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class ConnectionStatus(StrEnum):
    """Stable OAuth connection states returned across the MCP seam."""

    NOT_CONFIGURED = "not_configured"
    AUTHORIZATION_REQUIRED = "authorization_required"
    CONNECTED = "connected"
    AUTHORIZATION_EXPIRED = "authorization_expired"


class OAuthNextAction(StrEnum):
    """Stable onboarding actions; presentation text can evolve independently."""

    CONFIGURE_DESKTOP_CLIENT = "configure_google_desktop_oauth_client"
    AUTHORIZE_ACCOUNT = "authorize_google_account"
    REAUTHORIZE_ACCOUNT = "reauthorize_google_account"


@dataclass(frozen=True, slots=True)
class GoogleOAuthConnectionDetails:
    """Actionable connection state returned to an Agent Host."""

    status: ConnectionStatus
    message: str | None = None
    next_action: OAuthNextAction | None = None
    client_type: str | None = None
    client_file: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {"status": self.status.value}
        if self.message:
            payload["message"] = self.message
        if self.next_action:
            payload["next_action"] = self.next_action.value
        if self.client_type:
            payload["client_type"] = self.client_type
        if self.client_file:
            payload["client_file"] = self.client_file
        return payload


@dataclass(frozen=True, slots=True)
class GoogleOAuthProviderProfile:
    """Provider-specific facts for the shared Desktop OAuth lifecycle."""

    short_name: str
    account_name: str
    scope: str


class GoogleDesktopOAuthConfig(Protocol):
    client_id: str | None
    client_secret: str | None
    token_path: Path
    loopback_host: str
    loopback_timeout_seconds: int


class GoogleDesktopOAuthManager:
    """Shared Google installed-app OAuth lifecycle.

    The public seam is intentionally small: connection status, explicit authorization and usable
    credentials. Provider-specific managers supply configuration and a profile; token loading,
    refresh, loopback authorization, timeout mapping and secure persistence stay local here.
    """

    def __init__(
        self,
        config: GoogleDesktopOAuthConfig,
        profile: GoogleOAuthProviderProfile,
    ) -> None:
        self.config = config
        self.profile = profile
        self._lock = asyncio.Lock()

    def _import_local_token(self, local_token_path: Path) -> None:
        """Import this plugin's development consent once; never scan the user's cwd."""
        from google.oauth2.credentials import Credentials

        target = self.config.token_path
        if target.exists() or not local_token_path.is_file():
            return
        try:
            client_id = self.config.client_id
            client_file = self._client_file()
            local_client = local_token_path.with_name("google-oauth-client.json")
            client_payload = None
            if client_file is not None and client_file.is_file():
                client_id = json.loads(client_file.read_text())["installed"]["client_id"]
            elif client_file is not None and not os.getenv("GOOGLE_OAUTH_CLIENT_FILE") and local_client.is_file():
                client_payload = json.loads(local_client.read_text())
                client_id = client_payload["installed"]["client_id"]
            payload = json.loads(local_token_path.read_text())
            credentials = Credentials.from_authorized_user_info(payload)
            if not client_id or credentials.client_id != client_id or not (
                credentials.refresh_token and self.profile.scope in (credentials.scopes or ())
            ):
                return
        except (ValueError, KeyError, TypeError, AttributeError):
            # An invalid local file cannot establish consent in the installed environment.
            return

        if client_payload is not None:
            _publish_once(client_file, json.dumps(client_payload))
            # A concurrent installer may have supplied a different client; it takes priority.
            if json.loads(client_file.read_text())["installed"]["client_id"] != credentials.client_id:
                return
        _publish_once(target, credentials.to_json())

    async def connection_status(self) -> dict[str, str]:
        if not self._has_client_config():
            return {"status": ConnectionStatus.NOT_CONFIGURED.value}
        if not self.config.token_path.exists():
            return {"status": ConnectionStatus.AUTHORIZATION_REQUIRED.value}
        try:
            credentials = await asyncio.to_thread(self._load_credentials)
        except Exception:
            return {"status": ConnectionStatus.AUTHORIZATION_EXPIRED.value}
        if credentials.valid:
            return {"status": ConnectionStatus.CONNECTED.value}
        if credentials.expired and credentials.refresh_token:
            try:
                await asyncio.to_thread(self._refresh_credentials, credentials)
                return {"status": ConnectionStatus.CONNECTED.value}
            except Exception:
                return {"status": ConnectionStatus.AUTHORIZATION_EXPIRED.value}
        return {"status": ConnectionStatus.AUTHORIZATION_REQUIRED.value}

    async def connection_details(self) -> dict[str, str]:
        """Return connection state plus the next user action when setup is incomplete."""

        status = ConnectionStatus((await self.connection_status())["status"])
        if status is ConnectionStatus.NOT_CONFIGURED:
            return GoogleOAuthConnectionDetails(
                status=status,
                message=self._client_setup_message(),
                next_action=OAuthNextAction.CONFIGURE_DESKTOP_CLIENT,
                client_type="Desktop app",
                client_file=self._expected_client_file(),
            ).to_dict()
        if status is ConnectionStatus.AUTHORIZATION_REQUIRED:
            return GoogleOAuthConnectionDetails(
                status=status,
                message=self._authorization_required_message(),
                next_action=OAuthNextAction.AUTHORIZE_ACCOUNT,
            ).to_dict()
        if status is ConnectionStatus.AUTHORIZATION_EXPIRED:
            return GoogleOAuthConnectionDetails(
                status=status,
                message=f"{self.profile.short_name} 授权已失效；请重新连接 {self.profile.account_name}",
                next_action=OAuthNextAction.REAUTHORIZE_ACCOUNT,
            ).to_dict()
        return GoogleOAuthConnectionDetails(status=status).to_dict()

    async def authorize(self) -> dict[str, str]:
        """Run one explicit system-browser OAuth flow and persist the resulting token."""

        self._require_client_config()
        async with self._lock:
            try:
                credentials = await asyncio.to_thread(self._run_local_flow)
            except Exception as exc:
                from google_auth_oauthlib.flow import WSGITimeoutError

                if isinstance(exc, WSGITimeoutError):
                    raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_TIMEOUT,
                        f"{self.profile.short_name} OAuth 回调超时；请确保授权浏览器与 OAuth 进程运行在同一台主机",
                    ) from exc
                raise
        return {"status": ConnectionStatus.CONNECTED.value}

    async def credentials(self) -> Any:
        """Return usable credentials without ever starting an interactive flow implicitly."""

        self._require_client_config()
        if not self.config.token_path.exists():
            raise SeoDataError(
                SeoDataErrorCode.AUTHORIZATION_REQUIRED,
                self._authorization_required_message(),
            )

        credentials = await asyncio.to_thread(self._load_credentials)
        if credentials.valid:
            return credentials
        if credentials.expired and credentials.refresh_token:
            try:
                await asyncio.to_thread(self._refresh_credentials, credentials)
            except Exception as exc:
                raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED,
                    f"{self.profile.short_name} 授权已失效，请重新连接",
                ) from exc
            return credentials
        raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED,
            f"{self.profile.short_name} 授权不可用，请重新连接",
        )

    def _require_client_config(self) -> None:
        if not self._has_client_config():
            raise SeoDataError(SeoDataErrorCode.NOT_CONFIGURED, self._client_setup_message())

    def _expected_client_file(self) -> str:
        client_file = self._client_file()
        return str(client_file) if client_file is not None else "${PLUGIN_DATA}/credentials/google-oauth-client.json"

    def _client_setup_message(self) -> str:
        return (
            "缺少 Google Desktop OAuth Client。请在 Google Cloud Console 创建 OAuth 2.0 "
            "Client ID，Application type 选择 Desktop app；下载 JSON 后保存到 "
            f"{self._expected_client_file()}，或设置 GOOGLE_OAUTH_CLIENT_FILE 指向该文件。"
            f"配置完成后重新连接 {self.profile.account_name}。"
        )

    def _authorization_required_message(self) -> str:
        return (
            f"Google Desktop OAuth Client 已配置，但 {self.profile.short_name} 尚未授权；"
            f"请连接 {self.profile.account_name} 完成 Google 授权。"
        )

    def _has_client_config(self) -> bool:
        client_file = self._client_file()
        if client_file is not None and client_file.is_file():
            return True
        return bool(self.config.client_id and self.config.client_secret)

    def _client_file(self) -> Path | None:
        value = getattr(self.config, "client_file", None)
        return value if isinstance(value, Path) else None

    def _load_credentials(self) -> Any:
        from google.oauth2.credentials import Credentials

        return Credentials.from_authorized_user_file(
            str(self.config.token_path), [self.profile.scope]
        )

    def _refresh_credentials(self, credentials: Any) -> None:
        from google.auth.transport.requests import Request

        credentials.refresh(Request())
        self._save_credentials(credentials)

    def _run_local_flow(self) -> Any:
        from google_auth_oauthlib.flow import InstalledAppFlow

        client_file = self._client_file()
        if client_file is not None and client_file.is_file():
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_file), scopes=[self.profile.scope]
            )
        else:
            client_config = {
                "installed": {
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            flow = InstalledAppFlow.from_client_config(
                client_config, scopes=[self.profile.scope]
            )

        return run_google_oauth_callback(
            flow,
            host=self.config.loopback_host,
            timeout_seconds=self.config.loopback_timeout_seconds,
            save_credentials=self._save_credentials,
            page=GoogleOAuthCallbackPage(
                provider_name=self.profile.short_name,
                account_name=self.profile.account_name,
            ),
        )

    def _save_credentials(self, credentials: Any) -> None:
        self.config.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.token_path.write_text(credentials.to_json(), encoding="utf-8")
        try:
            os.chmod(self.config.token_path, 0o600)
        except OSError:
            pass


def _publish_once(target: Path, contents: str) -> None:
    """Publish a complete 0600 file without replacing another process's credentials."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, mode="w", encoding="utf-8") as temporary:
        temporary.write(contents)
        temporary.flush()
        try:
            os.link(temporary.name, target)
        except FileExistsError:
            pass
