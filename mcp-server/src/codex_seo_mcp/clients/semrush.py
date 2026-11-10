from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.provider_cache import ProviderCache


@dataclass(slots=True)
class SemrushConfig:
    """Semrush v3/v4 API 配置。

    Semrush 从 2026 年起明确区分 v3/v4 API Key，两者不能混用。具体版本变量优先；
    `SEMRUSH_API_KEY` 只作为开发阶段兼容 fallback，方便识别用户手里的旧 Key 属于哪一版。
    """

    base_url: str
    v3_api_key: str | None
    v4_api_key: str | None
    request_timeout_seconds: float = 30.0
    cache_ttl_seconds: int = 21600
    default_keyword_limit: int = 20

    @classmethod
    def from_env(cls) -> "SemrushConfig":
        generic = (os.getenv("SEMRUSH_API_KEY") or "").strip() or None
        return cls(
            base_url=(os.getenv("SEMRUSH_BASE_URL") or "https://api.semrush.com").rstrip("/"),
            v3_api_key=(os.getenv("SEMRUSH_V3_API_KEY") or "").strip() or generic,
            v4_api_key=(os.getenv("SEMRUSH_V4_API_KEY") or "").strip() or generic,
            request_timeout_seconds=float(os.getenv("SEMRUSH_REQUEST_TIMEOUT") or "30"),
            cache_ttl_seconds=max(0, _int_env("SEMRUSH_CACHE_TTL_SECONDS", 21600)),
            default_keyword_limit=max(
                1, min(_int_env("SEMRUSH_DEFAULT_KEYWORD_LIMIT", 20), 100)
            ),
        )


@dataclass(slots=True)
class SemrushReport:
    """v3 CSV report 解析后的通用行集合。"""

    rows: list[dict[str, str]]


