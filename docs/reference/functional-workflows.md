# Functional workflow to Kedro

[Documentation index](../README.md)

Status: bounded E2 generation slice implemented on 2026-11-12, extended with opt-in ordered
joins/local packages on 2026-11-15 and declared shared intermediates on 2026-11-19. It converts
explicit workflows from scripts or notebook cells, with single-use data by default.
Schemas 1.0/1.1 require a linear data chain; schema 1.2 preserves source order across independent
calls and joins; schema 1.3 additionally preserves one declared Python package and schema 1.4 adds
explicit raw-file path inputs with sibling sidecars. Schemas 1.5/1.6 add explicit memory results
and owned artifact destinations. Schema 1.7 adds application distribution capture on 2026-11-16.
An optional versioned shared-data policy admits named intermediate references in source order.
General DAG inference, unrestricted fan-out and cross-module workflow discovery remain outside this slice. The first
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

The JSON configuration has exactly five fields in schemas 1.0/1.1/1.2, six in schema 1.3 and
seven in schemas 1.4/1.5 (adding `file_inputs`), eight in schema 1.6 (adding
`artifact_destinations`) and nine in schema 1.7 (adding `application_project`).
Schemas 1.2 through 1.7 additionally accept the optional closed `shared_data` policy below.
Unknown/duplicate fields are rejected. The
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
- Schema 1.0 parameters are finite JSON scalars. Schemas 1.1 through 1.7 additionally accept flat JSON
  objects with string keys and finite scalar values. Arrays, nested objects and inferred
  parameters remain unsupported. Parameters become `parameters.yml` entries and
  `params:<argument>` node inputs.
- There is exactly one configured output, matching the entrypoint's named return. Its path is
  restricted to `data/08_reporting/<lowercase_name>.json`. This is an explicit JSON serialization
  boundary, not preservation of every possible Python return type. Schema 1.5 can explicitly
  select the nonpersistent memory result described below instead.
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

