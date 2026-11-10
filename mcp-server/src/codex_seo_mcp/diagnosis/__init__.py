"""Codex SEO 通用诊断领域契约与确定性事实计算。"""

from codex_seo_mcp.diagnosis.contracts import (
    ActionCategory,
    Confidence,
    DiagnosisResult,
    Finding,
    FindingStatus,
    Hypothesis,
    HypothesisStatus,
    RankingPremiseStatus,
)
from codex_seo_mcp.diagnosis.handoff import (
    HANDOFF_BLOCKS,
    HANDOFF_SCHEMA_ID,
    DiagnosisHandoff,
    HandoffConstraints,
    HandoffContinuation,
    HandoffContractError,
    HandoffDesiredState,
    HandoffEvidence,
    HandoffProgress,
    HandoffTarget,
    HandoffTask,
)
from codex_seo_mcp.diagnosis.content_lifecycle import (
    CONTENT_LIFECYCLE_SCHEMA_ID,
    assess_content_lifecycle,
)
from codex_seo_mcp.diagnosis.hreflang import HREFLANG_SCHEMA_ID, assess_hreflang_cluster
from codex_seo_mcp.diagnosis.keyword_opportunity import (
    classify_relative_demand,
    evaluate_keyword_opportunity,
    missing_scenario_inputs,
)
from codex_seo_mcp.diagnosis.page_ownership import (
    PAGE_OWNERSHIP_SCHEMA_ID,
    assess_page_ownership,
    observations_from_ranking_comparison,
)
from codex_seo_mcp.diagnosis.ranking import (
    RANKING_COMPARISON_SCHEMA_ID,
    RankingComparison,
    build_ranking_comparison,
)
from codex_seo_mcp.diagnosis.search_appearance import (
    SEARCH_APPEARANCE_SCHEMA_ID,
    assess_search_appearance,
)
from codex_seo_mcp.diagnosis.site_migration import (
    SITE_MIGRATION_SCHEMA_ID,
    assess_site_migration,
)
from codex_seo_mcp.diagnosis.structured_data import (
    STRUCTURED_DATA_SCHEMA_ID,
    assess_structured_data,
)
from codex_seo_mcp.diagnosis.template_regression import (
    TEMPLATE_REGRESSION_SCHEMA_ID,
    assess_template_regression,
    snapshot_from_page_inspection,
)
from codex_seo_mcp.diagnosis.url_lifecycle import (
    URL_LIFECYCLE_SCHEMA_ID,
    assess_url_lifecycle,
)

__all__ = [
    "ActionCategory",
    "Confidence",
    "DiagnosisResult",
    "Finding",
    "FindingStatus",
    "HANDOFF_BLOCKS",
    "HANDOFF_SCHEMA_ID",
    "DiagnosisHandoff",
    "HandoffConstraints",
    "HandoffContinuation",
    "HandoffContractError",
    "HandoffDesiredState",
    "HandoffEvidence",
    "HandoffProgress",
    "HandoffTarget",
    "HandoffTask",
    "Hypothesis",
    "HypothesisStatus",
    "CONTENT_LIFECYCLE_SCHEMA_ID",
    "assess_content_lifecycle",
    "HREFLANG_SCHEMA_ID",
    "assess_hreflang_cluster",
    "classify_relative_demand",
    "evaluate_keyword_opportunity",
    "missing_scenario_inputs",
    "PAGE_OWNERSHIP_SCHEMA_ID",
    "assess_page_ownership",
    "observations_from_ranking_comparison",
    "RankingPremiseStatus",
    "RANKING_COMPARISON_SCHEMA_ID",
    "RankingComparison",
    "build_ranking_comparison",
    "SEARCH_APPEARANCE_SCHEMA_ID",
    "assess_search_appearance",
    "SITE_MIGRATION_SCHEMA_ID",
    "assess_site_migration",
    "STRUCTURED_DATA_SCHEMA_ID",
    "assess_structured_data",
    "TEMPLATE_REGRESSION_SCHEMA_ID",
    "assess_template_regression",
    "snapshot_from_page_inspection",
    "URL_LIFECYCLE_SCHEMA_ID",
    "assess_url_lifecycle",
]
