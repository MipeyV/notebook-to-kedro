import { strict as assert } from "node:assert";
import * as path from "node:path";
import { test } from "node:test";
import {
  decodeValidationPlan,
  decodeValidationOutcome,
  validationArguments,
  prepareValidation,
  runValidation,
  type ValidationRequest,
  type ValidationPlan,
} from "../src/validation";
import { summaryMarkdown } from "../src/summary";

function request(): ValidationRequest {
  return {
    enginePython: path.resolve("engine python"),
    python: path.resolve("runtime python"),
    configuration: path.resolve("config ; $name.json"),
    project: path.resolve("generated project"),
    output: "generated/attempt",
    timeout: 30,
  };
}
function plan(): ValidationPlan {
  return {
    schema_version: "1.0",
    operation: "validation-plan",
    execution_status: "not_run",
    plan_sha256: "a".repeat(64),
    project: request().project,
    python: request().python,
    output: path.resolve("generated/attempt"),
    timeout_seconds: 30,
    files: [{ path: "tests/test_notebook_regressions.py", sha256: "b".repeat(64), size: 8 }],
    tests: ["tests/test_notebook_regressions.py"],
    execution_notice: "Tests execute project code.",
  };
}
function outcome(): Record<string, any> {
  return {
    schema_version: "1.0",
    operation: "validate",
    status: "passed",
    plan_sha256: plan().plan_sha256,
    project: plan().project,
    python: plan().python,
    output: plan().output,
    duration_ns: 100_000_000,
    worker_duration_ns: 80_000_000,
    returncode: 0,
    tests: { tests: 2, passed: 1, failed: 0, errors: 0, skipped: 1 },
    environment: { missing: [] },
    original_unchanged: true,
    snapshot_unchanged: true,
    inputs_unchanged: true,
    python_unchanged: true,
    log: "tests.log",
    log_truncated: false,
    error: null,
  };
}

test("validation arguments keep engine/runtime/project choices separate and require explicit execution approval", () => {
  const review = validationArguments(request());
  assert.equal(review[7], "validation-plan");
  assert.ok(review.includes(request().configuration));
  assert.ok(review.includes(request().python));
  assert.ok(!review.includes("--approved-sha256"));
  const run = validationArguments(request(), plan().plan_sha256);
  assert.equal(run[7], "validate");
  assert.ok(run.includes("--cancellable-stdin"));
  assert.equal(run.at(-2), plan().plan_sha256);
  assert.throws(() => validationArguments({ ...request(), python: "python" }));
  assert.throws(() => validationArguments({ ...request(), timeout: 601 }));
  assert.throws(() => validationArguments(request(), "invalid"));
});

test("review remains static and rejects incompatible runtime/project/budget metadata", () => {
  assert.equal(decodeValidationPlan(JSON.stringify(plan()), request()).execution_status, "not_run");
  for (const change of [
    { execution_status: "passed" },
    { project: path.resolve("other") },
    { python: path.resolve("other") },
    { timeout_seconds: 1 },
    { plan_sha256: "bad" },
    { files: [] },
    { files: [{ path: "test", sha256: "bad", size: -1 }] },
    { tests: ["arbitrary.py"] },
  ]) {
    assert.throws(() => decodeValidationPlan(JSON.stringify({ ...plan(), ...change }), request()));
  }
});

test("passing results require matching review, positive tests and unchanged captured inputs", () => {
  assert.equal(decodeValidationOutcome(JSON.stringify(outcome()), plan(), 0).status, "passed");
  const changes = [
    { plan_sha256: "b".repeat(64) },
    { project: path.resolve("other") },
    { output: path.resolve("other") },
    { python: path.resolve("other") },
    { duration_ns: -1 },
    { tests: null },
    { tests: { tests: 0, passed: 0, failed: 0, errors: 0, skipped: 0 } },
    { tests: { tests: 2, passed: 2, failed: 1, errors: 0, skipped: 0 } },
    { original_unchanged: false },
    { snapshot_unchanged: false },
    { inputs_unchanged: false },
    { python_unchanged: false },
    { returncode: 1 },
    { error: "failed" },
    { environment: { missing: ["pytest"] } },
    { environment: null },
    { log: "../other.log" },
    { log_truncated: "false" },
    { status: "unknown" },
  ];
  for (const change of changes)
    assert.throws(() =>
      decodeValidationOutcome(JSON.stringify({ ...outcome(), ...change }), plan(), 0),
    );
  assert.throws(() => decodeValidationOutcome(JSON.stringify(outcome()), plan(), 1));
});

for (const status of [
  "failed",
  "environment_missing",
  "timed_out",
  "canceled",
  "runner_error",
  "no_passing_tests",
  "cleanup_incomplete",
  "drifted",
]) {
  test(`${status} is an outcome, never an implied passing test run`, () => {
    const result = decodeValidationOutcome(
      JSON.stringify({ ...outcome(), status, tests: null, returncode: null, environment: null }),
      plan(),
      1,
    );
    const text = summaryMarkdown({
      validation: result,
      artifacts: {},
      artifactErrors: [],
      timings: [],
    });
    assert.match(text, /Explicit generated-project test run/);
    assert.ok(text.includes(status.replaceAll("_", "\\_")));
    assert.doesNotMatch(text, /Supplied tests: passed/);
    assert.match(text, /scientific acceptance not established/);
  });
}

test("pre-launch cancellation never starts an execution", async () => {
  const controller = new AbortController();
  controller.abort();
  const current = { ...request(), signal: controller.signal };
  await assert.rejects(prepareValidation(current), /canceled before launch/);
  await assert.rejects(runValidation(current, plan()), /canceled before launch/);
});

test("real test outcomes stay separate from static manifests and imported evidence", () => {
  const result = decodeValidationOutcome(JSON.stringify(outcome()), plan(), 0);
  const text = summaryMarkdown({
    validation: result,
    artifacts: {},
    artifactErrors: [],
    timings: [],
  });
  assert.match(text, /Supplied tests: passed.*1/);
  assert.match(text, /static not\\_run manifests unchanged/);
  assert.match(text, /Constraints not evaluated; no installation performed/);
});
