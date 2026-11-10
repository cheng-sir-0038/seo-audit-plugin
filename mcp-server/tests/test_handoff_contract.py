from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from codex_seo_mcp.diagnosis.contracts import (
    ActionCategory,
    Confidence,
    DiagnosisResult,
    Finding,
    FindingStatus,
)
from codex_seo_mcp.diagnosis.handoff import (
    HANDOFF_BLOCKS,
    HANDOFF_SCHEMA_ID,
    DiagnosisHandoff,
    HandoffConstraints,
    HandoffContinuation,
    HandoffContractError,
    HandoffDesiredState,
    HandoffEvidence,
    HandoffProgress,
    HandoffTarget,
    HandoffTask,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "diagnosis-handoff.v1.schema.json"


def _handoff(*, target_kind: str = "repository") -> DiagnosisHandoff:
    source_ref = "PageInspection:https://example.com/a"
    finding = Finding(
        type="canonical_mismatch",
        subject="https://example.com/a",
        status=FindingStatus.CONFIRMED,
        confidence=Confidence.HIGH,
        summary="页面 canonical 指向错误 URL",
        rationale="最终 HTML canonical 指向 /b",
        action_category=ActionCategory.TECHNICAL,
        source_refs=[source_ref],
    )
    diagnosis = DiagnosisResult(
        diagnosis_type="technical-seo-audit",
        summary="canonical mismatch 已确认",
        findings=[finding],
        source_refs=[source_ref],
    )
    locator = (
        {
            "repository": "example/web",
            "revision": "main",
            "path": "src/seo/canonical.ts",
        }
        if target_kind == "repository"
        else {
            "site": "https://example.com",
            "objectType": "post",
            "objectId": "123",
        }
    )
    return DiagnosisHandoff(
        task=HandoffTask(
            goal="让 canonical 与当前页面 URL 一致",
            handoff_reason="诊断已确认工程问题，需要下游执行",
        ),
        target=HandoffTarget(kind=target_kind, locator=locator),
        diagnosis=diagnosis,
        evidence=[
            HandoffEvidence(
                ref=source_ref,
                summary="最终 HTML canonical=https://example.com/b",
            )
        ],
        desired_state=HandoffDesiredState(
            summary="页面 canonical 指向 https://example.com/a",
            outcomes={"canonical": "https://example.com/a"},
            acceptance_criteria=[
                "最终 HTML 只有一个 canonical",
                "canonical 等于 https://example.com/a",
            ],
        ),
        constraints=HandoffConstraints(
            scope=["canonical generation"],
            must=["保持当前页面可访问"],
            must_not=["修改页面 URL", "新增 301"],
        ),
        progress=HandoffProgress(
            completed=["已验证线上 HTML", "已定位 owning implementation"],
            attempted=["已排除反向代理注入 canonical"],
            decisions=["保持现有路由行为"],
        ),
        continuation=HandoffContinuation(
            next_action="在目标系统形成最小变更计划",
            verification=["重新读取最终 HTML", "确认页面仍返回 200"],
        ),
    )


class DiagnosisHandoffTests(unittest.TestCase):
    def test_serializes_exactly_eight_resumable_blocks_and_matches_schema(self) -> None:
        """新 Agent 只拿 Handoff 也应有完整任务状态，而不是依赖旧 Prompt/聊天记录。"""

        handoff = _handoff()
        payload = handoff.to_dict()

        self.assertEqual(tuple(payload), HANDOFF_BLOCKS)
        self.assertEqual(payload["task"]["handoffReason"], "诊断已确认工程问题，需要下游执行")
        self.assertEqual(payload["continuation"]["nextAction"], "在目标系统形成最小变更计划")
        self.assertNotIn("prompt", payload)
        self.assertNotIn("conversationHistory", payload)

        schema = json.loads(SCHEMA.read_text())
        self.assertEqual(schema["$id"], HANDOFF_SCHEMA_ID)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)

    def test_requires_progress_and_continuation_for_true_resumability(self) -> None:
        """只有 Finding/Evidence 不够；没有进度与下一步时不能宣称可续跑。"""

        handoff = _handoff()
        handoff.progress.completed = []
        handoff.continuation.verification = []

        with self.assertRaises(HandoffContractError) as context:
            handoff.validate_resumable()

        message = str(context.exception)
        self.assertIn("progress.completed", message)
        self.assertIn("continuation.verification", message)

    def test_requires_all_diagnosis_source_refs_to_be_present_in_evidence(self) -> None:
        """诊断引用必须能在 Handoff evidence 中重新找到，防止新 Agent 接到无来源结论。"""

        handoff = _handoff()
        handoff.evidence = [HandoffEvidence(ref="other", summary="无关证据")]

        with self.assertRaisesRegex(HandoffContractError, "evidence 缺少 diagnosis 引用"):
            handoff.validate_resumable()

    def test_target_locator_supports_cms_extensions_without_coupling_core_to_wordpress(self) -> None:
        """第三方 CMS 只通过 generic target locator 消费，不把 WordPress 字段写死成 Core 顶层。"""

        payload = _handoff(target_kind="cms-object").to_dict()

        self.assertEqual(payload["target"]["kind"], "cms-object")
        self.assertEqual(payload["target"]["locator"]["objectType"], "post")
        self.assertEqual(payload["target"]["locator"]["objectId"], "123")
        self.assertEqual(tuple(payload), HANDOFF_BLOCKS)

    def test_extension_map_keys_are_preserved_exactly(self) -> None:
        """Core 只规范自己的字段名，不能偷偷改写 CMS locator 或 desired outcomes 的键。"""

        handoff = _handoff()
        handoff.target.locator["object_id"] = "123"
        handoff.desired_state.outcomes["custom_policy"] = "index,follow"

        payload = handoff.to_dict()

        self.assertEqual(payload["target"]["locator"]["object_id"], "123")
        self.assertEqual(
            payload["desiredState"]["outcomes"]["custom_policy"],
            "index,follow",
        )

    def test_rejects_non_json_extension_values(self) -> None:
        """跨 Host Handoff 必须能真正序列化，不能让扩展 Map 塞进 Python 私有对象。"""

        handoff = _handoff()
        handoff.desired_state.outcomes["opaque"] = object()

        with self.assertRaisesRegex(HandoffContractError, "JSON 可序列化"):
            handoff.to_dict()

    def test_schema_itself_forbids_prompt_as_a_ninth_top_level_block(self) -> None:
        """Prompt 只能由 Host 渲染，不能偷偷升级成 Handoff 的第九块。"""

        schema = json.loads(SCHEMA.read_text())
        self.assertEqual(tuple(schema["required"]), HANDOFF_BLOCKS)
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("prompt", schema["properties"])

    def test_machine_schema_rejects_an_empty_diagnosis(self) -> None:
        """非 Python Host 只做 JSON Schema 校验时也不能放过空诊断。"""

        payload = _handoff().to_dict()
        payload["diagnosis"]["findings"] = []
        payload["diagnosis"]["hypotheses"] = []
        payload["diagnosis"]["unknowns"] = []
        schema = json.loads(SCHEMA.read_text())

        self.assertFalse(Draft202012Validator(schema).is_valid(payload))


if __name__ == "__main__":
    unittest.main()
