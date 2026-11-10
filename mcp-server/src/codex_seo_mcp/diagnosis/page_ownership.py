from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from codex_seo_mcp.diagnosis.ranking import RankingComparison
from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.page_ownership import (
    ContentOverlap,
    PageOwnershipAction,
    PageOwnershipAssessment,
    PageOwnershipObservation,
    PageOwnershipPairEvidence,
    PageOwnershipState,
    PageRoleRelation,
    TargetPageOwnershipState,
    VisibilityImpact,
)


PAGE_OWNERSHIP_SCHEMA_ID = "urn:codex-seo:page-ownership-assessment:v1"


@dataclass(frozen=True, slots=True)
class _PageOwnershipContext:
    query: str
    market: str
    target_page: str | None
    visibility_impact: VisibilityImpact
    observations: tuple[PageOwnershipObservation, ...]
    pair_evidence: tuple[PageOwnershipPairEvidence, ...]
    current_pages: tuple[str, ...]
    previous_pages: tuple[str, ...]
    current_owner: str | None
    previous_owner: str | None
    switching: bool
    target_state: TargetPageOwnershipState
    conflict_pair: PageOwnershipPairEvidence | None
    current_pairs: tuple[PageOwnershipPairEvidence, ...]
    all_current_pairs_distinct: bool

    @classmethod
    def from_input(
        cls,
        *,
        query: str,
        market: str,
        observations: Iterable[PageOwnershipObservation],
        pair_evidence: Iterable[PageOwnershipPairEvidence],
        target_page: str | None,
        visibility_impact: VisibilityImpact | str,
    ) -> "_PageOwnershipContext":
        clean_query = str(query or "").strip()
        clean_market = str(market or "").strip().upper()
        if not clean_query:
            raise ValueError("page ownership query is required")
        if not clean_market:
            raise ValueError("page ownership market is required")

        impact = (
            visibility_impact
            if isinstance(visibility_impact, VisibilityImpact)
            else VisibilityImpact(str(visibility_impact))
        )
        clean_target = _clean(target_page)
        normalized_observations = _normalize_observations(observations)
        normalized_pairs = _normalize_pairs(pair_evidence)
        current_pages = tuple(
            sorted(
                {
                    item.url
                    for item in normalized_observations
                    if item.current_observed or item.current_position is not None
                }
            )
        )
        previous_pages = tuple(
            sorted(
                {
                    item.url
                    for item in normalized_observations
                    if item.previous_observed or item.previous_position is not None
                }
            )
        )
        current_owner = _leader(normalized_observations, current=True)
        previous_owner = _leader(normalized_observations, current=False)
        switching = bool(
            current_owner and previous_owner and current_owner != previous_owner
        )
        target_state = _target_state(clean_target, list(current_pages))
        conflict_pair = _conflict_pair(normalized_pairs)
        current_pairs = tuple(_pairs_for_pages(normalized_pairs, list(current_pages)))
        return cls(
            query=clean_query,
            market=clean_market,
            target_page=clean_target,
            visibility_impact=impact,
            observations=tuple(normalized_observations),
            pair_evidence=tuple(normalized_pairs),
            current_pages=current_pages,
            previous_pages=previous_pages,
            current_owner=current_owner,
            previous_owner=previous_owner,
            switching=switching,
            target_state=target_state,
            conflict_pair=conflict_pair,
            current_pairs=current_pairs,
            all_current_pairs_distinct=_all_pairs_distinct(
                list(current_pages), list(current_pairs)
            ),
        )


@dataclass(slots=True)
class _PageOwnershipDecision:
    state: PageOwnershipState
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


def observations_from_ranking_comparison(
    comparison: RankingComparison,
) -> list[PageOwnershipObservation]:
    """Convert first-party GSC Query×Page comparison facts into ownership observations."""

    return [
        PageOwnershipObservation(
            url=item.page,
            current_position=item.current.position if item.current is not None else None,
            previous_position=item.prior.position if item.prior is not None else None,
            current_observed=item.current is not None,
            previous_observed=item.prior is not None,
        )
        for item in comparison.pages
    ]


