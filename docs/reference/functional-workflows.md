# Functional workflow to Kedro

[Documentation index](../README.md)

Status: bounded E2 generation slice implemented on 2026-11-12, extended with opt-in ordered
joins and explicit local package preservation on 2026-11-15. It converts explicit single-use workflows from scripts or notebook cells.
Schemas 1.0/1.1 require a linear data chain; schema 1.2 preserves source order across independent
calls and joins; schema 1.3 additionally preserves one declared Python package. General DAG inference,
data fan-out and cross-module workflow discovery remain outside this slice. The first
[generated-test increment](generated-workflow-tests.md) now optionally delivers pytest
regressions from explicit expectations. A separate opt-in trusted-example bootstrap check
now installs generated wheels and runs shipped tests plus the Kedro CLI in fresh environments.

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

The JSON configuration has exactly five fields in schemas 1.0/1.1/1.2 and six in schema 1.3;
unknown/duplicate fields are rejected. The
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
- Schema 1.0 parameters are finite JSON scalars. Schemas 1.1/1.2/1.3 additionally accept flat JSON
  objects with string keys and finite scalar values. Arrays, nested objects and inferred
  parameters remain unsupported. Parameters become `parameters.yml` entries and
  `params:<argument>` node inputs.
- There is exactly one configured output, matching the entrypoint's named return. Its path is
  restricted to `data/08_reporting/<lowercase_name>.json`. This is an explicit JSON serialization
  boundary, not preservation of every possible Python return type.
- Catalog and parameter configuration are rendered as quoted JSON, which is valid YAML.
  Dataset formats/options, credential injection and inferred dependencies are not configurable
  in this first schema. The generated dependency declarations reuse the existing Kedro scaffold.

### Candidate mappings in schema 1.1

Use schema 1.1 explicitly for a candidate/options dictionary. For example:

```json
{
  "schema_version": "1.1",
  "entrypoint": "workflow",
  "inputs": {"values": "examples/functional_candidate/input.json"},
  "parameters": {"candidate": {"name": "baseline", "seed": 42, "phase": "validation"}},
  "outputs": {"total": "data/08_reporting/total.json"}
}
```

This shows the boundary shape, not business logic for those keys. The complete synthetic
[script](../../examples/functional_candidate/workflow.py),
[notebook](../../examples/functional_candidate/workflow.ipynb) and
[configuration](../../examples/functional_candidate/workflow.json) define their own explicit
numeric behavior and [expectations](../../examples/functional_candidate/regression.json).

`FunctionalWorkflowConfiguration.from_dict` copies each flat object into immutable pairs.
Direct construction uses `(("candidate", (("name", "baseline"), ("seed", 42))),)` for the
`parameters` field; `()` as a parameter value represents an empty object, not an array.
`parameter_values()` and `to_dict()` return fresh ordinary JSON objects. Repeated mapping
keys, mutable direct values, non-finite/non-JSON values and non-scalar contents are rejected.
The existing 64 KiB loader limit and duplicate-field checks apply inside mappings as well.

Schema 1.0 remains scalar-only. Analysis schema 1.1, workflow configuration schemas 1.0/1.1/1.2 and
local-operation/project-settings schema 1.0 are independent contracts. A candidate mapping
does not establish that a string path is contained, a phase is scientifically authorized or an
application dependency is available. Those remain application/boundary responsibilities.

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

Called functions and their helpers can return expressions directly, for example
`return values * scale` or `return math.fabs(prepared)`. Those original return ASTs stay in
the relocated module without introducing a temporary assignment or evaluating the expression
during generation. Call order, short-circuit evaluation and exception behavior remain in the
original Python function. The wrapper's dataset name comes from the explicit entrypoint
assignment, not from a fabricated return name. The entrypoint itself still requires a named
final call result; a direct `return summarize(prepared)` there needs a separate wiring extension.

