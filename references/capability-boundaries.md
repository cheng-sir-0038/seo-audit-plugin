# SEO Capability Boundaries

Use this reference to choose the correct V1 data capability and avoid turning provider-specific fields into false product truth.

## Market boundary

For provider-backed search data, Product Skills operate on `country + language + search_engine` semantics. Provider-specific market fields (`location_code`, private language code, Semrush regional database, GSC alpha-3 filter) are resolver output and must not be guessed by the Skill. `CN` is a market, not a search engine; Google and Baidu evidence must preserve separate axes unless the user explicitly asks for a cross-engine comparison.

## SearchPerformance

Use `SearchPerformance` for the site's own first-party clicks, impressions, CTR, Search Console average position, date trends, and GSC Query × Page analysis.

In V1, GSC is the first-party implementation. If it is unavailable, keep those first-party metrics unknown; do not fill this Contract with third-party visibility data.

`SearchPerformance` is an internal capability name. In normal user-facing output, call this **Google 自然搜索表现**; mention **Google Search Console** only as the data source/provenance when useful.

## OrganicVisibility

Use `OrganicVisibility` for third-party observations of any public domain/URL: ranked keywords, provider-observed positions, ranking URLs/pages, estimated organic traffic, and historical visibility. The current Adapter is DataForSEO Labs; future Ahrefs/Semrush Adapters must map into the same Contract.

`OrganicVisibility` is an internal capability name. In the final user-facing answer, describe it as third-party organic-search visibility/ranking evidence and name the Provider separately when useful. Do not expose gateway/adapter/client/Tool identifiers as part of the SEO result.

Keep these boundaries explicit:

- `estimated_traffic` is a third-party estimate, never GSC clicks;
- provider keyword coverage is not impressions;
- current/previous ranking comparisons should stay on the same Provider and market axis;
- provider freshness/coverage is part of the evidence;
- DataForSEO Sandbox data is dummy test data and cannot support a real Finding;
- missing provider rows are No Data, not proof of no Google ranking.

Use `OrganicVisibility` as the default ranking/visibility evidence when no first-party SearchPerformance exists. If both are available, report them as separate evidence surfaces rather than overwriting one with the other.

## WebAnalytics

Use `WebAnalytics` for first-party GA4 evidence about what Organic Search visitors do after entering the site: sessions, engagement, key events, landing pages, country/device behavior, page consumption, and revenue when configured.

Keep it separate from SearchPerformance and OrganicVisibility. GA4 does not establish keyword rankings, Search Console impressions/CTR/position, or Google index state. The current public analytics Tool is intentionally scoped to `sessionDefaultChannelGroup = Organic Search`; it must not be presented as whole-site or paid-media performance.

In normal user-facing output, call this **自然流量与转化** or **自然搜索访客行为**. When provenance matters, identify **Google Analytics 4 (GA4)** separately.

## PageInspection

Use `PageInspection` for delivered HTTP and response-HTML facts such as status, final URL, each server-side redirect hop (`from/status/location/to`), headers, title, canonical, robots directives, language, H1, and critical content present in the returned HTML.

`PageInspection` intentionally accepts HTML/XHTML only. It is not a generic `robots.txt`/XML resource reader and it does not execute JavaScript. Repository intent is not a substitute for the final delivered response when runtime evidence is available, but raw response HTML is also not proof of the post-JavaScript DOM.

For robots.txt / sitemap resources, use `ResourceInspection`. For CSR-rendered DOM claims, use a browser-rendered Host surface when available. Raw response HTML remains distinct from post-JavaScript DOM.

Current PageInspection now preserves page-level hreflang alternates from HTML/HTTP Link headers, crawlable anchor URLs, explicit `rel=next/prev` URLs, and JSON-LD blocks with parse status/types plus property-presence paths for each top-level JSON-LD entity. Those feed diagnosis-layer `HreflangAssessment`, `StructuredDataAssessment`, and the derived `check_rich_results` Tool. Rich Results is not another Capability. PageInspection still does not expose Microdata/RDFa, anchor-context/link-graph coverage, or media inventory. Soft-404 body/error evidence is intentionally not modeled as a generic Page body contract yet; use Host/rendered/user evidence until a concrete reusable input is proven necessary.

## SiteSafety

Use `SiteSafety` when the user asks whether a public URL is currently matched by a malicious-URL safety Provider. The current personal/non-commercial Provider uses Google Safe Browsing v4 Lookup (`threatMatches.find`) because it provides a stable JSON response for this lightweight read-only check; commercial distribution must switch the Provider to Google Cloud Web Risk while preserving the same Contract.

