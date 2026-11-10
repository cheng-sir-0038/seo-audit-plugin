from __future__ import annotations

from codex_seo_mcp.adapters.organic_visibility_gateway import OrganicVisibilityGateway
from codex_seo_mcp.models.common import CapabilityResult
from codex_seo_mcp.models.organic_visibility import OrganicVisibility
from codex_seo_mcp.snapshots import OrganicVisibilitySnapshotStore


class SnapshottingOrganicVisibility:
    """Decorate OrganicVisibility provider routing with local weekly observations.

    Provider selection/fallback stays inside `OrganicVisibilityGateway`. This decorator owns only
    the local persistence concern: record every successful provider result and optionally attach
    recent observations to the returned domain model.
    """

    capability = "OrganicVisibility"

    def __init__(
        self,
        gateway: OrganicVisibilityGateway,
        snapshot_store: OrganicVisibilitySnapshotStore | None = None,
    ) -> None:
        self.gateway = gateway
        self.snapshot_store = snapshot_store or OrganicVisibilitySnapshotStore()

    async def inspect(
        self,
        target: str,
        *,
        country: str,
        language: str,
        search_engine: str,
        view: str = "keywords",
        target_scope: str = "domain",
        limit: int = 100,
        offset: int = 0,
        historical_serp_mode: str = "live",
        date_from: str | None = None,
        date_to: str | None = None,
        include_snapshots: bool = False,
        snapshot_weeks: int = 8,
    ) -> CapabilityResult[OrganicVisibility]:
        result = await self.gateway.inspect(
            target,
            country=country,
            language=language,
            search_engine=search_engine,
            view=view,
            target_scope=target_scope,
            limit=limit,
            offset=offset,
            historical_serp_mode=historical_serp_mode,
            date_from=date_from,
            date_to=date_to,
        )
        try:
            self.snapshot_store.record(result)
            if include_snapshots:
                self._attach_recent_snapshots(result, weeks=snapshot_weeks)
        except OSError:
            result.warnings.append(
                "本地周趋势暂时无法保存或读取；本次第三方数据仍可正常使用。"
            )
        return result

    def _attach_recent_snapshots(
        self,
        result: CapabilityResult[OrganicVisibility],
        *,
        weeks: int,
    ) -> None:
        result.data.snapshots = self.snapshot_store.recent(
            target=result.data.target,
            target_scope=result.data.target_scope,
            country=result.data.market.country,
            language=result.data.market.language,
            provider=result.provider,
            weeks=weeks,
        )
        if len(result.data.snapshots) < max(1, weeks):
            result.warnings.append(
                f"本地周趋势当前只有 {len(result.data.snapshots)} 个实际观测点；缺失周不会自动补值。"
            )
