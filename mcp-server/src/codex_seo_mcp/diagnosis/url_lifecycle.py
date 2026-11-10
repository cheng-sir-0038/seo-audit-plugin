from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.page_inspection import PageInspection
from codex_seo_mcp.models.url_lifecycle import (
    CanonicalState,
    ErrorPageSignal,
    RedirectState,
    Soft404State,
    TargetState,
    UrlLifecycleAssessment,
    UrlLifecycleIntent,
    UrlLifecycleState,
    UrlRedirectObservation,
)

URL_LIFECYCLE_SCHEMA_ID = "urn:codex-seo:url-lifecycle-assessment:v1"
_PERMANENT_REDIRECTS = {301, 308}


@dataclass(frozen=True, slots=True)
class _EvaluationContext:
    page: PageInspection
    intent: UrlLifecycleIntent
    expected_target: str | None
    redirects: tuple[UrlRedirectObservation, ...]
    redirect_state: RedirectState
    target_state: TargetState
    canonical_state: CanonicalState
    soft404_state: Soft404State
    check_soft404: bool


@dataclass(slots=True)
class _AssessmentDraft:
    """Collect rule output without leaking aggregation mechanics into each rule."""

    issues: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    severity: int = 0

    def add_issue(
        self,
        code: str,
        reason: str,
        *,
        action: str | None = None,
        severity: int = 0,
    ) -> None:
        self.issues.append(code)
        self.reasons.append(reason)
        if action:
            self.actions.append(action)
        self.severity = max(self.severity, severity)

    def add_reason(self, reason: str) -> None:
        self.reasons.append(reason)

    def add_unknown(self, name: str, reason: str) -> None:
        self.unknowns.append(name)
        self.reasons.append(reason)


_LifecycleRule = Callable[[_EvaluationContext, _AssessmentDraft], None]


def assess_url_lifecycle(
    page: PageInspection,
    *,
    intent: UrlLifecycleIntent | str = UrlLifecycleIntent.OBSERVE,
    expected_target: str | None = None,
    check_soft404: bool = False,
    error_page_signal: ErrorPageSignal | str = ErrorPageSignal.UNKNOWN,
) -> UrlLifecycleAssessment:
    """Evaluate redirect/canonical/status behavior from PageInspection facts.

    The evaluator never guesses redirect status types: PageInspection must preserve every observed
    redirect hop with its HTTP status. Soft-404 classification requires an explicit body/error-page
    signal because the current PageInspection does not yet expose strong body semantics.
    """

    context = _build_context(
        page,
        intent=intent,
        expected_target=expected_target,
        check_soft404=check_soft404,
        error_page_signal=error_page_signal,
    )
    draft = _AssessmentDraft()
    for rule in _COMMON_RULES:
        rule(context, draft)
    _INTENT_RULES[context.intent](context, draft)
    _evaluate_soft404(context, draft)
    return _build_assessment(context, draft)


def _build_context(
    page: PageInspection,
    *,
    intent: UrlLifecycleIntent | str,
    expected_target: str | None,
    check_soft404: bool,
    error_page_signal: ErrorPageSignal | str,
) -> _EvaluationContext:
    lifecycle_intent = intent if isinstance(intent, UrlLifecycleIntent) else UrlLifecycleIntent(str(intent))
    body_signal = (
        error_page_signal
        if isinstance(error_page_signal, ErrorPageSignal)
        else ErrorPageSignal(str(error_page_signal))
    )
    expected = _clean_url(expected_target)
    redirects = tuple(
        UrlRedirectObservation(
            from_url=item.from_url,
            status_code=item.status_code,
            location=item.location,
            to_url=item.to_url,
        )
        for item in page.redirects
    )
    return _EvaluationContext(
        page=page,
        intent=lifecycle_intent,
        expected_target=expected,
        redirects=redirects,
        redirect_state=_redirect_state(redirects),
        target_state=_target_state(page.final_url, expected),
        canonical_state=_canonical_state(page.final_url, page.canonical, expected),
        soft404_state=_soft404_state(
            page.status_code,
            check=check_soft404,
            signal=body_signal,
        ),
        check_soft404=check_soft404,
    )


