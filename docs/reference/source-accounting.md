# Conversion source accounting

[Documentation index](../README.md)

Status: initial deterministic API/use-case guard implemented. Audit schema `1.0` is separate
from existing facts/planning and benchmark artifact schemas. No notebook code is executed.

## Inspect an audit

```python
from notebook_to_kedro import analyze_notebook_path, audit_conversion_source, plan_notebook_path

path = "tests/fixtures/notebooks/file_backed_training.ipynb"
facts = analyze_notebook_path(path)
plan = plan_notebook_path(path)
audit = audit_conversion_source(facts, plan)
print(audit.to_json())
```

The immutable result records schema version, supplied notebook path/SHA-256, a SHA-256 of
the plan's sorted compact dataclass JSON, ordered statement dispositions and diagnostics.
`complete` means these source-accounting and limited static checks passed, not full semantic,
environment, business or production validation. The audit performs no provider/filesystem I/O
and does not import source libraries. Acquire facts from the trusted analyzer; supplied facts
are not independently re-read or authenticated by this function.

Every parsed top-level statement receives one record with its cell/statement IDs, claimed
destinations and a reason:

| Disposition | Meaning |
| --- | --- |
| `task` | Claimed by one task; its ordered source AST and provenance are checked separately. |
| `module_import` | Preserved as an ordered shared import, without a second task claim. |
| `catalog` | Exact supported CSV relocation, with one matching catalog entry. |
| `unhandled` | No single supported destination; conversion must be rejected or explicitly supported later. |

Unparsed/blocked source cannot produce a complete audit just because it has no statements.
No implicit exclusion policy or human approval is inferred from a passing audit.

## Checks and diagnostics

| Code | Blocking condition |
| --- | --- |
| `SA000` | Source analysis has blocking diagnostics. |
| `SA001` | Existing plan validation fails or the notebook path differs from supplied facts. |
| `SA002` | Original statements are unhandled/duplicated or task statement references are unknown. |
| `SA003` | Task source AST, statement order or cell provenance differs from declared source. |
| `SA004` | Catalog relocation is not one-to-one with exact supported pandas loading. |
| `SA005` | Ordered shared imports differ from source. |
| `SA006` | Declared inputs lack earlier task/catalog producers, source dependency inputs are missing, outputs are not source writes, or source names are unresolved. |
| `SA007` | Selected parameter values differ from deterministic extraction, or task/argument/source-cell bindings are inconsistent. |
| `SA008` | Mixed-cell promotion cannot preserve the required import/CSV preamble, first read, source task order or linear data chain; unsupported retained CSV readers and catalog reloads also block. |
| `SA009` | A recognized Pipeline component alias is read after fitting across task boundaries that can detach its fitted state through memory copies. |

Catalog relocation supports a single ordinary assignment from an earlier bound pandas import,
with exactly one positional literal local path and no reader keywords/unpacking. Compare dataset
type, copied filepath and source filepath with the current renderer's convention. Rebinding the
reader alias, reader options, remote URIs and multiple catalog claims cannot silently pass.
Supported mixed cells use the separate ownership/order checks below. A loader kept wholly in
an unchanged legacy task remains a code statement; accounting
does not make its runtime paths portable or invent a catalog connector.

Parameter checks reuse the current deterministic extraction rules. Hybrid task/parameter prefixes
may change, but selected source cell/suffix/value evidence and task argument bindings must match.
This is not an independent proof that every relevant business parameter has been extracted.

Graph checks use source name-flow facts and the plan's ordered interfaces. Internal dependencies
inside a merged task remain internal. The renderer separately versions the first rewrite of a
catalog-backed variable and rejects generated dataset names with multiple producers.

## Enforcement and boundaries

`plan_notebook_path` audits the returned deterministic/injected/hybrid proposal. Passing plans
are unchanged; failures add blocking diagnostics visible in the ordinary conversion report.
CLI generation then refuses them before output publication. Low-level `plan_tasks` and provider
APIs remain proposal-building boundaries, not source-completeness guarantees.

Direct callers can request the same guard when generating a supplied plan:

```python
from notebook_to_kedro import generate_kedro_project

generate_kedro_project(plan, "generated/checked_project", source_facts=facts)
```

