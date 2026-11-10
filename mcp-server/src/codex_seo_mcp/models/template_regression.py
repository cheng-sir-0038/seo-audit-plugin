from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


from codex_seo_mcp.models.common import Confidence

class TemplateRegressionState(StrEnum):
    STABLE = "stable"
    CHANGED = "changed"
    REGRESSION_DETECTED = "regression_detected"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class TemplateRegressionSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TemplateRegressionIssueCode(StrEnum):
    STATUS_REGRESSION = "status_regression"
    NOINDEX_INTRODUCED = "noindex_introduced"
    CANONICAL_CHANGED = "canonical_changed"
    TITLE_STRUCTURE_REGRESSION = "title_structure_regression"
    TITLE_REMOVED = "title_removed"
    DESCRIPTION_REMOVED = "description_removed"
    H1_REMOVED = "h1_removed"
    LANG_CHANGED = "lang_changed"
    HREFLANG_REMOVED = "hreflang_removed"
    HREFLANG_REDUCED = "hreflang_reduced"
    STRUCTURED_DATA_TYPE_REMOVED = "structured_data_type_removed"
    FINAL_URL_CHANGED = "final_url_changed"


@dataclass(slots=True)
class TemplateSeoSnapshot:
    url: str
    status_code: int | None = None
    final_url: str | None = None
    canonical: str | None = None
    declared_noindex: bool | None = None
    title: str | None = None
    title_count: int | None = None
    meta_description: str | None = None
    h1_count: int | None = None
    lang: str | None = None
    hreflang_pairs: list[tuple[str, str]] = field(default_factory=list)
    structured_data_types: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.hreflang_pairs = [
            (str(item[0]), str(item[1]))
            for item in self.hreflang_pairs
            if isinstance(item, (list, tuple)) and len(item) == 2
        ]
        self.structured_data_types = [str(item) for item in self.structured_data_types]


@dataclass(slots=True)
class TemplateRegressionIssue:
    code: TemplateRegressionIssueCode
    url: str
    summary: str
    severity: TemplateRegressionSeverity


@dataclass(slots=True)
class TemplateRegressionAssessment:
    state: TemplateRegressionState
    pages_compared: int
    changed_pages: int
    regression_pages: int
    issues: list[TemplateRegressionIssue] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "pagesCompared": self.pages_compared,
            "changedPages": self.changed_pages,
            "regressionPages": self.regression_pages,
            "issues": [
                {
                    "code": item.code.value,
                    "url": item.url,
                    "summary": item.summary,
                    "severity": item.severity.value,
                }
                for item in self.issues
            ],
            "unknowns": list(self.unknowns),
            "reasons": list(self.reasons),
            "confidence": self.confidence.value,
        }
