# ADR 0025: explicit procedural regression contracts

[Documentation index](../README.md)

Status: accepted, 2026-11-19, within the authorized procedural delivered-test increment.

Procedural notebook nodes can return pandas objects, arrays and estimators. Reusing the
functional JSON-only schema or capturing notebook outputs would blur independent oracles,
runtime observations and inferred behavior.

Use a separate bounded notebook contract with supplied CSV fixtures and closed finite
representations for JSON, numeric scalars, arrays and flat pandas values. Bind original task
IDs and output names through the backend's actual dataset naming and profile resolution.
Require source facts/accounting and use the existing writer. The API, CLI and local settings
share this implementation; no transformation logic moves into the interface.

Do not serialize trained models or infer missing expectations. Publish explicit gaps,
distinguishing exception-only cases from positive observations. Keep default generation and
functional contract versions unchanged. Running shipped pytest remains a separate execution
step, without a converter dependency or automatic consent for a real pilot.

See the [implemented contract](../reference/generated-notebook-tests.md) for validation,
budgets, standalone execution and remaining limitations.

## Follow-up: isolated bootstrap, 2026-11-20

Extend the fixed-example developer/CI bootstrap with two procedural profile variants, reusing
its wheel installation and source-free execution boundary. Keep the ordinary Kedro CLI check;
observe memory-only results through a checker-owned SequentialRunner subclass selected by a
second CLI invocation. A separate in-memory calculation mutation must fail that observer after
runner completion. This adds verification evidence, not a new runtime API, result serializer,
generated application hook or execution consent. Static generation/review snapshots stay intact.
