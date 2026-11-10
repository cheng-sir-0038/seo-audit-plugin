from __future__ import annotations

import unittest

from codex_seo_mcp.registry import build_registry


class FakeAdapter:
    def __init__(self, capability: str) -> None:
        self.capability = capability


class RegistryTests(unittest.TestCase):
    def test_registry_only_binds_supplied_capability_adapters(self) -> None:
        """Registry 只做 capability 绑定，不负责构造运行时依赖。"""

        page = FakeAdapter("PageInspection")
        search = FakeAdapter("SearchPerformance")

        registry = build_registry([page, search])

        self.assertEqual(registry.capabilities(), ["PageInspection", "SearchPerformance"])
        self.assertIs(registry.get("PageInspection"), page)
        self.assertIs(registry.get("SearchPerformance"), search)
