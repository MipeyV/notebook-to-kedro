# ADR 0023 - Explicit source-ordered shared intermediate references

Date: 2026-11-19

Status: accepted

## Context

The remaining frozen boundary case creates one buffer, passes it to two mutating consumers and
combines results whose nested references must still point to that same buffer. Existing source
ordering and assign-mode intermediates already provide the needed runtime mechanics, while the
single-consumer guard deliberately rejects this wiring. Removing that guard globally would
silently change earlier contracts and admit boundary inputs/parameters with different load rules.

## Decision

Add an optional closed shared_data policy, independently versioned at 1.0, on source-ordered
workflow schemas 1.2 through 1.7. Existing schema selection and absent-policy behavior are unchanged.
The immutable declaration names 1 to 100 distinct public values, at most 64 characters each.
Only actual nonfinal intermediate outputs with at least two explicit argument occurrences qualify.
All undeclared data and mutable mapping parameters retain the existing single-use guard. Catalog
boundaries, parameters, unknown/unused/final values and linear 1.0/1.1 modes cannot opt in.

Recompute exact wiring before generation. Retain original source ASTs and wrappers, assign-mode
intermediates and existing adjacent source-order dependencies. Duplicate use within one call
forwards the same declared object twice. Effects are not inferred, optimized or repaired. Later
calls do not start after a failed call and no retry is added. No runtime/analysis dependency is added.

Plan/manifest schema 1.7 records the policy, producer, ordered consumer arguments, assign mode,
single-process scope and runtime_validation=not_run. Workflow versions and local-operation envelopes
remain separate. The concrete policy composes existing API/CLI/preview/publication; preparation
retains its prior strict single-use validation. Publication still uses the shared writer.

## Consequences

SequentialRunner and ThreadRunner can preserve the frozen buffer identity and left-before-right
mutations without copies. Negative controls change storage to deepcopy or remove the ordering
edge and expose the original identity/order assertion failures. Process runners, partial pipelines,
edited graphs/catalogs and external concurrent mutations are not covered. This is not arbitrary
fan-out inference, a purity proof, source-effect completeness or execution consent.

JSON expectations do not encode aliases between separately supplied node arguments. Preserve
original pipeline oracles and explicitly supplied constructor tests; report other node gaps.
Record a new independent follow-up without rewriting original blocked inputs, criteria or outcomes.
Financial runtime authorization and pending human pilot review remain unchanged.
