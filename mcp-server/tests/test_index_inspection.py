from __future__ import annotations

import unittest

from codex_seo_mcp.adapters.index_inspection import IndexInspectionAdapter
from codex_seo_mcp.clients.gsc import GscClient, GscInspectionResponse


class FakeGscClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, str]] = []

    async def inspect_url(
        self,
        *,
        property_url: str,
        inspection_url: str,
        language_code: str,
    ) -> GscInspectionResponse:
        self.calls.append(
            {
                "property_url": property_url,
                "inspection_url": inspection_url,
                "language_code": language_code,
            }
        )
        return GscInspectionResponse(payload=self.payload)


class IndexInspectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_google_index_status_without_claiming_live_state(self) -> None:
        client = FakeGscClient(
            {
                "inspectionResult": {
                    "inspectionResultLink": "https://search.google.com/search-console/inspect?id=1",
                    "indexStatusResult": {
                        "verdict": "PASS",
                        "coverageState": "Submitted and indexed",
                        "robotsTxtState": "ALLOWED",
                        "indexingState": "INDEXING_ALLOWED",
                        "lastCrawlTime": "2026-09-01T10:00:00Z",
                        "pageFetchState": "SUCCESSFUL",
                        "googleCanonical": "https://example.com/a",
                        "userCanonical": "https://example.com/a",
                        "crawledAs": "MOBILE",
                        "sitemap": ["https://example.com/sitemap.xml"],
                        "referringUrls": ["https://example.com/"],
                    },
                }
            }
        )
        adapter = IndexInspectionAdapter(client=client)

        result = await adapter.inspect(
            property_url="sc-domain:example.com",
            inspection_url="https://example.com/a",
            language_code="en-US",
        )

        self.assertEqual(result.capability, "IndexInspection")
        self.assertEqual(result.provider, "gsc")
        self.assertEqual(result.source_kind, "first_party")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.verdict, "PASS")
        self.assertEqual(result.data.google_canonical, "https://example.com/a")
        self.assertEqual(result.data.sitemaps, ["https://example.com/sitemap.xml"])
        self.assertFalse(result.data.live_test)
        self.assertIn("Google 索引中的版本", result.warnings[0])

    async def test_missing_index_status_is_partial_not_not_indexed(self) -> None:
        adapter = IndexInspectionAdapter(
            client=FakeGscClient(
                {
                    "inspectionResult": {
                        "inspectionResultLink": "https://search.google.com/search-console/inspect?id=1"
                    }
                }
            )
        )

        result = await adapter.inspect(
            property_url="https://example.com/",
            inspection_url="https://example.com/a",
        )

        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.data.verdict)
        self.assertTrue(any("没有返回 indexStatusResult" in warning for warning in result.warnings))

    async def test_invalid_property_stops_before_gsc_call(self) -> None:
        client = FakeGscClient({})
        adapter = IndexInspectionAdapter(client=client)

        with self.assertRaisesRegex(Exception, "GSC property"):
            await adapter.inspect(
                property_url="example.com",
                inspection_url="https://example.com/a",
            )

        self.assertEqual(client.calls, [])


class _FakeRequest:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def execute(self) -> dict[str, object]:
        return self.payload


class _FakeIndexResource:
    def __init__(self) -> None:
        self.body: dict[str, object] | None = None

    def inspect(self, *, body: dict[str, object]) -> _FakeRequest:
        self.body = body
        return _FakeRequest({"inspectionResult": {"indexStatusResult": {"verdict": "PASS"}}})


class _FakeUrlInspectionResource:
    def __init__(self, index: _FakeIndexResource) -> None:
        self._index = index

    def index(self) -> _FakeIndexResource:
        return self._index


class _FakeSearchConsoleService:
    def __init__(self, index: _FakeIndexResource) -> None:
        self._index = index

    def urlInspection(self) -> _FakeUrlInspectionResource:  # noqa: N802
        return _FakeUrlInspectionResource(self._index)


class GscIndexInspectionClientTests(unittest.TestCase):
    def test_uses_official_url_inspection_request_shape(self) -> None:
        index = _FakeIndexResource()
        client = GscClient.__new__(GscClient)
        client._build_service = lambda _credentials: _FakeSearchConsoleService(index)  # type: ignore[method-assign]

        payload = client._inspect_url_sync(
            object(),
            "sc-domain:example.com",
            "https://example.com/a",
            "en-US",
        )

        self.assertEqual(payload["inspectionResult"]["indexStatusResult"]["verdict"], "PASS")
        self.assertEqual(
            index.body,
            {
                "inspectionUrl": "https://example.com/a",
                "siteUrl": "sc-domain:example.com",
                "languageCode": "en-US",
            },
        )


if __name__ == "__main__":
    unittest.main()
