from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.provider_cache import ProviderCache


@dataclass(slots=True)
class CruxConfig:
    """Chrome UX Report API 配置。

    CrUX 当前是免费 API，但每个请求仍需要 Google Cloud API Key。Key 只用于 Provider
    调用，不进入领域模型或 MCP 返回值。
    """

    api_key: str | None
    cache_ttl_seconds: int = 86400

    @classmethod
    def from_env(cls) -> "CruxConfig":
        return cls(
            api_key=(os.getenv("CRUX_API_KEY") or "").strip() or None,
            cache_ttl_seconds=_int_env("CRUX_CACHE_TTL_SECONDS", 86400),
        )


@dataclass(slots=True)
class CruxResponse:
    """CrUX 原始 JSON 外壳；字段解释只允许发生在 PageQuality Adapter。"""

    payload: dict[str, object]


class CruxClient:
    """Chrome UX Report API Client。

    业务边界：404 表示该 URL/Origin 当前没有足够的 CrUX 样本，因此返回 `None`；
    这不是 Provider 故障，更不能被解释成页面性能好/坏或页面没有流量。
    """

    def __init__(
        self,
        config: CruxConfig | None = None,
        cache: ProviderCache | None = None,
    ) -> None:
        self.config = config or CruxConfig.from_env()
        self.cache = cache or ProviderCache()

    async def query_url(
        self, url: str, *, form_factor: str, metrics: tuple[str, ...]
    ) -> CruxResponse | None:
        return await self._query(
            {"url": url, "formFactor": form_factor, "metrics": list(metrics)}
        )

    async def query_origin(
        self, origin: str, *, form_factor: str, metrics: tuple[str, ...]
    ) -> CruxResponse | None:
        return await self._query(
            {"origin": origin, "formFactor": form_factor, "metrics": list(metrics)}
        )

    async def _query(self, body: dict[str, object]) -> CruxResponse | None:
        key = self._require_key()
        if self.config.cache_ttl_seconds > 0:
            cached = self.cache.get(
                provider="crux",
                operation="query-record",
                request_key=body,
            )
            if isinstance(cached, dict) and cached.get("version") == 1:
                if cached.get("found") is False:
                    return None
                payload = cached.get("payload")
                if cached.get("found") is True and isinstance(payload, dict):
                    return CruxResponse(payload=payload)

        response = await asyncio.to_thread(self._query_sync, key, body)
        self.cache.set(
            provider="crux",
            operation="query-record",
            request_key=body,
            value=(
                {"version": 1, "found": False}
                if response is None
                else {"version": 1, "found": True, "payload": response.payload}
            ),
            ttl_seconds=self.config.cache_ttl_seconds,
        )
        return response

    def _query_sync(self, key: str, body: dict[str, object]) -> CruxResponse | None:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        try:
            service = build(
                "chromeuxreport",
                "v1",
                developerKey=key,
                cache_discovery=False,
            )
            payload = service.records().queryRecord(body=body).execute()
        except HttpError as exc:
            status = int(getattr(exc.resp, "status", 0) or 0)
            if status == 404:
                return None
            if status in {401, 403}:
                raise SeoDataError(SeoDataErrorCode.PERMISSION_DENIED,
                    "CrUX API Key 无效、Chrome UX Report API 未启用或 Key restriction 不允许该 API",
                ) from exc
            if status == 429:
                raise SeoDataError(SeoDataErrorCode.RATE_LIMITED, "CrUX API 请求频率已达限制") from exc
            if 500 <= status < 600:
                raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "CrUX API 暂时不可用") from exc
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, f"CrUX API 请求失败（HTTP {status}）") from exc
        except SeoDataError:
            raise
        except Exception as exc:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "CrUX API 请求失败") from exc

        if not isinstance(payload, dict):
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "CrUX API 返回格式无效")
        return CruxResponse(payload=payload)

    def _require_key(self) -> str:
        if not self.config.api_key:
            raise SeoDataError(SeoDataErrorCode.NOT_CONFIGURED, "缺少 CRUX_API_KEY")
        return self.config.api_key


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default
