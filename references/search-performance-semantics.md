# Search Performance Semantics

Use this reference for ranking, clicks, impressions, CTR, average-position, and Query × Page diagnosis.

## First-party ranking truth

For the site's own organic search performance, `SearchPerformance` is authoritative when available. In V1 it is backed by Google Search Console.

Third-party research data never populates first-party SearchPerformance fields. If GSC is unavailable, keep first-party clicks/impressions/CTR/position unknown; a separate third-party `OrganicVisibility` premise may still support a clearly labelled provider-observed ranking/visibility conclusion with its own freshness and coverage limits.

## Property identity and default comparison window

GSC Property identity is resolved as a hidden MCP dependency of the GSC-backed Tool, not as a model-visible `property_url`. For a bare domain prefer the exact `sc-domain:<domain>` Property when accessible because it covers protocols and subdomains; for an explicit URL prefer the most specific covering URL-prefix Property. If multiple URL-prefix Properties remain equally valid, the Tool must return native `input-required` elicitation before the Search Console request runs. Zero matches are a property-access gap, not permission to use another accessible Property. Never default to the first row.

When an owned-site trend question omits dates, default to the latest complete 28-day SearchPerformance window and the immediately preceding equal 28-day window. Use final GSC data, disclose the exact dates, and keep the property/country/search-type/query grain identical across both windows.

## Owned-domain ranking momentum / near top 10

For an owned domain, use `SearchPerformance` as the primary ranking-trend evidence when accessible. Third-party `OrganicVisibility` may add market/search-volume/freshness context, but it must not replace first-party Search Console position/impression/click evidence for the site's own trend. Only use third-party ranking as the primary fallback when GSC is not connected, the property is not accessible, or the requested SearchPerformance window has no usable evidence; label that fallback as third-party observation with its real freshness.

For a question such as “哪些关键词快进前 10”：

- compare explicit current and previous windows of equal length;
- use the same GSC property, country filter, search type, and query grain in both windows;
- a **near-top-10 rising candidate** has current average position 11–20 inclusive and a better (numerically lower) average position than the previous window;
- a keyword at 11–20 with no improvement is merely near the top 10, not “快进”;
- a current 11–20 row with no previous observation is a new/insufficient-comparison observation, not proven ranking growth;
- very low impressions weaken confidence: preserve the candidate as an observation and warn about sample strength instead of claiming it is certain to enter the top 10.

If the user specifies a country market, use the supported GSC country filter for the first-party slice. GSC Search Analytics has no language filter, so do not describe the first-party result as language-filtered; language-specific market context can come from a compatible third-party research source and must remain a separate evidence surface.

## Keep dimensions distinct

Treat these as different views:

- **Query**: performance aggregated by query.
- **Page**: performance aggregated by page.
- **Query × Page**: the concrete relationship between a query and each page receiving performance.

Use Query × Page whenever the diagnosis concerns a concrete ranking page, page switching, or multiple pages competing for the same query. Never merge multiple Ranking Pages into one invented rank.

## Target Page vs Ranking Page

- **Target Page** is the page the business intends to rank for a query.
- **Ranking Page** is a page that actually receives search performance for that query.

A mismatch is an investigation signal, not proof of a defect.

When the Target Page changes from A to B, treat the change as time-bounded. Evaluate the new target after the change while preserving historical Ranking Page evidence for A.

## No data

No returned record does not mean position zero, not ranked, deindexed, or zero traffic unless the capability contract explicitly proves that interpretation.

Preserve the difference between:

- no record in the requested window;
- a record with zero-valued metrics;
- unavailable data;
- a page/query that genuinely disappeared from previously observed data.

## Verify the premise before causes

Compare concrete current and prior windows and inspect, as available:

- clicks;
- impressions;
- CTR;
- average position;
- Query × Page contribution;
- date-series direction;
- whether the change is broad or isolated.

Classify the premise before causal analysis. Do not continue into confident cause language when the premise is `decline-not-confirmed` or `insufficient-data`.

## Page behavior

For an affected query or query group:

1. identify the intended Target Page when known;
2. list actual Ranking Pages;
3. compare current and prior contribution by page;
4. test for page switching, a new competing page, disappearance, or consolidation;
5. keep every material page separate in the reasoning.
