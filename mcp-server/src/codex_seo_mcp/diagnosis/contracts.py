from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from codex_seo_mcp.models.common import Confidence


class FindingStatus(StrEnum):
    """Finding 是否已由当前证据成立。"""

    CONFIRMED = "confirmed"
    PLAUSIBLE = "plausible"
    ALREADY_SAFE = "already-safe"
    UNPROVEN = "unproven"


class HypothesisStatus(StrEnum):
    """因果 Hypothesis 当前证据状态。"""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially-supported"
    EXCLUDED = "excluded"
    INSUFFICIENT_DATA = "insufficient-data"


class ActionCategory(StrEnum):
    """跨 Host 稳定的下一步行动类别。"""

    TECHNICAL = "technical"
    PAGE_STRUCTURE = "page-structure"
    INDEXING = "indexing"
    CONTENT = "content"
    KEYWORD_STRATEGY = "keyword-strategy"
    OBSERVATION = "observation"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class RankingPremiseStatus(StrEnum):
    """用户声称“排名/自然搜索下降”这一前提本身的验证状态。"""

    DECLINE_CONFIRMED = "decline-confirmed"
    MIXED_CHANGE = "mixed-change"
    DECLINE_NOT_CONFIRMED = "decline-not-confirmed"
    INSUFFICIENT_DATA = "insufficient-data"


@dataclass(slots=True)
class Finding:
    """完成证据判断后的一个诊断事项。

    `source_refs` 只引用可追溯的数据、页面或代码来源。公司内部 Task/Capability ID 不
    进入这个通用 Contract，Host 自己把 `action_category` 映射到业务流程。
    """

    type: str
    subject: str
    status: FindingStatus
    confidence: Confidence
    summary: str
    rationale: str
    action_category: ActionCategory
    source_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Hypothesis:
    """排名下降等因果调查中的一个独立假设。"""

    type: str
    status: HypothesisStatus
    rationale: str
    source_refs: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DiagnosisResult:
    """跨 Host 的通用诊断输出外壳。

    这个对象只表达专业判断结果，不包含公司派单、审批、发布或内部对象 ID。
    `premise_status` 主要服务 Ranking Drop；Technical Audit 可以留空。
    """

    diagnosis_type: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    premise_status: RankingPremiseStatus | None = None

    def to_dict(self) -> dict[str, object]:
        """返回跨 Host 稳定的 Diagnosis wire payload。

        展示层不进入这个 Contract。Codex、Web UI 或其他 Host 可以基于同一 payload
        自行渲染 Markdown、表格、卡片或图表。
        """

        return {
            "diagnosisType": self.diagnosis_type,
            "summary": self.summary,
            "findings": [
                {
                    "type": finding.type,
                    "subject": finding.subject,
                    "status": finding.status.value,
                    "confidence": finding.confidence.value,
                    "summary": finding.summary,
                    "rationale": finding.rationale,
                    "actionCategory": finding.action_category.value,
                    "sourceRefs": list(finding.source_refs),
                }
                for finding in self.findings
            ],
            "hypotheses": [
                {
                    "type": hypothesis.type,
                    "status": hypothesis.status.value,
                    "rationale": hypothesis.rationale,
                    "sourceRefs": list(hypothesis.source_refs),
                    "unknowns": list(hypothesis.unknowns),
                }
                for hypothesis in self.hypotheses
            ],
            "unknowns": list(self.unknowns),
            "sourceRefs": list(self.source_refs),
            "premiseStatus": self.premise_status.value if self.premise_status else None,
        }
