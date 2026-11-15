# ADR 0014: retain explicitly selected final results in memory

Status: accepted, 2026-11-15.

[Documentation index](../README.md)

## Context

Application functions can return domain objects containing datasets, protocols, paths and other
values without a JSON serializer. The existing final-output contract requires JSON. Inferring
serialization, converting a dataclass to a dictionary or falling back after a save error would
change application behavior. Intermediate assign-mode memory datasets already preserve references.

## Decision

Opt-in workflow schema 1.5 accepts the explicit output target `memory` for the single named final
call result. It inherits schema 1.4's required package/file-input fields and ordering/parameter
rules. Existing JSON targets remain available; legacy schemas still reject the memory target.

Render the final catalog entry as `MemoryDataset(copy_mode="assign")`, with no filepath, serializer
or type conversion. Leave function bodies, result names, call ordering and source accounting
unchanged. Require the final named source return as before. Do not infer or validate runtime
types. The same-process Kedro catalog retains the original object after successful execution;
tests cover SequentialRunner and ThreadRunner. No process-runner portability claim is made.

Plan/manifest schema 1.4 records the result dataset, selected mode/persistence, unverified type
and undefined artifact policy. Configuration stays schema 1.5, package analysis 1.2 and local
operation/project settings 1.0. Interface previews render those facts without running a workflow
or transporting the business object in a JSON operation response.

Existing JSON regression contracts do not specify typed result comparators; reject them for
memory outputs and record explicit missing-result-expectation gaps without test stubs. JSON
mode with supported JSON inputs keeps its generated regressions. Synthetic development tests
use hand-specified result fields, identity checks and a deliberate JSON serialization failure.

## Consequences

An opaque result can retain its original type and reference identity without a fabricated
persistent format. Python callers that explicitly run a pipeline can read it from their catalog.
It is not persisted: a new catalog/process cannot recover it, and a `kedro run` process ending
does not create a durable result. Releasing or discarding the catalog follows Kedro semantics.

This setting does not suppress application effects, approve benchmark execution or manage
application-owned artifacts. Durable results, typed comparators, artifact destinations and
dependency/distribution metadata need separate explicit contracts. Actual human pilot review
and real-project runtime validation remain pending.
