---
name: organic-traffic-analysis
description: Analyze first-party GA4 organic-search traffic, conversion/key-event changes, landing-page value, country/device behavior, and what visitors consume after entering the site. Use when the user asks why organic conversion changed, which organic landing pages are most valuable, which countries are engaging, or what visitors from a market are viewing.
---

# Organic Traffic Analysis

Use GA4 as first-party post-click behavior evidence without turning it into ranking truth or paid-media attribution.

This Skill is read-only. It analyzes Organic Search behavior and may recommend an SEO/content investigation; it does not change Analytics settings, edit pages, buy ads, or publish content.

## References

Read only what the task needs:

- `../../references/web-analytics-semantics.md` — GA4 scope, views, comparison logic, geography, landing-page value, and paid-budget boundary. Read for every task.
- `../../references/capability-boundaries.md` — keep WebAnalytics, SearchPerformance, OrganicVisibility, and page/runtime facts separate.
- `../../references/search-performance-semantics.md` — read only when the user asks whether search-side clicks/impressions/CTR/ranking explain a GA4 change.
- `../../references/evidence-semantics.md` — missing-data and confidence discipline.
- `../../references/diagnosis-output.md` — user-facing terminology and evidence presentation.

## Workflow

### 1. Resolve the analytics scope

If the target website is missing from the conversation, ask for its domain or URL once and wait for the answer before querying data. A Host acknowledgement that an asynchronous question was accepted only means the question was queued, not that the user answered. Keep an outstanding required question open using the Host's interruptible waiting mechanism; a final answer must wait until the user replies or explicitly skips/cancels. Do not close the pending question by sending a second request for the same URL as the final answer, or treat elapsed waiting time as a user decision. On reply, reuse the supplied target and continue; on explicit skip/cancel, stop the dependent analysis and state the missing target.

Establish the analytics target and explicit current date window. Pass the user's domain (or an explicitly supplied GA4 Property ID) as `target` to the analytics Tool. Do not manually choose or invent `property_id` / `site_domain`: they are hidden MCP dependencies resolved immediately before the report. A unique accessible Web Data Stream/defaultUri match auto-continues; multiple equally valid Properties produce native `input-required` elicitation, and zero matches remain an access gap. The property-list Tool is for an explicit “show my Properties”/troubleshooting job, not a mandatory pre-step for analysis. For “this month vs last month” or another change question, resolve a real comparison window rather than inventing one.

The current public analytics tool is scoped to `Organic Search`. If the user says only “访客 / visitors” in this SEO workflow, explicitly disclose that the result covers Organic Search visitors rather than all visitors. If they mean whole-site or paid-traffic conversion, state that this capability is insufficient instead of answering from organic traffic alone.

### 2. Use the smallest GA4 view

- conversion/key-event change → start with `overview`, then inspect `landing_pages`, `devices`, or `countries` only when they can explain the change;
- landing pages worth SEO/content investment → `landing_pages`; when the question explicitly asks which pages to improve for both ranking and conversion, also use page-level `SearchPerformance`;
- where organic visitors come from → `countries`;
- what visitors from selected countries are viewing → `country_pages` with ISO2 country codes;
- day-level change → `daily`.

Do not request every breakdown by default.

### 3. Keep evidence grains separate

Landing-page reports use session-level metrics. Page-consumption reports use page-view/user metrics. Do not compare or aggregate them as if they were the same grain.

Keep GA4 separate from GSC: GA4 describes what happened after arrival; SearchPerformance describes Google Search clicks/impressions/CTR/average position. Use SearchPerformance only when the user asks for search-side causes or when it materially tests a conversion/traffic hypothesis.

### 4. Diagnose, do not overclaim causality

For conversion decline, separate traffic-volume change from key-event-rate change, then test landing-page, country and device mix. A correlated change is a hypothesis until multiple evidence surfaces support it.

For landing-page investment, combine traffic/engagement/key-event value with SEO demand/visibility only when needed. For a ranking and conversion prioritization question, keep GSC page opportunity and GA4 landing-page value as separate explainable axes; reconstruct GA4 URLs from `hostName + landingPage` before joining them to GSC Page URLs and do not invent an opaque combined score. If “加预算” means paid advertising spend, explicitly require paid-media cost/ROAS data; GA4 Organic Search alone cannot justify an ad-budget change.

### 5. Present the answer in business language

Use headings such as 自然流量、转化/关键事件、落地页、国家/设备、证据缺口. Keep GA4 as provenance, not as the result heading. Preserve the current/previous date windows and avoid exposing Tool/Adapter/Client names.
