from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from codex_seo_mcp.auth.google_desktop_oauth import (
    GoogleDesktopOAuthManager,
    GoogleOAuthProviderProfile,
)
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode

GA4_READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
_LOCAL_TOKEN_PATH = Path(__file__).resolve().parents[4] / ".local/credentials/ga4.json"


@dataclass(slots=True)
class Ga4OAuthConfig:
    """GA4 Desktop OAuth configuration kept separate from GSC credentials."""

    client_id: str | None
    client_secret: str | None
    token_path: Path
    client_file: Path | None = None
    loopback_host: str = "127.0.0.1"
    loopback_timeout_seconds: int = 120

    @classmethod
    def from_env(cls) -> "Ga4OAuthConfig":
        data_root = Path(os.getenv("CODEX_SEO_DATA_DIR") or os.getenv("PLUGIN_DATA") or ".local")
        client_file = Path(
            os.getenv("GOOGLE_OAUTH_CLIENT_FILE")
            or data_root / "credentials" / "google-oauth-client.json"
        )
        return cls(
            client_id=(os.getenv("GOOGLE_GA4_CLIENT_ID") or "").strip() or None,
            client_secret=(os.getenv("GOOGLE_GA4_CLIENT_SECRET") or "").strip() or None,
            token_path=Path(os.getenv("GA4_TOKEN_PATH") or data_root / "credentials" / "ga4.json"),
            client_file=client_file,
            loopback_host=(os.getenv("GA4_OAUTH_LOOPBACK_HOST") or "127.0.0.1").strip(),
            loopback_timeout_seconds=max(30, int(os.getenv("GA4_OAUTH_TIMEOUT_SECONDS") or "120")),
        )


_GA4_PROFILE = GoogleOAuthProviderProfile(
    short_name="GA4",
    account_name="Google Analytics",
    scope=GA4_READONLY_SCOPE,
)


class Ga4AuthManager(GoogleDesktopOAuthManager):
    """GA4-specific configuration for the shared Google Desktop OAuth lifecycle."""

    def __init__(self, config: Ga4OAuthConfig | None = None) -> None:
        super().__init__(config or Ga4OAuthConfig.from_env(), _GA4_PROFILE)
        if config is None and os.getenv("PLUGIN_DATA") and not (
            os.getenv("GA4_TOKEN_PATH") or os.getenv("CODEX_SEO_DATA_DIR")
        ):
            self._import_local_token(_LOCAL_TOKEN_PATH)

    def cache_generation(self) -> str:
        """Return a non-secret generation for isolating cached data across reconnects."""

        try:
            stat = self.config.token_path.stat()
        except OSError as exc:
            raise SeoDataError(
                SeoDataErrorCode.AUTHORIZATION_REQUIRED,
                "GA4 授权文件不可用，请重新连接",
            ) from exc
        return (
            f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:"
            f"{stat.st_mtime_ns}:{stat.st_ctime_ns}"
        )
