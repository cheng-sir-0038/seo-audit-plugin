from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


from codex_seo_mcp.models.common import Confidence

class PageOwnershipAction(StrEnum):
    CONSOLIDATE_OR_DIFFERENTIATE = "consolidate_or_differentiate"
    KEEP_ROLES_DISTINCT = "keep_roles_distinct"
    CLARIFY_PAGE_ROLES = "clarify_page_roles"
    REASSESS_TARGET_PAGE = "reassess_target_page"
    KEEP_OR_STRENGTHEN_OWNER = "keep_or_strengthen_owner"
    MONITOR = "monitor"
    COLLECT_ROLE_EVIDENCE = "collect_role_evidence"


class PageOwnershipState(StrEnum):
    """Query 的页面职责状态；这是诊断层语义，不是 Provider 原生字段。"""

    STABLE_OWNER = "stable_owner"
    INTENT_SPLIT = "intent_split"
    PAGE_SWITCHING = "page_switching"
    PROBABLE_CANNIBALIZATION = "probable_cannibalization"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class TargetPageOwnershipState(StrEnum):
    """用户预期 Target Page 与当前实际 Ranking Page 的关系。"""

    MATCHED = "matched"
    MISMATCHED = "mismatched"
    UNKNOWN = "unknown"


class VisibilityImpact(StrEnum):
    """同一 Query/Page ownership 观察期内的可见性影响。"""

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    UNKNOWN = "unknown"


class PageRoleRelation(StrEnum):
    """两页是否承担同一搜索意图/页面职责。"""

    SAME = "same"
    DISTINCT = "distinct"
    UNKNOWN = "unknown"


class ContentOverlap(StrEnum):
    """两页主体主题/内容重叠程度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class PageOwnershipObservation:
    """一个 URL 在当前/前一观察点的排名事实。"""

    url: str
    current_position: float | None = None
    previous_position: float | None = None
    current_observed: bool = False
    previous_observed: bool = False


@dataclass(slots=True)
class PageOwnershipPairEvidence:
    """两页的页面职责/内容关系，由 SERP + 页面证据归一化后交给 evaluator。"""

    page_a: str
    page_b: str
    role_relation: PageRoleRelation = PageRoleRelation.UNKNOWN
    content_overlap: ContentOverlap = ContentOverlap.UNKNOWN


@dataclass(slots=True)
class PageOwnershipAssessment:
    """稳定的页面职责诊断 wire model。

    它只表达 Query 的页面职责状态，不把“多个 Ranking URL”直接等同于关键词内耗。
    """

    query: str
    market: str
    ownership_state: PageOwnershipState
    target_page: str | None
    target_page_state: TargetPageOwnershipState
    current_owner: str | None
    previous_owner: str | None
    current_ranking_pages: list[str]
    previous_ranking_pages: list[str]
    switching_observed: bool
    visibility_impact: VisibilityImpact
    observations: list[PageOwnershipObservation]
    pair_evidence: list[PageOwnershipPairEvidence] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    recommended_action: PageOwnershipAction = PageOwnershipAction.COLLECT_ROLE_EVIDENCE
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict[str, object]:
        """返回 Host-neutral、可版本化校验的稳定 wire payload。"""

        return {
            "query": self.query,
            "market": self.market,
            "ownershipState": self.ownership_state.value,
            "targetPage": self.target_page,
            "targetPageState": self.target_page_state.value,
            "currentOwner": self.current_owner,
            "previousOwner": self.previous_owner,
            "currentRankingPages": list(self.current_ranking_pages),
            "previousRankingPages": list(self.previous_ranking_pages),
            "switchingObserved": self.switching_observed,
            "visibilityImpact": self.visibility_impact.value,
            "observations": [
                {
                    "url": item.url,
                    "currentPosition": item.current_position,
                    "previousPosition": item.previous_position,
                    "currentObserved": item.current_observed,
                    "previousObserved": item.previous_observed,
                }
                for item in self.observations
            ],
            "pairEvidence": [
                {
                    "pageA": item.page_a,
                    "pageB": item.page_b,
                    "roleRelation": item.role_relation.value,
                    "contentOverlap": item.content_overlap.value,
                }
                for item in self.pair_evidence
            ],
            "reasons": list(self.reasons),
            "unknowns": list(self.unknowns),
            "recommendedAction": self.recommended_action.value,
            "confidence": self.confidence.value,
        }