def _evaluate_redirect_chain(context: _EvaluationContext, draft: _AssessmentDraft) -> None:
    redirect_count = len(context.redirects)
    if redirect_count > 1:
        draft.add_issue(
            "redirect_chain",
            f"当前 URL 经过 {redirect_count} 跳服务端重定向；可以直接指向最终 URL 时应减少中间跳。",
            action="把旧 URL 尽量直接重定向到最终目标，减少中间跳。",
            severity=1,
        )
    if redirect_count > 3:
        draft.add_issue(
            "long_redirect_chain",
            "重定向链已经超过 3 跳，属于明显需要收敛的迁移/URL 生命周期问题。",
            severity=2,
        )


def _evaluate_meta_refresh(context: _EvaluationContext, draft: _AssessmentDraft) -> None:
    if context.page.meta_refresh_url:
        draft.add_issue(
            "meta_refresh_present",
            "最终 HTML 仍声明 Meta Refresh；URL 迁移优先使用服务端 HTTP 重定向。",
            action="确认 Meta Refresh 是否仍有业务必要；迁移场景优先改为服务端重定向。",
            severity=1,
        )


def _evaluate_keep_intent(context: _EvaluationContext, draft: _AssessmentDraft) -> None:
    if context.redirects:
        draft.add_issue(
            "unexpected_redirect",
            "用户意图是保留当前 URL，但实际请求发生了重定向。",
            action="确认当前 URL 是否应该继续作为独立可访问地址；若应保留，移除非预期重定向。",
            severity=2,
        )
    if not 200 <= context.page.status_code < 300:
        draft.add_issue(
            "live_url_not_successful",
            f"应保留的 URL 最终返回 HTTP {context.page.status_code}，没有正常提供成功页面。",
            severity=2,
        )
    if context.page.canonical and context.canonical_state is CanonicalState.OTHER:
        draft.add_issue(
            "canonical_points_elsewhere",
            "应保留的 URL 声明了指向其他地址的 canonical，需要确认是否与页面职责冲突。",
            action="确认该页面是否应独立索引；若是，统一 canonical 与页面真实职责。",
            severity=1,
        )


def _evaluate_move_intent(context: _EvaluationContext, draft: _AssessmentDraft) -> None:
    if context.expected_target is None:
        draft.add_unknown(
            "expected_target",
            "迁移/跳转场景没有提供预期目标 URL，无法验证最终落点是否正确。",
        )
    if not context.redirects:
        draft.add_issue(
            "missing_redirect",
            "用户声明了 URL 迁移/临时跳转意图，但当前请求没有观察到服务端重定向。",
            action="按 old→new 映射配置服务端重定向，并再次验证最终落点。",
            severity=2,
        )
    if context.target_state is TargetState.MISMATCHED:
        draft.add_issue(
            "redirect_target_mismatch",
            "实际最终 URL 与用户提供的预期目标 URL 不一致。",
            action="修正 URL mapping 或重定向规则，使旧 URL 落到最相关的预期新 URL。",
            severity=2,
        )
    if not 200 <= context.page.status_code < 300:
        draft.add_issue(
            "redirect_destination_not_successful",
            f"重定向最终目标返回 HTTP {context.page.status_code}，迁移链路没有落到正常成功页面。",
            severity=2,
        )

    if context.intent is UrlLifecycleIntent.PERMANENT_MOVE and context.redirects:
        if any(item.status_code not in _PERMANENT_REDIRECTS for item in context.redirects):
            draft.add_issue(
                "non_permanent_redirect_in_permanent_move",
                "永久迁移链路中存在非 301/308 的跳转，和永久迁移意图不完全一致。",
                action="永久 URL 迁移优先使用 301/308，并尽量直接跳到最终目标。",
                severity=1,
            )
    if context.intent is UrlLifecycleIntent.TEMPORARY_MOVE and context.redirects:
        if all(item.status_code in _PERMANENT_REDIRECTS for item in context.redirects):
            draft.add_issue(
                "permanent_redirect_for_temporary_move",
                "用户声明为临时跳转，但实际链路只使用永久重定向状态。",
                action="确认跳转是否真的临时；若是，使用与临时意图一致的重定向策略。",
                severity=1,
            )
    if context.page.canonical and context.canonical_state is CanonicalState.OTHER:
        draft.add_issue(
            "destination_canonical_conflict",
            "最终页面 canonical 指向第三个 URL，与当前迁移目标形成冲突信号。",
            action="让新页面 canonical 与最终迁移目标/页面真实职责保持一致。",
            severity=2,
        )


