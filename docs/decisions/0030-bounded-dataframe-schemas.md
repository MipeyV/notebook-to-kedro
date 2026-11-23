# ADR 0030 - Bounded notebook DataFrame metadata schemas

Date: 2026-11-23

Status: accepted

## Context

Dataset class checks accept DataFrames with incompatible columns/dtypes. ML review needs
explicit metadata constraints without inference, data repair, new analysis dependencies,
source instruction changes or confusion between prepared checks and execution evidence.

## Decision

Extend the independent notebook type declaration to schema 1.1 with immutable ordered frame
schemas bound to declared DataFrame dataset versions. Validate names, finite dtype labels,
extra-column booleans and per-frame/total budgets before publication. Keep 1.0 input/output
unchanged. Reuse enforce_node_types and compose readonly metadata checks with the existing
class validator in the self-contained generated helper, with NVS001/NVS002 ValueError errors.

Closed schemas require exact ordered columns; allowing extras preserves declared relative
order. Actual labels must be unique flat strings; dtype labels compare exactly. No metadata
inference, dtype constructor evaluation, coercion, reordering or row-value inspection occurs.
Report schema policies and gaps separately, preserving generation-time not_run status.

## Consequences

DataFrame metadata can be enforced without altering original bodies, reader options, return
identity or satisfied-boundary source errors. Stricter metadata may fail before original asserts;
new opt-in regression expectations must acknowledge that ordering while original fixtures,
oracles and experiment observations remain intact. The credit example constrains selected
numeric metadata and leaves immature target handling to source rules.

Index/row constraints, null counts, value ranges, categories/storage details, array/Series
schemas, fitted-state checks, custom dtype adapters, functional workflow schemas, scientific
acceptance, source assertion repair and execution authorization remain outside this slice.
