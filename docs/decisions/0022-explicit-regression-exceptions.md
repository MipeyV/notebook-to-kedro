# ADR 0022 - Explicit regression exception outcomes

Date: 2026-11-18

Status: accepted

## Context

Preserved helper control flow makes the frozen clipping notebook convertible, but its existing
positive JSON contract delivers 12 tests. The original acceptance requires 14, including two
source ValueError paths. Independently observing those paths does not deliver their tests.
The original blocked comparison and 12-test follow-up remain historical evidence.

## Decision

Add regression schema 1.2 with explicit inline/fixtures storage, preserving 1.0 inline and 1.1
fixture contracts. Each supplied scenario/node case has exactly one expected JSON value or
raises declaration. Exception declarations name one of seven concrete built-ins and its exact
literal message, bounded to 4 KiB UTF-8. Pipeline declarations also identify a known unprefixed
step; node declarations derive the owner from their enclosing key. No custom imports, broad
catch-all expectations, regex or subclass matching are accepted.

The generator validates data without source execution. Standalone pytest code matches concrete
type/message and, for pipelines, tracks the specified node function's exception object escaping
the sequential runner. Catalog construction and registry loading are outside that context.
The final JSON dataset must not exist in the fresh temporary workspace after an expected failure.
Node inputs are copied before the expected-exception context. Existing snapshot/path/hash/budget
and shared-writer publication rules apply to both storage modes.

## Consequences

Operators can express reviewed source failures without changing source ASTs or inferring oracles.
Generation coverage snapshots count exception declarations but still record not_run and
not_authenticated. Running pytest executes application code; the tests are not a sandbox or
general proof of business correctness, rollback, side-effect absence or concurrent-run behavior.

The new clipping contract adds the two frozen failure scenarios to unchanged positive cases.
Its original 14-test requirement can now be checked without lowering criteria. Shared mutable
fan-out, richer typed/artifact outcomes, real-project execution and pending pilot review remain
separate scopes.
