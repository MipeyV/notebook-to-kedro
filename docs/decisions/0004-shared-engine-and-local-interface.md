# ADR 0004: Build a shared ML engineering engine with local operation interfaces

[Documentation index](../README.md)

- **Status:** Accepted direction; implementation starts with source accounting
- **Date:** 2026-11-06

## Context

The intended product lets a user open an ML project, configure local standards and choose
conversion, project creation, refactoring, standardization or validation. Notebook-to-Kedro
is the first operation. The UI may be a local application or a VS Code extension; this choice
is not yet settled. Existing components should be strengthened and reused rather than forked
into separate tools or replaced with a broad platform rewrite.

## Decision

Keep analysis, provenance, workflow representation, planning, generation and validation in a
reusable core. Operations compose these capabilities under different contracts. UI/CLI choose
operations and present plans, diffs and evidence; they do not duplicate transformation logic.
Derive source-independent contracts from working notebook and structured-script slices. Kedro
remains the first backend. Prompt-based generation needs reviewed requirements, not a fictitious
equivalence oracle; project standardization needs diff/conflict/idempotence contracts.

The first approved engine increment is a recomputed statement-accounting audit and limited graph
checks. The high-level notebook planning API blocks unsupported/omitted/duplicated instructions,
source AST/provenance/import drift, unsupported catalog relocation and inconsistent source-derived
parameter/dependency bindings. Low-level candidate planners remain proposal APIs; direct generation
can opt into the same audit by supplying `source_facts`.

Keep this evidence outside `ConversionPlan` and `NotebookFacts` schemas. Fully accounted legacy
plans remain byte-identical. A separate versioned audit carries facts identity, plan fingerprint,
per-statement dispositions and diagnostics. Reports are declarations for inspection, not permission
to bypass recomputation or authenticated/full runtime equivalence. Preserve strict node-code validation.

## Consequences

- Lost standalone assertions, expressions and side-effect cells become visible blockers; automatic
  preservation/ordering of such cells is future work.
- Exact option-free pandas CSV statements can be accounted as catalog relocation. Unsupported
  reader options, ambiguous bindings and mixed load/task cells fail rather than lose semantics.
- Later writes of a catalog-backed variable are genuine tasks. Seed generated dataset versioning
  with catalog inputs and reject resolved dataset-name collisions before publication.
- Windows access/sharing refusals observed in regression tests allow at most three attempts at
  the final directory rename, rechecking the destination each time. No writes, model calls or
  execution are retried; other/persistent errors remain visible. No filesystem lock is claimed.
- No UI, Python/repository frontend, general workflow IR, test generator or patch applier is
  introduced by this first increment. Pilot review status and old measurement evidence stay intact.

## Alternatives considered

- **Build UI first:** would expose incomplete fidelity guarantees and risk duplicating core rules.
- **A universal ProjectSpec now:** insufficient concrete source/operation cases for a stable contract.
- **Count task IDs alone:** cannot detect changed bodies, lost import/catalog semantics or miswired data.
- **Silently retain only data-producing cells:** drops assertions and side effects without review.
