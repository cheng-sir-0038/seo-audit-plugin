from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.page_inspection import PageInspection
from codex_seo_mcp.models.template_regression import (
    TemplateRegressionAssessment,
    TemplateRegressionIssue,
    TemplateRegressionIssueCode,
    TemplateRegressionSeverity,
    TemplateRegressionState,
    TemplateSeoSnapshot,
)

TEMPLATE_REGRESSION_SCHEMA_ID = "urn:codex-seo:template-regression-assessment:v1"


@dataclass(frozen=True, slots=True)
class _PageComparisonContext:
    before: TemplateSeoSnapshot
    after: TemplateSeoSnapshot
    url: str


@dataclass(slots=True)
class _PageComparisonDraft:
    url: str
    issues: list[TemplateRegressionIssue] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    changed: bool = False
    regression: bool = False

    def add_issue(
        self,
        code: TemplateRegressionIssueCode,
        summary: str,
        severity: TemplateRegressionSeverity,
        *,
        regression: bool = True,
    ) -> None:
        self.issues.append(
            TemplateRegressionIssue(
                code=code,
                url=self.url,
                summary=summary,
                severity=severity,
            )
        )
        self.changed = True
        if regression:
            self.regression = True

    def add_unknown(self, key: str) -> None:
        self.unknowns.append(key)

    def mark_changed(self) -> None:
        self.changed = True


_PageComparisonRule = Callable[[_PageComparisonContext, _PageComparisonDraft], None]


def snapshot_from_page_inspection(page: PageInspection) -> TemplateSeoSnapshot:
    """Normalize current delivered PageInspection facts into a regression snapshot."""

    structured_types: list[str] = []
    for block in page.structured_data:
        if not block.valid:
            continue
        for schema_type in block.types:
            if schema_type not in structured_types:
                structured_types.append(schema_type)
    return TemplateSeoSnapshot(
        url=page.requested_url,
        status_code=page.status_code,
        final_url=page.final_url,
        canonical=page.canonical,
        declared_noindex=page.declared_noindex,
        title=page.title,
        title_count=page.title_count,
        meta_description=page.meta_description,
        h1_count=len(page.h1),
        lang=page.lang,
        hreflang_pairs=[(item.hreflang, item.url) for item in page.hreflang_alternates],
        structured_data_types=structured_types,
    )


def assess_template_regression(
    before_after: Iterable[tuple[TemplateSeoSnapshot, TemplateSeoSnapshot]],
) -> TemplateRegressionAssessment:
    """Compare representative page facts across a release/template change.

    A temporal before/after difference is evidence of regression in delivered SEO facts, not proof
    that a particular repository commit caused it. Repository localization remains a separate step.
    """

    pairs = list(before_after)
    issues: list[TemplateRegressionIssue] = []
    unknowns: list[str] = []
    changed_pages: set[str] = set()
    regression_pages: set[str] = set()

    for before, after in pairs:
        context = _PageComparisonContext(
            before=before,
            after=after,
            url=after.url or before.url,
        )
        draft = _PageComparisonDraft(url=context.url)
        for rule in _PAGE_COMPARISON_RULES:
            rule(context, draft)

        issues.extend(draft.issues)
        unknowns.extend(draft.unknowns)
        if draft.changed:
            changed_pages.add(context.url)
        if draft.regression:
            regression_pages.add(context.url)

    unknowns = _dedupe(unknowns)
    state, confidence, reasons = _assessment_outcome(
        pairs_count=len(pairs),
        changed_pages=changed_pages,
        regression_pages=regression_pages,
        unknowns=unknowns,
    )
    return TemplateRegressionAssessment(
        state=state,
        pages_compared=len(pairs),
        changed_pages=len(changed_pages),
        regression_pages=len(regression_pages),
        issues=issues,
        unknowns=unknowns,
        reasons=reasons,
        confidence=confidence,
    )


def _status_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before.status_code
    after = context.after.status_code
    if before is None or after is None:
        draft.add_unknown(f"status:{context.url}")
        return
    if 200 <= before < 300 and not 200 <= after < 300:
        draft.add_issue(
            TemplateRegressionIssueCode.STATUS_REGRESSION,
            f"发布前 HTTP {before}，发布后变为 {after}。",
            TemplateRegressionSeverity.HIGH,
        )
    elif before != after:
        draft.mark_changed()


def _indexability_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before.declared_noindex
    after = context.after.declared_noindex
    if before is None or after is None:
        draft.add_unknown(f"robots:{context.url}")
        return
    if not before and after:
        draft.add_issue(
            TemplateRegressionIssueCode.NOINDEX_INTRODUCED,
            "发布后页面新增 noindex。",
            TemplateRegressionSeverity.HIGH,
        )
    elif before != after:
        draft.mark_changed()


def _canonical_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before.canonical
    after = context.after.canonical
    if _norm(before) == _norm(after) or (before is None and after is None):
        return
    draft.add_issue(
        TemplateRegressionIssueCode.CANONICAL_CHANGED,
        f"Canonical 从 {before or '无'} 变为 {after or '无'}。",
        TemplateRegressionSeverity.HIGH,
    )


