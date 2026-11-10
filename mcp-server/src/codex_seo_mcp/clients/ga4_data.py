from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from codex_seo_mcp.clients.ga4_transport import Ga4HttpTransport
from codex_seo_mcp.provider_cache import ProviderCache



class Ga4CredentialProvider(Protocol):
    async def credentials(self) -> Any: ...

    def cache_generation(self) -> str: ...


@dataclass(slots=True)
class Ga4ReportResponse:
    payload: dict[str, object]


class Ga4DataClient:
    """Read GA4 Data API reports and keep identical requests in the short-lived cache."""

    def __init__(
        self,
        *,
        auth: Ga4CredentialProvider,
        transport: Ga4HttpTransport,
        cache: ProviderCache,
        cache_ttl_seconds: int,
    ) -> None:
        self.auth = auth
        self.transport = transport
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds

    async def run_report(
        self,
        property_id: str,
        body: dict[str, object],
    ) -> Ga4ReportResponse:
        credentials = await self.auth.credentials()
        cache_key = {
            "auth_generation": self.auth.cache_generation(),
            "property_id": property_id,
            "body": body,
        }
        # TTL 为零时连已有缓存也不能读取，但当前授权仍必须先通过校验。
        if self.cache_ttl_seconds > 0:
            cached = self.cache.get(
                provider="ga4",
                operation="run-report",
                request_key=cache_key,
            )
            if isinstance(cached, dict):
                return Ga4ReportResponse(payload=cached)

        payload = await asyncio.to_thread(
            self.transport.data_post,
            credentials,
            f"/properties/{property_id}:runReport",
            body=body,
        )
        self.cache.set(
            provider="ga4",
            operation="run-report",
            request_key=cache_key,
            value=payload,
            ttl_seconds=self.cache_ttl_seconds,
        )
        return Ga4ReportResponse(payload=payload)
