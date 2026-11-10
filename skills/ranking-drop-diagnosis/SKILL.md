---
name: ranking-drop-diagnosis
description: Diagnose organic-search ranking/performance changes and ranking-page ownership using evidence-first Query/Page analysis. Use when rankings, clicks, impressions, CTR, or organic visibility rose or fell; when keywords are approaching the top 10; when the ranking URL keeps switching; when multiple pages may be competing for one query; or when an old/declining page needs a refresh, merge, keep, or removal decision.
---

# Ranking Drop Diagnosis

Verify whether a decline actually occurred before explaining it. Do not start from generic algorithm-update speculation or treat missing data as proof of a ranking loss.

This Skill is read-only. It may locate a repository-controlled cause and prepare a Diagnosis Handoff, but downstream code execution belongs to the Host. Do not generate or apply a patch, diff, commit, build, test, deploy, or publish operation.

For a domain/URL-only diagnosis, use the registered SEO MCP capabilities directly. Do not inspect this plugin's own implementation files (`mcp.json`, `.mcp.json`, `server.py`, provider clients/adapters, or tests) and do not run shell commands to verify or manually invoke the plugin wiring. Repository inspection is only for a repository the user explicitly asked to audit or when a supported diagnosis needs code localization in that target repository. If a required MCP capability is absent or unavailable, report the capability gap instead of introspecting the plugin source.

## References

Read only the references needed for the current task:

- `../../references/evidence-semantics.md` — premise, Finding, and Hypothesis states plus missing-evidence behavior. Read before assigning diagnosis states.
- `../../references/organic-visibility-semantics.md` — third-party ranking/visibility evidence, same-provider comparison, freshness, No Data, and ranking URL semantics. Read for every ranking-drop diagnosis.
- `../../references/search-performance-semantics.md` — first-party GSC Query × Page, clicks/impressions/CTR, No Data, and page switching. Read when first-party `SearchPerformance` is available.
- `../../references/capability-boundaries.md` — `OrganicVisibility`, optional `SearchPerformance`/`IndexInspection`, `SerpResearch`, page/runtime, quality, keyword, and competitor boundaries. Read before using provider-backed evidence.
- `../../references/page-quality-semantics.md` — Chinese business meanings and thresholds for LCP/INP/CLS/FCP/TTFB. Read only when page performance materially enters the diagnosis.
- `../../references/ranking-page-ownership-semantics.md` — multiple Ranking Pages, page switching, Target Page mismatch, and cannibalization boundaries. Read only when the actual input/evidence involves page ownership conflicts.
- `../../references/content-lifecycle-semantics.md` — refresh/expand/merge/keep/remove decisions for declining or old content. Read only when the user asks what to do with an aging/declining page.
- `../../references/search-appearance-seo-semantics.md` — source metadata vs Google SERP title/snippet/CTR presentation. Read only when the user's decline claim is specifically about CTR/title/snippet/search appearance.
- `../../references/diagnosis-output.md` — Hypothesis/Finding fields and the structured Diagnosis Handoff contract. Read before producing material hypotheses, findings, or engineering Handoff.

## Workflow

### 1. Define the claim

Establish the site/domain or URL, affected query or page when known, intended Target Page when known, and the target market. Ranking/visibility comparison requires one consistent market; ask only when it cannot be resolved reliably. When a market label such as CN could mean Google users in China or Baidu, resolve the search engine before making provider-backed ranking claims; current `OrganicVisibility` is Google visibility, not Baidu.

If the user says “recently”, use explicit provider observation/comparison dates when available instead of inventing a window the Provider does not support. For an owned-site `SearchPerformance` trend with no requested window, default to the latest complete 28-day window and the immediately preceding 28-day window, and show the exact dates.

### 2. Verify the premise

