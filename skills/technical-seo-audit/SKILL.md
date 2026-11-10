---
name: technical-seo-audit
description: Audit a web repository and live/rendered pages for evidence-backed technical SEO issues and map supported findings to real implementation locations. Use for crawl/indexability, canonical/redirect/status, hreflang/international SEO, JavaScript rendering, internal-link/pagination/faceted navigation, structured data/rich results, site safety, search appearance, media SEO, migrations, template/release regressions, page performance, or general technical SEO health checks.
---

# Technical SEO Audit

Find technical SEO problems that are supported by repository or runtime evidence. Do not turn a generic checklist into an audit.

This Skill is read-only. It may locate the owning implementation and prepare a Diagnosis Handoff, but downstream code execution belongs to the Host. Do not generate or apply a patch, diff, commit, build, test, deploy, or publish operation.

Choose the target surface before inspecting anything. For a domain/URL-only audit, use the registered SEO MCP capabilities and Host browser/runtime evidence; collect covered HTTP/HTML/resource/performance facts through `PageInspection`, `ResourceInspection`, `IndexInspection`, and `PageQuality` rather than treating Host shell/curl as a parallel data source. Do not inspect this plugin's own `mcp.json`, `.mcp.json`, MCP server/client/adapter source, or tests, and do not run shell commands to prove that the plugin is wired correctly. Read repository code only when the user explicitly included a repository/project in scope or when a supported finding needs localization in that target repository. If a required capability is missing, report a capability gap / missing evidence instead of debugging the plugin implementation inside the user task.

## References

Read only the references needed for the current task:

- `../../references/evidence-semantics.md` — evidence states, missing-data behavior, and confidence rules. Read before classifying any material Finding.
- `../../references/technical-seo-checks.md` — evidence surfaces, page-purpose clarification, priorities, and stop conditions. Read for a full audit or when new evidence needs user intent before choosing a recommendation.
- `../../references/technical-seo-scenario-router.md` — route the user's actual hreflang/migration/JS/internal-link/pagination/schema/search-appearance/media/release-regression input to the narrow specialized reference. Read for targeted technical questions and before expanding a full audit into specialist domains.
- `../../references/capability-boundaries.md` — `PageInspection`, `IndexInspection`, `ResourceInspection`, `PageQuality`, and other V1 capability boundaries. Read when runtime or provider-backed evidence is used.
- `../../references/page-quality-semantics.md` — Chinese business meanings and thresholds for LCP/INP/CLS/FCP/TTFB. Read only when page performance is actually inspected or reported.
- `../../references/structured-data-seo-semantics.md` — interpret rich-result states and inspection coverage. Read for Rich Results questions and the structured-data result of an SEO one-click recheck.
- `../../references/diagnosis-output.md` — Finding fields and the structured Diagnosis Handoff contract. Read before producing material Findings or an engineering Handoff.

## Workflow

### 1. Establish the available evidence surface

Determine whether the task has repository access, a runnable app, a live URL, user-provided evidence, or some combination. State important limits when the requested conclusion depends on a missing surface.

### 2. Understand how the page is produced

Inspect the repository before judging implementation. Identify the rendering, routing, metadata, canonical, sitemap, robots, locale/pagination, and relevant server/CDN paths that can control the delivered result.

Prefer the repository's existing mechanisms over inventing a parallel SEO layer.

### 3. Verify runtime truth when possible

When live or local runtime evidence exists, verify the delivered behavior instead of relying on code intent. Use `PageInspection` for current HTML, `ResourceInspection` for robots.txt/sitemaps, `IndexInspection` for Google's indexed-state facts when GSC is available, and `PageQuality` only when page quality is materially relevant.

For internal-link or pagination questions, use `PageInspection.anchor_links / rel_next_urls / rel_prev_urls` only for the inspected page. Treat orphan/depth/inlink-count or domain-wide link claims as unavailable without a site-wide graph; do not extrapolate them from one page.

When a finding depends on page purpose, use the user's already-stated intent or ask the smallest question that changes the recommendation. For example, an observed `noindex` needs a distinction between a page intended for search and one intentionally excluded. Follow the mid-task clarification guidance in `technical-seo-checks.md`; a business answer is not permission to edit or publish.

For Rich Results questions, use the derived `check_rich_results` path over PageInspection facts; do not scrape Google's Rich Results Test webpage. For malware/phishing/unsafe-site questions, use `SiteSafety` and preserve `no_known_threats` / potential-risk wording instead of claiming absolute safety.

For an explicit **SEO one-click recheck**, run the fixed SEO baseline rather than progressive specialist expansion: `PageInspection` + robots/sitemap `ResourceInspection` + connected GSC `SearchPerformance` and homepage `IndexInspection` + `PageQuality` mobile/desktop + `check_rich_results` + `SiteSafety`. Pass the supplied domain/URL to the GSC-backed Tools and let their hidden Property resolver auto-select or elicit when ambiguous; do not preselect from a site list. Keep unavailable first-party checks as gaps, and do not present this baseline as a full-site crawl. GEO is outside this recheck.

For page-performance questions, use `PageQuality` as the evidence surface. Do not open `pagespeed.web.dev` in a Host browser to collect PageSpeed metrics or audits. If the user explicitly scopes mobile or desktop, inspect only that strategy; otherwise inspect both `mobile` and `desktop` separately before diagnosing the performance problem. Tracking-only URL uses the canonical URL for PageQuality by default once `PageInspection` confirms the query parameter does not define a distinct page; compare tracking and canonical forms only when parameter-sensitive cache/rendering behavior is itself the hypothesis. Use Host browser evidence only when rendered DOM, real interaction, or visual behavior itself is material.

### 4. Inspect the requested technical domains

Check only evidence-backed domains relevant to the audit. For a targeted user question, use the scenario router and load only the matching specialist reference; for a full audit, expand into specialist references only when the site/input actually exhibits that domain. Map each supported repository-controlled issue to the source that owns it and identify the smallest plausible modification boundary.

Do not broaden the work into keyword strategy, backlink planning, content calendars, or generic marketing advice unless the user requested them.

### 5. Classify and prioritize

Separate observed facts, inferences, unknowns, and audit capability limitations. A missing/non-applicable inspection surface is not a target-site Finding. Classify every material Finding using the shared evidence semantics, then rank supported technical issues by search risk and implementation scope.

Do not fabricate numeric impact.

### 6. Finish at diagnosis

Lead with the direct answer, then report material Findings, capability limitations / missing evidence, implementation locations, important already-safe checks, unknowns, and the next Action Category.

In interactive chat, render the result for the user; do not print the full structured Diagnosis/Handoff JSON unless the user explicitly requests machine-readable output or the Host is transferring it downstream.

Use SEO/domain terminology in the user-facing answer. Provider names may be shown as evidence provenance, but internal Capability/Tool/Gateway/Adapter/Client/module/file names belong only to explicit implementation/debug discussions.

Create an engineering Diagnosis Handoff only when a repository-controllable issue is sufficiently supported and localized. If it covers only a subset of the audit, say so. The Handoff must stand on its own without old chat history.

Do not claim a full-site audit when only a subset of URLs or templates was inspected.
