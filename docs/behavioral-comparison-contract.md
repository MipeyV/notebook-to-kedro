# Behavioral Comparison Contract

## Scope

`notebook_to_kedro.evaluation.behavioral` defines versioned, deterministic evidence for isolated
comparisons between a reviewed notebook task and a proposed node. It describes runtime inputs,
expected outputs or an expected exception, and explicit comparison policies. The separate
`behavioral_execution` module can execute an approved reference function; it does not execute model
proposals or decide equivalence yet.

Behavioral schema `1.0` is linked to the
[independent node-code corpus](node-code-evaluation-corpus.md) by `node_code_case_id`.
`validate_behavioral_case` requires input names and order to match the node function arguments.
For successful cases, output names and order must match the node outputs. Exception cases have no
expected outputs and instead record an exception type plus an optional stable message fragment.

The initial corpus in `tests/fixtures/evaluation/behavioral/v1/` contains five reviewed scenarios:
four successful cases for the independent node references and one missing-column exception case.
These fixtures specify future execution expectations; this milestone does not execute them.

## Serializable Values

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
exact comparator because their shape, dtype and ordering policies must remain visible. The contract
defines comparison intent only; comparator implementation remains a separate milestone.

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

## API

```python
from notebook_to_kedro.evaluation import (
    load_behavioral_corpus,
    load_node_code_corpus,
    validate_behavioral_corpus,
)

behavior_cases = load_behavioral_corpus("tests/fixtures/evaluation/behavioral/v1")
node_cases = load_node_code_corpus("tests/fixtures/evaluation/node_code/v1")
validate_behavioral_corpus(behavior_cases, node_cases)
```

Both loaders use deterministic filename order. Cases must be explicitly approved and case IDs must
be unique. Unknown node-code links, duplicate node IDs and interface mismatches fail validation.
Dictionary and JSON round trips are available through `behavioral_case_to_*` and
`behavioral_case_from_*`.

## Trust Boundary

Process separation is fault containment, not an operating-system sandbox. The worker does not
disable filesystem or network access and does not impose portable CPU or memory limits. This
milestone therefore executes only source-controlled, human-approved references. Running a model
proposal requires an additional isolation decision and must use a fresh process with independently
materialized inputs so one run cannot mutate evidence observed by the other.

The five approved corpus references now execute successfully, including the reviewed exception
case. Comparator evaluation and proposal execution are still absent, so behavioral equivalence
remains `not_evaluated`.
