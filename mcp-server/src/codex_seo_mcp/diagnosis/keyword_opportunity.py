from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.keyword_opportunity import (
    KEYWORD_OPPORTUNITY_SCENARIOS,
    KeywordDemandLevel,
    KeywordFitState,
    KeywordOpportunityAction,
    KeywordOpportunityAssessment,
    KeywordOpportunityLevel,
    KeywordOpportunityScenario,
    KeywordOpportunitySignals,
    KeywordOpportunityStatus,
    KeywordOpportunityTiming,
    KeywordSignalState,
)


@dataclass(frozen=True, slots=True)
class _KeywordOpportunityContext:
    scenario: KeywordOpportunityScenario
    keyword: str
    market: str
    signals: KeywordOpportunitySignals
    target_domain: str | None
    target_page: str | None
    competitor_domains: tuple[str, ...]
    missing_inputs: tuple[str, ...]

    @classmethod
    def from_input(
        cls,
        *,
        scenario: KeywordOpportunityScenario | str,
        keyword: str,
        market: str,
        signals: KeywordOpportunitySignals,
        target_domain: str | None,
        target_page: str | None,
        competitor_domains: Sequence[str] | None,
    ) -> "_KeywordOpportunityContext":
        selected = _scenario(scenario)
        clean_keyword = str(keyword or "").strip()
        clean_market = str(market or "").strip().upper()
        competitors = tuple(
            str(item).strip()
            for item in (competitor_domains or [])
            if str(item).strip()
        )
        missing = missing_scenario_inputs(
            selected,
            keyword=clean_keyword,
            market=clean_market,
            target_domain=target_domain,
            target_page=target_page,
            competitor_domains=competitors,
        )
        if not clean_keyword and "keyword" not in missing:
            missing.insert(0, "keyword")
        return cls(
            scenario=selected,
            keyword=clean_keyword,
            market=clean_market,
            signals=signals,
            target_domain=_clean(target_domain),
            target_page=_clean(target_page),
            competitor_domains=competitors,
            missing_inputs=tuple(missing),
        )


@dataclass(slots=True)
class _KeywordOpportunityDecision:
    status: KeywordOpportunityStatus
    value_level: KeywordOpportunityLevel | None = None
    feasibility_level: KeywordOpportunityLevel | None = None
    opportunity_level: KeywordOpportunityLevel | None = None
    timing: KeywordOpportunityTiming | None = None
    action: KeywordOpportunityAction | None = None
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    include_target_context: bool = True


def missing_scenario_inputs(
    scenario: KeywordOpportunityScenario | str,
    *,
    keyword: str | None = None,
    market: str | None,
    target_domain: str | None = None,
    target_page: str | None = None,
    competitor_domains: Sequence[str] | None = None,
) -> list[str]:
    """Return user-input gaps before a scenario should start provider research."""

    selected = _scenario(scenario)
    missing: list[str] = []
    if selected is KeywordOpportunityScenario.METRIC_LOOKUP and not str(keyword or "").strip():
        missing.append("keyword")
    if not str(market or "").strip():
        missing.append("market")
    if selected in {KeywordOpportunityScenario.SITE_RESEARCH, KeywordOpportunityScenario.PAGE_RESEARCH, KeywordOpportunityScenario.OPPORTUNITY_DISCOVERY, KeywordOpportunityScenario.COMPETITOR_GAP}:
        if not str(target_domain or "").strip():
            missing.append("target_domain")
    if selected is KeywordOpportunityScenario.PAGE_RESEARCH and not str(target_page or "").strip():
        missing.append("target_page")
    if selected is KeywordOpportunityScenario.COMPETITOR_GAP and not [item for item in (competitor_domains or []) if str(item).strip()]:
        missing.append("competitor_domains")
    return missing


