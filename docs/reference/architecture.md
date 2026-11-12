# Architecture

[Documentation index](../README.md)

Status: implementation boundaries reviewed on 2026-11-13. The
[proposed evolution](#proposed-evolution) is separate from current capabilities.

## Objective

Notebook to Kedro is designed as a staged compiler assisted by an optional semantic planner:

```text
Notebook source
    → deterministic loading and static analysis
    → NotebookFacts
    → optional semantic planning
    → ConversionPlan
    → deterministic validation
    → Kedro generation
    → generated project validation
```

Each boundary has a typed contract. Source facts, semantic inferences, and accepted transformations must never be mixed in the same model.

A separate [functional inspection path](functional-blocks.md) now accepts a `.py` module or real
notebook code cells: source adapters -> `SourceUnit` -> pure analysis -> `FunctionalAnalysis`.
It records explicit function interfaces, reference edges, source spans and blockers without
execution or framework imports. Small AST primitives are shared with notebook analysis.
Inspection remains independent of generation, as recorded in
[ADR 0005](../decisions/0005-explicit-functional-block-inspection.md). A separate
[functional workflow adapter](functional-workflows.md) now recomputes facts, validates explicit
linear wiring and adapts calls to the shared Kedro renderer, profiles and writer. Original
instruction ASTs live in a relocated module with a source manifest; Python tasks do not invent
notebook cells. [ADR 0006](../decisions/0006-linear-functional-workflow-generation.md) records
ordering, identity and bounded I/O decisions. The old notebook conversion contracts are unchanged.

An optional [regression contract](generated-workflow-tests.md) now renders standalone pytest
node/pipeline tests and a gap snapshot before the same publication boundary. It never derives
an oracle by execution or imports application code during generation. Expectations, generation
status and later execution stay distinct; [ADR 0007](../decisions/0007-explicit-generated-regression-tests.md)
records this first E3 slice. Fresh-environment bootstrap remains future work.

## Design rules

- Notebook code is never executed by the static analyzer.
- The deterministic core has no dependency on Kedro or an LLM SDK.
- `NotebookFacts` contains observations only.
- `ConversionPlan` contains proposed semantic decisions and their evidence.
- Only a validated conversion plan may reach a generator.
- Generated files remain traceable to source cells and statements.
- Unsupported or ambiguous behavior is reported explicitly.
- Provider-specific integrations remain optional and replaceable.
- Filesystem writes protect existing destinations by default.

## Current source layout

Selected files showing implemented responsibilities (not an exhaustive file inventory):

```text
src/notebook_to_kedro/
├── __init__.py
├── api.py
├── exceptions.py
├── cli.py
├── reporting.py
├── notebook/
│   ├── __init__.py
│   ├── loader.py
│   └── models.py
├── analysis/
│   ├── __init__.py
│   ├── ast_analyzer.py
│   └── dependencies.py
├── ir/
│   ├── __init__.py
│   ├── facts.py
│   ├── plan.py
│   └── serialization.py
├── semantic/
│   ├── __init__.py
│   ├── planner.py
│   ├── protocols.py
│   ├── contracts.py
│   ├── hybrid.py
│   ├── orchestration.py
│   ├── ollama.py
│   ├── source_accounting.py
│   └── validation.py
├── generation/
│   ├── writer.py
│   ├── parameters.py
│   ├── code/
│   │   ├── contracts.py
│   │   ├── assembly.py
│   │   ├── validation.py
│   │   └── service.py
│   └── kedro/
│       ├── generator.py
│       └── profiles.py
└── evaluation/
    ├── behavioral_comparison.py
    ├── behavioral_execution.py
    ├── response_capture.py
    ├── notebook_body.py
    ├── notebook_execution.py
    └── notebook_campaign.py
```

Directories are introduced only when their first implementation is added. Empty architectural placeholders are avoided.

## Public API

The package root exposes a small conversion API:

```python
from notebook_to_kedro import (
    analyze_notebook_path,
    generate_kedro_project,
    plan_notebook_path,
    render_conversion_report,
    validate_conversion_plan,
)

facts = analyze_notebook_path("notebooks/model.ipynb")
plan = plan_notebook_path("notebooks/model.ipynb")
report = render_conversion_report(plan)
validate_conversion_plan(plan)
created_files = generate_kedro_project(plan, "generated/model_project")
```

Current command-line entrypoints:

```bash
notebook-to-kedro plan notebooks/model.ipynb
notebook-to-kedro generate notebooks/model.ipynb generated/model_project
```

There is no package-root `analyze` or `convert` function. Such convenience APIs remain
historical proposals in the original overview. Explicit plan validation is useful for
review; the generator also enforces it itself and reports failures as `ProjectGenerationError`.

`api.py` orchestrates the use cases. It must not contain AST traversal, prompt construction, or template-rendering logic.

## Components

### Notebook loading

`notebook/` owns the Jupyter boundary:

- validate the path and notebook format;
- load through `nbformat`;
- detect the declared language;
- preserve physical cell order and relevant metadata;
- normalize source into internal notebook models.

It does not perform semantic or AST analysis.

### Static analysis

`analysis/` is the deterministic frontend:

- parse Python code with the standard-library AST;
- discover imports, declarations, reads, and writes;
- model scopes and free variables;
- record syntactic calls without importing their packages;
- identify possible mutations and side effects;
- resolve cross-cell name dependencies;
- emit stable diagnostic codes.

Static analysis describes name flow. It does not claim runtime object identity or business intent.

### Intermediate representation

`ir/` owns the domain contracts.

`NotebookFacts` is immutable source evidence:

```text
cells
statements
imports
calls
symbols
dependencies
diagnostics
```

`ConversionPlan` is a separate semantic proposal:

```text
candidate nodes
source fragments
proposed inputs and outputs
parameters
conversion diagnostics
blocking diagnostic codes
schema and planner versions
```

Serialization must be deterministic and versioned. DataFrames may be exposed as inspection views but are not canonical storage.

`NotebookFacts` has canonical JSON round trips. `ConversionPlan` is currently a frozen
notebook/Kedro-oriented dataclass; a general project specification, profile identity and
shared review/readiness model are not implemented. Experimental evaluation contracts track
their own explicit review and evidence status rather than adding those fields to the plan.

### Semantic planning

`semantic/` interprets facts and proposes node boundaries. It depends on a provider-neutral protocol:

```python
class SemanticPlanner(Protocol):
    def create_plan(self, facts: NotebookFacts) -> ConversionPlan: ...
```

`DeterministicSemanticPlanner` is the default implementation and preserves the V1 planning rules.
The public Python API accepts a `PlannerMode`, a supported mode name, or any compatible injected
`SemanticPlanner`. Both CLI commands expose the same explicit planner selection. Hybrid mode builds
a loopback-only Ollama provider from a required local model name and optional URL and timeout;
provider failures remain subject to deterministic fallback.

The semantic layer may propose but cannot silently override static evidence.

The versioned provider exchange is defined in
[`semantic-planning-contract.md`](semantic-planning-contract.md). Requests contain canonical
`NotebookFacts` and a projection of the deterministic baseline plan. Responses contain only
structured task suggestions; provider and model metadata are recorded independently by the
orchestrator. Suggestions must preserve the complete baseline statement set and can reference
only known source cells, statements, interfaces, and parameters before they can be considered for
conversion into a plan.

Provider transports implement `SemanticPlanningProvider` and return raw JSON. Prompt rendering,
strict parsing, static cross-validation, trace creation, and deterministic fallback are owned by
the semantic orchestration layer. Expected provider failures fall back to the V1 plan; unexpected
programming errors remain visible. The in-process fake provider tests this flow without network
access or nondeterminism.

The first real transport is the loopback-only Ollama adapter documented in
[`ollama-provider.md`](../guides/ollama-provider.md). It uses the native `/api/chat` endpoint with a JSON
Schema, non-streaming output, and temperature zero. It has no provider SDK dependency, cannot
target a remote host, and rejects known cloud-model tags. Strict isolation also requires disabling
Ollama cloud features on the local server. Direct cloud integration remains outside this adapter
and requires a separate consent and credential policy.

Validated suggestions are assembled according to
[`hybrid-planning.md`](../guides/hybrid-planning.md). The initial hybrid planner permits semantic naming and
adjacent task grouping while recomputing interfaces, parameters, source, and diagnostics from V1
evidence. Unsupported boundaries and provider failures return a reportable deterministic fallback
instead of reaching generation.

The deterministic planner assigns stable, valid Python identifiers to task candidates. It prefers recognized source patterns such as train/test split, model training, prediction, and evaluation, then falls back to the nearest preceding Markdown heading, and finally to a `cell_0000` style name when no semantic clue is available.

It also emits `PlanDiagnostic` review notes for conversion risks that should be visible but not necessarily blocking, including fallback task names, inherited source diagnostics, unresolved external inputs, and tasks without data outputs.

`semantic/validation.py` validates `ConversionPlan` invariants before generation. It rejects
blocked plans, duplicate task/configuration names, invalid or keyword Python task names,
and unresolved parameter references. This is not a complete semantic or graph-equivalence
proof. Cell-oriented planning, unknown inputs, mutation and side-effect-only cells still
require the supported-subset limitations and explicit review.

The high-level `plan_notebook_path` use case additionally calls
[`source_accounting.py`](source-accounting.md). A separate immutable audit accounts for every
parsed statement and cross-checks task AST/provenance, ordered imports, exact catalog relocation,
selected parameter evidence and source dependencies. Passing plans are unchanged; failures add
blocking diagnostics. Root `audit_conversion_source(facts, plan)` exposes recomputed JSON evidence
without I/O. Low-level candidate planners remain proposals. A direct generator caller can bind
`source_facts` to request the same guard; a plan alone cannot establish absent-source completeness.

### Kedro generation

`generation/kedro/` consumes only a validated `ConversionPlan`:

- refactor approved source fragments into functions;
- render the Kedro package and pipeline files;
- generate configuration and catalog entries;
- register the pipeline;
- version catalog-backed symbols on their first node rewrite and reject resolved output collisions;
- compile rendered Python before filesystem writes, without importing or executing it;
- hand rendered files and source-copy instructions to the shared writer.

Repetitive boilerplate and source wrapping are deterministic. Code/body proposal APIs are
separate experiments and do not supply code to normal project generation. Compile-only
preflight is structural evidence; it does not check installed dependencies, arbitrary
globals, runtime equivalence, a clean `kedro run` bootstrap or production readiness.

### Initial architecture profiles

`generation/kedro/profiles.py` owns the [schema-1.0 profile contract](../guides/kedro-profiles.md).
Immutable profiles select one pipeline directory/import/registry name and a function/node prefix.
Resolution checks normalized-name and import/builtin collisions without changing the plan.
The renderer keeps source bodies, interfaces, dataset versioning and parameter identities intact.
Both CLI commands accept `--architecture-profile`; reporting and generation accept the same object.
Explicit profiles add review mappings and `architecture-profile.json` with normalized profile
identity/hash and stable task/cell/statement references. Omitted profiles preserve output bytes
and inventory; the explicit default adds only the manifest. This is not a full source-byte binding
or an enterprise policy engine. No provider is involved in profile loading or name resolution.

### Reporting

`reporting.py` renders review artifacts from `ConversionPlan` without importing Kedro or reading
notebook files. Deterministic Markdown covers tasks, catalog, parameters and diagnostics. An
explicit architecture profile adds its configuration identity and source/generated node names.

### CLI

`cli.py` owns terminal argument parsing and delegates to the public API. It should remain thin:
commands orchestrate existing use cases and write their results, while analysis, planning,
reporting, planner selection, and generation logic stay in their component modules. The `plan` and
`generate` commands share deterministic-by-default planner options and optional local Ollama
settings.

Expected notebook loading and project generation failures are formatted by the CLI as concise stderr messages with a non-zero exit code. Unexpected programming errors are not swallowed.

### Filesystem writing

`generation/writer.py` handles side effects:

- reject existing destinations, including observed broken symlinks; there is no overwrite option;
- reject absolute, drive-relative, traversing and overlapping written targets, including
  collisions between copied data and generated files, case-insensitive aliases, trailing
  dot/space components and Windows device names;
- require copied sources to be regular files before preparing output;
- stage files and data in a private temporary directory on the destination filesystem;
- recheck the destination and rename the complete prepared project into place;
- return final paths and clean temporary preparation after routine failures.

Source-copy and write failures therefore do not expose a partially written final project.
New parent directories can remain. Publication/cleanup errors are reported; abrupt process
termination can leave staging data. Rechecks are not a filesystem lock against concurrent
edits, and OS rename behavior does not establish crash durability or hostile-filesystem safety.
Catalog entries without a source copy remain configuration only, with no claimed data existence.
On Windows only, final rename errors 5/32/33 allow at most three attempts with 50 ms waits and
destination rechecks. Other/persistent failures remain errors; preparation writes, source copies,
model calls and code execution are not retried by this mechanism.

## Dependency direction

Dependencies point inward toward the domain contracts:

```text
api
├── notebook → ir
├── analysis → ir
├── semantic → ir
└── generation → semantic validation/accounting → ir
    └── writer → filesystem
```

Forbidden dependencies include:

- `ir` importing Kedro, Jupyter, or an LLM SDK;
- `analysis` importing `semantic` or `generation`;
- `semantic` importing the Kedro generator;
- the static analyzer importing packages referenced by a notebook;
- provider-neutral protocols importing provider SDKs.

The generator reuses the existing plan validator; it does not invoke semantic providers.
Experimental evaluation may orchestrate generation and runtime execution, while static
analysis and normal generation remain free of notebook/model execution.

## Proposed evolution

[ADR 0004](../decisions/0004-shared-engine-and-local-interface.md) defines a reusable engine
composed into operations, exposed first through API/CLI and later a local app or VS Code extension.
The UI choice is open and must not own transformation logic. Local configuration and reviewable
plans/diffs precede application/execution. No UI or operation registry is implemented in this slice.

[ADR 0002](../decisions/0002-incremental-platform-evolution.md) records the incremental
direction. Two future entrypoints should eventually converge on shared project requirements:
source analysis reconstructs existing logic; greenfield specifications declare required logic
and unresolved slots. A versioned architecture profile then maps those requirements to a
reviewable generation plan and the Kedro renderer. Keep profile rules separate from business
semantics, and retain source/code references rather than pretending configuration encodes all
Python behavior.

The initial default/custom Kedro naming/organization profile is now implemented as recorded in
[ADR 0003](../decisions/0003-minimal-kedro-profiles.md). Broader standards and the greenfield slice
remain future work; derive the common typed/versioned project representation from those actual
requirements. No `ProjectSpec`, general template engine, greenfield API, remote provider, extra
backend or enterprise service is introduced here.
Generation, structural checks, behavioral observations, human review and operational acceptance
remain separate evidence dimensions. See the [roadmap](../product/roadmap.md) for dependencies.

## Test architecture

```text
tests/
├── unit/
│   ├── notebook/
│   ├── analysis/
│   ├── ir/
│   ├── semantic/
│   └── generation/
├── contract/
├── integration/
├── end_to_end/
├── fixtures/
│   ├── notebooks/
│   ├── expected_facts/
│   ├── expected_plans/
│   └── generated_projects/
└── conftest.py
```

### Unit tests

Unit tests are fast, isolated, and offline. They cover one behavior at a time and do not launch notebook kernels, call LLMs, or run Kedro projects.

### Contract tests

Contract tests protect versioned boundaries:

- JSON serialization;
- schema compatibility;
- diagnostic-code stability;
- provider response validation;
- generator input requirements.

### Integration tests

Integration tests exercise real component boundaries:

- load and analyze a complete notebook;
- execute a controlled notebook fixture;
- render and import a generated package;
- run a generated Kedro pipeline.

### End-to-end tests

End-to-end tests compare observable notebook and Kedro outputs:

- predictions;
- metrics with explicit numerical tolerances;
- dataset schemas and shapes;
- model behavior where stable serialization is possible.

Successful execution alone is insufficient evidence of equivalence.

### LLM tests

Default CI never performs a paid or nondeterministic external LLM call. It uses fixtures and fake providers to test prompts, structured responses, validation, and error handling.

External tests are opt-in and marked:

```python
@pytest.mark.external
@pytest.mark.llm
```

They require explicit credentials and run only in a protected workflow or manually.

### Planner evaluation

The versioned planning corpus described in
[`planning-evaluation-corpus.md`](../evaluation/planning-evaluation-corpus.md) compares planners by source
boundaries, names, raw code, inputs, outputs, parameters, diagnostics, pipeline assignments, and
plan-level configuration. The deterministic planner is the first baseline. Future local and remote
providers must be evaluated against the same reviewed cases before their results are compared.

`evaluation/benchmark.py` runs named planners over facts analyzed once per corpus case and measures
only planner execution. It records deterministic plan validity, semantic fallback, structural
metrics, and wall-clock latency. `evaluation/benchmark_serialization.py` emits a versioned JSON
report containing corpus hashes and per-model labels. Live model runs are manual or marked both
`external` and `llm`; the default CI suite tests the runner with deterministic in-process planners.

## Delivery increments

The [roadmap](../product/roadmap.md) owns historical milestones and current priorities;
the [project status](../product/project-status.md) owns supported versus experimental scope.
Avoid maintaining a second completion checklist here.

Each increment must leave the repository linted, typed, tested, and documented.