Without `source_facts`, the generator still enforces plan validation, compile-only preflight,
target graph checks and the shared writer, but cannot establish completeness against an absent
source. Do not consume serialized audit results as approval; recompute from the current supplied
facts/plan. The fingerprint includes diagnostics, so changing a plan also changes audit identity.

Unsupported standalone side effects/assertions and unsafe mixed cells remain rejected.
The bounded mixed-cell extension below separates only leading imports/catalog instructions;
it does not split arbitrary business blocks, model object identity/aliasing or all nested scopes, prove
safe import hoisting/side-effect ordering, lock changing files, validate data schemas, generate
project tests or replace behavioral comparison. See [ADR 0004](../decisions/0004-shared-engine-and-local-interface.md)
and the [roadmap](../product/roadmap.md) for the next functional-block/Python slice.

## Fitted Pipeline aliases

Added on 2026-11-21, SA009 conservatively rejects a bounded object-identity hazard exposed by
the [nested financial corpus](../evaluation/nested-financial-models.md). For example, a named
preprocessor created in one task, passed as a step to a Pipeline fitted in another, and later
read through its original name can remain unfitted in Kedro because memory datasets copy it.
Reading the fitted component through the returned model (`model.named_steps[...]`) avoids that
particular external alias. The tool reports the risk; it does not rewrite user code.

The pure scan resolves source-ordered imports and direct aliases for `sklearn.pipeline.Pipeline`
and `make_pipeline`, literal step lists/tuples, named assignments and direct named `fit`,
`fit_transform` or `fit_predict` calls. It follows the actual proposed task ownership, not cell
boundaries or generated names. If construction and fitting share a task, local component use
and components exported from that task retain eligibility. If construction and fitting are
separate, even a separately loaded prototype used within the fitting task can be detached.
Direct rebinding, valueless annotations and immutable disabled/passthrough values are handled.

This detects a potential unsupported dependency on shared fitted state, not a proof that the
source succeeds or that every flagged access reads learned attributes. Caching/cloning options,
custom factories, dynamic step containers, chained calls, control-flow-dependent aliases,
nested wrappers and arbitrary object graphs are not interpreted. Absence of SA009 is not a
general alias or equivalence guarantee. No source library is imported or executed, no copy
policy is changed and the existing facts/planning/audit schemas remain unchanged. As with the
other source checks, direct low-level generation needs `source_facts` to recompute this audit.
See [ADR 0025](../decisions/0025-fitted-pipeline-alias-guard.md).

## Procedural mixed cells

The historical notebook path accepts ordinary code cells without user-defined functions. Added
on 2026-11-19, a bounded extension handles cells that combine imports, a CSV assignment and
business statements. It uses derived planning views; original NotebookFacts, cell IDs, statement
IDs, source spans and raw notebook bytes remain unchanged. No source cell is synthesized.

Shared imports and supported CSV statements are removed only from the proposed task's ownership
and source; remaining statements stay in their original cell and order, with the same AST.
Business writes, calls and boundary inputs are derived from those retained statements. An
in-cell rewrite such as df = df.dropna() receives the catalog df as an input and exports the
rewritten df; the existing renderer assigns a distinct dataset version. A promoted CSV read
must feed the first business task even if overwritten/ignored, so its load is not lost.

The independently recomputed audit requires all shared imports first, then at most one catalog
CSV load, then business tasks forming a source-ordered data chain. Imports after CSV loading,
imports/readers after business statements, reversed or independent tasks and repeated raw catalog
loads are blocked by SA008. An explicit business rewrite can feed the existing intermediate
dataset instead. CSV calls left inside a newly mixed task are rejected, including nested/dynamic
readers. Unsupported promoted options still fail SA004; no option is dropped or replaced.

This extends earlier blocked mixed cases. Previously supported unmixed plans retain their output.
Low-level planning views remain proposals; high-level planning enforces accounting, and direct
generation can pass source_facts for the same audit. Facts/planning/audit wire schemas remain 1.0.
This is not arbitrary control-flow, alias, side-effect or library analysis. See
[ADR 0024](../decisions/0024-procedural-mixed-cell-ownership.md).
