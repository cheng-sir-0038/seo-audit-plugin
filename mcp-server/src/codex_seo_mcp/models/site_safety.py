from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SiteSafetyStatus(StrEnum):
    NO_KNOWN_THREATS = "no_known_threats"
    POTENTIAL_RISK = "potential_risk"


@dataclass(slots=True)
class SiteSafetyThreat:
    """One Provider-reported threat match for the requested URL or one of its expressions."""

    matched_url: str
    threat_types: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SiteSafety:
    """Provider-neutral website-safety observation.

    `no_known_threats` only means the current Provider did not return a known threat match. It is
    deliberately not named `safe`, because malicious-URL databases can have false negatives and
    false positives.
    """

    url: str
    status: SiteSafetyStatus
    threats: list[SiteSafetyThreat] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.status, SiteSafetyStatus):
            self.status = SiteSafetyStatus(str(self.status))
