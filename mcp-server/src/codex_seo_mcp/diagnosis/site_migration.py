from __future__ import annotations

from collections.abc import Iterable

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.hreflang import HreflangState
from codex_seo_mcp.models.site_migration import (
    InternalLinksMigrationState,
    SiteMigrationAssessment,
    SiteMigrationCoverage,
    SiteMigrationMappingResult,
    SiteMigrationState,
)
from codex_seo_mcp.models.url_lifecycle import UrlLifecycleAssessment, UrlLifecycleState

SITE_MIGRATION_SCHEMA_ID = "urn:codex-seo:site-migration-assessment:v1"


def assess_site_migration(
    mappings: Iterable[UrlLifecycleAssessment],
    *,
    expected_mapping_count: int | None = None,
    new_sitemap_urls: set[str] | None = None,
    internal_links_state: InternalLinksMigrationState | str | None = None,
    multilingual: bool = False,
    hreflang_state: HreflangState | str | None = None,
) -> SiteMigrationAssessment:
    """Aggregate URL-level lifecycle checks into a migration acceptance result.

    This evaluator never upgrades a sample to a full-site pass. Full coverage needs an explicit
    expected mapping count or an external URL inventory that proves every mapping was checked.
    """

    items = list(mappings)
    checked = len(items)
    expected = expected_mapping_count
    if expected is not None and expected < 0:
        raise ValueError("expected_mapping_count must be >= 0")

    results: list[SiteMigrationMappingResult] = []
    issue_codes: list[str] = []
    unknowns: list[str] = []
    passed = attention = failed = 0
    site_attention = False

    for item in items:
        if item.state is UrlLifecycleState.HEALTHY:
            passed += 1
        elif item.state is UrlLifecycleState.NEEDS_ATTENTION:
            attention += 1
        elif item.state is UrlLifecycleState.MISCONFIGURED:
            failed += 1
        else:
            unknowns.append(f"mapping:{item.requested_url}")
        issue_codes.extend(item.issue_codes)
        results.append(
            SiteMigrationMappingResult(
                old_url=item.requested_url,
                new_url=item.expected_target or item.final_url,
                lifecycle_state=item.state,
                target_state=item.target_state,
                redirect_state=item.redirect_state,
                canonical_state=item.canonical_state,
                issue_codes=list(item.issue_codes),
            )
        )

    coverage = SiteMigrationCoverage.SAMPLE
    if expected is not None and checked == expected:
        coverage = SiteMigrationCoverage.COMPLETE
    elif expected is not None and checked < expected:
        unknowns.append("unvalidated_mappings")
    elif expected is None:
        unknowns.append("full_mapping_count")

    if new_sitemap_urls is not None:
        normalized_sitemap = {_norm(url) for url in new_sitemap_urls}
        missing_new = [item.new_url for item in results if _norm(item.new_url) not in normalized_sitemap]
        if missing_new:
            issue_codes.append("mapped_targets_missing_from_new_sitemap")
            site_attention = True
    else:
        unknowns.append("new_sitemap_coverage")

    links_state = _internal_links_state(internal_links_state)
    if links_state is InternalLinksMigrationState.ISSUES_FOUND:
        issue_codes.append("internal_links_not_updated")
        site_attention = True
    elif links_state in {None, InternalLinksMigrationState.INSUFFICIENT_EVIDENCE}:
        unknowns.append("internal_link_migration")

    if multilingual:
        resolved_hreflang_state = _hreflang_state(hreflang_state)
        if resolved_hreflang_state is HreflangState.ISSUES_FOUND:
            issue_codes.append("hreflang_migration_issues")
            site_attention = True
        elif resolved_hreflang_state in {None, HreflangState.INSUFFICIENT_EVIDENCE}:
            unknowns.append("hreflang_migration")

    issue_codes = _dedupe(issue_codes)
    unknowns = _dedupe(unknowns)
    reasons: list[str] = []

    if not items:
        state = SiteMigrationState.INSUFFICIENT_EVIDENCE
        confidence = Confidence.LOW
        reasons.append("没有提供任何 old→new URL mapping 的运行时验证结果，无法验收迁移。")
    elif failed:
        state = SiteMigrationState.FAILED
        confidence = Confidence.HIGH
        reasons.append(f"已检查 mapping 中有 {failed} 条 URL 生命周期配置错误。")
    elif attention or site_attention:
        state = SiteMigrationState.NEEDS_ATTENTION
        confidence = Confidence.MEDIUM if unknowns else Confidence.HIGH
        reasons.append("迁移 mapping 基础链路可用，但仍存在需要修正的 redirect/canonical/sitemap/hreflang 信号。")
    elif coverage is SiteMigrationCoverage.COMPLETE and not unknowns:
        state = SiteMigrationState.PASSED
        confidence = Confidence.HIGH
        reasons.append("已按完整 mapping 数量验证全部 URL，当前没有发现迁移链路异常。")
    elif coverage is SiteMigrationCoverage.COMPLETE and unknowns:
        state = SiteMigrationState.INSUFFICIENT_EVIDENCE
        confidence = Confidence.LOW
        reasons.append("URL mapping 已完整验证，但仍缺少本次迁移范围内要求的 supporting evidence，不能宣布迁移通过。")
    elif passed == checked and checked > 0:
        state = SiteMigrationState.SAMPLE_PASSED
        confidence = Confidence.MEDIUM
        reasons.append("已检查样本均通过，但当前证据不能证明全站所有 URL mapping 都已验证。")
    else:
        state = SiteMigrationState.INSUFFICIENT_EVIDENCE
        confidence = Confidence.LOW
        reasons.append("迁移样本存在未确认状态，需要补齐 mapping 或相关迁移证据。")

    return SiteMigrationAssessment(
        state=state,
        checked_mappings=checked,
        expected_mappings=expected,
        coverage=coverage,
        passed_mappings=passed,
        attention_mappings=attention,
        failed_mappings=failed,
        mappings=results,
        issue_codes=issue_codes,
        unknowns=unknowns,
        reasons=reasons,
        confidence=confidence,
    )


def _internal_links_state(
    value: InternalLinksMigrationState | str | None,
) -> InternalLinksMigrationState | None:
    if value is None or isinstance(value, InternalLinksMigrationState):
        return value
    return InternalLinksMigrationState(str(value))


def _hreflang_state(value: HreflangState | str | None) -> HreflangState | None:
    if value is None or isinstance(value, HreflangState):
        return value
    return HreflangState(str(value))


def _norm(value: str) -> str:
    return str(value).strip().rstrip("/").casefold()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        if item not in result:
            result.append(item)
    return result