def _evaluate_remove_intent(context: _EvaluationContext, draft: _AssessmentDraft) -> None:
    if context.page.status_code in {404, 410} and not context.redirects:
        draft.add_reason(
            f"该 URL 当前正确返回 HTTP {context.page.status_code}，与明确删除且无替代页面的意图一致。"
        )
        return
    draft.add_issue(
        "removal_not_effective",
        "用户声明该 URL 应直接移除，但当前仍返回成功页面或跳转到其他地址。",
        action="若确实没有替代内容，让旧 URL 返回 404/410；若有最相关替代页，则把业务意图改为 consolidation/move 再验证。",
        severity=2,
    )


def _evaluate_observe_intent(context: _EvaluationContext, draft: _AssessmentDraft) -> None:
    if context.page.status_code >= 500:
        draft.add_issue(
            "server_error",
            f"最终 URL 返回 HTTP {context.page.status_code}，属于当前 URL 生命周期的硬错误事实。",
            action="先恢复 URL 的正常 HTTP 服务，再继续判断 canonical/迁移信号。",
            severity=2,
        )
    elif context.page.status_code in {404, 410}:
        draft.add_reason(
            f"当前 URL 返回 HTTP {context.page.status_code}，可以确认它现在是已移除/不存在状态。"
        )
    if context.page.canonical and context.canonical_state is CanonicalState.OTHER:
        draft.add_issue(
            "canonical_points_elsewhere",
            "当前成功页面声明 canonical 到其他 URL；这可能是合法重复页治理，也可能是页面职责错位，需要结合业务意图判断。",
            severity=1,
        )


def _evaluate_soft404(context: _EvaluationContext, draft: _AssessmentDraft) -> None:
    if context.soft404_state is Soft404State.SUSPECTED:
        draft.add_issue(
            "soft404_suspected",
            "页面返回成功状态，但页面内容证据表明它实际像错误/不存在页面，存在 soft 404 风险。",
            action="让真实不存在内容返回 404/410，或恢复与成功状态一致的有效页面内容。",
            severity=1,
        )
    elif context.soft404_state is Soft404State.UNKNOWN:
        draft.add_unknown(
            "error_page_signal",
            "当前没有足够正文/错误页证据，不能只凭 HTTP 200 判断是否为 soft 404。",
        )


_COMMON_RULES: tuple[_LifecycleRule, ...] = (
    _evaluate_redirect_chain,
    _evaluate_meta_refresh,
)
_INTENT_RULES: dict[UrlLifecycleIntent, _LifecycleRule] = {
    UrlLifecycleIntent.KEEP: _evaluate_keep_intent,
    UrlLifecycleIntent.PERMANENT_MOVE: _evaluate_move_intent,
    UrlLifecycleIntent.TEMPORARY_MOVE: _evaluate_move_intent,
    UrlLifecycleIntent.REMOVE: _evaluate_remove_intent,
    UrlLifecycleIntent.OBSERVE: _evaluate_observe_intent,
}


def _build_assessment(
    context: _EvaluationContext,
    draft: _AssessmentDraft,
) -> UrlLifecycleAssessment:
    issue_codes = _dedupe(draft.issues)
    recommended_actions = _dedupe(draft.actions)
    unknowns = _dedupe(draft.unknowns)
    state = _assessment_state(context, severity=draft.severity)
    confidence = _assessment_confidence(context, state=state, unknowns=unknowns)

    if not recommended_actions and state in {UrlLifecycleState.HEALTHY, UrlLifecycleState.REMOVED}:
        recommended_actions.append("保持当前 URL 生命周期配置，并按业务变更继续监控。")

    return UrlLifecycleAssessment(
        requested_url=context.page.requested_url,
        final_url=context.page.final_url,
        final_status_code=context.page.status_code,
        intent=context.intent,
        expected_target=context.expected_target,
        state=state,
        redirect_state=context.redirect_state,
        target_state=context.target_state,
        canonical=context.page.canonical,
        canonical_state=context.canonical_state,
        soft404_state=context.soft404_state,
        redirects=list(context.redirects),
        issue_codes=issue_codes,
        reasons=list(draft.reasons),
        recommended_actions=recommended_actions,
        unknowns=unknowns,
        confidence=confidence,
    )


