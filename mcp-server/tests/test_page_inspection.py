from __future__ import annotations

from dataclasses import MISSING, fields
import unittest

from codex_seo_mcp.adapters.page_inspection import PageInspectionAdapter
from codex_seo_mcp.clients.page_html import PageHtmlClient, RawHttpResponse
from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.models.page_inspection import PageInspection


PUBLIC_IPS = ["93.184.216.34"]
PRIVATE_IPS = ["127.0.0.1"]


class FakeTransport:
    def __init__(self, responses: dict[str, RawHttpResponse]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []

    async def get(self, url: str, *, config, pinned_addresses) -> RawHttpResponse:  # noqa: ANN001
        self.requested_urls.append(url)
        try:
            return self.responses[url]
        except KeyError as exc:
            raise AssertionError(f"测试未配置 URL：{url}") from exc


async def public_resolver(_host: str) -> list[str]:
    return PUBLIC_IPS


class PageInspectionTests(unittest.IsolatedAsyncioTestCase):
    def test_page_inspection_contract_has_no_legacy_compatibility_fields(self) -> None:
        """开发阶段只维护当前 PageInspection Contract，不保留旧字段/可省略新字段。"""

        contract_fields = {item.name: item for item in fields(PageInspection)}

        self.assertNotIn("redirect_chain", contract_fields)
        self.assertIn("redirects", contract_fields)
        self.assertIn("hreflang_alternates", contract_fields)
        self.assertIs(contract_fields["hreflang_alternates"].default, MISSING)
        self.assertIs(contract_fields["hreflang_alternates"].default_factory, MISSING)
        self.assertIn("anchor_links", contract_fields)
        self.assertIs(contract_fields["anchor_links"].default, MISSING)
        self.assertIn("rel_next_urls", contract_fields)
        self.assertIs(contract_fields["rel_next_urls"].default, MISSING)
        self.assertIn("rel_prev_urls", contract_fields)
        self.assertIs(contract_fields["rel_prev_urls"].default, MISSING)
        self.assertIn("structured_data", contract_fields)
        self.assertIs(contract_fields["structured_data"].default, MISSING)
        self.assertIs(contract_fields["structured_data"].default_factory, MISSING)

    async def test_returns_runtime_page_facts(self) -> None:
        """PageInspection 应返回真实页面事实，而不是生成 SEO 结论。"""

        transport = FakeTransport(
            {
                "https://example.com/products/a": RawHttpResponse(
                    status_code=200,
                    headers={
                        "content-type": "text/html; charset=utf-8",
                        "x-robots-tag": "index, follow",
                    },
                    body="""
                    <html lang="zh-CN"><head>
                      <title>产品 A</title>
                      <meta name="description" content="产品 A 描述">
                      <link rel="canonical" href="/products/a">
                    </head><body><h1>产品 A</h1></body></html>
                    """.encode(),
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/products/a")

        self.assertEqual(result.capability, "PageInspection")
        self.assertEqual(result.provider, "page-html")
        self.assertEqual(result.source_kind, "runtime")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.title, "产品 A")
        self.assertEqual(result.data.meta_description, "产品 A 描述")
        self.assertEqual(result.data.canonical, "https://example.com/products/a")
        self.assertEqual(result.data.h1, ["产品 A"])
        self.assertEqual(result.data.lang, "zh-CN")
        self.assertFalse(result.data.declared_noindex)

    async def test_extracts_crawlable_anchor_links_and_explicit_rel_navigation(self) -> None:
        transport = FakeTransport(
            {
                "https://example.com/list?page=2": RawHttpResponse(
                    200,
                    {"content-type": "text/html"},
                    b"""
                    <html><head><title>List</title>
                      <link rel="prev" href="?page=1#top">
                    </head><body><h1>List</h1>
                      <a href="/product/a#details">A</a>
                      <a href="?page=3" rel="next">Next</a>
                      <a href="?page=4">4</a>
                      <a href="https://other.example/path#x">External</a>
                      <a href="#section">Section</a>
                      <a href="mailto:hello@example.com">Mail</a>
                      <a href="javascript:void(0)">JS</a>
                    </body></html>
                    """,
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/list?page=2")

        self.assertEqual(
            result.data.anchor_links,
            [
                "https://example.com/product/a",
                "https://example.com/list?page=3",
                "https://example.com/list?page=4",
                "https://other.example/path",
            ],
        )
        self.assertEqual(result.data.rel_next_urls, ["https://example.com/list?page=3"])
        self.assertEqual(result.data.rel_prev_urls, ["https://example.com/list?page=1"])

    async def test_ignores_svg_title_when_counting_document_titles(self) -> None:
        """SVG <title> 是图形无障碍名称，不是 HTML document title。"""

        transport = FakeTransport(
            {
                "https://example.com/": RawHttpResponse(
                    200,
                    {"content-type": "text/html"},
                    b"""
                    <html><head><title>Document title</title></head><body>
                      <svg><title>Icon one</title><path d=""></path></svg>
                      <svg><g><title>Icon two</title></g></svg>
                      <h1>Home</h1>
                    </body></html>
                    """,
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/")

        self.assertEqual(result.data.title, "Document title")
        self.assertEqual(result.data.title_count, 1)
        self.assertFalse(any("多个 Title" in item for item in result.warnings))

    async def test_preserves_html_hreflang_alternates(self) -> None:
        transport = FakeTransport(
            {
                "https://example.com/en/page": RawHttpResponse(
                    200,
                    {"content-type": "text/html"},
                    b"""
                    <html lang="en"><head><title>EN</title>
                    <link rel="canonical" href="/en/page">
                    <link rel="alternate" hreflang="en" href="/en/page">
                    <link rel="alternate" hreflang="de-DE" href="/de/page">
                    <link rel="alternate" hreflang="x-default" href="/">
                    </head><body><h1>EN</h1></body></html>
                    """,
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/en/page")

        self.assertEqual(
            [(item.hreflang, item.url, item.source) for item in result.data.hreflang_alternates],
            [
                ("en", "https://example.com/en/page", "html"),
                ("de-DE", "https://example.com/de/page", "html"),
                ("x-default", "https://example.com/", "html"),
            ],
        )

    async def test_preserves_repeated_http_link_hreflang_headers(self) -> None:
        transport = FakeTransport(
            {
                "https://example.com/en/page": RawHttpResponse(
                    200,
                    {"content-type": "text/html"},
                    b"<html><head><title>EN</title></head><body><h1>EN</h1></body></html>",
                    header_values={
                        "content-type": ["text/html"],
                        "link": [
                            '<https://example.com/en/page>; rel="alternate"; hreflang="en"',
                            '<https://example.com/de/page>; rel="alternate"; hreflang="de-DE", <https://example.com/>; rel="alternate"; hreflang="x-default"',
                        ],
                    },
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/en/page")

        self.assertEqual(
            [(item.hreflang, item.url, item.source) for item in result.data.hreflang_alternates],
            [
                ("en", "https://example.com/en/page", "http_header"),
                ("de-DE", "https://example.com/de/page", "http_header"),
                ("x-default", "https://example.com/", "http_header"),
            ],
        )


    async def test_warning_policy_preserves_existing_order(self) -> None:
        transport = FakeTransport(
            {
                "https://example.com/problem": RawHttpResponse(
                    500,
                    {"content-type": "text/html"},
                    b"""
                    <html><head>
                      <meta name="robots" content="noindex">
                      <meta http-equiv="refresh" content="0;url=/other">
                      <link rel="canonical" href="/a">
                      <link rel="canonical" href="/b">
                    </head><body></body></html>
                    """,
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/problem")

        self.assertEqual(
            result.warnings,
            [
                "页面返回 HTTP 500，当前 HTML 可能是错误页或中间页。",
                "页面 HTML 中没有非空 Title。",
                "页面 HTML 中没有非空 Meta Description。",
                "页面存在多个 Canonical 声明。",
                "页面 HTML 中没有 H1。",
                "页面声明了 noindex，需要确认该页面是否本来就不应被索引。",
                "页面存在 Meta Refresh，需要确认是否应该改为服务端重定向或保留现状。",
            ],
        )

    async def test_preserves_redirect_and_noindex_facts(self) -> None:
        """重定向和 noindex 必须原样交给诊断层。"""

        transport = FakeTransport(
            {
                "https://example.com/old": RawHttpResponse(
                    301, {"location": "/new"}, b""
                ),
                "https://example.com/new": RawHttpResponse(
                    200,
                    {"content-type": "text/html", "x-robots-tag": "noindex"},
                    b"""
                    <html><head><title>New</title>
                    <meta name="robots" content="index,follow">
                    <meta http-equiv="refresh" content="10; url=/later">
                    </head><body><h1>New</h1></body></html>
                    """,
                ),
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/old")

        self.assertEqual(result.data.final_url, "https://example.com/new")
        self.assertEqual(
            [
                (
                    item.from_url,
                    item.status_code,
                    item.location,
                    item.to_url,
                )
                for item in result.data.redirects
            ],
            [
                (
                    "https://example.com/old",
                    301,
                    "/new",
                    "https://example.com/new",
                )
            ],
        )
        self.assertTrue(result.data.declared_noindex)
        self.assertEqual(result.data.meta_refresh_url, "https://example.com/later")
        self.assertTrue(any("noindex" in item for item in result.warnings))
        self.assertTrue(any("Meta Refresh" in item for item in result.warnings))

    async def test_preserves_each_redirect_status_in_multi_hop_chain(self) -> None:
        """URL Lifecycle 不能从 URL-only chain 猜永久/临时跳转类型。"""

        transport = FakeTransport(
            {
                "https://example.com/a": RawHttpResponse(301, {"location": "/b"}, b""),
                "https://example.com/b": RawHttpResponse(302, {"location": "/c"}, b""),
                "https://example.com/c": RawHttpResponse(
                    200,
                    {"content-type": "text/html"},
                    b"<html><head><title>C</title></head><body><h1>C</h1></body></html>",
                ),
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/a")

        self.assertEqual(
            [(item.status_code, item.from_url, item.to_url) for item in result.data.redirects],
            [
                (301, "https://example.com/a", "https://example.com/b"),
                (302, "https://example.com/b", "https://example.com/c"),
            ],
        )

    async def test_later_robots_noindex_overrides_earlier_index(self) -> None:
        """多个 robots 声明必须按有效限制聚合，不能只看第一条。"""

        transport = FakeTransport(
            {
                "https://example.com/a": RawHttpResponse(
                    200,
                    {"content-type": "text/html"},
                    b"""
                    <html><head><title>A</title>
                    <meta name="robots" content="index,follow">
                    <meta name="robots" content="noindex,follow">
                    </head><body><h1>A</h1></body></html>
                    """,
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/a")

        self.assertEqual(
            result.data.robots_meta_tags,
            ["index,follow", "noindex,follow"],
        )
        self.assertTrue(result.data.declared_noindex)

    async def test_none_directive_is_effective_noindex(self) -> None:
        """Google robots `none` 等价于 noindex,nofollow，不能被漏判。"""

        transport = FakeTransport(
            {
                "https://example.com/a": RawHttpResponse(
                    200,
                    {"content-type": "text/html"},
                    b"""
                    <html><head><title>A</title>
                    <meta name="googlebot" content="none">
                    </head><body><h1>A</h1></body></html>
                    """,
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/a")

        self.assertEqual(result.data.googlebot_meta_tags, ["none"])
        self.assertTrue(result.data.declared_noindex)

    async def test_preserves_repeated_x_robots_tag_values(self) -> None:
        """重复 X-Robots-Tag 不能在 transport dict 化时丢失限制更严的值。"""

        transport = FakeTransport(
            {
                "https://example.com/a": RawHttpResponse(
                    200,
                    {"content-type": "text/html", "x-robots-tag": "index,follow"},
                    b"<html><head><title>A</title></head><body><h1>A</h1></body></html>",
                    header_values={
                        "content-type": ["text/html"],
                        "x-robots-tag": ["index,follow", "noindex"],
                    },
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        result = await adapter.inspect("https://example.com/a")

        self.assertEqual(result.data.x_robots_tags, ["index,follow", "noindex"])
        self.assertTrue(result.data.declared_noindex)

    async def test_blocks_private_network_targets(self) -> None:
        """公开 URL 工具默认不能访问宿主机和内网。"""

        async def private_resolver(_host: str) -> list[str]:
            return PRIVATE_IPS

        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=private_resolver, transport=FakeTransport({}))
        )

        with self.assertRaises(SeoDataError) as caught:
            await adapter.inspect("http://internal.example/")

        self.assertEqual(caught.exception.code, "access_forbidden")

    async def test_rechecks_redirect_target_network_boundary(self) -> None:
        """跳转到私网时必须在真正发起第二次 HTTP 请求前终止。"""

        async def resolver(host: str) -> list[str]:
            return PUBLIC_IPS if host == "example.com" else PRIVATE_IPS

        transport = FakeTransport(
            {
                "https://example.com/start": RawHttpResponse(
                    302, {"location": "http://internal.example/secret"}, b""
                )
            }
        )
        adapter = PageInspectionAdapter(PageHtmlClient(resolver=resolver, transport=transport))

        with self.assertRaises(SeoDataError) as caught:
            await adapter.inspect("https://example.com/start")

        self.assertEqual(caught.exception.code, "access_forbidden")
        self.assertEqual(transport.requested_urls, ["https://example.com/start"])

    async def test_rejects_non_html_response(self) -> None:
        """PDF/图片等响应不能伪装成 PageInspection。"""

        transport = FakeTransport(
            {
                "https://example.com/file.pdf": RawHttpResponse(
                    200, {"content-type": "application/pdf"}, b"%PDF-1.7"
                )
            }
        )
        adapter = PageInspectionAdapter(
            PageHtmlClient(resolver=public_resolver, transport=transport)
        )

        with self.assertRaises(SeoDataError) as caught:
            await adapter.inspect("https://example.com/file.pdf")

        self.assertEqual(caught.exception.code, "data_unavailable")

# Structured-data extraction tests are kept here because PageInspection owns delivered JSON-LD facts.
class PageInspectionStructuredDataTests(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_valid_json_ld_types(self) -> None:
        transport = FakeTransport({
            "https://example.com/product": RawHttpResponse(
                200,
                {"content-type": "text/html"},
                b'''<html><head><title>P</title><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"P"}</script></head><body><h1>P</h1></body></html>''',
            )
        })
        adapter = PageInspectionAdapter(PageHtmlClient(resolver=public_resolver, transport=transport))
        result = await adapter.inspect("https://example.com/product")
        self.assertEqual(len(result.data.structured_data), 1)
        block = result.data.structured_data[0]
        self.assertTrue(block.valid)
        self.assertEqual(block.types, ["Product"])
        self.assertEqual(block.nodes[0].types, ["Product"])
        self.assertIn("name", block.nodes[0].property_paths)

    async def test_preserves_invalid_json_ld_as_fact(self) -> None:
        transport = FakeTransport({
            "https://example.com/bad": RawHttpResponse(
                200,
                {"content-type": "text/html"},
                b'''<html><head><title>B</title><script type="application/ld+json">{"@type":"Article",}</script></head><body><h1>B</h1></body></html>''',
            )
        })
        adapter = PageInspectionAdapter(PageHtmlClient(resolver=public_resolver, transport=transport))
        result = await adapter.inspect("https://example.com/bad")
        block = result.data.structured_data[0]
        self.assertFalse(block.valid)
        self.assertIsNotNone(block.parse_error)

    async def test_extracts_types_from_json_ld_graph(self) -> None:
        transport = FakeTransport({
            "https://example.com/": RawHttpResponse(
                200,
                {"content-type": "text/html"},
                b'''<html><head><title>H</title><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Organization"},{"@type":["WebSite","Thing"]}]}</script></head><body><h1>H</h1></body></html>''',
            )
        })
        adapter = PageInspectionAdapter(PageHtmlClient(resolver=public_resolver, transport=transport))
        result = await adapter.inspect("https://example.com/")
        self.assertEqual(result.data.structured_data[0].types, ["Organization", "WebSite", "Thing"])
        self.assertEqual(
            [node.types for node in result.data.structured_data[0].nodes],
            [["Organization"], ["WebSite", "Thing"]],
        )

    async def test_extracts_breadcrumb_property_paths_without_storing_full_json_ld(self) -> None:
        transport = FakeTransport({
            "https://example.com/p": RawHttpResponse(
                200,
                {"content-type": "text/html"},
                b'''<html><head><title>P</title><script type="application/ld+json">{
                  "@context":"https://schema.org",
                  "@type":"BreadcrumbList",
                  "itemListElement":[
                    {"@type":"ListItem","position":1,"name":"Home","item":"https://example.com/"},
                    {"@type":"ListItem","position":2,"name":"P"}
                  ]
                }</script></head><body><h1>P</h1></body></html>''',
            )
        })
        adapter = PageInspectionAdapter(PageHtmlClient(resolver=public_resolver, transport=transport))

        result = await adapter.inspect("https://example.com/p")
        node = result.data.structured_data[0].nodes[0]

        self.assertEqual(node.types, ["BreadcrumbList"])
        self.assertIn("itemListElement[0].position", node.property_paths)
        self.assertIn("itemListElement[0].name", node.property_paths)
        self.assertIn("itemListElement[0].item", node.property_paths)
        self.assertIn("itemListElement[1].position", node.property_paths)
        self.assertIn("itemListElement[1].name", node.property_paths)
