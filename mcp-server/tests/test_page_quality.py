from __future__ import annotations

import unittest

from codex_seo_mcp.adapters.page_quality import PageQualityAdapter
from codex_seo_mcp.clients.crux import CruxResponse
from codex_seo_mcp.clients.pagespeed import PageSpeedResponse
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode


class FakePageSpeedClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def analyze(
        self,
        url: str,
        *,
        strategy: str,
        categories: tuple[str, ...],
        locale: str,
    ) -> PageSpeedResponse:
        self.calls.append(
            {
                "url": url,
                "strategy": strategy,
                "categories": categories,
                "locale": locale,
            }
        )
        return PageSpeedResponse(payload=self.payload)


class FakeCruxClient:
    def __init__(self, *, url_payload: dict | None = None, origin_payload: dict | None = None) -> None:
        self.url_payload = url_payload
        self.origin_payload = origin_payload
        self.calls: list[dict[str, object]] = []

    async def query_url(
        self, url: str, *, form_factor: str, metrics: tuple[str, ...]
    ) -> CruxResponse | None:
        self.calls.append({"scope": "url", "key": url, "form_factor": form_factor, "metrics": metrics})
        return CruxResponse(self.url_payload) if self.url_payload is not None else None

    async def query_origin(
        self, origin: str, *, form_factor: str, metrics: tuple[str, ...]
    ) -> CruxResponse | None:
        self.calls.append(
            {"scope": "origin", "key": origin, "form_factor": form_factor, "metrics": metrics}
        )
        return CruxResponse(self.origin_payload) if self.origin_payload is not None else None


def _crux_payload(*, scope: str = "origin") -> dict:
    key_value = "https://example.com/page" if scope == "url" else "https://example.com"
    return {
        "record": {
            "key": {"formFactor": "PHONE", scope: key_value},
            "metrics": {
                "largest_contentful_paint": {
                    "histogram": [
                        {"start": 0, "end": 2500, "density": 0.60},
                        {"start": 2500, "end": 4000, "density": 0.25},
                        {"start": 4000, "density": 0.15},
                    ],
                    "percentiles": {"p75": 3076},
                },
                "interaction_to_next_paint": {
                    "histogram": [
                        {"start": 0, "end": 200, "density": 0.76},
                        {"start": 200, "end": 500, "density": 0.18},
                        {"start": 500, "density": 0.06},
                    ],
                    "percentiles": {"p75": 197},
                },
                "cumulative_layout_shift": {
                    "histogram": [
                        {"start": "0.00", "end": "0.10", "density": 0.82},
                        {"start": "0.10", "end": "0.25", "density": 0.12},
                        {"start": "0.25", "density": 0.06},
                    ],
                    "percentiles": {"p75": "0.05"},
                },
            },
            "collectionPeriod": {
                "firstDate": {"year": 2026, "month": 8, "day": 5},
                "lastDate": {"year": 2026, "month": 9, "day": 1},
            },
        }
    }


def _lighthouse_payload() -> dict:
    return {
        "lighthouseResult": {
            "requestedUrl": "https://example.com/page",
            "finalUrl": "https://example.com/page",
            "lighthouseVersion": "13.0.0",
            "fetchTime": "2026-09-03T07:00:00.000Z",
            "categories": {
                "performance": {"score": 0.91},
                "accessibility": {"score": 0.88},
                "best-practices": {"score": 0.95},
                "seo": {"score": 1.0},
            },
            "audits": {
                "first-contentful-paint": {
                    "score": 0.9,
                    "numericValue": 1200,
                    "displayValue": "1.2 s",
                },
                "largest-contentful-paint": {
                    "score": 0.8,
                    "numericValue": 2300,
                    "displayValue": "2.3 s",
                },
                "cumulative-layout-shift": {
                    "score": 0.95,
                    "numericValue": 0.04,
                    "displayValue": "0.04",
                },
                "total-blocking-time": {
                    "score": 0.7,
                    "numericValue": 180,
                    "displayValue": "180 ms",
                },
                "speed-index": {
                    "score": 0.8,
                    "numericValue": 2500,
                    "displayValue": "2.5 s",
                },
                "unused-javascript": {
                    "score": 0.4,
                    "title": "Reduce unused JavaScript",
                    "description": "Remove unused JavaScript.",
                    "displayValue": "Potential savings of 120 KiB",
                    "details": {"overallSavingsBytes": 122880},
                },
            },
            "runWarnings": ["Lab values may vary."],
        }
    }


class PageQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_lighthouse_lab_when_crux_has_no_sample(self) -> None:
        """CrUX 无样本时保留 Lighthouse，并明确 partial；不能把无 Field 当性能正常。"""

        adapter = PageQualityAdapter(
            pagespeed=FakePageSpeedClient(_lighthouse_payload()),
            crux=FakeCruxClient(),
        )

        result = await adapter.inspect("https://example.com/page", strategy="mobile")

        self.assertEqual(result.capability, "PageQuality")
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.provider, "pagespeed")
        self.assertIsNone(result.data.field)
        self.assertEqual(result.data.lab.category_scores["performance"], 91)
        self.assertEqual(result.data.lab.category_scores["seo"], 100)
        self.assertEqual(result.data.lab.metrics["lcp"].numeric_value, 2300)
        self.assertEqual(result.data.lab.metrics["cls"].unit, "unitless")
        self.assertEqual(result.data.lab.opportunities[0].audit_id, "unused-javascript")
        self.assertEqual(
            result.data.lab.opportunities[0].business_label,
            "未使用的 JavaScript 过多",
        )
        self.assertTrue(result.data.lab.opportunities[0].recommendations)
        self.assertTrue(
            any("拆分代码" in item for item in result.data.lab.opportunities[0].recommendations)
        )
        self.assertIn("CrUX 当前 URL/Origin 没有足够真实用户样本", result.warnings)

    async def test_combines_lighthouse_and_crux_into_complete_page_quality(self) -> None:
        """Lab + Field 都成功时，PageQuality 才是 complete。"""

        crux = FakeCruxClient(url_payload=_crux_payload(scope="url"))
        adapter = PageQualityAdapter(
            pagespeed=FakePageSpeedClient(_lighthouse_payload()),
            crux=crux,
        )

        result = await adapter.inspect("https://example.com/page", strategy="mobile")

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.provider, "pagespeed+crux")
        self.assertEqual(result.data.field.scope, "url")
        self.assertEqual(result.data.field.form_factor, "PHONE")
        self.assertEqual(result.data.field.collection_start, "2026-08-05")
        self.assertEqual(result.data.field.collection_end, "2026-09-01")
        self.assertEqual(result.data.field.metrics["lcp"].p75, 3076)
        self.assertEqual(result.data.field.metrics["cls"].p75, 0.05)
        self.assertEqual(len(result.data.field.metrics["inp"].histogram), 3)
        self.assertEqual([call["scope"] for call in crux.calls], ["url"])

    async def test_falls_back_to_origin_without_claiming_page_level_field_data(self) -> None:
        """URL 没 CrUX 样本时可以回退 Origin，但必须保留 scope=origin。"""

        crux = FakeCruxClient(origin_payload=_crux_payload(scope="origin"))
        adapter = PageQualityAdapter(
            pagespeed=FakePageSpeedClient(_lighthouse_payload()),
            crux=crux,
        )

        result = await adapter.inspect("https://example.com/page", strategy="mobile")

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.data.field.scope, "origin")
        self.assertIn("CrUX URL 级真实用户样本不足，已回退到站点 Origin 数据", result.warnings)
        self.assertEqual([call["scope"] for call in crux.calls], ["url", "origin"])

    async def test_keeps_crux_field_when_pagespeed_fails(self) -> None:
        """Lab Provider 失败不能把已经拿到的真实用户 Field 数据一起丢掉。"""

        class BrokenPageSpeed(FakePageSpeedClient):
            async def analyze(self, *args, **kwargs):  # type: ignore[override]
                raise SeoDataError(SeoDataErrorCode.QUOTA_EXCEEDED, "PageSpeed quota")

        adapter = PageQualityAdapter(
            pagespeed=BrokenPageSpeed({}),
            crux=FakeCruxClient(url_payload=_crux_payload(scope="url")),
        )

        result = await adapter.inspect("https://example.com/page", strategy="mobile")

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.provider, "crux")
        self.assertIsNone(result.data.lab)
        self.assertIsNotNone(result.data.field)
        self.assertIn("Google PageSpeed Insights 实验室检测不可用：quota_exceeded", result.warnings)

    async def test_runtime_error_does_not_return_fake_scores_when_no_field_fallback(self) -> None:
        """Lighthouse 失败且 CrUX 也无数据时，不能返回一份看似成功的 PageQuality。"""

        payload = {
            "lighthouseResult": {
                "runtimeError": {
                    "code": "ERRORED_DOCUMENT_REQUEST",
                    "message": "The page did not load successfully.",
                }
            }
        }
        adapter = PageQualityAdapter(pagespeed=FakePageSpeedClient(payload), crux=FakeCruxClient())

        with self.assertRaisesRegex(Exception, "PageSpeed Lighthouse 检测失败"):
            await adapter.inspect("https://example.com", strategy="mobile")

    async def test_requires_explicit_strategy(self) -> None:
        """单次 PageQuality 必须明确设备，避免默认 mobile 被误当成完整性能诊断。"""

        adapter = PageQualityAdapter(
            pagespeed=FakePageSpeedClient(_lighthouse_payload()),
            crux=FakeCruxClient(),
        )

        with self.assertRaises(TypeError):
            await adapter.inspect("https://example.com/page")  # type: ignore[call-arg]

    async def test_validates_strategy_before_provider_call(self) -> None:
        """mobile/desktop 是产品层稳定枚举，错误值不应该发给上游再猜。"""

        client = FakePageSpeedClient({})
        adapter = PageQualityAdapter(pagespeed=client, crux=FakeCruxClient())

        with self.assertRaisesRegex(Exception, "mobile 或 desktop"):
            await adapter.inspect("https://example.com", strategy="tablet")

        self.assertEqual(client.calls, [])
