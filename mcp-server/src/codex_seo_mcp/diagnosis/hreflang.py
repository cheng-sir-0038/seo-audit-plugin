from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.hreflang import (
    HreflangAssessment,
    HreflangIssue,
    HreflangIssueCode,
    HreflangState,
)
from codex_seo_mcp.models.page_inspection import PageInspection

HREFLANG_SCHEMA_ID = "urn:codex-seo:hreflang-assessment:v1"
_HREFLANG_CODE = re.compile(
    r"^(?:x-default|[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-[A-Za-z]{2})?)$"
)


@dataclass(frozen=True, slots=True)
class _ClusterIndex:
    by_url: dict[str, PageInspection]

    @classmethod
    def from_pages(cls, pages: list[PageInspection]) -> "_ClusterIndex":
        return cls(by_url={_normalize_url(page.final_url): page for page in pages})

    def find(self, url: str) -> PageInspection | None:
        return self.by_url.get(_normalize_url(url))


@dataclass(slots=True)
class _HreflangDraft:
    issues: list[HreflangIssue] = field(default_factory=list)
    unknown_targets: list[str] = field(default_factory=list)
    unknown_target_keys: set[str] = field(default_factory=set)
    x_default_present: bool = False

    def add_issue(
        self,
        code: HreflangIssueCode,
        *,
        page_url: str,
        hreflang: str | None,
        target_url: str | None,
        summary: str,
    ) -> None:
        self.issues.append(
            HreflangIssue(
                code=code,
                page_url=page_url,
                hreflang=hreflang,
                target_url=target_url,
                summary=summary,
            )
        )

    def add_unknown_target(self, target_url: str) -> None:
        key = _normalize_url(target_url)
        if key in self.unknown_target_keys:
            return
        self.unknown_target_keys.add(key)
        self.unknown_targets.append(target_url)


def assess_hreflang_cluster(pages: list[PageInspection]) -> HreflangAssessment:
    """Validate a localized page cluster from runtime PageInspection facts.

    A target that was not inspected stays an unknown target. The evaluator does not fabricate its
    status/indexability or reciprocal annotation from the source page alone.
    """

    if not pages:
        raise ValueError("hreflang assessment requires at least one PageInspection")

    cluster = _ClusterIndex.from_pages(pages)
    draft = _HreflangDraft()
    for page in pages:
        if not page.hreflang_alternates:
            draft.add_issue(
                HreflangIssueCode.HREFLANG_MISSING,
                page_url=page.final_url,
                hreflang=None,
                target_url=None,
                summary="该本地化页面没有发现 hreflang alternate 声明。",
            )
            continue
        _inspect_page_annotations(page, draft)
        _inspect_alternate_relationships(page, cluster, draft)

    issues = _dedupe_issues(draft.issues)
    state, confidence, reasons = _assessment_outcome(
        issues=issues,
        unknown_targets=draft.unknown_targets,
    )
    if not draft.x_default_present:
        reasons.append(
            "当前集群未发现 x-default；这不是必然错误，只有存在通用语言/地区 fallback 时才需要评估是否添加。"
        )

    return HreflangAssessment(
        state=state,
        pages_checked=sorted(page.final_url for page in pages),
        x_default_present=draft.x_default_present,
        issues=issues,
        unknown_targets=list(draft.unknown_targets),
        reasons=reasons,
        confidence=confidence,
    )


