from __future__ import annotations

from dataclasses import dataclass

from codex_seo_mcp.adapters.competitor_research import CompetitorResearchAdapter
from codex_seo_mcp.adapters.index_inspection import IndexInspectionAdapter
from codex_seo_mcp.adapters.keyword_research import KeywordResearchAdapter
from codex_seo_mcp.adapters.organic_visibility_gateway import OrganicVisibilityGateway
from codex_seo_mcp.adapters.organic_visibility_snapshotting import SnapshottingOrganicVisibility
from codex_seo_mcp.adapters.page_inspection import PageInspectionAdapter
from codex_seo_mcp.adapters.page_quality import PageQualityAdapter
from codex_seo_mcp.adapters.resource_inspection import ResourceInspectionAdapter
from codex_seo_mcp.adapters.search_performance import SearchPerformanceAdapter
from codex_seo_mcp.adapters.serp_research import SerpResearchAdapter
from codex_seo_mcp.adapters.site_safety import SiteSafetyAdapter
from codex_seo_mcp.adapters.web_analytics import WebAnalyticsAdapter
from codex_seo_mcp.clients.ga4 import Ga4Client
from codex_seo_mcp.clients.gsc import GscClient
from codex_seo_mcp.registry import CapabilityRegistry, build_registry


@dataclass(slots=True)
class SeoRuntime:
    """Concrete runtime graph for the portable MCP process.

    This is the single composition root: shared Provider clients are constructed once, adapters
    receive those instances explicitly, and the Registry binds the same adapter objects.
    """

    gsc: GscClient
    ga4: Ga4Client
    page_inspection: PageInspectionAdapter
    index_inspection: IndexInspectionAdapter
    resource_inspection: ResourceInspectionAdapter
    page_quality: PageQualityAdapter
    search_performance: SearchPerformanceAdapter
    keyword_research: KeywordResearchAdapter
    organic_visibility: SnapshottingOrganicVisibility
    competitor_research: CompetitorResearchAdapter
    serp_research: SerpResearchAdapter
    site_safety: SiteSafetyAdapter
    web_analytics: WebAnalyticsAdapter
    registry: CapabilityRegistry


def build_runtime() -> SeoRuntime:
    """Construct one consistent dependency graph for the MCP process."""

    gsc = GscClient()
    ga4 = Ga4Client()
    page_inspection = PageInspectionAdapter()
    index_inspection = IndexInspectionAdapter(client=gsc)
    resource_inspection = ResourceInspectionAdapter()
    page_quality = PageQualityAdapter()
    search_performance = SearchPerformanceAdapter(client=gsc)
    keyword_research = KeywordResearchAdapter()
    organic_visibility = SnapshottingOrganicVisibility(OrganicVisibilityGateway())
    competitor_research = CompetitorResearchAdapter()
    serp_research = SerpResearchAdapter()
    site_safety = SiteSafetyAdapter()
    web_analytics = WebAnalyticsAdapter(client=ga4)

    adapters = [
        page_inspection,
        index_inspection,
        resource_inspection,
        page_quality,
        search_performance,
        keyword_research,
        organic_visibility,
        competitor_research,
        serp_research,
        site_safety,
        web_analytics,
    ]
    return SeoRuntime(
        gsc=gsc,
        ga4=ga4,
        page_inspection=page_inspection,
        index_inspection=index_inspection,
        resource_inspection=resource_inspection,
        page_quality=page_quality,
        search_performance=search_performance,
        keyword_research=keyword_research,
        organic_visibility=organic_visibility,
        competitor_research=competitor_research,
        serp_research=serp_research,
        site_safety=site_safety,
        web_analytics=web_analytics,
        registry=build_registry(adapters),
    )
