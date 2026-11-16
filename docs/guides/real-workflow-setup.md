# From function inspection to a real workflow

[Documentation index](../README.md)

Status: implemented flat candidate parameters, opt-in source-ordered joins and explicit local package preservation; broader real-project conversion remains
blocked. This guide distinguishes a declared workflow proposal from a source-derived plan.

## Keep the boundaries explicit

A real ML library can expose independent data/configuration loaders and a benchmark function
without containing an orchestration entrypoint. A passing `inspect-blocks` result identifies
functions; it does not infer their dataset graph or make their runtime objects serializable.

A first reviewed integration might propose:

```text
frozen snapshot + provenance -> load observations -> domain dataset ----+
                                                                     |
frozen scientific protocol -> load specification -> protocol object ---+-> evaluate candidate
                                                                     |          |
candidate parameters -----------------------------------------------+          v
                                                                result object + artifacts
```

Record the declared call arguments, outputs and scientific rules before authoring an adapter.
Keep the frozen protocol separate from candidate settings. File presence is not proof that a
snapshot matches the protocol's domain fingerprint. Keep training/validation/test rules and
the original application runner; do not introduce a second scientific implementation.

Schemas 1.0/1.1 still reject this independent-loader/fan-in graph. Opt-in schema 1.2 can now
preserve its source call order, with synthetic positive/negative controls. This resolves the
ordering contract only. The explicit package mode below can preserve one local import context;
a real application still needs declared dependencies, typed I/O and artifact ownership before
complete conversion/runtime claims.

## Working slice: a candidate dictionary

