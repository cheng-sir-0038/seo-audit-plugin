from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

from codex_seo_mcp.clients.pagespeed import PageSpeedClient, PageSpeedConfig
from codex_seo_mcp.provider_cache import ProviderCache, ProviderCacheConfig


class PageSpeedClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_runpagespeed_api_with_explicit_device_and_consumes_json(self) -> None:
        """性能事实应直接来自 runPagespeed JSON API，不依赖 pagespeed.web.dev 网页。"""

        response = MagicMock()
        response.read.return_value = json.dumps(
            {"lighthouseResult": {"finalUrl": "https://example.com/page?x=1"}}
        ).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        client = PageSpeedClient(
            PageSpeedConfig(
                api_url="https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                api_key="test-key",
                timeout_seconds=5,
            ),
            cache=ProviderCache(ProviderCacheConfig(root=Path(".local-test"), enabled=False)),
        )
        with patch("codex_seo_mcp.clients.pagespeed.urlopen", return_value=response) as urlopen_mock:
            result = await client.analyze(
                "https://example.com/page?x=1#ignored-fragment",
                strategy="desktop",
                categories=("performance", "seo"),
                locale="zh-CN",
            )

        request = urlopen_mock.call_args.args[0]
        parsed = urlparse(request.full_url)
        params = parse_qs(parsed.query)

        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
        )
        self.assertNotIn("pagespeed.web.dev", request.full_url)
        self.assertEqual(params["url"], ["https://example.com/page?x=1"])
        self.assertEqual(params["strategy"], ["desktop"])
        self.assertEqual(params["category"], ["performance", "seo"])
        self.assertEqual(params["locale"], ["zh-CN"])
        self.assertEqual(params["key"], ["test-key"])
        self.assertEqual(
            result.payload,
            {"lighthouseResult": {"finalUrl": "https://example.com/page?x=1"}},
        )

    async def test_reuses_short_lived_cache_for_same_measurement(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"lighthouseResult": {"finalUrl": "https://example.com/page"}}
        ).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with tempfile.TemporaryDirectory() as temp_dir:
            client = PageSpeedClient(
                PageSpeedConfig(
                    api_url="https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                    api_key="test-key",
                    timeout_seconds=5,
                    cache_ttl_seconds=1800,
                ),
                cache=ProviderCache(ProviderCacheConfig(root=Path(temp_dir))),
            )
            with patch("codex_seo_mcp.clients.pagespeed.urlopen", return_value=response) as urlopen_mock:
                first = await client.analyze(
                    "https://example.com/page",
                    strategy="mobile",
                    categories=("performance", "seo"),
                    locale="zh-CN",
                )
                second = await client.analyze(
                    "https://example.com/page",
                    strategy="mobile",
                    categories=("performance", "seo"),
                    locale="zh-CN",
                )
                await client.analyze(
                    "https://example.com/page",
                    strategy="desktop",
                    categories=("performance", "seo"),
                    locale="zh-CN",
                )

        self.assertEqual(urlopen_mock.call_count, 2)
        self.assertEqual(first.payload, second.payload)


if __name__ == "__main__":
    unittest.main()
