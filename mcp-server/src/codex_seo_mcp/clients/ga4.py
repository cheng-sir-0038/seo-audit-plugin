from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from codex_seo_mcp.clients.ga4_admin import Ga4AdminClient
from codex_seo_mcp.clients.ga4_data import Ga4DataClient, Ga4ReportResponse
from codex_seo_mcp.clients.ga4_mapper import Ga4AdminMapper
from codex_seo_mcp.clients.ga4_transport import Ga4HttpTransport
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.provider_cache import ProviderCache


@dataclass(slots=True)
class Ga4ClientConfig:
    """Shared GA4 runtime settings used when composing Admin/Data clients."""

    data_base_url: str = "https://analyticsdata.googleapis.com/v1beta"
    admin_base_url: str = "https://analyticsadmin.googleapis.com/v1beta"
    request_timeout_seconds: float = 30.0
    cache_ttl_seconds: int = 1800

    @classmethod
    def from_env(cls) -> "Ga4ClientConfig":
        return cls(
            data_base_url=(
                os.getenv("GA4_DATA_API_BASE_URL")
                or "https://analyticsdata.googleapis.com/v1beta"
            ).rstrip("/"),
            admin_base_url=(
                os.getenv("GA4_ADMIN_API_BASE_URL")
                or "https://analyticsadmin.googleapis.com/v1beta"
            ).rstrip("/"),
            request_timeout_seconds=_float_env("GA4_REQUEST_TIMEOUT_SECONDS", 30.0),
            cache_ttl_seconds=max(0, _int_env("GA4_CACHE_TTL_SECONDS", 1800)),
        )


class Ga4RuntimeAuth(Protocol):
    async def credentials(self) -> Any: ...

    def cache_generation(self) -> str: ...

    async def connection_details(self) -> dict[str, str]: ...

    async def authorize(self) -> dict[str, str]: ...


class Ga4AdminOperations(Protocol):
    async def list_properties(self) -> list[dict[str, str]]: ...

    async def list_data_streams(self, property_id: str) -> list[dict[str, str]]: ...


class Ga4DataOperations(Protocol):
    async def run_report(
        self,
        property_id: str,
        body: dict[str, object],
    ) -> Ga4ReportResponse: ...


class Ga4Client:
    """Small GA4 facade used by the runtime.

    OAuth, Admin metadata, and Data API reports have separate owners. This facade only keeps the
    stable methods consumed by Tools and scope resolution.
    """

    def __init__(
        self,
        auth: Ga4RuntimeAuth | None = None,
        config: Ga4ClientConfig | None = None,
        cache: ProviderCache | None = None,
        *,
        admin: Ga4AdminOperations | None = None,
        data: Ga4DataOperations | None = None,
    ) -> None:
        if auth is None:
            # OAuth dependencies are only needed by the real runtime, not by pure mapper/query tests.
            from codex_seo_mcp.auth.ga4_oauth import Ga4AuthManager

            auth = Ga4AuthManager()

        self.auth = auth
        self.config = config or Ga4ClientConfig.from_env()
        self.cache = cache or ProviderCache()

        transport = Ga4HttpTransport(
            admin_base_url=self.config.admin_base_url,
            data_base_url=self.config.data_base_url,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        self.admin = admin or Ga4AdminClient(
            auth=self.auth,
            transport=transport,
            mapper=Ga4AdminMapper(),
            cache=self.cache,
            cache_ttl_seconds=self.config.cache_ttl_seconds,
        )
        self.data = data or Ga4DataClient(
            auth=self.auth,
            transport=transport,
            cache=self.cache,
            cache_ttl_seconds=self.config.cache_ttl_seconds,
        )

    async def connection_status(self) -> dict[str, str]:
        return await self.auth.connection_details()

    async def authorize(self) -> dict[str, str]:
        result = await self.auth.authorize()
        # A successful reconnect may switch Google accounts. Old GA4 cache entries are scoped only
        # by provider request, so they must not survive an authorization change.
        self.cache.clear(provider="ga4")
        return result

    async def list_properties(self) -> list[dict[str, str]]:
        return await self.admin.list_properties()

    async def list_data_streams(self, property_id: str) -> list[dict[str, str]]:
        return await self.admin.list_data_streams(_property_id(property_id))

    async def run_report(
        self,
        property_id: str,
        body: dict[str, object],
    ) -> Ga4ReportResponse:
        return await self.data.run_report(_property_id(property_id), body)


def _property_id(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("properties/"):
        text = text.split("/", 1)[1]
    if not text.isdigit():
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "GA4 property_id 必须是数字 Property ID",
        )
    return text


def _float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


__all__ = [
    "Ga4Client",
    "Ga4ClientConfig",
    "Ga4ReportResponse",
]
