# Organic Visibility Semantics

Use this reference for ranking/visibility diagnosis backed by third-party providers such as DataForSEO, Ahrefs, or Semrush.

## Third-party observation, not first-party performance

`OrganicVisibility` can establish provider-observed keyword positions, ranking URLs/pages, new/lost/rise/fall signals, estimated traffic, and historical visibility. It does not establish GSC clicks, impressions, CTR, Query × Page, or Google index state.

Always preserve:

- `provider` from the `CapabilityResult` envelope;
- market and target scope;
- observation/freshness dates;
- coverage notes and warnings;
- whether traffic is estimated.

## Same-provider comparison

A ranking/visibility change should compare compatible observations from the same Provider and market whenever possible. Do not average provider positions or silently compare Provider A current data with Provider B historical data.

For the current DataForSEO Adapter, current/previous keyword position uses DataForSEO `rank_absolute` so both values remain on the same provider axis. DataForSEO Labs data follows the Provider database update cadence and is not a live Google SERP snapshot. DataForSEO Labs scope is not the DataForSEO platform: a market/language combination missing from Labs must not be generalized into “DataForSEO does not support this country”, because other DataForSEO APIs and search-engine products have separate location coverage.

## No Data

Missing provider rows mean that the provider did not return observations for the request. They do not prove that Google has no ranking, no traffic, or no indexed page.

DataForSEO Sandbox returns dummy data. Sandbox output can validate Contract behavior but cannot support a real SEO Finding.

For DataForSEO Ranked Keywords, `historical_serp_mode=live` excludes keywords that disappeared from the latest SERP. In that mode, a returned aggregate `lost=0` must not be presented as “没有丢失关键词”; the domain Contract keeps lost count unknown. When the diagnosis/report explicitly needs lost-keyword evidence, request a mode that includes lost observations (for example `all`).

## Local weekly observations

The plugin may persist a small local aggregate observation after a successful visibility query. This exists to answer report questions such as “最近一周” or “最近 8 周” without pretending that a provider monthly-history endpoint contains weekly rows.

Rules:

- one observation bucket is separated by target, target scope, market, and Provider;
- at most one record is retained for each ISO week; a later query in the same week replaces that week's earlier local record;
- the snapshot stores aggregate counts and estimated traffic only, not the full keyword list or credentials;
- missing weeks stay missing and must never be interpolated or filled with zero;
- a previous local observation is only “上周” when it is the immediately preceding ISO week;
- Provider data update time and local observation time are different facts and should remain distinguishable;
- weekly local observations are local runtime state under `PLUGIN_DATA`, not Provider-native historical truth.

When local weekly history is insufficient, report the available observation count. Provider historical data can still provide longer-term context, but keep its actual granularity (for example monthly history) instead of relabeling it as weekly.

## Visibility premise states

A ranking-drop diagnosis may verify a **third-party visibility premise** without GSC:

- decline observed;
- mixed change;
- decline not observed;
- insufficient third-party data.

If `SearchPerformance` is also available, evaluate the first-party performance premise separately. Do not overwrite either evidence surface with the other.

## Ranking URL/Page

Keep every ranking URL observation the Provider actually returns separate, but do not assume the Provider response is exhaustive. The current DataForSEO Ranked Keywords shape exposes one `ranked_serp_element` per returned keyword item, so it cannot by itself prove that no other page from the same domain also ranks for that query.

A Target Page mismatch or a provider-observed URL change is an investigation signal, not automatically a defect. Use current `SerpResearch` when multiple live ranking pages or the present SERP materially changes the conclusion; preserve GSC Query × Page separately if optional first-party data exists.
