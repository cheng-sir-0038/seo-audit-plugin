from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.url_lifecycle import (
    CanonicalState,
    RedirectState,
    TargetState,
    UrlLifecycleState,
)


class SiteMigrationState(StrEnum):
    PASSED = "passed"
    SAMPLE_PASSED = "sample_passed"
    NEEDS_ATTENTION = "needs_attention"
    FAILED = "failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SiteMigrationCoverage(StrEnum):
    SAMPLE = "sample"
    COMPLETE = "complete"


class InternalLinksMigrationState(StrEnum):
    UPDATED = "updated"
    ISSUES_FOUND = "issues_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"


@dataclass(slots=True)
class SiteMigrationMappingResult:
    old_url: str
    new_url: str
    lifecycle_state: UrlLifecycleState
    target_state: TargetState
    redirect_state: RedirectState
    canonical_state: CanonicalState
    issue_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SiteMigrationAssessment:
    state: SiteMigrationState
    checked_mappings: int
    expected_mappings: int | None
    coverage: SiteMigrationCoverage
    passed_mappings: int
    attention_mappings: int
    failed_mappings: int
    mappings: list[SiteMigrationMappingResult]
    issue_codes: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "checkedMappings": self.checked_mappings,
            "expectedMappings": self.expected_mappings,
            "coverage": self.coverage.value,
            "passedMappings": self.passed_mappings,
            "attentionMappings": self.attention_mappings,
            "failedMappings": self.failed_mappings,
            "mappings": [
                {
                    "oldUrl": item.old_url,
                    "newUrl": item.new_url,
                    "lifecycleState": item.lifecycle_state.value,
                    "targetState": item.target_state.value,
                    "redirectState": item.redirect_state.value,
                    "canonicalState": item.canonical_state.value,
                    "issueCodes": list(item.issue_codes),
                }
                for item in self.mappings
            ],
            "issueCodes": list(self.issue_codes),
            "unknowns": list(self.unknowns),
            "reasons": list(self.reasons),
            "confidence": self.confidence.value,
        }