def classify_relative_demand(
    search_volume: int | None,
    cohort_volumes: Sequence[int | None] | None,
) -> KeywordDemandLevel:
    """Classify demand relative to the candidate set instead of using one cross-industry cutoff."""

    if search_volume is None or search_volume < 0:
        return KeywordDemandLevel.UNKNOWN
    cohort = sorted(
        int(item)
        for item in (cohort_volumes or [])
        if item is not None and int(item) >= 0
    )
    if len(cohort) < 3:
        return KeywordDemandLevel.UNKNOWN
    less_or_equal = sum(1 for value in cohort if value <= search_volume)
    percentile = less_or_equal / len(cohort)
    if percentile >= 0.70:
        return KeywordDemandLevel.HIGH
    if percentile <= 0.30:
        return KeywordDemandLevel.LOW
    return KeywordDemandLevel.MEDIUM


def evaluate_keyword_opportunity(
    *,
    scenario: KeywordOpportunityScenario | str,
    keyword: str,
    market: str,
    signals: KeywordOpportunitySignals,
    target_domain: str | None = None,
    target_page: str | None = None,
    competitor_domains: Sequence[str] | None = None,
) -> KeywordOpportunityAssessment:
    """Deterministically map normalized evidence into a scenario-specific keyword decision."""

    context = _KeywordOpportunityContext.from_input(
        scenario=scenario,
        keyword=keyword,
        market=market,
        signals=signals,
        target_domain=target_domain,
        target_page=target_page,
        competitor_domains=competitor_domains,
    )
    decision = _decide_keyword_opportunity(context)
    return _build_keyword_opportunity_assessment(context, decision)


def _decide_keyword_opportunity(
    context: _KeywordOpportunityContext,
) -> _KeywordOpportunityDecision:
    signals = context.signals
    if context.missing_inputs:
        missing = list(context.missing_inputs)
        return _KeywordOpportunityDecision(
            status=KeywordOpportunityStatus.NEEDS_INPUT,
            missing_inputs=missing,
            unknowns=list(missing),
            confidence=Confidence.LOW,
        )

    if context.scenario is KeywordOpportunityScenario.METRIC_LOOKUP:
        return _KeywordOpportunityDecision(
            status=KeywordOpportunityStatus.FACTS_ONLY,
            feasibility_level=_feasibility_from_kd(signals.keyword_difficulty),
            reasons=[
                "当前场景只查询关键词市场事实；没有目标站点上下文，不生成站点级机会等级。"
            ],
            unknowns=["target_domain"],
            confidence=Confidence.HIGH,
            include_target_context=False,
        )

    context_unknowns = _keyword_context_unknowns(context)
    if context_unknowns:
        return _KeywordOpportunityDecision(
            status=KeywordOpportunityStatus.INSUFFICIENT_EVIDENCE,
            reasons=[
                "缺少决定关键词业务价值或需求强度的上下文，不能把未知信号默认成中等后继续给出机会/时机结论。"
            ],
            unknowns=context_unknowns,
            confidence=Confidence.LOW,
        )

    value = _value(signals)
    feasibility = _feasibility(signals)
    if feasibility is None:
        unknowns = _unknowns(signals)
        if "feasibility" not in unknowns:
            unknowns.append("feasibility")
        return _KeywordOpportunityDecision(
            status=KeywordOpportunityStatus.INSUFFICIENT_EVIDENCE,
            value_level=value,
            reasons=[
                "当前没有足够的 KD、已有排名信号或等价证据判断排名可行性，因此不输出“现在做/后续做”。"
            ],
            unknowns=unknowns,
            confidence=Confidence.LOW,
        )

    opportunity, timing = _opportunity_matrix(value, feasibility)
    action = _recommended_action(
        scenario=context.scenario,
        value=value,
        feasibility=feasibility,
        timing=timing,
        signals=signals,
        target_page=context.target_page,
    )
    unknowns = _unknowns(signals)
    confidence = (
        Confidence.HIGH
        if not unknowns
        else Confidence.MEDIUM
        if len(unknowns) <= 2
        else Confidence.LOW
    )
    return _KeywordOpportunityDecision(
        status=KeywordOpportunityStatus.ASSESSED,
        value_level=value,
        feasibility_level=feasibility,
        opportunity_level=opportunity,
        timing=timing,
        action=action,
        reasons=_reasons(context.scenario, signals, value, feasibility, action),
        unknowns=unknowns,
        confidence=confidence,
    )