def _title_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before
    after = context.after
    if before.title_count is not None and after.title_count is not None:
        if before.title_count == 1 and after.title_count != 1:
            draft.add_issue(
                TemplateRegressionIssueCode.TITLE_STRUCTURE_REGRESSION,
                f"发布后 Title 数量从 1 变为 {after.title_count}。",
                TemplateRegressionSeverity.MEDIUM,
            )
    if _text(before.title) == _text(after.title):
        return
    if before.title is not None or after.title is not None:
        draft.mark_changed()
        if before.title and not after.title:
            draft.add_issue(
                TemplateRegressionIssueCode.TITLE_REMOVED,
                "发布后页面 Title 丢失。",
                TemplateRegressionSeverity.MEDIUM,
            )


def _description_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before.meta_description
    after = context.after.meta_description
    if before and not after:
        draft.add_issue(
            TemplateRegressionIssueCode.DESCRIPTION_REMOVED,
            "发布后 Meta Description 丢失。",
            TemplateRegressionSeverity.LOW,
        )
    elif _text(before) != _text(after):
        draft.mark_changed()


def _h1_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before.h1_count
    after = context.after.h1_count
    if before is not None and after is not None and before >= 1 and after == 0:
        draft.add_issue(
            TemplateRegressionIssueCode.H1_REMOVED,
            "发布后页面 H1 丢失。",
            TemplateRegressionSeverity.MEDIUM,
        )


def _lang_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before.lang
    after = context.after.lang
    if before == after or (before is None and after is None):
        return
    draft.add_issue(
        TemplateRegressionIssueCode.LANG_CHANGED,
        f"页面语言声明从 {before or '无'} 变为 {after or '无'}。",
        TemplateRegressionSeverity.MEDIUM,
        regression=False,
    )


def _hreflang_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before.hreflang_pairs
    after = context.after.hreflang_pairs
    if set(before) == set(after):
        return
    draft.mark_changed()
    if before and not after:
        draft.add_issue(
            TemplateRegressionIssueCode.HREFLANG_REMOVED,
            "发布后 hreflang alternate 集合被清空。",
            TemplateRegressionSeverity.HIGH,
        )
    elif len(after) < len(before):
        draft.add_issue(
            TemplateRegressionIssueCode.HREFLANG_REDUCED,
            "发布后 hreflang alternate 数量减少。",
            TemplateRegressionSeverity.MEDIUM,
        )


def _structured_data_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = set(context.before.structured_data_types)
    after = set(context.after.structured_data_types)
    if before == after:
        return
    draft.mark_changed()
    removed = sorted(before - after)
    if removed:
        draft.add_issue(
            TemplateRegressionIssueCode.STRUCTURED_DATA_TYPE_REMOVED,
            f"发布后结构化数据类型减少：{', '.join(removed)}。",
            TemplateRegressionSeverity.MEDIUM,
        )


def _final_url_rule(context: _PageComparisonContext, draft: _PageComparisonDraft) -> None:
    before = context.before.final_url
    after = context.after.final_url
    if before and after and _norm(before) != _norm(after):
        draft.add_issue(
            TemplateRegressionIssueCode.FINAL_URL_CHANGED,
            f"发布后最终 URL 从 {before} 变为 {after}。",
            TemplateRegressionSeverity.HIGH,
        )


_PAGE_COMPARISON_RULES: tuple[_PageComparisonRule, ...] = (
    _status_rule,
    _indexability_rule,
    _canonical_rule,
    _title_rule,
    _description_rule,
    _h1_rule,
    _lang_rule,
    _hreflang_rule,
    _structured_data_rule,
    _final_url_rule,
)


def _assessment_outcome(
    *,
    pairs_count: int,
    changed_pages: set[str],
    regression_pages: set[str],
    unknowns: list[str],
) -> tuple[TemplateRegressionState, Confidence, list[str]]:
    if not pairs_count:
        return (
            TemplateRegressionState.INSUFFICIENT_EVIDENCE,
            Confidence.LOW,
            ["没有 before/after 页面样本，无法判断模板或发布是否改变 SEO 交付事实。"],
        )
    if regression_pages:
        return (
            TemplateRegressionState.REGRESSION_DETECTED,
            Confidence.HIGH if not unknowns else Confidence.MEDIUM,
            [f"已在 {len(regression_pages)} 个样本页面观察到发布后 SEO 交付事实回归。"],
        )
    if changed_pages:
        return (
            TemplateRegressionState.CHANGED,
            Confidence.MEDIUM if unknowns else Confidence.HIGH,
            ["发布前后存在 SEO 事实变化，但当前规则没有把这些变化分类为明确回归。"],
        )
    return (
        TemplateRegressionState.STABLE,
        Confidence.MEDIUM if unknowns else Confidence.HIGH,
        ["已比较样本页面，没有观察到当前规则覆盖的 SEO 交付事实回归。"],
    )


def _norm(value: str | None) -> str:
    return str(value or "").strip().rstrip("/").casefold()


def _text(value: str | None) -> str:
    return " ".join(str(value or "").split()).casefold()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        if item not in result:
            result.append(item)
    return result