Structured if/for/while, raise/pass and loop break/continue can remain inside called functions.
They are copied with the original helper signature/body AST and single final value return,
without inferred nodes or path evaluation. The [binding checker](functional-blocks.md#initial-supported-subset)
requires definite locals on normal branch paths and conservatively does not export new loop
bindings. BL104 records unknown runtime paths/counts/termination. Entrypoint if/for/while,
early/multiple returns and try/with/match retain their existing blockers. Shared references at
the orchestration boundary require the explicit policy below.
The [paired example](../../examples/functional_control_flow/project.json) supports the existing
local-operation commands and now selects an explicit schema 1.2 regression contract with 14
shipped tests: 12 unchanged positive expectations and two source exception scenarios. The earlier
positive-only regression.json remains unchanged. See the
[exception contract](generated-workflow-tests.md#explicit-exception-outcomes-in-schema-12).

In schemas 1.0/1.1, every call after the first must consume its predecessor's result. Data values can be consumed
at most once across the workflow, including within a call; scalar parameters can be reused.
Mapping parameters are also single-use across entrypoint calls, including duplicate arguments
within one call. Sharing a mutable mapping through repeated `params:` loads could change
mutation/identity behavior, so the planner rejects it. A mapping returned from its consuming
function can flow through the existing assign-mode intermediate datasets.
Without the shared-data declaration below, these restrictions reject data fan-out and aliases
at the orchestration boundary. Independent
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
and hand-edited graphs have their own behavior. Undeclared source reuse and dynamic orchestration
remain unsupported. Explicit intermediate sharing has the narrower contract below.

Schema 1.2 plans export plan schema 1.1 with `ordering.policy: source_order` and explicit
`ordering.after` edges. The generated manifest also records `ordering_inputs`, their existing
dataset, private argument and `forwarded_to_function: false`. These edges are generation
decisions, separate from observed `steps[].inputs` and function-reference facts. The renderer
checks predecessor IDs, single-output dependencies and private-argument collisions before the
shared writer publishes anything. Schemas 1.0/1.1 keep plan schema 1.0 and the linear guard.
Local operation envelopes/project settings stay schema 1.0; analysis stays schema 1.1.

See [ADR 0010](../decisions/0010-source-ordered-functional-joins.md) for the ordering decision.

## Raw-file path inputs in schema 1.4

Use schema 1.4 explicitly when the original function expects a filename rather than loaded
JSON. It inherits schema 1.3's required `source_package` and ordered-call rules. Keep `inputs`
for JSON values; declare `file_inputs` separately, even when empty. JSON/file/parameter boundary
names must be disjoint and together cover the entrypoint arguments.

```json
"file_inputs": {
  "snapshot_path": {
    "path": "data/snapshot.parquet",
    "sidecars": ["data/snapshot.metadata.json"]
  },
  "protocol_path": {"path": "protocols/study.json", "sidecars": []}
}
```

Each reference has exactly `path` and `sidecars`; unknown reader/options fields are rejected.
Paths are normalized relative POSIX paths anchored to `project_root`, without traversal,
drives or backslashes. Sidecars must be distinct siblings of the primary file, explicitly
listed with at most 16 entries. Python callers use immutable `FileReferenceInput(path, sidecars)`
pairs in `FunctionalWorkflowConfiguration.file_inputs`; exports return fresh JSON lists.

Planning checks contained regular files, rejecting links/reparse points in every component,
directories and special files. It hashes raw bytes in chunks, bounded to 256 MiB total across
all declared references. It invokes no domain loader, decoder or data library. The immutable
inventory is bound to the plan and recaptured before rendering; changed/missing files block.
Existing writer concurrency limits still apply.

The writer copies each bundle to `data/01_raw/<argument>/`, keeping the original filenames.
An assign-mode `MemoryDataset` supplies the primary relative path string as catalog data. Run
from the generated project directory, as with its other relative catalog paths. Original
application code receives that string and owns loading/validation, including sidecar reads
and domain-object construction. No generic Parquet/DataFrame/protocol coercion is introduced.
Intermediate objects retain the existing assign-mode contract. Runtime hash enforcement is
not performed; byte identities do not establish scientific dataset/protocol compatibility.

Plan/manifest schema 1.3 adds `file_inputs` inventories with `hashed_not_loaded` and
`not_verified` statuses. `file_reference_destinations` records each source/target/hash/size,
`load_policy: path_string` and `runtime_hash_validation: not_performed`. Package-aware analysis
stays schema 1.2; local operation/project-settings envelopes remain 1.0. Legacy modes retain
their original serializers and JSON-input behavior.

Try the [synthetic configuration](../../examples/functional_files/workflow.json):

```bash
uv run notebook-to-kedro plan-workflow examples/functional_files/src/reference_ml/workflow.py examples/functional_files/workflow.json --project-root .
uv run notebook-to-kedro generate-workflow examples/functional_files/src/reference_ml/workflow.py examples/functional_files/workflow.json generated/file_project --project-root .
```

Its original readers build typed measurements/protocol objects from text, a JSON sidecar and
a JSON protocol, then return an explicitly JSON-compatible summary. Tests cover default/custom
profiles, SequentialRunner/ThreadRunner, source order, type/reference identity and domain
sidecar errors. This is not a Parquet runtime compatibility claim.

Schema 1.4 final outputs require JSON compatibility; schema 1.5 also permits an explicit memory
result. Application-owned artifacts and typed final-result persistence are separate work.
Existing JSON regression contracts do not define file
fixtures and are rejected for workflows with file references; `regression-coverage.json`
records `missing_file_fixtures` and no pytest stubs are invented. See
[ADR 0013](../decisions/0013-explicit-file-reference-inputs.md) and the
[test boundary](generated-workflow-tests.md).

## Memory-only final results in schema 1.5

Select schema 1.5 and the exact output target `memory` to retain the single named result as an
opaque Python object during explicitly requested in-process Kedro execution:

```json
"outputs": {"result": "memory"}
```

Schema 1.5 inherits schema 1.4's seven required fields, including `source_package` and an explicit
`file_inputs` object (possibly empty). JSON targets under `data/08_reporting/<name>.json` remain
available. Legacy schemas still reject `memory`; unknown targets, serializers and output names
remain blocked. The output name must match the source entrypoint's final named call result.

The catalog declares `MemoryDataset` with `copy_mode: assign` and no filepath. It performs no
JSON/pickle conversion, dataclass extraction, type inference or type validation. Original function
bodies and return ASTs stay unchanged. After a caller explicitly runs a pipeline with its own
catalog, `catalog.load("result")` returns the retained object in that process. Synthetic tests
check the original type, exact result identity, internal dataset/protocol identities and mutable
member identity with SequentialRunner and ThreadRunner. Other process runners are unverified.

This result is not persisted. A new catalog or process cannot recover it; an ending `kedro run`
process creates no durable result through this boundary. Releasing/discarding the catalog follows
normal Kedro semantics. Memory mode does not suppress application side effects or approve artifact
writes. A typed result's referenced files/directories still need their own ownership contract.

Plan/manifest schema 1.4 records `result_boundary` with the dataset name, mode, persistence,
`type_validation: not_performed` and `artifact_policy: not_defined`. Memory mode records
`persistence: none`; JSON mode records `json_file`. Package-aware analysis stays schema 1.2 and
local-operation/project-settings envelopes stay 1.0. Static operations never run the pipeline
or put a business result into a JSON CLI/UI response.

```bash
uv run notebook-to-kedro plan-workflow examples/functional_files/src/reference_ml/memory_workflow.py examples/functional_files/memory_workflow.json --project-root .
uv run notebook-to-kedro generate-workflow examples/functional_files/src/reference_ml/memory_workflow.py examples/functional_files/memory_workflow.json generated/memory_project --project-root .
```

The [synthetic source](../../examples/functional_files/src/reference_ml/memory_workflow.py)
returns an application dataclass without a JSON serializer. Its
[configuration](../../examples/functional_files/memory_workflow.json) keeps input paths/sidecars
and the original domain readers. Selecting JSON for that same opaque result fails serialization
at runtime; the engine never silently switches modes after a failure.

Existing JSON regression contracts do not define typed memory-result comparisons and are
rejected for this mode. Gap snapshots record `missing_memory_result_expectations`, without
inventing tests or oracles. Schema 1.5 JSON mode with supported JSON inputs keeps existing
regressions. Durable serializers, typed comparators and application artifacts remain separate
work. See [ADR 0014](../decisions/0014-memory-only-functional-results.md).

## Declared runtime artifact destinations in schema 1.6

Schema 1.6 inherits package, file-input, memory/JSON result and ordering rules. Its eighth
required field, `artifact_destinations`, is an explicit mapping, possibly empty:

```json
"parameters": {"candidate": {"output": "artifacts/example_run", "bias": 0.5}},
"artifact_destinations": {
  "run": {"parameter": "candidate", "key": "output", "path": "artifacts/example_run"}
}
```

Each destination has exactly `parameter`, `key` and `path`. The named parameter must be a flat
mapping whose selected string value already equals the declared path. No parameter rewrite or
output-path inference occurs. Names follow the public lowercase identifier rules; paths are
restricted to `artifacts/<run_name>` with a lowercase letter followed by up to 63 lowercase
letters/digits/underscores/hyphens, excluding Windows device names. Up to eight destinations
must have distinct paths. Nested/external paths and overwrite/retry options are unsupported.
Python callers use immutable `ArtifactDestination` values in configuration pairs; exports are
fresh JSON objects. Legacy schemas reject these declarations.

Planning derives the owner from the actual single workflow call consuming the mapping. An
unused parameter cannot claim ownership. This identifies the consuming call, not proof that
the function writes only under that path. Original source functions, return ASTs and generated
business wrappers remain unchanged. A generated `ArtifactChecked` callable wraps the owning
registered pipeline node, composing with any existing source-order adapter.

Immediately before that call, the adapter checks the runtime mapping value, project policy
marker, parent directory kind and target absence. Run from the generated project directory:
the current working directory must contain the exact generated `artifact-policy.json` bytes.
A digest in the generated package binds that bounded 64 KiB runtime contract. Modified/missing
markers, changed path parameters, pre-existing targets and links/reparse points are refused
before the owner is invoked. Other earlier workflow calls still run in their original order.

Generation only publishes policy/source/configuration files. It does not inspect the original
project's runtime target or create the generated project's artifact directory. At runtime the
adapter creates no parent/target, reserves nothing, and performs no retry or cleanup. Original
application code owns its directory creation, existence check, writes and exceptions. Partial
artifacts remain after an application failure. A repeated run refuses the existing directory.
There is no lock against concurrent mutation between the check and application call.

Plan/manifest schema 1.5 records declared destinations/derived owner IDs, checks `not_run`,
`effect_completeness: not_verified` and `reservation: not_performed`. The manifest additionally
records `artifact_policy_sha256`; an empty declaration emits no runtime policy/helper files.
This is a local contract, not authenticated approval, complete effect analysis or a sandbox.
Direct business-function calls bypass the registered-pipeline adapter. Static operations never
execute application writes, and selecting this schema does not approve a benchmark run.

```bash
uv run notebook-to-kedro plan-workflow examples/functional_artifacts/src/artifact_ml/file_workflow.py examples/functional_artifacts/file_workflow.json --project-root .
uv run notebook-to-kedro generate-workflow examples/functional_artifacts/src/artifact_ml/file_workflow.py examples/functional_artifacts/file_workflow.json generated/artifact_project --project-root .
```

The trusted example combines an application raw-file reader, independent artifact writer,
source-ordered join and typed memory result. Its paired JSON-value-input
[configuration](../../examples/functional_artifacts/workflow.json) uses
[workflow.py](../../examples/functional_artifacts/src/artifact_ml/workflow.py). Tests cover both
input modes, default/custom profiles and sequential/threaded runs, callable pickling, binding/
marker drift, existing targets, links, partial writes and no cleanup/retry. Pickling alone is
not process-runner verification. JSON regression contracts do not define artifact expectations
and are rejected; gap snapshots name `missing_artifact_expectations` without invented stubs.
See [ADR 0015](../decisions/0015-declared-runtime-artifact-destinations.md).

## Application distribution in schema 1.7

Schema 1.7 inherits source ordering, flat parameters, package capture, file references,
JSON/memory results and artifact declarations. Its additional required field explicitly selects
an original application project. The full configuration is available in the
[synthetic distribution example](../../examples/functional_distribution/workflow.json).

```json
{
  "application_project": {
    "pyproject": "examples/functional_distribution/pyproject.toml",
    "files": ["application.lock"]
  }
}
```

`pyproject` is a normalized relative POSIX path from `project_root` to a `pyproject.toml`.
The selected source package must be inside its directory. `files` is an explicit list, possibly
empty, of distinct relative files from that directory. Python construction uses the immutable
`ApplicationProject(pyproject, files_tuple)` exported by the public API.

The engine reads static PEP 621 name, version, requires-python, dependencies, optional dependencies
and scripts with `tomllib`. A static name/version and static dependency declarations are required.
Requirement/version grammar and backend-specific metadata validation occur during build or
installation. The complete raw pyproject retains its other metadata, backend and tool settings.
Referenced readme and license-file resources are selected automatically. Other build/provenance
inputs require explicit selection. A 64 KiB metadata limit, a 256 MiB selected-project-file budget
and existing regular-file/link/path guards apply. Rendering recaptures all selected identities.

Generation stages `application/pyproject.toml`, selected project files and the original relative
source layout under `application/`. It records actual statement destinations in that layout.
The generated Kedro wheel includes its generated package and declares the original distribution's
exact name/version requirement. Distribution names are compared using normalized punctuation and
case, alongside the existing import-name collision checks. Local copy previews expose the
metadata/resource files and their hashes.

The generated README supplies installation commands for both projects. From the generated root,
after reviewing source metadata, build inputs and compatible environment constraints, use

```sh
python -m pip install -e ./application -e .
kedro run
```

Select application extras explicitly, such as `-e './application[tracking]'` when declared.
Editable installation keeps source-relative project-file lookups anchored in the staged project.
A regular application wheel exposes its installed metadata and packaged resources, while its
source-relative filesystem lookups depend on the installed layout. Copied lockfiles retain their
original scope and paths. Review local workspace/path sources and additional backend inputs for
the selected installation. Backend execution and dependency resolution occur during installation.

Plan/manifest schema 1.6 includes `application_distribution`, its captured file identities and
`application_distribution_sha256`. Metadata status is `static_declarations_captured`, with build
and dependency resolution initially `not_run`. Source-package inventory keeps its own original
capture statuses. Source facts, declarations and later runtime evidence have separate provenance.

Trusted synthetic tests build and install standard/editable application wheels plus the generated
wheel, then check metadata lookup, script declarations, resources, pipeline behavior, delivered
regressions and `kedro run`. Their temporary environments reuse locked development dependencies.
An editable variant checks the source-relative auxiliary-file hash. The real-source declaration
capture retains its absent adopted entrypoint and pending runtime-review snapshot. The subsequent
authorized private prepared-copy trial is described in the
[setup guide](../guides/real-workflow-setup.md#developer-harness) with its own scoped evidence.
The architectural decision is recorded in [ADR 0016](../decisions/0016-explicit-application-distributions.md).

## Explicit orchestration preparation

A missing source entrypoint still blocks faithful conversion. To declare new orchestration,
use the separate preparation operation. It previews by default and writes a new review copy
only with `--output-dir`:

```bash
uv run notebook-to-kedro prepare-workflow examples/functional_package/src/example_ml/transforms.py examples/functional_package/preparation.json --project-root .
uv run notebook-to-kedro prepare-workflow examples/functional_package/src/example_ml/transforms.py examples/functional_package/preparation.json --project-root . --output-dir generated/prepared_package
```

The [definition](../../examples/functional_package/preparation.json) is a separate schema 1.0
contract with exactly `schema_version`, `source_package`, `entrypoint`, `arguments`, `calls`
and `output`. `arguments` is an ordered list of unique public lowercase ASCII names. Each call
has exactly `function`, an `arguments` object binding source parameter names to declared/earlier
values, and one `output`. The entrypoint/output/function/argument names follow the existing
workflow identifier rules. There are at most 64 arguments, 1-64 calls and 64 bindings per call;
the UTF-8 JSON loader is bounded to 64 KiB and rejects duplicate/unknown fields.

Python callers use `WorkflowCall`, `WorkflowPreparationDefinition`,
`load_workflow_preparation_definition`, `render_workflow_preparation` and
`prepare_functional_workflow`. Definitions and nested calls use immutable tuples; exports are
fresh JSON values. The renderer returns proposed text files and raw-file copy pairs without
writing. Publication uses the shared writer, refusing existing targets, source-package overlap
and a package file already occupying `workflow_adapter.py`.

One declared regular package must contain the selected `.py` module, which must pass functional
inspection in its captured module context. Declared functions must be observed definitions;
entrypoint names cannot replace existing definitions. The engine emits new forwarding functions
that delegate by keyword to those originals, then the explicitly ordered calls. Shared wiring
validation checks exact signatures, bound names, distinct assignments, single-use values and
the final call result. All arguments are conservatively single-use here; no scalar/mapping
role or persistent boundary is inferred. Supporting modules remain opaque retained source.

The copy contains unchanged package files under `src/<original_package>`, a synthesized
`workflow_adapter.py`, `workflow-preparation.json` and `REVIEW.md`. The manifest separates
original `source_facts`/inventory from the declaration and `proposal` analysis/steps. Synthesized
instructions have their own path, hash and spans; `source_bindings` links forwarding functions
to original module/function/block IDs and AST hashes. Inventory/selected-file drift blocks
preparation. Existing filesystem concurrency limits still apply.

Status stays `unreviewed_proposal`, execution `not_run`, persistent I/O/artifact policies
`not_defined`. No catalog, workflow I/O settings, dependency declarations or test stubs are
invented. The copy is not a generated Kedro project. Review/adopt the adapter, then supply actual
input/output/dependency/artifact contracts and expectations for a later conversion. A static
proposal does not verify business behavior or execution consent. The initial operation is
API/CLI-only; local operation/project-settings schema 1.0 is unchanged.
See [ADR 0012](../decisions/0012-explicit-orchestration-preparation.md).

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
between calls. The source-ordered graph preserves call order. Catalog boundary inputs remain
single-use; declared shared intermediates can be loaded by several ordered consumers.
Output catalog entries are added after graph rendering, so a persistent final output is not
mistaken for a pre-existing catalog input and renamed as a rewrite. The shared renderer and
writer retain validation, compile preflight, profile compatibility and no-overwrite publication.

### Shared intermediate references (policy 1.0)

On source-ordered workflow schemas 1.2 through 1.7, optionally declare exactly which intermediate
values may be consumed more than once. The policy has its own version, preserving existing
workflow versions, required fields and output when this field is absent:

```json
"shared_data": {"schema_version": "1.0", "values": ["buffer"]}
```

The closed policy accepts 1 to 100 distinct lowercase public ASCII names, each at most 64
characters, stored as an immutable tuple in Python. Use
`SharedDataPolicy(("buffer",))` for direct construction. Each name must be an actual nonfinal
call output with at least two argument occurrences in the recomputed entrypoint. Declaration
of unknown, unused, singly consumed or final values, catalog inputs or parameters fails before
publication. Schemas 1.0/1.1 cannot opt in. Every undeclared data/mapping value remains single-use.
Repeated use within one call is allowed only for a declared intermediate and forwards the same
object to both original arguments. No purity or mutation classification is inferred.

The [paired example](../../examples/functional_shared_data/project.json) uses the unchanged
source pattern: create one buffer, call left then right with that buffer, then combine both
results. Its original identity/order assertions remain inside the business function. The graph
adds the existing ordering-only edge from left to right and uses assign-mode intermediate
datasets throughout. Business wrapper signatures, source ASTs, mutation methods, scalar parameter
handling and failure propagation remain unchanged. No copies, serialization or automatic retries
are inserted between calls. Full registered pipelines are exercised with SequentialRunner and
ThreadRunner. This is a single-process contract; process runners, partial pipeline selection,
manually changed graphs/catalogs and concurrent external mutation are not covered.

Plans/manifests with this opt-in use plan schema 1.7 and a `data_sharing` section containing the
policy, assign mode, execution scope, producer and ordered consumer step/argument bindings.
`runtime_validation` remains `not_run`. Analysis facts, workflow configuration versions and
local-operation envelopes remain separate. The existing settings file, API/CLI and local preview/
generation compose the policy; orchestration preparation retains its stricter single-use contract.

The example delivers three original pipeline expectations and one explicitly supplied constructor
node expectation (four tests). JSON cannot encode shared identity between separate node arguments;
the remaining node-oracle gaps stay explicit rather than inventing aliased fixtures. The full
pipeline preserves the source assertions, while repository runtime checks additionally verify
reference identity, mutation order and stop-on-error under both supported runners. See
[ADR 0023](../decisions/0023-explicit-ordered-shared-data.md).

## Application projects in preparation schema 1.1

Preparation schema 1.1 adds a required `application_project` field using the same
`ApplicationProject` selection as workflow schema 1.7. Its pyproject is relative to `project_root`
and its explicit `files` list is relative to the pyproject directory. The
[synthetic preparation definition](../../examples/functional_distribution/preparation.json)
selects original metadata, a provenance fixture and the input needed for subsequent conversion.

```sh
notebook-to-kedro prepare-workflow examples/functional_distribution/src/distribution_ml/workflow.py examples/functional_distribution/preparation.json --project-root .
notebook-to-kedro prepare-workflow examples/functional_distribution/src/distribution_ml/workflow.py examples/functional_distribution/preparation.json --project-root . --output-dir generated/prepared_distribution
```

The new review copy is the selected application project. It contains the original pyproject,
readme/license resources, selected additional files and source package in its original relative
layout. For example, `lib/package` retains that path. The new adapter sits inside the package.
Selected project files already captured in the source package are copied once. Target collisions
with `workflow_adapter.py`, `REVIEW.md` or `workflow-preparation.json` block publication.

Preparation manifest schema 1.1 includes original `application_distribution` declarations and
their digest, alongside source facts, call declarations and synthesized adapter facts. Its
`prepared_application` object gives pyproject/source-package/adapter paths relative to the review
copy. Project-file and source inventories are recaptured before publication. Review status starts
as `unreviewed_proposal`, with execution/build/resolution `not_run`. Persistent I/O and artifact
policy await an explicit conversion configuration.

To convert the prepared application, use the new adapter as the actual source and configure
workflow schema 1.7 relative to that copy. Select `pyproject.toml`, the prepared package path and
explicit inputs, parameters, outputs and artifact settings. Select the preparation manifest and
`REVIEW.md` as additional application files to carry the original/proposed provenance into the
generated project's `application/` directory. Follow generated installation instructions for
both local projects. Adopting the proposed orchestration and approving runtime expectations are
separate review decisions. The decision is recorded in
[ADR 0017](../decisions/0017-application-aware-workflow-preparation.md).

## Original-source and installed-workflow provenance

Application-aware generation now includes `generation-inventory.json` schema 1.0. It records
every published text/copied file's SHA-256, byte size and origin, excluding the inventory itself.
The existing workflow schemas retain their versions. Regenerate older application projects to
obtain this publication witness before capturing provenance.

Capture provenance explicitly from the original source root and the chosen installed environment.
Use a workflow configuration that selects the original package, pyproject and input files.
Its entrypoint can still be absent in that original module when a separately prepared adapter
supplies orchestration. The operation recomputes the saved preparation and verifies the adapter
against its original declaration and source facts.

```sh
notebook-to-kedro generate-workflow examples/functional_distribution/src/distribution_ml/workflow.py examples/functional_distribution/workflow.json generated/distribution_project --project-root .
```

After installing both local projects as described in the generated README, choose that
environment's interpreter and create a new evidence directory.

```sh
notebook-to-kedro capture-workflow-provenance examples/functional_distribution/src/distribution_ml/workflow.py examples/functional_distribution/workflow.json generated/distribution_project generated/distribution_provenance --project-root . --python /path/to/installed/environment/python
```

The same entrypoint is available through `python -m notebook_to_kedro.cli`. Python callers use
`capture_workflow_provenance(source, configuration, generated_project, output_path, *,
project_root, python_executable)`, exported by the public API.

The new `workflow-provenance.json` schema 1.0 records the original Git commit and clean/dirty
status, selected package/application identities, verified original-to-generated copy bindings
and the complete listed publication inventory. It also records the chosen interpreter and all
observed distribution names/versions. Exactly one installed distribution must identify each
original/generated name. Declared and observed versions are retained together, including any
normalization difference. Package versions come from metadata observed in that interpreter.
Runtime import/file selection has a separate validation scope.

The report's `source.git` describes the explicit original root. `execution_directory_git` describes
the generated working directory or records its unavailable status. Git status includes normal
untracked entries and ignores submodule inspection. Original file hashes retain their own
identity alongside that Git observation. Inherited Git environment overrides are cleared and
fsmonitor hooks and optional locks are disabled for these read operations.

Source/package/project/input drift, changed publication bytes and inconsistent prepared bindings
block report publication. All selected identities are recaptured after interpreter observation.
The shared writer requires a new contained report destination outside the protected package and
generated project. Git probes use 15-second timeouts and the metadata probe 30 seconds. Reads of
on-disk JSON evidence are bounded to 16 MiB per file. Capture verifies listed files, with
post-generation additions and concurrent filesystem mutation beyond the final recapture remaining
outside that snapshot.

The report records pending review and `benchmark_execution` as `not_run`. A separately scoped
trial can reference this evidence when comparing application and Kedro outputs. Original-source
Git attribution then has an explicit reference even when application code reads ambient Git.
The decision is recorded in [ADR 0018](../decisions/0018-explicit-workflow-provenance.md).

The [proposed paired validation protocol](../guides/real-workflow-setup.md#proposed-paired-validation-trial)
defines how a private trial can bind exact provenance/definition bytes to direct application and
registered-pipeline observations, with explicit metric/table/artifact checks and retained failures.
Its worksheet is preparation evidence. A separate developer script now checks installed synthetic
pairs and the real runtime preflight. One explicitly reviewed/authorized private real pair now
matches its implemented scoped expectations, with detailed results kept locally. The existing
generated JSON regression contract retains its supported boundaries and no runtime operation is added.

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
dynamic orchestration branching, unrestricted data sharing, richer datasets, dependency inference and broader ML workflows need additional
contracts and behavioral cases. The existing whole-notebook pilot's human review remains pending.

The package fixture checks relative imports, an internal dataclass and file-relative JSON
resources with default/custom profiles. Pipeline-only expectations pass and detect changed
resource bytes; absent typed node oracles remain explicit gaps. An offline Hatchling build
and isolated execution from an unpacked wheel prove source-free package/resource inclusion,
separately from fresh dependency installation. No real user project is executed by this evidence.
