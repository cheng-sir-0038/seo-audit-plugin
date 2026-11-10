from __future__ import annotations

import unittest
from unittest.mock import patch

from codex_seo_mcp import server
from codex_seo_mcp.adapters.page_inspection import PageInspectionAdapter
from codex_seo_mcp.adapters.resource_inspection import ResourceInspectionAdapter
from codex_seo_mcp.clients.page_html import PageHtmlClient, RawHttpResponse
from codex_seo_mcp.clients.resource_http import ResourceHttpClient
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from mcp import Client


class FixtureTransport:
    def __init__(self, responses: dict[str, RawHttpResponse]) -> None:
        self.responses = responses
        self.requests: list[str] = []

    async def get(self, url: str, *, config) -> RawHttpResponse:
        self.requests.append(url)
        if url not in self.responses:
            raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "fixture unavailable")
        return self.responses[url]


async def public_resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def adapters(responses: dict[str, RawHttpResponse]):
    transport = FixtureTransport(responses)
    page = PageInspectionAdapter(PageHtmlClient(resolver=public_resolver, transport=transport))
    resource = ResourceInspectionAdapter(
        ResourceHttpClient(resolver=public_resolver, transport=transport)
    )
    return transport, page, resource


PAGE = RawHttpResponse(
    200,
    {"content-type": "text/html"},
    b"<html><head><title>Example</title></head><body><h1>Example</h1></body></html>",
)
SITEMAP = RawHttpResponse(
    200,
    {"content-type": "application/xml"},
    b"<urlset><url><loc>https://example.com/</loc></url></urlset>",
)


class SiteAuditWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_workflow_fetches_page_robots_and_declared_sitemap(self) -> None:
        transport, page, resource = adapters({
            "https://example.com/": PAGE,
            "https://example.com/robots.txt": RawHttpResponse(
                200, {"content-type": "text/plain"},
                b"User-agent: *\nAllow: /\nSitemap: https://example.com/map.xml\n",
            ),
            "https://example.com/map.xml": SITEMAP,
        })
        with patch.object(server, "_page_inspection", page), patch.object(
            server, "_resource_inspection", resource
        ):
            async with Client(server.mcp) as client:
                result = await client.call_tool("inspect_site_basics", {"url": "https://example.com/"})

        self.assertFalse(result.is_error)
        payload = result.structured_content
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["page"]["data"]["title"], "Example")
        self.assertEqual(payload["robots"]["data"]["status_code"], 200)
        self.assertEqual(payload["sitemap"]["data"]["requested_url"], "https://example.com/map.xml")
        self.assertEqual(payload["sitemap_entry_count"], 1)
        self.assertEqual(transport.requests, [
            "https://example.com/", "https://example.com/robots.txt", "https://example.com/map.xml"
        ])
        self.assertTrue(any("收录" in item for item in payload["limitations"]))

    async def test_robots_failure_keeps_page_and_sitemap_evidence(self) -> None:
        transport, page, resource = adapters({
            "https://example.com/": PAGE,
            "https://example.com/sitemap.xml": SITEMAP,
        })
        with patch.object(server, "_page_inspection", page), patch.object(
            server, "_resource_inspection", resource
        ):
            async with Client(server.mcp) as client:
                result = await client.call_tool("inspect_site_basics", {"url": "https://example.com/"})

        self.assertFalse(result.is_error)
        payload = result.structured_content
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["page"]["data"]["title"], "Example")
        self.assertEqual(payload["robots"]["error"]["code"], "provider_unavailable")
        self.assertEqual(payload["sitemap"]["data"]["status_code"], 200)
        self.assertIn("https://example.com/sitemap.xml", transport.requests)

    async def test_does_not_fetch_foreign_declared_sitemap(self) -> None:
        transport, page, resource = adapters({
            "https://example.com/": PAGE,
            "https://example.com/robots.txt": RawHttpResponse(
                200, {"content-type": "text/plain"},
                b"User-agent: *\nSitemap: https://other.example/map.xml\n",
            ),
            "https://example.com/sitemap.xml": SITEMAP,
        })
        with patch.object(server, "_page_inspection", page), patch.object(
            server, "_resource_inspection", resource
        ):
            async with Client(server.mcp) as client:
                result = await client.call_tool("inspect_site_basics", {"url": "https://example.com/"})

        self.assertFalse(result.is_error)
        self.assertNotIn("https://other.example/map.xml", transport.requests)
        self.assertTrue(any("跨站" in item for item in result.structured_content["limitations"]))

    async def test_private_target_is_rejected_before_transport(self) -> None:
        transport, page, resource = adapters({})
        with patch.object(server, "_page_inspection", page), patch.object(
            server, "_resource_inspection", resource
        ):
            async with Client(server.mcp) as client:
                result = await client.call_tool("inspect_site_basics", {"url": "http://127.0.0.1/"})

        self.assertTrue(result.is_error)
        self.assertIn("[access_forbidden]", result.content[0].text)
        self.assertEqual(transport.requests, [])

    async def test_malformed_sitemap_directive_keeps_other_evidence(self) -> None:
        transport, page, resource = adapters({
            "https://example.com/": PAGE,
            "https://example.com/robots.txt": RawHttpResponse(
                200, {"content-type": "text/plain"},
                b"User-agent: *\nSitemap: http://[invalid\n",
            ),
            "https://example.com/sitemap.xml": SITEMAP,
        })
        with patch.object(server, "_page_inspection", page), patch.object(
            server, "_resource_inspection", resource
        ):
            async with Client(server.mcp) as client:
                result = await client.call_tool("inspect_site_basics", {"url": "https://example.com/"})

        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["status"], "partial")
        self.assertEqual(result.structured_content["page"]["data"]["title"], "Example")
        self.assertTrue(any("无效" in item for item in result.structured_content["limitations"]))
        self.assertIn("https://example.com/sitemap.xml", transport.requests)

    async def test_robots_http_error_is_partial_even_when_resource_was_read(self) -> None:
        _, page, resource = adapters({
            "https://example.com/": PAGE,
            "https://example.com/robots.txt": RawHttpResponse(
                403, {"content-type": "text/plain"}, b"Forbidden"
            ),
            "https://example.com/sitemap.xml": SITEMAP,
        })
        with patch.object(server, "_page_inspection", page), patch.object(
            server, "_resource_inspection", resource
        ):
            async with Client(server.mcp) as client:
                result = await client.call_tool("inspect_site_basics", {"url": "https://example.com/"})

        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["status"], "partial")
        self.assertEqual(result.structured_content["robots"]["data"]["status_code"], 403)
        self.assertEqual(result.structured_content["sitemap"]["data"]["status_code"], 200)

    async def test_cross_origin_redirect_is_reported_and_does_not_expand_scope(self) -> None:
        transport, page, resource = adapters({
            "https://example.com/": PAGE,
            "https://example.com/robots.txt": RawHttpResponse(
                302, {"location": "https://other.example/robots.txt"}, b""
            ),
            "https://other.example/robots.txt": RawHttpResponse(
                200, {"content-type": "text/plain"},
                b"User-agent: *\nSitemap: https://other.example/map.xml\n",
            ),
            "https://example.com/sitemap.xml": SITEMAP,
        })
        with patch.object(server, "_page_inspection", page), patch.object(
            server, "_resource_inspection", resource
        ):
            async with Client(server.mcp) as client:
                result = await client.call_tool("inspect_site_basics", {"url": "https://example.com/"})

        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["status"], "partial")
        self.assertTrue(any("跨站重定向" in item for item in result.structured_content["limitations"]))
        self.assertNotIn("https://other.example/map.xml", transport.requests)
        self.assertIn("https://example.com/sitemap.xml", transport.requests)
