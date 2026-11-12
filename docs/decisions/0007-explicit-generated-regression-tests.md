# ADR 0007: ship regression tests from explicit expectations

Status: accepted, 2026-11-13.

## Context

Linear workflows now generate Kedro projects. Users need tests, but recording the generated
code's own outputs would silently validate existing mistakes. Missing business expectations
must remain visible.

## Decision

Accept a separate bounded immutable JSON contract of supplied inputs, scalar parameters,
final outputs and optional node expectations. Validate schema/binding without running source.
Emit standalone pytest tests using actual nodes, pipeline registration and JSON catalog I/O,
with temporary test workspaces and profile mappings.

Always emit a generation-time gap report. No contract means no suite or passing stub. Node
expectations are never inferred. Keep supplied data/hash, generation status and later test
execution separate. Validation cannot authenticate review or business correctness.

## Consequences

The first E3 increment delivers node/pipeline regressions with explicit oracle ownership.
Negative controls must show code/oracle drift causing failures. Generation stays independent
of pytest/Kedro imports; pytest is an optional generated-project dependency. Emitted tests
import no Notebook to Kedro code.

Exact finite-JSON comparison is narrow. Fresh dependency bootstrap, richer comparators and
tests for procedural conversion remain later increments. Running tests executes application
code and is not a sandbox or business proof. See the [contract](../reference/generated-workflow-tests.md).
