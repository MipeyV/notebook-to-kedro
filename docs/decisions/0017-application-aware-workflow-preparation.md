# ADR 0017 - Prepare orchestration with the original application project

Accepted on 2026-11-16.

[Documentation index](../README.md)

## Context

Package preparation supplies an explicit orchestration adapter for review. Application
distribution capture additionally needs the original pyproject, build inputs and source layout.
A prepared source package needs those files to feed workflow schema 1.7 and retain original
distribution metadata and source-relative provenance paths during installation.

## Decision

Extend the separate preparation definition with opt-in schema 1.1. Require an immutable
`application_project` selection using the existing pyproject/additional-file contract. Reuse
static application capture for identity, dependency declarations, project-file hashes and path
checks. Preserve the source package's path relative to its original pyproject directory in the
prepared project. Place selected original project files at their original relative paths.

Synthesize the adapter inside that preserved package layout. Manifest schema 1.1 records the
original application distribution and digest, plus prepared pyproject/package/adapter paths.
Existing source facts, declared calls, original source bindings and proposed adapter facts retain
their own provenance. Record `unreviewed_proposal` and initial `not_run` execution/build statuses.

Deduplicate selected project files already included in the package inventory. Reject target
collisions with the adapter and preparation evidence using the shared portable writer checks.
Recapture selected project files and source package before publication. Keep destination overlap
and new-directory publication rules. Supply application-specific review instructions with the copy.

The prepared project can subsequently receive an explicitly selected workflow schema 1.7
configuration. Preserve its preparation manifest and review file by selecting them as additional
application files during conversion when that provenance should travel with the generated project.
Input/result/artifact settings and expected runtime behavior remain explicit integration choices.

## Consequences

The API and existing prepare-workflow CLI support a complete application review copy. Schema 1.0
continues to describe package preparation. Synthetic tests exercise original src/lib layouts,
exact bytes, source/proposal provenance, file drift, target collisions, subsequent conversion,
installed distribution metadata and shipped regressions through standard/editable application
wheels. Installation tests reuse locked runtime dependencies. Actual environment-specific
dependency resolution and scientific/runtime expectations require their own evidence.

A prepared adapter represents a proposed addition to the application. Its creation records
neither adoption nor human approval. Real-project publication and installation follow the user's
authorized scope. Human pilot review and provider/execution contracts continue to apply to their
respective experiments.
