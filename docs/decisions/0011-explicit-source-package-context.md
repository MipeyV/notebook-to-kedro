# ADR 0011: preserve one explicit local source package

Status: accepted, 2026-11-15.

[Documentation index](../README.md)

## Context

Relocating a selected Python module to `workflow_source.py` changes import context and cannot
preserve its local helpers, internal types or file-relative resources. A real workflow proposal
needs these boundaries before richer data and artifact contracts can be addressed. Discovering
an arbitrary project or silently installing dependencies would exceed that bounded need.

## Decision

Opt-in workflow schema 1.3 requires an explicit `source_package` relative to the project root.
Accept one regular Python package containing the selected `.py` workflow module. Retain its
original import name and copy all regular source/resource files byte-for-byte through the
shared writer. Include both packages in the generated wheel. Reject namespace packages,
namespace collisions, links/reparse points, special and compiled files; record excluded caches
and enforce bounded counts/sizes as specified in the workflow reference.

Capture immutable file hashes, sizes, Python AST hashes and syntactic import references.
Compile Python without importing/executing it. Resolve relative import base modules inside
the captured package; do not claim imported-symbol or runtime dependency resolution. Bind
selected-source facts to its actual module and document hash, recompute functional analysis,
and recapture the inventory before rendering. Changed/added content blocks the captured plan.
Concurrent filesystem mutation remains outside the existing writer guarantees.

Keep supported-subset analysis on the selected module. Supporting modules are opaque retained
source; do not infer cross-module node wiring or change business logic. Package-aware analysis
and plan exports use schema 1.2; the inventory uses schema 1.0. Old standalone/notebook modes,
source-only inspection and local operation envelopes retain their contracts. UI composition
uses existing file/copy previews and contains no import/transformation rules.

## Consequences

Relative imports, package-internal type identities and file-relative resources can survive
generation. Synthetic tests check real Kedro execution, default/custom profiles, pipeline
regressions and source-free execution from an unpacked wheel. Missing typed node oracles stay
reported; an unpacked wheel test does not establish fresh dependency installation.

The generated distribution owns the original import namespace. Third-party distribution
requirements/versions are not inferred or installed. Original project metadata, lockfiles and
external resources outside the package are not reconstructed; code querying the original
distribution metadata may still fail. Namespace packages, multiple roots, automatic entrypoint
creation, typed persistent I/O and application artifact ownership need separate contracts.
Static capture never approves real-project execution or the pending human pilot review.