For an owned domain, call first-party search performance with the user's domain/URL/explicit `sc-domain:` identity as `target`; do not choose or pass the final `property_url` yourself. GSC Property is a hidden MCP dependency: a unique match auto-continues, multiple equally valid Properties produce native `input-required` elicitation before SearchPerformance runs, and zero matches remain an access gap rather than defaulting to another site. Bare domain resolution prefers the exact `sc-domain:` Property; an explicit URL prefers the most specific covering URL-prefix Property. Use Query-level position/impressions/clicks as the primary evidence for ranking-trend questions such as “快进前 10”. Use `OrganicVisibility` as the default for a public domain without accessible first-party performance, and as supplemental market/freshness evidence when both exist.

Report the evidence source, market, freshness/comparison basis, ranking changes, ranking URLs/pages where available, and estimated-traffic semantics for third-party visibility.

For a weekly report or a request such as “最近一周 / 最近 8 周”, request the locally accumulated weekly observations together with the current visibility result. Compare only weeks that were actually observed. Do not fill missing weeks, and do not call a non-consecutive previous observation “上周”. If local history is still short, state how many weekly observations have been accumulated and use provider historical data only with its real monthly/observation granularity.

If first-party `SearchPerformance` is available, evaluate clicks, impressions, CTR, Search Console average position, and GSC Query × Page as a separate stronger evidence surface. Lack of GSC does not block third-party visibility diagnosis; lack of all ranking/visibility evidence leaves the premise unverified.

### 3. Resolve page behavior

Keep Query and Ranking URL/Page relationships distinct. Preserve every Ranking URL/Page observation returned by `OrganicVisibility`, but respect Provider coverage notes and do not assume the set is exhaustive. Use `SerpResearch` when current multiple-page behavior matters; when `SearchPerformance` exists, preserve GSC Query × Page separately rather than merging the two data sources.

Investigate page switching, new competing pages, disappearance, consolidation, and time-bounded Target Page changes without rewriting historical evidence.

When the actual input/evidence involves multiple Ranking Pages, Target Page mismatch, page switching, or cannibalization, apply the Page Ownership semantics and classify the case as stable owner, intent split, page switching, probable cannibalization, or insufficient evidence. Keep Target Page matched/mismatched/unknown as a separate fact. Multiple pages alone never proves cannibalization; require same page role + high content overlap plus switching or supported negative visibility impact before recommending consolidation/differentiation.

### 4. Test causes with the narrowest relevant evidence

Use `SerpResearch` only to test current SERP or intent hypotheses. Use `PageInspection` and repository inspection for current delivered-page or implementation claims. Use `IndexInspection` when Google's indexed/crawl/canonical state materially tests a hypothesis, and `ResourceInspection` when robots.txt or sitemap behavior is implicated. Use `PageQuality` only when page experience is materially relevant.

Use `KeywordResearch` and `CompetitorResearch` only for external demand, intent, and competitor context. They do not verify the site's own ranking premise.

### 5. Build competing hypotheses

Keep meaningful causes separate and change each Hypothesis state only when evidence supports it. Exclude contradicted explanations instead of retaining a generic SEO checklist.

Do not convert “possible” into “confirmed” to produce a decisive answer.

### 6. Finish at diagnosis

Lead with the primary evidence surface appropriate to the target: first-party `SearchPerformance` for an owned domain when accessible, otherwise third-party visibility. Keep the other surface separate when both exist. Then report the market, freshness/comparison basis, ranking URL/Page behavior, Query × Page where material, Target Page mismatch, supported hypotheses, exclusions, unknowns, and missing evidence.

In the user-facing answer, use SEO language rather than internal implementation names: describe `OrganicVisibility` as third-party organic-search visibility/ranking evidence, keep DataForSEO/Ahrefs/Semrush only as provenance, and never expose Tool/Gateway/Adapter/Client/module/file identifiers unless the user explicitly asks for debugging details.

Create an engineering Diagnosis Handoff only for a sufficiently supported repository-controllable issue. The Handoff must stand on its own without old chat history.
