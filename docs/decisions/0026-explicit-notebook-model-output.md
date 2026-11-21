# ADR 0026 - One explicit persisted notebook model leaf

Date: 2026-11-21

Status: accepted

## Context

The nested financial cases return fitted models in memory. A practical generated project needs
a way to keep and reload an explicitly selected model without inferring types, rewriting source
or importing ML libraries during analysis. Intermediate serialization could change computation,
identity and scheduling semantics, so a general catalog override is outside this slice.

## Decision

Accept one optional model_output source identifier through notebook generation API, CLI and local
settings. Require original source facts and the existing audit. Bind only the latest generated
leaf, excluding intermediate/ordering consumers and Kedro's reserved parameters dataset.

Use the existing kedro-datasets PickleDataset, stdlib pickle backend, fixed local filepath and
ordinary versioned storage. Add a declaration manifest and runtime guide through the shared
renderer/writer. Keep source/node ASTs, wiring, parameters and default generated output unchanged.
Do not expose paths, serializer hooks, arbitrary catalog overrides or a new project specification.

When explicit regressions are supplied, validate the model catalog entry exactly but keep their
outputs in isolated memory datasets. Preserve supplied oracles and missing-model gaps. Separate
runtime checks establish storage/reload evidence; generated tests do not infer a model comparator.

## Consequences

The credit Pipeline and calibrated lapse ensemble can be saved and reloaded in the selected
environment with matching predictions and fitted state. No analysis dependency, automatic model
classification, remote provider, functional-workflow schema or source-accounting relaxation is
introduced. The original data/source/regression/observation snapshots remain unchanged.

Pickles must be trusted and need compatible runtime dependencies/importable classes. Kedro owns
save versions and dataset errors; no concurrency lock, transactional storage, partial-file cleanup,
cross-version portability, arbitrary-object guarantee or deployment contract is supplied. Further
serializers, typed artifact comparators and broader installation evidence need separate work.
