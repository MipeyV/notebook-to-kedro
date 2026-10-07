# Behavioral Comparison Contract

## Scope

`notebook_to_kedro.evaluation.behavioral` defines versioned, deterministic evidence for isolated
comparisons between a reviewed notebook task and a proposed node. It describes runtime inputs,
expected outputs or an expected exception, and explicit comparison policies. The separate
`behavioral_execution` module executes approved references and explicitly authorized, statically
validated proposals. `behavioral_proposal` joins proposal execution with deterministic comparison.
The provider-level [behavioral code benchmark](behavioral-code-benchmark.md) aggregates these
outcomes without hiding proposals that never reach execution.

Behavioral schema `1.0` is linked to the
[independent node-code corpus](node-code-evaluation-corpus.md) by `node_code_case_id`.
`validate_behavioral_case` requires input names and order to match the node function arguments.
For successful cases, output names and order must match the node outputs. Exception cases have no
expected outputs and instead record an exception type plus an optional stable message fragment.

The initial corpus in `tests/fixtures/evaluation/behavioral/v1/` contains five reviewed scenarios:
four successful cases for the independent node references and one missing-column exception case.
The approved references execute in isolated workers and all five currently match their reviewed
expectations.

The expanded `tests/fixtures/evaluation/behavioral/v2/` dataset preserves these five scenarios and
adds twelve for aggregation, customer joins, categorical encoding and calendar features. It has
seventeen scenarios for eight nodes: twelve successful cases and five expected exceptions. Every
new node has nominal, boundary and exception evidence with explicit dtype, order and index checks.
The case schema remains `1.0`.

All seventeen approved scenarios pass through both reference and proposal execution. Eight
checked-in semantic negative controls also produce behavioral mismatches when executed directly in
the test worker. This verifies that the new expectations detect the documented logic changes, in
addition to their rejection by the static validator.

## Serializable Values

The standalone [fresh `v3` dataset](fresh-node-corpus-v3.md) supplies twelve disjoint scenarios
for four new nodes: eight successful cases, four expected exceptions and eighteen output records.
It uses exact recursive comparisons for scalar/list/object outputs and explicit zero-tolerance
dtype/order/index checks for ranking tables. All reference scenarios and body-only reference
benchmark/replay checks pass without model calls; eight fixed negative controls are detected.
It is not a cumulative expansion of `v2` or a published model-accuracy measurement.

Runtime evidence uses immutable tagged values rather than Python pickle or arbitrary object
serialization:

| Kind | Contract |
| --- | --- |
| `scalar` | A finite JSON scalar: string, integer, float, boolean or null. |
| `list` | An ordered tuple of recursively tagged values. |
| `object` | Ordered, unique, non-empty string keys mapped to tagged values. |
| `array` | Explicit dtype, non-negative shape and flattened scalar values. Shape must match value count. |
| `table` | Ordered unique columns, one dtype per column, rectangular rows and an optional explicit index. |

Non-finite floats (`NaN` and infinities), arbitrary Python objects, duplicate object keys,
inconsistent array shapes, malformed tables and unsupported tags are rejected. JSON parsing is
strict and rejects duplicate keys and non-finite constants. This avoids unsafe pickle loading and
keeps fixtures reviewable in source control.

This first contract cannot represent fitted estimators, file handles, iterators, sparse matrices,
timestamps or extension dtypes. Such values must receive an explicit reviewed representation in a
future schema rather than being serialized implicitly.

## Comparators

Every successful output selects one comparator and all of its settings explicitly:

| Comparator | Intended value | Settings |
| --- | --- | --- |
| `exact` | Scalar, list or object | No tolerance or container settings. |
| `numeric` | Numeric scalar | Absolute/relative tolerance and `equal_nan`. |
| `array` | Typed array | Tolerances, `equal_nan` and dtype checking. Shape and order remain structural. |
| `table` | Typed table | Tolerances, `equal_nan`, dtype, column-order and index checks. |

Tolerance values must be finite and non-negative. Array and table values cannot select the generic
exact comparator because their shape, dtype and ordering policies must remain visible.

`compare_behavioral_result` implements these policies deterministically. Exact comparison is
type-sensitive and recursive. Numeric comparison uses explicit absolute and relative tolerances.
Array comparison always checks shape and flattened order, optionally checks dtype, and applies
tolerances to numeric values. Table comparison always checks row count and cell values, can align
columns by name when column order is ignored, and applies the explicit dtype and index policies.
Non-numeric values remain type-sensitive under array and table comparison.

Expected exceptions match an exact exception type name and, when configured, require the stable
message fragment to be present. Reports distinguish a completed behavioral `mismatch` from an
`execution_error` such as setup failure, timeout, worker failure or serialization failure.

## Approved Reference Execution

