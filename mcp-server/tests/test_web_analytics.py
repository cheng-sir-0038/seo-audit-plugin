from __future__ import annotations

import unittest

from codex_seo_mcp.adapters.web_analytics import WebAnalyticsAdapter
from codex_seo_mcp.clients.ga4 import Ga4ReportResponse


class FakeGa4Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def run_report(self, property_id: str, body: dict[str, object]) -> Ga4ReportResponse:
        self.calls.append((property_id, body))
        dimensions = [item["name"] for item in body.get("dimensions", [])]
        metrics = [item["name"] for item in body.get("metrics", [])]
        dimension_values = []
        for name in dimensions:
            values = {
                "hostName": "www.example.com",
                "landingPage": "/pricing",
                "country": "India",
                "countryId": "IN",
                "pagePath": "/features",
                "deviceCategory": "desktop",
                "date": "20260815",
            }
            dimension_values.append({"value": values.get(name, "")})
        metric_values = []
        sample_metrics = {
            "sessions": "120",
            "activeUsers": "90",
            "engagedSessions": "72",
            "engagementRate": "0.6",
            "keyEvents": "8",
            "sessionKeyEventRate": "0.05",
            "totalRevenue": "199.5",
            "screenPageViews": "230",
            "userEngagementDuration": "4800",
            "userKeyEventRate": "0.08",
        }
        for name in metrics:
            metric_values.append({"value": sample_metrics.get(name, "0")})
        return Ga4ReportResponse(
            payload={
                "dimensionHeaders": [{"name": name} for name in dimensions],
                "metricHeaders": [{"name": name, "type": "TYPE_FLOAT"} for name in metrics],
                "rows": [{"dimensionValues": dimension_values, "metricValues": metric_values}],
                "totals": [{"metricValues": metric_values}],
                "rowCount": 1,
                "metadata": {"currencyCode": "USD", "timeZone": "Asia/Shanghai"},
            }
        )


class WebAnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_landing_pages_use_organic_search_filter_and_session_metrics(self) -> None:
        client = FakeGa4Client()
        result = await WebAnalyticsAdapter(client=client).analyze(
            property_id="222",
            start_date="2026-08-01",
            end_date="2026-08-31",
            view="landing_pages",
            limit=20,
        )

        self.assertEqual(result.capability, "WebAnalytics")
        self.assertEqual(result.provider, "ga4")
        self.assertEqual(result.source_kind, "first_party")
        self.assertEqual(result.data.scope, "organic_search")
        self.assertEqual(result.data.current.rows[0].dimensions["hostName"], "www.example.com")
        self.assertEqual(result.data.current.rows[0].dimensions["landingPage"], "/pricing")
        self.assertEqual(result.data.current.rows[0].metrics["sessions"], 120.0)
        body = client.calls[0][1]
        self.assertEqual(body["dimensionFilter"], {
            "filter": {
                "fieldName": "sessionDefaultChannelGroup",
                "stringFilter": {"matchType": "EXACT", "value": "Organic Search"},
            }
        })
        self.assertEqual(body["limit"], "20")

    async def test_site_domain_filters_hostname_for_root_and_subdomains(self) -> None:
        client = FakeGa4Client()
        result = await WebAnalyticsAdapter(client=client).analyze(
            property_id="222",
            start_date="2026-08-01",
            end_date="2026-08-31",
            view="landing_pages",
            site_domain="https://www.site.example/path",
        )

        self.assertEqual(result.data.site_domain, "site.example")
        body = client.calls[0][1]
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

    async def test_country_pages_accept_iso2_country_filter_and_use_page_metrics(self) -> None:
        client = FakeGa4Client()
        result = await WebAnalyticsAdapter(client=client).analyze(
            property_id="222",
            start_date="2026-08-01",
            end_date="2026-08-31",
            view="country_pages",
            country_codes=["IN", "TR"],
        )

        self.assertEqual(result.data.current.rows[0].dimensions["countryId"], "IN")
        self.assertEqual(result.data.current.rows[0].dimensions["hostName"], "www.example.com")
        self.assertEqual(result.data.current.rows[0].metrics["screenPageViews"], 230.0)
        body = client.calls[0][1]
        self.assertEqual(body["dimensionFilter"], {
            "andGroup": {
                "expressions": [
                    {
                        "filter": {
                            "fieldName": "sessionDefaultChannelGroup",
                            "stringFilter": {"matchType": "EXACT", "value": "Organic Search"},
                        }
                    },
                    {
                        "filter": {
                            "fieldName": "countryId",
                            "inListFilter": {"values": ["IN", "TR"], "caseSensitive": False},
                        }
                    },
                ]
            }
        })

    async def test_optional_previous_period_preserves_two_periods_without_inventing_delta(self) -> None:
        client = FakeGa4Client()
        result = await WebAnalyticsAdapter(client=client).analyze(
            property_id="222",
            start_date="2026-08-01",
            end_date="2026-08-31",
            compare_start_date="2026-07-01",
            compare_end_date="2026-07-31",
            view="overview",
        )

        self.assertIsNotNone(result.data.previous)
        self.assertEqual(result.data.previous.start_date, "2026-07-01")
        self.assertEqual(len(client.calls), 2)
        current_body = client.calls[0][1]
        previous_body = client.calls[1][1]
        self.assertEqual(
            current_body["dateRanges"],
            [{"startDate": "2026-08-01", "endDate": "2026-08-31"}],
        )
        self.assertEqual(
            previous_body["dateRanges"],
            [{"startDate": "2026-07-01", "endDate": "2026-07-31"}],
        )
        for field in ("dimensions", "metrics", "dimensionFilter", "orderBys", "limit", "offset"):
            self.assertEqual(current_body[field], previous_body[field])

    async def test_rejects_partial_compare_window(self) -> None:
        client = FakeGa4Client()
        with self.assertRaisesRegex(Exception, "compare_start_date"):
            await WebAnalyticsAdapter(client=client).analyze(
                property_id="222",
                start_date="2026-08-01",
                end_date="2026-08-31",
                compare_start_date="2026-07-01",
            )
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