def assess_page_ownership(
    *,
    query: str,
    market: str,
    observations: Iterable[PageOwnershipObservation],
    pair_evidence: Iterable[PageOwnershipPairEvidence] = (),
    target_page: str | None = None,
    visibility_impact: VisibilityImpact | str = VisibilityImpact.UNKNOWN,
) -> PageOwnershipAssessment:
    """Deterministically assess query ownership without equating multi-page ranking with harm."""

    context = _PageOwnershipContext.from_input(
        query=query,
        market=market,
        observations=observations,
        pair_evidence=pair_evidence,
        target_page=target_page,
        visibility_impact=visibility_impact,
    )
    decision = _decide_page_ownership(context)
    _append_page_ownership_evidence(context, decision)
    decision.unknowns = _dedupe(decision.unknowns)

    action = _recommended_action(
        state=decision.state,
        target_state=context.target_state,
        switching=context.switching,
        conflict_pair=context.conflict_pair,
        visibility_impact=context.visibility_impact,
    )
    confidence = _confidence(
        state=decision.state,
        unknowns=decision.unknowns,
        conflict_pair=context.conflict_pair,
    )
    return PageOwnershipAssessment(
        query=context.query,
        market=context.market,
        ownership_state=decision.state,
        target_page=context.target_page,
        target_page_state=context.target_state,
        current_owner=context.current_owner,
        previous_owner=context.previous_owner,
        current_ranking_pages=list(context.current_pages),
        previous_ranking_pages=list(context.previous_pages),
        switching_observed=context.switching,
        visibility_impact=context.visibility_impact,
        observations=list(context.observations),
        pair_evidence=list(context.pair_evidence),
        reasons=decision.reasons,
        unknowns=decision.unknowns,
        recommended_action=action,
        confidence=confidence,
    )


def _decide_page_ownership(
    context: _PageOwnershipContext,
) -> _PageOwnershipDecision:
    if context.conflict_pair is not None and (
        context.switching or context.visibility_impact is VisibilityImpact.NEGATIVE
    ):
        return _PageOwnershipDecision(
            state=PageOwnershipState.PROBABLE_CANNIBALIZATION,
            reasons=[
                "至少两个 Ranking Page 承担相同搜索职责且内容高度重叠，并且已经观察到页面切换或负向可见性影响。"
            ],
        )
    if len(context.current_pages) >= 2 and context.all_current_pairs_distinct:
        return _PageOwnershipDecision(
            state=PageOwnershipState.INTENT_SPLIT,
            reasons=[
                "当前有多个 Ranking Page，但页面职责/搜索意图证据显示它们承担不同角色，不能仅因为同一 Query 多页面排名就判定内耗。"
            ],
        )
    if context.switching:
        unknowns = [] if context.pair_evidence else ["page_role_relationship"]
        return _PageOwnershipDecision(
            state=PageOwnershipState.PAGE_SWITCHING,
            reasons=["前后观察点的主要 Ranking Page 发生切换，但当前证据不足以确认这是有害的关键词内耗。"],
            unknowns=unknowns,
        )
    if len(context.current_pages) == 1:
        return _PageOwnershipDecision(
            state=PageOwnershipState.STABLE_OWNER,
            reasons=["当前只观察到一个主要 Ranking Page，且没有观察到页面所有权切换。"],
        )
    if not context.current_pages and not context.previous_pages:
        return _PageOwnershipDecision(
            state=PageOwnershipState.INSUFFICIENT_EVIDENCE,
            reasons=["当前没有足够的 Query × Page / Ranking URL 观测，无法判断页面职责。"],
            unknowns=["ranking_pages"],
        )
    if len(context.current_pages) >= 2:
        unknowns: list[str] = []
        if not context.current_pairs:
            unknowns.append("page_role_relationship")
        if context.visibility_impact is VisibilityImpact.UNKNOWN:
            unknowns.append("visibility_impact")
        return _PageOwnershipDecision(
            state=PageOwnershipState.INSUFFICIENT_EVIDENCE,
            reasons=[
                "当前有多个 Ranking Page，但页面意图/内容重叠或负向影响证据不足，不能把多页面排名直接解释为关键词内耗。"
            ],
            unknowns=unknowns,
        )
    return _PageOwnershipDecision(
        state=PageOwnershipState.INSUFFICIENT_EVIDENCE,
        reasons=["当前页面职责证据不完整，无法形成稳定结论。"],
    )


