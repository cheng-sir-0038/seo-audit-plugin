from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from codex_seo_mcp.diagnosis.contracts import (
    ActionCategory,
    DiagnosisResult,
    FindingStatus,
    HypothesisStatus,
    RankingPremiseStatus,
)
from codex_seo_mcp.diagnosis.handoff import HANDOFF_BLOCKS
from codex_seo_mcp.diagnosis.content_lifecycle import assess_content_lifecycle
from codex_seo_mcp.diagnosis.hreflang import assess_hreflang_cluster
from codex_seo_mcp.diagnosis.keyword_opportunity import evaluate_keyword_opportunity
from codex_seo_mcp.diagnosis.page_ownership import assess_page_ownership
from codex_seo_mcp.diagnosis.ranking import build_ranking_comparison
from codex_seo_mcp.diagnosis.search_appearance import assess_search_appearance
from codex_seo_mcp.diagnosis.site_migration import assess_site_migration
from codex_seo_mcp.diagnosis.structured_data import assess_structured_data
from codex_seo_mcp.diagnosis.template_regression import assess_template_regression
from codex_seo_mcp.diagnosis.url_lifecycle import assess_url_lifecycle
from codex_seo_mcp.models.content_lifecycle import ContentLifecycleSignals
from codex_seo_mcp.models.keyword_opportunity import KeywordOpportunitySignals
from codex_seo_mcp.models.page_inspection import (
    PageHreflangAlternate,
    PageInspection,
    PageRedirectHop,
    PageStructuredDataBlock,
)
from codex_seo_mcp.models.page_ownership import (
    ContentOverlap,
    PageOwnershipObservation,
    PageOwnershipPairEvidence,
    PageRoleRelation,
)
from codex_seo_mcp.models.search_performance import SearchPerformance, SearchPerformanceRow
from codex_seo_mcp.models.search_appearance import SearchAppearanceSignals
from codex_seo_mcp.models.template_regression import TemplateSeoSnapshot

ROOT = Path(__file__).resolve().parents[1]
CASES = Path(__file__).with_name("cases.json")


def main() -> None:
    """运行不依赖真实账号的确定性诊断基准。"""

    cases = json.loads(CASES.read_text())
    failures: list[str] = []
    for case in cases:
        try:
            _run_case(case)
            print(f"PASS {case['id']}")
        except AssertionError as exc:
            failures.append(f"{case['id']}: {exc}")
            print(f"FAIL {case['id']}: {exc}")

    if failures:
        raise SystemExit("\n".join(failures))
    print(f"evals={len(cases)} passed")


def _run_case(case: dict[str, Any]) -> None:
    kind = case["kind"]
    if kind == "ranking-comparison":
        _ranking_case(case)
        return
    if kind == "enum-contract":
        _enum_case(case)
        return
    if kind == "skill-guardrails":
        _skill_case(case)
        return
    if kind == "keyword-opportunity":
        _keyword_opportunity_case(case)
        return
    if kind == "page-ownership":
        _page_ownership_case(case)
        return
    if kind == "url-lifecycle":
        _url_lifecycle_case(case)
        return
    if kind == "content-lifecycle":
        _content_lifecycle_case(case)
        return
    if kind == "search-appearance":
        _search_appearance_case(case)
        return
    if kind == "hreflang":
        _hreflang_case(case)
        return
    if kind == "structured-data":
        _structured_data_case(case)
        return
    if kind == "site-migration":
        _site_migration_case(case)
        return
    if kind == "template-regression":
        _template_regression_case(case)
        return
    if kind == "plugin-boundary":
        _plugin_boundary_case(case)
        return
    if kind == "handoff-contract":
        _handoff_contract_case(case)
        return
    raise AssertionError(f"unknown kind: {kind}")


