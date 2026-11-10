from __future__ import annotations

import unittest

from codex_seo_mcp.errors import SeoDataError
from codex_seo_mcp.market import (
    DataForSEOLabsMarketResolver,
    MarketContext,
    SemrushMarketResolver,
)


class FakeLabsClient:
    async def locations_and_languages(self) -> list[dict[str, object]]:
        return [
            {
                "location_code": 2840,
                "location_name": "United States",
                "country_iso_code": "US",
                "available_languages": [
                    {
                        "language_code": "en",
                        "available_sources": ["google"],
                    }
                ],
            },
            {
                "location_code": 2158,
                "location_name": "Taiwan",
                "country_iso_code": "TW",
                "available_languages": [
                    {
                        "language_code": "zh-TW",
                        "available_sources": ["google"],
                    }
                ],
            },
        ]


class AmbiguousChineseLabsClient:
    async def locations_and_languages(self) -> list[dict[str, object]]:
        return [
            {
                "location_code": 2344,
                "location_name": "Hong Kong",
                "country_iso_code": "HK",
                "available_languages": [
                    {"language_code": "zh-CN", "available_sources": ["google"]},
                    {"language_code": "zh-TW", "available_sources": ["google"]},
                ],
            }
        ]


class MarketResolutionTests(unittest.IsolatedAsyncioTestCase):
    def test_market_context_normalizes_product_level_codes_only(self) -> None:
        market = MarketContext.from_values(
            country="uk",
            language="zh_cn",
            search_engine="GOOGLE",
        )

        self.assertEqual(market.country, "GB")
        self.assertEqual(market.language, "zh-CN")
        self.assertEqual(market.search_engine, "google")

    def test_market_context_does_not_silently_default_language(self) -> None:
        with self.assertRaisesRegex(SeoDataError, "language"):
            MarketContext.from_values(
                country="CN",
                language="",
                search_engine="baidu",
            )

    async def test_dataforseo_labs_resolves_from_registry_not_guessed_codes(self) -> None:
        resolver = DataForSEOLabsMarketResolver(FakeLabsClient())
        market = MarketContext.from_values(
            country="US",
            language="en-US",
            search_engine="google",
        )

        resolved = await resolver.resolve(market, capability="OrganicVisibility")

        self.assertTrue(resolved.supported)
        self.assertEqual(resolved.location_code, 2840)
        self.assertEqual(resolved.language_code, "en")
        self.assertEqual(resolved.resolution_source, "dataforseo_labs_registry")

    async def test_labs_unsupported_is_capability_scope_not_dataforseo_country_claim(self) -> None:
        resolver = DataForSEOLabsMarketResolver(FakeLabsClient())
        market = MarketContext.from_values(
            country="CN",
            language="zh-CN",
            search_engine="google",
        )

        with self.assertRaisesRegex(
            SeoDataError,
            "当前 DataForSEO Labs.*不代表 DataForSEO 其他 API",
        ) as captured:
            await resolver.resolve(market, capability="OrganicVisibility")

        self.assertEqual(captured.exception.code, "unsupported_for_capability")

    async def test_labs_does_not_guess_between_multiple_same_base_languages(self) -> None:
        resolver = DataForSEOLabsMarketResolver(AmbiguousChineseLabsClient())
        market = MarketContext.from_values(
            country="HK",
            language="zh-HK",
            search_engine="google",
        )

        with self.assertRaisesRegex(SeoDataError, "DataForSEO Labs") as captured:
            await resolver.resolve(market, capability="OrganicVisibility")

        self.assertEqual(captured.exception.code, "unsupported_for_capability")

    def test_semrush_v3_database_is_resolver_owned_not_country_lowercase(self) -> None:
        resolver = SemrushMarketResolver()

        self.assertEqual(resolver.v3_database("US"), "us")
        self.assertEqual(resolver.v3_database("GB"), "uk")
        self.assertEqual(resolver.v3_database("DE"), "de")
        self.assertEqual(resolver.v3_database("FR"), "fr")
        self.assertEqual(resolver.v3_database("HK"), "hk")

        with self.assertRaisesRegex(SeoDataError, "regional database"):
            resolver.v3_database("CN")


if __name__ == "__main__":
    unittest.main()
