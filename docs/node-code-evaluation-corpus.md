# Independent Node Code Evaluation Corpus

## Purpose

The first node-code benchmark compares model proposals with functions rendered by the deterministic
V1 generator. That catches regressions against the implementation, but the generator is not an
independent ground truth. The versioned corpus in `tests/fixtures/evaluation/node_code/v1/` adds
task-level references reviewed and written independently of the planner and generator.

Corpus schema `1.0` contains four small notebooks that were not used in the earlier 26-task prompt
experiments. They cover a custom ratio transformation, regression evaluation, mixed-type missing
value imputation and a holdout split. Each case records:

- the notebook path and SHA-256 identity;
- one hand-authored `NodeCodeRequest`, including exact source-cell provenance;
- one approved reference `NodeCodeResponse`;
- reviewed invalid responses and the stable diagnostic fragment expected for each.

The initial corpus has four references and nine invalid examples. It is intentionally small and
synthetic. It establishes an independent contract and test mechanism, not representative model
accuracy or a release threshold.

## Expanded Corpus

The dataset revision in `tests/fixtures/evaluation/node_code/v2/` preserves the four original cases
and adds four independent source tasks. Its JSON schema remains `1.0`; `v2` identifies the expanded
dataset, not a change to the case format or an application release.

| Task | Source behavior | Negative controls |
| --- | --- | --- |
| `aggregate-orders` | Sorted customer totals and order counts, including missing amounts and refunds. | Count non-null amounts instead of orders; change group ordering. |
| `join-customers` | Left enrichment, unmatched-region fallback and many-to-one key validation. | Drop unmatched orders with an inner join; omit duplicate-key validation. |
| `encode-categories` | Integer indicators for every observed segment, with zero indicators for missing values. | Drop the baseline category; change indicator dtypes. |
| `date-features` | Strict ISO date parsing, month strings and Monday-based integer weekdays. | Coerce invalid dates; change weekday numbering. |

The complete dataset has eight references and seventeen invalid examples. Every reference passes
static validation and every invalid example is rejected with its expected diagnostic. Corpus tests
also require the copied baseline cases to equal their original `v1` contracts.

The associated [behavioral corpus](behavioral-comparison-contract.md) has seventeen scenarios. Each
new task has a nominal scenario, a boundary scenario and an expected exception. Its expected results
are hand-authored; they are checked by executing approved references and never derived from the V1
generator. Integer and object casts in the source make observable table dtypes explicit across
pandas versions. Dates are inputs as strings and outputs as month strings and integer weekdays, so
the behavioral schema does not need timestamp support.

These are small synthetic task cells with explicit external inputs. They broaden the operations
under evaluation but do not establish performance on full, real-world notebooks or add those
operations to deterministic project generation. The new cases were authored before running models
on them, with the existing prompt and validator unchanged.

## Loading And Integrity

`load_node_code_corpus` reads strict JSON in deterministic filename order. Unknown or missing
fields, unsupported versions, pending reviews, duplicate IDs and response identities that differ
from the request are rejected. Every case must be explicitly marked `approved` and include at
least one invalid example.

`verify_node_code_case_source` checks the notebook bytes against the recorded SHA-256 and requires
the request's `raw_source` to equal one complete code cell. It does not invoke notebook analysis,
planning or generation. Consequently, a change to those components cannot silently rewrite the
reviewed reference.

```python
from notebook_to_kedro.evaluation import (
    load_node_code_corpus,
    verify_node_code_case_source,
)

cases = load_node_code_corpus("tests/fixtures/evaluation/node_code/v1")
for case in cases:
    verify_node_code_case_source(case, project_root=".")
```

## Static Evaluation

`evaluate_node_code_corpus` evaluates the stored responses directly and never calls a provider.
For every candidate it records these dimensions separately:

| Dimension | Meaning |
| --- | --- |
| `compilation_valid` | Imports and function compile as Python without execution. |
| `static_valid` | The current request-specific node-code validator accepts the response. |
| `reference_ast_match` | Function AST exactly matches the independent approved reference. |
| `expected_outcome_match` | An approved reference passed all checks, or an invalid example was rejected with its reviewed diagnostic fragment. |

Corpus aggregates expose accepted references, false rejections, detected invalid examples and
missed invalid examples. A malformed proposal demonstrates that compilation and AST parsing can
fail, while a missing-import example demonstrates that compilable, AST-identical code can still
fail request-specific validation.

```python
from notebook_to_kedro.evaluation import evaluate_node_code_corpus

evaluation = evaluate_node_code_corpus(cases)
assert evaluation.reference_accepted_count == 4
assert evaluation.false_rejection_count == 0
assert evaluation.detected_invalid_count == 9
assert evaluation.missed_invalid_count == 0
```

These are validator regression results over stored reviewed examples, not model scores. The
reference functions and invalid proposals are compiled but never imported or executed. The corpus
does not establish data-dependent behavior, package availability, side-effect safety or semantic
equivalence. A separate [behavioral comparison contract](behavioral-comparison-contract.md) now
defines explicit inputs, expected outputs or exceptions and comparator policies. Approved references
and explicitly authorized proposals now execute through the bounded worker and deterministic
comparators. This validates the harness; model performance requires separate provider runs.

## Extension Rules

New cases should come from notebooks not used to tune the prompt or validator under evaluation.
References must be manually reviewed rather than copied from generated output. Each invalid example
should represent one documented failure mode and use the narrowest stable diagnostic fragment.
Notebook hashes and exact code-cell source must be updated together. Keep measured dataset revisions
immutable and publish expanded datasets in a new directory. Breaking case-format changes also
require a new schema version.