class SemrushClient:
    """Semrush Provider Client。

    Client 只处理 v3/v4 鉴权、HTTP、CSV/JSON 与供应商错误；领域字段解释留给 Adapter。
    Semrush Project / Position Tracking / Site Audit 在这里没有任何实现入口。
    """

    def __init__(
        self,
        config: SemrushConfig | None = None,
        cache: ProviderCache | None = None,
    ) -> None:
        self.config = config or SemrushConfig.from_env()
        self.cache = cache or ProviderCache()

    @property
    def default_keyword_limit(self) -> int:
        """Semrush 关键词列表默认返回数量；用户显式指定时由 Adapter 覆盖。"""

        return self.config.default_keyword_limit

    async def keyword_metrics(
        self, keyword: str, country: str, month: str | None = None
    ) -> dict[str, object]:
        """调用 v4 Get Keyword Metrics；官方固定成本 20 API units/请求。"""

        key = self._require_key("v4")
        params = {"keyword": keyword, "country": country}
        if month:
            params["month"] = month
        cache_key = {"api": "v4", "operation": "keyword_metrics", "params": params}
        if self.config.cache_ttl_seconds > 0:
            cached = self.cache.get(
                provider="semrush",
                operation="v4-keyword-metrics",
                request_key=cache_key,
            )
            if isinstance(cached, dict):
                return cached
        url = f"{self.config.base_url}/apis/v4/keywords/v1/metrics?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Authorization": f"Apikey {key}",
                "Accept": "application/json",
                "User-Agent": "CodexSEO/0.1 Semrush",
            },
        )
        payload = await asyncio.to_thread(self._request_json, request)
        if not isinstance(payload, dict):
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "Semrush v4 Keyword Metrics 返回格式无效")
        self.cache.set(
            provider="semrush",
            operation="v4-keyword-metrics",
            request_key=cache_key,
            value=payload,
            ttl_seconds=self.config.cache_ttl_seconds,
        )
        return payload

    async def keyword_overview_v3(
        self, keyword: str, database: str, month: str | None = None
    ) -> SemrushReport:
        """v3 Keyword Overview fallback。

        v3 已被 Semrush 标记 deprecated，但现有 v3 Key 仍可用。这里仅作为兼容路径，
        保留 volume/CPC/competition/trend/intent/KD，不把 v3 版本细节暴露给 Skill。
        """

        params = {
            "type": "phrase_this",
            "phrase": keyword,
            "database": database,
            "export_columns": "Ph,Nq,Cp,Co,Nr,Td,In,Kd",
        }
        if month:
            params["display_date"] = month.replace("-", "") + "15"
        return await self._v3_report(params)

    async def related_keywords_v3(
        self, keyword: str, database: str, limit: int
    ) -> SemrushReport:
        """v3 Related Keywords；调用成本按返回行计费，因此 limit 必须由上层显式控制。"""

        return await self._v3_report(
            {
                "type": "phrase_related",
                "phrase": keyword,
                "database": database,
                "display_limit": str(limit),
                "display_sort": "nq_desc",
                "export_columns": "Ph,Nq,Cp,Co,Nr,Td,In,Kd",
            }
        )

    async def keyword_questions_v3(
        self, keyword: str, database: str, limit: int
    ) -> SemrushReport:
        """v3 Phrase Questions；只在调用方明确需要时请求，避免自动消耗大量 API units。"""

        return await self._v3_report(
            {
                "type": "phrase_questions",
                "phrase": keyword,
                "database": database,
                "display_limit": str(limit),
                "display_sort": "nq_desc",
                "export_columns": "Ph,Nq,Cp,Co,Nr,Td,In,Kd",
            }
        )

    async def domain_overview(self, domain: str, database: str) -> SemrushReport:
        return await self._v3_report(
            {
                "type": "domain_rank",
                "domain": domain,
                "database": database,
                "export_columns": "Dn,Rk,Or,Ot,Oc,Ad,At,Ac",
            }
        )

    async def organic_competitors(
        self, domain: str, database: str, limit: int
    ) -> SemrushReport:
        return await self._v3_report(
            {
                "type": "domain_organic_organic",
                "domain": domain,
                "database": database,
                "display_limit": str(limit),
                "display_sort": "np_desc",
                "export_columns": "Dn,Cr,Np,Or,Ot,Oc,Ad",
            }
        )

    async def organic_pages(
        self, domain: str, database: str, limit: int
    ) -> SemrushReport:
        return await self._v3_report(
            {
                "type": "domain_organic_unique",
                "domain": domain,
                "database": database,
                "display_limit": str(limit),
                "display_sort": "tr_desc",
                "export_columns": "Ur,Pc,Tg,Tr",
            }
        )

    async def keyword_gap(
        self, domains: list[str], database: str, limit: int
    ) -> SemrushReport:
        if not 2 <= len(domains) <= 5:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "Semrush Keyword Gap 需要 2 到 5 个域名")
        domain_expr = "|".join(f"*|or|{domain}" for domain in domains)
        position_columns = [f"P{i}" for i in range(len(domains))]
        return await self._v3_report(
            {
                "type": "domain_domains",
                "domains": domain_expr,
                "database": database,
                "display_limit": str(limit),
                "export_columns": ",".join(["Ph", *position_columns, "Co", "Nq", "Cp"]),
            }
        )

    async def v3_api_units(self) -> int:
        """使用 Semrush 官方 0-unit Standard API balance 请求验证 v3 Key。"""

        key = self._require_key("v3")
        url = f"https://www.semrush.com/users/countapiunits.html?{urlencode({'key': key})}"
        body = await asyncio.to_thread(self._request_text, Request(url))
        cleaned = body.strip().replace(",", "")
        if not cleaned.isdigit():
            self._raise_v3_error(body)
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "Semrush v3 API units 返回格式无效")
        return int(cleaned)

    async def _v3_report(self, params: dict[str, str]) -> SemrushReport:
        key = self._require_key("v3")
        cache_key = {"api": "v3", "params": params}
        if self.config.cache_ttl_seconds > 0:
            cached = self.cache.get(
                provider="semrush",
                operation=f"v3-{params.get('type', 'report')}",
                request_key=cache_key,
            )
            cached_report = _report_from_cache(cached)
            if cached_report is not None:
                return cached_report
        query = dict(params)
        query["key"] = key
        url = f"{self.config.base_url}/?{urlencode(query)}"
        body = await asyncio.to_thread(self._request_text, Request(url))
        if re.match(r"ERROR\s+50\s*::\s*NOTHING FOUND", body.strip(), re.I):
            # Semrush v3 用 ERROR 50 表达“当前查询没有数据”；这不是鉴权失败，也不能
            # 让上层把它误解成 Provider 不可用。领域层收到空 rows 后自行保留 No Data。
            report = SemrushReport(rows=[])
            self._cache_v3_report(params, cache_key, report)
            return report
        self._raise_v3_error(body)
        if not body.strip():
            report = SemrushReport(rows=[])
            self._cache_v3_report(params, cache_key, report)
            return report
        reader = csv.DictReader(io.StringIO(body), delimiter=";")
        if not reader.fieldnames:
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "Semrush v3 CSV 缺少表头")
        report = SemrushReport(
            rows=[{str(k): str(v or "") for k, v in row.items()} for row in reader]
        )
        self._cache_v3_report(params, cache_key, report)
        return report

    def _cache_v3_report(
        self,
        params: dict[str, str],
        cache_key: dict[str, object],
        report: SemrushReport,
    ) -> None:
        self.cache.set(
            provider="semrush",
            operation=f"v3-{params.get('type', 'report')}",
            request_key=cache_key,
            value={"rows": report.rows},
            ttl_seconds=self.config.cache_ttl_seconds,
        )

    def _request_json(self, request: Request) -> Any:
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8", "replace"))
        except HTTPError as exc:
            self._raise_http_error(exc)
        except (URLError, TimeoutError) as exc:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "Semrush API 请求失败") from exc
        raise AssertionError("unreachable")

    def _request_text(self, request: Request) -> str:
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:  # noqa: S310
                return response.read().decode("utf-8", "replace")
        except HTTPError as exc:
            self._raise_http_error(exc)
        except (URLError, TimeoutError) as exc:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "Semrush API 请求失败") from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _raise_http_error(exc: HTTPError) -> None:
        status = int(exc.code)
        if status == 401:
            raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, "Semrush API Key 无效或版本不匹配") from exc
        if status == 403:
            raise SeoDataError(SeoDataErrorCode.PERMISSION_DENIED, "Semrush API 权限不足或当前套餐未开放该接口") from exc
        if status == 429:
            raise SeoDataError(SeoDataErrorCode.RATE_LIMITED, "Semrush API 请求频率已达限制") from exc
        if 500 <= status < 600:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "Semrush API 暂时不可用") from exc
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, f"Semrush API 请求失败（HTTP {status}）") from exc

    @staticmethod
    def _raise_v3_error(body: str) -> None:
        text = body.strip()
        match = re.match(r"ERROR\s+(\d+)\s*::\s*(.*)", text, re.I)
        if not match:
            return
        code = int(match.group(1))
        message = match.group(2).strip().lower()
        if code == 50 and "nothing found" in message:
            return
        if code == 132:
            raise SeoDataError(SeoDataErrorCode.QUOTA_EXCEEDED, "Semrush API units 已耗尽")
        if "wrong key" in message or code in {120, 121, 122}:
            raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, "Semrush v3 API Key 无效或版本不匹配")
        if code == 130:
            raise SeoDataError(SeoDataErrorCode.PERMISSION_DENIED, "当前 Semrush 套餐未开放 Standard API")
        raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, f"Semrush v3 返回 ERROR {code}")

    def _require_key(self, version: str) -> str:
        key = self.config.v4_api_key if version == "v4" else self.config.v3_api_key
        if not key:
            raise SeoDataError(SeoDataErrorCode.NOT_CONFIGURED,
                f"缺少 Semrush {version} API Key；请配置 SEMRUSH_{version.upper()}_API_KEY",
            )
        return key


def _report_from_cache(value: object) -> SemrushReport | None:
    if not isinstance(value, dict):
        return None
    raw_rows = value.get("rows")
    if not isinstance(raw_rows, list):
        return None
    rows: list[dict[str, str]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        rows.append({str(key): str(item or "") for key, item in raw.items()})
    return SemrushReport(rows=rows)


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
