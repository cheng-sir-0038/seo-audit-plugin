from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from mcp.server.mcpserver import Elicit
from pydantic import BaseModel, ConfigDict, Field

from codex_seo_mcp.clients.gsc import GscClient
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.observability import emit_event
from codex_seo_mcp.tool_boundary import as_tool_error


class PropertyChoice(BaseModel):
    """Human/client selection returned through MCP elicitation.

    The model never sees this parameter in a Tool input schema. The MCP client supplies it only
    after the server has determined that multiple materially different Properties remain valid.
    """

    @staticmethod
    def _form_schema(schema: dict[str, object]) -> None:
        # Keep model metadata out of the MCP form root; Elicit.message describes the choice.
        schema.pop("title", None)
        schema.pop("description", None)

    model_config = ConfigDict(json_schema_extra=_form_schema)

    choice: int = Field(..., ge=1, description="候选 Property 的序号，从 1 开始")


@dataclass(frozen=True, slots=True)
class GscPropertyCandidates:
    target: str
    properties: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class GscResolvedScope:
    target: str
    property_url: str


@dataclass(frozen=True, slots=True)
class Ga4PropertyCandidates:
    target: str
    properties: tuple[dict[str, object], ...]
    site_domain: str | None


@dataclass(frozen=True, slots=True)
class Ga4ResolvedScope:
    target: str
    property_id: str
    site_domain: str | None


class Ga4ScopeClient(Protocol):
    async def list_properties(self) -> list[dict[str, str]]: ...

    async def list_data_streams(self, property_id: str) -> list[dict[str, str]]: ...


async def resolve_gsc_candidates(client: GscClient, target: str) -> GscPropertyCandidates:
    """Resolve a domain/URL/Property identity to every equally-valid GSC candidate."""

    try:
        clean_target = str(target or "").strip()
        if not clean_target:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GSC target 不能为空")

        if clean_target.startswith("sc-domain:"):
            exact = [
                item
                for item in await client.list_properties()
                if str(item.get("property_url") or "").strip() == clean_target
            ]
            return GscPropertyCandidates(clean_target, tuple(exact))

        return GscPropertyCandidates(
            clean_target,
            tuple(await client.resolve_properties_for_target(clean_target)),
        )
    except SeoDataError as exc:
        raise as_tool_error(exc) from exc


def choose_gsc_property(
    candidates: GscPropertyCandidates,
) -> PropertyChoice | Elicit[PropertyChoice]:
    """Auto-resolve one GSC Property or elicit a human/client choice for true ambiguity."""

    count = len(candidates.properties)
    if count == 0:
        raise as_tool_error(
            SeoDataError(
                SeoDataErrorCode.DATA_UNAVAILABLE,
                f"当前 Google Account 没有可用于 {candidates.target} 的 Search Console Property",
            )
        )
    if count == 1:
        return PropertyChoice(choice=1)

    lines = ["检测到多个同等有效的 Search Console Property，请选择本次分析范围："]
    for index, item in enumerate(candidates.properties, start=1):
        lines.append(
            f"{index}. {str(item.get('property_url') or '').strip()} "
            f"({str(item.get('permission_level') or 'permission unknown')})"
        )
    return Elicit("\n".join(lines), PropertyChoice)


def finalize_gsc_scope(
    candidates: GscPropertyCandidates,
    choice: PropertyChoice,
) -> GscResolvedScope:
    selected = _selected(candidates.properties, choice.choice, label="GSC Property")
    property_url = str(selected.get("property_url") or "").strip()
    if not property_url:
        raise as_tool_error(SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "GSC Property 缺少 property_url"))
    emit_event(
        "interaction_resolved",
        interaction_kind="selection",
        reason_code="gsc_property_resolution",
        selected_index=choice.choice,
    )
    return GscResolvedScope(target=candidates.target, property_url=property_url)


async def resolve_ga4_candidates(
    client: Ga4ScopeClient,
    target: str,
) -> Ga4PropertyCandidates:
    """Resolve a GA4 Property ID or site domain without allowing the model to invent identity."""

    try:
        clean_target = str(target or "").strip()
        if not clean_target:
            raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GA4 target 不能为空")

        if clean_target.isdigit():
            exact = [
                item
                for item in await client.list_properties()
                if str(item.get("property_id") or "").strip() == clean_target
            ]
            return Ga4PropertyCandidates(clean_target, tuple(exact), None)

        site_domain = _normalized_host(clean_target)
        return Ga4PropertyCandidates(
            clean_target,
            tuple(await _ga4_properties_for_domain(client, site_domain)),
            site_domain,
        )
    except SeoDataError as exc:
        raise as_tool_error(exc) from exc


