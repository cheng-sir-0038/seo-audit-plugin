from __future__ import annotations

import unittest

from codex_seo_mcp.adapters.web_analytics.query_builder import WebAnalyticsQueryBuilder


class WebAnalyticsQueryBuilderTests(unittest.TestCase):
    def test_builds_landing_page_query_with_organic_and_domain_filters(self) -> None:
        builder = WebAnalyticsQueryBuilder()

        spec = builder.build(
            view="landing_pages",
            country_codes=[],
            site_domain="https://www.site.example/path",
            limit=20,
            offset=0,
        )
        body = spec.body(("2026-08-01", "2026-08-31"))

        self.assertEqual(spec.site_domain, "site.example")
        self.assertEqual(spec.dimensions, ("hostName", "landingPage"))
        self.assertEqual(body["limit"], "20")
        self.assertEqual(
            body["dimensionFilter"],
            {
                "andGroup": {
                    "expressions": [
                        {
                            "filter": {
                                "fieldName": "sessionDefaultChannelGroup",
                                "stringFilter": {
                                    "matchType": "EXACT",
                                    "value": "Organic Search",
                                },
                            }
                        },
                        {
                            "filter": {
                                "fieldName": "hostName",
                                "stringFilter": {
                                    "matchType": "FULL_REGEXP",
                                    "value": r"(^|.*\.)site\.example$",
                                    "caseSensitive": False,
                                },
                            }
                        },
                    ]
                }
            },
        )

    def test_country_filter_normalizes_iso2_and_deduplicates(self) -> None:
        spec = WebAnalyticsQueryBuilder().build(
            view="country_pages",
            country_codes=["in", "TR", "IN"],
            site_domain=None,
            limit=100,
            offset=0,
        )

        self.assertEqual(spec.countries, ("IN", "TR"))


if __name__ == "__main__":
    unittest.main()
