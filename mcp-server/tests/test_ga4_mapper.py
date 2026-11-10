from __future__ import annotations

import unittest

from codex_seo_mcp.clients.ga4_mapper import Ga4AdminMapper
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class Ga4AdminMapperTests(unittest.TestCase):
    def test_empty_admin_collections_are_valid_no_data(self) -> None:
        mapper = Ga4AdminMapper()

        self.assertEqual(mapper.map_properties({}), [])
        self.assertEqual(mapper.map_data_streams({}, property_id="123"), [])

    def test_malformed_account_summaries_is_invalid_response(self) -> None:
        with self.assertRaises(SeoDataError) as caught:
            Ga4AdminMapper().map_properties({"accountSummaries": "broken"})

        self.assertEqual(caught.exception.code, SeoDataErrorCode.INVALID_RESPONSE)

    def test_malformed_property_summary_is_invalid_response(self) -> None:
        payload = {
            "accountSummaries": [
                {
                    "account": "accounts/111",
                    "propertySummaries": ["broken"],
                }
            ]
        }

        with self.assertRaises(SeoDataError) as caught:
            Ga4AdminMapper().map_properties(payload)

        self.assertEqual(caught.exception.code, SeoDataErrorCode.INVALID_RESPONSE)

    def test_web_stream_without_web_stream_data_is_invalid_response(self) -> None:
        payload = {
            "dataStreams": [
                {
                    "name": "properties/123/dataStreams/456",
                    "type": "WEB_DATA_STREAM",
                }
            ]
        }

        with self.assertRaises(SeoDataError) as caught:
            Ga4AdminMapper().map_data_streams(payload, property_id="123")

        self.assertEqual(caught.exception.code, SeoDataErrorCode.INVALID_RESPONSE)


if __name__ == "__main__":
    unittest.main()
