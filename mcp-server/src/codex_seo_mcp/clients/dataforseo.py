from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.observability import emit_event
from codex_seo_mcp.provider_cache import ProviderCache


@dataclass(slots=True)
class DataForSEOConfig:
    api_base_url: str
    sandbox_base_url: str
    login: str | None
    password: str | None
    request_timeout_seconds: float = 30.0
    use_sandbox: bool = False
    cache_ttl_seconds: int = 86400

    @classmethod
    def from_env(cls) -> "DataForSEOConfig":
        sandbox_flag = (os.getenv("DATAFORSEO_USE_SANDBOX") or "").strip().lower()
        return cls(
            api_base_url=(os.getenv("DATAFORSEO_API_BASE_URL") or "https://api.dataforseo.com").rstrip("/"),
            sandbox_base_url=(
                os.getenv("DATAFORSEO_SANDBOX_BASE_URL") or "https://sandbox.dataforseo.com"
            ).rstrip("/"),
            login=(os.getenv("DATAFORSEO_LOGIN") or "").strip() or None,
            password=(os.getenv("DATAFORSEO_PASSWORD") or "").strip() or None,
            request_timeout_seconds=float(os.getenv("DATAFORSEO_REQUEST_TIMEOUT") or "30"),
            use_sandbox=sandbox_flag in {"1", "true", "yes", "on"},
            cache_ttl_seconds=max(0, _int_env("DATAFORSEO_CACHE_TTL_SECONDS", 86400)),
        )


@dataclass(slots=True)
class DataForSEOReport:
    """Validated DataForSEO task result without leaking provider envelope details upward."""

    result: list[dict[str, object]]
    cost: float | None = None
    partial: bool = False
    status_message: str | None = None


class DataForSEOClient:
    """DataForSEO v3 client for the first OrganicVisibility provider adapter.

    Authentication is HTTP Basic with the API-access login/password. The client only handles HTTP,
    provider envelopes and stable error mapping; SEO field interpretation stays in the adapter.
    """

    def __init__(
        self,
        config: DataForSEOConfig | None = None,
        cache: ProviderCache | None = None,
    ) -> None:
        self.config = config or DataForSEOConfig.from_env()
        self.cache = cache or ProviderCache()

    @property
    def is_sandbox(self) -> bool:
        return self.config.use_sandbox

    async def locations_and_languages(self) -> list[dict[str, object]]:
        report = await self._request_report(
            method="GET",
            path="/v3/dataforseo_labs/locations_and_languages",
            operation="locations_and_languages",
        )
        return report.result

    async def ranked_keywords(self, task: dict[str, object]) -> DataForSEOReport:
        return await self._post(
            "/v3/dataforseo_labs/google/ranked_keywords/live",
            task,
            operation="ranked_keywords",
        )

    async def relevant_pages(self, task: dict[str, object]) -> DataForSEOReport:
        return await self._post(
            "/v3/dataforseo_labs/google/relevant_pages/live",
            task,
            operation="relevant_pages",
        )

    async def domain_rank_overview(self, task: dict[str, object]) -> DataForSEOReport:
        return await self._post(
            "/v3/dataforseo_labs/google/domain_rank_overview/live",
            task,
            operation="domain_rank_overview",
        )

    async def historical_rank_overview(self, task: dict[str, object]) -> DataForSEOReport:
        return await self._post(
            "/v3/dataforseo_labs/google/historical_rank_overview/live",
            task,
            operation="historical_rank_overview",
        )

    async def _post(
        self,
        path: str,
        task: dict[str, object],
        *,
        operation: str,
    ) -> DataForSEOReport:
        self._require_credentials()
        return await self._request_report(
            method="POST",
            path=path,
            operation=operation,
            task=task,
        )

    async def _request_report(
        self,
        *,
        method: Literal["GET", "POST"],
        path: str,
        operation: str,
        task: dict[str, object] | None = None,
    ) -> DataForSEOReport:
        # 缓存不能绕过 Provider credential 边界；即使本地有旧数据，也先确认当前运行
        # 环境配置了 DataForSEO 凭据，避免共享 PLUGIN_DATA 时把旧缓存当公开数据源。
        self._require_credentials()
        cache_key: dict[str, object] = {
            "method": method,
            "path": path,
            "sandbox": self.config.use_sandbox,
        }
        if task is not None:
            cache_key["task"] = task
        if self.config.cache_ttl_seconds > 0:
            cached = self.cache.get(
                provider="dataforseo",
                operation=path,
                request_key=cache_key,
            )
            cached_report = _report_from_cache(cached)
            if cached_report is not None:
                emit_event(
                    "provider_request_cache_hit",
                    provider="dataforseo",
                    operation=operation,
                    sandbox=self.config.use_sandbox,
                )
                return cached_report

        data = None
        if task is not None:
            data = json.dumps([task], ensure_ascii=False).encode("utf-8")
        request = Request(
            self._url(path),
            data=data,
            headers=self._headers(),
            method=method,
        )
        payload = await asyncio.to_thread(self._request_json, request)
        report = _parse_report(payload)
        _emit_provider_cost(operation, report, sandbox=self.config.use_sandbox)
        self.cache.set(
            provider="dataforseo",
            operation=path,
            request_key=cache_key,
            value=_report_to_cache(report),
            ttl_seconds=self.config.cache_ttl_seconds,
        )
        return report

    def _url(self, path: str) -> str:
        base = self.config.sandbox_base_url if self.config.use_sandbox else self.config.api_base_url
        return f"{base}{path}"

    def _headers(self) -> dict[str, str]:
        login, password = self._require_credentials()
        token = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CodexSEO/0.1 DataForSEO",
        }

    def _require_credentials(self) -> tuple[str, str]:
        if not self.config.login or not self.config.password:
            raise SeoDataError(SeoDataErrorCode.NOT_CONFIGURED,
                "缺少 DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD；请配置 DataForSEO API access 凭据",
            )
        return self.config.login, self.config.password

    def _request_json(self, request: Request) -> dict[str, object]:
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except HTTPError as exc:
            status = int(exc.code)
            if status == 401:
                raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, "DataForSEO API 凭据无效") from exc
            if status == 402:
                raise SeoDataError(SeoDataErrorCode.QUOTA_EXCEEDED, "DataForSEO 账户余额或计费状态不足") from exc
            if status == 404:
                raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "DataForSEO endpoint 不存在") from exc
            if status == 429:
                raise SeoDataError(SeoDataErrorCode.RATE_LIMITED, "DataForSEO API 请求频率已达限制") from exc
            if 500 <= status < 600:
                raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "DataForSEO API 暂时不可用") from exc
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, f"DataForSEO API 请求失败（HTTP {status}）") from exc
        except (URLError, TimeoutError) as exc:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "DataForSEO API 请求失败") from exc
        except json.JSONDecodeError as exc:
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "DataForSEO 返回的 JSON 无效") from exc
        if not isinstance(payload, dict):
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "DataForSEO 返回格式无效")
        return payload


