from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp_types import ElicitResult

from codex_seo_mcp import server as server_module
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class McpServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_maps_public_data_error_to_native_mcp_error(self) -> None:
        fake_page_inspection = AsyncMock()
        fake_page_inspection.inspect.side_effect = SeoDataError(
            SeoDataErrorCode.INVALID_REQUEST,
            "bad page request",
        )

        with patch.object(server_module, "_page_inspection", fake_page_inspection):
            async with Client(server_module.mcp) as client:
                result = await client.call_tool("inspect_page", {"url": "https://example.com"})

        self.assertTrue(result.is_error)
        self.assertIsNone(result.structured_content)
        self.assertIn("[invalid_request] bad page request", result.content[0].text)

    async def test_exposes_only_current_tools_and_reports_gsc_not_configured(self) -> None:
        """MCP Host 应看到真实已实现工具；没有 OAuth Client 时明确返回 not_configured。"""

        # 测试不能读取开发者真实 `.local` OAuth 配置，否则换一台机器状态就会漂移。
        fake_gsc = AsyncMock()
        fake_gsc.connection_status.return_value = {"status": "not_configured"}
        fake_ga4 = AsyncMock()
        fake_ga4.connection_status.return_value = {"status": "not_configured"}
        with (
            patch.object(server_module, "_gsc", fake_gsc),
            patch.object(server_module, "_ga4", fake_ga4),
        ):
            async with Client(server_module.mcp) as client:
                listed = await client.list_tools()
                self.assertEqual(
                    sorted(tool.name for tool in listed.tools),
                    [
                        "analyze_organic_traffic",
                        "analyze_rankings",
                        "analyze_search_console",
                        "check_analytics_connection",
                        "check_page_performance",
                        "check_rich_results",
                        "check_search_console_connection",
                        "check_site_safety",
                        "connect_analytics",
                        "connect_search_console",
                        "inspect_google_index",
                        "inspect_page",
                        "inspect_robots_sitemap",
                        "inspect_site_basics",
                        "list_analytics_properties",
                        "list_search_console_sites",
                        "research_competitors",
                        "research_keywords",
                        "research_serp",
                    ],
                )
                titles = {tool.name: tool.title for tool in listed.tools}
                self.assertEqual(titles["inspect_page"], "页面 SEO 检查")
                self.assertEqual(titles["inspect_site_basics"], "网站 SEO 基础检查")
                self.assertEqual(titles["inspect_google_index"], "Google 收录检查")
                self.assertEqual(titles["inspect_robots_sitemap"], "Robots / Sitemap 检查")
                self.assertEqual(titles["check_page_performance"], "页面性能检查")
                self.assertEqual(titles["check_rich_results"], "富媒体结果检查")
                self.assertEqual(titles["check_site_safety"], "网站安全检查")
                self.assertEqual(titles["analyze_search_console"], "Google 搜索表现")
                self.assertEqual(titles["analyze_rankings"], "自然排名与可见性")
                self.assertEqual(titles["research_keywords"], "关键词研究")
                self.assertEqual(titles["research_competitors"], "竞品 SEO 研究")
                self.assertEqual(titles["research_serp"], "搜索结果研究")
                self.assertEqual(titles["check_analytics_connection"], "GA4 连接状态")
                self.assertEqual(titles["connect_analytics"], "连接 GA4")
                gsc_properties = next(
                    tool for tool in listed.tools if tool.name == "list_search_console_sites"
                )
                self.assertIn("target", gsc_properties.input_schema.get("properties", {}))
                search_performance = next(
                    tool for tool in listed.tools if tool.name == "analyze_search_console"
                )
                self.assertTrue(
                    {"target", "start_date", "end_date"}
                    <= set(search_performance.input_schema.get("required", []))
                )
                self.assertNotIn("property_url", search_performance.input_schema.get("properties", {}))
                self.assertNotIn("scope", search_performance.input_schema.get("properties", {}))
                index_inspection = next(
                    tool for tool in listed.tools if tool.name == "inspect_google_index"
                )
                self.assertIn("inspection_url", index_inspection.input_schema.get("required", []))
                self.assertNotIn("property_url", index_inspection.input_schema.get("properties", {}))
                self.assertNotIn("scope", index_inspection.input_schema.get("properties", {}))
                self.assertEqual(titles["list_analytics_properties"], "GA4 媒体资源列表")
                analytics_properties = next(
                    tool for tool in listed.tools if tool.name == "list_analytics_properties"
                )
                self.assertIn("domain", analytics_properties.input_schema.get("properties", {}))
                self.assertEqual(titles["analyze_organic_traffic"], "自然流量与转化")
                page_quality = next(tool for tool in listed.tools if tool.name == "check_page_performance")
                self.assertIn("strategy", page_quality.input_schema.get("required", []))
                organic_visibility = next(
                    tool for tool in listed.tools if tool.name == "analyze_rankings"
                )
                self.assertTrue(
                    {"country", "language", "search_engine"}
                    <= set(organic_visibility.input_schema.get("required", []))
                )
                keyword_research = next(
                    tool for tool in listed.tools if tool.name == "research_keywords"
                )
                self.assertTrue(
                    {"country", "language", "search_engine"}
                    <= set(keyword_research.input_schema.get("required", []))
                )
                self.assertNotIn("database", keyword_research.input_schema.get("properties", {}))
                competitor_research = next(
                    tool for tool in listed.tools if tool.name == "research_competitors"
                )
                self.assertTrue(
                    {"country", "language", "search_engine"}
                    <= set(competitor_research.input_schema.get("required", []))
                )
                self.assertNotIn("database", competitor_research.input_schema.get("properties", {}))
                serp_research = next(tool for tool in listed.tools if tool.name == "research_serp")
                self.assertTrue(
                    {"country", "language", "search_engine"}
                    <= set(serp_research.input_schema.get("required", []))
                )
                web_analytics = next(
                    tool for tool in listed.tools if tool.name == "analyze_organic_traffic"
                )
                self.assertTrue(
                    {"target", "start_date", "end_date"}
                    <= set(web_analytics.input_schema.get("required", []))
                )
                self.assertNotIn("property_id", web_analytics.input_schema.get("properties", {}))
                self.assertNotIn("site_domain", web_analytics.input_schema.get("properties", {}))
                self.assertNotIn("scope", web_analytics.input_schema.get("properties", {}))
                self.assertIn("country_codes", web_analytics.input_schema.get("properties", {}))
                self.assertIn("compare_start_date", web_analytics.input_schema.get("properties", {}))
                rich_results = next(
                    tool for tool in listed.tools if tool.name == "check_rich_results"
                )
                self.assertIn("url", rich_results.input_schema.get("required", []))
                self.assertIn("expected_types", rich_results.input_schema.get("properties", {}))
                site_safety = next(
                    tool for tool in listed.tools if tool.name == "check_site_safety"
                )
                self.assertIn("url", site_safety.input_schema.get("required", []))
                inspect_page_tool = next(tool for tool in listed.tools if tool.name == "inspect_page")
                site_basics = next(tool for tool in listed.tools if tool.name == "inspect_site_basics")
                connect_gsc_tool = next(
                    tool for tool in listed.tools if tool.name == "connect_search_console"
                )
                check_gsc_tool = next(
                    tool for tool in listed.tools if tool.name == "check_search_console_connection"
                )
                self.assertTrue(inspect_page_tool.annotations.read_only_hint)
                self.assertTrue(inspect_page_tool.annotations.open_world_hint)
                self.assertTrue(site_basics.annotations.read_only_hint)
                self.assertTrue(site_basics.annotations.open_world_hint)
                self.assertIn("url", site_basics.input_schema.get("required", []))
                self.assertTrue(check_gsc_tool.annotations.read_only_hint)
                self.assertFalse(check_gsc_tool.annotations.open_world_hint)
                self.assertFalse(connect_gsc_tool.annotations.read_only_hint)
                self.assertFalse(connect_gsc_tool.annotations.destructive_hint)
                self.assertNotIn("approval", connect_gsc_tool.input_schema.get("properties", {}))
                status = await client.call_tool("check_search_console_connection", {})
                self.assertEqual(status.structured_content, {"status": "not_configured"})
                analytics_status = await client.call_tool("check_analytics_connection", {})
                self.assertEqual(analytics_status.structured_content, {"status": "not_configured"})

    async def test_gsc_connect_has_no_nested_form_elicitation(self) -> None:
        fake_gsc = AsyncMock()
        fake_gsc.authorize.return_value = {"status": "connected"}
        elicitation_called = False

        async def unexpected_elicitation(_context, _params):  # noqa: ANN001
            nonlocal elicitation_called
            elicitation_called = True
            raise AssertionError("OAuth connect must use Host Tool Approval, not nested form elicitation")

        with patch.object(server_module, "_gsc", fake_gsc):
            async with Client(
                server_module.mcp,
                mode="2026-07-28",
                elicitation_callback=unexpected_elicitation,
            ) as client:
                result = await client.call_tool("connect_search_console", {})

        self.assertFalse(result.is_error)
        self.assertFalse(elicitation_called)
        fake_gsc.authorize.assert_awaited_once_with()

    async def test_gsc_site_list_resolves_target_without_defaulting_to_first_property(self) -> None:
        fake_gsc = AsyncMock()
        properties = [
            {"property_url": "https://www.site.example/", "permission_level": "siteRestrictedUser"},
            {"property_url": "sc-domain:site.example", "permission_level": "siteRestrictedUser"},
        ]
        fake_gsc.list_properties.return_value = properties
        fake_gsc.resolve_properties_for_target.return_value = [properties[1]]

        with patch.object(server_module, "_gsc", fake_gsc):
            async with Client(server_module.mcp) as client:
                result = await client.call_tool(
                    "list_search_console_sites", {"target": "site.example"}
                )

        self.assertEqual(result.structured_content["match_status"], "matched")
        self.assertEqual(
            result.structured_content["matched_properties"], [properties[1]]
        )
        fake_gsc.resolve_properties_for_target.assert_awaited_once_with("site.example")

    async def test_gsc_site_list_preserves_ambiguous_candidates(self) -> None:
        fake_gsc = AsyncMock()
        matches = [
            {"property_url": "https://www.example.com/", "permission_level": "siteFullUser"},
            {"property_url": "https://shop.example.com/", "permission_level": "siteFullUser"},
        ]
        fake_gsc.resolve_properties_for_target.return_value = matches

        with patch.object(server_module, "_gsc", fake_gsc):
            async with Client(server_module.mcp) as client:
                result = await client.call_tool(
                    "list_search_console_sites", {"target": "example.com"}
                )

        self.assertEqual(result.structured_content["match_status"], "ambiguous")
        self.assertEqual(result.structured_content["matched_properties"], matches)
        fake_gsc.list_properties.assert_not_awaited()

    async def test_ga4_property_list_resolves_domain_without_defaulting_to_first_property(self) -> None:
        fake_ga4 = AsyncMock()
        properties = [
            {
                "property_id": "517883690",
                "property_name": "seo001",
                "account_id": "378893158",
                "account_name": "Personal",
            },
            {
                "property_id": "533923277",
                "property_name": "Webhub",
                "account_id": "392129637",
                "account_name": "WEBHUB (SINGAPORE) PTE. LTD.",
            },
        ]
        match = {
            **properties[1],
            "web_streams": [
                {
                    "data_stream_id": "14407105327",
                    "display_name": "Webhub Homepage -> uc -> site instance",
                    "type": "WEB_DATA_STREAM",
                    "measurement_id": "G-TF5RTH0BLR",
                    "default_uri": "https://www.site.example",
                }
            ],
        }
        fake_ga4.list_properties.return_value = properties

        async def streams_for_property(property_id: str):
            if property_id == "533923277":
                return match["web_streams"]
            return []

        fake_ga4.list_data_streams.side_effect = streams_for_property

        with patch.object(server_module, "_ga4", fake_ga4):
            async with Client(server_module.mcp) as client:
                result = await client.call_tool(
                    "list_analytics_properties", {"domain": "site.example"}
                )

        self.assertEqual(result.structured_content["match_status"], "matched")
        self.assertEqual(
            result.structured_content["matched_properties"][0]["property_id"],
            "533923277",
        )
        self.assertEqual(result.structured_content["properties"][0]["property_id"], "517883690")
        self.assertEqual(fake_ga4.list_data_streams.await_count, 2)

    async def test_search_console_analysis_elicits_ambiguous_property_before_query(self) -> None:
        fake_gsc = AsyncMock()
        matches = [
            {"property_url": "https://www.example.com/", "permission_level": "siteFullUser"},
            {"property_url": "https://shop.example.com/", "permission_level": "siteFullUser"},
        ]
        fake_gsc.resolve_properties_for_target.return_value = matches
        fake_search_performance = AsyncMock()
        fake_search_performance.query.return_value = SimpleNamespace(
            to_dict=lambda: {"status": "complete", "data": {"rows": []}}
        )
        prompts: list[str] = []

        async def choose_second(_context, params):  # noqa: ANN001
            prompts.append(params.message)
            return ElicitResult(action="accept", content={"choice": 2})

        with (
            patch.object(server_module, "_gsc", fake_gsc),
            patch.object(server_module, "_search_performance", fake_search_performance),
        ):
            async with Client(
                server_module.mcp,
                mode="2026-07-28",
                elicitation_callback=choose_second,
            ) as client:
                result = await client.call_tool(
                    "analyze_search_console",
                    {
                        "target": "example.com",
                        "start_date": "2026-08-01",
                        "end_date": "2026-08-28",
                    },
                )

        self.assertFalse(result.is_error)
        self.assertEqual(len(prompts), 1)
        self.assertIn("1. https://www.example.com/", prompts[0])
        self.assertIn("2. https://shop.example.com/", prompts[0])
        self.assertEqual(
            fake_search_performance.query.await_args.kwargs["property_url"],
            "https://shop.example.com/",
        )

    async def test_mrtr_revalidates_property_candidates_and_reasks_when_the_question_changes(self) -> None:
        fake_gsc = AsyncMock()
        first = [
            {"property_url": "https://www.example.com/", "permission_level": "siteFullUser"},
            {"property_url": "https://shop.example.com/", "permission_level": "siteFullUser"},
        ]
        changed = [
            {"property_url": "https://www.example.com/", "permission_level": "siteFullUser"},
            {"property_url": "https://blog.example.com/", "permission_level": "siteFullUser"},
        ]
        fake_gsc.resolve_properties_for_target.side_effect = [first, changed, changed]
        fake_search_performance = AsyncMock()
        fake_search_performance.query.return_value = SimpleNamespace(
            to_dict=lambda: {"status": "complete", "data": {"rows": []}}
        )
        prompts: list[str] = []

        async def choose(_context, params):  # noqa: ANN001
            prompts.append(params.message)
            return ElicitResult(action="accept", content={"choice": 2})

        with (
            patch.object(server_module, "_gsc", fake_gsc),
            patch.object(server_module, "_search_performance", fake_search_performance),
        ):
            async with Client(
                server_module.mcp,
                mode="2026-07-28",
                elicitation_callback=choose,
            ) as client:
                result = await client.call_tool(
                    "analyze_search_console",
                    {
                        "target": "example.com",
                        "start_date": "2026-08-01",
                        "end_date": "2026-08-28",
                    },
                )

        self.assertFalse(result.is_error)
        self.assertEqual(len(prompts), 2)
        self.assertIn("shop.example.com", prompts[0])
        self.assertIn("blog.example.com", prompts[1])
        self.assertEqual(
            fake_search_performance.query.await_args.kwargs["property_url"],
            "https://blog.example.com/",
        )

    async def test_ambiguous_property_fails_closed_when_client_has_no_elicitation_capability(self) -> None:
        fake_gsc = AsyncMock()
        fake_gsc.resolve_properties_for_target.return_value = [
            {"property_url": "https://www.example.com/", "permission_level": "siteFullUser"},
            {"property_url": "https://shop.example.com/", "permission_level": "siteFullUser"},
        ]
        fake_search_performance = AsyncMock()

        with (
            patch.object(server_module, "_gsc", fake_gsc),
            patch.object(server_module, "_search_performance", fake_search_performance),
        ):
            async with Client(server_module.mcp, mode="2026-07-28") as client:
                with self.assertRaisesRegex(MCPError, "form elicitation capability"):
                    await client.call_tool(
                        "analyze_search_console",
                        {
                            "target": "example.com",
                            "start_date": "2026-08-01",
                            "end_date": "2026-08-28",
                        },
                    )

        fake_search_performance.query.assert_not_awaited()

    async def test_search_console_unique_property_auto_continues_without_elicitation(self) -> None:
        fake_gsc = AsyncMock()
        fake_gsc.resolve_properties_for_target.return_value = [
            {"property_url": "sc-domain:example.com", "permission_level": "siteOwner"}
        ]
        fake_search_performance = AsyncMock()
        fake_search_performance.query.return_value = SimpleNamespace(
            to_dict=lambda: {"status": "complete", "data": {"rows": []}}
        )

        with (
            patch.object(server_module, "_gsc", fake_gsc),
            patch.object(server_module, "_search_performance", fake_search_performance),
        ):
            async with Client(server_module.mcp, mode="2026-07-28") as client:
                result = await client.call_tool(
                    "analyze_search_console",
                    {
                        "target": "example.com",
                        "start_date": "2026-08-01",
                        "end_date": "2026-08-28",
                    },
                )

        self.assertFalse(result.is_error)
        self.assertEqual(
            fake_search_performance.query.await_args.kwargs["property_url"],
            "sc-domain:example.com",
        )

    async def test_ga4_analysis_elicits_ambiguous_property_and_injects_domain_scope(self) -> None:
        fake_ga4 = AsyncMock()
        fake_ga4.list_properties.return_value = [
            {"property_id": "101", "property_name": "Main"},
            {"property_id": "202", "property_name": "Shop"},
        ]

        async def streams_for_property(property_id: str):
            if property_id == "101":
                return [{"default_uri": "https://example.com"}]
            if property_id == "202":
                return [{"default_uri": "https://www.example.com"}]
            return []

        fake_ga4.list_data_streams.side_effect = streams_for_property
        fake_web_analytics = AsyncMock()
        fake_web_analytics.analyze.return_value = SimpleNamespace(
            to_dict=lambda: {"status": "complete", "data": {}}
        )

        async def choose_second(_context, _params):  # noqa: ANN001
            return ElicitResult(action="accept", content={"choice": 2})

        with (
            patch.object(server_module, "_ga4", fake_ga4),
            patch.object(server_module, "_web_analytics", fake_web_analytics),
        ):
            async with Client(
                server_module.mcp,
                mode="2026-07-28",
                elicitation_callback=choose_second,
            ) as client:
                result = await client.call_tool(
                    "analyze_organic_traffic",
                    {
                        "target": "example.com",
                        "start_date": "2026-09-01",
                        "end_date": "2026-09-09",
                    },
                )

        self.assertFalse(result.is_error)
        kwargs = fake_web_analytics.analyze.await_args.kwargs
        self.assertEqual(kwargs["property_id"], "202")
        self.assertEqual(kwargs["site_domain"], "example.com")

    async def test_index_inspection_resolves_property_from_url_before_query(self) -> None:
        fake_gsc = AsyncMock()
        fake_gsc.resolve_properties_for_target.return_value = [
            {"property_url": "https://www.example.com/", "permission_level": "siteOwner"}
        ]
        fake_index = AsyncMock()
        fake_index.inspect.return_value = SimpleNamespace(
            to_dict=lambda: {"status": "complete", "data": {}}
        )

        with (
            patch.object(server_module, "_gsc", fake_gsc),
            patch.object(server_module, "_index_inspection", fake_index),
        ):
            async with Client(server_module.mcp, mode="2026-07-28") as client:
                result = await client.call_tool(
                    "inspect_google_index",
                    {"inspection_url": "https://www.example.com/blog/post"},
                )

        self.assertFalse(result.is_error)
        self.assertEqual(
            fake_index.inspect.await_args.kwargs["property_url"],
            "https://www.example.com/",
        )

    async def test_page_quality_emits_sanitized_structured_observability_to_stderr(self) -> None:
        """运行日志应能定位 Tool/设备/结果，但不能把 URL query 或 Provider payload 打进日志。"""

        fake_page_quality = AsyncMock()
        fake_page_quality.inspect.return_value = SimpleNamespace(
            to_dict=lambda: {
                "capability": "PageQuality",
                "provider": "pagespeed+crux",
                "source_kind": "measurement",
                "status": "complete",
                "data": {
                    "url": "https://example.com/private?token=secret",
                    "strategy": "mobile",
                    "lab": {"raw": "must-not-be-logged"},
                },
                "warnings": [],
            }
        )
        stderr = io.StringIO()

        with (
            patch.object(server_module, "_page_quality", fake_page_quality),
            patch.dict(os.environ, {"SEO_OBSERVABILITY_ENABLED": "1"}, clear=False),
            redirect_stderr(stderr),
        ):
            async with Client(server_module.mcp) as client:
                result = await client.call_tool(
                    "check_page_performance",
                    {
                        "url": "https://example.com/private?token=secret",
                        "strategy": "mobile",
                    },
                )

        self.assertEqual(result.structured_content["status"], "complete")
        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        self.assertEqual([event["event"] for event in events], ["tool_call_started", "tool_call_completed"])
        self.assertEqual(events[0]["tool"], "check_page_performance")
        self.assertEqual(events[0]["capability"], "PageQuality")
        self.assertEqual(events[0]["strategy"], "mobile")
        self.assertEqual(events[0]["target_host"], "example.com")
        self.assertTrue(events[0]["target_hash"])
        self.assertEqual(events[1]["result_status"], "complete")
        self.assertEqual(events[1]["provider"], "pagespeed+crux")
        self.assertIn("duration_ms", events[1])

        log_text = stderr.getvalue()
        self.assertNotIn("token=secret", log_text)
        self.assertNotIn("/private", log_text)
        self.assertNotIn("must-not-be-logged", log_text)
