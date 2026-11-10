# Keyword Opportunity Semantics

Use this reference only for keyword research, keyword opportunity, page keyword targeting, or competitor-gap decisions.

## Scenario first

Resolve one scenario before collecting data:

| Scenario | Required user input | Default behavior |
| --- | --- | --- |
| `metric_lookup` | keyword + market | show market facts only; no site-level opportunity rating |
| `site_research` | target domain + market | inspect site visibility before expanding candidates |
| `page_research` | target domain + target page + market | page fit and intent fit are mandatory |
| `opportunity_discovery` | target domain + market | prefer existing momentum and business fit before broad expansion |
| `competitor_gap` | target domain + competitor domain(s) + market | Gap is a candidate source, not the final decision |

Do not start site/page/Gap opportunity analysis when a required input is missing. In an independent plugin, required market, competitor domain(s), and target page must come from explicit user context or a prior confirmed result; do not guess them from company-specific assumptions.

## Owned-site first-party context

For an owned site with accessible GSC, use `SearchPerformance` query/impression/click/average-position facts as the first site-context surface before broad keyword expansion. `KeywordResearch` supplies external demand/KD/Provider Intent and expansion candidates; `OrganicVisibility` remains third-party ranking/market context. Do not overwrite the first-party site signal with a third-party position.

## Market is not a Provider parameter

Resolve a provider-neutral market before research: country, language and—when ranking/SERP semantics depend on it—search engine. `CN` means a country/market, not automatically Google or Baidu. Product Skills may infer the missing search engine from strong user context and disclose that inference; otherwise ask before the conclusion would materially differ.

Never guess Provider wire values such as DataForSEO `location_code`, private language code, Semrush regional database or GSC country filter. Those belong to the Provider Market Resolver and must be validated from official registry/coverage or a deterministic standard mapping.

Within one opportunity assessment, keep the search-engine axis consistent. Google keyword metrics and Baidu SERP observations may be shown as separate evidence sections, but must not be silently merged into one opportunity/feasibility score.

## Intent is not high/medium/low

Keep Provider intent types as facts:

- `INFORMATIONAL`
- `NAVIGATIONAL`
- `COMMERCIAL`
- `TRANSACTIONAL`

Derive contextual `intent_fit = strong | medium | weak | unknown` instead. Informational can be highly valuable for a guide; Transactional can be a poor fit for an informational article. User-facing tables must not relabel contextual observations such as “案例型 / 指南型 / 预算比较 / 服务页 fit” as Provider Intent; show them in a separate SERP/page-fit column.

## Value and feasibility stay separate

Normalize contextual signals before judging the opportunity:

```text
Value
= business fit + relative demand + intent fit + commercial context

Feasibility
= general KD + existing ranking signal + current SERP fit
```

`unknown` is not an implicit `medium`. If demand context is unknown, Value is not sufficiently established. If KD is unknown and there is no existing ranking/visibility signal that establishes feasibility, Feasibility remains unknown and the deterministic assessment must stay `insufficient_evidence`; do not emit `now/现在做` by substituting a medium default.

Use `business_fit = strong | medium | weak | unknown`.
Use `demand_level = high | medium | low | unknown` relative to the current candidate cohort when possible; do not apply one global minimum Volume threshold across every industry.
Use `existing_signal = strong | medium | weak | none | unknown` from current domain/page visibility.
Use `serp_fit = strong | medium | weak | unknown` after checking important shortlisted SERPs.
For page research also use `page_fit = strong | medium | weak | unknown`.

## KD semantics

General Semrush KD is feasibility evidence, not value.

| KD | General feasibility starting point |
| ---: | --- |
| 0–14 | very easy / high feasibility |
| 15–29 | easy / high feasibility |
| 30–49 | possible / medium feasibility |
| 50–69 | difficult / normally low unless the site already has strong signals |
| 70–84 | hard / normally later |
| 85–100 | very hard / normally later |

Example:

```text
KD 9 + Volume 10 + weak business fit
→ feasibility high, value low, opportunity low, ignore
```

Do not say “KD is too low to matter.”

## Low volume does not always mean low value

A low-volume B2B term may remain valuable when business fit and commercial/transactional intent fit are strong. Treat Volume as demand, not revenue.

When a candidate set is available, compare demand within that set instead of using one universal cutoff. If relative demand cannot be established, keep it unknown rather than inventing a threshold.

## Opportunity matrix

Use the deterministic diagnosis-layer matrix:

| Value | Feasibility | Opportunity | Timing |
| --- | --- | --- | --- |
| high | high | high | now |
| high | medium | medium | now |
| high | low | medium | later |
| medium | high | medium | test |
| medium | medium | medium | test |
| medium | low | low | later |
| low | any | low | ignore |

“Too difficult” and “not valuable” are different outcomes. Preserve `later` separately from `ignore`.

## Existing page vs new content

Prefer existing-page work when there is a suitable current ranking URL/page and the intent/page fit is compatible:

- strong existing signal → `optimize_existing_page`
- suitable existing page but weaker signal → `expand_existing_page`

If the existing target page is a poor fit, do not keyword-stuff it. Use current SERP and intent to choose:

- informational → `create_new_article`
- commercial / transactional → `create_new_landing_page`

When value or evidence is insufficient use `monitor`, `later`, or `ignore` rather than generating content.

## Gap semantics

A competitor Gap proves only that a competitor has visibility for the candidate. Re-evaluate the keyword for the target site's business fit, feasibility, demand, intent fit, and current SERP before recommending it.

## Candidate generation and cost

Semrush keyword lists default to 20 entries unless the user explicitly requests another amount. Do not expand expensive related/question/Gap requests just to make the report longer.

Shortlist first, then use `SerpResearch` only where the current SERP materially affects intent/page/action decisions.

## No automatic article JSON

Keyword discovery defaults to a decision table, not content generation. Show:

```text
keyword
search demand
KD
Provider Intent
contextual SERP/page fit
value
feasibility
opportunity
recommended action
reason
```

Only create a content brief or article JSON after the user explicitly selects a keyword/opportunity or explicitly asks for content generation.

## User-facing wording

Use business language:

- `高机会 / 中机会 / 低机会`
- `现在做 / 小规模测试 / 后续做 / 不建议做`
- `优化现有页面 / 扩充现有页面 / 新建文章 / 新建落地页`

Do not expose `KeywordOpportunityEvaluator`, internal scenario enums, weight vectors, Provider Adapter names, or internal normalized signal names unless the user asks for debugging details.
