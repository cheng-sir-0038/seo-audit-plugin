from __future__ import annotations

import unittest

from codex_seo_mcp.clients.gsc import GscClient


class StubGscClient(GscClient):
    def __init__(self, properties: list[dict[str, str]]) -> None:
        self._properties = properties

    async def list_properties(self) -> list[dict[str, str]]:
        return list(self._properties)


class GscClientResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_bare_domain_prefers_exact_domain_property(self) -> None:
        client = StubGscClient([
            {"property_url": "https://www.site.example/", "permission_level": "siteRestrictedUser"},
            {"property_url": "sc-domain:site.example", "permission_level": "siteRestrictedUser"},
            {"property_url": "https://uc.site.example/", "permission_level": "siteRestrictedUser"},
        ])

        matches = await client.resolve_properties_for_target("site.example")

        self.assertEqual(matches, [
            {"property_url": "sc-domain:site.example", "permission_level": "siteRestrictedUser"}
        ])

    async def test_explicit_url_prefers_most_specific_covering_prefix(self) -> None:
        client = StubGscClient([
            {"property_url": "sc-domain:site.example", "permission_level": "siteFullUser"},
            {"property_url": "https://www.site.example/", "permission_level": "siteFullUser"},
            {"property_url": "https://www.site.example/blog/", "permission_level": "siteFullUser"},
        ])

        matches = await client.resolve_properties_for_target(
            "https://www.site.example/blog/article-1"
        )

        self.assertEqual(matches, [
            {"property_url": "https://www.site.example/blog/", "permission_level": "siteFullUser"}
        ])

    async def test_bare_domain_without_domain_property_preserves_multiple_prefixes(self) -> None:
        client = StubGscClient([
            {"property_url": "https://www.site.example/", "permission_level": "siteFullUser"},
            {"property_url": "https://uc.site.example/", "permission_level": "siteFullUser"},
        ])

        matches = await client.resolve_properties_for_target("site.example")

        self.assertEqual(
            [item["property_url"] for item in matches],
            ["https://www.site.example/", "https://uc.site.example/"],
        )

    async def test_unrelated_target_returns_no_match(self) -> None:
        client = StubGscClient([
            {"property_url": "sc-domain:example.com", "permission_level": "siteOwner"}
        ])

        self.assertEqual(await client.resolve_properties_for_target("site.example"), [])


if __name__ == "__main__":
    unittest.main()
