# ADR 0021 - Preserve structured control flow inside function bodies

[Documentation index](../README.md)

Accepted on 2026-11-18.

## Context

The frozen missing-value/clipping notebook was blocked even though its orchestration is three
explicit calls: the bodies contain loops, conditions, raises and continue. Coding agents retained
those original functions. Converting their internal paths into a new graph is unnecessary for
faithful node wrapping, but dropping local-binding checks would weaken source validation.

## Decision

Admit structured if/for/while, raise/pass and loop break/continue inside inspected functions,
retaining original body/signature ASTs and the single terminal value-return contract. No source
execution, path evaluation, body repair, new dependency or inferred node subdivision is introduced.
Existing facts/schemas remain compatible; BL104 warns that paths/iterations/termination are unknown.

Use conservative definite-local-binding analysis. If branches merge only their normal fallthrough
bindings; raise/return/break/continue stop normal flow. For targets bind inside the body. Values
introduced in a loop body/else are not promoted beyond the loop because counts and breaks are
unknown. Unsupported nested syntax, dynamic calls, mutation writes, global/call-target guards and
function-cycle checks remain in force, including in unreachable source.

The orchestration planner independently requires direct named-call assignments followed by a
final named result. Accepting inspection of a control-flow function does not approve a conditional
or iterative pipeline. Shared mutable fan-out remains unsupported. Source accounting and AST
recomputation remain mandatory before publication through the shared writer.

## Consequences

Script/notebook and default/custom profiles can wrap these helpers without changing their branch,
error, object or loop semantics. Tests compare original functions and actual registered pipelines
under sequential/threaded runners, preserving ValueError text, call order and intermediate identity.
Runtime loops can still fail or not terminate; static acceptance is not execution consent or safety.

The existing supplied-JSON contract emits 12 positive tests for the frozen example. Its two source
error paths are independently verified, not newly represented as generated exception tests. The
original comparison's 14-shipped-test criterion stays unmet and must not be silently lowered.
An explicit exception-expectation contract and fan-out need separate scopes. The original blocked
records, pilot review and financial execution authorizations remain untouched.
