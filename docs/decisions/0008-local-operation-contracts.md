# ADR 0008: Compose existing engines through explicit local operations

[Documentation index](../README.md)

- **Status:** Accepted; initial deterministic slice implemented
- **Date:** 2026-11-14

## Context

The notebook and functional workflow engines now support bounded generation and explicit
regressions. A future local app or VS Code extension needs project configuration and results
it can present without owning transformation rules. The first interface should use concrete
operations, rather than a universal project model or an independent UI conversion engine.

## Decision

Add explicit versioned JSON local settings, immutable inspect/plan/generate requests and result
envelopes. Support the two existing deterministic source kinds. Keep workflow I/O, architecture
profiles and regression expectations in their existing schema files; local settings reference
them rather than introducing competing schemas. Resolve the project root from the settings
file and all source/configuration/copied input/destination paths inside that declared root.
Do not add automatic configuration discovery, provider transport or execution hooks.

Planning renders the actual proposed new files without filesystem writes. Extract functional
rendering from publication and share the writer's read-only validation. Preserve source
accounting, strict AST/wiring checks, profile behavior, optional expectations and the existing
staging writer. Generation recomputes current inputs and accepts no cached serialized plan.
Neither inspection completeness nor successful publication is runtime verification.

Expose the operations through Python and `project inspect|plan|generate` in the CLI. Retain
existing direct API/CLI contracts. Record effective settings, static status, file inventories
and explicit runtime/install gaps in result envelopes. Keep normal generation independent of
Kedro, pytest, ML packages, provider SDKs and live experiments.

## Consequences

- The new operation boundary has an explicit working-root contract, including procedural CSV
  copy paths; outside-root data blocks these operations instead of being silently copied.
- A preview is a review snapshot, not an authenticated approval or apply capability. Changed
  valid inputs are recomputed; binding publication to an approved hash needs a later contract.
- Existing-project diffs/patches, general DAGs, requirements generation, job systems, a shared
  `ProjectSpec`, an app and a VS Code extension remain outside this slice.
- Source/metadata read races and publication limitations remain documented; this is not an OS
  sandbox, atomic project snapshot or filesystem lock. Pending pilot human review is unchanged.
