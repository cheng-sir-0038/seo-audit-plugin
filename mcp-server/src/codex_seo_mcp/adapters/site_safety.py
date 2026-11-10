from __future__ import annotations

from typing import Protocol

from codex_seo_mcp.clients.safe_browsing import SafeBrowsingClient, SafeBrowsingResponse
from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.models.common import CapabilityResult, CapabilitySourceKind
from codex_seo_mcp.models.site_safety import SiteSafety, SiteSafetyStatus, SiteSafetyThreat


class SafeBrowsingLike(Protocol):
    async def search_url(self, url: str) -> SafeBrowsingResponse: ...


class SiteSafetyAdapter:
    """Map malicious-URL Provider observations into the stable `SiteSafety` contract."""

    capability = "SiteSafety"

    def __init__(self, client: SafeBrowsingLike | None = None) -> None:
        self.client = client or SafeBrowsingClient()

    async def check(self, url: str) -> CapabilityResult[SiteSafety]:
        response = await self.client.search_url(url)
        raw_threats = response.payload.get("threats") or []
        if not isinstance(raw_threats, list):
            raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "Safe Browsing threats 返回结构无效")

        threats: list[SiteSafetyThreat] = []
        for raw in raw_threats:
            if not isinstance(raw, dict):
                continue
            matched_url = str(raw.get("url") or "").strip()
            raw_types = raw.get("threatTypes") or []
            if not isinstance(raw_types, list):
                raise SeoDataError(SeoDataErrorCode.INVALID_RESPONSE, "Safe Browsing threatTypes 返回结构无效")
            threat_types = _dedupe(
                [str(value).strip() for value in raw_types if str(value).strip()]
            )
            if matched_url and threat_types:
                threats.append(
                    SiteSafetyThreat(
                        matched_url=matched_url,
                        threat_types=threat_types,
                    )
                )

        status = (
            SiteSafetyStatus.POTENTIAL_RISK
            if threats
            else SiteSafetyStatus.NO_KNOWN_THREATS
        )
        warnings = (
            ["Google Safe Browsing 返回潜在威胁匹配；应按威胁类型继续核实，不应表述为 100% 已确认恶意。"]
            if threats
            else ["Google Safe Browsing 当前未匹配已知威胁；这不代表绝对安全，也不能排除尚未收录的风险。"]
        )
        return CapabilityResult.complete(
            capability=self.capability,
            provider="google-safe-browsing-v4",
            source_kind=CapabilitySourceKind.THIRD_PARTY,
            data=SiteSafety(
                url=response.requested_url or str(url).strip(),
                status=status,
                threats=threats,
            ),
            warnings=warnings,
        )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