In schemas 1.0/1.1, every call after the first must consume its predecessor's result. Data values can be consumed
at most once across the workflow, including within a call; scalar parameters can be reused.
Mapping parameters are also single-use across entrypoint calls, including duplicate arguments
within one call. Sharing a mutable mapping through repeated `params:` loads could change
mutation/identity behavior, so the planner rejects it. A mapping returned from its consuming
function can flow through the existing assign-mode intermediate datasets.
These restrictions reject data fan-out and aliases at the orchestration boundary. Independent
calls require the explicit schema 1.2 mode below. Module-identity globals such as `__name__` are rejected.
Unused function definitions and imports remain in the relocated module, rather than disappearing.
Unknown dependency availability, library effects, ambient notebook state and runtime errors are
not proven by static acceptance. Imports execute later when the generated project is run.

### Source-ordered calls in schema 1.2

Set `schema_version` to `1.2` explicitly to admit independent calls while retaining source
sequencing. All other entrypoint, argument, single-assignment, parameter and I/O guards apply:

```python
def workflow(raw_values, raw_specification, candidate):
    observations = load_values(raw_values)
    specification = load_specification(raw_specification)
    total = evaluate(observations, specification, candidate)
    return total
```

The paired [script](../../examples/functional_join/workflow.py),
[notebook](../../examples/functional_join/workflow.ipynb),
[configuration](../../examples/functional_join/workflow.json) and
[expectations](../../examples/functional_join/regression.json) exercise this synthetic join.
Neither independence nor commutative effects are inferred. The first loader must finish before
the second starts, and both finish before the join. If a call raises, later calls do not start;
the engine adds no retries. An unused assigned result does not remove its call.

`plan.order_after` records adjacent step-ID pairs that lack a natural data dependency. The
renderer passes the preceding result through a private `_ntk_after` input to an importable
`_AfterPrevious` callable in the generated pipeline module. It ignores that argument and calls
the unchanged business wrapper with only its original inputs. Ordering uses the existing
assign-mode memory dataset; it does not invent a dataset, copy/serialize the object or alter
the business return. Old and naturally linear pipelines need no adapter. Original functions
and business node signatures remain unchanged, including for generated standalone node tests.

The complete registered pipeline is ordered even with a runner capable of concurrent execution.
Trusted tests check SequentialRunner and ThreadRunner plus an adapter pickle round-trip;
this is not a claim that every process runner/deployment is verified. Partial pipeline selection
and hand-edited graphs have their own behavior. Source reuse/fan-out and dynamic control flow
remain unsupported.

Schema 1.2 plans export plan schema 1.1 with `ordering.policy: source_order` and explicit
`ordering.after` edges. The generated manifest also records `ordering_inputs`, their existing
dataset, private argument and `forwarded_to_function: false`. These edges are generation
decisions, separate from observed `steps[].inputs` and function-reference facts. The renderer
checks predecessor IDs, single-output dependencies and private-argument collisions before the
shared writer publishes anything. Schemas 1.0/1.1 keep plan schema 1.0 and the linear guard.
Local operation envelopes/project settings stay schema 1.0; analysis stays schema 1.1.

See [ADR 0010](../decisions/0010-source-ordered-functional-joins.md) for the ordering decision.

## Rendering, identity and source accounting

### Explicit local package in schema 1.3

Schema 1.3 requires a sixth field, `source_package`, naming one regular package directory
relative to `project_root`. It inherits schema 1.2 ordering and parameter rules. For example:

```json
{
  "schema_version": "1.3",
  "entrypoint": "workflow",
  "inputs": {"values": "examples/functional_package/input.json"},
  "parameters": {"scale": 2.0},
  "outputs": {"total": "data/08_reporting/total.json"},
  "source_package": "examples/functional_package/src/example_ml"
}
```

Use the [selected module](../../examples/functional_package/src/example_ml/workflow.py) and
[configuration](../../examples/functional_package/workflow.json) together:

```bash
uv run notebook-to-kedro plan-workflow examples/functional_package/src/example_ml/workflow.py examples/functional_package/workflow.json --project-root .
uv run notebook-to-kedro generate-workflow examples/functional_package/src/example_ml/workflow.py examples/functional_package/workflow.json generated/package_project --project-root . --regression-contract examples/functional_package/regression.json
```

