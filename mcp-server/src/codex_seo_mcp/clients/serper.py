from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


@dataclass(slots=True)
class SerperConfig:
    """Serper 实时 Google Search API 配置。"""

    api_url: str
    api_key: str | None
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "SerperConfig":
        raw = (os.getenv("SERPER_API_BASE_URL") or "https://google.serper.dev").rstrip("/")
        api_url = raw if raw.endswith("/search") else f"{raw}/search"
        return cls(
            api_url=api_url,
            api_key=(os.getenv("SERPER_API_KEY") or "").strip() or None,
            request_timeout_seconds=float(os.getenv("SERPER_REQUEST_TIMEOUT") or "30"),
        )


class SerperClient:
    """Serper Provider Client，只负责实时 SERP HTTP/JSON 调用。"""

    def __init__(self, config: SerperConfig | None = None) -> None:
        self.config = config or SerperConfig.from_env()

    async def search(
        self,
        query: str,
        *,
        country: str,
        language: str,
        num: int,
        location: str | None = None,
    ) -> dict[str, object]:
        key = self._require_key()
        payload: dict[str, object] = {
            "q": query,
            "gl": country.lower(),
            "hl": language,
            "num": num,
        }
        if location:
            payload["location"] = location
        request = Request(
            self.config.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "X-API-KEY": key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "CodexSEO/0.1 Serper",
            },
            method="POST",
        )
        return await asyncio.to_thread(self._request_json, request)

    def _request_json(self, request: Request) -> dict[str, object]:
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except HTTPError as exc:
            status = int(exc.code)
            if status in {401, 403}:
                raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, "Serper API Key 无效或权限不足") from exc
            if status == 429:
                raise SeoDataError(SeoDataErrorCode.RATE_LIMITED, "Serper API 请求频率或 credits 已达限制") from exc
            if 500 <= status < 600:
                raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "Serper API 暂时不可用") from exc
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, f"Serper API 请求失败（HTTP {status}）") from exc
        except (URLError, TimeoutError) as exc:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "Serper API 请求失败") from exc
        except json.JSONDecodeError as exc:
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "Serper 返回的 JSON 无效") from exc
        if not isinstance(payload, dict):
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "Serper 返回格式无效")
        return payload

    def _require_key(self) -> str:
        if not self.config.api_key:
            raise SeoDataError(SeoDataErrorCode.NOT_CONFIGURED, "缺少 SERPER_API_KEY")
        return self.config.api_key
