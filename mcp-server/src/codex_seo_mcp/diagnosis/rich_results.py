from __future__ import annotations

import re

from codex_seo_mcp.diagnosis.structured_data import assess_structured_data
from codex_seo_mcp.models.common import Confidence
from codex_seo_mcp.models.page_inspection import PageInspection
from codex_seo_mcp.models.structured_data import (
    RichResultAssessment,
    RichResultRuleStatus,
    RichResultState,
    RichResultTypeCheck,
)

RICH_RESULT_RULES_VERSION = "google-search-2026-09-09"


def assess_rich_results(
    page: PageInspection,
    *,
    expected_types: list[str] | None = None,
) -> RichResultAssessment:
    """Apply the small maintained Google Rich Result rule profile to PageInspection facts.

    Rich Results stays a derived diagnosis, not a Provider Capability. This evaluator only checks
    rule profiles that can be kept deterministic and regression-tested; value validity, visible
    content consistency, rendered-only markup, and Google's final display decision remain explicit
    evidence gaps.
    """

    base = assess_structured_data(page, expected_types=expected_types)
    checks: list[RichResultTypeCheck] = []
    unknowns: list[str] = [*base.unknowns, "rendered_only_markup", "microdata_rdfa"]
    reasons = [
        *base.reasons,
        "本检查只读取响应 HTML 中的 JSON-LD；未检查 JavaScript 渲染后标记及 Microdata/RDFa。",
        "这是插件规则检查，无需独立 API 密钥；未调用 Google 官方 Rich Results Test。",
        f"当前 required-property 规则快照：{RICH_RESULT_RULES_VERSION}。",
        "满足当前必需属性只表示通过这一层检查，不保证 Google 实际展示富媒体结果。",
    ]

    for block in page.structured_data:
        if block.format != "json_ld" or not block.valid:
            continue
        if not block.nodes:
            # Backward-compatible/synthetic fixtures may only carry @type facts. Keep them unknown
            # rather than manufacturing property readiness from the type alone.
            checks.extend(
                RichResultTypeCheck(
                    schema_type=schema_type,
                    feature=_feature_for(schema_type),
                    rule_status=RichResultRuleStatus.NOT_CHECKED,
                    notes=["当前结果缺少 property-level facts，无法执行 required-property 检查。"],
                )
                for schema_type in block.types
            )
            continue

        for node in block.nodes:
            for schema_type in node.types:
                check, node_unknowns = _check_type(
                    schema_type=schema_type,
                    property_paths=node.property_paths,
                )
                checks.append(check)
                unknowns.extend(node_unknowns)

    profiled = [item for item in checks if item.rule_status is not RichResultRuleStatus.NOT_CHECKED]
    has_required_issue = any(
        item.rule_status is RichResultRuleStatus.MISSING_REQUIRED_PROPERTIES for item in profiled
    )
    issues = list(base.issues)

    if issues or has_required_issue:
        state = RichResultState.ISSUES_FOUND
        confidence = Confidence.HIGH
    elif not profiled:
        state = RichResultState.NO_SUPPORTED_MARKUP
        confidence = Confidence.MEDIUM if checks else Confidence.HIGH
        reasons.append("当前没有命中 V1 已维护的 Google Rich Result rule profile。")
        if base.observed_types:
            reasons.append(f"已发现 JSON-LD 类型：{', '.join(base.observed_types)}；具体未检查原因见各类型 checks。")
    else:
        unknowns.append("visible_content_consistency")
        state = RichResultState.INSUFFICIENT_EVIDENCE
        confidence = Confidence.LOW

    return RichResultAssessment(
        page_url=page.final_url,
        rules_version=RICH_RESULT_RULES_VERSION,
        state=state,
        checks=checks,
        issues=issues,
        unknowns=_dedupe(unknowns),
        reasons=reasons,
        confidence=confidence,
    )


def _check_type(
    *,
    schema_type: str,
    property_paths: list[str],
) -> tuple[RichResultTypeCheck, list[str]]:
    normalized_type = schema_type.casefold()
    paths = set(property_paths)

    if normalized_type == "breadcrumblist":
        missing = _breadcrumb_missing_properties(paths)
        return (
            RichResultTypeCheck(
                schema_type=schema_type,
                feature="breadcrumb",
                rule_status=(
                    RichResultRuleStatus.MISSING_REQUIRED_PROPERTIES
                    if missing
                    else RichResultRuleStatus.REQUIRED_PROPERTY_PRESENCE_PASSED
                ),
                required_properties=[
                    "itemListElement(minItems=2)",
                    "ListItem.position",
                    "ListItem.name",
                    "ListItem.item(except-final)",
                ],
                missing_required_properties=missing,
                notes=["最后一个 breadcrumb 的 item 可以省略；Google 会使用当前页面 URL。"],
            ),
            [] if missing else ["property_value_validity"],
        )

    if normalized_type == "product":
        missing: list[str] = []
        if "name" not in paths:
            missing.append("name")
        if not {"review", "aggregateRating", "offers"} & paths:
            missing.append("one_of(review,aggregateRating,offers)")
        return (
            RichResultTypeCheck(
                schema_type=schema_type,
                feature="product_snippet",
                rule_status=(
                    RichResultRuleStatus.MISSING_REQUIRED_PROPERTIES
                    if missing
                    else RichResultRuleStatus.REQUIRED_PROPERTY_PRESENCE_PASSED
                ),
                required_properties=["name", "one_of(review,aggregateRating,offers)"],
                missing_required_properties=missing,
                notes=["V1 只检查 Product snippet 顶层 gate；嵌套 Offer/Review/Rating 仍有各自规则。"],
            ),
            [] if missing else ["property_value_validity", "product_nested_requirements"],
        )

    if normalized_type in {"article", "newsarticle", "blogposting"}:
        return (
            RichResultTypeCheck(
                schema_type=schema_type,
                feature="article",
                rule_status=RichResultRuleStatus.NO_REQUIRED_PROPERTIES,
                notes=["Google 当前 Article profile 没有必需属性；author/headline/image/date 等为建议属性。"],
            ),
            ["article_recommended_properties"],
        )

    return (
        RichResultTypeCheck(
            schema_type=schema_type,
            feature=None,
            rule_status=RichResultRuleStatus.NOT_CHECKED,
            notes=["V1 没有为该 Schema.org 类型维护 Google Rich Result rule profile。"],
        ),
        [],
    )


def _breadcrumb_missing_properties(paths: set[str]) -> list[str]:
    missing: list[str] = []
    indexes = sorted(
        {
            int(match.group(1))
            for path in paths
            if (match := re.match(r"^itemListElement\[(\d+)\](?:\.|$)", path))
        }
    )
    if "itemListElement" not in paths or len(indexes) < 2:
        missing.append("itemListElement(minItems=2)")
    if not indexes:
        return missing

    last_index = indexes[-1]
    for index in indexes:
        prefix = f"itemListElement[{index}]"
        if f"{prefix}.position" not in paths:
            missing.append(f"{prefix}.position")
        if f"{prefix}.name" not in paths and f"{prefix}.item.name" not in paths:
            missing.append(f"{prefix}.name")
        if index != last_index and f"{prefix}.item" not in paths:
            missing.append(f"{prefix}.item")
    return missing


def _feature_for(schema_type: str) -> str | None:
    normalized = schema_type.casefold()
    if normalized == "breadcrumblist":
        return "breadcrumb"
    if normalized == "product":
        return "product_snippet"
    if normalized in {"article", "newsarticle", "blogposting"}:
        return "article"
    return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
