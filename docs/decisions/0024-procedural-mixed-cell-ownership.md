# ADR 0024 - Single instruction ownership for procedural mixed notebook cells

Date: 2026-11-19

Status: accepted

## Context

The original notebook path already converts procedural pandas/scikit-learn cells without source
functions. A mixed import/CSV/business cell previously caused its whole cell task and shared
imports/catalog to claim the same statements. Source accounting correctly blocked publication.
Dropping that audit or ignoring unsupported cells would violate faithful conversion.

## Decision

Build pure internal planning views that remove only proposed shared import/catalog instructions.
Keep original NotebookFacts, cell IDs, statement IDs/spans and raw source unchanged. Retain cell
business blocks and their exact statement ASTs; do not synthesize source functions/cells, execute
source, infer business oracles or introduce a universal project abstraction.

Derive retained writes/calls and force the promoted CSV boundary as the first business node's
input even if ignored or overwritten. Existing dataset versioning preserves in-cell rewrites.
Keep existing catalog type/path/alias/reader-option and parameter evidence checks. The independent
SA008 audit permits newly mixed cells only with imports first, at most one supported CSV load,
then a source-ordered business data chain. Check first-read inclusion, actual task order and
absence of raw catalog reloads until an explicit source rewrite produces an intermediate.
Reject nested/dynamic CSV calls retained in newly mixed business code; never replace reader options.

Retain default cell boundaries for business tasks. No new planner mode, source kind, UI rule,
runtime dependency or wire schema is required. Previously valid unmixed output stays compatible.
Low-level task planning remains a proposal; high-level planning or direct source_facts validation
provides the audit before publication through the shared writer.

## Consequences

A synthetic procedural CSV/preparation/split/training/evaluation notebook can generate four
nodes and five parameters with default/custom profiles. Trusted reference execution and actual
SequentialRunner/ThreadRunner, catalog/parameter and Kedro CLI checks verify predictions/accuracy,
single CSV loading, stale-output independence, retained assertion failures and a negative business
mutation. These executions are separate from static analysis/generation and remain fixture-bound.

Arbitrary conditional scopes, alias reconstruction, independent effects, exploratory/display cells,
multi-reader mixed layouts and richer reader options need additional contracts. Existing functional
workflow regression expectations do not supply procedural typed fixtures or generated tests.
Original experiment outcomes and pending human pilot review remain unchanged; no model/financial
execution or new human productivity evidence is introduced.
