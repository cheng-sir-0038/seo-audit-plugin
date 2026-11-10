from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


from codex_seo_mcp.models.common import Confidence

class RichResultState(StrEnum):
    ISSUES_FOUND = "issues_found"
    NO_SUPPORTED_MARKUP = "no_supported_markup"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RichResultRuleStatus(StrEnum):
    NOT_CHECKED = "not_checked"
    MISSING_REQUIRED_PROPERTIES = "missing_required_properties"
    REQUIRED_PROPERTY_PRESENCE_PASSED = "required_property_presence_passed"
    NO_REQUIRED_PROPERTIES = "no_required_properties"


class StructuredDataState(StrEnum):
    MARKUP_PRESENT = "markup_present"
    ISSUES_FOUND = "issues_found"
    NO_MARKUP = "no_markup"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(slots=True)
class StructuredDataIssue:
    code: str
    summary: str
    block_index: int | None = None
    schema_type: str | None = None


@dataclass(slots=True)
class StructuredDataAssessment:
    page_url: str
    state: StructuredDataState
    json_ld_block_count: int
    valid_json_ld_blocks: int
    invalid_json_ld_blocks: int
    observed_types: list[str]
    expected_types: list[str]
    issues: list[StructuredDataIssue] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageUrl": self.page_url,
            "state": self.state.value,
            "jsonLdBlockCount": self.json_ld_block_count,
            "validJsonLdBlocks": self.valid_json_ld_blocks,
            "invalidJsonLdBlocks": self.invalid_json_ld_blocks,
            "observedTypes": list(self.observed_types),
            "expectedTypes": list(self.expected_types),
            "issues": [
                {
                    "code": item.code,
                    "summary": item.summary,
                    "blockIndex": item.block_index,
                    "schemaType": item.schema_type,
                }
                for item in self.issues
            ],
            "unknowns": list(self.unknowns),
            "reasons": list(self.reasons),
            "confidence": self.confidence.value,
        }


@dataclass(slots=True)
class RichResultTypeCheck:
    """One current Google rich-result rule profile applied to one JSON-LD entity."""

    schema_type: str
    feature: str | None
    rule_status: RichResultRuleStatus
    required_properties: list[str] = field(default_factory=list)
    missing_required_properties: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RichResultAssessment:
    """Derived rich-result readiness, intentionally separate from PageInspection facts.

    `state` is about the current rule profile and evidence completeness. It never means Google will
    actually display a rich result.
    """

    page_url: str
    rules_version: str
    state: RichResultState
    checks: list[RichResultTypeCheck] = field(default_factory=list)
    issues: list[StructuredDataIssue] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageUrl": self.page_url,
            "rulesVersion": self.rules_version,
            "state": self.state.value,
            "checks": [
                {
                    "schemaType": item.schema_type,
                    "feature": item.feature,
                    "ruleStatus": item.rule_status.value,
                    "requiredProperties": list(item.required_properties),
                    "missingRequiredProperties": list(item.missing_required_properties),
                    "notes": list(item.notes),
                }
                for item in self.checks
            ],
            "issues": [
                {
                    "code": item.code,
                    "summary": item.summary,
                    "blockIndex": item.block_index,
                    "schemaType": item.schema_type,
                }
                for item in self.issues
            ],
            "unknowns": list(self.unknowns),
            "reasons": list(self.reasons),
            "confidence": self.confidence.value,
        }