def _append_page_ownership_evidence(
    context: _PageOwnershipContext,
    decision: _PageOwnershipDecision,
) -> None:
    if context.target_state is TargetPageOwnershipState.MISMATCHED:
        decision.reasons.append(
            "用户预期的 Target Page 当前没有被观察为 Ranking Page；这属于页面职责错位事实，但不能在缺少页面意图证据时直接要求 canonical/redirect。"
        )
    elif context.target_state is TargetPageOwnershipState.MATCHED:
        decision.reasons.append("当前实际 Ranking Page 集合包含用户预期的 Target Page。")

    if (
        context.conflict_pair is not None
        and decision.state is not PageOwnershipState.PROBABLE_CANNIBALIZATION
    ):
        decision.reasons.append(
            "存在相同职责且高度重叠的页面，但尚未观察到足够的页面切换/负向可见性影响，因此暂不升级为已确认内耗。"
        )
        if context.visibility_impact is VisibilityImpact.UNKNOWN:
            decision.unknowns.append("visibility_impact")

    if len(context.current_pages) >= 2 and not context.pair_evidence:
        decision.unknowns.append("page_role_relationship")



def _normalize_observations(
    observations: Iterable[PageOwnershipObservation],
) -> list[PageOwnershipObservation]:
    merged: dict[str, PageOwnershipObservation] = {}
    for raw in observations:
        url = _clean(raw.url)
        if not url:
            continue
        current_position = _position(raw.current_position)
        previous_position = _position(raw.previous_position)
        existing = merged.get(url)
        current_observed = bool(raw.current_observed or current_position is not None)
        previous_observed = bool(raw.previous_observed or previous_position is not None)
        if existing is None:
            merged[url] = PageOwnershipObservation(
                url=url,
                current_position=current_position,
                previous_position=previous_position,
                current_observed=current_observed,
                previous_observed=previous_observed,
            )
            continue
        existing.current_observed = existing.current_observed or current_observed
        existing.previous_observed = existing.previous_observed or previous_observed
        existing.current_position = _best_position(existing.current_position, current_position)
        existing.previous_position = _best_position(existing.previous_position, previous_position)
    return [merged[url] for url in sorted(merged)]


def _normalize_pairs(
    pairs: Iterable[PageOwnershipPairEvidence],
) -> list[PageOwnershipPairEvidence]:
    normalized: dict[tuple[str, str], PageOwnershipPairEvidence] = {}
    for raw in pairs:
        page_a = _clean(raw.page_a)
        page_b = _clean(raw.page_b)
        if not page_a or not page_b or page_a == page_b:
            continue
        key = tuple(sorted((page_a, page_b)))
        role = raw.role_relation if isinstance(raw.role_relation, PageRoleRelation) else PageRoleRelation(str(raw.role_relation))
        overlap = raw.content_overlap if isinstance(raw.content_overlap, ContentOverlap) else ContentOverlap(str(raw.content_overlap))
        normalized[key] = PageOwnershipPairEvidence(
            page_a=key[0],
            page_b=key[1],
            role_relation=role,
            content_overlap=overlap,
        )
    return [normalized[key] for key in sorted(normalized)]


