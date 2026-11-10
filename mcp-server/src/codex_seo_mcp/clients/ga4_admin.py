from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from codex_seo_mcp.clients.ga4_mapper import Ga4AdminMapper
from codex_seo_mcp.clients.ga4_transport import Ga4HttpTransport
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.provider_cache import ProviderCache



class Ga4CredentialProvider(Protocol):
    async def credentials(self) -> Any: ...

    def cache_generation(self) -> str: ...


class Ga4AdminClient:
    """Read GA4 Admin metadata: accessible properties and their web data streams."""

    def __init__(
        self,
        *,
        auth: Ga4CredentialProvider,
        transport: Ga4HttpTransport,
        mapper: Ga4AdminMapper,
        cache: ProviderCache,
        cache_ttl_seconds: int,
    ) -> None:
        self.auth = auth
        self.transport = transport
        self.mapper = mapper
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds

    async def list_properties(self) -> list[dict[str, str]]:
        credentials = await self.auth.credentials()
        cache_key = {
            "auth_generation": self.auth.cache_generation(),
            "scope": "accessible_properties",
        }
        if self.cache_ttl_seconds > 0:
            cached = self.cache.get(
                provider="ga4",
                operation="list-properties",
                request_key=cache_key,
            )
            cached_rows = _cached_rows(
                cached,
                id_fields=("property_id", "account_id"),
                text_fields=("property_name", "account_name"),
            )
            if cached_rows is not None:
                return cached_rows

        properties = await asyncio.to_thread(
            self._list_all_properties_sync,
            credentials,
        )
        self.cache.set(
            provider="ga4",
            operation="list-properties",
            request_key=cache_key,
            value=properties,
            ttl_seconds=self.cache_ttl_seconds,
        )
        return properties

    async def list_data_streams(self, property_id: str) -> list[dict[str, str]]:
        credentials = await self.auth.credentials()
        cache_key = {
            "auth_generation": self.auth.cache_generation(),
            "property_id": property_id,
            # 旧缓存只保存流 ID，无法证明其所属 Property 已校验；不继续复用。
            "mapping_version": 2,
        }
        if self.cache_ttl_seconds > 0:
            cached = self.cache.get(
                provider="ga4",
                operation="list-data-streams",
                request_key=cache_key,
            )
            cached_rows = _cached_rows(
                cached,
                id_fields=("data_stream_id",),
                text_fields=("display_name", "type", "measurement_id", "default_uri"),
            )
            if cached_rows is not None:
                return cached_rows

        streams = await asyncio.to_thread(
            self._list_all_data_streams_sync,
            credentials,
            property_id,
        )
        self.cache.set(
            provider="ga4",
            operation="list-data-streams",
            request_key=cache_key,
            value=streams,
            ttl_seconds=self.cache_ttl_seconds,
        )
        return streams

    def _list_all_properties_sync(self, credentials: object) -> list[dict[str, str]]:
        properties: list[dict[str, str]] = []
        for payload in _iter_pages(
            lambda page_token: self._list_properties_page_sync(
                credentials,
                page_token=page_token,
            )
        ):
            properties.extend(self.mapper.map_properties(payload))
        return properties

    def _list_properties_page_sync(
        self,
        credentials: object,
        *,
        page_token: str | None = None,
    ) -> dict[str, object]:
        params: dict[str, object] = {"pageSize": 200}
        if page_token:
            params["pageToken"] = page_token
        return self.transport.admin_get(
            credentials,
            "/accountSummaries",
            params=params,
        )

    def _list_all_data_streams_sync(
        self,
        credentials: object,
        property_id: str,
    ) -> list[dict[str, str]]:
        streams: list[dict[str, str]] = []
        for payload in _iter_pages(
            lambda page_token: self._list_data_streams_page_sync(
                credentials,
                property_id,
                page_token=page_token,
            )
        ):
            streams.extend(self.mapper.map_data_streams(payload, property_id=property_id))
        return streams

    def _list_data_streams_page_sync(
        self,
        credentials: object,
        property_id: str,
        *,
        page_token: str | None = None,
    ) -> dict[str, object]:
        params: dict[str, object] = {"pageSize": 200}
        if page_token:
            params["pageToken"] = page_token
        return self.transport.admin_get(
            credentials,
            f"/properties/{property_id}/dataStreams",
            params=params,
        )


def _cached_rows(
    value: object,
    *,
    id_fields: tuple[str, ...],
    text_fields: tuple[str, ...],
) -> list[dict[str, str]] | None:
    """损坏的完整列表视为缓存未命中，不能只丢弃坏行而改变可访问资源范围。"""

    if not isinstance(value, list):
        return None
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        if any(not isinstance(item.get(field), str) for field in id_fields + text_fields):
            return None
        if any(not item[field].isascii() or not item[field].isdecimal() for field in id_fields):
            return None
        rows.append(dict(item))
    return rows


def _iter_pages(
    fetch_page: Callable[[str | None], dict[str, object]],
) -> Iterator[dict[str, object]]:
    """Iterate a Google pageToken/nextPageToken API without a pagination framework."""

    page_token: str | None = None
    seen_tokens: set[str] = set()
    while True:
        payload = fetch_page(page_token)
        next_page_token = payload.get("nextPageToken")
        if next_page_token is not None and not isinstance(next_page_token, str):
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                "GA4 Admin API nextPageToken 不是字符串",
            )
        # 分页标记是供应商提供的不透明字符串；不去空格，也不把错误类型当作翻页结束。
        yield payload
        if not next_page_token:
            return
        if next_page_token == page_token or next_page_token in seen_tokens:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                "GA4 Admin API 返回重复 nextPageToken，已停止分页以避免无限循环",
            )
        seen_tokens.add(next_page_token)
        page_token = next_page_token