def _ranking_case(case: dict[str, Any]) -> None:
    prior = _performance(case["prior"])
    current = _performance(case["current"])
    result = build_ranking_comparison(
        prior,
        current,
        query=case["query"],
        target_page=case.get("target_page"),
    )
    payload = result.to_dict()
    ranking_schema = json.loads(
        (ROOT / "schemas" / "ranking-comparison.v1.schema.json").read_text()
    )
    assert tuple(payload) == tuple(ranking_schema["required"])
    assert ranking_schema["$id"] == "urn:codex-seo:ranking-comparison:v1"
    expected = case["expected"]

    if "prior_page_count" in expected:
        assert len(result.prior_ranking_pages) == expected["prior_page_count"]
    if "current_page_count" in expected:
        assert len(result.current_ranking_pages) == expected["current_page_count"]
    if "target_prior_state" in expected:
        assert result.target_page_prior_state.value == expected["target_prior_state"]
    if "target_current_state" in expected:
        assert result.target_page_current_state.value == expected["target_current_state"]
    if "change_page_count" in expected:
        assert len(result.pages) == expected["change_page_count"]
    if expected.get("prior_is_none"):
        assert result.prior is None
    if expected.get("current_is_present"):
        assert result.current is not None
    if text := expected.get("warning_contains"):
        assert any(text in warning for warning in result.warnings)


def _enum_case(case: dict[str, Any]) -> None:
    expected = case["expected"]
    assert [item.value for item in FindingStatus] == expected["finding_status"]
    assert [item.value for item in HypothesisStatus] == expected["hypothesis_status"]
    assert [item.value for item in RankingPremiseStatus] == expected["premise_status"]
    assert [item.value for item in ActionCategory] == expected["action_category"]


def _skill_case(case: dict[str, Any]) -> None:
    expected = case["expected"]
    technical_skill, technical_refs, technical = _skill_bundle("technical-seo-audit")
    ranking_skill, ranking_refs, ranking = _skill_bundle("ranking-drop-diagnosis")
    keyword_skill, keyword_refs, keyword = _skill_bundle("keyword-opportunity-research")
    analytics_skill, analytics_refs, analytics = _skill_bundle("organic-traffic-analysis")

    shared_reference_files = sorted(
        path.name for path in (ROOT / "references").glob("*.md") if path.is_file()
    )
    assert shared_reference_files == expected["shared_references"]

    for skill_name, skill_text, direct_refs in (
        ("technical-seo-audit", technical_skill, technical_refs),
        ("ranking-drop-diagnosis", ranking_skill, ranking_refs),
        ("keyword-opportunity-research", keyword_skill, keyword_refs),
        ("organic-traffic-analysis", analytics_skill, analytics_refs),
    ):
        assert len(skill_text.splitlines()) <= expected["max_skill_lines"], (
            f"{skill_name} SKILL.md should stay concise"
        )
        assert len(direct_refs) >= expected["min_direct_references"], (
            f"{skill_name} should use progressive disclosure"
        )
        assert _frontmatter_keys(skill_text) == ["name", "description"], (
            f"{skill_name} frontmatter should only contain name + description"
        )

    for value in expected["technical_statuses"]:
        assert f"`{value}`" in technical, f"technical skill bundle missing {value}"
    for value in expected["ranking_hypotheses"]:
        assert f"`{value}`" in ranking, f"ranking skill bundle missing {value}"
    for value in expected["ranking_premises"]:
        assert f"`{value}`" in ranking, f"ranking skill bundle missing {value}"
    for value in expected["required_ranking_capabilities"]:
        assert f"`{value}`" in ranking, f"ranking skill bundle missing capability {value}"
    for phrase in expected["technical_guardrails"]:
        assert phrase in technical, f"technical skill bundle missing guardrail: {phrase}"
    for phrase in expected["visibility_guardrails"]:
        assert phrase in ranking, f"ranking skill bundle missing visibility guardrail: {phrase}"
    for phrase in expected["snapshot_guardrails"]:
        assert phrase in ranking_skill, f"ranking skill missing snapshot guardrail: {phrase}"
    for phrase in expected["execution_guardrails"]:
        assert phrase in ranking_skill.lower(), f"ranking skill missing execution guardrail: {phrase}"
        assert phrase in technical_skill.lower(), f"technical skill missing execution guardrail: {phrase}"
    for phrase in expected["page_quality_guardrails"]:
        assert phrase in technical_skill.lower(), f"technical skill missing PageQuality guardrail: {phrase}"
    for phrase in expected["presentation_guardrails"]:
        assert phrase in technical, f"technical skill bundle missing presentation guardrail: {phrase}"
        assert phrase in ranking, f"ranking skill bundle missing presentation guardrail: {phrase}"
    for phrase in expected["keyword_opportunity_guardrails"]:
        assert phrase in keyword, f"keyword opportunity skill bundle missing guardrail: {phrase}"
    for phrase in expected["web_analytics_guardrails"]:
        assert phrase in analytics, f"organic traffic skill bundle missing guardrail: {phrase}"
    for value in expected["required_keyword_capabilities"]:
        assert f"`{value}`" in keyword, f"keyword opportunity skill bundle missing capability {value}"
    for reference in expected["technical_scenario_references"]:
        assert reference in technical, f"technical scenario router missing reference {reference}"
    for reference in expected["ranking_scenario_references"]:
        assert reference in ranking_skill, f"ranking skill missing conditional reference {reference}"
    for phrase in expected["scenario_routing_guardrails"]:
        assert phrase in technical, f"technical scenario routing missing guardrail: {phrase}"
    for phrase in expected["decision_interaction_guardrails"]:
        for skill_name, bundle in (
            ("technical-seo-audit", technical),
            ("ranking-drop-diagnosis", ranking),
            ("keyword-opportunity-research", keyword),
            ("organic-traffic-analysis", analytics),
        ):
            assert phrase in bundle, f"{skill_name} bundle missing decision/interaction guardrail: {phrase}"

    assert "They never populate `SearchPerformance` first-party fields" in ranking
    assert "company-specific assignee" in ranking
    assert "company-specific assignee" in technical


