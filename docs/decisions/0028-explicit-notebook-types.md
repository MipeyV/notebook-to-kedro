# ADR 0028 - Explicit notebook dataset type declarations

Date: 2026-11-22

Status: accepted

## Context

Generated Google-style documentation and annotations currently expose unresolved runtime
types as Any. MLOps review needs meaningful DataFrame/model interfaces without pretending
that static notebook conversion inferred schemas, executing source or changing business logic.

## Decision

Add an optional independently versioned notebook type declaration, pinned to source bytes
and keyed by actual generated dataset identities. Accept only a finite vocabulary of Python
scalars, pandas/NumPy objects and two sklearn model classes. Validate JSON/direct construction,
source identity and graph membership before the shared writer. Propagate each declared type
to its producer return slot and consumers, retaining versioned redefinitions and profile wiring.

Compose the same implementation through the notebook API, generate CLI and local project
settings/preview/generation used by VS Code. Analysis remains free of ML imports; generated
runtime imports are fixed and use collision-avoiding aliases. An explicit report preserves
untyped gaps and unverified runtime status. Default output, source bodies, assertions, optional
provider contracts and functional source preservation remain unchanged.

## Consequences

Operator declarations can replace Any without a generic ProjectSpec or type-inference system.
They are not observed source facts or execution evidence. Incorrect semantic declarations may
still pass structural checks; no coercion or implicit repair is introduced. DataFrame schemas,
array dtype/shape, custom types, functional declaration binding, strict generated-project typing
and runtime enforcement remain outside this slice. The opt-in financial example keeps original
notebooks/data/oracles and historical measurements intact.