def choose_ga4_property(
    candidates: Ga4PropertyCandidates,
) -> PropertyChoice | Elicit[PropertyChoice]:
    """Auto-resolve one GA4 Property or elicit a choice before any report runs."""

    count = len(candidates.properties)
    if count == 0:
        raise as_tool_error(
            SeoDataError(
                SeoDataErrorCode.DATA_UNAVAILABLE,
                f"当前 Google Account 没有可用于 {candidates.target} 的 GA4 Property",
            )
        )
    if count == 1:
        return PropertyChoice(choice=1)

    lines = ["检测到多个同等有效的 GA4 Property，请选择本次分析范围："]
    for index, item in enumerate(candidates.properties, start=1):
        property_id = str(item.get("property_id") or "").strip()
        property_name = str(item.get("property_name") or "").strip() or "Unnamed Property"
        streams = item.get("web_streams")
        stream_uris = []
        if isinstance(streams, list):
            stream_uris = [
                str(stream.get("default_uri") or "").strip()
                for stream in streams
                if isinstance(stream, dict) and str(stream.get("default_uri") or "").strip()
            ]
        suffix = f" | {', '.join(stream_uris)}" if stream_uris else ""
        lines.append(f"{index}. {property_name} ({property_id}){suffix}")
    return Elicit("\n".join(lines), PropertyChoice)


def finalize_ga4_scope(
    candidates: Ga4PropertyCandidates,
    choice: PropertyChoice,
) -> Ga4ResolvedScope:
    selected = _selected(candidates.properties, choice.choice, label="GA4 Property")
    property_id = str(selected.get("property_id") or "").strip()
    if not property_id:
        raise as_tool_error(SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "GA4 Property 缺少 property_id"))
    emit_event(
        "interaction_resolved",
        interaction_kind="selection",
        reason_code="ga4_property_resolution",
        selected_index=choice.choice,
    )
    return Ga4ResolvedScope(
        target=candidates.target,
        property_id=property_id,
        site_domain=candidates.site_domain,
    )


def _selected(
    candidates: tuple[dict[str, object], ...] | tuple[dict[str, str], ...],
    choice: int,
    *,
    label: str,
) -> dict[str, object] | dict[str, str]:
    if choice < 1 or choice > len(candidates):
        raise as_tool_error(
            SeoDataError(
                SeoDataErrorCode.INVALID_REQUEST,
                f"{label} 候选序号无效；请选择 1 到 {len(candidates)}",
            )
        )
    return candidates[choice - 1]


def _normalized_host(value: str) -> str:
    host = _optional_normalized_host(value)
    if not host:
        raise SeoDataError(SeoDataErrorCode.INVALID_REQUEST, "GA4 target 必须包含有效域名或 Property ID")
    return host


def _optional_normalized_host(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text if "://" in text else f"https://{text}"
    host = (urlsplit(candidate).hostname or "").lower().rstrip(".")
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


async def _ga4_properties_for_domain(
    client: Ga4ScopeClient,
    site_domain: str,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for property_summary in await client.list_properties():
        property_id = str(property_summary.get("property_id") or "").strip()
        if not property_id:
            raise SeoDataError(
                SeoDataErrorCode.INVALID_RESPONSE,
                "GA4 Property 缺少 property_id",
            )
        streams = await client.list_data_streams(property_id)
        matched_streams = [
            stream
            for stream in streams
            if _optional_normalized_host(stream.get("default_uri")) == site_domain
        ]
        if matched_streams:
            matches.append(
                {
                    **property_summary,
                    "web_streams": matched_streams,
                }
            )
    return matches


async def match_ga4_properties_for_domain(
    client: Ga4ScopeClient,
    domain: str,
) -> list[dict[str, object]]:
    """Return GA4 Properties whose Web Data Stream default URI matches the domain."""

    return await _ga4_properties_for_domain(client, _normalized_host(domain))
