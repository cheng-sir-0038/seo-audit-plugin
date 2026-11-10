from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_seo_mcp.adapters.competitor_research import CompetitorResearchAdapter
from codex_seo_mcp.adapters.keyword_research import KeywordResearchAdapter
from codex_seo_mcp.clients.semrush import SemrushClient, SemrushConfig, SemrushReport
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class FakeSemrushClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def keyword_metrics(self, keyword: str, country: str, month: str | None = None) -> dict[str, object]:
        self.calls.append(("keyword_metrics", (keyword, country, month)))
        return {
            "meta": {"keyword": keyword, "country": country, "month": month or "2026-09", "success": True},
            "data": {
                "search_volume": "60500",
                "keyword_difficulty": 74,
                "intents": ["COMMERCIAL", "INFORMATIONAL"],
                "cpc": "1245",
                "competitive_density": 78,
                "trends": [82, 78, 85],
                "number_of_results": "1850000000",
                "serp_features": ["SITELINKS", "PEOPLE_ALSO_ASK", "AI_OVERVIEW"],
            },
        }

    async def keyword_overview_v3(
        self, keyword: str, database: str, month: str | None = None
    ) -> SemrushReport:
        self.calls.append(("keyword_overview_v3", (keyword, database, month)))
        return SemrushReport(rows=[{
            "Keyword": keyword,
            "Search Volume": "880",
            "CPC": "6.63",
            "Competition": "0.30",
            "Number of Results": "162000000",
            "Trends": "0.20,0.16,0.65",
            "Intent": "1,0",
            "Keyword Difficulty": "61.2",
        }])

    async def related_keywords_v3(self, keyword: str, database: str, limit: int) -> SemrushReport:
        self.calls.append(("related_keywords_v3", (keyword, database, limit)))
        return SemrushReport(rows=[{"Keyword": "seo software"}, {"Keyword": "seo platform"}][:limit])

    async def keyword_questions_v3(self, keyword: str, database: str, limit: int) -> SemrushReport:
        self.calls.append(("keyword_questions_v3", (keyword, database, limit)))
        return SemrushReport(rows=[{"Keyword": "what is seo"}, {"Keyword": "how does seo work"}][:limit])

    async def domain_overview(self, domain: str, database: str) -> SemrushReport:
        self.calls.append(("domain_overview", (domain, database)))
        return SemrushReport(rows=[{
            "Domain": domain,
            "Rank": "24041",
            "Organic Keywords": "5249",
            "Organic Traffic": "37332",
            "Organic Cost": "143496",
            "Adwords Keywords": "12",
            "Adwords Traffic": "100",
            "Adwords Cost": "350",
        }])

    async def organic_competitors(self, domain: str, database: str, limit: int) -> SemrushReport:
        self.calls.append(("organic_competitors", (domain, database, limit)))
        return SemrushReport(rows=[{
            "Domain": "competitor.example",
            "Competitor Relevance": "0.13",
            "Common Keywords": "338",
            "Organic Keywords": "11021",
            "Organic Traffic": "5640",
            "Organic Cost": "9690",
            "Adwords Keywords": "4",
        }])

    async def organic_pages(self, domain: str, database: str, limit: int) -> SemrushReport:
        self.calls.append(("organic_pages", (domain, database, limit)))
        return SemrushReport(rows=[{
            "Url": "https://example.com/page-a",
            "Number of Keywords": "317",
            "Traffic": "2488",
            "Traffic (%)": "15.14",
        }])

    async def keyword_gap(self, domains: list[str], database: str, limit: int) -> SemrushReport:
        self.calls.append(("keyword_gap", (tuple(domains), database, limit)))
        return SemrushReport(rows=[{
            "Keyword": "seo tools",
            domains[0]: "5",
            domains[1]: "12",
            "Competition": "0.72",
            "Search Volume": "1000",
            "CPC": "4.50",
        }])


class KeywordResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_related_and_questions_default_to_twenty_keywords(self) -> None:
        client = FakeSemrushClient()
        await KeywordResearchAdapter(client=client).research(
            "seo tools",
            country="US",
            language="en-US",
            search_engine="google",
            include_related=True,
            include_questions=True,
        )

        related_call = next(call for call in client.calls if call[0] == "related_keywords_v3")
        questions_call = next(call for call in client.calls if call[0] == "keyword_questions_v3")
        self.assertEqual(related_call[1][2], 20)
        self.assertEqual(questions_call[1][2], 20)


    async def test_v4_core_does_not_resolve_v3_database_without_fallback_or_enrichment(self) -> None:
        class Resolver:
            def __init__(self) -> None:
                self.v3_calls = 0

            def v4_country(self, country: str) -> str:
                return country

            def v3_database(self, _country: str) -> str:
                self.v3_calls += 1
                return "us"

        resolver = Resolver()
        result = await KeywordResearchAdapter(
            client=FakeSemrushClient(),
            market_resolver=resolver,  # type: ignore[arg-type]
        ).research(
            "seo tools",
            country="US",
            language="en-US",
            search_engine="google",
        )

        self.assertEqual(result.provider, "semrush-v4")
        self.assertEqual(resolver.v3_calls, 0)

    async def test_requested_auxiliary_failure_keeps_core_data_and_marks_partial(self) -> None:
        class RelatedUnavailable(FakeSemrushClient):
            async def related_keywords_v3(self, *args, **kwargs):  # type: ignore[override]
                raise SeoDataError(SeoDataErrorCode.PROVIDER_UNAVAILABLE, "related unavailable")

        result = await KeywordResearchAdapter(client=RelatedUnavailable()).research(
            "seo tools",
            country="US",
            language="en-US",
            search_engine="google",
            include_related=True,
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.provider, "semrush-v4")
        self.assertIsNone(result.data.related)
        self.assertEqual(result.data.search_volume, 60500)
        self.assertTrue(any("Related Keywords 不可用" in item for item in result.warnings))

    async def test_maps_v4_metrics_and_normalizes_cpc_to_usd(self) -> None:
        """能力名收敛不能丢掉 Semrush 的 SEO/PPC 核心研究字段。"""

        client = FakeSemrushClient()
        result = await KeywordResearchAdapter(client=client).research(
            "seo tools", country="US", language="en-US", search_engine="google"
        )

        self.assertEqual(result.capability, "KeywordResearch")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.market, "US")
        self.assertEqual(result.data.language, "en-US")
        self.assertEqual(result.data.search_engine, "google")
        self.assertEqual(result.data.search_volume, 60500)
        self.assertEqual(result.data.keyword_difficulty, 74.0)
        self.assertEqual(result.data.intents, ["COMMERCIAL", "INFORMATIONAL"])
        self.assertEqual(result.data.cpc_usd, 12.45)
        self.assertEqual(result.data.competitive_density, 78.0)
        self.assertEqual(result.data.trends, [82.0, 78.0, 85.0])
        self.assertEqual(result.data.number_of_results, 1850000000)
        self.assertIn("AI_OVERVIEW", result.data.serp_features)
        self.assertIsNone(result.data.related)
        self.assertIsNone(result.data.questions)

    async def test_falls_back_to_v3_and_normalizes_units_without_losing_research_fields(self) -> None:
        """只有 v3 Key 时核心 KeywordResearch 仍可完成，且单位必须与 v4 领域语义一致。"""

        class V3OnlyClient(FakeSemrushClient):
            async def keyword_metrics(self, *args, **kwargs):  # type: ignore[override]
                raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, "v4 key mismatch")

        client = V3OnlyClient()
        result = await KeywordResearchAdapter(client=client).research(
            "seo tools",
            country="US",
            language="en-US",
            search_engine="google",
            include_related=True,
            include_questions=True,
            idea_limit=2,
        )

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.provider, "semrush-v3")
        self.assertEqual(result.data.search_volume, 880)
        self.assertEqual(result.data.keyword_difficulty, 61.2)
        self.assertEqual(result.data.intents, ["INFORMATIONAL", "COMMERCIAL"])
        self.assertEqual(result.data.cpc_usd, 6.63)
        self.assertEqual(result.data.competitive_density, 30.0)
        self.assertEqual(result.data.trends, [20.0, 16.0, 65.0])
        self.assertEqual(result.data.related, ["seo software", "seo platform"])
        self.assertEqual(result.data.questions, ["what is seo", "how does seo work"])
        self.assertIn("Semrush v4 Keyword Metrics 不可用", result.warnings[0])

    async def test_maps_gb_market_to_semrush_uk_database(self) -> None:
        """英国市场不能把 ISO GB 机械 lower 成不存在的 v3 `gb` database。"""

        class V3OnlyClient(FakeSemrushClient):
            async def keyword_metrics(self, *args, **kwargs):  # type: ignore[override]
                raise SeoDataError(SeoDataErrorCode.AUTHORIZATION_REQUIRED, "v4 key mismatch")

        client = V3OnlyClient()
        result = await KeywordResearchAdapter(client=client).research(
            "seo tools",
            country="GB",
            language="en-GB",
            search_engine="google",
        )

        overview_call = next(call for call in client.calls if call[0] == "keyword_overview_v3")
        self.assertEqual(overview_call[1][1], "uk")
        self.assertEqual(result.data.market, "GB")

    async def test_rejects_non_alpha2_keyword_market_before_provider_call(self) -> None:
        """v4 Keyword Metrics 用 ISO alpha-2 国家码；错误市场不能被误解释成无数据。"""

        client = FakeSemrushClient()
        with self.assertRaises(SeoDataError):
            await KeywordResearchAdapter(client=client).research(
                "seo", country="USA", language="en-US", search_engine="google"
            )
        self.assertEqual(client.calls, [])

    async def test_rejects_baidu_before_keyword_provider_call(self) -> None:
        """当前 Semrush 关键词路径是 Google evidence，不能拿来回答百度关键词事实。"""

        client = FakeSemrushClient()
        with self.assertRaisesRegex(SeoDataError, "Semrush/Google") as caught:
            await KeywordResearchAdapter(client=client).research(
                "网站建设",
                country="CN",
                language="zh-CN",
                search_engine="baidu",
            )

        self.assertEqual(caught.exception.code, "unsupported_for_capability")
        self.assertEqual(client.calls, [])


class CompetitorResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_baidu_before_competitor_provider_call(self) -> None:
        """Semrush Domain Analytics 当前作为 Google evidence，search-engine 轴必须显式保持。"""

        client = FakeSemrushClient()
        with self.assertRaisesRegex(SeoDataError, "Semrush/Google") as caught:
            await CompetitorResearchAdapter(client=client).research(
                "example.cn",
                country="CN",
                language="zh-CN",
                search_engine="baidu",
            )

        self.assertEqual(caught.exception.code, "unsupported_for_capability")
        self.assertEqual(client.calls, [])

    async def test_keyword_gap_defaults_to_twenty_without_changing_page_limit(self) -> None:
        client = FakeSemrushClient()
        await CompetitorResearchAdapter(client=client).research(
            "example.com",
            country="US",
            language="en-US",
            search_engine="google",
            compare_domains=["competitor.example"],
            limit=5,
        )

        competitors_call = next(call for call in client.calls if call[0] == "organic_competitors")
        pages_call = next(call for call in client.calls if call[0] == "organic_pages")
        gap_call = next(call for call in client.calls if call[0] == "keyword_gap")
        self.assertEqual(competitors_call[1][2], 5)
        self.assertEqual(pages_call[1][2], 5)
        self.assertEqual(gap_call[1][2], 20)

    async def test_explicit_keyword_gap_limit_overrides_default(self) -> None:
        client = FakeSemrushClient()
        await CompetitorResearchAdapter(client=client).research(
            "example.com",
            country="US",
            language="en-US",
            search_engine="google",
            compare_domains=["competitor.example"],
            keyword_limit=37,
        )

        gap_call = next(call for call in client.calls if call[0] == "keyword_gap")
        self.assertEqual(gap_call[1][2], 37)

    async def test_combines_domain_research_without_becoming_ranking_authority(self) -> None:
        """Semrush 域名排名字段只属于竞争研究，不进入本站 GSC SearchPerformance。"""

        client = FakeSemrushClient()
        result = await CompetitorResearchAdapter(client=client).research(
            "example.com",
            country="US",
            language="en-US",
            search_engine="google",
            compare_domains=["competitor.example"],
            limit=10,
        )

        self.assertEqual(result.capability, "CompetitorResearch")
        self.assertEqual(result.data.domain, "example.com")
        self.assertEqual(result.data.market, "US")
        self.assertEqual(result.data.language, "en-US")
        self.assertEqual(result.data.search_engine, "google")
        self.assertEqual(result.data.overview.semrush_rank, 24041)
        self.assertEqual(result.data.competitors[0].domain, "competitor.example")
        self.assertEqual(result.data.organic_pages[0].organic_keywords, 317)
        self.assertEqual(result.data.keyword_gap[0].positions["example.com"], 5)
        self.assertEqual(result.data.keyword_gap[0].positions["competitor.example"], 12)
        self.assertEqual(result.data.keyword_gap[0].cpc_usd, 4.5)

    async def test_skips_keyword_gap_when_no_compare_domains_given(self) -> None:
        """Keyword Gap 成本高，只有真实比较目标时才调用，不能为了“数据多”自动烧 API units。"""

        client = FakeSemrushClient()
        result = await CompetitorResearchAdapter(client=client).research(
            "example.com",
            country="US",
            language="en-US",
            search_engine="google",
            compare_domains=None,
            limit=5,
        )
        self.assertEqual(result.data.keyword_gap, [])
        self.assertFalse(any(name == "keyword_gap" for name, _ in client.calls))


