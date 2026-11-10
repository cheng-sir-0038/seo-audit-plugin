from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


from codex_seo_mcp.models.common import Confidence

class HreflangState(StrEnum):
    HEALTHY = "healthy"
    ISSUES_FOUND = "issues_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class HreflangIssueCode(StrEnum):
    HREFLANG_MISSING = "hreflang_missing"
    INVALID_HREFLANG_CODE = "invalid_hreflang_code"
    MISSING_SELF_REFERENCE = "missing_self_reference"
    DUPLICATE_HREFLANG_TARGET = "duplicate_hreflang_target"
    CANONICAL_POINTS_ELSEWHERE = "canonical_points_elsewhere"
    ALTERNATE_NOT_SUCCESSFUL = "alternate_not_successful"
    ALTERNATE_NOINDEX = "alternate_noindex"
    RETURN_LINK_MISSING = "return_link_missing"


@dataclass(slots=True)
class HreflangIssue:
    code: HreflangIssueCode
    page_url: str
    hreflang: str | None
    target_url: str | None
    summary: str


@dataclass(slots=True)
class HreflangAssessment:
    state: HreflangState
    pages_checked: list[str]
    x_default_present: bool
    issues: list[HreflangIssue] = field(default_factory=list)
    unknown_targets: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "pagesChecked": list(self.pages_checked),
            "xDefaultPresent": self.x_default_present,
            "issues": [
                {
                    "code": item.code.value,
                    "pageUrl": item.page_url,
                    "hreflang": item.hreflang,
                    "targetUrl": item.target_url,
                    "summary": item.summary,
                }
                for item in self.issues
            ],
            "unknownTargets": list(self.unknown_targets),
            "reasons": list(self.reasons),
            "confidence": self.confidence.value,
        }
