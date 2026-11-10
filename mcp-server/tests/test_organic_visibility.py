from __future__ import annotations

import unittest

from codex_seo_mcp.adapters.organic_visibility import DataForSEOOrganicVisibilityAdapter
from codex_seo_mcp.clients.dataforseo import DataForSEOReport
from codex_seo_mcp.models.organic_visibility import OrganicVisibilityKeywordStatus


class FakeDataForSEOClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def locations_and_languages(self) -> list[dict[str, object]]:
        return [
            {
                "location_code": 2840,
                "location_name": "United States",
                "country_iso_code": "US",
                "available_languages": [
                    {
                        "language_name": "English",
                        "language_code": "en",
                        "available_sources": ["google"],
                        "keywords": 100,
                    }
                ],
            }
        ]

    async def ranked_keywords(self, task: dict[str, object]) -> DataForSEOReport:
        self.calls.append(("keywords", task))
        return DataForSEOReport(
            result=[
                {
                    "target": "example.com",
                    "location_code": 2840,
                    "language_code": "en",
                    "metrics": {
                        "organic": {
                            "pos_1": 1,
                            "pos_2_3": 2,
                            "pos_4_10": 7,
                            "count": 20,
                            "etv": 123.5,
                            "is_new": 2,
                            "is_up": 5,
                            "is_down": 4,
                            "is_lost": 1,
                        }
                    },
                    "items": [
                        {
                            "keyword_data": {
                                "keyword": "seo tools",
                                "keyword_info": {"search_volume": 1000},
                                "serp_info": {
                                    "serp_item_types": ["organic", "people_also_ask"],
                                    "last_updated_time": "2026-09-01 10:00:00 +00:00",
                                },
                            },
                            "ranked_serp_element": {
                                "serp_item": {
                                    "type": "organic",
                                    "rank_group": 8,
                                    "rank_absolute": 10,
                                    "url": "https://example.com/seo",
                                    "etv": 32.5,
                                    "rank_changes": {
                                        "previous_rank_absolute": 16,
                                        "is_new": False,
                                        "is_up": True,
                                        "is_down": False,
                                    },
                                },
                                "is_lost": False,
                                "last_updated_time": "2026-09-01 10:00:00 +00:00",
                                "previous_updated_time": "2026-08-25 10:00:00 +00:00",
                            },
                        }
                    ],
                }
            ],
            cost=0.01,
        )

    async def relevant_pages(self, task: dict[str, object]) -> DataForSEOReport:
        self.calls.append(("pages", task))
        return DataForSEOReport(
            result=[
                {
                    "items": [
                        {
                            "page_address": "https://example.com/seo",
                            "metrics": {
                                "organic": {
                                    "count": 12,
                                    "etv": 88.5,
                                    "is_new": 1,
                                    "is_up": 4,
                                    "is_down": 2,
                                    "is_lost": 1,
                                }
                            },
                        }
                    ]
                }
            ],
            cost=0.01,
        )

    async def domain_rank_overview(self, task: dict[str, object]) -> DataForSEOReport:
        self.calls.append(("overview", task))
        return DataForSEOReport(
            result=[
                {
                    "items": [
                        {
                            "metrics": {
                                "organic": {
                                    "pos_1": 2,
                                    "pos_2_3": 3,
                                    "pos_4_10": 5,
                                    "count": 50,
                                    "etv": 300.0,
                                    "is_new": 5,
                                    "is_up": 10,
                                    "is_down": 8,
                                    "is_lost": 4,
                                }
                            }
                        }
                    ]
                }
            ],
            cost=0.01,
        )

    async def historical_rank_overview(self, task: dict[str, object]) -> DataForSEOReport:
        self.calls.append(("history", task))
        return DataForSEOReport(
            result=[
                {
                    "items": [
                        {
                            "year": 2026,
                            "month": 8,
                            "metrics": {
                                "organic": {
                                    "pos_1": 1,
                                    "pos_2_3": 2,
                                    "pos_4_10": 3,
                                    "count": 25,
                                    "etv": 200.0,
                                    "is_new": 2,
                                    "is_up": 3,
                                    "is_down": 4,
                                    "is_lost": 1,
                                }
                            },
                        }
                    ]
                }
            ],
            cost=0.01,
        )


class OrganicVisibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_data_keeps_visibility_unknown_instead_of_zero(self) -> None:
        class NoDataClient(FakeDataForSEOClient):
            async def ranked_keywords(self, task: dict[str, object]) -> DataForSEOReport:
                self.calls.append(("keywords", task))
                return DataForSEOReport(result=[], cost=0.01)

        result = await DataForSEOOrganicVisibilityAdapter(client=NoDataClient()).inspect(
            "example.com",
            country="US",
            language="en",
            search_engine="google",
            view="keywords",
        )

        self.assertIsNone(result.data.overview)
        self.assertEqual(result.data.keywords, [])
        self.assertTrue(any("No Data" in warning for warning in result.warnings))

    async def test_keywords_maps_dataforseo_to_provider_neutral_visibility(self) -> None:
        client = FakeDataForSEOClient()
        adapter = DataForSEOOrganicVisibilityAdapter(client=client)

        result = await adapter.inspect(
            "https://www.example.com/",
            country="US",
            language="en",
            search_engine="google",
            view="keywords",
            target_scope="domain",
            limit=20,
        )

        self.assertEqual(result.capability, "OrganicVisibility")
        self.assertEqual(result.provider, "dataforseo")
        self.assertEqual(result.source_kind, "third_party")
        self.assertEqual(result.data.target, "example.com")
        self.assertEqual(result.data.market.country, "US")
        self.assertEqual(result.data.overview.total_keywords, 20)
        self.assertEqual(result.data.overview.top10_keywords, 10)
        self.assertIsNone(result.data.overview.lost_keywords)
        self.assertTrue(
            any("lost keyword count is therefore unknown" in note for note in result.data.observation.coverage_notes)
        )
        keyword = result.data.keywords[0]
        self.assertEqual(keyword.query, "seo tools")
        self.assertEqual(keyword.current_position, 10)
        self.assertEqual(keyword.previous_position, 16)
        self.assertEqual(keyword.current_url, "https://example.com/seo")
        self.assertEqual(keyword.status, OrganicVisibilityKeywordStatus.RISE)
        self.assertEqual(keyword.search_volume, 1000.0)
        self.assertEqual(keyword.estimated_traffic, 32.5)
        self.assertIn("people_also_ask", keyword.serp_features)
        payload = result.to_dict()
        self.assertNotIn("clicks", payload["data"])
        self.assertNotIn("impressions", payload["data"])
        self.assertEqual(client.calls[0][1]["location_code"], 2840)
        self.assertEqual(client.calls[0][1]["language_code"], "en")
        self.assertEqual(client.calls[0][1]["item_types"], ["organic"])

    async def test_all_mode_preserves_lost_keyword_count(self) -> None:
        client = FakeDataForSEOClient()
        result = await DataForSEOOrganicVisibilityAdapter(client=client).inspect(
            "example.com",
            country="US",
            language="en",
            search_engine="google",
            view="keywords",
            historical_serp_mode="all",
        )

        self.assertEqual(result.data.overview.lost_keywords, 1)
        self.assertEqual(client.calls[0][1]["historical_serp_mode"], "all")

    async def test_pages_maps_relevant_pages_without_calling_other_views(self) -> None:
        client = FakeDataForSEOClient()
        result = await DataForSEOOrganicVisibilityAdapter(client=client).inspect(
            "example.com",
            country="US",
            language="en",
            search_engine="google",
            view="pages",
            target_scope="domain",
        )

        self.assertEqual([name for name, _ in client.calls], ["pages"])
        self.assertEqual(result.data.pages[0].url, "https://example.com/seo")
        self.assertEqual(result.data.pages[0].keyword_count, 12)
        self.assertEqual(result.data.pages[0].estimated_traffic, 88.5)

    async def test_overview_and_history_preserve_estimated_visibility_semantics(self) -> None:
        client = FakeDataForSEOClient()
        adapter = DataForSEOOrganicVisibilityAdapter(client=client)

        overview = await adapter.inspect(
            "example.com",
            country="US",
            language="en",
            search_engine="google",
            view="overview",
        )
        history = await adapter.inspect(
            "example.com",
            country="US",
            language="en",
            search_engine="google",
            view="history",
            date_from="2026-08-01",
            date_to="2026-08-31",
        )

        self.assertEqual(overview.data.overview.total_keywords, 50)
        self.assertEqual(overview.data.overview.estimated_traffic, 300.0)
        self.assertEqual(history.data.history[0].date, "2026-08-01")
        self.assertEqual(history.data.history[0].total_keywords, 25)
        self.assertEqual(history.data.history[0].estimated_traffic, 200.0)
        self.assertIn("third-party", " ".join(overview.data.observation.coverage_notes))

    async def test_market_must_exist_and_support_google_language(self) -> None:
        client = FakeDataForSEOClient()
        adapter = DataForSEOOrganicVisibilityAdapter(client=client)

        with self.assertRaisesRegex(
            Exception,
            "DataForSEO Labs.*不代表 DataForSEO 其他 API",
        ):
            await adapter.inspect(
                "example.com",
                country="ZZ",
                language="en",
                search_engine="google",
            )


    async def test_history_task_only_carries_history_dates_not_keyword_paging_fields(self) -> None:
        client = FakeDataForSEOClient()
        await DataForSEOOrganicVisibilityAdapter(client=client).inspect(
            "example.com",
            country="US",
            language="en",
            search_engine="google",
            view="history",
            date_from="2026-08-01",
            date_to="2026-08-31",
            limit=20,
            offset=5,
        )

        task = client.calls[0][1]
        self.assertEqual(task["date_from"], "2026-08-01")
        self.assertEqual(task["date_to"], "2026-08-31")
        for field in ("limit", "offset", "historical_serp_mode", "item_types"):
            self.assertNotIn(field, task)

    async def test_exact_scope_is_keywords_only_for_first_dataforseo_adapter(self) -> None:
        adapter = DataForSEOOrganicVisibilityAdapter(client=FakeDataForSEOClient())

        with self.assertRaisesRegex(Exception, "exact"):
            await adapter.inspect(
                "https://example.com/seo",
                country="US",
                language="en",
                search_engine="google",
                view="pages",
                target_scope="exact",
            )


if __name__ == "__main__":
    unittest.main()
