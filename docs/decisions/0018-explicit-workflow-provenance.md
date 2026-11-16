# ADR 0018 - Capture original-source and installed-workflow provenance explicitly

Accepted on 2026-11-16.

[Documentation index](../README.md)

## Context

An application can query Git from its current working directory after conversion. In a generated
project that directory can belong to the engine's workspace. The source commit, published byte
identities and installed package versions need distinct observations before a benchmark trial.

## Decision

Application-aware workflow generation now publishes generation-inventory.json, schema 1.0, with
SHA-256, byte size and generated/copied origin for each published file. The inventory excludes
itself. Existing workflow configuration and plan schemas retain their versions.

Add an explicit capture-workflow-provenance API/CLI operation. Require the original Python
module, its application-aware workflow configuration, generated project, selected Python
interpreter and a new report directory. Read original Git HEAD/status from the explicit source
root, clearing inherited Git environment overrides and disabling fsmonitor hooks and optional
locks. Record the generated working directory's Git context independently when available.

Verify every recorded published file and bind original package/project/input identities to their
copied destinations. Direct source conversion must retain its selected module. For prepared
orchestration, recompute the existing preparation against current original source and compare its
complete manifest and actual adapter bytes. Recover keyword-binding order from ordered step
bindings and require the same declaration mapping, preserving existing serialized preparations.

Run a fixed standard-library metadata probe through the explicitly selected isolated interpreter.
Require one installed distribution for each original/generated name and record declared and
observed versions, including normalized version text. Record all observed distribution versions.
Recapture source, inputs, Git and published identities before
publishing a new workflow-provenance.json bundle through the shared writer. Reject source-package
and generated-project destination overlaps and existing destinations. Reads of on-disk JSON
evidence are bounded to 16 MiB per file. Git commands and the interpreter probe have explicit timeouts.

Report schema 1.0 records captured source Git, exact source/generation identities, declared
preparation lineage, runtime metadata, ambient execution Git and pending review/execution
status. Source accounting remains enforced at the normal conversion boundary. This operation
checks listed publication bytes and observes installed metadata. Files added after generation,
application behavior, runtime import selection and result semantics require their own evidence.
The record's observations come from operator-controlled local files and the selected runtime.

## Consequences

Trusted tests distinguish two Git repositories, observe dirty source contexts, reject file and
binding drift and check standard/editable installations with prepared and direct sources. Capture
remains separate from a benchmark runner and its consent. Existing application outputs can be
associated with the resulting report in a later explicitly scoped trial. Scientific expectations
and the independent human pilot review remain pending.

The authorized private real-source check binds 29 original files to 50 published files and
observes 61 installed distributions. The original and execution-directory commits differ and
are identified in separate fields. Actual benchmark execution remains pending.
