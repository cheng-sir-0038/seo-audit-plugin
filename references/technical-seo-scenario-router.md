# Technical SEO Scenario Router

Use this reference to choose **which specialized runtime reference to read from the user's actual input/evidence**. Do not preload every technical SEO reference.

## Route by explicit input

| User input/evidence | Read this primary reference |
| --- | --- |
| hreflang, multilingual, locale, region, x-default, language variants | `international-seo-semantics.md` |
| canonical, redirect, 301/302, 404/410, soft404, URL change, migration | `url-lifecycle-seo-semantics.md` |
| CSR/SSR, JavaScript, rendered DOM, source HTML differs, hydration, lazy-loaded content | `rendering-seo-semantics.md` |
| internal links, orphan, crawl depth, pagination, facet/filter/sort, query params, infinite scroll, crawl budget | `site-architecture-seo-semantics.md` |
| schema, JSON-LD, structured data, rich result markup | `structured-data-seo-semantics.md` |
| Google rewrote title/snippet, favicon, site name, breadcrumb, SERP appearance/CTR presentation | `search-appearance-seo-semantics.md` |
| image SEO, video SEO, thumbnail, watch page | `media-seo-semantics.md` |
| template regression, release regression, deploy 后 SEO 异常, 发布后 canonical/noindex/hreflang/schema 变化 | `template-regression-semantics.md` |

## Composition

Default: one primary reference. Add at most two supporting references only when the user's input or observed evidence creates a real cross-scenario dependency.

Examples:

- migration + multilingual → URL Lifecycle + International;
- infinite scroll + JS-only content → Site Architecture + Rendering;
- structured data valid but rich result missing → Structured Data + Search Appearance;
- canonical issue alone → URL Lifecycle only.

Do not load PageQuality unless performance is materially in scope. Do not load Media for ordinary pages. Do not discuss crawl budget unless the site scale/crawl evidence makes it relevant.

## Full technical audit

For an explicit full audit, first use `technical-seo-checks.md` for the common evidence surface and P0 crawl/indexability/canonical/resource checks. Then detect actual site traits (multilingual, JS-heavy, faceted, structured-data-heavy, media-heavy) and load specialized references only for traits that are present or requested.

## Capability gaps

A specialized reference does not mean the current MCP already has every required input. Hreflang alternates, crawlable anchor URLs, explicit `rel=next/prev`, and JSON-LD blocks are now available through PageInspection. Microdata/RDFa, site-wide link graph, media inventory, strong soft-404 body signals, and rendered DOM are still incomplete/missing surfaces. Report those gaps instead of reading plugin source or inventing a result.
