from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from codex_seo_mcp.errors import SeoDataError, SeoDataErrorCode
from codex_seo_mcp.observability import emit_event


class ProviderCostAdmission(StrEnum):
    """System decision before a paid Provider request is executed."""

    AUTO_ALLOWED = "auto_allowed"
    USER_APPROVAL_REQUIRED = "user_approval_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ProviderCostRequirement:
    """Cost fact passed to the Tool dependency/elicitation layer.

    This object is not user consent. It only states whether the deployment policy can run the
    request automatically, must elicit approval, or must block it regardless of approval.
    """

    provider: str
    feature: str
    estimated_multiplier: float
    admission: ProviderCostAdmission


@dataclass(slots=True)
class ProviderCostConfig:
    auto_multiplier_limit: float = 1.0
    approval_multiplier_limit: float = 10.0

    @classmethod
    def from_env(cls) -> "ProviderCostConfig":
        return cls(
            auto_multiplier_limit=_float_env("PROVIDER_AUTO_COST_MULTIPLIER_LIMIT", 1.0),
            approval_multiplier_limit=_float_env("PROVIDER_APPROVAL_COST_MULTIPLIER_LIMIT", 10.0),
        )


class ProviderCostGuard:
    """Classify cost before interaction; human approval cannot override the hard system ceiling."""

    def __init__(self, config: ProviderCostConfig | None = None) -> None:
        self.config = config or ProviderCostConfig.from_env()

    def assess(
        self,
        *,
        provider: str,
        feature: str,
        estimated_multiplier: float,
    ) -> ProviderCostRequirement:
        multiplier = float(estimated_multiplier)
        if multiplier < 1:
            raise ValueError("estimated_multiplier must be >= 1")
        if multiplier <= self.config.auto_multiplier_limit:
            admission = ProviderCostAdmission.AUTO_ALLOWED
        elif multiplier <= self.config.approval_multiplier_limit:
            admission = ProviderCostAdmission.USER_APPROVAL_REQUIRED
        else:
            admission = ProviderCostAdmission.BLOCKED
        emit_event(
            "provider_cost_admission_assessed",
            provider=provider,
            feature=feature,
            estimated_multiplier=multiplier,
            admission=admission.value,
        )
        return ProviderCostRequirement(
            provider=provider,
            feature=feature,
            estimated_multiplier=multiplier,
            admission=admission,
        )

    def require_not_blocked(self, requirement: ProviderCostRequirement) -> None:
        if requirement.admission is not ProviderCostAdmission.BLOCKED:
            return
        raise SeoDataError(
            SeoDataErrorCode.COST_LIMIT_EXCEEDED,
            (
                f"{requirement.feature} 的预计成本倍率 {requirement.estimated_multiplier:g}x "
                f"超过当前系统上限 {self.config.approval_multiplier_limit:g}x"
            ),
        )


def _float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1.0, float(raw))
    except ValueError:
        return default
