from __future__ import annotations

import json
import unittest
from dataclasses import asdict

from codex_seo_mcp.adapters.web_analytics.mapper import WebAnalyticsMapper
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class WebAnalyticsMapperTests(unittest.TestCase):
    def test_empty_report_accepts_google_empty_total_without_inventing_values(self) -> None:
        for row_count in ({}, {"rowCount": 0}):
            with self.subTest(row_count=row_count):
                period = WebAnalyticsMapper().map_period(
                    {"metricHeaders": [{"name": "sessions"}], "totals": [{}], **row_count},
                    start_date="2026-08-01",
                    end_date="2026-08-28",
                    expected_dimensions=(),
                    expected_metrics=("sessions",),
                )
                self.assertEqual(period.row_count, 0)
                self.assertEqual(period.rows, [])
                self.assertEqual(period.totals, {})

    def test_empty_total_with_nonempty_report_remains_invalid(self) -> None:
        for rows, row_count in (([], 1), ([{"metricValues": [{"value": "1"}]}], 1)):
            with self.subTest(rows=rows), self.assertRaises(SeoDataError) as caught:
                WebAnalyticsMapper().map_period(
                    {"metricHeaders": [{"name": "sessions"}], "rows": rows,
                     "totals": [{}], "rowCount": row_count},
                    start_date="2026-08-01",
                    end_date="2026-08-28",
                    expected_dimensions=(),
                    expected_metrics=("sessions",),
                )
            self.assertEqual(caught.exception.code, "invalid_response")

    def test_header_mismatch_errors_do_not_expose_provider_names(self) -> None:
        for field in ("dimensionHeaders", "metricHeaders"):
            for name in ("private-header-value", {"private-header-value": 1}, ["private-header-value"]):
                with self.subTest(field=field, name=name):
                    payload = {
                        "dimensionHeaders": [{"name": "landingPage"}],
                        "metricHeaders": [{"name": "sessions"}],
                        "rows": [],
                        "rowCount": 0,
                    }
                    payload[field] = [{"name": name}]
                    with self.assertRaises(SeoDataError) as caught:
                        WebAnalyticsMapper().map_period(
                            payload,
                            start_date="2026-08-01",
                            end_date="2026-08-28",
                            expected_dimensions=("landingPage",),
                            expected_metrics=("sessions",),
                        )
                    self.assertEqual(caught.exception.code, "invalid_response")
                    self.assertIn(field, caught.exception.message)
                    self.assertNotIn("private-header-value", caught.exception.message)

    def test_header_names_are_not_coerced_or_silently_trimmed(self) -> None:
        for field, expected in (("dimensionHeaders", "landingPage"), ("metricHeaders", "sessions")):
            for name in (None, "", True, 12, f" {expected} "):
                with self.subTest(field=field, name=name):
                    payload = {
                        "dimensionHeaders": [{"name": "landingPage"}],
                        "metricHeaders": [{"name": "sessions"}],
                        "rows": [],
                        "rowCount": 0,
                    }
                    payload[field] = [{"name": name}]
                    with self.assertRaises(SeoDataError) as caught:
                        WebAnalyticsMapper().map_period(
                            payload,
                            start_date="2026-08-01",
                            end_date="2026-08-28",
                            expected_dimensions=("landingPage",),
                            expected_metrics=("sessions",),
                        )
                    self.assertEqual(caught.exception.code, "invalid_response")

    def test_dimension_values_are_not_invented_from_non_text_values(self) -> None:
        for value in (None, True, False, 12, 1.5, [], {"private-dimension-value": "secret"}):
            with self.subTest(value=value):
                with self.assertRaises(SeoDataError) as caught:
                    WebAnalyticsMapper().map_period(
                        {
                            "dimensionHeaders": [{"name": "landingPage"}],
                            "metricHeaders": [{"name": "sessions"}],
                            "rows": [{
                                "dimensionValues": [{"value": value}],
                                "metricValues": [{"value": "10"}],
                            }],
                            "rowCount": 1,
                        },
                        start_date="2026-08-01",
                        end_date="2026-08-28",
                        expected_dimensions=("landingPage",),
                        expected_metrics=("sessions",),
                    )
                self.assertEqual(caught.exception.code, "invalid_response")
                self.assertIn("dimensionValues[0]", caught.exception.message)
                self.assertNotIn("private-dimension-value", caught.exception.message)

    def test_valid_dimension_text_is_preserved_without_normalization(self) -> None:
        values = ["", "(not set)", "01", " /路径?x=1 ", "/pricing"]
        period = WebAnalyticsMapper().map_period(
            {
                "dimensionHeaders": [{"name": "landingPage"}],
                "metricHeaders": [{"name": "sessions"}],
                "rows": [{
                    "dimensionValues": [{"value": value}],
                    "metricValues": [{"value": "10"}],
                } for value in values],
                "rowCount": len(values),
            },
            start_date="2026-08-01",
            end_date="2026-08-28",
            expected_dimensions=("landingPage",),
            expected_metrics=("sessions",),
        )
        self.assertEqual([row.dimensions["landingPage"] for row in period.rows], values)

    def test_row_count_rejects_values_that_would_be_coerced_to_integers(self) -> None:
        for value in (True, False, 1.5, 1.0, "2", float("inf"), float("nan"), -1, {}, []):
            with self.subTest(value=value):
                with self.assertRaises(SeoDataError) as caught:
                    WebAnalyticsMapper().map_period(
                        {"metricHeaders": [{"name": "sessions"}], "rows": [], "rowCount": value},
                        start_date="2026-08-01",
                        end_date="2026-08-28",
                        expected_dimensions=(),
                        expected_metrics=("sessions",),
                    )
                self.assertEqual(caught.exception.code, "invalid_response")
                self.assertIn("rowCount", caught.exception.message)

    def test_row_count_preserves_total_and_empty_page_semantics(self) -> None:
        row = {"metricValues": [{"value": "10"}]}
        for count, rows in ((175, [row]), (175, []), (0, [])):
            with self.subTest(count=count, rows=rows):
                period = WebAnalyticsMapper().map_period(
                    {"metricHeaders": [{"name": "sessions"}], "rows": rows, "rowCount": count},
                    start_date="2026-08-01",
                    end_date="2026-08-28",
                    expected_dimensions=(),
                    expected_metrics=("sessions",),
                )
                self.assertEqual(period.row_count, count)
                self.assertEqual(len(period.rows), len(rows))

        for count_field in ({}, {"rowCount": 0}):
            with self.subTest(count_field=count_field):
                with self.assertRaises(SeoDataError) as caught:
                    WebAnalyticsMapper().map_period(
                        {"metricHeaders": [{"name": "sessions"}], "rows": [row], **count_field},
                        start_date="2026-08-01",
                        end_date="2026-08-28",
                        expected_dimensions=(),
                        expected_metrics=("sessions",),
                    )
                self.assertEqual(caught.exception.code, "invalid_response")

    def test_invalid_row_and_total_metrics_fail_without_exposing_raw_values(self) -> None:
        invalid_values = {
            "nan": "NaN",
            "infinity": "Infinity",
            "negative_infinity": "-inf",
            "overflow": "1e400",
            "wrong_number_type": 12,
            "null": None,
            "boolean": True,
            "object": {"private-report-value": 1},
            "array": ["private-report-value"],
            "invalid_text": "private-report-value",
            "empty": "",
        }
        for section in ("rows", "totals"):
            for label, value in invalid_values.items():
                with self.subTest(section=section, value=label):
                    payload = {
                        "metricHeaders": [{"name": "totalRevenue", "type": "TYPE_FLOAT"}],
                        "rows": [{"metricValues": [{"value": "7"}]}],
                        "totals": [{"metricValues": [{"value": "7"}]}],
                        "rowCount": 1,
                    }
                    payload[section] = [{"metricValues": [{"value": value}]}]
                    with self.assertRaises(SeoDataError) as caught:
                        WebAnalyticsMapper().map_period(
                            payload,
                            start_date="2026-08-01",
                            end_date="2026-08-28",
                            expected_dimensions=(),
                            expected_metrics=("totalRevenue",),
                        )
                    self.assertEqual(caught.exception.code, "invalid_response")
                    self.assertIn(section, caught.exception.message)
                    self.assertNotIn("private-report-value", caught.exception.message)

    def test_finite_numeric_strings_remain_usable_in_rows_and_totals(self) -> None:
        for value, expected in (("0", 0.0), ("0.05", 0.05), ("-12.5", -12.5), ("1.25e3", 1250.0)):
            with self.subTest(value=value):
                period = WebAnalyticsMapper().map_period(
                    {
                        "metricHeaders": [{"name": "totalRevenue", "type": "TYPE_FLOAT"}],
                        "rows": [{"metricValues": [{"value": value}]}],
                        "totals": [{"metricValues": [{"value": value}]}],
                        "rowCount": 1,
                    },
                    start_date="2026-08-01",
                    end_date="2026-08-28",
                    expected_dimensions=(),
                    expected_metrics=("totalRevenue",),
                )
                self.assertEqual(period.rows[0].metrics["totalRevenue"], expected)
                self.assertEqual(period.totals["totalRevenue"], expected)
                json.dumps(asdict(period), allow_nan=False)

    def test_maps_ga4_rows_totals_and_metadata(self) -> None:
        payload = {
            "dimensionHeaders": [{"name": "landingPage"}],
            "metricHeaders": [{"name": "sessions", "type": "TYPE_INTEGER"}],
            "rows": [
                {
                    "dimensionValues": [{"value": "/pricing"}],
                    "metricValues": [{"value": "120"}],
                }
            ],
            "totals": [{"metricValues": [{"value": "120"}]}],
            "rowCount": 1,
            "metadata": {"currencyCode": "USD", "timeZone": "Asia/Shanghai"},
        }
        mapper = WebAnalyticsMapper()

        period = mapper.map_period(
            payload,
            start_date="2026-08-01",
            end_date="2026-08-31",
            expected_dimensions=("landingPage",),
            expected_metrics=("sessions",),
        )
        metadata = mapper.map_metadata(payload)

        self.assertEqual(period.rows[0].dimensions["landingPage"], "/pricing")
        self.assertEqual(period.rows[0].metrics["sessions"], 120.0)
        self.assertEqual(period.totals["sessions"], 120.0)
        self.assertEqual(metadata.currency_code, "USD")
        self.assertEqual(metadata.time_zone, "Asia/Shanghai")

    def test_missing_metric_value_is_invalid_response_not_zero(self) -> None:
        payload = {
            "dimensionHeaders": [{"name": "landingPage"}],
            "metricHeaders": [{"name": "sessions", "type": "TYPE_INTEGER"}],
            "rows": [
                {
                    "dimensionValues": [{"value": "/pricing"}],
                    "metricValues": [],
                }
            ],
            "rowCount": 1,
        }

        with self.assertRaises(SeoDataError) as caught:
            WebAnalyticsMapper().map_period(
                payload,
                start_date="2026-08-01",
                end_date="2026-08-31",
                expected_dimensions=("landingPage",),
                expected_metrics=("sessions",),
            )

        self.assertEqual(caught.exception.code, SeoDataErrorCode.INVALID_RESPONSE)

    def test_non_numeric_metric_is_invalid_response_not_zero(self) -> None:
        payload = {
            "metricHeaders": [{"name": "sessions", "type": "TYPE_INTEGER"}],
            "rows": [{"metricValues": [{"value": "not-a-number"}]}],
            "rowCount": 1,
        }

        with self.assertRaises(SeoDataError) as caught:
            WebAnalyticsMapper().map_period(
                payload,
                start_date="2026-08-01",
                end_date="2026-08-31",
                expected_dimensions=(),
                expected_metrics=("sessions",),
            )

        self.assertEqual(caught.exception.code, SeoDataErrorCode.INVALID_RESPONSE)

    def test_header_order_must_match_the_request(self) -> None:
        payload = {
            "dimensionHeaders": [{"name": "countryId"}, {"name": "country"}],
            "metricHeaders": [{"name": "sessions"}],
            "rows": [],
            "rowCount": 0,
        }

        with self.assertRaises(SeoDataError) as caught:
            WebAnalyticsMapper().map_period(
                payload,
                start_date="2026-08-01",
                end_date="2026-08-31",
                expected_dimensions=("country", "countryId"),
                expected_metrics=("sessions",),
            )

        self.assertEqual(caught.exception.code, SeoDataErrorCode.INVALID_RESPONSE)

    def test_empty_report_can_omit_rows_and_zero_row_count(self) -> None:
        payload = {
            "metricHeaders": [{"name": "sessions"}],
            "rowCount": 0,
        }

        period = WebAnalyticsMapper().map_period(
            payload,
            start_date="2026-08-01",
            end_date="2026-08-31",
            expected_dimensions=(),
            expected_metrics=("sessions",),
        )

        self.assertEqual(period.row_count, 0)
        self.assertEqual(period.rows, [])
        self.assertEqual(period.totals, {})


if __name__ == "__main__":
    unittest.main()
