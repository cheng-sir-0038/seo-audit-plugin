from __future__ import annotations

import io
import json
import socket
import threading
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from codex_seo_mcp.adapters.page_inspection import PageInspectionAdapter
from codex_seo_mcp.adapters.resource_inspection import ResourceInspectionAdapter
from codex_seo_mcp.clients.page_html import (
    PageHtmlClient,
    PageHtmlConfig,
    RawHttpResponse,
    UrllibTransport,
    resolve_fake_ip,
)
from codex_seo_mcp.clients.resource_http import ResourceHttpClient
from codex_seo_mcp.errors import SeoDataError


async def fake_ip_resolver(_host: str) -> list[str]:
    return ["198.18.0.189"]


class FixtureTransport:
    def __init__(self, responses: dict[str, RawHttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, list[str] | None]] = []

    async def get(self, url: str, *, config, pinned_addresses=None) -> RawHttpResponse:
        self.calls.append((url, pinned_addresses))
        return self.responses[url]


class FakeIpResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_doh_reads_a_and_aaaa_answers(self) -> None:
        def dns_response(request, *, timeout):
            record_type = parse_qs(urlparse(request.full_url).query)["type"][0]
            answer = (
                {"type": 1, "data": "93.184.216.34"}
                if record_type == "A" else {"type": 28, "data": "2606:4700:4700::1111"}
            )
            return io.BytesIO(json.dumps({"Status": 0, "Answer": [answer]}).encode())

        with patch("codex_seo_mcp.clients.page_html.urlopen", side_effect=dns_response):
            addresses = await resolve_fake_ip("example.com")

        self.assertEqual(addresses, ["93.184.216.34", "2606:4700:4700::1111"])

    async def test_dns_failure_does_not_attempt_target_request(self) -> None:
        transport = FixtureTransport({})
        with (
            patch("codex_seo_mcp.clients.page_html.urlopen", side_effect=OSError("DNS down")),
            self.assertRaises(SeoDataError) as caught,
        ):
            await PageHtmlClient(resolver=fake_ip_resolver, transport=transport).fetch(
                "https://example.com/"
            )
        self.assertEqual(caught.exception.code, "provider_unavailable")
        self.assertEqual(transport.calls, [])

    async def test_page_and_resource_use_verified_addresses_for_fake_ip(self) -> None:
        transport = FixtureTransport({
            "https://example.com/": RawHttpResponse(
                200, {"content-type": "text/html"}, b"<html><head><title>Example</title></head></html>"
            ),
            "https://example.com/robots.txt": RawHttpResponse(
                200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n"
            ),
        })
        lookup = AsyncMock(return_value=["93.184.216.34"])
        with patch("codex_seo_mcp.clients.page_html.resolve_fake_ip", lookup):
            page = await PageInspectionAdapter(
                PageHtmlClient(resolver=fake_ip_resolver, transport=transport)
            ).inspect("https://example.com/")
            resource = await ResourceInspectionAdapter(
                ResourceHttpClient(resolver=fake_ip_resolver, transport=transport)
            ).inspect("https://example.com/robots.txt", resource_type="robots")

        self.assertEqual(page.data.title, "Example")
        self.assertEqual(resource.data.status_code, 200)
        self.assertEqual(lookup.await_count, 2)
        self.assertEqual(transport.calls, [
            ("https://example.com/", ["93.184.216.34"]),
            ("https://example.com/robots.txt", ["93.184.216.34"]),
        ])

    async def test_fake_ip_with_private_public_dns_answer_is_rejected(self) -> None:
        transport = FixtureTransport({})
        with patch(
            "codex_seo_mcp.clients.page_html.resolve_fake_ip",
            AsyncMock(return_value=["93.184.216.34", "10.0.0.1"]),
        ), self.assertRaises(SeoDataError) as caught:
            await PageHtmlClient(resolver=fake_ip_resolver, transport=transport).fetch(
                "https://example.com/"
            )
        self.assertEqual(caught.exception.code, "access_forbidden")
        self.assertEqual(transport.calls, [])

    async def test_fake_ip_literal_and_shared_private_range_remain_blocked(self) -> None:
        transport = FixtureTransport({})
        with patch("codex_seo_mcp.clients.page_html.resolve_fake_ip", new_callable=AsyncMock) as lookup:
            for url in ("http://198.18.0.1/", "http://100.64.0.1/", "http://127.0.0.1/"):
                with self.subTest(url=url), self.assertRaises(SeoDataError) as caught:
                    await PageHtmlClient(transport=transport).fetch(url)
                self.assertEqual(caught.exception.code, "access_forbidden")
        lookup.assert_not_awaited()
        self.assertEqual(transport.calls, [])

    async def test_internal_names_are_not_sent_to_public_dns(self) -> None:
        transport = FixtureTransport({})
        with patch("codex_seo_mcp.clients.page_html.resolve_fake_ip", new_callable=AsyncMock) as lookup:
            for url in (
                "http://intranet/", "http://secret.internal/", "http://secret.internal./",
                "http://machine.lan/",
            ):
                with self.subTest(url=url), self.assertRaises(SeoDataError) as caught:
                    await PageHtmlClient(resolver=fake_ip_resolver, transport=transport).fetch(url)
                self.assertEqual(caught.exception.code, "access_forbidden")
        lookup.assert_not_awaited()
        self.assertEqual(transport.calls, [])

    async def test_fake_ip_redirect_to_private_target_is_blocked_before_second_request(self) -> None:
        transport = FixtureTransport({
            "https://example.com/": RawHttpResponse(
                302, {"location": "http://127.0.0.1/private"}, b""
            ),
        })
        with patch(
            "codex_seo_mcp.clients.page_html.resolve_fake_ip",
            AsyncMock(return_value=["93.184.216.34"]),
        ), self.assertRaises(SeoDataError) as caught:
            await PageHtmlClient(resolver=fake_ip_resolver, transport=transport).fetch(
                "https://example.com/"
            )
        self.assertEqual(caught.exception.code, "access_forbidden")
        self.assertEqual(transport.calls, [("https://example.com/", ["93.184.216.34"])])

    async def test_mixed_fake_and_private_system_answers_do_not_use_fallback(self) -> None:
        async def mixed_resolver(_host: str) -> list[str]:
            return ["198.18.0.1", "192.168.1.1"]

        with (
            patch("codex_seo_mcp.clients.page_html.resolve_fake_ip", new_callable=AsyncMock) as lookup,
            self.assertRaises(SeoDataError) as caught,
        ):
            await PageHtmlClient(resolver=mixed_resolver, transport=FixtureTransport({})).fetch(
                "https://example.com/"
            )
        self.assertEqual(caught.exception.code, "access_forbidden")
        lookup.assert_not_awaited()

    async def test_pinned_http_connects_to_verified_ip_and_keeps_host_header(self) -> None:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        server_port = listener.getsockname()[1]
        received: list[bytes] = []
        targets: list[tuple[str, int]] = []
        original_connect = socket.create_connection

        def serve() -> None:
            with listener, listener.accept()[0] as client:
                data = b""
                while b"\r\n\r\n" not in data:
                    data += client.recv(4096)
                received.append(data)
                client.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")

        def connect(target, timeout, source_address):
            targets.append(target)
            return original_connect(("127.0.0.1", server_port), timeout, source_address)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        with (
            patch("codex_seo_mcp.clients.page_html.getproxies", return_value={}),
            patch("codex_seo_mcp.clients.page_html.socket.create_connection", side_effect=connect),
        ):
            result = await UrllibTransport().get(
                "http://example.com/robots.txt", config=PageHtmlConfig(),
                pinned_addresses=["93.184.216.34"],
            )
        thread.join(timeout=2)

        self.assertEqual(result.status_code, 200)
        self.assertEqual(targets, [("93.184.216.34", 80)])
        self.assertIn(b"Host: example.com\r\n", received[0])
        self.assertIn(b"GET /robots.txt HTTP/1.1\r\n", received[0])

    async def test_explicit_proxy_does_not_bypass_address_pinning(self) -> None:
        with (
            patch("codex_seo_mcp.clients.page_html.getproxies", return_value={"https": "http://127.0.0.1:7890"}),
            patch("codex_seo_mcp.clients.page_html.proxy_bypass", return_value=False),
            self.assertRaises(SeoDataError) as caught,
        ):
            await UrllibTransport().get(
                "https://example.com/", config=PageHtmlConfig(), pinned_addresses=["93.184.216.34"]
            )
        self.assertEqual(caught.exception.code, "provider_unavailable")

    async def test_pinned_transport_rejects_private_addresses(self) -> None:
        with self.assertRaises(SeoDataError) as caught:
            await UrllibTransport().get(
                "http://example.com/", config=PageHtmlConfig(), pinned_addresses=["127.0.0.1"]
            )
        self.assertEqual(caught.exception.code, "access_forbidden")
