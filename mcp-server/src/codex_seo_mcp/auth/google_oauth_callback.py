from __future__ import annotations

import html
import webbrowser
import wsgiref.simple_server
import wsgiref.util
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

from google_auth_oauthlib.flow import WSGITimeoutError

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


@dataclass(frozen=True, slots=True)
class GoogleOAuthCallbackPage:
    """Render the local OAuth completion page from bundled, offline-only assets."""

    provider_name: str
    account_name: str

    def success_html(self) -> str:
        return _render_page(
            provider_name=self.provider_name,
            account_name=self.account_name,
            title=f"{self.provider_name} 授权完成",
            message="授权信息已完成校验并安全保存。",
            footer="现在可以关闭此页面并返回 Codex 继续使用 SEO 数据能力。",
            status_class="is-success",
            status_icon="✓",
        )

    def failure_html(self) -> str:
        return _render_page(
            provider_name=self.provider_name,
            account_name=self.account_name,
            title=f"{self.provider_name} 授权未完成",
            message="未能完成授权校验或安全保存凭据。",
            footer="请返回 Codex 重新发起连接；此页面不会展示 OAuth 错误详情或凭据内容。",
            status_class="is-danger",
            status_icon="!",
        )


class GoogleOAuthCallbackApp:
    """One-request WSGI callback that exchanges and persists OAuth credentials before success."""

    def __init__(
        self,
        *,
        flow: Any,
        save_credentials: Callable[[Any], None],
        page: GoogleOAuthCallbackPage,
    ) -> None:
        self.flow = flow
        self.save_credentials = save_credentials
        self.page = page
        self.request_received = False
        self.error: Exception | None = None

    def __call__(
        self,
        environ: dict[str, Any],
        start_response: Callable[[str, list[tuple[str, str]]], None],
    ) -> Iterable[bytes]:
        self.request_received = True
        authorization_response = wsgiref.util.request_uri(environ).replace(
            "http://", "https://", 1
        )
        try:
            self.flow.fetch_token(authorization_response=authorization_response)
        except Exception as exc:
            self.error = exc
            return _html_response(
                start_response,
                "400 Bad Request",
                self.page.failure_html(),
            )

        try:
            self.save_credentials(self.flow.credentials)
        except Exception as exc:
            self.error = exc
            return _html_response(
                start_response,
                "500 Internal Server Error",
                self.page.failure_html(),
            )

        return _html_response(start_response, "200 OK", self.page.success_html())


class _QuietWSGIRequestHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return None


def run_google_oauth_callback(
    flow: Any,
    *,
    host: str,
    timeout_seconds: int,
    save_credentials: Callable[[Any], None],
    page: GoogleOAuthCallbackPage,
) -> Any:
    """Open Google consent and complete token exchange/persistence inside the callback response."""

    app = GoogleOAuthCallbackApp(
        flow=flow,
        save_credentials=save_credentials,
        page=page,
    )
    local_server = wsgiref.simple_server.make_server(
        host,
        0,
        app,
        handler_class=_QuietWSGIRequestHandler,
    )
    try:
        flow.redirect_uri = f"http://{host}:{local_server.server_port}/"
        auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        webbrowser.get().open(auth_url, new=1, autoraise=True)

        local_server.timeout = timeout_seconds
        local_server.handle_request()
        if not app.request_received:
            raise WSGITimeoutError("Timed out waiting for response from authorization server")
        if app.error is not None:
            raise SeoDataError(
                SeoDataErrorCode.AUTHORIZATION_REQUIRED,
                f"{page.provider_name} OAuth 授权未完成，请返回 Codex 重试",
            ) from app.error
        return flow.credentials
    finally:
        local_server.server_close()


def _html_response(
    start_response: Callable[[str, list[tuple[str, str]]], None],
    status: str,
    body: str,
) -> list[bytes]:
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Cache-Control", "no-store"),
        ("Pragma", "no-cache"),
        ("Referrer-Policy", "no-referrer"),
        ("X-Content-Type-Options", "nosniff"),
        (
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        ),
    ]
    start_response(status, headers)
    return [body.encode("utf-8")]


def _render_page(
    *,
    provider_name: str,
    account_name: str,
    title: str,
    message: str,
    footer: str,
    status_class: str,
    status_icon: str,
) -> str:
    template, bootstrap_css, callback_css = _ui_assets()
    values = {
        "provider_name": html.escape(provider_name),
        "account_name": html.escape(account_name),
        "title": html.escape(title),
        "message": html.escape(message),
        "footer": html.escape(footer),
        "status_class": html.escape(status_class),
        "status_icon": html.escape(status_icon),
        "bootstrap_css": bootstrap_css,
        "callback_css": callback_css,
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


@lru_cache(maxsize=1)
def _ui_assets() -> tuple[str, str, str]:
    auth_root = resources.files("codex_seo_mcp.auth")
    ui_root = auth_root.joinpath("ui")
    return (
        ui_root.joinpath("callback.html").read_text(encoding="utf-8"),
        ui_root.joinpath("vendor", "bootstrap", "bootstrap.min.css").read_text(
            encoding="utf-8"
        ),
        ui_root.joinpath("callback.css").read_text(encoding="utf-8"),
    )
