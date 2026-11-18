# ADR 0020 - Bounded JSON scenario fixtures for delivered tests

[Documentation index](../README.md)

Accepted on 2026-11-18.

## Context

The eight-step comparison notebook passes functional inspection, but its explicit regression
contract exceeds 64 KiB even after compaction. Expectations must stay supplied and complete;
fixture provenance and publication need explicit bounds instead of unbounded inline metadata.

## Decision

Keep schema 1.0 unchanged. Add regression schema 1.1: a 64 KiB manifest lists 1-100 relative JSON
scenario paths and raw SHA-256 identities. Each file holds one complete existing scenario object,
bounded to 1 MiB with an 8 MiB aggregate budget and existing resolved depth/schema/binding checks.
Reject escaping, linked/reparse and nonregular sources. No recursive references or new analysis
dependency is introduced.

The loader captures immutable UTF-8 text with the manifest; direct construction validates the
same captured tuple. Original declarations and fresh resolved values remain separate. Generation
writes captured text through the shared private project writer without reopening source fixtures.
Local planning/generation reload on each request. Shipped pytest suites validate contained
digest-named copies, byte budgets and hashes before application imports. Reports retain source
references and generated paths/identities. Existing inline output stays unchanged.

## Consequences

The eight-step source/expectations can be reused in a new fixture-backed run while preserving the
original blocked experiment. Runtime/code/oracle negative controls and the offline coverage gate
protect delivery. Raw pins include line endings; example fixtures use LF. Direct callers reload
to observe source changes. No filesystem lock, race-proof capture, inferred oracle, authenticated
review, business proof, new runtime consent or provider is added.

Finite-JSON comparisons, unsupported helper control flow/fan-out, raw file-reference fixtures,
typed intermediates and artifact expectations retain earlier contracts. Further formats need
concrete evidence rather than an empty test framework.