def _assessment_state(
    context: _EvaluationContext,
    *,
    severity: int,
) -> UrlLifecycleState:
    if (
        context.intent in {UrlLifecycleIntent.REMOVE, UrlLifecycleIntent.OBSERVE}
        and context.page.status_code in {404, 410}
        and not context.redirects
    ):
        return UrlLifecycleState.REMOVED
    if severity >= 2:
        return UrlLifecycleState.MISCONFIGURED
    if severity == 1:
        return UrlLifecycleState.NEEDS_ATTENTION
    if (
        context.intent in {UrlLifecycleIntent.PERMANENT_MOVE, UrlLifecycleIntent.TEMPORARY_MOVE}
        and context.expected_target is None
    ):
        return UrlLifecycleState.INSUFFICIENT_EVIDENCE
    if context.check_soft404 and context.soft404_state is Soft404State.UNKNOWN:
        return UrlLifecycleState.INSUFFICIENT_EVIDENCE
    return UrlLifecycleState.HEALTHY


def _assessment_confidence(
    context: _EvaluationContext,
    *,
    state: UrlLifecycleState,
    unknowns: list[str],
) -> Confidence:
    confidence = Confidence.HIGH
    if unknowns:
        confidence = Confidence.MEDIUM if state is not UrlLifecycleState.INSUFFICIENT_EVIDENCE else Confidence.LOW
    if (
        context.intent in {UrlLifecycleIntent.PERMANENT_MOVE, UrlLifecycleIntent.TEMPORARY_MOVE}
        and context.expected_target is None
    ):
        confidence = Confidence.LOW
    return confidence


def _redirect_state(redirects: Sequence[UrlRedirectObservation]) -> RedirectState:
    if not redirects:
        return RedirectState.NONE
    if len(redirects) == 1:
        code = redirects[0].status_code
        if code in _PERMANENT_REDIRECTS:
            return RedirectState.DIRECT_PERMANENT
        return RedirectState.DIRECT_TEMPORARY
    kinds = {
        "permanent" if item.status_code in _PERMANENT_REDIRECTS else "temporary"
        for item in redirects
    }
    return RedirectState.MIXED_CHAIN if len(kinds) > 1 else RedirectState.CHAIN


def _target_state(final_url: str, expected_target: str | None) -> TargetState:
    if expected_target is None:
        return TargetState.UNKNOWN
    return TargetState.MATCHED if _same_url(final_url, expected_target) else TargetState.MISMATCHED


def _canonical_state(
    final_url: str,
    canonical: str | None,
    expected_target: str | None,
) -> CanonicalState:
    if not canonical:
        return CanonicalState.MISSING
    if _same_url(canonical, final_url):
        return CanonicalState.FINAL_URL
    if expected_target and _same_url(canonical, expected_target):
        return CanonicalState.EXPECTED_TARGET
    return CanonicalState.OTHER


def _soft404_state(
    status_code: int,
    *,
    check: bool,
    signal: ErrorPageSignal,
) -> Soft404State:
    if not check:
        return Soft404State.NOT_APPLICABLE
    if not 200 <= status_code < 300:
        return Soft404State.NOT_APPLICABLE
    if signal is ErrorPageSignal.PRESENT:
        return Soft404State.SUSPECTED
    if signal is ErrorPageSignal.ABSENT:
        return Soft404State.NOT_OBSERVED
    return Soft404State.UNKNOWN


def _clean_url(value: str | None) -> str | None:
    text = str(value or "").strip()
    if text and "://" not in text:
        text = f"https://{text}"
    return _normalize_compare(text) if text else None


def _same_url(left: str, right: str) -> bool:
    return _normalize_compare(left) == _normalize_compare(right)


def _normalize_compare(value: str) -> str:
    parsed = urlsplit(str(value).strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
