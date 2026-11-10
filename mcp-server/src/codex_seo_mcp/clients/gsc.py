from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from codex_seo_mcp.auth.google_oauth import GscAuthManager
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


@dataclass(slots=True)
class GscQueryResponse:
    """GSC Search Analytics 原始响应外壳，避免 Client 直接承担领域映射。"""

    payload: dict[str, object]


@dataclass(slots=True)
class GscInspectionResponse:
    """GSC URL Inspection 原始响应外壳。"""

    payload: dict[str, object]


class GscClient:
    """Google Search Console API Client。

    Client 只负责 OAuth 凭据和 Google API 调用，不决定 Ranking Drop、Target Page 等
    SEO 业务语义；这些判断属于 SearchPerformance Adapter / Product Skill 上层。
    """

    def __init__(self, auth: GscAuthManager | None = None) -> None:
        self.auth = auth or GscAuthManager()

    async def connection_status(self) -> dict[str, str]:
        return await self.auth.connection_details()

    async def authorize(self) -> dict[str, str]:
        return await self.auth.authorize()

    async def list_properties(self) -> list[dict[str, str]]:
        credentials = await self.auth.credentials()
        return await asyncio.to_thread(self._list_properties_sync, credentials)

    async def resolve_properties_for_target(
        self, target: str
    ) -> list[dict[str, str]]:
        """Resolve a user domain/URL to accessible Search Console Properties.

        A bare domain prefers the most specific matching domain Property. An explicit URL prefers
        the most specific covering URL-prefix Property, falling back to a covering domain Property.
        Multiple equally valid results are preserved so the Product Skill can ask the user.
        """

        properties = await self.list_properties()
        return _resolve_properties(properties, target)

    async def query(
        self, property_url: str, body: dict[str, object]
    ) -> GscQueryResponse:
        credentials = await self.auth.credentials()
        payload = await asyncio.to_thread(
            self._query_sync, credentials, property_url, body
        )
        return GscQueryResponse(payload=payload)

    async def inspect_url(
        self,
        *,
        property_url: str,
        inspection_url: str,
        language_code: str = "en-US",
    ) -> GscInspectionResponse:
        credentials = await self.auth.credentials()
        payload = await asyncio.to_thread(
            self._inspect_url_sync,
            credentials,
            property_url,
            inspection_url,
            language_code,
        )
        return GscInspectionResponse(payload=payload)

    @staticmethod
    def _build_service(credentials: Any) -> Any:
        from googleapiclient.discovery import build

        # Search Console 官方 Python quickstart 使用 searchconsole/v1。
        return build(
            "searchconsole",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

    def _list_properties_sync(self, credentials: Any) -> list[dict[str, str]]:
        try:
            payload = self._build_service(credentials).sites().list().execute()
        except Exception as exc:
            raise _map_google_error(exc) from exc
        entries = payload.get("siteEntry") or []
        return [
            {
                "property_url": str(item.get("siteUrl") or ""),
                "permission_level": str(item.get("permissionLevel") or ""),
            }
            for item in entries
            if isinstance(item, dict) and item.get("siteUrl")
        ]

    def _query_sync(
        self, credentials: Any, property_url: str, body: dict[str, object]
    ) -> dict[str, object]:
        try:
            payload = (
                self._build_service(credentials)
                .searchanalytics()
                .query(siteUrl=property_url, body=body)
                .execute()
            )
        except Exception as exc:
            raise _map_google_error(exc) from exc
        if not isinstance(payload, dict):
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "GSC 返回结构无效")
        return payload

    def _inspect_url_sync(
        self,
        credentials: Any,
        property_url: str,
        inspection_url: str,
        language_code: str,
    ) -> dict[str, object]:
        body = {
            "inspectionUrl": inspection_url,
            "siteUrl": property_url,
            "languageCode": language_code,
        }
        try:
            payload = (
                self._build_service(credentials)
                .urlInspection()
                .index()
                .inspect(body=body)
                .execute()
            )
        except Exception as exc:
            raise _map_google_error(exc) from exc
        if not isinstance(payload, dict):
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "GSC URL Inspection 返回结构无效")
        return payload



def _resolve_properties(
    properties: list[dict[str, str]], target: str
) -> list[dict[str, str]]:
    raw_target = str(target or "").strip()
    if not raw_target:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GSC target 不能为空")

    if "://" in raw_target:
        target_url = _normalized_url(raw_target)
        target_host = (urlsplit(target_url).hostname or "").lower()
        if not target_host:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GSC target 必须包含有效主机名")

        prefix_matches: list[tuple[int, dict[str, str]]] = []
        for item in properties:
            property_url = str(item.get("property_url") or "").strip()
            if property_url.startswith("sc-domain:"):
                continue
            normalized_property = _normalized_url(property_url)
            if target_url.startswith(normalized_property):
                prefix_matches.append((len(normalized_property), item))
        if prefix_matches:
            max_length = max(length for length, _ in prefix_matches)
            return [item for length, item in prefix_matches if length == max_length]

        return _most_specific_domain_properties(properties, target_host)

    target_host = _normalized_host(raw_target)
    domain_matches = _most_specific_domain_properties(properties, target_host)
    if domain_matches:
        return domain_matches

    prefix_matches: list[dict[str, str]] = []
    for item in properties:
        property_url = str(item.get("property_url") or "").strip()
        if property_url.startswith("sc-domain:"):
            continue
        host = (urlsplit(_normalized_url(property_url)).hostname or "").lower()
        if host == target_host or host.endswith(f".{target_host}"):
            prefix_matches.append(item)
    return prefix_matches


def _most_specific_domain_properties(
    properties: list[dict[str, str]], target_host: str
) -> list[dict[str, str]]:
    matches: list[tuple[int, dict[str, str]]] = []
    for item in properties:
        property_url = str(item.get("property_url") or "").strip()
        if not property_url.startswith("sc-domain:"):
            continue
        domain = _normalized_host(property_url.removeprefix("sc-domain:"))
        if target_host == domain or target_host.endswith(f".{domain}"):
            matches.append((len(domain), item))
    if not matches:
        return []
    max_length = max(length for length, _ in matches)
    return [item for length, item in matches if length == max_length]


def _normalized_host(value: str) -> str:
    candidate = value if "://" in value else f"https://{value}"
    host = (urlsplit(candidate).hostname or "").lower().rstrip(".")
    if not host:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GSC target 必须包含有效主机名")
    return host


def _normalized_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GSC URL-prefix 必须是有效 HTTP/HTTPS URL")
    netloc = parsed.hostname.lower()
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))

def _map_google_error(exc: Exception) -> SeoDataError:
    """把 Google Client Library 异常压缩成公共错误语义。"""

    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 400:
        return SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GSC 请求参数无效")
    if status == 401:
        return SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, "GSC 授权已失效，请重新连接")
    if status == 403:
        return SeoDataError(SeoDataErrorCode.PERMISSION_DENIED,
            "GSC 请求被拒绝，请检查 Property 权限和 Search Console API 配置",
        )
    if status == 429:
        return SeoDataError(SeoDataErrorCode.QUOTA_EXCEEDED, "GSC API 配额或请求频率已达限制")
    return SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "GSC API 请求失败")
