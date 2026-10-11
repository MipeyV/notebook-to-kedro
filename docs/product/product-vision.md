# Product vision: notebook-to-production workflows

[Documentation index](../README.md)

Status: proposed product direction, recorded on 2026-10-11. This document is not a
supported-feature list, an executable configuration contract, or a release commitment.
The [compatibility guide](../reference/compatibility.md) and [README](../../README.md#project-status)
remain authoritative for current capabilities.

## Objective

Build a reusable notebook-to-production foundation for data teams, with multiple usage
modes rather than a single conversion workflow. Starting from a notebook and an explicit
business contract, produce a traceable, reproducible project that fits the organization's
data systems, evaluation requirements and experiment-tracking policies.

The intended surfaces are a Python API and CLI first, with a possible application or
enterprise API later. Product names, commercial packaging and hosting are undecided.
Kedro is the initial execution target; other targets would need separate contracts and tests.

## Usage modes

| Mode | Purpose | Acceptance contract |
| --- | --- | --- |
| Faithful reproduction | Restructure the original workflow into nodes, pipelines, parameters and datasets. | Preserve declared observable behavior, source provenance and approved comparison tolerances. |
| Industrialization | Add approved project scaffolding, tests, configuration, tracking and environment integration. | Preserve the computational contract and explicitly approve added operational side effects. |
| Optimization | Propose changes to implementation or the ML workflow against business objectives and resource budgets. | Record and approve deviations from the baseline, then evaluate against a separate optimization contract. |

Faithful reproduction must remain independently usable. Bayesian search, cross-validation,
new preprocessing or a different model are not automatically faithful refactorings.
A better metric does not justify silently changing the original experiment. Fixing a defect
or leakage in the notebook is also a reviewed change, not an invisible conversion repair.

## Contract-driven generation

```text
Notebook + business requirements + enterprise execution profile
    -> immutable source facts and source-acquisition evidence
    -> reviewed baseline contract and pipeline plan
    -> compatible, versioned project and step templates
    -> adapted node bodies, catalog, parameters and tests
    -> static validation and consent-gated behavioral comparisons
    -> optional reviewed optimization candidates and benchmark reports
    -> reproducible project plus an auditable change and acceptance report
```

The baseline contract should describe source cells and statements, dependencies, datasets,
schemas, row identity/order where relevant, parameters, seeds, outputs, assertions and side
effects. Record unresolved assumptions explicitly. Business requirements additionally define
objectives, metric direction, segments, split policy, budgets and acceptance thresholds;
they must not be invented by the model.

Reuse V1's loader, AST facts, intermediate representations, diagnostics, plan validation,
Kedro rendering and source provenance. Reuse V2's provider boundaries, strict body assembly,
behavioral comparators and auditable capture/replay evidence. Broader source descriptors,
workflow contracts and optimization policies require new versioned boundaries.
The current strict AST-fidelity validator rejects rewritten instructions: optimization needs
a separate explicit validation path, not a relaxation of faithful-conversion defaults.

A coding role may fill approved template slots or propose bounded changes. A structuring
role may compare the proposal with the original evidence and report contract violations.
Neither role's judgement alone authorizes writing, execution or acceptance. Deterministic
checks, independent expected outcomes, execution consent and human review remain necessary.
Finite passing tests are evidence on covered cases, not a general equivalence proof.

## Templates that adapt to the notebook

Project templates define layout, dependency constraints, configuration, tests and CI.
Step templates define interfaces, preconditions and optional reusable implementations.
Template selection must check compatibility with the notebook contract and execution profile.
Every template and adaptation needs versioned provenance and reviewable source mappings.

Do not force unfamiliar logic into a standard sequence. Preserve custom steps when possible;
otherwise expose missing evidence or unsupported behavior. Keep business code separate from
tracking and storage adapters. Do not add a new framework or dependency merely to fit a template.

Potential workflow components, selected only when appropriate or explicitly requested:

- Source acquisition, loading and schema validation.
- Cleaning, preprocessing and feature engineering.
- Train/validation/test splitting, including grouped or temporal splits where required.
- Cross-validation and Bayesian hyperparameter optimization with explicit search spaces,
  objectives, trial/time budgets and reproducible seeds.
- Training, prediction, final evaluation and approved model-artifact persistence.
- Technical metrics, business KPIs, segmented metrics and segmented plots.
- Experiment tracking, reports and runtime/resource measurements.

New optimization workflows must fit preprocessing inside each training fold and keep final
test data outside feature selection, tuning and model selection. Preserve an original split
in faithful mode, but flag suspected leakage for review. Segment definitions, minimum support
and small-group disclosure rules must be explicit; aggregate improvement can hide segment
regressions. Report such trade-offs rather than claiming a universally better candidate.
The [scikit-learn common pitfalls guide](https://scikit-learn.org/1.7/common_pitfalls.html)
documents the leakage risks and training-only preprocessing principle.

## Automatic source interpretation and catalog generation

Read how the notebook obtains each dataset, not just the names of its DataFrames. Capture
the loader, engine, format, location or dataset identifier, read options, schema evidence,
version and credential references when statically supported. Use this evidence to propose
Kedro catalog entries and the corresponding node inputs/outputs.

| Source family | Intended interpretation |
| --- | --- |
| Local files | Generate appropriate dataset configuration from supported loading expressions and options. |
| Simulated data or scikit-learn datasets | Keep generation/loading as a node with parameters and seed; name its output without inventing a file path. |
| Kaggle | Separate acquisition from file loading; preserve dataset identity, version and file selection when available. |
| Databricks / Spark | Preserve Spark semantics and distinguish file reads from table reads; declare runtime prerequisites. |
| AWS / GCP storage | Resolve storage, reader and format together, using external credential references. |

Not every intermediate DataFrame requires a persistent YAML entry; in-memory node outputs
are distinct from external or persisted datasets. A URI alone does not establish the loader,
format or authentication method. Dynamic paths, ambiguous loaders and missing options require
diagnostics or explicit user configuration, not guessed connectors. Static analysis must not
download data, contact a cloud service or execute source code to resolve those ambiguities.

Current support includes controlled literal local CSV reads and bundled sklearn reference
workflows. Broader automatic interpretation of these source families remains a target, not
a general connector guarantee. Synthetic simulations must be exercised reproducibly before
any claim of real-world source coverage; Spark tests need a real Spark runtime, not a silent
pandas replacement.

## Enterprise profiles and experiment tracking

Proposed enterprise profiles select execution environment, storage adapters, dependency
constraints, secret references, tracking backend, allowed network destinations and data
disclosure policies. They must be supplied or reviewed, not inferred from a company name.
Local execution should remain possible without a tracking service or cloud account.

Provide optional tracking adapters for no tracking, MLflow and Weights & Biases (W&B),
selected explicitly by business and platform requirements. Keep a backend-neutral record of
run identity, source/configuration/dataset provenance, seeds, parameters, folds, trials,
metrics, segment support, plots and approved artifacts. Adapters must expose unsupported
capabilities rather than silently dropping evidence; backend features need not be identical.

MLflow documents tracking for parameters, metrics and artifacts; W&B documents structured
tables and their visualization. These are integration references, not evidence that this
repository already supports either backend:
[MLflow Tracking](https://mlflow.org/docs/latest/tracking/),
[W&B Tables](https://docs.wandb.ai/models/tables).

Tracking requires explicit authorization for its destination and payload. Never embed
credentials in generated source, catalog files or reports. Restrict raw data, row-level
predictions, sensitive segments and model artifacts according to the enterprise policy.
Define failure handling, retention and artifact transfer limits before enabling an adapter.
Generating a project is not the same as deploying, serving or monitoring it in production.

## Optimization and minimum description length

Distinguish program refactoring from statistical optimization: reducing duplication is not
the same objective as choosing a model or hyperparameters. Minimum description length (MDL)
balances description of a model with description of data given that model; it is not a rule
that the fewest source lines produce the best program.
[Grunwald's MDL introduction](https://arxiv.org/abs/math/0406077) provides the theoretical basis.

Start with an explicitly MDL-inspired complexity heuristic, not a claim of formal MDL:

```text
description cost = template description + configuration/adaptations + residual custom code
```

Define a versioned encoding/cost model and account consistently for shared helpers and
dependencies, so moving complexity into a library cannot make it disappear from the score.
Only compare candidates that pass the applicable acceptance contract. Keep readability,
runtime, peak memory, statistical performance and segment quality as distinct measured
criteria. A compact candidate can be slower or harder to maintain. Formal MDL experiments
would require a defined coding scheme and evaluation protocol of their own.

## Repository and product boundaries

Recommendation: record and refine the vision here now; do not create a second repository
or duplicate the analyzer solely because there are multiple usage modes. Keep faithful
conversion as this package's stable responsibility. Prototype broader workflow contracts
behind separate modules and opt-in boundaries only when the staged work requires them.
Keep cloud, tracking and optimization dependencies outside the minimal conversion runtime.

A separate application/platform repository becomes useful when it owns independent concerns:
UI or hosted API, identity and tenant isolation, persistent jobs, resource scheduling, billing,
deployment, or an independent release/security lifecycle. A separate optimization package may
also be appropriate if it acquires a distinct dependency and compatibility surface.
Those products should consume versioned core APIs and evidence artifacts, not fork conversion
logic or import private modules. API vs application, local vs hosted execution and commercial
product tiers remain open decisions; they do not require separate model training today.

## Staged roadmap and acceptance gates

These milestones extend, rather than replace, the unfinished V2 roadmap. None is marked
complete by this documentation change.

1. **Complete-notebook pilot:** create a reproducible synthetic workflow and independently
   review source acquisition, expected catalog, task boundaries, intermediate tables,
   predictions and metrics. Keep its review status pending until actual human approval.
   Follow with an authorized, redacted real notebook; synthetic success is not general accuracy.
2. **Source contracts:** version source descriptors and diagnostics; cover simulation/sklearn
   and local reads before isolated Kaggle, Spark/Databricks and AWS/GCP adapters. Test both
   recognition and real loading separately with explicit credentials/network consent.
3. **Faithful template adaptation:** render versioned skeletons and fill bounded slots;
   validate generated projects against independently reviewed baseline outputs and negative
   controls. Add review-gated project integration without automatically accepting LLM proposals.
4. **Industrialization profiles:** add optional tracking and environment adapters with local
   no-tracking coverage, backend-specific integration tests and privacy/failure policies.
5. **Explicit optimization:** introduce reviewed change plans, leakage-safe CV/search,
   KPI/segment contracts and complexity/runtime benchmarks under bounded execution budgets.
   Rejections and regressions must remain in reports, not disappear from success denominators.
6. **Product packaging:** validate team workflows, coverage, review burden, latency and cost;
   choose library/API/application packaging and repository boundaries from demonstrated needs.
   Serving, deployment and monitoring require their own acceptance gates if added.

The [draft complete-notebook pilot](../evaluation/synthetic-notebook-pilot.md) now covers one
controlled simulation-plus-local-CSV workflow. Its independent source/catalog and behavioral
review remains the next gate before a whole-notebook model experiment, not an unbounded
optimizer or a production platform.