def _keyword_context_unknowns(
    context: _KeywordOpportunityContext,
) -> list[str]:
    signals = context.signals
    unknowns: list[str] = []
    if signals.business_fit is KeywordFitState.UNKNOWN:
        unknowns.append("business_fit")
    if signals.intent_fit is KeywordFitState.UNKNOWN:
        unknowns.append("intent_fit")
    if signals.demand_level is KeywordDemandLevel.UNKNOWN:
        unknowns.append("demand_level")
    if (
        context.scenario is KeywordOpportunityScenario.PAGE_RESEARCH
        and signals.page_fit is KeywordFitState.UNKNOWN
    ):
        unknowns.append("page_fit")
    return unknowns


def _build_keyword_opportunity_assessment(
    context: _KeywordOpportunityContext,
    decision: _KeywordOpportunityDecision,
) -> KeywordOpportunityAssessment:
    target_domain = context.target_domain if decision.include_target_context else None
    target_page = context.target_page if decision.include_target_context else None
    competitors = (
        list(context.competitor_domains) if decision.include_target_context else []
    )
    return KeywordOpportunityAssessment(
        scenario=context.scenario,
        keyword=context.keyword,
        market=context.market,
        status=decision.status,
        value_level=decision.value_level,
        feasibility_level=decision.feasibility_level,
        opportunity_level=decision.opportunity_level,
        recommended_timing=decision.timing,
        recommended_action=decision.action,
        target_domain=target_domain,
        target_page=target_page,
        competitor_domains=competitors,
        signals=context.signals,
        reasons=decision.reasons,
        unknowns=decision.unknowns,
        missing_inputs=decision.missing_inputs,
        confidence=decision.confidence,
    )



def _value(signals: KeywordOpportunitySignals) -> KeywordOpportunityLevel:
    if signals.business_fit is KeywordFitState.WEAK:
        return KeywordOpportunityLevel.LOW
    transactional = any(
        intent.upper() in {"COMMERCIAL", "TRANSACTIONAL"} for intent in signals.intents
    )
    if signals.business_fit is KeywordFitState.STRONG:
        if signals.intent_fit is KeywordFitState.WEAK:
            return KeywordOpportunityLevel.MEDIUM if signals.demand_level is KeywordDemandLevel.HIGH else KeywordOpportunityLevel.LOW
        if signals.demand_level in {KeywordDemandLevel.HIGH, KeywordDemandLevel.MEDIUM}:
            return KeywordOpportunityLevel.HIGH if signals.intent_fit is KeywordFitState.STRONG else KeywordOpportunityLevel.MEDIUM
        if signals.demand_level is KeywordDemandLevel.LOW:
            return KeywordOpportunityLevel.HIGH if signals.intent_fit is KeywordFitState.STRONG and transactional else KeywordOpportunityLevel.MEDIUM
        return KeywordOpportunityLevel.HIGH if signals.intent_fit is KeywordFitState.STRONG and transactional else KeywordOpportunityLevel.MEDIUM
    # medium business fit
    if signals.intent_fit is KeywordFitState.WEAK:
        return KeywordOpportunityLevel.LOW
    if signals.demand_level is KeywordDemandLevel.HIGH and signals.intent_fit is KeywordFitState.STRONG:
        return KeywordOpportunityLevel.HIGH
    if signals.demand_level in {KeywordDemandLevel.HIGH, KeywordDemandLevel.MEDIUM}:
        return KeywordOpportunityLevel.MEDIUM
    return KeywordOpportunityLevel.LOW if signals.demand_level is KeywordDemandLevel.LOW else KeywordOpportunityLevel.MEDIUM


