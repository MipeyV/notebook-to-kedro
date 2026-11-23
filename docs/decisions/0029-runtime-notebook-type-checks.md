# ADR 0029 - Optional runtime notebook dataset class checks

Date: 2026-11-23

Status: accepted

## Context

Source-bound type declarations improve generated signatures but do not reject incompatible
values. Runtime checks must be explicit, independently usable from the converter, effective
under Python optimization and separate from source assertions, business validation and evidence.

## Decision

Add a notebook-only enforce_node_types boolean outside the unchanged type declaration schema.
Require a valid declaration/source audit before shared publication. Render stdlib decorators
and a private runtime helper around only callables with declared boundaries. Validate inputs
before the source call and output classes/tuple slots before returning to Kedro. Exact builtin
scalars and isinstance object checks use only the existing finite class vocabulary.

Raise explicit NTV001/NTV002 TypeError diagnostics without coercion or value dumps. Preserve
source body ASTs, names/signatures/docstrings, result identity and original exceptions. Default
and annotation-only output stay unchanged. API/CLI/local settings share the same implementation;
the interface does not own validation rules and generation does not execute the source.

## Consequences

Prepared checks can enforce declared classes in ordinary runs and remain active under -O.
Source asserts remain intact and optimization-sensitive. No columns/dtypes/array shapes,
business values, fitted-state checks, side-effect rollback, security sandbox, source repair,
new analysis dependency or functional-workflow runtime contract is introduced. The report
describes prepared policies/checked tasks while generation-time runtime validation stays
not_run. Actual execution evidence remains separate; annotations and passing tests do not
approve private/provider experiments or scientific acceptance.
