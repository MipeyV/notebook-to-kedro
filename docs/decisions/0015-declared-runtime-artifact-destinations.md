# ADR 0015: check declared runtime artifact destinations before their owning call

Status: accepted, 2026-11-16.

[Documentation index](../README.md)

## Context

An application can return an opaque result while writing its own artifacts from a path in a
candidate mapping. Project publication is separate from those runtime effects. Precreating or
reserving the destination would break an application that requires a new directory. Rewriting
business functions, guessing serializers or adding automatic retries would change its behavior.

## Decision

Opt-in workflow schema 1.6 requires an explicit artifact_destinations mapping, possibly empty.
Each declaration names a flat parameter, key and exact path under `artifacts/<run_name>`. Permit
up to eight distinct destinations; reject nonportable names, nested/external paths and mismatches
with configured parameter values. Derive the owner from the mapping's single consuming call.
This records declared ownership, not proof of where the function actually writes.

Keep source functions and generated business wrappers unchanged. Compose a generated callable
around each owning registered pipeline node, including its existing source-order adapter.
Immediately before invoking that callable, check the actual mapping value, matching project
policy marker, parent directory kind and absence of the target. Refuse existing files/directories,
links/reparse points and parameter/policy drift. Use the current project working directory as
the runtime root, with an exact-byte policy digest checked against the generated module.

Render a bounded 64 KiB `artifact-policy.json` runtime contract and a standard-library-only
helper in the generated package. Plan/manifest schema 1.5 separates declarations, derived owners,
runtime checks not yet run, unverified effect completeness and no reservation. Local operations
remain static and do not check runtime existence in the original source project.

Do not create, reserve, delete or retry application destinations. Let original code perform its
own existence check and writes. If it fails after a partial write, leave owned contents intact.
There is no filesystem lock between checking and the application call; concurrent mutation is
outside the guarantee. Direct function calls bypass the registered pipeline adapter. This is
not a sandbox, proof of all effects, authenticated approval or execution consent.

Existing JSON regression contracts do not define artifact fixtures/comparators; reject them
for declared artifacts and retain explicit missing-artifact-expectation gaps. Preserve faithful
legacy conversion and source/parameter/result contracts independently.

## Consequences

Trusted synthetic sequential/threaded runs check ordered loaders, owned writes and typed memory
results under default/custom profiles, including raw-file inputs. Negative controls check binding
and marker drift, pre-existing targets, links, partial failure and no retry/cleanup. Callable
pickling is separate evidence, not a process-runner portability claim.

Actual data/protocol compatibility, scientific expectations, dependency/distribution metadata,
durable result serializers and broader artifact layouts remain separate scopes. A real-project
proposal stays unreviewed and unexecuted; actual human pilot review remains pending.
