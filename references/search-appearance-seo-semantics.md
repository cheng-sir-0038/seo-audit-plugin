# Search Appearance SEO Semantics

Use when the user asks why Google shows a different title/snippet, why CTR changed without a clear ranking move, or about favicon/site name/breadcrumb/rich-result presentation.

The current deterministic `SearchAppearanceAssessment` is a diagnosis-layer contract. It combines source metadata, current Query-level SERP presentation, optional Target Page, and optional first-party CTR/position changes; it does not create a new Provider Capability.

## Source vs SERP presentation

Always separate:

```text
Page source/runtime facts
!=
Google SERP presentation
```

`PageInspection` answers what the page declares. `SerpResearch` answers what is currently shown for the searched query/market. Google may generate title links/snippets from multiple signals, so a rewritten title is not automatically evidence that the `<title>` tag is broken.

## Diagnosis inputs

Depending on the question, inspect:

- source title/meta description/canonical/H1;
- current SERP title/snippet/URL/feature;
- query + market;
- optional clicks/impressions/CTR when first-party SearchPerformance exists;
- structured data only when rich-result/breadcrumb presentation is part of the claim.

Do not diagnose CTR from third-party estimated traffic.

## Title/snippet cases

Classify:

- source metadata is incorrect/duplicated/missing;
- source is reasonable but Google rewrites presentation;
- query intent/context causes a different snippet/title emphasis;
- page/URL shown is not the intended ranking page;
- ranking position changed and likely explains CTR movement;
- evidence is insufficient because no query-level SERP/CTR facts exist.

Do not promise that changing `<title>` or meta description will force Google to use that exact text.

## Deterministic decision guardrails

Use these priorities:

- missing/duplicate source Title -> source metadata issue first;
- observed SERP URL differs from intended Target Page -> investigate Page Ownership before copy tweaks;
- CTR decline + ranking decline -> ranking movement is already a major factor; do not blame title/snippet rewrite;
- CTR decline + stable/improving ranking + observed rewrite -> presentation change is a **candidate** explanation, not confirmed causality;
- rewrite without performance harm -> report the rewrite and monitor, do not call it an SEO defect;
- missing Query-level SERP evidence -> insufficient evidence.

CTR thresholds are only deterministic noise guards for the evaluator, not Google rules. A 0.5 percentage-point CTR movement is currently treated as material for this helper; the result must still preserve first-party/third-party evidence boundaries.

## Rich presentation

When breadcrumbs/structured data/rich result are involved, load `structured-data-seo-semantics.md` only if markup eligibility is actually part of the question.

Favicon/site-name issues are search-appearance issues; do not turn them into ranking findings unless there is separate ranking evidence.

## User-facing output

Prefer:

> 页面源码标题是 X，但当前 US 市场对该 Query 的 Google 结果展示为 Y。这里可以确认“展示被改写”，但不能仅凭改写本身判断排名问题。

Then state the most likely actionable cause only when supported.

## Official facts source
