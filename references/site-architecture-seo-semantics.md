# Site Architecture SEO Semantics

Use for internal linking, orphan pages, crawl depth, pagination, faceted navigation, query parameters, infinite scroll, and crawl-budget questions.

## Distinguish page-level and site-level facts

Page-level facts can answer:

- which links a page exposes;
- whether next/previous/filter URLs are crawlable;
- canonical/indexability of a specific variant.

Site-level claims such as orphan pages, crawl depth, inlink counts, broken-link distribution, URL explosion, and crawl paths require a site graph/URL inventory. Without that data, do not claim full-site results from a few sampled pages.

## Internal links

Prefer evidence about real crawlable `<a href>` links and useful anchor context. A sitemap can help discovery but does not prove healthy internal-link architecture.

Key questions:

- can important pages be reached from other discoverable pages;
- are important links direct or routed through avoidable redirects;
- are anchors meaningful in context;
- are key pages excessively deep;
- are important URLs only present in sitemap but absent from navigation/content links.

`orphan` means no known internal-link path in the inspected graph, not simply “few links”.

## Pagination

For paginated/list content:

- each content chunk should have a stable URL when it needs independent discovery;
- pages should be linked sequentially with crawlable links;
- pagination should not rely only on click/scroll events;
- filter/sort URLs should not accidentally become the primary indexable pagination path;
- each page's canonical/indexability should reflect its actual content role rather than mechanically canonicalizing every page to page 1.

Do not resurrect old `rel=next/prev` assumptions as a mandatory Google indexing rule; focus on crawlable URLs/links and correct page signals.

## Faceted navigation / query parameters

Assess intent and URL-space behavior before recommending index/noindex/blocking:

- which filters create real search-demand landing pages;
- which variants are transient UX states;
- whether combinations create near-infinite crawl spaces;
- whether internal links expose unnecessary combinations;
- canonical/indexability consistency;
- sitemap should list intended indexable URLs, not every interaction state.

Do not use one global rule such as “all parameter URLs noindex” or “all facets block in robots.txt”. Different parameter classes can have different SEO roles.

## Infinite scroll / load more

Combine with `rendering-seo-semantics.md` when interaction triggers content. Google crawlers generally do not click UI buttons; content that matters for discovery needs crawlable URL/link paths.

## Crawl budget

Only enter crawl-budget diagnosis when scale or evidence justifies it, such as very large/frequently changing URL inventories, parameter explosion, or material discovery/crawl delays.

For ordinary sites, avoid generic “crawl budget” findings. First investigate simpler causes: discovery, robots, status, server capacity, duplicate URL inventory, sitemap quality, or content value.

## Capability boundary

Current PageInspection exposes crawlable `<a href>` URLs plus explicit `rel=next/prev` URLs for the inspected page. It still has no site-wide link graph, so full internal-link/orphan/depth/faceted inventory remains a capability gap.

`SiteGraph / SiteCrawl` is the preferred future data capability because it can serve multiple scenarios without creating separate InternalLink/Pagination/Facet tools.

## User-facing actions

Prefer concrete actions:

- add crawlable links from relevant hub/category pages;
- reduce unnecessary redirecting internal links;
- provide stable paginated URLs;
- stop exposing low-value filter combinations;
- reserve indexable facets for demand-backed landing pages;
- simplify crawl paths to important pages;
- measure with a site graph before claiming orphan/depth counts.

## Official facts source