`execute_behavioral_reference` validates the behavioral case against its linked node-code case,
revalidates the approved reference with the static node-code validator, and then starts a fresh
Python interpreter with `-I`. The worker runs in a temporary directory with a filtered environment,
no standard input, bounded request/result JSON, bounded Python stdout/stderr capture, a configurable
timeout, and a new process group that is terminated on timeout.

```python
from notebook_to_kedro.evaluation import (
    execute_behavioral_reference,
    load_behavioral_corpus,
    load_node_code_corpus,
)

behavior = load_behavioral_corpus("tests/fixtures/evaluation/behavioral/v1")[0]
nodes = {
    case.case_id: case for case in load_node_code_corpus("tests/fixtures/evaluation/node_code/v1")
}
result = execute_behavioral_reference(behavior, nodes[behavior.node_code_case_id])
```

Execution report schema `1.0` records the case identities, status, typed outputs or raised
exception, bounded text captures, truncation flags, duration and an optional failure diagnostic.
Statuses distinguish successful calls, raised function exceptions, setup failures, timeouts,
worker-process failures and output-serialization failures. Runtime values are transported with the
same reviewed tagged-value format; pickle and arbitrary objects remain unsupported.

The worker uses the current interpreter environment. References that need NumPy, pandas,
scikit-learn or another package require that package to be installed explicitly. A missing package
is reported as a setup failure rather than triggering installation or network access.

Comparison report schema `1.0` records each output comparator and its first actionable difference,
or the expected-exception outcome. Corpus reports preserve reviewed case order and aggregate case
count, matches, mismatches, execution errors, match rate and whole-corpus exact match. Reports have
canonical dictionary and JSON serializers.

## Validated Proposal Execution

`execute_behavioral_proposal` refuses execution unless the response passes the same request-specific
static validator used before generation. Invalid identities, imports, signatures, assertions,
parameter substitutions, bodies or returns fail before a subprocess is started. Every accepted
call starts a fresh worker, so inputs are materialized independently from reference execution and
cannot retain mutations from another run.

Because process separation is not an OS sandbox, proposal execution is disabled by default. The
caller must pass `allow_untrusted_code_execution=True` explicitly. `evaluate_behavioral_proposal`
then combines the typed execution result with its deterministic comparison and records a SHA-256
digest of the complete proposal response in proposal-evaluation report schema `1.0`.

```python
from notebook_to_kedro.evaluation import evaluate_behavioral_proposal

evaluation = evaluate_behavioral_proposal(
    behavior,
    nodes[behavior.node_code_case_id],
    proposal,
    allow_untrusted_code_execution=True,
)
assert evaluation.comparison.status in {"matched", "mismatch", "execution_error"}
```

## API

```python
from notebook_to_kedro.evaluation import (
    compare_behavioral_corpus,
    execute_behavioral_reference,
    load_behavioral_corpus,
    load_node_code_corpus,
    validate_behavioral_corpus,
)

behavior_cases = load_behavioral_corpus("tests/fixtures/evaluation/behavioral/v1")
node_cases = load_node_code_corpus("tests/fixtures/evaluation/node_code/v1")
validate_behavioral_corpus(behavior_cases, node_cases)
nodes_by_id = {case.case_id: case for case in node_cases}
results = tuple(
    execute_behavioral_reference(case, nodes_by_id[case.node_code_case_id])
    for case in behavior_cases
)
report = compare_behavioral_corpus(behavior_cases, results)
```

Both loaders use deterministic filename order. Cases must be explicitly approved and case IDs must
be unique. Unknown node-code links, duplicate node IDs and interface mismatches fail validation.
Dictionary and JSON round trips are available through `behavioral_case_to_*` and
`behavioral_case_from_*`.

## Trust Boundary

Process separation is fault containment, not an operating-system sandbox. The worker does not
disable filesystem or network access and does not impose portable CPU or memory limits. Proposal
execution therefore requires explicit caller consent and is intended for controlled evaluation
environments. Static validation constrains a proposal to the reviewed source-derived body, but it
does not make the original notebook code safe. Stronger production isolation still requires a
container or operating-system sandbox with filesystem, network, CPU and memory policies.

Approved references execute and compare successfully across both dataset revisions, including all
expected exceptions. This validates the execution and comparison harness. Real provider runs on
both the frozen `v1` and expanded `v2` corpora are documented in the
[benchmark](behavioral-code-benchmark.md). Three unchanged `qwen3:8b` runs on `v2` and one offline
replay each matched fifteen of seventeen scenarios end to end; two scenarios were not executed
because their node proposals failed static validation. These are synthetic corpus observations,
not proof of equivalence for arbitrary notebooks.

A [same-contract code-model comparison](local-code-model-comparison.md) subsequently evaluated
`qwen2.5-coder:7b`: three live runs and a replay each matched sixteen of seventeen scenarios, with
one scenario blocked by static rejection and no observed regression against the baseline.
