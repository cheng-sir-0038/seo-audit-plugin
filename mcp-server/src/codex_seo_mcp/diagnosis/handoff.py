from __future__ import annotations

import json
from dataclasses import dataclass, field

from codex_seo_mcp.diagnosis.contracts import DiagnosisResult


HANDOFF_SCHEMA_ID = "urn:codex-seo:diagnosis-handoff:v1"
HANDOFF_BLOCKS = (
    "task",
    "target",
    "diagnosis",
    "evidence",
    "desiredState",
    "constraints",
    "progress",
    "continuation",
)


class HandoffContractError(ValueError):
    """Diagnosis Handoff 不满足“新 Agent 可独立续跑”的最小契约。"""


@dataclass(slots=True)
class HandoffTask:
    """下游为什么接手，以及最终要达成什么目标。"""

    goal: str
    handoff_reason: str


@dataclass(slots=True)
class HandoffTarget:
    """下游需要重新定位的真实工作对象。

    `kind` 保持跨 Provider，例如 repository / cms-object / web-resource；`locator` 保存
    可机器定位的最小身份。WordPress 等扩展可以使用 site/object_type/object_id，代码
    Host 可以使用 repository/revision/path，而不把某个 CMS 的字段写死进 SEO Core。
    """

    kind: str
    locator: dict[str, str]


@dataclass(slots=True)
class HandoffEvidence:
    """可追溯证据引用及给新 Agent 快速恢复上下文的短摘要。"""

    ref: str
    summary: str


@dataclass(slots=True)
class HandoffDesiredState:
    """任务完成后应成立的状态与验收条件，而不是具体执行命令。"""

    summary: str
    outcomes: dict[str, object] = field(default_factory=dict)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HandoffConstraints:
    """执行边界；防止下游 Agent 为了完成任务顺手扩大修改范围。"""

    scope: list[str] = field(default_factory=list)
    must: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HandoffProgress:
    """前一个 Agent 已完成、尝试和决定的工作，避免新 Agent 重复调查。"""

    completed: list[str] = field(default_factory=list)
    attempted: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HandoffContinuation:
    """新 Agent 接手后的第一步以及完成后需要重新验证什么。"""

    next_action: str
    verification: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DiagnosisHandoff:
    """跨 Host 的 Minimum Resumable Handoff。

    顶层固定为 8 个工作块。它必须在没有旧聊天历史的情况下仍足以让新的 Agent 继续，
    因此不能用一段 Prompt 替代结构化任务状态。Prompt 如有需要只能由 Host 从本对象
    渲染，不能成为 Source of Truth。
    """

    task: HandoffTask
    target: HandoffTarget
    diagnosis: DiagnosisResult
    evidence: list[HandoffEvidence]
    desired_state: HandoffDesiredState
    constraints: HandoffConstraints
    progress: HandoffProgress
    continuation: HandoffContinuation

    def validate_resumable(self) -> None:
        """验证这份 Handoff 是否足以交给一个没有旧上下文的新 Agent。"""

        errors = self.resumability_errors()
        if errors:
            raise HandoffContractError("; ".join(errors))

    def resumability_errors(self) -> list[str]:
        """返回缺失的续跑信息；空列表表示满足最小工作集。"""

        errors: list[str] = []
        if not self.task.goal.strip():
            errors.append("task.goal 不能为空")
        if not self.task.handoff_reason.strip():
            errors.append("task.handoff_reason 不能为空")

        if not self.target.kind.strip():
            errors.append("target.kind 不能为空")
        if not self.target.locator or any(
            not str(key).strip() or not str(value).strip()
            for key, value in self.target.locator.items()
        ):
            errors.append("target.locator 必须包含可机器定位的非空键值")

        if not self.diagnosis.summary.strip():
            errors.append("diagnosis.summary 不能为空")
        if not (
            self.diagnosis.findings
            or self.diagnosis.hypotheses
            or self.diagnosis.unknowns
        ):
            errors.append("diagnosis 至少需要 Finding、Hypothesis 或 Unknown")

        if not self.evidence:
            errors.append("evidence 不能为空")
        evidence_refs = {item.ref.strip() for item in self.evidence if item.ref.strip()}
        if any(not item.ref.strip() or not item.summary.strip() for item in self.evidence):
            errors.append("evidence 每项都需要 ref 和 summary")

        diagnosis_refs = set(self.diagnosis.source_refs)
        for finding in self.diagnosis.findings:
            diagnosis_refs.update(finding.source_refs)
        for hypothesis in self.diagnosis.hypotheses:
            diagnosis_refs.update(hypothesis.source_refs)
        missing_refs = sorted(ref for ref in diagnosis_refs if ref and ref not in evidence_refs)
        if missing_refs:
            errors.append("evidence 缺少 diagnosis 引用：" + ", ".join(missing_refs))

        if not self.desired_state.summary.strip():
            errors.append("desiredState.summary 不能为空")
        if not self.desired_state.acceptance_criteria:
            errors.append("desiredState.acceptance_criteria 至少需要一项")
        if not self.constraints.scope:
            errors.append("constraints.scope 至少需要一项")
        if not self.progress.completed:
            errors.append("progress.completed 至少需要一项，说明上游已经完成什么")
        if not self.continuation.next_action.strip():
            errors.append("continuation.next_action 不能为空")
        if not self.continuation.verification:
            errors.append("continuation.verification 至少需要一项")
        return errors

    def to_dict(self, *, validate: bool = True) -> dict[str, object]:
        """转换为 Host/CMS 可直接传输的结构化 payload。"""

        if validate:
            self.validate_resumable()
        payload: dict[str, object] = {
            "task": {
                "goal": self.task.goal,
                "handoffReason": self.task.handoff_reason,
            },
            "target": {
                "kind": self.target.kind,
                # locator/outcomes 是扩展 Map，key 由消费者定义，Core 不擅自改名。
                "locator": dict(self.target.locator),
            },
            "diagnosis": self.diagnosis.to_dict(),
            "evidence": [
                {"ref": item.ref, "summary": item.summary} for item in self.evidence
            ],
            "desiredState": {
                "summary": self.desired_state.summary,
                "outcomes": dict(self.desired_state.outcomes),
                "acceptanceCriteria": list(self.desired_state.acceptance_criteria),
            },
            "constraints": {
                "scope": list(self.constraints.scope),
                "must": list(self.constraints.must),
                "mustNot": list(self.constraints.must_not),
            },
            "progress": {
                "completed": list(self.progress.completed),
                "attempted": list(self.progress.attempted),
                "decisions": list(self.progress.decisions),
                "blocked": list(self.progress.blocked),
            },
            "continuation": {
                "nextAction": self.continuation.next_action,
                "verification": list(self.continuation.verification),
            },
        }
        # 顶层工作集是协议边界；新增字段必须通过版本化 Schema，而不是临时塞 Prompt。
        if tuple(payload) != HANDOFF_BLOCKS:
            raise HandoffContractError("DiagnosisHandoff 顶层工作集发生未版本化变化")
        try:
            json.dumps(payload, ensure_ascii=False)
        except TypeError as exc:
            raise HandoffContractError("DiagnosisHandoff 必须只包含 JSON 可序列化数据") from exc
        return payload