def _keyword_opportunity_case(case: dict[str, Any]) -> None:
    for item in case["cases"]:
        assessment = evaluate_keyword_opportunity(
            scenario=item["scenario"],
            keyword=item["keyword"],
            market=item["market"],
            target_domain=item.get("target_domain"),
            target_page=item.get("target_page"),
            competitor_domains=item.get("competitor_domains"),
            signals=KeywordOpportunitySignals(**item["signals"]),
        )
        expected = item["expected"]
        assert assessment.status == expected["status"]
        assert assessment.value_level == expected.get("value_level")
        assert assessment.feasibility_level == expected.get("feasibility_level")
        assert assessment.opportunity_level == expected.get("opportunity_level")
        assert assessment.recommended_timing == expected.get("recommended_timing")
        assert assessment.recommended_action == expected.get("recommended_action")
        if expected.get("unknown_contains"):
            assert expected["unknown_contains"] in assessment.unknowns


def _page_ownership_case(case: dict[str, Any]) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "page-ownership-assessment.v1.schema.json").read_text()
    )
    for item in case["cases"]:
        observations = [PageOwnershipObservation(**value) for value in item["observations"]]
        pairs = [
            PageOwnershipPairEvidence(
                page_a=value["page_a"],
                page_b=value["page_b"],
                role_relation=PageRoleRelation(value.get("role_relation", "unknown")),
                content_overlap=ContentOverlap(value.get("content_overlap", "unknown")),
            )
            for value in item.get("pair_evidence", [])
        ]
        assessment = assess_page_ownership(
            query=item["query"],
            market=item["market"],
            target_page=item.get("target_page"),
            observations=observations,
            pair_evidence=pairs,
            visibility_impact=item.get("visibility_impact", "unknown"),
        )
        payload = assessment.to_dict()
        assert tuple(payload) == tuple(schema["required"])
        expected = item["expected"]
        assert assessment.ownership_state.value == expected["ownership_state"]
        assert assessment.target_page_state.value == expected.get("target_page_state", "unknown")
        assert assessment.switching_observed == expected.get("switching_observed", False)
        assert assessment.recommended_action == expected["recommended_action"]
        if expected.get("unknown_contains"):
            assert expected["unknown_contains"] in assessment.unknowns


