---
name: keyword-opportunity-research
description: Research and prioritize SEO keyword opportunities for a target domain, target page, or competitor gap. Use when the user asks for keyword research, keywords worth targeting, easy-but-valuable keywords, keyword opportunities, page keyword targeting, competitor keyword gaps, or whether a keyword is worth doing.
---

# Keyword Opportunity Research

Turn keyword-market facts into a scenario-specific SEO decision without pretending that low KD means low value or that competitor rankings automatically create an opportunity.

This Skill is read-only. It may recommend an SEO/content action, but it does not modify pages, create CMS content, publish, or generate article JSON unless the user explicitly asks for content generation after selecting an opportunity.

## References

Read only the references needed for the current task:

- `../../references/keyword-opportunity-semantics.md` — scenario routing, required inputs, Value/Feasibility, KD/Intent semantics, opportunity matrix, and recommended actions. Read for every keyword-opportunity task.
- `../../references/capability-boundaries.md` — `KeywordResearch`, `CompetitorResearch`, `OrganicVisibility`, `SerpResearch`, and page/runtime boundaries. Read before provider-backed research.
- `../../references/organic-visibility-semantics.md` — third-party target-domain/page ranking evidence and ranking URL coverage. Read for site/page opportunity work when first-party performance is unavailable or needs market context.
- `../../references/search-performance-semantics.md` — first-party owned-site query/impression/click/position signals. Read for an owned site with accessible GSC.
- `../../references/evidence-semantics.md` — missing data and confidence rules. Read before turning evidence into a recommendation.
- `../../references/diagnosis-output.md` — user-facing business terminology and structured output boundary. Read when producing material recommendations.

## Workflow

### 1. Resolve the scenario before calling data tools

Use exactly one scenario:

- single keyword metrics → `metric_lookup`;
- website keyword research → `site_research`;
- target-page keyword research → `page_research`;
- find new keyword opportunities → `opportunity_discovery`;
- competitor keyword / Gap research → `competitor_gap`.

Enforce required inputs from the reference. If a required input is missing, ask for it before any provider-backed research. Do not start site-level research without target domain + market, page research without target page, or Gap research without competitor domain(s); an independent plugin must not invent market, target page, or competitor domains from hidden business context.

Resolve market semantics before provider calls. Infer country/language/search engine from the user's wording when confidence is sufficient, but do not guess Provider location codes or regional databases. A label such as `CN` is not itself a search engine: if the task could materially differ between Baidu and Google, resolve that axis first. Keep one search-engine axis inside one opportunity assessment; do not silently combine Google keyword metrics with Baidu SERP evidence into one score.

### 2. Collect the narrowest evidence

For `metric_lookup`, use `KeywordResearch` only and return facts. Do not invent a site-level opportunity rating without a target domain.

For an owned site with accessible GSC, inspect query-level `SearchPerformance` before broad keyword expansion so real impressions/clicks/average position establish existing demand and momentum. Keep `OrganicVisibility` as a separate third-party market/ranking surface; when first-party performance is unavailable, it remains the fallback site-visibility context. For page work also inspect the target page and its exact visibility. For Gap work use `CompetitorResearch` as the candidate source, then reassess candidates for the target site.

Use Semrush related/questions/Gap lists conservatively; default keyword-list size is 20 unless the user explicitly asks for another count.

### 3. Normalize context, then judge the opportunity

Keep Provider Intent as Informational/Navigational/Commercial/Transactional. Judge contextual Intent Fit separately.

Separate Value from Feasibility. KD only affects Feasibility. Demand should be relative to the candidate cohort when possible; do not apply one global Volume cutoff across industries.

Unknown is not medium. If demand/value inputs or ranking feasibility cannot be supported by Volume/KD, existing ranking signals, or equivalent evidence, keep the assessment insufficient instead of emitting `现在做` from default assumptions.

Use current site/page visibility as existing-signal evidence. Check current SERP only for shortlisted terms where page type, intent, or recommended action would materially change.

### 4. Choose the SEO action

Prefer optimizing or expanding an existing suitable ranking page. If the current target page is a poor intent/page fit, recommend a new article or landing page instead of stuffing the keyword into the old page.

Keep `later` separate from `ignore`: high-value keywords can be strategically useful even when current feasibility is low.

### 5. Present a decision table

Default columns: keyword, monthly demand, KD + difficulty wording, Provider Intent, contextual SERP/page fit, value, feasibility, opportunity, recommended action, short reason. Provider Intent and contextual SERP/page fit must be separate columns.

Use Chinese business language such as 高机会/中机会/低机会 and 现在做/小规模测试/后续做/不建议做. Do not expose internal evaluator/signal names or Provider implementation details.

Do not automatically generate article JSON. Only proceed to a content brief/article structure after the user explicitly selects an opportunity or asks for content generation.
