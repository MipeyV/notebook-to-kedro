# ADR 0003: Start architecture profiles with deterministic Kedro naming and organization

[Documentation index](../README.md)

- **Status:** Accepted for the initial profile slice
- **Date:** 2026-11-06

## Context

[ADR 0002](0002-incremental-platform-evolution.md) prioritizes a default/custom profile on
the existing conversion core before a general project representation. The next approved
milestone needs a reusable convention set and checked behavior, with no new business logic,
LLM dependency or framework abstraction. The actual pilot's independent review remains pending.

## Decision

Use a frozen `KedroArchitectureProfile` with strict versioned UTF-8 JSON configuration. Schema
1.0 declares identity/version, one pipeline name and an optional function/node prefix. Keep
the current module layout and computational plan; customize the pipeline directory/imports/
registry and rendered function/node names only. Do not rename datasets, parameters or body symbols.

CLI `plan` and `generate` accept the same `--architecture-profile` file. Python reporting and
generation accept the same object. Resolve names without modifying `ConversionPlan`, reject
import/builtin and normalized-name collisions, and preserve existing writer preflight/publication.
Explicit profiles require explicit absolute imports so naming compatibility can be checked.

For opt-in adoption, omitted profiles preserve existing output bytes and inventory. Explicit
profiles add a normalized configuration hash and task/source-to-generated-name manifest.
The report exposes that same configuration identity for review; a manifest is neither human
approval nor authenticated/full-byte source provenance. No profile-version registry is implied.

## Consequences

- A checked-in example can be applied repeatedly without executing templates or adding dependencies.
- The default and customized project retain task bodies/interfaces, dataset versions, configuration
  and observable behavior on controlled tests, including the complete draft pilot with real CSV.
- Broader enterprise rules (mandatory stages, naming all datasets, contracts, CI, tracking) and
  multi-pipeline decomposition are future contracts, not implied by this initial capability.
- No `ProjectSpec`, greenfield generator, new backend or live model experiment is required here.
- Existing review status and historical benchmark measurements are preserved.

## Alternatives considered

- **Rewrite the plan's task names:** also changes source-derived dataset versions/parameter
  identities and risks confusing provenance with architectural presentation.
- **Free-form templates or Python hooks:** unnecessary execution/dependency surface for two conventions.
- **Implement all enterprise profile rules now:** lacks concrete compatibility and acceptance cases.
- **Always emit new metadata for legacy conversion:** would change existing output inventories
  before the user opts into the profile boundary.
