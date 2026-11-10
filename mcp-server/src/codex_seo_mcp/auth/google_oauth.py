from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from codex_seo_mcp.auth.google_desktop_oauth import (
    ConnectionStatus,
    GoogleDesktopOAuthManager,
    GoogleOAuthProviderProfile,
)

GSC_READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
_LOCAL_TOKEN_PATH = Path(__file__).resolve().parents[4] / ".local/credentials/gsc.json"


@dataclass(slots=True)
class GoogleOAuthConfig:
    """GSC Desktop OAuth configuration.

    OAuth client configuration identifies the installed application. The user token is a separate
    credential and stays under `.local`/PLUGIN_DATA instead of source-controlled configuration.
    """

    client_file: Path | None
    client_id: str | None
    client_secret: str | None
    token_path: Path
    loopback_host: str = "127.0.0.1"
    loopback_timeout_seconds: int = 120

    @classmethod
    def from_env(cls) -> "GoogleOAuthConfig":
        data_root = Path(
            os.getenv("CODEX_SEO_DATA_DIR")
            or os.getenv("PLUGIN_DATA")
            or ".local"
        )
        token_path = Path(
            os.getenv("GSC_TOKEN_PATH")
            or data_root / "credentials" / "gsc.json"
        )
        client_file = Path(
            os.getenv("GOOGLE_OAUTH_CLIENT_FILE")
            or data_root / "credentials" / "google-oauth-client.json"
        )
        return cls(
            client_file=client_file,
            client_id=(os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip() or None,
            client_secret=(os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip() or None,
            token_path=token_path,
            loopback_host=(os.getenv("GSC_OAUTH_LOOPBACK_HOST") or "127.0.0.1").strip(),
            loopback_timeout_seconds=max(
                30,
                int(os.getenv("GSC_OAUTH_TIMEOUT_SECONDS") or "120"),
            ),
        )


_GSC_PROFILE = GoogleOAuthProviderProfile(
    short_name="GSC",
    account_name="Google Search Console",
    scope=GSC_READONLY_SCOPE,
)


class GscAuthManager(GoogleDesktopOAuthManager):
    """GSC-specific configuration for the shared Google Desktop OAuth lifecycle."""

    def __init__(self, config: GoogleOAuthConfig | None = None) -> None:
        super().__init__(config or GoogleOAuthConfig.from_env(), _GSC_PROFILE)
        if config is None and os.getenv("PLUGIN_DATA") and not (
            os.getenv("GSC_TOKEN_PATH") or os.getenv("CODEX_SEO_DATA_DIR")
        ):
            self._import_local_token(_LOCAL_TOKEN_PATH)