`no_known_threats` means the Provider returned no current known threat match. It is not proof that the site is absolutely safe. `potential_risk` means a threat-list match was observed and should be presented as potential/suspected risk with the returned threat types, not as 100% certainty.

In normal user-facing output, call this **网站安全检查** or **网站安全风险**. Provider provenance can be shown when useful, but do not expose API/client implementation names.

## SiteGraph / SiteCrawl gap

V1 currently has no site-wide graph capability. Therefore full-site claims about orphan pages, crawl depth, inlink/outlink counts, broken internal-link distribution, faceted URL inventory, or bulk migration mapping cannot be established from isolated PageInspection calls.

`SiteGraph / SiteCrawl` is the preferred future capability candidate for this new site-level fact dimension. Until it exists, report sample-level findings and the missing graph evidence rather than fabricating whole-site counts.

## IndexInspection

Use `IndexInspection` for Google Search Console's first-party view of the **version in Google's index**:

- verdict / coverage state;
- robots.txt state;
- indexing state;
- page fetch state;
- last crawl time;
- Google-selected canonical vs user canonical;
- crawl user agent;
- known sitemap/referring URL associations.

`IndexInspection` is not a live URL test. Do not use it as proof of what the server returns right now; pair it with `PageInspection` when comparing current page declarations with Google's indexed state.

## ResourceInspection

Use `ResourceInspection` only for runtime SEO resources:

- `robots.txt` groups, `Allow` / `Disallow`, and `Sitemap` declarations;
- sitemap `urlset` entries;
- sitemap-index entries.

It is not a generic HTTP/XML downloader and does not replace repository inspection. V1 does not recurse through an entire sitemap graph automatically; the Skill decides which referenced resource needs another inspection.

## Rendered DOM boundary

V1 does **not** expose `RenderedPageInspection` as another MCP capability. Executing JavaScript requires a browser/runtime owned by the Host. When CSR behavior is material, use a Host browser-rendered DOM surface and compare it with `PageInspection` response HTML. If the Host cannot render the page, preserve the claim as missing evidence.

## PageQuality

Use `PageQuality` only when page experience or performance is materially relevant to the task.

`PageQuality` is an internal capability name. In normal user-facing output, call this **页面性能与体验**. When provenance matters, identify **Google PageSpeed Insights / Lighthouse** as the lab source and **CrUX** as the real-user source.

Acquire PageSpeed/Lighthouse facts through the registered `PageQuality` capability, which consumes the `runPagespeed` JSON API. Do not navigate a Host browser to `pagespeed.web.dev` to obtain performance metrics or audits; browser evidence belongs to rendered DOM / interaction / visual-behavior questions.

Each `PageQuality` result represents one explicit `mobile` or `desktop` strategy. If the user did not scope the task to one device, collect both strategies separately and compare them; do not let an implicit device default stand in for the full performance job.

Keep its evidence sources distinct:

- Lighthouse/PageSpeed `lab` is a controlled measurement and may vary between runs.
- CrUX `field` is aggregated real-user data.
- Missing `field` data is not evidence of good or bad real-user performance.
- `field.scope=origin` is origin-level context, not proof of the inspected URL's own field performance.
- A Lighthouse score is not a Google ranking score and cannot by itself explain a ranking change.

## SerpResearch

Use `SerpResearch` to test current SERP hypotheses such as:

- search-intent shift;
- result-type changes;
- competitor page-type changes;
- the site's current ranking URL in the observed SERP;
- SERP title/snippet presentation.

SERP presentation does not prove the page's source metadata. Inspect the page for HTML claims.

## KeywordResearch

Use `KeywordResearch` for external market research such as demand, keyword difficulty, intent, CPC, PPC competition, related keywords, and questions.

Do not use it to establish the site's own first-party ranking truth.

## CompetitorResearch

Use `CompetitorResearch` for competitor domains, organic pages, competitor keyword coverage, and explicit keyword-gap comparisons.

Keep competitor research separate from first-party site performance.

## Semrush boundary

Semrush remains third-party data. `KeywordResearch` / `CompetitorResearch` keep their current roles; if Semrush position/ranking fields later participate in ranking diagnosis, they must enter through an `OrganicVisibility` Adapter and remain third-party observations. They never populate `SearchPerformance` first-party fields.

## Missing capability behavior

When a capability required for a material claim is unavailable:

1. preserve the evidence gap;
2. do not silently substitute a weaker provider;
3. continue with other independent findings when useful;
4. name the capability needed next.