def _feasibility(signals: KeywordOpportunitySignals) -> KeywordOpportunityLevel | None:
    level = _feasibility_from_kd(signals.keyword_difficulty)

    existing = signals.existing_signal
    if signals.current_position is not None:
        if signals.current_position <= 20:
            existing = KeywordSignalState.STRONG
        elif signals.current_position <= 50 and existing in {KeywordSignalState.UNKNOWN, KeywordSignalState.NONE, KeywordSignalState.WEAK}:
            existing = KeywordSignalState.MEDIUM

    if existing is KeywordSignalState.STRONG:
        level = KeywordOpportunityLevel.HIGH if level is None else _raise(level)
    elif existing is KeywordSignalState.MEDIUM:
        if level is None or level is KeywordOpportunityLevel.LOW:
            level = KeywordOpportunityLevel.MEDIUM

    if level is not None and signals.serp_fit is KeywordFitState.WEAK:
        level = _lower(level)
    return level


def _feasibility_from_kd(kd: float | None) -> KeywordOpportunityLevel | None:
    if kd is None:
        return None
    value = max(0.0, min(float(kd), 100.0))
    if value <= 29:
        return KeywordOpportunityLevel.HIGH
    if value <= 49:
        return KeywordOpportunityLevel.MEDIUM
    if value <= 69:
        return KeywordOpportunityLevel.LOW
    return KeywordOpportunityLevel.LOW


def _opportunity_matrix(
    value: KeywordOpportunityLevel,
    feasibility: KeywordOpportunityLevel,
) -> tuple[KeywordOpportunityLevel, KeywordOpportunityTiming]:
    if value is KeywordOpportunityLevel.LOW:
        return KeywordOpportunityLevel.LOW, KeywordOpportunityTiming.IGNORE
    if value is KeywordOpportunityLevel.HIGH:
        if feasibility is KeywordOpportunityLevel.HIGH:
            return KeywordOpportunityLevel.HIGH, KeywordOpportunityTiming.NOW
        if feasibility is KeywordOpportunityLevel.MEDIUM:
            return KeywordOpportunityLevel.MEDIUM, KeywordOpportunityTiming.NOW
        return KeywordOpportunityLevel.MEDIUM, KeywordOpportunityTiming.LATER
    if feasibility is KeywordOpportunityLevel.HIGH:
        return KeywordOpportunityLevel.MEDIUM, KeywordOpportunityTiming.TEST
    if feasibility is KeywordOpportunityLevel.MEDIUM:
        return KeywordOpportunityLevel.MEDIUM, KeywordOpportunityTiming.TEST
    return KeywordOpportunityLevel.LOW, KeywordOpportunityTiming.LATER


def _recommended_action(
    *,
    scenario: KeywordOpportunityScenario,
    value: KeywordOpportunityLevel,
    feasibility: KeywordOpportunityLevel,
    timing: KeywordOpportunityTiming,
    signals: KeywordOpportunitySignals,
    target_page: str | None,
) -> KeywordOpportunityAction:
    if value is KeywordOpportunityLevel.LOW:
        return KeywordOpportunityAction.IGNORE
    if timing is KeywordOpportunityTiming.LATER or feasibility is KeywordOpportunityLevel.LOW:
        return KeywordOpportunityAction.LATER

    has_existing = bool(signals.current_ranking_url or target_page)
    if scenario is KeywordOpportunityScenario.PAGE_RESEARCH and signals.page_fit is KeywordFitState.WEAK:
        return _new_page_action(signals.intents)
    if has_existing:
        if signals.existing_signal is KeywordSignalState.STRONG or (
            signals.current_position is not None and signals.current_position <= 20
        ):
            return KeywordOpportunityAction.OPTIMIZE_EXISTING_PAGE
        return KeywordOpportunityAction.EXPAND_EXISTING_PAGE
    if signals.serp_fit is KeywordFitState.UNKNOWN or signals.intent_fit is KeywordFitState.UNKNOWN:
        return KeywordOpportunityAction.MONITOR
    return _new_page_action(signals.intents)