def _inspect_page_annotations(page: PageInspection, draft: _HreflangDraft) -> None:
    source = page.final_url
    self_reference = False
    targets_by_code: dict[str, set[str]] = defaultdict(set)

    for alternate in page.hreflang_alternates:
        code = alternate.hreflang.strip()
        target = alternate.url
        normalized_code = code.casefold()
        targets_by_code[normalized_code].add(_normalize_url(target))
        if normalized_code == "x-default":
            draft.x_default_present = True
        if not _HREFLANG_CODE.fullmatch(code):
            draft.add_issue(
                HreflangIssueCode.INVALID_HREFLANG_CODE,
                page_url=source,
                hreflang=code,
                target_url=target,
                summary=f"hreflang 代码 {code!r} 不符合当前支持的语言/地区格式。",
            )
        if _same_url(target, source):
            self_reference = True

    if not self_reference:
        draft.add_issue(
            HreflangIssueCode.MISSING_SELF_REFERENCE,
            page_url=source,
            hreflang=None,
            target_url=source,
            summary="页面的 hreflang 集合没有包含指向自身的本地化版本。",
        )

    for code, targets in targets_by_code.items():
        if len(targets) > 1:
            draft.add_issue(
                HreflangIssueCode.DUPLICATE_HREFLANG_TARGET,
                page_url=source,
                hreflang=code,
                target_url=None,
                summary="同一个 hreflang 代码在该页面指向多个不同 URL。",
            )

    if page.canonical and not _same_url(page.canonical, source):
        draft.add_issue(
            HreflangIssueCode.CANONICAL_POINTS_ELSEWHERE,
            page_url=source,
            hreflang=None,
            target_url=page.canonical,
            summary="本地化页面 canonical 指向其他 URL，需要确认是否会把该语言/地区版本合并掉。",
        )


def _inspect_alternate_relationships(
    page: PageInspection,
    cluster: _ClusterIndex,
    draft: _HreflangDraft,
) -> None:
    source = page.final_url
    for alternate in page.hreflang_alternates:
        target_page = cluster.find(alternate.url)
        if target_page is None:
            draft.add_unknown_target(alternate.url)
            continue
        if not 200 <= target_page.status_code < 300:
            draft.add_issue(
                HreflangIssueCode.ALTERNATE_NOT_SUCCESSFUL,
                page_url=source,
                hreflang=alternate.hreflang,
                target_url=alternate.url,
                summary=f"hreflang 目标页面最终返回 HTTP {target_page.status_code}。",
            )
        if target_page.declared_noindex:
            draft.add_issue(
                HreflangIssueCode.ALTERNATE_NOINDEX,
                page_url=source,
                hreflang=alternate.hreflang,
                target_url=alternate.url,
                summary="hreflang 目标页面声明了 noindex。",
            )
        if not _links_back(target_page, source):
            draft.add_issue(
                HreflangIssueCode.RETURN_LINK_MISSING,
                page_url=source,
                hreflang=alternate.hreflang,
                target_url=alternate.url,
                summary="目标本地化页面没有返回指向当前页面的 hreflang alternate。",
            )


def _assessment_outcome(
    *,
    issues: list[HreflangIssue],
    unknown_targets: list[str],
) -> tuple[HreflangState, Confidence, list[str]]:
    if issues:
        return (
            HreflangState.ISSUES_FOUND,
            Confidence.HIGH if not unknown_targets else Confidence.MEDIUM,
            [f"已发现 {len(issues)} 个 hreflang 集群问题。"],
        )
    if unknown_targets:
        return (
            HreflangState.INSUFFICIENT_EVIDENCE,
            Confidence.LOW,
            ["当前页面声明看起来一致，但部分 alternate URL 尚未检查，无法确认状态、可索引性和双向关系。"],
        )
    return (
        HreflangState.HEALTHY,
        Confidence.HIGH,
        ["已检查的本地化页面具有自引用、双向 alternate，且目标页面状态/可索引性没有发现冲突。"],
    )


def _links_back(page: PageInspection, source_url: str) -> bool:
    return any(_same_url(item.url, source_url) for item in page.hreflang_alternates)


def _same_url(left: str, right: str) -> bool:
    return _normalize_url(left) == _normalize_url(right)


def _normalize_url(value: str) -> str:
    parsed = urlsplit(str(value).strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _dedupe_issues(values: list[HreflangIssue]) -> list[HreflangIssue]:
    seen: set[tuple[HreflangIssueCode, str, str | None, str | None]] = set()
    result: list[HreflangIssue] = []
    for item in values:
        key = (item.code, item.page_url, item.hreflang, item.target_url)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
