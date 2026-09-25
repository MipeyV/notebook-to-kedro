# Hybrid Plan Assembly

## Purpose

Hybrid assembly converts a validated `SemanticPlanningResult` into the existing
`ConversionPlan` consumed by reporting and Kedro generation. The LLM proposes semantic structure;
the deterministic V1 plan remains authoritative for executable details.

`HybridSemanticPlanner` implements the same `SemanticPlanner` protocol as the deterministic
planner. It builds the V1 baseline, requests semantic suggestions only when the grouping schema
permits at least one merge, assembles a safe hybrid plan, and returns a structurally unchanged V1
fallback whenever the provider or assembly fails.

## Supported Decisions

The initial assembler permits the semantic provider to:

- rename a deterministic task;
- group adjacent deterministic tasks into one node;
- attach global and task-level review notes.

It does not require a closed task taxonomy. A model can choose a new node name that describes an
unseen business transformation while the source remains tied to known statements.

The assembler currently rejects:

- splitting one deterministic task into partial statement groups;
- grouping non-adjacent tasks, which could reorder execution;
- parameter suffix collisions inside a grouped node;
- pipeline IDs other than `notebook_pipeline`;
- blocked or statically invalid plans.

These constraints are explicit compatibility limits, not guesses. Future increments can relax
them only when the IR and generator can preserve the same deterministic guarantees.

## Static Authority

The provider-suggested inputs, outputs, and parameter references are never copied directly into
the final plan. For every accepted task, the assembler recomputes:

- ordered source cells and statement IDs;
- external inputs based on preceding outputs inside the group;
- outputs and diagnostic codes from the selected V1 tasks;
- exact source by concatenating adjacent deterministic source fragments;
- parameter names and function arguments using the accepted node name.

If suggested interfaces differ, the static values win and diagnostic `SP004` records the
adjustment. Existing imports, catalog datasets, blocking codes, and parameter values are preserved.

## Provenance And Fallback

Hybrid plans use planner version `0.2.0-hybrid` and add reportable diagnostics:

| Code | Meaning |
| --- | --- |
| `SP001` | Provider, model, and prompt provenance for an accepted response. |
| `SP002` | Response-level review note. |
| `SP003` | Task-level review note. |
| `SP004` | Suggested interfaces were replaced by deterministic interfaces. |
| `SP005` | Provider or assembly failure caused deterministic fallback. |

Fallback plans retain the V1 tasks and use planner version `0.2.0-hybrid-fallback`. Blocking
source diagnostics bypass the provider entirely. The provider is also skipped when every valid
group is a singleton. That no-op path returns the original V1 plan and version `0.1.0`; it does
not add provider provenance or a fallback diagnostic because no provider call was attempted.

## Remaining Limitation

The assembler accepts only the existing single `notebook_pipeline` target because the generator
does not yet materialize multiple pipeline packages. Multi-pipeline support must update the IR,
registry generation, cross-pipeline dataset wiring, reports, and equivalence tests together.

The public Python API and both CLI commands expose explicit `deterministic` or `hybrid` selection,
with deterministic planning remaining the default. Hybrid mode requires the name of a downloaded
local Ollama model and accepts loopback URL and timeout overrides.
