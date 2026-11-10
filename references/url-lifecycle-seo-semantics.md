# URL Lifecycle SEO Semantics

Use for canonicalization, redirects, HTTP status, soft 404, URL changes, consolidation, and site migrations.

## Separate facts

Do not collapse these into one “URL problem”:

- requested URL;
- final URL;
- HTTP status;
- redirect chain;
- canonical target;
- robots/indexability;
- sitemap presence;
- intended old→new mapping when the user supplies one.

A redirect target and a canonical target are different signals and can conflict.

Current `PageInspection` preserves each HTTP redirect hop as `from URL + status code + Location + resolved target`. Do not collapse `301 → 302 → 308` into a URL-only chain because permanent/temporary intent would be lost.

## Deterministic lifecycle intents

`UrlLifecycleAssessment` supports these diagnosis intents:

- `observe` — report current facts without inventing a business intention;
- `keep` — the requested URL is expected to remain directly live;
- `permanent_move` — old URL is permanently moved to a known target;
- `temporary_move` — redirect is intentionally temporary;
- `remove` — URL is intentionally gone and has no replacement.

Permanent migration should normally use server-side permanent redirect statuses such as 301/308. Temporary redirects should not be silently treated as permanent migration. Redirect chains are reported separately from wrong destinations.

## Redirect diagnosis

Check:

- whether a redirect exists when the user expects one;
- whether the final URL is the intended destination;
- unnecessary redirect chains/loops;
- whether internal links still point through redirects;
- whether old URLs consolidate to the closest relevant new URL rather than an unrelated destination;
- whether temporary/permanent behavior matches the actual lifecycle intent.

Do not label every 302 as an SEO defect without understanding why it is temporary.

## 404 / 410 / soft 404

A genuine removed URL can correctly return a not-found status. The SEO problem is not “404 exists”; it is usually one of:

- important URL removed without a suitable replacement;
- internal links/sitemap still promote the removed URL;
- a page that visually says “not found” returns success and is treated like normal content;
- many invalid variants are generated and crawlable.

Current PageInspection does not yet expose strong body/error-page classification. Without enough content evidence, keep soft-404 classification unproven.

The current evaluator accepts an explicit body/error-page signal from a Host/user evidence surface. HTTP 200 alone is never enough to call a soft 404.

## Canonical diagnosis

Canonical is a preference signal, not a guarantee of Google's selected URL. Check whether site signals agree:

- canonical;
- redirects;
- internal links;
- sitemap URLs;
- localized annotations when applicable.

For a single URL, report the current declared canonical fact. For site-wide duplicate patterns, do not claim full coverage without URL inventory/site graph evidence.

## Migration mode

`SiteMigrationAssessment` aggregates URL-level `UrlLifecycleAssessment` results without inventing whole-site coverage. Hreflang validation only enters this assessment when the migration is explicitly multilingual; non-multilingual moves do not need a fake hreflang status to pass. Require at least old/new domains or representative old→new URL mapping. Full migration validation should cover:

1. old→new mapping;
2. redirects;
3. new self-canonical;
4. updated internal links;
5. updated sitemap;
6. updated hreflang when the site is multilingual;
7. critical media/resource URLs where migration changes them;
8. representative traffic/visibility before-after evidence when available.

One successful URL sample does not prove the migration is globally correct. `sample_passed` is intentionally different from `passed`; full pass requires explicit mapping coverage, updated internal-link evidence, new-sitemap coverage, and hreflang evidence when the migration is multilingual.

## Recommended actions

Use business actions such as:

- keep current URL;
- redirect to specific replacement;
- fix redirect chain;
- align canonical/internal links/sitemap;
- remove invalid URL from discovery surfaces;
- validate migration mapping;
- monitor post-migration visibility.

Do not recommend bulk redirect-to-home as a generic cleanup.

## Official facts source