def _url_lifecycle_case(case: dict[str, Any]) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "url-lifecycle-assessment.v1.schema.json").read_text()
    )
    for item in case["cases"]:
        redirects = [PageRedirectHop(**value) for value in item.get("redirects", [])]
        page = PageInspection(
            requested_url=item["requested_url"],
            final_url=item["final_url"],
            status_code=item["status_code"],
            content_type="text/html",
            content_length_bytes=100,
            redirects=redirects,
            title="Title",
            title_count=1,
            meta_description="Description",
            meta_description_count=1,
            canonical=item.get("canonical"),
            canonical_count=1 if item.get("canonical") else 0,
            robots_meta_tags=[],
            googlebot_meta_tags=[],
            declared_noindex=False,
            h1=["Title"],
            lang="en",
            charset="utf-8",
            meta_refresh_url=item.get("meta_refresh_url"),
            x_robots_tags=[],
            hreflang_alternates=[],
            anchor_links=[],
            rel_next_urls=[],
            rel_prev_urls=[],
            structured_data=[],
        )
        assessment = assess_url_lifecycle(
            page,
            intent=item.get("intent", "observe"),
            expected_target=item.get("expected_target"),
            check_soft404=item.get("check_soft404", False),
            error_page_signal=item.get("error_page_signal", "unknown"),
        )
        payload = assessment.to_dict()
        assert tuple(payload) == tuple(schema["required"])
        expected = item["expected"]
        assert assessment.state.value == expected["state"]
        assert assessment.redirect_state.value == expected["redirect_state"]
        assert assessment.target_state.value == expected.get("target_state", "unknown")
        if expected.get("issue_contains"):
            assert expected["issue_contains"] in assessment.issue_codes
        if expected.get("unknown_contains"):
            assert expected["unknown_contains"] in assessment.unknowns


def _content_lifecycle_case(case: dict[str, Any]) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "content-lifecycle-assessment.v1.schema.json").read_text()
    )
    for item in case["cases"]:
        assessment = assess_content_lifecycle(
            page_url=item["page_url"],
            market=item["market"],
            signals=ContentLifecycleSignals(**item["signals"]),
        )
        payload = assessment.to_dict()
        assert tuple(payload) == tuple(schema["required"])
        expected = item["expected"]
        assert assessment.action.value == expected["action"]
        assert assessment.state == expected["state"]
        if expected.get("merge_target"):
            assert assessment.merge_target == expected["merge_target"]


def _search_appearance_case(case: dict[str, Any]) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "search-appearance-assessment.v1.schema.json").read_text()
    )
    for item in case["cases"]:
        assessment = assess_search_appearance(
            query=item["query"],
            market=item["market"],
            signals=SearchAppearanceSignals(**item["signals"]),
        )
        payload = assessment.to_dict()
        assert tuple(payload) == tuple(schema["required"])
        expected = item["expected"]
        assert assessment.state.value == expected["state"]
        assert assessment.recommended_action == expected["recommended_action"]
        if expected.get("ctr_trend"):
            assert assessment.ctr_trend.value == expected["ctr_trend"]
        if expected.get("position_trend"):
            assert assessment.position_trend.value == expected["position_trend"]


def _hreflang_case(case: dict[str, Any]) -> None:
    schema = json.loads(
        (ROOT / "schemas" / "hreflang-assessment.v1.schema.json").read_text()
    )
    for item in case["cases"]:
        pages = [_eval_page(value) for value in item["pages"]]
        assessment = assess_hreflang_cluster(pages)
        payload = assessment.to_dict()
        assert tuple(payload) == tuple(schema["required"])
        expected = item["expected"]
        assert assessment.state.value == expected["state"]
        if expected.get("issue_contains"):
            assert expected["issue_contains"] in [issue.code for issue in assessment.issues]
        if expected.get("unknown_target"):
            assert expected["unknown_target"] in assessment.unknown_targets


