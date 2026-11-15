# ADR 0013: stage raw file references with declared sibling sidecars

Status: accepted, 2026-11-15.

[Documentation index](../README.md)

## Context

Domain loaders may accept file paths and construct typed objects while validating associated
metadata. Loading a protocol as a generic JSON dictionary or replacing a snapshot reader with
a DataFrame dataset would change that boundary. Existing workflow inputs deserialize JSON
values and cannot faithfully represent these path arguments.

## Decision

Opt-in workflow schema 1.4 inherits explicit package preservation/source ordering and requires
a separate `file_inputs` mapping. Each immutable reference declares a primary path and an
explicit list of up to 16 sibling sidecars, including an empty list. Keep existing JSON `inputs`
independent and require disjoint JSON/file/parameter names.

Paths are normalized contained POSIX paths relative to the project root. Reject missing files,
directories, links, reparse points and special files. Hash raw bytes in bounded chunks, with
256 MiB total across all declared references. Do not decode data or invoke application readers.
Bind the captured inventory to planning and recapture it before rendering. Plan schema 1.3 and
manifest destinations distinguish `hashed_not_loaded` evidence from unverified domain semantics.

Copy each bundle to `data/01_raw/<argument>/`, preserving original filenames. Pass the primary
relative path string through an assign-mode MemoryDataset; leave domain loading/validation in
the original node function. Ordinary Kedro execution uses the generated project as its working
directory. Runtime byte-hash enforcement is not performed. Source filenames/contents remain
unchanged, but absolute locations relocate to the generated project as explicitly configured.

Reuse the writer and local copy previews; preserve legacy workflow JSON/serialization and
analysis/local operation schemas. No Kedro or data reader becomes an engine runtime dependency.
Existing JSON regression contracts do not define file fixtures: reject their use for references
and retain explicit missing-file-fixture gaps, rather than fabricating serialized test inputs.

## Consequences

Application loaders can construct typed intermediate objects from staged files/sidecars while
the engine remains deterministic and execution-free. Synthetic evidence covers sequential and
threaded source ordering, identity/type preservation, unchanged reader ASTs/bytes, sidecar
errors and local/VS Code previews. The fixture uses text plus JSON metadata, not a Parquet
compatibility claim. Hashing a file does not verify a scientific dataset/protocol fingerprint.

Sidecars must be explicitly declared siblings; nested layouts, implicit discovery, external or
remote files and broader file-fixture regression contracts need separate scopes. Final outputs
remain explicitly JSON-compatible; typed result persistence and application-owned runtime
artifact policies remain unresolved. No real-project generation, execution or pilot approval
follows from this input contract.
