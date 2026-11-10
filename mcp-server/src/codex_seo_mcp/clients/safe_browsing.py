from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.provider_cache import ProviderCache

_DEFAULT_API_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
_THREAT_TYPES = (
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
    "POTENTIALLY_HARMFUL_APPLICATION",
)


@dataclass(slots=True)
class SafeBrowsingConfig:
    """Google Safe Browsing lookup configuration.

    Safe Browsing is currently used only for personal/non-commercial SiteSafety checks. Commercial
    distribution must keep the SiteSafety contract and replace this Provider with Web Risk.
    """

    api_url: str = _DEFAULT_API_URL
    api_key: str | None = None
    timeout_seconds: float = 15.0
    cache_max_ttl_seconds: int = 86400

    @classmethod
    def from_env(cls) -> "SafeBrowsingConfig":
        return cls(
            api_url=(os.getenv("SAFE_BROWSING_API_BASE_URL") or _DEFAULT_API_URL).strip()
            or _DEFAULT_API_URL,
            api_key=(os.getenv("SAFE_BROWSING_API_KEY") or "").strip() or None,
            timeout_seconds=_float_env("SAFE_BROWSING_REQUEST_TIMEOUT", 15.0),
            cache_max_ttl_seconds=max(
                0,
                _int_env("SAFE_BROWSING_CACHE_MAX_TTL_SECONDS", 86400),
            ),
        )


@dataclass(slots=True)
class SafeBrowsingResponse:
    """Normalized Safe Browsing lookup response consumed by the SiteSafety adapter."""

    payload: dict[str, object]
    requested_url: str | None = None


class SafeBrowsingClient:
    """Thin Safe Browsing JSON lookup client with short-lived response caching."""

    def __init__(
        self,
        config: SafeBrowsingConfig | None = None,
        cache: ProviderCache | None = None,
    ) -> None:
        self.config = config or SafeBrowsingConfig.from_env()
        self.cache = cache or ProviderCache()

    async def search_url(self, url: str) -> SafeBrowsingResponse:
        target = _normalize_public_url(url)
        if not self.config.api_key:
            raise SeoDataError(
                SeoDataErrorCode.NOT_CONFIGURED,
                "缺少 SAFE_BROWSING_API_KEY；请先为当前 Google Cloud Project 启用 Safe Browsing API",
            )

        request_key = {"url": target}
        # TTL 为零同时关闭读取；不能只停写缓存却继续返回之前保存的结果。
        if self.config.cache_max_ttl_seconds > 0:
            cached = self.cache.get(
                provider="google-safe-browsing-v4",
                operation="url-search",
                request_key=request_key,
            )
            if isinstance(cached, dict):
                return SafeBrowsingResponse(payload=cached, requested_url=target)

        response = await asyncio.to_thread(self._request_sync, target)
        normalized = _normalize_lookup_payload(response.payload)
        ttl_seconds = _response_cache_ttl_seconds(
            response.payload,
            max_ttl_seconds=self.config.cache_max_ttl_seconds,
        )
        self.cache.set(
            provider="google-safe-browsing-v4",
            operation="url-search",
            request_key=request_key,
            value=normalized,
            ttl_seconds=ttl_seconds,
        )
        return SafeBrowsingResponse(payload=normalized, requested_url=target)

    def _request_sync(self, target: str) -> SafeBrowsingResponse:
        body = json.dumps(
            {
                "client": {
                    "clientId": "codex-seo-plugin",
                    "clientVersion": "0.2.1",
                },
                "threatInfo": {
                    "threatTypes": list(_THREAT_TYPES),
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": target}],
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self.config.api_url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Goog-Api-Key": str(self.config.api_key),
            },
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:  # noqa: S310
                raw = response.read()
        except HTTPError as exc:
            if exc.code == 400:
                raise SeoDataError(
                    SeoDataErrorCode.INVALID_REQUEST,
                    "Safe Browsing URL 查询参数无效",
                ) from exc
            if exc.code in {401, 403}:
                raise SeoDataError(
                    SeoDataErrorCode.PERMISSION_DENIED,
                    "Safe Browsing API 无权访问，请检查 API Key、API 启用状态和 Key restriction",
                ) from exc
            if exc.code == 429:
                raise SeoDataError(
                    SeoDataErrorCode.QUOTA_EXCEEDED,
                    "Safe Browsing API 配额或请求频率已达限制",
                ) from exc
            raise SeoDataError(
                SeoDataErrorCode.PROVIDER_UNAVAILABLE,
                f"Safe Browsing API 返回 HTTP {exc.code}",
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise SeoDataError(
                SeoDataErrorCode.PROVIDER_UNAVAILABLE,
                "Safe Browsing API 请求失败或超时",
            ) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                "Safe Browsing API 返回了无效 JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                "Safe Browsing API 返回结构无效",
            )
        return SafeBrowsingResponse(payload=payload)


def _normalize_lookup_payload(payload: dict[str, object]) -> dict[str, object]:
    # v4 的无匹配响应是空对象；错误正文或其他版本的结构不能当作检查通过。
    if not payload:
        return {"threats": []}
    raw_matches = payload.get("matches")
    if "error" in payload or not isinstance(raw_matches, list):
        raise SeoDataError(
            SeoDataErrorCode.INVALID_RESPONSE,
            "Safe Browsing matches 返回结构无效",
        )

    by_url: dict[str, list[str]] = {}
    for index, raw in enumerate(raw_matches):
        if not isinstance(raw, dict):
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                f"Safe Browsing matches[{index}] 返回结构无效",
            )
        threat = raw.get("threat")
        if not isinstance(threat, dict):
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                f"Safe Browsing matches[{index}] 缺少 threat",
            )
        matched_url = str(threat.get("url") or "").strip()
        threat_type = str(raw.get("threatType") or "").strip()
        if not matched_url or not threat_type:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                f"Safe Browsing matches[{index}] 缺少 url/threatType",
            )
        bucket = by_url.setdefault(matched_url, [])
        if threat_type not in bucket:
            bucket.append(threat_type)

    return {
        "threats": [
            {"url": matched_url, "threatTypes": threat_types}
            for matched_url, threat_types in by_url.items()
        ]
    }


def _response_cache_ttl_seconds(
    payload: dict[str, object],
    *,
    max_ttl_seconds: int,
) -> int:
    if max_ttl_seconds <= 0:
        return 0

    raw_matches = payload.get("matches")
    if isinstance(raw_matches, list) and raw_matches:
        durations = [
            _duration_seconds(raw.get("cacheDuration"))
            for raw in raw_matches
            if isinstance(raw, dict)
        ]
        positive = [value for value in durations if value is not None]
        if positive:
            return min(min(positive), max_ttl_seconds)

    # V4 Lookup does not provide a negative-cache duration. Keep misses short-lived so repeated
    # one-click rechecks do not immediately hit the API while avoiding long stale "no threat" data.
    return min(300, max_ttl_seconds)


def _normalize_public_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "网站安全检查 URL 不能为空")
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "网站安全检查只支持有效的 HTTP/HTTPS URL",
        )
    if parsed.username or parsed.password:
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "网站安全检查不接受 URL 内嵌账号或密码",
        )

    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "网站安全检查只接受公开 URL",
        )
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    ):
        raise SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "网站安全检查只接受公开 URL",
        )

    return parsed._replace(path=parsed.path or "/", fragment="").geturl()


def _duration_seconds(value: object) -> int | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", str(value or ""))
    if not match:
        return None
    return max(0, int(float(match.group(1))))


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
