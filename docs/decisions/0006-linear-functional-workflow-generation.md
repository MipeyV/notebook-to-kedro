# ADR 0006: generate explicit linear functional workflows

Status: accepted, 2026-11-12.

## Context

Functional inspection now preserves honest script/notebook origins. Function-reference graphs
alone do not define dataset wiring, execution order or safe object-copy behavior. E2 needs a
working paired generation case before broader project or orchestration abstractions.

## Decision

Use an explicitly selected entrypoint with straight-line call assignments and one final named
return. A small versioned configuration distinguishes contained JSON file inputs, scalar
parameters and one JSON output. Require a single-use linear value chain to preserve order;
reject fan-out and reassignment rather than silently changing semantics.

Preserve all original instruction ASTs in a normalized module and retain captured raw source
and per-statement destinations in a manifest. Generate wrappers only for entrypoint calls;
internal helpers stay inside their original functions. Use assignment-mode memory datasets
between nodes to preserve identity. Recompute analysis/wiring before generation.

Extract the existing Kedro renderer from publication and reuse it, profiles and the shared
writer. Keep the procedural notebook API unchanged and do not fabricate notebook facts/cells.
Add final output persistence after graph rendering so output catalog entries are not mistaken
for existing input datasets. Check the paired workflow with real Kedro/JSON execution in tests.

## Consequences

The bounded E2 acceptance case is executable from both source presentations without executing
source during planning/generation. General DAGs, arbitrary return types, richer formats,
multi-file dependency reconstruction and generated-project tests remain future work. Static
acceptance, a manifest and fixture matches are not a general behavioral proof or consent gate
for running arbitrary user code. Existing pilot review requirements remain unchanged.

See the [workflow contract](../reference/functional-workflows.md) for precise API and limits.

The 2026-11-14 candidate-configuration increment adds opt-in workflow schema 1.1: flat JSON
objects whose values are finite scalars. Store these as immutable pairs, export fresh objects
and reuse the existing shared parameter renderer. Keep schema 1.0 scalar-only and validate
regression overrides using the workflow's declared schema. Unlike scalars, a mapping may be
consumed only once across orchestration calls; repeated parameter loads could otherwise change
source mutation/identity behavior. Mapping results can flow through assign-mode memory datasets.
This addresses one concrete real-workflow configuration gap, without approving independent
loaders/fan-in, external package reconstruction, typed domain objects or artifact side effects.

The later [ADR 0010](0010-source-ordered-functional-joins.md) adds opt-in schema 1.2 ordering
dependencies for independent calls and joins. The linear rules above remain the contract for
schemas 1.0/1.1; package, typed-I/O and artifact execution work remains separate.
