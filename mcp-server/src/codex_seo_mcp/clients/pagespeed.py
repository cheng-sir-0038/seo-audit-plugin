from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.page_quality_url import normalize_page_quality_url
from codex_seo_mcp.provider_cache import ProviderCache

_DEFAULT_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


@dataclass(slots=True)
class PageSpeedConfig:
    """PageSpeed Insights 调用配置。

    API Key 在开发阶段允许为空，因为 Google 官方允许无 Key 调用；自动化和频繁调用时
    再通过环境变量配置 Key。Key 只属于 Provider Client，不进入 Skill 或领域模型。
    """

    api_url: str = _DEFAULT_API_URL
    api_key: str | None = None
    timeout_seconds: float = 60.0
    cache_ttl_seconds: int = 1800

    @classmethod
    def from_env(cls) -> "PageSpeedConfig":
        return cls(
            api_url=os.getenv("PAGESPEED_API_BASE_URL", _DEFAULT_API_URL).strip()
            or _DEFAULT_API_URL,
            api_key=(os.getenv("PAGESPEED_API_KEY") or "").strip() or None,
            timeout_seconds=_float_env("PAGESPEED_REQUEST_TIMEOUT", 60.0),
            cache_ttl_seconds=_int_env("PAGESPEED_CACHE_TTL_SECONDS", 1800),
        )


@dataclass(slots=True)
class PageSpeedResponse:
    """PageSpeed 原始 JSON 外壳；只有 Adapter 可以解释里面的 Lighthouse 业务字段。"""

    payload: dict[str, object]


class PageSpeedClient:
    """只负责调用 PageSpeed Insights API，不做 SEO 业务判断。"""

    def __init__(
        self,
        config: PageSpeedConfig | None = None,
        cache: ProviderCache | None = None,
    ) -> None:
        self.config = config or PageSpeedConfig.from_env()
        self.cache = cache or ProviderCache()

    async def analyze(
        self,
        url: str,
        *,
        strategy: str,
        categories: tuple[str, ...],
        locale: str,
    ) -> PageSpeedResponse:
        target = normalize_page_quality_url(url)
        query: list[tuple[str, str]] = [
            ("url", target),
            ("strategy", strategy),
            ("locale", locale),
        ]
        query.extend(("category", category) for category in categories)
        if self.config.api_key:
            query.append(("key", self.config.api_key))

        request_key = {
            "url": target,
            "strategy": strategy,
            "categories": list(categories),
            "locale": locale,
        }
        if self.config.cache_ttl_seconds > 0:
            cached = self.cache.get(
                provider="pagespeed",
                operation="runpagespeed",
                request_key=request_key,
            )
            if isinstance(cached, dict):
                try:
                    validate_pagespeed_response(cached)
                except SeoDataError:
                    pass  # 旧的失败响应不是测量缓存，重新请求。
                else:
                    return PageSpeedResponse(payload=cached)

        request_url = f"{self.config.api_url}?{urlencode(query)}"
        response = await asyncio.to_thread(self._request_sync, request_url)
        validate_pagespeed_response(response.payload)
        self.cache.set(
            provider="pagespeed",
            operation="runpagespeed",
            request_key=request_key,
            value=response.payload,
            ttl_seconds=self.config.cache_ttl_seconds,
        )
        return response

    def _request_sync(self, request_url: str) -> PageSpeedResponse:
        request = Request(request_url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:  # noqa: S310
                raw = response.read()
        except HTTPError as exc:
            # 上游 4xx/5xx 是 Provider 状态，不应该把 Google 的 HTML/JSON 错误正文泄漏给 Skill。
            if exc.code in {401, 403}:
                raise SeoDataError(SeoDataErrorCode.PERMISSION_DENIED, "PageSpeed API 无权访问或 API Key 无效") from exc
            if exc.code == 429:
                raise SeoDataError(SeoDataErrorCode.QUOTA_EXCEEDED, "PageSpeed API 配额或请求频率已达限制") from exc
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, f"PageSpeed API 返回 HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "PageSpeed API 请求失败或超时") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "PageSpeed API 返回了无效 JSON") from exc
        if not isinstance(payload, dict):
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "PageSpeed API 返回结构无效")
        return PageSpeedResponse(payload=payload)


def validate_pagespeed_response(payload: Mapping[str, object]) -> None:
    """Validate the provider outcome before caching; metric interpretation stays in the adapter."""

    if not isinstance(payload, Mapping) or "error" in payload:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "PageSpeed API 返回结构无效")
    lighthouse = payload.get("lighthouseResult")
    if not isinstance(lighthouse, Mapping) or not lighthouse:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "PageSpeed 响应缺少 lighthouseResult")
    runtime_error = lighthouse.get("runtimeError")
    if runtime_error is not None and (
        not isinstance(runtime_error, Mapping)
        or (runtime_error and runtime_error.get("code") != "NO_ERROR")
    ):
        # Provider 消息可能包含目标地址或其他原始内容，不作为公共错误返回。
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "PageSpeed Lighthouse 检测失败")


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
        return max(0, int(raw))
    except ValueError:
        return default