def _eval_page(payload: dict[str, Any]) -> PageInspection:
    url = payload["url"]
    alternates = [
        PageHreflangAlternate(
            hreflang=item["hreflang"],
            url=item["url"],
            source=item.get("source", "html"),
        )
        for item in payload.get("hreflang_alternates", [])
    ]
    return PageInspection(
        requested_url=url,
        final_url=url,
        status_code=payload.get("status_code", 200),
        content_type="text/html",
        content_length_bytes=100,
        redirects=[],
        title="Title",
        title_count=1,
        meta_description="Description",
        meta_description_count=1,
        canonical=payload.get("canonical", url),
        canonical_count=1,
        robots_meta_tags=["noindex"] if payload.get("noindex") else [],
        googlebot_meta_tags=[],
        declared_noindex=bool(payload.get("noindex")),
        h1=["Title"],
        lang=payload.get("lang", "en"),
        charset="utf-8",
        meta_refresh_url=None,
        x_robots_tags=[],
        hreflang_alternates=alternates,
        anchor_links=[],
        rel_next_urls=[],
        rel_prev_urls=[],
        structured_data=[],
    )



def _structured_data_case(case: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas" / "structured-data-assessment.v1.schema.json").read_text())
    for item in case["cases"]:
        blocks = [
            PageStructuredDataBlock(
                format="json_ld",
                valid=value.get("valid", True),
                types=list(value.get("types", [])),
                parse_error=value.get("parse_error"),
            )
            for value in item.get("blocks", [])
        ]
        page = _eval_page({
            "url": item["url"],
            "status_code": item.get("status_code", 200),
            "canonical": item.get("canonical", item["url"]),
            "noindex": item.get("noindex", False),
        })
        page.structured_data = blocks
        assessment = assess_structured_data(
            page,
            expected_types=item.get("expected_types"),
            check_rich_result_eligibility=item.get("check_rich_result_eligibility", False),
        )
        payload = assessment.to_dict()
        assert tuple(payload) == tuple(schema["required"])
        expected = item["expected"]
        assert assessment.state.value == expected["state"]
        if expected.get("issue_contains"):
            assert expected["issue_contains"] in [issue.code for issue in assessment.issues]
        if expected.get("unknown_contains"):
            assert expected["unknown_contains"] in assessment.unknowns


def _site_migration_case(case: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas" / "site-migration-assessment.v1.schema.json").read_text())
    lifecycle_results = []
    for value in case.get("mappings", []):
        old_url = value["old_url"]
        expected_target = value["new_url"]
        final_url = value.get("final_url", expected_target)
        redirect_status = value.get("redirect_status", 301)
        page = _eval_page({"url": old_url, "canonical": value.get("canonical", final_url)})
        page.final_url = final_url
        page.redirects = [PageRedirectHop(old_url, redirect_status, final_url, final_url)]
        lifecycle_results.append(
            assess_url_lifecycle(page, intent="permanent_move", expected_target=expected_target)
        )
    assessment = assess_site_migration(
        lifecycle_results,
        expected_mapping_count=case.get("expected_mapping_count"),
        new_sitemap_urls=set(case["new_sitemap_urls"]) if "new_sitemap_urls" in case else None,
        internal_links_state=case.get("internal_links_state"),
        multilingual=case.get("multilingual", False),
        hreflang_state=case.get("hreflang_state"),
    )
    payload = assessment.to_dict()
    assert tuple(payload) == tuple(schema["required"])
    expected = case["expected"]
    assert assessment.state.value == expected["state"]
    assert assessment.coverage == expected.get("coverage", assessment.coverage)
    if expected.get("issue_contains"):
        assert expected["issue_contains"] in assessment.issue_codes
    if expected.get("unknown_contains"):
        assert expected["unknown_contains"] in assessment.unknowns


def _template_regression_case(case: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas" / "template-regression-assessment.v1.schema.json").read_text())
    pairs = [
        (TemplateSeoSnapshot(**item["before"]), TemplateSeoSnapshot(**item["after"]))
        for item in case.get("pairs", [])
    ]
    assessment = assess_template_regression(pairs)
    payload = assessment.to_dict()
    assert tuple(payload) == tuple(schema["required"])
    expected = case["expected"]
    assert assessment.state.value == expected["state"]
    if expected.get("issue_contains"):
        assert expected["issue_contains"] in [issue.code for issue in assessment.issues]


def _skill_bundle(skill_name: str) -> tuple[str, list[Path], str]:
    skill_path = ROOT / "skills" / skill_name / "SKILL.md"
    skill_text = skill_path.read_text()
    relative_refs = re.findall(r"`(\.\./\.\./references/[^`]+\.md)`", skill_text)
    direct_refs: list[Path] = []
    texts = [skill_text]

    for relative_ref in relative_refs:
        ref_path = (skill_path.parent / relative_ref).resolve()
        assert ref_path.is_relative_to(ROOT / "references"), (
            f"{skill_name} reference escapes shared references: {relative_ref}"
        )
        assert ref_path.is_file(), f"{skill_name} missing reference: {relative_ref}"
        direct_refs.append(ref_path)
        texts.append(ref_path.read_text())

    return skill_text, direct_refs, "\n".join(texts)


def _frontmatter_keys(skill_text: str) -> list[str]:
    lines = skill_text.splitlines()
    assert lines and lines[0] == "---", "SKILL.md missing YAML frontmatter"
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise AssertionError("SKILL.md frontmatter is not closed") from exc

    return [
        line.split(":", 1)[0]
        for line in lines[1:end]
        if line and not line.startswith((" ", "\t")) and ":" in line
    ]


def _plugin_boundary_case(case: dict[str, Any]) -> None:
    """锁住 ADR-0009：portable Plugin 到 Diagnosis Handoff 截止。"""

    expected = case["expected"]
    skill_root = ROOT / "skills"
    skills = sorted(
        child.name
        for child in skill_root.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    )
    assert skills == expected["skills"]
    assert not (skill_root / expected["forbidden_skill"]).exists()

    codex_manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    interface = codex_manifest["interface"]
    assert interface["capabilities"] == expected["codex_capabilities"]
    assert all("fix" not in prompt.lower() for prompt in interface["defaultPrompt"])

    technical = (skill_root / "technical-seo-audit" / "SKILL.md").read_text()
    ranking = (skill_root / "ranking-drop-diagnosis" / "SKILL.md").read_text()
    phrase = expected["required_handoff_phrase"]
    assert phrase in technical
    assert phrase in ranking
    assert "Do not generate or apply a patch" in technical
    assert "Do not generate or apply a patch" in ranking


def _handoff_contract_case(case: dict[str, Any]) -> None:
    """锁住 ADR-0010：8 块 Schema 是真源，Prompt/旧历史不是 Handoff 组成部分。"""

    expected = case["expected"]
    assert callable(DiagnosisResult.to_dict), "DiagnosisResult must expose a stable wire serializer"
    schema = json.loads(
        (ROOT / "schemas" / "diagnosis-handoff.v1.schema.json").read_text()
    )
    diagnosis_payload = DiagnosisResult(
        diagnosis_type="contract-check",
        summary="wire format check",
        unknowns=["fixture"],
    ).to_dict()
    assert tuple(diagnosis_payload) == tuple(schema["$defs"]["diagnosis"]["required"])
    assert list(HANDOFF_BLOCKS) == expected["blocks"]
    assert schema["required"] == expected["blocks"]
    assert schema["additionalProperties"] is False
    for key in expected["forbidden_top_level"]:
        assert key not in schema["properties"]
    if expected["progress_required"]:
        assert "progress" in schema["required"]
        assert schema["properties"]["progress"]["properties"]["completed"]["minItems"] == 1
    if expected["continuation_required"]:
        assert "continuation" in schema["required"]
        assert schema["properties"]["continuation"]["properties"]["verification"]["minItems"] == 1


def _performance(payload: dict[str, Any]) -> SearchPerformance:
    rows = [SearchPerformanceRow(**row) for row in payload.get("rows", [])]
    return SearchPerformance(
        property_url="sc-domain:example.com",
        start_date=payload["start_date"],
        end_date=payload["end_date"],
        dimensions=["query", "page"],
        rows=rows,
    )


if __name__ == "__main__":
    main()