The current engine accepts a flat scalar-valued candidate dictionary using workflow schema 1.1.
The [workflow reference](../reference/functional-workflows.md#candidate-mappings-in-schema-11)
defines immutability, JSON types and single-use mapping constraints. Arbitrary nested settings
and dataset serializers are not inferred.

The committed [synthetic example](../../examples/functional_candidate/workflow.py) has one
explicit call, scalar numeric input, a candidate dictionary and JSON-compatible output. It
reuses the normal planner, renderer, profile and writer:

```bash
uv run notebook-to-kedro plan-workflow examples/functional_candidate/workflow.py examples/functional_candidate/workflow.json --project-root .
uv run notebook-to-kedro generate-workflow examples/functional_candidate/workflow.py examples/functional_candidate/workflow.json generated/candidate_project --project-root . --regression-contract examples/functional_candidate/regression.json
```

Use `workflow.ipynb` for the paired notebook. The example's configuration and explicit expected
numeric results are synthetic, not copied scientific logic or an oracle for a real benchmark.
Generation executes neither source nor generated tests. Install/review a generated project
before choosing to execute it; fresh installation is not established by static generation.

In VS Code, create/select local project settings, select the source and choose the existing
schema 1.1 workflow configuration. Existing inspection and file-preview commands use the same
engine contract. The interpreter must contain this engine revision; local project settings
retain schema 1.0.

## Working slice: ordered independent loaders

The [paired join example](../../examples/functional_join/workflow.py) has two independent
loaders followed by a function consuming both results. Its
[configuration](../../examples/functional_join/workflow.json) selects schema 1.2; its
[notebook](../../examples/functional_join/workflow.ipynb) and
[supplied expectations](../../examples/functional_join/regression.json) exercise the same graph.

```bash
uv run notebook-to-kedro plan-workflow examples/functional_join/workflow.py examples/functional_join/workflow.json --project-root .
uv run notebook-to-kedro generate-workflow examples/functional_join/workflow.py examples/functional_join/workflow.json generated/ordered_project --project-root . --regression-contract examples/functional_join/regression.json
```

The [source-order contract](../reference/functional-workflows.md#source-ordered-calls-in-schema-12)
explains the private ordering input and how it stays outside business function arguments and
node expectations. The first loader finishes before the second starts, and a failure stops later
calls. The fixture uses plain JSON values, not application-specific dataset/result objects.

The local real-workflow proposal now plans three calls with one explicit ordering edge in
schema 1.2. This is still an in-memory proposal rather than an existing source entrypoint or a
generated/executed real project. Placeholder JSON boundaries do not serialize domain objects.

## Working slice: preserve a local package

The [package example](../../examples/functional_package/workflow.json) selects schema 1.3 and
declares `source_package: examples/functional_package/src/example_ml`. Its selected Python
module has an explicit entrypoint; supporting modules use relative imports, an internal
dataclass and a file-relative JSON resource. The engine copies the original package bytes and
resources and imports its original module from generated wrappers:

```bash
uv run notebook-to-kedro plan-workflow examples/functional_package/src/example_ml/workflow.py examples/functional_package/workflow.json --project-root .
uv run notebook-to-kedro generate-workflow examples/functional_package/src/example_ml/workflow.py examples/functional_package/workflow.json generated/package_project --project-root . --regression-contract examples/functional_package/regression.json
```

The [package contract](../reference/functional-workflows.md#explicit-local-package-in-schema-13)
defines inventory binding, bounded files, static import checks and unsupported namespaces.
Its supplied expectations cover the pipeline; typed intermediate node expectations stay
explicit gaps. Schema 1.7 adds explicit application distribution capture for separate installation.
Source-only inspection does not infer package context from workflow settings. If a selected
module uses relative imports, review the explicit package-aware plan as well.

The read-only real-source inventory now captures the local package. The actual selected
module has no orchestration entrypoint, so package-bound planning correctly blocks. The older
in-memory proposal is not substituted for those original bytes. Review the actual entrypoint,
captured dependency declarations, selected file/result boundaries and proposed artifact destination
before an explicitly scoped integration trial. The inventory check is read-only.

## Working slice: declare a missing orchestration

Use [explicit preparation](../reference/functional-workflows.md#explicit-orchestration-preparation)
to review a call sequence before choosing persistent serializers. It uses observed functions
from one captured module and emits a new forwarding adapter, with a separate proposal manifest:

```bash
uv run notebook-to-kedro prepare-workflow examples/functional_package/src/example_ml/transforms.py examples/functional_package/preparation.json --project-root .
uv run notebook-to-kedro prepare-workflow examples/functional_package/src/example_ml/transforms.py examples/functional_package/preparation.json --project-root . --output-dir generated/prepared_package
```

The first command previews only. The second publishes a new review copy containing raw original
files plus `workflow_adapter.py`. Neither imports or executes application code. Calls must match
observed signatures and preserve explicit order, distinct outputs and single-use values. This
preparation supplies no workflow I/O configuration and keeps its status unreviewed.

The private real-source preview now declares the two loaders followed by the benchmark function.
It records three proposed calls and unchanged original package hashes, without publishing a real
package copy or executing the application. A synthesized adapter is not an existing entrypoint.
Original-source conversion still correctly rejects its missing entrypoint.

## Working slice: domain file references with sibling sidecars

Workflow schema 1.4 now accepts explicit path inputs, separately from JSON-value inputs:
see the [file-reference contract](../reference/functional-workflows.md#raw-file-path-inputs-in-schema-14).
It copies a primary file and declared sibling sidecars, then passes the staged primary path
to the original application loader. The loader still constructs and validates domain objects.
The separate protocol can also be a file reference, even when its on-disk format is JSON.

```bash
uv run notebook-to-kedro generate-workflow examples/functional_files/src/reference_ml/workflow.py examples/functional_files/workflow.json generated/file_project --project-root .
```

The synthetic fixture reads text values, a metadata sidecar and a protocol with original
application code; it is not a Parquet execution claim. Its typed intermediates retain identity
under SequentialRunner and ThreadRunner. Its final summary is explicitly JSON-compatible.
JSON regression contracts cannot yet supply file fixtures, so these are explicit missing-test
gaps rather than invented oracles. Dependencies and application execution remain separate.

A private read-only check now hashes the real snapshot, metadata sidecar and protocol as two
declared bundles. No application code or domain reader runs, and original source/data remain
unchanged. Scientific compatibility is still unverified. The real orchestration remains a
separate unreviewed proposal; its typed final result and artifact ownership are still blockers.

## Working slice: retain a domain result in memory

Workflow schema 1.5 now accepts the explicit final target `"memory"`. It retains an opaque
Python result in the same-process Kedro catalog with assign-mode identity, without JSON/pickle
coercion. The [memory-result contract](../reference/functional-workflows.md#memory-only-final-results-in-schema-15)
defines its nonpersistence and unchanged source behavior.

```bash
uv run notebook-to-kedro generate-workflow examples/functional_files/src/reference_ml/memory_workflow.py examples/functional_files/memory_workflow.json generated/memory_project --project-root .
```

The synthetic result keeps typed measurements/protocol references and has no JSON serializer.
Trusted tests recover it through the execution catalog, preserve its exact identity and show
that a newly created catalog has no saved result. Finishing a CLI process does not persist it.
An explicit JSON target still fails for a nonserializable object; no automatic fallback occurs.
Typed generated expectations remain an explicit gap rather than fabricated JSON oracles.

This provides a possible boundary for a future reviewed real integration returning its original
application result. It does not adopt the unreviewed orchestration, suppress the runner's own
artifact writes, verify dependencies or authorize a benchmark execution. The real source stays
unchanged and its original missing entrypoint continues to block conversion.

## Working slice: explicit application-owned artifact destinations

Workflow schema 1.6 can bind a declared artifact path to an exact field such as
`candidate.output`. The mapping's consuming call becomes the declared owner. The
[artifact contract](../reference/functional-workflows.md#declared-runtime-artifact-destinations-in-schema-16)
defines its narrow `artifacts/<run_name>` layout and generated policy marker.

```bash
uv run notebook-to-kedro generate-workflow examples/functional_artifacts/src/artifact_ml/file_workflow.py examples/functional_artifacts/file_workflow.json generated/artifact_project --project-root .
```

Generation publishes a project without creating its runtime artifact directory. During an
explicit run, the registered pipeline checks the selected parameter, matching working-root
policy and absence of the destination immediately before the owner. Original application code
creates the directory and writes files. Existing targets are refused; application failures and
partial files remain intact, without cleanup or retry. Direct function calls bypass this adapter;
it is not a sandbox or a concurrency lock, and earlier workflow calls retain their order/effects.

Synthetic tests combine raw-file inputs, original readers/writes and a typed memory result under
default/custom profiles and sequential/threaded runners. They separately verify failed writes,
unchanged owned contents and missing generated artifact expectations. This does not execute or
approve a scientific user workflow.

The private real configuration now proposes a new relative destination with the matching
`candidate.output` declaration. It changes only that private integration proposal, without
rewriting source or checking/creating an actual runtime directory. Original source-bound planning
still rejects the absent entrypoint. Schema 1.7 now captures the selected application's declared
metadata. Actual installation and scientific/result/artifact review remain pending before a trial.

## Working slice for application declarations

Preparation schema 1.1 can now retain the original application project while adding the proposed
adapter in its source layout. Select its pyproject and additional build/provenance/input files
explicitly. After reviewing the resulting copy, configure workflow schema 1.7 against the saved
adapter. The preparation manifest provides the relative pyproject, package and adapter paths.
Select that manifest and review file as additional application files to carry their provenance
into subsequent generation. The
[application preparation contract](../reference/functional-workflows.md#application-projects-in-preparation-schema-11)
and synthetic definition demonstrate this path.

Workflow schema 1.7 selects the original application pyproject and required additional files,
such as its lockfile. Static capture records the declared name/version, Python requirements,
dependencies, extras, scripts and raw project-file identities. Generation stages a separately
installable application under `application/`, retaining its source layout and original metadata.
The generated Kedro distribution requires that original name/version. Follow the generated
README to install both local projects, selecting optional extras explicitly. Editable installation
retains source-relative project-file lookups. The details and synthetic example are documented in
the [application distribution contract](../reference/functional-workflows.md#application-distribution-in-schema-17).

The private real proposal now selects the original pyproject and lockfile. Read-only capture
records six requirements, two extras groups, one script declaration and three project files.
The 23-file source inventory and raw input hashes match the previous observation. Original
source planning still reports its absent adopted entrypoint. The private report records pending
review and `not_run` build/resolution/execution. The application keeps its original provenance
implementation. Actual dependency installation, data/protocol compatibility and scientific
expectations require later evidence.

## Next contracts for review and durable results

Use the separate explicit provenance capture before choosing a benchmark trial. It verifies the
new publication inventory, recomputes the prepared adapter against original source and records
the original Git context, ambient execution Git and installed versions from the chosen interpreter.
The private real report now binds 29 original files to 50 published files and observes 61
installed distributions. Its original source commit differs from the containing workspace's
commit. The report retains pending review and benchmark execution status. A later trial can
reference this report when associating application outputs with their source/environment evidence.
See the [provenance contract](../reference/functional-workflows.md#original-source-and-installed-workflow-provenance).

An explicitly authorized private review copy now exercises preparation schema 1.1 and subsequent
workflow schema 1.7 generation for the selected real source. It retains the original 23 package
files plus the proposed adapter. Its plan has three calls and one ordering edge. Both local
distributions install in a dedicated environment, with metadata and all 61 installed packages
validated. Resolution uses the declared constraints, and the copied original lockfile provides
source provenance. After separate read-only authorization, original loaders verify dataset
fingerprint/version/asset against the frozen protocol. Three registered nodes, installed metadata
and the source-relative lockfile hash are also checked. Windows refused the initial NumPy 2.5.5
binary. The successful runtime uses compatible NumPy 2.5.2, SciPy 1.18.0 and scikit-learn 1.9.0,
matching versions already used by the engine tests. The application reports the containing
execution workspace's Git commit. Use the engine report's explicit source.git field for original
source attribution. Scientific/runtime expectations and benchmark execution have separate scope.

The following distinguishes the implemented input slice from proposed remaining boundaries;
it is not permission to execute a real run. Preserve application domain loaders rather than recreating
their scientific validation inside a generic dataset adapter.

| Boundary | Proposed contract and acceptance requirement |
| --- | --- |
| Snapshot and provenance | Implemented for one primary file and explicitly declared sibling sidecars: contained raw-byte hashes, preserved filenames and a staged path passed to the application loader. Nested layouts and broader fixture contracts remain future work. A copied byte hash does not establish the domain dataset fingerprint. |
| Frozen protocol | Implemented as a separate file-reference input passed to the existing protocol loader. Keep target/split/metric settings out of candidate parameters. A generic JSON dictionary is not the application's protocol object. |
| Intermediate domain objects | Use assign-mode memory datasets between calls; preserve type/reference identity. Do not infer pickle, DataFrame or JSON coercions. |
| Final domain result | Implemented explicit memory-only retention in schema 1.5, without type conversion/validation. A durable application serializer/descriptor and typed generated comparators remain future work. Do not assume a result dataclass is JSON-compatible or portable across runners/processes. |
| Artifact directory | Implemented schema 1.6 declarations for exact flat-parameter bindings under artifacts/<run_name>, checked before the consuming registered-pipeline call. No precreation, reservation, overwrite, cleanup or retry. Broader layouts, complete effects and concurrency locking remain unsupported. |
| Dependencies and provenance | Implemented schema 1.7 captures selected static distribution declarations and project files for separate application installation. Review backend inputs, lockfile/path scope, compatible requirements, optional extras and actual metadata/provenance behavior in the chosen environment. |
| Runtime evidence | Supply reviewed expectations and actual snapshot/protocol compatibility checks, then scope any validation-only execution explicitly. Keep final-test evaluation separate. |

Installation/review/durable-result requirements remain concrete inputs to later slices. Static source
preparation alone still records persistent-I/O/artifact policies as undefined; selecting an
actual workflow I/O configuration is a separate integration decision.

## Review gaps before a real trial

Keep a local, source-bound proposal with the selected functions, paths, source hashes,
configuration choices and unresolved expectations. Sharing it may disclose source and paths.
The proposal is not an executable configuration, conversion acceptance or execution consent.
Do not publish private project source or data as a reusable example.

For a workflow like the graph above, the remaining concrete gates are:

1. Use the explicit source-order mode; do not assume loader effects commute or remove its edges.
2. Select the explicit package mode where applicable; review an actual orchestration entrypoint
   and declare application dependencies, versions and any required distribution metadata.
3. Specify typed data/protocol boundaries, sidecars and reference-copy behavior.
4. Separate generated-project publication from application-owned artifact writes and require
   a new explicit artifact destination. A result dataclass is not implicitly a JSON output.
5. Check actual data/protocol compatibility and supply reviewed runtime expectations before
   an explicitly scoped trial. A tool demonstration does not authorize final-test scoring.

Existing whole-notebook pilot review and provider/execution consent requirements remain pending
and separate. Synthetic tooling tests do not approve that pilot or a user project's science.

## Proposed paired validation trial

Status: review protocol, prepared on 2026-11-16. Actual benchmark execution, the trial harness
and reusable typed/artifact comparison support remain pending. This protocol does not add a
CLI command or expand the generated JSON regression contract. Keep the concrete source paths,
hashes and trial worksheet in the ignored local integration directory.

The first trial should measure conversion fidelity for one frozen candidate. Compare direct calls
to the original application functions in the installed private copy with the generated registered
pipeline. Agreement establishes evidence for that candidate, snapshot and runtime; evaluating
predictive usefulness requires separate scientific acceptance criteria.

### Freeze before execution

Record these choices in a private trial definition before seeing benchmark results:

| Item | Required record |
| --- | --- |
| Evidence binding | Path, SHA-256 and byte size of the exact workflow-provenance.json report; generated inventory, adapter, manifest, catalog, parameters and artifact-policy identities. |
| Application inputs | Original and staged primary/sidecar/protocol byte identities, plus the already observed domain dataset fingerprint, version and asset. Preserve the frozen protocol. |
| Candidate | One estimator, strategy, validation phase and seed. Keep candidate parameters separate from target, split, feature and metric definitions. |
| Runtime | Selected interpreter and captured distribution versions. Recheck actual import locations and current metadata before execution, including the original application functions and generated registry. |
| Invocations | Direct loader -> protocol loader -> benchmark call, then the generated registered pipeline with the existing catalog and a sequential runner. Use fresh processes and exactly one invocation per path. |
| Write scope | Two distinct absent artifact destinations under private roots, plus explicit logs/result-evidence files. Preserve the generated policy's exact relative path and parameter value. |
| Controls | Comparison rules, exact metadata exclusions, timeout, attempt retention and explicit execution consent. Record missing review as pending. |

The reference uses the original installed functions directly, bypassing the proposed adapter and
generated node wrappers. Both paths consume the same staged input bytes and candidate values.
An identical relative artifact path can resolve under different working roots: a new reference
working directory and the unchanged generated project root. Do not override only the generated
output parameter, because its artifact policy requires the declared value. Neither application
destination is precreated; the application owns its creation and any partial output.

The proposed first real-source candidate uses validation, the naive estimator, one-step strategy
and seed 42. It reads the frozen snapshot and uses the application's training/validation rules.
The protocol may describe test partitions and the loader may read the full snapshot; this does
not authorize final-test scoring. Leave the protocol, fitting rules and candidate logic unchanged.
Use the application's existing local no-op tracker, with no provider calls or external tracking.

### Observable acceptance rules

Freeze zero absolute/relative tolerance for the initial same-environment deterministic comparison.
Any mismatch is retained for investigation. A later tolerance change defines a new reviewed trial;
it cannot retroactively turn the first attempt into a pass. Require finite numeric observations.

| Observable | Proposed acceptance |
| --- | --- |
| Completion and object | Each invocation completes once. The final memory result has the application's declared result type, directory, metrics and metadata; its metrics/metadata match its own saved artifacts. Capture these observations before its process ends. |
| Protocol | Saved protocol objects equal each other and the original frozen protocol as parsed JSON; record serialized byte hashes separately. |
| Metrics | Exact expected metric keys, finite values and numeric equality between paths. Independently recompute the declared metrics from each saved prediction table. The reference output is observed evidence, not a pre-existing scientific oracle. |
| Predictions | Exact ordered columns, dtypes, row count, row order, coordinates, assets, horizons, target names and values after Parquet decoding. Keep timestamps in their declared types. Compare decoded values rather than treating Parquet byte equality as semantic equivalence. |
| Scientific metadata | Equal benchmark/dataset/evaluation fingerprints, candidate identity, phase, seed, fitted-component declarations, features, horizons, targets and split summaries. Check frozen fields against the trial definition as well as against each other. |
| Provenance metadata | Compare all run metadata by default. Enumerate allowed contextual differences before execution, retain both raw values, and bind them to the engine report and observed import locations. Ambient Git is separate from original source Git. |
| Artifact inventory | Required protocol, metrics, run metadata and prediction files exist and parse. Require the declared figure files to exist and be nonempty. List and hash every observed file; unexpected or missing files require review. |

The private worksheet must enumerate actual fields and filenames for the selected application.
For the first inspected candidate, seven figures each have JSON and HTML outputs. Their existence
is required; visual equivalence and exact serialized figure equality remain unverified unless
separately implemented and checked. Record optional selector/importance artifacts explicitly as
expected or absent for the chosen candidate. Do not silently ignore them.

Metadata exclusions must be narrow. The two processes' ambient Git commit/dirty observations can
depend on their working directories, so retain and attribute them separately. Package source
hashes and installed versions should still agree when both paths import the same staged
application. Never exclude the source map merely because it contains the proposed adapter.

Before trusting a future comparator, check synthetic controls for a modified prediction, altered
metric, reordered row/column, changed dtype, missing file and changed frozen fingerprint. Every
control must fail the intended check. Such controls exercise the harness and do not approve the
real scientific run or the independent notebook pilot.

### Execution record and stop conditions

Recheck frozen source/generated/input identities, import origins, metadata and destination absence
immediately before execution. A prior provenance capture alone does not establish current runtime
state. Changes require a fresh reviewed definition and provenance record. Record containing Git
context at execution separately; preparing this worksheet can legitimately advance the engine
repository's commit after the earlier capture.

Reserve an attempt record before starting either process. Keep the definition/report digests,
exact invocations, working directories, environment controls, exit codes, durations, bounded logs,
artifact inventories and every comparison outcome. A proposed initial budget is 300 seconds per
invocation, with no automatic retry. Confirm it in the private definition. Timeout or failure stops
the pair and retains partial files. Do not delete or overwrite them to obtain a successful result;
another attempt needs fresh destinations and its own evidence and consent.

Recheck protected source/input/generated identities and installed metadata afterwards. Record
`not_run`, setup/execution failure, comparison mismatch, or matched scoped expectations distinctly.
An unimplemented comparison stays `not_checked`; it cannot contribute a passing result. A future
harness must retain failures as carefully as successes and link its result to both the frozen
trial definition and exact provenance report. Local observations are not authenticated attestation
or an operating-system effect sandbox.

The user's existing copy/generation/installation and read-only loader/provenance permissions
cover preparing the private worksheet. Next implement/check the bounded harness and present it
with the reviewed definition. Obtain explicit approval of the concrete pair and its writes as
the final step before benchmark execution. Promote comparison primitives into the shared engine
only when this evidence establishes their actual reusable contract.
