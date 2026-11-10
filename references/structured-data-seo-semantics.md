# Structured Data SEO Semantics

Use when the user asks about Schema.org/JSON-LD/Microdata/RDFa, rich-result eligibility, Product/Article/Breadcrumb/Organization markup, or a rich result that is missing/broken.

## Rich Results implementation boundary

`check_rich_results` is a diagnosis Tool over existing `PageInspection` structured-data facts. It is **not** a new Provider Capability and must not scrape or automate Google's Rich Results Test webpage.

Current V1 property-level checks stay intentionally small:

- `BreadcrumbList`: `itemListElement`, each `ListItem.position` / `name`, and `item` except for the final breadcrumb;
- `Product` product-snippet gate: `name` plus at least one of `review` / `aggregateRating` / `offers`;
- `Article` / `NewsArticle` / `BlogPosting`: Google currently defines recommended properties but no required properties, so report recommendations/evidence gaps rather than inventing a required-property failure;
- other Schema.org types remain `not_checked` until a real product case justifies another Google rule profile.

Keep the three states separate: JSON-LD parse validity, current Google required-property presence/readiness, and whether Google actually displays a rich result. V1 property-level checks are presence-oriented and keep value/type/content consistency as explicit unknowns; passing them never guarantees display.

## Reporting a completed check

The envelope `status=complete` means execution finished. Derive the SEO conclusion from `data.state`, `checks`, `issues`, `reasons`, and `unknowns`:

- `no_supported_markup` with no JSON-LD observed: “检查已完成；响应 HTML 未发现 JSON-LD。” Absence alone is not a site defect; assess page-type fit before recommending markup.
- `no_supported_markup` with observed types: name the types and their `not_checked` reasons. This is a rule/evidence coverage gap, not absence of structured data or a validation pass.
- `issues_found`: report the concrete parse, property, or page-state issues.
- `required_property_presence_passed` inside a type check: only that property's presence check passed; preserve the remaining value/content unknowns and overall evidence state.

State that rendered-only JSON-LD and Microdata/RDFa were not inspected. This local rule check needs no separate API key and does not run Google's official test; official validation is outside its coverage, not a failed configuration or an unfinished baseline step. In the recheck report, label this item “结构化数据与富媒体资格初检”.

## Separate three questions

1. **Does structured data exist and parse?**
2. **Does it accurately describe visible page content and use a currently supported search feature/type?**
3. **Does Google actually show a rich result?**

These are not the same. Correct markup can make a page eligible without guaranteeing a rich result.

## Required facts

Preserve where possible:

- markup format and schema types;
- required/recommended properties for the relevant Google feature;
- values that materially identify the entity/content;
- URL/canonical/status/indexability;
- consistency with visible content;
- conflicting/duplicate schema blocks;
- SERP appearance only when the user asks whether the feature is actually shown.

Current PageInspection now exposes JSON-LD blocks with parse status and discovered `@type` values. Microdata/RDFa are not yet extracted. The generic `StructuredDataAssessment` checks parse/type/page-state conflicts but intentionally does not hard-code every Google rich-result feature requirement.

## Current first-version boundary

- JSON-LD: inspected from delivered response HTML; malformed blocks remain explicit invalid facts. JSON-LD injected only after JavaScript execution requires rendered-DOM evidence and is not proven by raw PageInspection.
- Microdata/RDFa: currently an evidence gap.
- Rich-result eligibility: only claim generic readiness unless the current type-specific Google requirements and visible-content consistency have also been checked.
- Correct markup never guarantees that Google will display a rich result.

## Page-type fit

Do not recommend every supported schema type on every page. First identify the actual page role, for example:

- article/editorial;
- product/software/service;
- breadcrumb/navigation;
- organization/business identity;
- video/media;
- other currently supported feature.

A schema type that does not match the page's real visible content is not an SEO improvement.

## Consistency

Flag when evidence shows:

- required values missing;
- markup describes content not visible/available to users;
- canonical/entity URLs conflict materially;
- duplicate blocks disagree on important fields;
- page is not indexable/accessible enough for the intended search feature;
- markup uses a feature Google no longer supports in Search.

Do not promise CTR/ranking gains from adding markup.

## Missing rich result

If markup is valid but the user asks “why no rich result”, combine with `search-appearance-seo-semantics.md`. Keep the conclusion as eligibility/presentation evidence, not a guarantee that Google must display the feature.

## Recommended actions

Use actions such as:

- add/fix the page-type-appropriate markup;
- align markup with visible content;
- fix required properties;
- remove conflicting/obsolete markup;
- verify indexability/canonical before rich-result debugging;
- re-check current Google support documentation after template changes.

## Official facts source
