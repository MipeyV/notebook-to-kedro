# ADR 0005: inspect explicit functional blocks before adding generation

Status: accepted, 2026-11-06.

## Context

E2 needs source-independent building blocks for structured Python and notebooks. Existing
`NotebookFacts` and `ConversionPlan` encode the supported procedural notebook conversion path.
Pretending a Python module is a notebook would lose honest provenance; treating function calls
as dataset wiring would invent semantics before testing actual examples.

## Decision

Introduce a narrow immutable `FunctionalAnalysis` contract derived from explicit functions in
one script or real notebook code cells. Share deterministic AST utilities, retain source units
and statement accounting, and report unsupported constructs. Expose read-only API/CLI inspection
with paired examples and a static structural fingerprint. Keep file adapters outside the pure
analyzer and preserve existing conversion contracts.

Deliver E2 in two increments. This increment implements analysis/provenance only. The following
increment will define workflow entrypoints and data wiring, adapt supported blocks to Kedro and
check paired observable behavior. Do not introduce a universal `ProjectSpec`, execution policy,
provider dependency or UI abstraction to complete the first increment.

## Consequences

The shared engine has a concrete second source frontend without broadening generation claims.
The extra analysis contract deliberately coexists with notebook facts until working conversion
cases justify deeper unification. Static completeness/fingerprints cannot approve execution,
prove behavior or substitute for source-accounting checks. Procedural notebook segmentation,
multi-file analysis, arbitrary Python and local UI remain later work.

See the [inspection contract](../reference/functional-blocks.md) for exact boundaries.
