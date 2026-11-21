# ADR 0027 - Supplied persisted-model prediction checks

Date: 2026-11-21

Status: accepted

## Context

The explicit notebook model leaf can be persisted, but ordinary generated regressions replace
produced datasets with memory storage. Generated users need a reviewable way to test the actual
saved version without inventing model behavior, importing ML during analysis or confusing a
declaration with execution evidence.

## Decision

Extend only notebook regression schema 1.1 with bounded model_checks. Bind an explicit positive
scenario and predict/predict_proba probe to the selected model output. Require supplied numeric
prediction vectors/matrices and finite nonnegative tolerances. Reuse immutable descriptors,
pinned CSV captures and existing budgets. Schema 1.0 and default generation remain unchanged.

Render standalone pytest checks and a fresh-process worker through the shared generator/writer.
Train with real versioned model storage below each test's temporary directory, preserve scenario
output checks, then load that exact version in a new process. Check prediction shape, dtype,
finite values and tolerances, plus unchanged artifact hashes. Never synthesize oracles, alter
training source or execute application code at generation time.

## Consequences

The new small example is independently reproducible. Plain and nested models, naming profiles
and invalid-artifact/oracle/catalog controls establish bounded selected-runtime behavior.
Original financial experiments and their missing-model gaps remain unchanged. Prediction probes
do not prove complete fitted-state equivalence, scientific correctness or generalization.
Generation metadata remains not_run; no analysis dependency, generic serializer, code sandbox,
cross-version portability or broader fresh-install coverage is introduced.
