# Technical SEO Checks

Use this reference when a technical audit needs concrete inspection targets, implementation mapping, and prioritization.

## SEO one-click recheck

An explicit SEO one-click recheck is a fixed baseline Job, not an excuse to load every specialist reference. For the supplied domain/homepage, collect current `PageInspection` facts, robots/sitemap `ResourceInspection`, accessible GSC `SearchPerformance` plus homepage `IndexInspection`, `PageQuality` for both mobile and desktop, the derived `check_rich_results` result, and `SiteSafety`. Missing GSC or provider data remains a named gap. This baseline does not prove full-site coverage without a site inventory/crawl, and it does not include GEO.

## Evidence surfaces

Classify what is actually available:

1. repository only;
2. repository + runnable local app;
3. repository + live URL;
4. live URL only;
5. user-provided evidence only.

Do not claim a full runtime result from repository intent alone, and do not claim a repository cause from a live-page symptom when the owning code cannot be inspected.

## Understand the rendering model

Before judging implementation, determine where relevant:

- framework and routing model;
- SSR / SSG / CSR behavior;
- page, template, and layout hierarchy;
- metadata generation;
- sitemap and robots generation;
- canonical, locale, and pagination conventions;
- proxy, CDN, or server behavior that can change HTTP headers.

Prefer repository-native conventions over inventing a parallel SEO layer.

## Establish runtime truth

When runtime evidence is available, inspect the delivered facts that matter to the task:

- status and redirects;
- `X-Robots-Tag`;
- response HTML `<title>`;
- meta description;
- canonical;
- robots meta;
- document language;
- hreflang alternates when international SEO is in scope;
- JSON-LD parse/type facts when structured data is present or requested;
- H1 and critical indexable content;
- sitemap and robots.txt output when a compatible resource surface is available.

`PageInspection` is an HTTP + response-HTML inspector. It intentionally accepts HTML/XHTML only and does not execute JavaScript. Do not treat those boundaries as target-site SEO defects.

For `robots.txt` and sitemap XML, use `ResourceInspection`; do not force those resources through `PageInspection`. Repository/generated-output evidence can still be used to map the runtime result back to implementation.

When the question is whether Google actually indexed/crawled a URL, use `IndexInspection` when GSC authorization/property access is available. Keep it separate from `PageInspection`: Google indexed-state evidence can be stale relative to the current response, while PageInspection says nothing about Google's stored index state.

A claim about CSR content after JavaScript execution requires browser-rendered DOM evidence or an equivalent Host capability. Raw response HTML can prove what the server returned, but it cannot prove what JavaScript later rendered. Without rendered-DOM evidence, report a capability gap / missing evidence and keep the CSR claim unknown.

A SERP title/snippet is not source HTML metadata because search engines may rewrite presentation.

## V1 technical domains

Prioritize checks that can map to engineering work:

- title and meta-description generation;
- canonical generation and normalization;
- robots meta and `X-Robots-Tag`;
- indexability conflicts;
- H1 and basic page semantics;
- page language;
- sitemap generation;
- robots.txt behavior;
- routing, duplicate URL, and obvious canonicalization problems;
- SSR/CSR behavior that hides critical SEO content;
- page-quality issues only when evidence connects them to the current task.

For targeted specialist questions, do not expand this list into a generic checklist. Use `technical-seo-scenario-router.md` and load only the specialist reference selected by the user's actual input/evidence. For a full audit, specialist domains are discovered progressively after the common crawl/indexability/status/canonical/resource checks.

Do not broaden a technical audit into keyword strategy, backlink planning, content calendars, or generic marketing advice unless explicitly requested.

## Map findings to implementation

### Clarify page purpose after new evidence

Keep the observed declaration separate from the user's intended outcome. For a `noindex` page whose purpose is unresolved, explain the observed declaration and ask whether the page should appear in search. Use an intent already supplied in this task instead of asking again. Ordinary business clarification belongs in conversation; trusted Property selection stays in the Host's native input flow.

An intended search page can justify a scoped recommendation to review or remove the conflicting declaration, with page/header/source evidence and a recheck plan. An intentionally excluded page can justify keeping the declaration. Neither conclusion proves Google's current index state or guarantees a later ranking change. `noindex` controls indexing, not who can access confidential material; it is not an access-control mechanism.

If the user defers, refuses, or cancels, preserve the observed facts and identify the dependent work that did not run. Resume only from a new applicable answer, not a guessed first candidate. A Host without the required native input capability must leave that branch unavailable rather than silently replacing the user's selection. A changed purpose invalidates recommendations that depended on the old purpose; unchanged evidence may still be reused.

In an important recommendation, connect the object, evidence, chosen action, material alternatives, constraints, uncertainty and verification. Preserve the read-only scope: recommending a change and receiving a business answer never authorize the change itself.

Google indexing behavior: [noindex documentation](https://developers.google.com/search/docs/crawling-indexing/block-indexing).

### Locate the relevant implementation

For a repository-controlled finding:

1. identify the delivered behavior;
2. locate the code that controls it;
3. classify the scope as global, template-level, route-level, or page-specific;
4. identify the smallest plausible modification boundary;
5. stop before proposing or applying a patch inside the Product Skill.

Do not treat every repository diff as causal. A temporal match is only a hypothesis until the search mechanism and available evidence support it.

## Prioritize findings

Rank findings in this order:

1. indexability or crawl-blocking errors;
2. site-wide or template-wide correctness errors;
3. incorrect canonical or routing behavior;
4. page-level metadata or structural errors;
5. lower-confidence or lower-impact observations.

Do not invent numeric business impact without measurement.

## Stop conditions

Stop expanding when the requested technical domains have been checked to the available evidence level, more work would only create generic advice, a missing capability blocks the next claim, or a finding is sufficiently localized for Diagnosis Handoff.
