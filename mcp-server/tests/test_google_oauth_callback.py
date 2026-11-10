from __future__ import annotations

import unittest

from codex_seo_mcp.auth.google_oauth_callback import (
    GoogleOAuthCallbackApp,
    GoogleOAuthCallbackPage,
)


class _FakeFlow:
    def __init__(self) -> None:
        self.credentials = object()
        self.fetch_calls: list[str] = []

    def fetch_token(self, *, authorization_response: str) -> None:
        self.fetch_calls.append(authorization_response)


def _invoke(app: GoogleOAuthCallbackApp, query: str = "code=abc&state=xyz") -> tuple[str, dict[str, str], str]:
    response: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        response["status"] = status
        response["headers"] = dict(headers)

    body = b"".join(
        app(
            {
                "wsgi.url_scheme": "http",
                "SERVER_NAME": "127.0.0.1",
                "SERVER_PORT": "51321",
                "REQUEST_METHOD": "GET",
                "SCRIPT_NAME": "",
                "PATH_INFO": "/",
                "QUERY_STRING": query,
                "SERVER_PROTOCOL": "HTTP/1.1",
            },
            start_response,
        )
    ).decode("utf-8")
    return str(response["status"]), response["headers"], body  # type: ignore[return-value]


class GoogleOAuthCallbackPageTests(unittest.TestCase):
    def test_success_page_bundles_local_bootstrap_without_external_assets_or_js(self) -> None:
        html = GoogleOAuthCallbackPage(
            provider_name="GA4",
            account_name="Google Analytics",
        ).success_html()

        self.assertIn("v5.3.8", html)
        self.assertIn("GA4 授权完成", html)
        self.assertIn("Google Analytics", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("<link", html.lower())
        self.assertNotIn('src="http', html.lower())
        self.assertNotIn('href="http', html.lower())

    def test_callback_saves_credentials_before_rendering_success(self) -> None:
        flow = _FakeFlow()
        events: list[str] = []

        def save(credentials: object) -> None:
            self.assertIs(credentials, flow.credentials)
            events.append("saved")

        app = GoogleOAuthCallbackApp(
            flow=flow,
            save_credentials=save,
            page=GoogleOAuthCallbackPage("GA4", "Google Analytics"),
        )
        status, headers, body = _invoke(app)

        self.assertEqual(flow.fetch_calls, ["https://127.0.0.1:51321/?code=abc&state=xyz"])
        self.assertEqual(events, ["saved"])
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("GA4 授权完成", body)
        self.assertIsNone(app.error)

    def test_callback_renders_failure_if_token_persistence_fails(self) -> None:
        flow = _FakeFlow()

        def save(_credentials: object) -> None:
            raise OSError("disk full")

        app = GoogleOAuthCallbackApp(
            flow=flow,
            save_credentials=save,
            page=GoogleOAuthCallbackPage("GA4", "Google Analytics"),
        )
        status, headers, body = _invoke(app)

        self.assertEqual(status, "500 Internal Server Error")
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("GA4 授权未完成", body)
        self.assertNotIn("disk full", body)
        self.assertIsInstance(app.error, OSError)


if __name__ == "__main__":
    unittest.main()
