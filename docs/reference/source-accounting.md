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

Catalog relocation supports a single ordinary assignment from an earlier bound pandas import,
with exactly one positional literal local path and no reader keywords/unpacking. Compare dataset
type, copied filepath and source filepath with the current renderer's convention. Rebinding the
reader alias, reader options, remote URIs, multiple catalog claims and mixed loader/task cells
cannot silently pass. A loader kept wholly in task code remains a code statement; accounting
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

This first increment rejects unsupported standalone side effects/assertions and mixed cells.
It does not split arbitrary cells, model object identity/aliasing or all nested scopes, prove
safe import hoisting/side-effect ordering, lock changing files, validate data schemas, generate
project tests or replace behavioral comparison. See [ADR 0004](../decisions/0004-shared-engine-and-local-interface.md)
and the [roadmap](../product/roadmap.md) for the next functional-block/Python slice.
