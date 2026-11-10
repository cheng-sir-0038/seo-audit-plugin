from __future__ import annotations

import unittest

from mcp.server.elicitation import render_elicitation_schema
from mcp.server.mcpserver import Elicit

from codex_seo_mcp.scope_resolution import (
    Ga4PropertyCandidates,
    GscPropertyCandidates,
    PropertyChoice,
    choose_ga4_property,
    choose_gsc_property,
    finalize_ga4_scope,
    finalize_gsc_scope,
    resolve_ga4_candidates,
    resolve_gsc_candidates,
)
from codex_seo_mcp.tool_boundary import SeoToolError


class StubGscClient:
    def __init__(self, properties: list[dict[str, str]]) -> None:
        self.properties = properties

    async def list_properties(self) -> list[dict[str, str]]:
        return list(self.properties)

    async def resolve_properties_for_target(self, target: str) -> list[dict[str, str]]:
        if target == "example.com":
            return list(self.properties)
        return []


class StubGa4Client:
    def __init__(self, properties: list[dict[str, object]]) -> None:
        self.properties: list[dict[str, str]] = []
        self.streams: dict[str, list[dict[str, str]]] = {}
        for item in properties:
            property_id = str(item.get("property_id") or "")
            self.properties.append(
                {
                    "property_id": property_id,
                    "property_name": str(item.get("property_name") or ""),
                }
            )
            raw_streams = item.get("web_streams")
            self.streams[property_id] = (
                [
                    {str(key): str(value) for key, value in stream.items()}
                    for stream in raw_streams
                    if isinstance(stream, dict)
                ]
                if isinstance(raw_streams, list)
                else []
            )

    async def list_properties(self) -> list[dict[str, str]]:
        return list(self.properties)

    async def list_data_streams(self, property_id: str) -> list[dict[str, str]]:
        return list(self.streams.get(property_id, []))


class ScopeResolutionTests(unittest.IsolatedAsyncioTestCase):
    def test_property_choice_renders_only_mcp_form_root_fields(self) -> None:
        schema = render_elicitation_schema(PropertyChoice)

        self.assertEqual(set(schema), {"type", "properties", "required"})
        self.assertEqual(schema["required"], ["choice"])
        self.assertEqual(schema["properties"]["choice"]["type"], "integer")
        self.assertEqual(schema["properties"]["choice"]["minimum"], 1)

    async def test_gsc_unique_candidate_auto_resolves_without_elicitation(self) -> None:
        item = {"property_url": "sc-domain:example.com", "permission_level": "siteOwner"}
        candidates = await resolve_gsc_candidates(StubGscClient([item]), "example.com")

        choice = choose_gsc_property(candidates)

        self.assertIsInstance(choice, PropertyChoice)
        scope = finalize_gsc_scope(candidates, choice)
        self.assertEqual(scope.property_url, "sc-domain:example.com")

    async def test_gsc_ambiguity_becomes_elicitation_not_default_first_row(self) -> None:
        candidates = GscPropertyCandidates(
            "example.com",
            (
                {"property_url": "https://www.example.com/", "permission_level": "siteOwner"},
                {"property_url": "https://shop.example.com/", "permission_level": "siteOwner"},
            ),
        )

        result = choose_gsc_property(candidates)

        self.assertIsInstance(result, Elicit)
        self.assertIn("1. https://www.example.com/", result.message)
        self.assertIn("2. https://shop.example.com/", result.message)

    async def test_gsc_explicit_domain_property_is_checked_exactly(self) -> None:
        client = StubGscClient(
            [
                {"property_url": "sc-domain:example.com", "permission_level": "siteOwner"},
                {"property_url": "sc-domain:other.com", "permission_level": "siteOwner"},
            ]
        )

        candidates = await resolve_gsc_candidates(client, "sc-domain:example.com")

        self.assertEqual(len(candidates.properties), 1)
        self.assertEqual(candidates.properties[0]["property_url"], "sc-domain:example.com")

    async def test_ga4_domain_ambiguity_requires_elicitation_and_preserves_domain_scope(self) -> None:
        properties = [
            {
                "property_id": "101",
                "property_name": "Main",
                "web_streams": [{"default_uri": "https://example.com"}],
            },
            {
                "property_id": "202",
                "property_name": "Shop",
                "web_streams": [{"default_uri": "https://www.example.com"}],
            },
        ]
        candidates = await resolve_ga4_candidates(StubGa4Client(properties), "example.com")

        result = choose_ga4_property(candidates)

        self.assertIsInstance(result, Elicit)
        scope = finalize_ga4_scope(candidates, PropertyChoice(choice=2))
        self.assertEqual(scope.property_id, "202")
        self.assertEqual(scope.site_domain, "example.com")

    async def test_ga4_www_target_injects_root_domain_scope(self) -> None:
        properties = [
            {
                "property_id": "101",
                "property_name": "Main",
                "web_streams": [{"default_uri": "https://example.com"}],
            },
        ]
        candidates = await resolve_ga4_candidates(StubGa4Client(properties), "www.example.com")

        scope = finalize_ga4_scope(candidates, choose_ga4_property(candidates))

        self.assertEqual(scope.site_domain, "example.com")

    async def test_ga4_property_name_alone_is_not_domain_ownership_evidence(self) -> None:
        candidates = await resolve_ga4_candidates(
            StubGa4Client(
                [
                    {
                        "property_id": "101",
                        "property_name": "example.com",
                        "web_streams": [],
                    }
                ]
            ),
            "example.com",
        )

        self.assertEqual(candidates.properties, ())

    async def test_ga4_explicit_property_id_must_be_accessible(self) -> None:
        candidates = await resolve_ga4_candidates(
            StubGa4Client([{"property_id": "101", "property_name": "Main"}]),
            "999",
        )

        with self.assertRaises(SeoToolError) as caught:
            choose_ga4_property(candidates)

        self.assertEqual(caught.exception.seo_code, "data_unavailable")

    async def test_invalid_human_choice_is_rejected_before_provider_report(self) -> None:
        candidates = Ga4PropertyCandidates(
            "example.com",
            ({"property_id": "101", "property_name": "Main"},),
            "example.com",
        )

        with self.assertRaises(SeoToolError) as caught:
            finalize_ga4_scope(candidates, PropertyChoice(choice=2))

        self.assertEqual(caught.exception.seo_code, "invalid_request")


if __name__ == "__main__":
    unittest.main()
