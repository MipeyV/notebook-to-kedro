# ADR 0019 - Separate operation timings from declared conversion effort

[Documentation index](../README.md)

Accepted on 2026-11-17.

## Context

One private application/generated pipeline pair reproduces its scoped outputs. Worker execution
durations do not measure time saved restructuring a project. Local operations offer a concrete
observation boundary while deterministic source facts and interface contracts stay independent.
Human effort and a fair manual baseline require explicit observations.

## Decision

Add opt-in measure_local_operation around inspect/plan/generate. Preserve return values,
diagnostics, generation guards and result schemas; default calls collect nothing. Reserve a new
directory through the shared writer before operation I/O, then publish an exclusive outcome
with status and monotonic duration. Protect source/package/settings/generation targets and
retain missing observations as unfinished attempts.

Summarize explicit attempt directories, settings, source identities, environment and known
operation seconds. Bind optional human declarations to the canonical current inventory.
Preparation, installation, runtime execution, journey timing and human work stay outside
automatic collection in this initial slice.

Human declarations state activity seconds, measured/estimated basis, outcome, operator, primary
source, acceptance criteria and first-use/reuse setup. Compare matching declarations only with
stable source and a complete inventory. Compute human/elapsed differences separately, retaining
negative results. Missing baselines produce no saving. Label comparisons as operator-declared
measurement or estimate; never infer human work from timestamp gaps.

Expose API/CLI first, with no dependency or interface/configuration schema change. Source/label
matching supplies partial task evidence, not authenticated semantic equivalence. Acceptance,
execution consent and independent notebook-pilot review keep separate contracts.

## Consequences

Operators can inspect actual timings and include failures/corrections in a local balance.
Nothing is uploaded automatically. This cannot retroactively establish time saved on earlier
projects. Matched cases and human baselines remain a product-evaluation workstream.

Timing excludes collection overhead/configuration loading; hashing can warm caches. Abrupt
termination may leave a missing or malformed outcome. Missing outcomes are unfinished;
malformed evidence is rejected. No filesystem lock, global attempt discovery, automatic repair
or acceptance authority is introduced. See the
[operation reference](../reference/local-operations.md#opt-in-conversion-measurements).

## Increment: pending comparison forms

The operation API/CLI now prepares pending tool/manual/general-assistant declarations from a
complete stable ledger containing successful generation. A new sibling directory holds three
shared-criteria forms, the observed machine summary and prospective collection instructions.
Validation and inventory recapture precede shared-writer publication. Forms remain estimated,
in_progress and empty until actual human observations and acceptance are entered.

This is a collection aid, not a workspace snapshot, automatic stopwatch, acceptance authority
or productivity benchmark. Existing tool outputs can bias a manual baseline; independent
operators or fresh counterbalanced tasks are needed when appropriate. New attempts require
fresh inventory binding rather than silently overwriting earlier forms.