class SemrushConfigTests(unittest.TestCase):
    def test_default_keyword_limit_is_twenty_and_env_can_override(self) -> None:
        config = SemrushConfig(
            base_url="https://api.semrush.com",
            v3_api_key="v3",
            v4_api_key="v4",
        )
        self.assertEqual(config.default_keyword_limit, 20)

        with patch.dict("os.environ", {"SEMRUSH_DEFAULT_KEYWORD_LIMIT": "37"}, clear=False):
            self.assertEqual(SemrushConfig.from_env().default_keyword_limit, 37)

    def test_specific_version_keys_win_over_legacy_generic_fallback(self) -> None:
        """Semrush v3/v4 key 版本隔离，通用 key 只允许作为开发兼容 fallback。"""

        config = SemrushConfig(
            base_url="https://api.semrush.com",
            v3_api_key="v3",
            v4_api_key="v4",
            request_timeout_seconds=20,
        )
        self.assertEqual(config.v3_api_key, "v3")
        self.assertEqual(config.v4_api_key, "v4")


class SemrushClientCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_v3_report_reuses_local_cache_without_spending_units_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = SemrushClient(
                SemrushConfig(
                    base_url="https://api.example",
                    v3_api_key="secret-v3",
                    v4_api_key="secret-v4",
                    cache_ttl_seconds=21600,
                ),
                cache=ProviderCache(ProviderCacheConfig(root=root)),
            )
            calls = 0

            def fake_text(_request):  # noqa: ANN001
                nonlocal calls
                calls += 1
                return "Domain;Rank;Organic Keywords\nexample.com;42;120\n"

            client._request_text = fake_text  # type: ignore[method-assign]

            first = await client.domain_overview("example.com", "us")
            second = await client.domain_overview("example.com", "us")
            await client.domain_overview("other.example", "us")

            self.assertEqual(first.rows, second.rows)
            self.assertEqual(calls, 2)
            cache_text = "\n".join(
                path.read_text(encoding="utf-8") for path in root.rglob("*.json")
            )
            self.assertNotIn("secret-v3", cache_text)

    async def test_v4_keyword_metrics_reuses_local_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = SemrushClient(
                SemrushConfig(
                    base_url="https://api.example",
                    v3_api_key="v3",
                    v4_api_key="v4",
                    cache_ttl_seconds=21600,
                ),
                cache=ProviderCache(
                    ProviderCacheConfig(root=Path(temp_dir))
                ),
            )
            calls = 0

            def fake_json(_request):  # noqa: ANN001
                nonlocal calls
                calls += 1
                return {"meta": {"success": True}, "data": {"search_volume": 100}}

            client._request_json = fake_json  # type: ignore[method-assign]

            first = await client.keyword_metrics("seo tools", "US")
            second = await client.keyword_metrics("seo tools", "US")
            await client.keyword_metrics("seo tools", "GB")

            self.assertEqual(first, second)
            self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()

class SemrushV3ErrorSemanticsTests(unittest.TestCase):
    def test_nothing_found_is_not_treated_as_wrong_key(self) -> None:
        """v3 ERROR 50 NOTHING FOUND 表示无研究数据，不是鉴权失败。"""

        SemrushClient._raise_v3_error("ERROR 50 :: NOTHING FOUND")

    def test_wrong_key_text_still_maps_to_authorization_required(self) -> None:
        """同一历史错误码可能有不同文本，鉴权错误必须看真实语义。"""

        with self.assertRaises(SeoDataError) as context:
            SemrushClient._raise_v3_error("ERROR 50 :: WRONG KEY")
        self.assertEqual(context.exception.code, "authorization_required")
