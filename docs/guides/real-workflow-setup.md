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
explicit gaps. Dependency installation and original distribution metadata remain separate.
Source-only inspection does not infer package context from workflow settings. If a selected
module uses relative imports, review the explicit package-aware plan as well.

The read-only real-source inventory now captures the local package. The actual selected
module has no orchestration entrypoint, so package-bound planning correctly blocks. The older
in-memory proposal is not substituted for those original bytes. A reviewed entrypoint,
declared dependencies/metadata, typed data/results and artifact destinations remain required;
no real source is modified, imported, executed or generated by this inventory check.

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

## Next contract: domain file references and owned artifacts

The following is a proposed next implementation boundary, not current dataset support or
permission to execute a real run. Preserve application domain loaders rather than recreating
their scientific validation inside a generic dataset adapter.

| Boundary | Proposed contract and acceptance requirement |
| --- | --- |
| Snapshot and provenance | Explicit raw file-reference input with declared sidecars. Preserve filenames/relative layout needed by the loader, contain and hash every declared regular file, and pass a path to the existing application loader. A copied byte hash does not establish the domain dataset fingerprint. |
| Frozen protocol | Separate file-reference input passed to the existing protocol loader. Keep target/split/metric settings out of candidate parameters. A generic JSON dictionary is not the application's protocol object. |
| Intermediate domain objects | Use assign-mode memory datasets between calls; preserve type/reference identity. Do not infer pickle, DataFrame or JSON coercions. |
| Final domain result | Require an explicit memory-only result or a reviewed application serializer/descriptor. Do not assume a result dataclass is JSON-compatible. Memory-only retention would not establish persistence or runner portability. |
| Artifact directory | Declare the application-owned runtime destination separately from generated-project publication. Preserve refusal of an existing destination; never precreate, overwrite, delete or retry the application's writes. Validate how a candidate output path is bound before a runtime trial. |
| Dependencies and provenance | Declare application requirements/versions and any original distribution metadata or lockfile lookups. Copying importable source alone does not satisfy those lookups. |
| Runtime evidence | Supply reviewed expectations and actual snapshot/protocol compatibility checks, then scope any validation-only execution explicitly. Keep final-test evaluation separate. |

These requirements are now concrete inputs to the next bounded slice. Static preparation
records persistent-I/O/artifact policies as undefined until those contracts exist.

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
