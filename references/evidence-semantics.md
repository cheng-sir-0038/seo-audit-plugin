# Evidence Semantics

Use this reference whenever a Product Skill must turn raw observations into a diagnosis state.

## Evidence layers

Keep three layers separate:

- **Observed**: directly read from HTTP, rendered HTML, repository code, first-party search data, or another named source.
- **Inferred**: a conclusion supported by observations but not directly observed.
- **Unknown**: a claim the available evidence cannot establish.

Never promote an inference to an observation just to make the answer decisive.

## Missing evidence

A missing row, unavailable provider, blocked runtime, unsupported content type, unavailable browser-rendered DOM, or unreadable repository surface is an evidence gap. It is not proof that a page does not rank, is not indexed, has no field data, lacks a feature, or has an SEO defect.

A limitation of the audit tooling is not a target-site Finding. If the user is explicitly auditing this plugin's own product coverage, describe the limitation as a capability gap / known limitation unless there is a separate repository defect that violates the intended capability contract.

When the missing surface is necessary for the requested conclusion:

1. say what cannot be established;
2. continue only with claims supported by the remaining evidence;
3. name the next capability or surface needed.

## Decision and interaction semantics

Do not turn ambiguity into an implicit default. Separate evidence routing from trusted execution input:

- **auto-continue**: one option is uniquely supported by deterministic facts; the runtime may resolve it without user interruption;
- **input-required**: two or more materially different choices remain valid, or an execution approval is required. The MCP Tool must elicit the missing trusted input before the dependent operation;
- **fallback-continue**: the primary evidence surface is unavailable but a documented weaker source can safely continue the job; disclose the fallback and its limits. This is not user approval;
- **stop**: the requested conclusion needs an unsupported evidence surface, the target cannot be resolved, or a hard policy blocks execution.

Model-visible Tool arguments never carry human approval or resolved GSC/GA4 Property identity. Property/provider lists are evidence/discovery surfaces, not permission to select the first row. A dependent Tool with multiple equally valid Property candidates uses native MCP elicitation; zero candidates remain an access/evidence gap.

## Diagnosis states

Technical findings use:

- `confirmed`
- `plausible`
- `already-safe`
- `unproven`

Ranking hypotheses use:

- `supported`
- `partially-supported`
- `excluded`
- `insufficient-data`

Ranking-drop premise states use:

- `decline-confirmed`
- `mixed-change`
- `decline-not-confirmed`
- `insufficient-data`

Use the narrowest state justified by evidence. Common SEO explanations are not evidence.

## Confidence

For material findings, use `high`, `medium`, or `low` confidence only after deciding the evidence state. Confidence does not replace the state and must not turn an unproven claim into a confirmed one.

## Source references

Every material Finding or Hypothesis must retain source references sufficient to recover the evidence that changed its state. Prefer concrete repository locations, HTTP/HTML observations, capability result references, and explicit time windows.

This file is the compact runtime reference used by Product Skills.
