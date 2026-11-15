# ADR 0012: prepare explicitly declared orchestration before persistent I/O

Status: accepted, 2026-11-15.

[Documentation index](../README.md)

## Context

A package can expose usable functions without containing an orchestration entrypoint. The
faithful workflow converter must continue to reject a missing entrypoint. Injecting one into
captured facts would confuse original source with a new integration decision. Requiring typed
data and artifact serializers before reviewing an actual call sequence also obscures the
remaining work.

## Decision

Add a separate deterministic preparation API/CLI, with an explicit ordered call declaration.
Preview by default; publish only when a new output directory is supplied. Capture one regular
local package using the existing inventory, inspect its selected Python module without imports
or execution, and require declared calls to identify observed function definitions.

Synthesize `workflow_adapter.py` with forwarding functions and a new entrypoint. Original
functions, annotations, imports and package resources remain unchanged in the copied package.
Forwarding functions use original argument names and delegate by keyword. Shared straight-line
call validation enforces exact signatures, bound names, distinct assignments, single-use values
and the final call result. All arguments are conservatively single-use; there is no parameter
type or persistent I/O inference. Calls retain their declared order, including independent loaders.

Keep observed module facts, package inventory, operator declaration and synthesized adapter facts
separate in `workflow-preparation.json`. Record `unreviewed_proposal`, `not_run` execution and
undefined persistent-I/O/artifact policies. The synthesized unit owns its own path/hash/spans;
its calls are never represented as existing original instructions. Original function bindings
record their block IDs and AST hashes. These local records do not authenticate provenance.

Recapture the inventory before rendering. Reuse portable target validation, private staging and
no-overwrite publication. Refuse destination/source-package overlap and an existing adapter file.
Do not install dependencies, execute code, invent I/O configuration, emit pytest stubs or mutate
the source package. The original converter and source-only inspection remain independent.

## Consequences

An explicit missing orchestration can now be reviewed as concrete source in a separate package
copy. Synthetic tests check order, type/reference identity, exception boundaries and subsequent
Kedro conversion with separately supplied JSON I/O/expectations, including a changed-binding
negative control. A private real-source preview can establish the proposed static shape without
publishing or executing the actual application.

The prepared copy is not a Kedro project or an approved integration. Domain loaders, typed
results, sidecars, dependency/distribution metadata, artifact ownership and reviewed expectations
remain separate contracts. No scientific equivalence or human pilot approval is inferred.
The initial operation is API/CLI-only; the existing VS Code operation envelope is unchanged.
