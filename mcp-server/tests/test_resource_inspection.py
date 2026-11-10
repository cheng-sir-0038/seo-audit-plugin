from __future__ import annotations

import unittest

from codex_seo_mcp.adapters.resource_inspection import ResourceInspectionAdapter
from codex_seo_mcp.clients.resource_http import FetchedResource, ResourceHttpClient
from codex_seo_mcp.clients.page_html import RawHttpResponse


PUBLIC_IPS = ["93.184.216.34"]


class FakeTransport:
    def __init__(self, responses: dict[str, RawHttpResponse]) -> None:
        self.responses = responses

    async def get(self, url: str, *, config, pinned_addresses) -> RawHttpResponse:  # noqa: ANN001
        return self.responses[url]


async def public_resolver(_host: str) -> list[str]:
    return PUBLIC_IPS


class ResourceInspectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_robots_groups_and_sitemap_directives(self) -> None:
        transport = FakeTransport(
            {
                "https://example.com/robots.txt": RawHttpResponse(
                    200,
                    {"content-type": "text/plain; charset=utf-8"},
                    b"""User-agent: Googlebot\nDisallow: /private/\n\nUser-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n""",
                )
            }
        )
        adapter = ResourceInspectionAdapter(
            ResourceHttpClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/robots.txt", resource_type="robots")

        self.assertEqual(result.capability, "ResourceInspection")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.resource_type, "robots")
        self.assertEqual(len(result.data.robots.groups), 2)
        self.assertEqual(result.data.robots.groups[0].user_agents, ["Googlebot"])
        self.assertEqual(result.data.robots.groups[0].rules[0].directive, "disallow")
        self.assertEqual(result.data.robots.sitemaps, ["https://example.com/sitemap.xml"])

    async def test_parses_sitemap_index_without_treating_it_as_html(self) -> None:
        transport = FakeTransport(
            {
                "https://example.com/sitemap.xml": RawHttpResponse(
                    200,
                    {"content-type": "application/xml"},
                    b"""<?xml version="1.0" encoding="UTF-8"?>
                    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                      <sitemap><loc>https://example.com/products.xml</loc><lastmod>2026-09-01</lastmod></sitemap>
                      <sitemap><loc>https://example.com/blog.xml</loc></sitemap>
                    </sitemapindex>""",
                )
            }
        )
        adapter = ResourceInspectionAdapter(
            ResourceHttpClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/sitemap.xml", resource_type="sitemap")

        self.assertEqual(result.data.resource_type, "sitemap")
        self.assertEqual(result.data.sitemap.kind, "sitemapindex")
        self.assertEqual(
            [entry.loc for entry in result.data.sitemap.entries],
            ["https://example.com/products.xml", "https://example.com/blog.xml"],
        )
        self.assertEqual(result.data.sitemap.entries[0].lastmod, "2026-09-01")

    async def test_auto_detects_robots_from_path(self) -> None:
        transport = FakeTransport(
            {
                "https://example.com/robots.txt": RawHttpResponse(
                    200,
                    {"content-type": "text/plain"},
                    b"User-agent: *\nDisallow:\n",
                )
            }
        )
        adapter = ResourceInspectionAdapter(
            ResourceHttpClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/robots.txt")

        self.assertEqual(result.data.resource_type, "robots")

    async def test_rejects_generic_html_page_as_seo_resource(self) -> None:
        transport = FakeTransport(
            {
                "https://example.com/page": RawHttpResponse(
                    200,
                    {"content-type": "text/html"},
                    b"<html><body>page</body></html>",
                )
            }
        )
        adapter = ResourceInspectionAdapter(
            ResourceHttpClient(resolver=public_resolver, transport=transport)
        )

        with self.assertRaisesRegex(Exception, "不是 robots.txt 或 sitemap"):
            await adapter.inspect("https://example.com/page")


if __name__ == "__main__":
    unittest.main()