def _new_page_action(intents: Sequence[str]) -> KeywordOpportunityAction:
    normalized = {str(item).upper() for item in intents}
    if normalized & {"COMMERCIAL", "TRANSACTIONAL"}:
        return KeywordOpportunityAction.CREATE_NEW_LANDING_PAGE
    return KeywordOpportunityAction.CREATE_NEW_ARTICLE


def _reasons(
    scenario: KeywordOpportunityScenario,
    signals: KeywordOpportunitySignals,
    value: KeywordOpportunityLevel,
    feasibility: KeywordOpportunityLevel,
    action: KeywordOpportunityAction,
) -> list[str]:
    reasons = [
        f"业务价值判断为 {value.value}：business_fit={signals.business_fit.value}，intent_fit={signals.intent_fit.value}，demand={signals.demand_level.value}。",
        f"可行性判断为 {feasibility.value}：KD={_format_kd(signals.keyword_difficulty)}，existing_signal={signals.existing_signal.value}，serp_fit={signals.serp_fit.value}。",
    ]
    if signals.keyword_difficulty is not None and signals.keyword_difficulty <= 14:
        reasons.append("KD 位于 Semrush 0–14 的 Very easy 区间，只说明通用排名难度低，不代表关键词一定有业务价值。")
    if scenario is KeywordOpportunityScenario.COMPETITOR_GAP:
        reasons.append("竞品 Gap 只作为候选信号；机会等级仍由目标站业务匹配和可行性决定。")
    if scenario is KeywordOpportunityScenario.PAGE_RESEARCH and signals.page_fit is KeywordFitState.WEAK:
        reasons.append("当前页面与关键词/搜索结果承接方式不匹配，因此不建议把关键词硬塞进现有页面。")
    reasons.append(f"建议动作：{action.value}。")
    return reasons


def _unknowns(signals: KeywordOpportunitySignals) -> list[str]:
    unknowns = [
        name
        for name, is_unknown in (
            ("demand_level", signals.demand_level is KeywordDemandLevel.UNKNOWN),
            ("intent_fit", signals.intent_fit is KeywordFitState.UNKNOWN),
            ("page_fit", signals.page_fit is KeywordFitState.UNKNOWN),
            ("existing_signal", signals.existing_signal is KeywordSignalState.UNKNOWN),
            ("gap_signal", signals.gap_signal is KeywordSignalState.UNKNOWN),
            ("serp_fit", signals.serp_fit is KeywordFitState.UNKNOWN),
        )
        if is_unknown
    ]
    if signals.keyword_difficulty is None:
        unknowns.append("keyword_difficulty")
    if signals.search_volume is None:
        unknowns.append("search_volume")
    return unknowns


def _scenario(value: KeywordOpportunityScenario | str) -> KeywordOpportunityScenario:
    if isinstance(value, KeywordOpportunityScenario):
        return value
    selected = str(value or "").strip().lower()
    if selected not in KEYWORD_OPPORTUNITY_SCENARIOS:
        raise ValueError(f"unsupported keyword opportunity scenario: {selected or '<empty>'}")
    return KeywordOpportunityScenario(selected)


def _raise(level: KeywordOpportunityLevel) -> KeywordOpportunityLevel:
    return {
        KeywordOpportunityLevel.LOW: KeywordOpportunityLevel.MEDIUM,
        KeywordOpportunityLevel.MEDIUM: KeywordOpportunityLevel.HIGH,
        KeywordOpportunityLevel.HIGH: KeywordOpportunityLevel.HIGH,
    }[level]


def _lower(level: KeywordOpportunityLevel) -> KeywordOpportunityLevel:
    return {
        KeywordOpportunityLevel.HIGH: KeywordOpportunityLevel.MEDIUM,
        KeywordOpportunityLevel.MEDIUM: KeywordOpportunityLevel.LOW,
        KeywordOpportunityLevel.LOW: KeywordOpportunityLevel.LOW,
    }[level]


def _clean(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _format_kd(value: float | None) -> str:
    return "unknown" if value is None else f"{float(value):g}"
