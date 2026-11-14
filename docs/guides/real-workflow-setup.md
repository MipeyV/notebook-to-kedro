# From function inspection to a real workflow

[Documentation index](../README.md)

Status: implemented flat candidate-parameter slice; broader real-project conversion remains
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

This independent-loader/fan-in graph is still outside the current linear conversion contract.
Publication must remain blocked until ordering/effects, import context, typed I/O and artifact
ownership are specified and exercised. A synthetic negative fixture enforces that boundary.

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

## Review gaps before a real trial

Keep a local, source-bound proposal with the selected functions, paths, source hashes,
configuration choices and unresolved expectations. Sharing it may disclose source and paths.
The proposal is not an executable configuration, conversion acceptance or execution consent.
Do not publish private project source or data as a reusable example.

For a workflow like the graph above, the remaining concrete gates are:

1. Define ordering/effect semantics for independent loaders and their join.
2. Preserve local application imports, dependency installation and versions.
3. Specify typed data/protocol boundaries, sidecars and reference-copy behavior.
4. Separate generated-project publication from application-owned artifact writes and require
   a new explicit artifact destination. A result dataclass is not implicitly a JSON output.
5. Check actual data/protocol compatibility and supply reviewed runtime expectations before
   an explicitly scoped trial. A tool demonstration does not authorize final-test scoring.

Existing whole-notebook pilot review and provider/execution consent requirements remain pending
and separate. Synthetic tooling tests do not approve that pilot or a user project's science.
