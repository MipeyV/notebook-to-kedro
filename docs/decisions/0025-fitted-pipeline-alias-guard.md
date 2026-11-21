# ADR 0025 - Reject bounded fitted Pipeline alias hazards

Date: 2026-11-21

Status: accepted

## Context

The nested financial experiment preserved a notebook that succeeds in source but fails after
conversion: Pipeline fitting mutates its preprocessor, while an external reference loaded
through default Kedro memory copies remains unfitted. Static statement accounting was complete.
Changing copy policies or silently rewriting references would change the conversion contract.

## Decision

Add the blocking diagnostic SA009 to the recomputed source audit. Recognize direct imported
Pipeline/make_pipeline constructors, literal named steps, named bindings/aliases and direct
fit calls. Track construction, fitting and subsequent reads against actual proposed task owners.
Reject later external component reads that can depend on sharing across memory-copy boundaries.
Keep local fitting/export in the same task and explicit model-owned component access eligible.

Use Python ASTs and existing immutable source facts only. Do not import sklearn, execute source,
change ASTs, infer arbitrary graph semantics, add a planner mode or alter memory dataset policy.
Normal notebook planning and direct generation with source_facts share this audit before the
existing writer. Low-level proposals and generation without source facts retain their existing
limitations. No wire schema change is needed for another ordinary diagnostic code.

## Consequences

The original fitted-alias notebook is now refused before publication, with the source/report
bytes and historical failure preserved. Working credit/calibrated-vote cases remain convertible.
Temporal stacking's source library error remains a separate runtime boundary. Tests cover
imports, alias/rebinding ownership, separately constructed/fitted models, annotations, immutable
passthrough values, generated profiles and API/CLI/local-operation refusal without publication.

SA009 is conservative and limited to this syntactic pattern. It does not prove that a source
execution would succeed, interpret caching/clone policies, repair aliases, or guarantee arbitrary
wrappers, dynamic containers, factories or control flow. Broader alias support, persistence and
scientific/productivity validation remain separate work.
