# Rendering SEO Semantics

Use when the question involves JavaScript rendering, CSR/SSR/SSG, hydration, content visible in the browser but absent from source HTML, JS-injected metadata/links, or lazy-loaded content.

## Keep evidence surfaces separate

```text
Raw HTTP / response HTML
!=
Rendered DOM after JavaScript
!=
Google's stored/indexed version
```

Use `PageInspection` only for the first surface. Use Host browser/rendered DOM evidence for the second. `IndexInspection` is optional first-party evidence for Google's stored state and must not be treated as a live DOM snapshot.

## Compare material SEO facts

When both raw and rendered evidence exist, compare only facts relevant to the user's claim:

- title/meta description;
- canonical;
- robots/noindex;
- H1/main content;
- crawlable links;
- hreflang/alternate links when international SEO is in scope;
- structured data when rich-result behavior is in scope;
- image/video URLs when media discovery is in scope.

Do not flag a difference merely because the DOM changed. The question is whether critical searchable content or control signals depend on rendering in a way that creates discovery/indexing risk.

## JavaScript links

Rendered links should ultimately be normal crawlable web links. Event-only navigation without a resolvable `<a href>` is weaker crawl/discovery evidence.

## Lazy loading / infinite scroll

If content appears only after user scrolling/clicking, combine with `site-architecture-seo-semantics.md`. Verify whether the content has stable URLs/crawlable pagination and whether relevant content exists in rendered HTML without requiring an interaction Google may not trigger.

## Missing rendered evidence

If only raw HTML is available, say exactly what is known:

> 服务器返回的 HTML 中没有发现正文；当前没有渲染后 DOM 证据，因此无法确认 JavaScript 执行后正文是否对搜索引擎可见。

Do not infer rendered success/failure from framework names alone.

## Recommended actions

Actions should target the observed gap, for example:

- ensure critical metadata/content is present in server output or reliably rendered;
- expose real crawlable URLs/links;
- avoid blocking resources required for essential rendering;
- provide crawlable pagination for interaction-driven lists;
- verify rendered output after the change.

Do not recommend SSR as a universal cure when current rendered evidence is already correct.

## Official facts source