def _parse_report(payload: dict[str, object]) -> DataForSEOReport:
    general_code = _int(payload.get("status_code"))
    general_message = _text(payload.get("status_message"))
    if general_code != 20000:
        raise _status_error(general_code, general_message)

    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "DataForSEO 返回缺少 tasks")
    task = tasks[0]
    if not isinstance(task, dict):
        raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "DataForSEO task 结构无效")

    task_code = _int(task.get("status_code"))
    task_message = _text(task.get("status_message"))
    result = [item for item in (task.get("result") or []) if isinstance(item, dict)]
    cost = _float(task.get("cost"))

    if task_code == 40102:
        return DataForSEOReport(result=[], cost=cost, status_message=task_message)
    if task_code == 40106:
        return DataForSEOReport(
            result=result,
            cost=cost,
            partial=True,
            status_message=task_message,
        )
    if task_code != 20000:
        raise _status_error(task_code, task_message)
    return DataForSEOReport(result=result, cost=cost, status_message=task_message)


def _report_to_cache(report: DataForSEOReport) -> dict[str, object]:
    return {
        "result": report.result,
        "cost": report.cost,
        "partial": report.partial,
        "status_message": report.status_message,
    }


def _emit_provider_cost(
    operation: str,
    report: DataForSEOReport,
    *,
    sandbox: bool,
) -> None:
    emit_event(
        "provider_request_completed",
        provider="dataforseo",
        operation=operation,
        cost_usd=report.cost,
        sandbox=sandbox,
    )


def _report_from_cache(value: object) -> DataForSEOReport | None:
    if not isinstance(value, dict):
        return None
    raw_result = value.get("result")
    if not isinstance(raw_result, list):
        return None
    result = [item for item in raw_result if isinstance(item, dict)]
    return DataForSEOReport(
        result=result,
        cost=_float(value.get("cost")),
        partial=bool(value.get("partial")),
        status_message=_text(value.get("status_message")),
    )


def _status_error(code: int | None, message: str | None) -> SeoDataError:
    text = message or "DataForSEO 请求失败"
    if code in {40100, 40104}:
        return SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, text)
    if code in {40204, 40207}:
        return SeoDataError(SeoDataErrorCode.PERMISSION_DENIED, text)
    if code in {40202, 40205, 40206, 40209}:
        return SeoDataError(SeoDataErrorCode.RATE_LIMITED, text)
    if code in {40200, 40203, 40210}:
        return SeoDataError(SeoDataErrorCode.QUOTA_EXCEEDED, text)
    if code is not None and 40000 <= code < 50000:
        return SeoDataError(SeoDataErrorCode.INVALID_REQUEST, text)
    if code is not None and code >= 50000:
        return SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, text)
    return SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, text)


def _text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
