from __future__ import annotations

from typing import Any

from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class Ga4HttpTransport:
    """Send authenticated GA4 HTTP requests and normalize provider-level failures."""

    def __init__(
        self,
        *,
        admin_base_url: str,
        data_base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.admin_base_url = admin_base_url.rstrip("/")
        self.data_base_url = data_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def admin_get(
        self,
        credentials: Any,
        path: str,
        *,
        params: dict[str, object],
    ) -> dict[str, object]:
        with _authorized_session(credentials) as session:
            try:
                response = session.get(
                    f"{self.admin_base_url}{path}",
                    params=params,
                    timeout=self.timeout_seconds,
                )
            except (RequestsConnectionError, Timeout) as exc:
                # 没收到 HTTP 响应也是供应商不可用；不把异常中的 URL 或凭据返回给 Host。
                raise SeoDataError(
                    SeoDataErrorCode.PROVIDER_UNAVAILABLE,
                    "GA4 Admin API 网络连接失败或请求超时",
                ) from exc
            return _json_response(response, provider="GA4 Admin API")

    def data_post(
        self,
        credentials: Any,
        path: str,
        *,
        body: dict[str, object],
    ) -> dict[str, object]:
        with _authorized_session(credentials) as session:
            try:
                response = session.post(
                    f"{self.data_base_url}{path}",
                    json=body,
                    timeout=self.timeout_seconds,
                )
            except (RequestsConnectionError, Timeout) as exc:
                raise SeoDataError(
                    SeoDataErrorCode.PROVIDER_UNAVAILABLE,
                    "GA4 Data API 网络连接失败或请求超时",
                ) from exc
            return _json_response(response, provider="GA4 Data API")


def _authorized_session(credentials: Any) -> Any:
    # Imported lazily so mapper/query-builder tests do not require Google HTTP packages.
    from google.auth.transport.requests import AuthorizedSession

    return AuthorizedSession(credentials)


def _json_response(response: Any, *, provider: str) -> dict[str, object]:
    status = int(getattr(response, "status_code", 0) or 0)
    if not 200 <= status < 300:
        if status == 400:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                f"{provider} 请求参数无效",
            )
        if status == 401:
            raise SeoDataError(
                SeoDataErrorCode.AUTHORIZATION_REQUIRED,
                "GA4 授权已失效，请重新连接",
            )
        if status == 403:
            raise SeoDataError(
                SeoDataErrorCode.PERMISSION_DENIED,
                "GA4 请求被拒绝，请检查 Analytics API 是否启用以及当前账号的 Property 权限",
            )
        if status == 429:
            raise SeoDataError(
                SeoDataErrorCode.QUOTA_EXCEEDED,
                "GA4 API 配额或并发请求已达限制",
            )
        if 500 <= status < 600:
            raise SeoDataError(
                SeoDataErrorCode.PROVIDER_UNAVAILABLE,
                "GA4 API 暂时不可用",
            )
        raise SeoDataError(
            SeoDataErrorCode.PROVIDER_UNAVAILABLE,
            f"GA4 API 请求失败（HTTP {status}）",
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise SeoDataError(
            SeoDataErrorCode.INVALID_RESPONSE,
            f"{provider} 返回非 JSON 响应",
        ) from exc
    if not isinstance(payload, dict) or "error" in payload:
        # HTTP 成功但正文仍是错误不能被当成空列表或写入成功缓存。
        raise SeoDataError(
            SeoDataErrorCode.INVALID_RESPONSE,
            f"{provider} 返回结构无效",
        )
    return payload
