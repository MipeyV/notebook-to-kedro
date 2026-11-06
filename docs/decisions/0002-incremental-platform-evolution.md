# ADR 0002: Evolve the conversion core incrementally toward ML engineering automation

[Documentation index](../README.md)

- **Status:** Accepted direction; future capabilities remain proposals
- **Date:** 2026-11-06

## Context

Notebook conversion is the first use case of a broader ML engineering automation product.
The existing core already separates immutable notebook facts, semantic planning, deterministic
Kedro generation and experimental validation. Replacing it with a universal project model or
enterprise service architecture now would discard useful contracts before both entrypoints
have demonstrated common requirements.

The approved first implementation scope is documentation alignment and generation reliability.
It does not authorize implementing every phase of the product roadmap.

## Decision

- Keep the current library/CLI and Kedro target in this repository. Reuse the existing core.
- Recognize two strategic entrypoints: industrialize an existing project and generate a new
  project from explicit requirements. Keep faithful conversion and optional optimization separate.
- Prioritize a dependable generation boundary, reviewed project-level evidence, a narrow
  versioned architecture profile, then a first greenfield slice. Order integrations by user need.
- Introduce a common project representation only when those slices justify its fields. Keep
  source evidence separate from requirements, inferred implementations and checked observations.
- Keep deterministic analysis/generation and replaceable optional providers. Do not train a
  foundation model or add another framework backend for this milestone.
- Measure total engineering effort, standards compliance and correctness against general coding
  agents on the same authorized cases, with corrections, failures and incomplete attempts visible.

The generator enforces existing plan validation itself, compiles rendered Python without execution
and delegates publication to a shared writer. The writer rejects escaping/overlapping copy targets,
checks regular source files, stages on the destination filesystem and renames prepared output.
Targets also reject Windows device names, trailing dot/space components and control characters.
Existing destinations are checked before preparation and immediately before publication. No overwrite
option is added. Routine preparation failures clean temporary output; newly created parents may remain.
This does not provide a filesystem lock against concurrent edits, authenticated provenance, crash
durability or an OS sandbox. OS rename and cleanup failures are reported explicitly; abrupt process
termination may leave a temporary directory requiring inspection.

## Consequences

- Existing V1 users retain the same generated layout and deterministic source transformations.
- Direct API callers now receive `ProjectGenerationError` for invalid plans and rendered Python,
  rather than being able to bypass the CLI's preflight. Keyword identifiers are rejected.
- Source files that cannot be copied or targets that overlap generated files fail before publication.
- Structural checks do not establish runtime equivalence, environment reproducibility or production
  readiness. The actual pilot still requires independent human review before live model evaluation.
- Profiles, greenfield generation, MLOps adapters, application hosting and commercial packaging
  remain separate work. This decision changes neither the MIT license nor historical measurements.

## Alternatives considered

- **Broad rewrite / universal `ProjectSpec` now:** insufficient evidence for a stable shared model.
- **Enterprise services or a separate platform repository now:** no demonstrated independent
  hosting or release requirement for this milestone.
- **More model benchmarks before generator reliability:** does not close the public generation
  boundary or prove a reduction in end-user engineering effort.
- **Write directly into the final directory and clean on failure:** exposes incomplete projects
  and risks confusing unrelated destination content with owned temporary output.
