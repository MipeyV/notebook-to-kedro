# Fresh Node Corpus V3

## Purpose And Status

Dataset `v3` provides fresh task contracts for the next evaluation after the repeated
[body-only development measurements](node-body-local-measurements.md). The existing eight-node
`v2` dataset has already informed prompt experiments and must not be presented as fresh held-out
evidence. Its files, results and corpus identity are unchanged.

This is a **standalone** dataset of four new nodes, twelve behavioral scenarios and eight negative
controls, not a twelve-node cumulative extension of `v2`. Node, request, task and scenario IDs,
notebook paths and exact source bodies are disjoint from `v1` and `v2`. Both case schemas remain
`1.0`: the directory version identifies the dataset, not a format or application release.

No evaluated Ollama model was invoked on these cases in this PR, and no prompt, validator or
production code was changed. The references and expected results are explicitly authored fixture
candidates, not outputs copied from the planner, generator or a sampled model response. Test
execution checks the authored expectations rather than computing replacement snapshots.

The candidates were authored by the coding assistant and need maintainer review through the PR
before a first scored model evaluation. No second independent human review is asserted here.
`review_status: approved` follows the existing loader's eligibility contract; the field alone is
not evidence of independent human sign-off. Review the source, interfaces, expected values and
negative controls before freezing this candidate dataset through merge.

## Cases And Boundaries

| Node | New source pattern | Nominal evidence | Boundary | Expected exception |
| --- | --- | --- | --- | --- |
| `normalize-tags` | Imported stdlib helper and list comprehension. | NFKC normalization, trimming and Unicode case folding. | Empty labels. | Non-string label raises `TypeError`. |
| `partition-measurements` | Assertion, branch, append loop and three ordered outputs. | Keep values equal to or above an external limit; retain rejected nulls and count each partition. | Empty measurements at limit zero. | Negative limit raises `AssertionError`. |
| `cumulative-balance` | Stateful loop, `continue`, explicit raise and two outputs. | Apply transactions in order and skip zero amounts in history. | Empty transactions and zero opening balance. | Overdraft raises `ValueError`. |
| `rank-candidates` | Two-key table ordering, tied rows, index reset and three outputs. | Descending scores, ascending names, preserved identical-key ties and a two-row shortlist. | Empty typed table. | Missing score raises `KeyError`. |

Every node has one nominal, one boundary and one exception scenario. Across the dataset there
are eight successful scenarios, four expected exceptions and eighteen expected output records.
Inputs are explicit external arguments, not inferred automatically by notebook planning.

The normalization example uses full-width letters and German sharp s to distinguish compatibility
normalization and case folding from simple lowercasing. Partitioning puts an observation exactly
on the threshold. The balance example includes a zero transaction so removing `continue` changes
history even when the final balance agrees. Ranking uses duplicate keys and non-default input
indices so value order and index reset are observable, rather than incidental formatting.

Scalar/list/object outputs use the type-sensitive `exact` comparator. Ranking tables explicitly
require dtype, column/row order and index agreement with zero numeric tolerance. Inputs and outputs
remain JSON-tagged values; there is no pickle, callable input, fitted estimator or file access.
Thresholds are explicit input arguments, not a new automatic parameter-extraction rule.

These are small synthetic task notebooks requiring supplied inputs. They are not complete
independently executable Data Science workflows, a representative real-world sample or new
deterministic generation support. Imported helpers are allowed, but nested functions, classes,
dynamic imports and scope-changing constructs remain outside the unchanged strict code contract.
This PR does not weaken that boundary to make helper definitions pass.

## Negative Controls And Verification

| Node | Fixed invalid variants | Discriminating scenario |
| --- | --- | --- |
| `normalize-tags` | Lowercase instead of case folding; omit whitespace trimming. | Nominal Unicode labels. |
| `partition-measurements` | Exclusive rather than inclusive threshold; omit limit assertion. | Nominal threshold tie; negative limit. |
| `cumulative-balance` | Record zero transactions; omit overdraft guard. | Nominal history; overdraft. |
| `rank-candidates` | Reverse the score direction; retain the source index. | Nominal tied ranking and explicit index. |

Static evaluation accepts all four hand-authored references and rejects all eight invalid
variants with their specified diagnostics. Scenario-sensitivity tests execute only those fixed
checked-in negative controls directly in the test worker; each yields a mismatch. This narrow
test bypass is never applied to unvalidated provider proposals or exposed as a CLI option.

Integrity tests validate notebook format and empty execution state, byte-level source hashes,
exact source-cell binding, top-level statement IDs, disjoint identities and linked interfaces.
Approved body statements reconstruct the reference function ASTs and necessary imports through
the existing assembler. Real subprocess tests execute all twelve scenarios for references and
validated reference proposals. An offline reference provider then exercises body benchmarking,
exclusive artifact publication and replay on all twelve scenarios, without Ollama.

These checks establish fixture and harness consistency, not LLM acceptance or generalization.
The new dataset has no published model score. Once model results guide changes, treat it as a
development regression corpus and reserve another fresh dataset for evaluation.

## Identity And Measurement Gate

Sources live in `tests/fixtures/notebooks/node_code_eval_v3/`. Node contracts are in
`tests/fixtures/evaluation/node_code/v3/`, and behavioral contracts are in
`tests/fixtures/evaluation/behavioral/v3/`. Each node records its notebook SHA-256. The complete
canonical corpus SHA-256 is pinned by a test before any model evaluation:

```text
1a4fade0462bc0ef58a18cea70099079ff9dd09f8980fb697c5cb64794e32125
```

The digest covers node requests, references, invalid variants, behavioral inputs, expected results
and comparison policies. Keep measured revisions immutable; further reviewed cases belong in a
new dataset rather than silently changing these inputs after observing model outputs. Do not
compare `v2` and `v3` percentages as improvements: both task sets and denominators differ.

After maintainer review, evaluate both existing local models without tuning prompts on `v3`.
Retain rejected proposals and all twelve scenarios in end-to-end denominators. Use fixed versions
and runtime settings, distinct output paths, repeated runs, raw archives and offline replay.
The [benchmark commands](node-body-benchmark.md#cli) accept these two `v3` corpus directories;
reading the corpus or running the default tests does not invoke a model.

A corpus-bound full-code/body-only comparison bridge and contemporaneous full-code controls
remain separate work. Model roles, full notebooks and project-level equivalence need their own
evaluation. Keep execution opt-in in a controlled environment: subprocesses are fault containment,
not an OS security sandbox.
