from __future__ import annotations

from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.page_inspection import PageInspection
from codex_seo_mcp.models.structured_data import (
    StructuredDataAssessment,
    StructuredDataIssue,
    StructuredDataState,
)

STRUCTURED_DATA_SCHEMA_ID = "urn:codex-seo:structured-data-assessment:v1"


def assess_structured_data(
    page: PageInspection,
    *,
    expected_types: list[str] | None = None,
    check_rich_result_eligibility: bool = False,
) -> StructuredDataAssessment:
    expected = _dedupe([value.strip() for value in (expected_types or []) if value.strip()])
    blocks = [item for item in page.structured_data if item.format == "json_ld"]
    valid = [item for item in blocks if item.valid]
    invalid = [item for item in blocks if not item.valid]
    observed = _dedupe([schema_type for item in valid for schema_type in item.types])
    issues: list[StructuredDataIssue] = []
    unknowns: list[str] = []
    reasons: list[str] = []

    for index, item in enumerate(blocks):
        if not item.valid:
            issues.append(
                StructuredDataIssue(
                    code="invalid_json_ld",
                    summary="页面存在无法解析的 JSON-LD 块。",
                    block_index=index,
                )
            )

    missing_types = [value for value in expected if value.casefold() not in {item.casefold() for item in observed}]
    for schema_type in missing_types:
        issues.append(
            StructuredDataIssue(
                code="expected_schema_type_missing",
                summary=f"页面没有发现预期的 {schema_type} JSON-LD 类型。",
                schema_type=schema_type,
            )
        )

    if page.status_code < 200 or page.status_code >= 300:
        issues.append(StructuredDataIssue(code="page_not_successful", summary=f"页面最终返回 HTTP {page.status_code}。"))
    if page.declared_noindex:
        issues.append(StructuredDataIssue(code="page_noindex", summary="页面声明了 noindex；即使 markup 正确也不应把它当作正常可索引 Rich Result 页面。"))
    if page.canonical and page.canonical.rstrip("/") != page.final_url.rstrip("/"):
        issues.append(StructuredDataIssue(code="canonical_points_elsewhere", summary="页面 canonical 指向其他 URL，需要确认结构化数据对应的页面职责。"))

    if check_rich_result_eligibility:
        unknowns.extend(["type_specific_google_requirements", "visible_content_consistency"])
        reasons.append("当前通用 evaluator 不硬编码所有 Google Rich Result 类型的 required/recommended properties；具体 eligibility 需要加载对应类型的当前 Google 规则并核对页面可见内容。")

    if issues:
        state = StructuredDataState.ISSUES_FOUND
        confidence = Confidence.HIGH if not unknowns else Confidence.MEDIUM
    elif not blocks:
        state = StructuredDataState.NO_MARKUP
        confidence = Confidence.HIGH
        reasons.append("当前 HTML 没有发现 JSON-LD。没有 JSON-LD 本身不一定是 SEO 错误，只有页面业务类型/目标搜索功能确实需要时才建议补。")
    elif unknowns:
        state = StructuredDataState.INSUFFICIENT_EVIDENCE
        confidence = Confidence.LOW
    else:
        state = StructuredDataState.MARKUP_PRESENT
        confidence = Confidence.HIGH
        reasons.append("当前 JSON-LD 可以解析，且没有发现通用的页面状态/canonical/expected-type 冲突。")

    return StructuredDataAssessment(
        page_url=page.final_url,
        state=state,
        json_ld_block_count=len(blocks),
        valid_json_ld_blocks=len(valid),
        invalid_json_ld_blocks=len(invalid),
        observed_types=observed,
        expected_types=expected,
        issues=issues,
        unknowns=_dedupe(unknowns),
        reasons=reasons,
        confidence=confidence,
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        if item not in result:
            result.append(item)
    return result
