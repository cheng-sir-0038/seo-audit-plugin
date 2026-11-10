# Template / Release Regression Semantics

Use when the user reports SEO breakage after a template, layout, framework, routing, CDN, or release change.

The first deterministic `TemplateRegressionAssessment` compares **before vs after delivered SEO facts** on representative URLs. Current PageInspection can be normalized directly into `TemplateSeoSnapshot`; historical/before snapshots still need to come from an earlier observation, fixture, release capture, or user-provided evidence. It does not infer repository causality merely because a commit/release happened at the same time.

## Compare facts that templates commonly control

- HTTP/final URL;
- noindex/indexability declarations;
- canonical;
- title/title count;
- meta description;
- H1 presence;
- language;
- hreflang set;
- structured-data types when available.

## Regression threshold

Treat these as strong regression candidates when they appear after release:

- successful page becomes non-successful;
- `noindex` is newly introduced;
- canonical changes unexpectedly;
- title/H1 disappears or title structure becomes invalid;
- hreflang is removed/reduced;
- important structured-data types disappear;
- final URL unexpectedly changes.

A content/title wording change is not automatically a regression. Keep it as `changed` unless evidence shows the new value is invalid or conflicts with the intended page role.

## Scope boundary

A few representative URLs can prove a sampled template regression but cannot prove how many pages/site sections are affected. Full blast-radius claims require a URL inventory / SiteGraph or equivalent template-to-URL mapping.

After a regression is confirmed, repository inspection can locate the owning template/component, but the temporal match alone does not prove the exact code line caused the delivered change.
