# ADR 0010: preserve source order across independent functional calls

Status: accepted, 2026-11-15.

## Context

The first real workflow proposal has two independent loaders followed by a node that consumes
both results. Schemas 1.0/1.1 require every call to consume its immediate predecessor, because
data dependencies alone do not preserve source call order. Removing that guard would allow
Kedro to reorder or concurrently execute calls with unverified effects.

## Decision

Opt-in workflow schema 1.2 selects source-order execution for the existing straight-line,
single-assignment function-call subset. Keep data and mapping parameters single-use and the
final return bound to the last call. Preserve schema 1.0/1.1 linear behavior and parameter rules.

For an adjacent pair without a natural data dependency, the recomputed plan declares an
ordering edge. The shared renderer routes the previous result to a private `_ntk_after` input
on a generated callable adapter. The adapter does not forward that value to the business node.
Reuse assign-mode memory datasets, so the extra ordering read does not copy/serialize the
object. Original instruction ASTs, business wrapper signatures, values and output names stay
unchanged. A join can consume each loader result once as an actual function argument.

Use an importable adapter class rather than an invocation-local closure. Check its pickle
round-trip separately; this does not establish every runner's process behavior. Validate each
ordering edge against the immediately preceding single-output task and reject argument capture
before publication. Emit the adapter only when an edge is needed. Keep graph construction in
the engine and reuse compile preflight, profiles and the shared writer.

Plans for schema 1.2 export schema 1.1 with an explicit `source_order` policy and ordering
edges, distinct from observed function arguments. Generated manifests additionally identify
the ordering input/dataset and record that it is not forwarded. Analysis schema 1.1 and local
operation/project-settings schema 1.0 remain separate.

## Consequences

Independent calls and joins can retain source sequencing without claiming their effects
commute. The complete registered pipeline preserves call order and stops after a failed call;
no retry or concurrency optimization is introduced. Trusted paired fixtures exercise default
and custom profiles with SequentialRunner and ThreadRunner, identity checks, exception traces,
shipped pytest checks and a negative control removing an order edge.

This remains a bounded ordered workflow, not general DAG/fan-out inference. Data reuse,
mutation through shared arguments, control flow, source-package reconstruction, typed I/O,
artifact execution policy and arbitrary runtime behavior need separate contracts. An unused
assigned result does not remove its original call. A declared JSON boundary does not verify
domain-object serialization. Real-project planning alone does not establish full conversion,
installation, execution consent or pending human pilot approval.

See the [workflow reference](../reference/functional-workflows.md#source-ordered-calls-in-schema-12)
for the public configuration and provenance contract.
