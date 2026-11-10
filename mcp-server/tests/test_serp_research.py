from __future__ import annotations

import unittest

from codex_seo_mcp.adapters.serp_research import SerpResearchAdapter
from codex_seo_mcp.errors import SeoDataError


class FakeSerperClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def search(
        self,
        query: str,
        *,
        country: str,
        language: str,
        num: int,
        location: str | None = None,
    ) -> dict[str, object]:
        self.calls.append({
            "query": query,
            "country": country,
            "language": language,
            "num": num,
            "location": location,
        })
        return self.payload


class SerpResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_organic_paa_and_serp_features(self) -> None:
        """SERP 能力应保留当前结果 URL、PAA 与 feature，不推断页面源 HTML。"""

        client = FakeSerperClient({
            "searchParameters": {"q": "seo tools", "gl": "us", "hl": "en"},
            "knowledgeGraph": {
                "title": "Search engine optimization",
                "type": "Topic",
                "website": "https://example.org/seo",
                "description": "SEO topic summary",
            },
            "answerBox": {"answer": "A concise answer"},
            "organic": [
                {
                    "position": 1,
                    "title": "Example SEO Tools",
                    "link": "https://example.com/tools",
                    "snippet": "Tools for SEO.",
                    "sitelinks": [
                        {"title": "Audit", "link": "https://example.com/audit"}
                    ],
                },
                {
                    "position": 2,
                    "title": "Other",
                    "link": "https://other.example/",
                    "snippet": "Other result",
                },
            ],
            "peopleAlsoAsk": [
                {
                    "question": "What is an SEO tool?",
                    "snippet": "A tool for SEO workflows.",
                    "title": "SEO tools explained",
                    "link": "https://example.net/answer",
                }
            ],
            "topStories": [{"title": "SEO news"}],
        })

        result = await SerpResearchAdapter(client=client).research(
            "seo tools", country="US", language="en-US", search_engine="google", num=10
        )

        self.assertEqual(result.capability, "SerpResearch")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.query, "seo tools")
        self.assertEqual(result.data.market, "US")
        self.assertEqual(result.data.language, "en-US")
        self.assertEqual(result.data.search_engine, "google")
        self.assertEqual(result.data.organic[0].url, "https://example.com/tools")
        self.assertEqual(result.data.organic[0].position, 1)
        self.assertEqual(result.data.organic[0].sitelinks[0].title, "Audit")
        self.assertEqual(result.data.people_also_ask[0].question, "What is an SEO tool?")
        self.assertIn("knowledge_graph", result.data.features)
        self.assertIn("answer_box", result.data.features)
        self.assertIn("people_also_ask", result.data.features)
        self.assertIn("top_stories", result.data.features)
        self.assertEqual(result.data.knowledge_graph.title, "Search engine optimization")

    async def test_empty_organic_is_valid_serp_result(self) -> None:
        """没有 Organic 结果不等于 Provider 失败，诊断层需要看到真实空结果。"""

        result = await SerpResearchAdapter(client=FakeSerperClient({})).research(
            "unlikely query", country="US", language="en-US", search_engine="google", num=10
        )
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.organic, [])

    async def test_rejects_invalid_market_before_provider_call(self) -> None:
        """Serper 国家参数使用两位国家码，错误参数不能被误判成 SERP 无结果。"""

        client = FakeSerperClient({})
        with self.assertRaises(SeoDataError):
            await SerpResearchAdapter(client=client).research(
                "seo", country="USA", language="en-US", search_engine="google", num=10
            )
        self.assertEqual(client.calls, [])

    async def test_rejects_baidu_when_current_provider_is_google_only(self) -> None:
        client = FakeSerperClient({})

        with self.assertRaisesRegex(SeoDataError, "Serper/Google") as captured:
            await SerpResearchAdapter(client=client).research(
                "网站建设",
                country="CN",
                language="zh-CN",
                search_engine="baidu",
                num=10,
            )

        self.assertEqual(captured.exception.code, "unsupported_for_capability")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
