"""Codex SEO MCP 领域模型。

模型只表达跨 Provider 稳定的 SEO 数据语义，不暴露第三方 SDK 类型。
"""

from codex_seo_mcp.models.common import (
    CapabilityResult,
    CapabilitySourceKind,
    CapabilityStatus,
    Confidence,
)
from codex_seo_mcp.models.competitor_research import CompetitorResearch
from codex_seo_mcp.models.content_lifecycle import (
    ContentLifecycleAction,
    ContentLifecycleAssessment,
    ContentLifecycleSignals,
    ContentLifecycleState,
    FitState,
    FreshnessState,
    GapState,
    PurposeState,
    TrendState,
    ValueState,
)
from codex_seo_mcp.models.hreflang import (
    HreflangAssessment,
    HreflangIssue,
    HreflangIssueCode,
    HreflangState,
)
from codex_seo_mcp.models.index_inspection import IndexInspection
from codex_seo_mcp.models.keyword_opportunity import (
    KeywordDemandLevel,
    KeywordFitState,
    KeywordOpportunityAction,
    KeywordOpportunityAssessment,
    KeywordOpportunityLevel,
    KeywordOpportunityScenario,
    KeywordOpportunitySignals,
    KeywordOpportunityStatus,
    KeywordOpportunityTiming,
    KeywordSignalState,
)
from codex_seo_mcp.models.keyword_research import KeywordResearch
from codex_seo_mcp.models.organic_visibility import (
    OrganicVisibility,
    OrganicVisibilityKeywordStatus,
    OrganicVisibilitySnapshot,
)
from codex_seo_mcp.models.page_ownership import (
    ContentOverlap,
    PageOwnershipAction,
    PageOwnershipAssessment,
    PageOwnershipObservation,
    PageOwnershipPairEvidence,
    PageOwnershipState,
    PageRoleRelation,
    TargetPageOwnershipState,
    VisibilityImpact,
)
from codex_seo_mcp.models.page_inspection import (
    PageHreflangAlternate,
    PageInspection,
    PageRedirectHop,
    PageStructuredDataBlock,
    PageStructuredDataNode,
)
from codex_seo_mcp.models.page_quality import PageQuality
from codex_seo_mcp.models.resource_inspection import ResourceInspection
from codex_seo_mcp.models.search_performance import SearchPerformance
from codex_seo_mcp.models.search_appearance import (
    MetricTrend,
    PresentationState,
    SearchAppearanceAction,
    SearchAppearanceAssessment,
    SearchAppearanceSignals,
    SearchAppearanceState,
)
from codex_seo_mcp.models.serp_research import SerpResearch
from codex_seo_mcp.models.site_migration import (
    InternalLinksMigrationState,
    SiteMigrationAssessment,
    SiteMigrationCoverage,
    SiteMigrationMappingResult,
    SiteMigrationState,
)
from codex_seo_mcp.models.structured_data import (
    RichResultAssessment,
    RichResultRuleStatus,
    RichResultState,
    RichResultTypeCheck,
    StructuredDataAssessment,
    StructuredDataIssue,
    StructuredDataState,
)
from codex_seo_mcp.models.site_safety import SiteSafety, SiteSafetyStatus, SiteSafetyThreat
from codex_seo_mcp.models.template_regression import (
    TemplateRegressionAssessment,
    TemplateRegressionIssue,
    TemplateRegressionIssueCode,
    TemplateRegressionSeverity,
    TemplateRegressionState,
    TemplateSeoSnapshot,
)
from codex_seo_mcp.models.url_lifecycle import (
    CanonicalState,
    ErrorPageSignal,
    RedirectState,
    Soft404State,
    TargetState,
    UrlLifecycleAssessment,
    UrlLifecycleIntent,
    UrlLifecycleState,
    UrlRedirectObservation,
)
from codex_seo_mcp.models.web_analytics import (
    WebAnalytics,
    WebAnalyticsPeriod,
    WebAnalyticsRow,
)

__all__ = [
    "CapabilityResult",
    "CapabilitySourceKind",
    "CapabilityStatus",
    "Confidence",
    "CompetitorResearch",
    "ContentLifecycleAction",
    "ContentLifecycleAssessment",
    "ContentLifecycleSignals",
    "ContentLifecycleState",
    "FitState",
    "FreshnessState",
    "GapState",
    "PurposeState",
    "TrendState",
    "ValueState",
    "HreflangAssessment",
    "HreflangIssue",
    "HreflangIssueCode",
    "HreflangState",
    "IndexInspection",
    "KeywordDemandLevel",
    "KeywordFitState",
    "KeywordOpportunityAction",
    "KeywordOpportunityAssessment",
    "KeywordOpportunityLevel",
    "KeywordOpportunityScenario",
    "KeywordOpportunitySignals",
    "KeywordOpportunityStatus",
    "KeywordOpportunityTiming",
    "KeywordSignalState",
    "KeywordResearch",
    "OrganicVisibility",
    "OrganicVisibilityKeywordStatus",
    "OrganicVisibilitySnapshot",
    "ContentOverlap",
    "PageOwnershipAction",
    "PageOwnershipAssessment",
    "PageOwnershipObservation",
    "PageOwnershipPairEvidence",
    "PageOwnershipState",
    "PageRoleRelation",
    "TargetPageOwnershipState",
    "VisibilityImpact",
    "PageInspection",
    "PageHreflangAlternate",
    "PageRedirectHop",
    "PageStructuredDataBlock",
    "PageStructuredDataNode",
    "InternalLinksMigrationState",
    "SiteMigrationAssessment",
    "SiteMigrationCoverage",
    "SiteMigrationMappingResult",
    "SiteMigrationState",
    "StructuredDataAssessment",
    "StructuredDataIssue",
    "StructuredDataState",
    "RichResultAssessment",
    "RichResultRuleStatus",
    "RichResultState",
    "RichResultTypeCheck",
    "SiteSafety",
    "SiteSafetyStatus",
    "SiteSafetyThreat",
    "TemplateRegressionAssessment",
    "TemplateRegressionIssue",
    "TemplateRegressionIssueCode",
    "TemplateRegressionSeverity",
    "TemplateRegressionState",
    "TemplateSeoSnapshot",
    "PageQuality",
    "ResourceInspection",
    "SearchPerformance",
    "MetricTrend",
    "PresentationState",
    "SearchAppearanceAction",
    "SearchAppearanceAssessment",
    "SearchAppearanceSignals",
    "SearchAppearanceState",
    "SerpResearch",
    "CanonicalState",
    "ErrorPageSignal",
    "RedirectState",
    "Soft404State",
    "TargetState",
    "UrlLifecycleAssessment",
    "UrlLifecycleIntent",
    "UrlLifecycleState",
    "UrlRedirectObservation",
    "WebAnalytics",
    "WebAnalyticsPeriod",
    "WebAnalyticsRow",
]
