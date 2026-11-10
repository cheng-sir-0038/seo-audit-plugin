# Diagnosis Output Contract

Use this reference when a Product Skill has enough evidence to produce material Findings, Hypotheses, or a downstream engineering Handoff.

## Finding

A material Finding uses the portable fields:

- `type`
- `subject`
- `status`
- `confidence`
- `sourceRefs`
- `summary`
- `rationale`
- `actionCategory`

`actionCategory` is one of:

- `technical`
- `page-structure`
- `indexing`
- `content`
- `keyword-strategy`
- `observation`
- `insufficient-evidence`

Do not add a company-specific assignee, workflow ID, approval state, or private Capability ID.

## Hypothesis

A material ranking hypothesis keeps:

- `type`
- `status`
- `rationale`
- `sourceRefs`
- `unknowns`

Keep competing hypotheses separate. Remove or exclude a hypothesis when evidence contradicts it instead of retaining every common SEO explanation.

Useful classes include:

- target/ranking page mismatch;
- page switching or multiple-page competition;
- indexability, canonical, or redirect regression;
- significant rendering or metadata regression;
- SERP or search-intent change;
- demand or impression change;
- CTR change without equivalent position decline;
- data coverage or reporting artifact;
- unknown external cause.

## When engineering Handoff is justified

Create an engineering Diagnosis Handoff only when the diagnosis identifies a repository-controllable problem such as an incorrect canonical, robots rule, redirect, rendering regression, routing defect, or metadata-generation defect.

Do not create an engineering Handoff for demand changes, competitor movement without a concrete implementation defect, editorial strategy, unproven algorithm explanations, or evidence gaps.

## Wire contracts

`DiagnosisResult.to_dict()` is the canonical Host-neutral serializer for diagnosis results. `DiagnosisHandoff` must reuse it rather than maintain a second diagnosis serializer.

`RankingComparison.to_dict()` is the canonical serializer for Query × Page comparison facts. Its versioned machine contract is `schemas/ranking-comparison.v1.schema.json`.

Neither wire format contains Markdown, HTML, table definitions, cards, charts, or view recommendations. The consuming Host decides how to render the structured result.

## User-facing presentation

The structured diagnosis and Handoff are machine truth, not the default chat presentation. In an interactive user conversation, render a concise Host-native answer first: direct conclusion, Findings/limitations, evidence, and next action. Use a table when it improves comparison.

Do not dump the full `DiagnosisResult` or 8-block `DiagnosisHandoff` JSON unless the user explicitly asks for JSON / machine-readable output, a debugging view, or the Host is actually transferring the payload to another system or Agent.

### Public terminology boundary

Normal user-facing prose must describe the **SEO meaning**, not the plugin implementation. Do not surface internal capability, Tool, gateway, adapter, client, module, or file names unless the user explicitly asks for implementation/debug details.

Keep evidence-source names when they help the user judge provenance. For example:

- say **“第三方自然搜索可见性”** instead of `OrganicVisibility`;
- say **“Google 自然搜索表现”** instead of `SearchPerformance`; when provenance matters, add **“数据来源：Google Search Console”** separately;
- say **“自然流量与转化”** or **“自然搜索访客行为”** instead of `WebAnalytics`; when provenance matters, add **“数据来源：Google Analytics 4 (GA4)”** separately;
- say **“网站安全检查”** / **“潜在安全风险”** instead of `SiteSafety`; `no_known_threats` must be rendered as **“当前未匹配已知威胁”**, never “网站绝对安全”;
- for Rich Results, distinguish **结构化数据可解析 / 当前必需属性检查 / Google 实际展示**. Do not collapse them into one “Rich Result passed” label;
- say **“页面性能与体验”** instead of `PageQuality`; when provenance matters, add **“实验室检测：Google PageSpeed Insights / Lighthouse”** and **“真实用户体验：Chrome UX Report (CrUX)”** separately;
- say **“Google 索引状态”** instead of `IndexInspection`; when provenance matters, add **“数据来源：Google Search Console URL Inspection”** separately;
- say **“当前搜索结果 / SERP”** instead of `SerpResearch`;
- say **“页面运行时检查”** instead of `PageInspection`;
- say **“DataForSEO Labs”** when naming the evidence provider is useful;
- do not say `analyze_rankings`, `OrganicVisibilityGateway`, `DataForSEOOrganicVisibilityAdapter`, `DataForSEOClient`, `server.py`, or similar implementation identifiers in normal results.

Do not use provider/product names as the business heading. A normal result should look like:

```text
页面性能与体验
  - 移动端性能 ...
  - LCP / INP / CLS ...
  数据来源：Google PageSpeed Insights / CrUX

Google 自然搜索表现
  - 点击 / 展示 / CTR / 平均排名 ...
  数据来源：Google Search Console
```

Provider names explain provenance; the heading explains what the user is looking at.

Provider provenance is user-relevant; implementation topology is not. A concise source footer may include provider, market, observation/update time, and whether traffic is estimated, without exposing internal service names.

Keep the complete audit result separate from a scoped engineering Handoff. If only one Finding justifies downstream engineering work, the Handoff may contain the diagnosis subset needed for that Finding, but the user-facing audit must not imply that the scoped Handoff represents every Finding, limitation, or unknown from the audit.

## Diagnosis Handoff

The final portable handoff is structured, resumable, and sufficient for a new Agent with no previous conversation history.

Use exactly these eight top-level blocks:

`task -> target -> diagnosis -> evidence -> desiredState -> constraints -> progress -> continuation`

Do not replace the structured payload with a prose prompt. A Host may render prose from the payload after the fact.

`progress` records what the diagnosis already completed, attempted, or decided. `continuation` names the downstream first action and its verification.

Business choices in `progress.decisions` are context, not an execution permit. On receipt, verify that referenced evidence, page purpose, target identity and current permissions still apply before continuing. If a fresh read already meets the desired state, report that evidence instead of applying an obsolete recommendation. If purpose changed, re-evaluate the recommendation; do not replay old approval text.

Schema validity proves structure, not successful Agent resumption. A new process rereading a handoff is not by itself a fresh model session. Keep technical recheck results separate from Google's later indexing, rankings or conversion outcomes.

The schema source of truth is `schemas/diagnosis-handoff.v1.schema.json`.

## Portable boundary

Product Skills are read-only diagnosis workflows. They may locate owning implementation and describe the smallest plausible modification boundary, but they do not generate or apply patches, diffs, commits, builds, tests, deploys, or publishing operations.