The selected source must be one `.py` file inside that package. Paths must be normalized,
contained relative POSIX paths, without traversal, drives or backslashes. Root and Python
subpackage directories need `__init__.py`; namespace packages are unsupported. Module/package
names must be ASCII Python identifiers. The root name must be public and cannot shadow a
standard-library/Kedro namespace or collide with the generated package name.

Capture inventories every regular file, including resources, with raw-byte hashes/sizes and
Python AST hashes. Limits are 256 files, 16 MiB total, 1 MiB per Python file and 4 MiB per
resource. `__pycache__` directories are excluded explicitly and recorded. Links, reparse points,
special files and compiled `.pyc/.pyo/.pyd/.so/.dll` files outside excluded caches are rejected.
Every Python file is parsed and compiled without import or execution. Syntactic local import
base-module references must name captured modules; relative references cannot escape the root.
Imported symbols, dynamic imports and external dependency availability are not established.

Only the selected workflow module receives functional supported-subset analysis. Supporting
modules/resources are retained as opaque source, not recursively converted into nodes. The
planner binds the selected document hash and module context to the inventory; rendering
recaptures it and rejects changed/added files. There is no filesystem lock against concurrent
changes. Source-only `inspect-blocks` and `project inspect` stay context-free: relative imports
can block that inspection while explicit package-aware `plan-workflow` accepts their context.

The writer copies all captured bytes to `src/<original_package>/...`, retaining encodings,
comments and resources. Generated wrappers import the original selected module; no
`workflow_source.py` is emitted. The wheel includes both the generated and original packages.
Its environment must accommodate ownership of that original import namespace. Root-level
distribution metadata, lockfiles and build configuration outside the package are not
reconstructed. Calls relying on the original distribution version or external files can
therefore still fail. External imports are module references, not inferred distribution names,
requirements or versions; install required application dependencies separately.

Package-aware analysis uses schema 1.2 with `package_module`; its plan/manifest uses schema 1.2
with inventory schema 1.0, `source_package_sha256`, `compiled_not_executed`, `not_inferred` and
`not_reconstructed` statuses. Each selected statement points to the original copied module.
Legacy analysis/plan serialization remains unchanged without package context, as do local
operation/project-settings schema 1.0. See [ADR 0011](../decisions/0011-explicit-source-package-context.md).

### Relocation without package context

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
The paired [expression-return script](../../examples/functional_workflow/expression_returns.py)
and [notebook](../../examples/functional_workflow/expression_returns.ipynb) reuse `workflow.json`
and `regression.json`. They check direct arithmetic/library-call returns, unchanged source ASTs,
the same runtime results and shipped pytest node/pipeline expectations for both profiles.
A separate mutable-list fixture checks receiver identity and an internal helper executing once
inside its owning node, including a direct helper-call return. Negative tests block unsupported
return constructs, wiring, drift, source contexts and I/O
configuration before publication. This is bounded fixture evidence, not arbitrary-code equivalence.

The schema 1.2 join fixture also checks both source formats, default/custom profiles and two
explicit numeric cases with SequentialRunner and ThreadRunner. Traces require each call once
in source order and preserve loader-result identity at the join. First/second-loader failures
stop later calls without retries. Removing the order dependency is a negative control that
permits a forbidden concurrent loader start. The generated callable survives a pickle round-trip;
this is separate from process-runner verification. Shipped pipeline/business-node tests pass
and detect an arithmetic change, without requiring ordering inputs in node expectations.

The first E3 increment now supplies explicit JSON contracts and tests delivered with generated
projects, followed by a separate trusted-example fresh dependency bootstrap check. General
control-flow branching, data fan-out, richer datasets, dependency inference and broader ML workflows need additional
contracts and behavioral cases. The existing whole-notebook pilot's human review remains pending.

The package fixture checks relative imports, an internal dataclass and file-relative JSON
resources with default/custom profiles. Pipeline-only expectations pass and detect changed
resource bytes; absent typed node oracles remain explicit gaps. An offline Hatchling build
and isolated execution from an unpacked wheel prove source-free package/resource inclusion,
separately from fresh dependency installation. No real user project is executed by this evidence.
