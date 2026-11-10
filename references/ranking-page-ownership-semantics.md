# Ranking Page Ownership Semantics

Use when the user asks about cannibalization, multiple Ranking Pages for one query, ranking URL switching, intended Target Page mismatch, or which page should own a keyword.

## Do not equate multiple ranking pages with cannibalization

Multiple URLs can legitimately rank for the same query when they satisfy different intents, formats, stages, or subtopics. Diagnose a harmful ownership conflict only when evidence shows the pages are competing for substantially the same search role and the behavior is unstable or diluting the intended page.

## Required evidence

Prefer:

- query + market;
- current and previous ranking URL/page observations;
- intended Target Page when the user has one;
- current SERP page types/intents;
- PageInspection of competing URLs;
- optional GSC Query × Page when available.

Provider coverage limits must remain explicit; one DataForSEO `ranked_serp_element` does not prove an exhaustive list of every URL that can rank for that query. GSC is optional corroboration for page ownership: same-provider ranking-URL history can establish owner switching, while GSC Query × Page is stronger first-party impact evidence when available, not a mandatory prerequisite.

## Distinguish states

Classify the observed behavior before recommending action:

- `stable_owner` — one suitable page consistently owns the query;
- `intent_split` — multiple pages rank but serve meaningfully different intents/roles;
- `page_switching` — observed owner changes over time;
- `probable_cannibalization` — highly overlapping pages compete for the same role and switching/visibility evidence supports harm;
- `insufficient_evidence` — multiple URLs exist but harm/role overlap is not established.

Track intended Target Page separately as `matched | mismatched | unknown`. A Target Page mismatch can coexist with a stable owner or page switching and is not itself cannibalization.

These are diagnosis semantics, not Provider-native statuses. The deterministic `PageOwnershipAssessment` uses the same state set; its machine wire format is versioned separately from user-facing presentation.

## Cannibalization evidence threshold

Do not promote a case to `probable_cannibalization` from page count alone. Require:

1. at least two pages with evidence that they serve substantially the **same search role**;
2. **high content/topic overlap** between those pages; and
3. either observed owner switching or a supported negative visibility impact.

Two pages ranking strongly and stably (for example both occupying very high positions) are not automatically a problem. If overlap exists but harm is not established, keep the state `insufficient_evidence` and explain what evidence is still missing.

## Deterministic actions

The current assessment maps states to action categories:

- stable owner → keep/strengthen the owner; if Target Page is mismatched, reassess which page should own the query;
- intent split → keep page roles distinct;
- page switching → clarify/differentiate page roles before consolidating anything;
- probable cannibalization → consolidate or differentiate based on the pages' actual user purpose;
- insufficient evidence → collect page-role/visibility evidence when key facts are missing; if two pages are already stable in very strong positions with no negative impact, monitor instead of forcing a consolidation.

Do not automatically choose canonical/redirect as the action. Those are URL lifecycle mechanisms and are only appropriate when the underlying page-purpose decision supports them.

## Recommended actions

Choose based on role and evidence:

- strengthen the intended owner page;
- differentiate page intent/topic/format;
- adjust internal links/anchor context toward the intended owner;
- merge/consolidate materially duplicate pages when one page should own the role;
- redirect only when a page no longer has a distinct user purpose;
- update keyword/page ownership planning;
- monitor when multiple pages are healthy and intentional.

Do not use canonical or redirect solely to “force ranking” when both pages are genuinely distinct and useful.

## Content lifecycle interaction

If the user is deciding refresh/merge/delete, also read `content-lifecycle-semantics.md`. Page ownership can explain why a declining article should be consolidated, but the lifecycle action still needs content/value evidence.

## User-facing wording

Prefer:

> 当前可以确认这个 Query 在 A/B 两个页面之间发生排名页面切换，而且两页承担的搜索意图高度重叠，因此存在明显的页面职责冲突。

Avoid:

> 有两个 URL，所以一定是关键词内耗。

## Research facts source
