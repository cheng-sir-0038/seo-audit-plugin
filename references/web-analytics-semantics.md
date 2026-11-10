# Web Analytics Semantics

Use this reference when the user asks what organic-search visitors do after entering the site: conversion/key-event changes, landing-page value, country/device behavior, or which pages visitors consume.

## Evidence boundary

`WebAnalytics` is first-party GA4 behavior/conversion evidence. It can establish:

- Organic Search sessions and active users;
- engaged sessions / engagement rate;
- key events and session/user key-event rate;
- landing pages;
- country/device breakdowns;
- page views / user engagement for page-consumption views;
- revenue when the GA4 property actually records it.

It does **not** establish:

- keyword rankings or ranking URLs;
- Search Console clicks/impressions/CTR/average position;
- Google index state;
- ad spend, CAC, CPC, ROAS, or whether paid-media budget should be increased.

Keep GA4 and Search Console as separate first-party evidence surfaces. Search Console explains how users reached the site from Google Search; GA4 explains what happened after arrival.


## Property identity from a domain

GA4 Property identity is a hidden dependency of the analytics Tool. Pass a domain (or an explicitly supplied accessible Property ID) as `target`; the runtime resolves the final `property_id` before `runReport`. For a domain, use each accessible Property's **Web Data Stream** `defaultUri`; a unique host match auto-continues, multiple equally valid matches return native `input-required` elicitation, and zero matches remain an access gap. Property display names are labels, not ownership evidence, and row order is never a default. Treat `www.example.com` and `example.com` as the same host for this resolution. The resolver also injects the normalized root domain as hidden `site_domain`, so WebAnalytics filters GA4 `hostName` to that domain plus subdomains and does not silently mix other domains from the same Property.

## Organic Search scope

The current public tool intentionally filters `sessionDefaultChannelGroup = Organic Search`. Do not present the result as whole-site conversion unless the user explicitly has an all-traffic analytics capability in another system.

When the user simply says “这个月转化率下降了” inside an SEO workflow, state that the current analysis is **Organic Search traffic**. Likewise, an unqualified “visitors / 访客” question must be disclosed as Organic Search visitors rather than **all visitors**. If they mean the whole site or paid traffic, the current capability is insufficient.

## Views

- `overview`: period totals for sessions, engagement, key events and revenue;
- `landing_pages`: session-level landing-page performance with `hostName + landingPage` so multi-subdomain paths remain distinguishable;
- `countries`: session-level country performance;
- `country_pages`: which pages users from selected countries consumed, preserving `hostName + pagePath`; page-view/user metrics, not landing-page session metrics;
- `devices`: session performance by device category;
- `daily`: day-level organic-search trend.

Do not mix landing-page/session metrics with page-consumption metrics as if they were the same grain.

## Comparison

A comparison must use two explicit date windows. Preserve current and previous periods separately; do not invent causality from a percentage change alone.

For “why did conversion fall”, test plausible evidence in order:

1. did Organic Search sessions change?
2. did session key-event rate change?
3. did the landing-page mix change?
4. did specific high-volume landing pages lose engagement/key-event rate?
5. did country/device mix change?
6. only then combine with Search Console/ranking evidence if the user asks for search-side causes.

A correlated ranking, traffic or conversion change is a hypothesis until the relevant evidence surfaces line up.

## Landing-page investment

For SEO/content investment, prioritize using a combination of demand/visibility plus GA4 landing-page value. For explicit **ranking and conversion** prioritization, use GSC Page impressions/clicks/CTR/average position for search opportunity and GA4 landing-page sessions/engagement/key-event value for post-click value. Reconstruct each GA4 landing URL from `hostName + landingPage` before joining to GSC full Page URLs; keep unmatched or different page roles separate and do not invent a universal blended score. Use the same date window on both first-party surfaces. If the user did not specify a market/country, keep GSC and GA4 unfiltered by country and describe the result as site-wide first-party organic-search evidence rather than inventing a market. A high session count with weak key-event rate is not automatically “most worth investing in”; a lower-traffic page with strong key-event rate can be strategically valuable.

If the user means **advertising budget**, GA4 organic evidence is insufficient without paid-media spend/cost/ROAS data. State that boundary instead of turning organic landing-page performance into an ad-budget recommendation.

## Geography

Use GA4 `countryId` as ISO alpha-2 for filtering (for example `IN`, `TR`) while preserving the human-readable country in the result. Country behavior is first-party site behavior; it is not a search-engine market/ranking measurement.

## No Data

Empty GA4 rows mean no rows were returned for the requested property/date/filter. They do not prove the site had no total traffic, no Google visibility, or no indexed pages. Keep the request scope explicit.