def _leader(observations: list[PageOwnershipObservation], *, current: bool) -> str | None:
    ranked: list[tuple[float, str]] = []
    for item in observations:
        position = item.current_position if current else item.previous_position
        observed = item.current_observed if current else item.previous_observed
        if observed and position is not None:
            ranked.append((position, item.url))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked[0][1]


def _target_state(
    target_page: str | None,
    current_pages: list[str],
) -> TargetPageOwnershipState:
    if not target_page or not current_pages:
        return TargetPageOwnershipState.UNKNOWN
    return (
        TargetPageOwnershipState.MATCHED
        if target_page in current_pages
        else TargetPageOwnershipState.MISMATCHED
    )


def _conflict_pair(
    pairs: list[PageOwnershipPairEvidence],
) -> PageOwnershipPairEvidence | None:
    for item in pairs:
        if (
            item.role_relation is PageRoleRelation.SAME
            and item.content_overlap is ContentOverlap.HIGH
        ):
            return item
    return None


def _pairs_for_pages(
    pairs: list[PageOwnershipPairEvidence], pages: list[str]
) -> list[PageOwnershipPairEvidence]:
    allowed = set(pages)
    return [item for item in pairs if item.page_a in allowed and item.page_b in allowed]


def _all_pairs_distinct(
    pages: list[str], pairs: list[PageOwnershipPairEvidence]
) -> bool:
    if len(pages) < 2:
        return False
    required = len(pages) * (len(pages) - 1) // 2
    if len(pairs) < required:
        return False
    relations = {
        tuple(sorted((item.page_a, item.page_b))): item.role_relation for item in pairs
    }
    for index, page_a in enumerate(pages):
        for page_b in pages[index + 1 :]:
            if relations.get(tuple(sorted((page_a, page_b)))) is not PageRoleRelation.DISTINCT:
                return False
    return True


def _recommended_action(
    *,
    state: PageOwnershipState,
    target_state: TargetPageOwnershipState,
    switching: bool,
    conflict_pair: PageOwnershipPairEvidence | None,
    visibility_impact: VisibilityImpact,
) -> PageOwnershipAction:
    if state is PageOwnershipState.PROBABLE_CANNIBALIZATION:
        return PageOwnershipAction.CONSOLIDATE_OR_DIFFERENTIATE
    if state is PageOwnershipState.INTENT_SPLIT:
        return PageOwnershipAction.KEEP_ROLES_DISTINCT
    if state is PageOwnershipState.PAGE_SWITCHING:
        return PageOwnershipAction.CLARIFY_PAGE_ROLES
    if state is PageOwnershipState.STABLE_OWNER:
        if target_state is TargetPageOwnershipState.MISMATCHED:
            return PageOwnershipAction.REASSESS_TARGET_PAGE
        return PageOwnershipAction.KEEP_OR_STRENGTHEN_OWNER
    if (
        state is PageOwnershipState.INSUFFICIENT_EVIDENCE
        and conflict_pair is not None
        and not switching
        and visibility_impact in {VisibilityImpact.NEUTRAL, VisibilityImpact.POSITIVE}
    ):
        return PageOwnershipAction.MONITOR
    return PageOwnershipAction.COLLECT_ROLE_EVIDENCE


def _confidence(
    *,
    state: PageOwnershipState,
    unknowns: list[str],
    conflict_pair: PageOwnershipPairEvidence | None,
) -> Confidence:
    if state is PageOwnershipState.PROBABLE_CANNIBALIZATION and conflict_pair and not unknowns:
        return Confidence.HIGH
    if state in {PageOwnershipState.STABLE_OWNER, PageOwnershipState.INTENT_SPLIT} and not unknowns:
        return Confidence.HIGH
    if state is PageOwnershipState.INSUFFICIENT_EVIDENCE:
        return Confidence.LOW
    return Confidence.MEDIUM if unknowns else Confidence.HIGH


def _position(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _best_position(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _clean(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        if item not in result:
            result.append(item)
    return result
