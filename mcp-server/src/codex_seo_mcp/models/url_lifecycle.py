from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


from codex_seo_mcp.models.common import Confidence

class UrlLifecycleIntent(StrEnum):
    OBSERVE = "observe"
    KEEP = "keep"
    PERMANENT_MOVE = "permanent_move"
    TEMPORARY_MOVE = "temporary_move"
    REMOVE = "remove"


class UrlLifecycleState(StrEnum):
    HEALTHY = "healthy"
    REMOVED = "removed"
    NEEDS_ATTENTION = "needs_attention"
    MISCONFIGURED = "misconfigured"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RedirectState(StrEnum):
    NONE = "none"
    DIRECT_PERMANENT = "direct_permanent"
    DIRECT_TEMPORARY = "direct_temporary"
    CHAIN = "chain"
    MIXED_CHAIN = "mixed_chain"


class TargetState(StrEnum):
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    UNKNOWN = "unknown"


class CanonicalState(StrEnum):
    FINAL_URL = "final_url"
    EXPECTED_TARGET = "expected_target"
    OTHER = "other"
    MISSING = "missing"


class Soft404State(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    SUSPECTED = "suspected"
    NOT_OBSERVED = "not_observed"
    UNKNOWN = "unknown"


class ErrorPageSignal(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class UrlRedirectObservation:
    from_url: str
    status_code: int
    location: str
    to_url: str


@dataclass(slots=True)
class UrlLifecycleAssessment:
    requested_url: str
    final_url: str
    final_status_code: int
    intent: UrlLifecycleIntent
    expected_target: str | None
    state: UrlLifecycleState
    redirect_state: RedirectState
    target_state: TargetState
    canonical: str | None
    canonical_state: CanonicalState
    soft404_state: Soft404State
    redirects: list[UrlRedirectObservation] = field(default_factory=list)
    issue_codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, object]:
        return {
            "requestedUrl": self.requested_url,
            "finalUrl": self.final_url,
            "finalStatusCode": self.final_status_code,
            "intent": self.intent.value,
            "expectedTarget": self.expected_target,
            "state": self.state.value,
            "redirectState": self.redirect_state.value,
            "targetState": self.target_state.value,
            "canonical": self.canonical,
            "canonicalState": self.canonical_state.value,
            "soft404State": self.soft404_state.value,
            "redirects": [
                {
                    "fromUrl": item.from_url,
                    "statusCode": item.status_code,
                    "location": item.location,
                    "toUrl": item.to_url,
                }
                for item in self.redirects
            ],
            "issueCodes": list(self.issue_codes),
            "reasons": list(self.reasons),
            "recommendedActions": list(self.recommended_actions),
            "unknowns": list(self.unknowns),
            "confidence": self.confidence.value,
        }
