# Functional workflow to Kedro

[Documentation index](../README.md)

Status: bounded E2 generation slice implemented on 2026-11-12. It converts an explicit,
single-use linear function workflow from a script or physical notebook cells. General DAGs,
multi-file projects remain outside this slice. The first
[generated-test increment](generated-workflow-tests.md) now optionally delivers pytest
regressions from explicit expectations; fresh dependency bootstrap remains outstanding.

## Review and generate

```bash
uv run notebook-to-kedro plan-workflow examples/functional_workflow/workflow.py examples/functional_workflow/workflow.json --project-root .
uv run notebook-to-kedro generate-workflow examples/functional_workflow/workflow.py examples/functional_workflow/workflow.json generated/functional_project --project-root .
```

Use the paired `workflow.ipynb` as the first argument for notebook input. Both commands are
deterministic and do not execute source or import its dependencies. Generation creates a new
destination, compiles Python and uses the existing private-staging writer; it never runs Kedro.
Review the generated project and install its declared dependencies before running it yourself.
Fresh-environment installation is not established by these checks.

```python
from notebook_to_kedro import (
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    plan_functional_workflow_path,
)

config = load_functional_workflow_configuration("examples/functional_workflow/workflow.json")
plan = plan_functional_workflow_path("examples/functional_workflow/workflow.py", config)
print(plan.to_json())
generate_functional_kedro_project(
    "examples/functional_workflow/workflow.py", config, "generated/functional_project"
)
```

`generate-workflow` also accepts `--package-name` and `--architecture-profile`. The Python API
accepts a validated `KedroArchitectureProfile`. Existing pipeline names and function/node prefixes
apply to generated wrappers; original functions keep their names and bodies in a separate module.
The old `plan`/`generate` notebook operations retain their existing contract.

## Explicit boundaries

The JSON configuration has exactly five fields; unknown/duplicate fields are rejected. The
file is bounded to 64 KiB. The same immutable configuration validates direct Python construction.

```json
{
  "schema_version": "1.0",
  "entrypoint": "workflow",
  "inputs": {"values": "examples/functional_workflow/input.json"},
  "parameters": {"scale": 2.0},
  "outputs": {"total": "data/08_reporting/total.json"}
}
```

- Entrypoint and boundary names are public lowercase ASCII Python identifiers. Kedro's
  reserved `parameters` dataset name is rejected for boundaries and intermediate results.
- Inputs and parameters are disjoint and cover the entrypoint signature exactly. Input paths
  are resolved relative to `project_root` (the current directory by default), not the config
  file. They must resolve to contained `.json` files. The writer checks existence before copying
  them to `data/01_raw/<argument>.json`. Input JSON contents/schema are not validated statically.
- Parameters are finite JSON scalars; nested values and inferred parameters are unsupported.
  They become `parameters.yml` entries and `params:<argument>` node inputs.
- There is exactly one configured output, matching the entrypoint's named return. Its path is
  restricted to `data/08_reporting/<lowercase_name>.json`. This is an explicit JSON serialization
  boundary, not preservation of every possible Python return type.
- Catalog and parameter configuration are rendered as quoted JSON, which is valid YAML.
  Dataset formats/options, credential injection and inferred dependencies are not configurable
  in this first schema. The generated dependency declarations reuse the existing Kedro scaffold.

## Workflow shape and ordering

```python
def workflow(values, scale):
    prepared = prepare_values(values, scale)
    total = summarize(prepared)
    return total
```

Full [functional inspection](functional-blocks.md) must pass first. The planner recomputes the
analysis from captured units and rejects stale/tampered facts. After an optional docstring,
every entrypoint statement before the final return must assign one direct module-function call
to one new public ASCII name. Arguments must be bound names, positional or explicit keywords,
and match the called function signature. Expressions, literals, expansion, extra assertions,
reassignments, tuple targets and passthrough/earlier-result returns block conversion.

Every call after the first must consume its predecessor's result. Data values can be consumed
at most once across the workflow, including within a call; scalar parameters can be reused.
These restrictions reject fan-out, aliases at the orchestration boundary and independent branches
instead of silently reordering calls. Module-identity globals such as `__name__` are rejected.
Unused function definitions and imports remain in the relocated module, rather than disappearing.
Unknown dependency availability, library effects, ambient notebook state and runtime errors are
not proven by static acceptance. Imports execute later when the generated project is run.

## Rendering, identity and source accounting

Only entrypoint call statements become wrappers/nodes. Internal helper calls remain inside the
original functions. The entrypoint definition is retained but is not also run as a node. All
original top-level instruction ASTs are relocated into `src/<package>/workflow_source.py`, in
order, with Python AST normalization. Normalization removes encoding cookies and comments from
that executable module; original decoded source, comments and document/text hashes remain in
`functional-workflow.json`. This avoids writing UTF-8 bytes under an obsolete encoding cookie.
Combined notebook compilation can still fail, for example for a late future import; publication
is refused in that case. The initial inspection loader's provenance limitations still apply.

`functional-workflow.json` records the complete inspection, configuration, step source/spans,
profile identity and a module destination for every parsed statement. It is a recomputed local
review record, not authenticated evidence or execution consent. No Python file is represented
as invented notebook cells. A private `ConversionPlan` adapter reuses rendering; its legacy
`notebook_path` slot carries the source path, and Python tasks have empty `source_cell_ids`.
It is not a new notebook-facts schema or a bypass of the old notebook source-accounting guard.

Intermediate datasets use `MemoryDataset(copy_mode="assign")` to preserve the object passed
between calls. The linear graph preserves call order; each input dataset is loaded at most once.
Output catalog entries are added after graph rendering, so a persistent final output is not
mistaken for a pre-existing catalog input and renamed as a rewrite. The shared renderer and
writer retain validation, compile preflight, profile compatibility and no-overwrite publication.

## Evidence and next work

Trusted tests execute the paired committed fixtures and generated pipelines through real Kedro
and JSON catalog loading/saving. Three hand-specified numeric cases run for both source formats
and default/custom profiles. Call counters require exactly two orchestration calls in order.
A separate mutable-list fixture checks receiver identity and an internal helper executing once
inside its owning node. Negative tests block unsupported wiring, drift, source contexts and I/O
configuration before publication. This is bounded fixture evidence, not arbitrary-code equivalence.

The first E3 increment now supplies explicit JSON contracts and tests delivered with generated
projects; fresh dependency bootstrap remains next. General
branching, richer datasets, dependency inference and broader ML workflows need additional
contracts and behavioral cases. The existing whole-notebook pilot's human review remains pending.
