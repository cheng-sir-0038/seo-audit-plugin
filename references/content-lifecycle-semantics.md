# Content Lifecycle SEO Semantics

Use when the user asks whether a declining/old page should be refreshed, expanded, merged, consolidated, kept, removed, or redirected.

The current deterministic `ContentLifecycleAssessment` is a diagnosis-layer contract, not a new Provider Capability. It consumes normalized evidence from visibility, demand/intent research, page inspection, and optional Page Ownership results; it does not fetch data itself.

## Do not use freshness theater

Do not recommend changing dates, rewriting intros, adding arbitrary word count, or deleting old content merely to make the site look fresh. Content actions must respond to a real user/search need or page-role problem.

## Required evidence

Prefer:

- page/domain + market;
- visibility/ranking trend and comparison basis;
- query/topic demand and current intent;
- current SERP competitors/page types;
- current page content/structure;
- current Ranking URL/Page ownership;
- optional first-party clicks/impressions when available.

A traffic decline alone does not tell you whether to refresh or remove the page.

## Decision states

### Refresh

Use when the page still owns the right intent/topic but important facts, examples, product information, coverage, or user needs are outdated.

### Expand

Use when the page is still directionally correct and has ranking momentum, but current SERP/user needs require materially better depth, evidence, subtopics, comparison, or task completion.

### Merge / consolidate

Use when multiple pages overlap heavily in role/topic and page-ownership evidence supports consolidation into a stronger user destination.

### Keep

Use when the page is useful, stable/strategically necessary, and there is no supported problem to solve. “No recent growth” is not itself a reason to rewrite.

### Remove / redirect

Use only when the page no longer has a useful distinct purpose, is obsolete/duplicate/unsupported, or has a clearly better replacement. Redirect to the closest relevant replacement, not automatically to home/category.

### Monitor / later

Use when the value remains but current evidence is too weak or the topic is strategically valid yet not worth immediate work.

## Deterministic decision guardrails

The evaluator follows these priority rules:

- `probable_cannibalization` + no distinct page purpose + known merge target -> `merge`;
- low content value + no distinct purpose + known replacement -> `redirect`;
- low content value + no distinct purpose + no replacement -> `remove`;
- visibility decline + demand not declining + strong/medium intent fit + outdated facts -> `refresh`;
- visibility decline + demand not declining + suitable/current page + meaningful coverage gap -> `expand`;
- visibility decline + demand decline -> `monitor`, because rewriting cannot manufacture lost market demand;
- stable/growing visibility + current content + suitable intent -> `keep`;
- materially incomplete evidence -> `monitor`, never a destructive action.

`remove` does not mean redirect-to-home. If a replacement exists, prefer the closest relevant replacement; if there is no replacement and the page is intentionally gone, URL lifecycle rules determine the correct 404/410 behavior.

## Demand decline vs page decline

Separate:

- topic/search demand shrank;
- page lost share while demand remained;
- SERP intent/page type changed;
- competing internal page took ownership;
- technical/indexing issue affected the page;
- content became outdated/incomplete.

Different causes imply different actions.

## Cannibalization interaction

When multiple Ranking Pages are observed, read `ranking-page-ownership-semantics.md` before recommending merge/delete. Do not merge pages merely because both rank for the same query.

## User-facing output

Give one primary recommendation plus evidence, for example:

> 建议“扩充现有页面”，不是新建文章：这个 URL 仍是主要排名页，主题需求没有明显消失，但当前 SERP 已经普遍覆盖 X/Y 两块用户需求，而现页缺失。

or:

> 建议暂缓删除。当前只看到可见性下降，还不能证明这个主题没有价值；需要先区分需求下降、页面份额下降和页面职责冲突。

## Official facts source
