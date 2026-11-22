import { strict as assert } from "node:assert";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import * as path from "node:path";
import { test } from "node:test";
import type { Envelope } from "../src/bridge";
import {
  decodeExecutionEvidence,
  importedEvidence,
  previewArtifacts,
  readLocalReport,
  summaryGroups,
  summaryMarkdown,
  type SummaryInput,
} from "../src/summary";
import { declaredJourney } from "./summary-fixture";

function input(): SummaryInput {
  const result: Envelope = {
    schema_version: "1.0",
    operation: "plan",
    status: "planned",
    execution_status: "not_run",
    configuration: {
      project_root: path.resolve("synthetic"),
      source: "workflow.ipynb",
      source_kind: "notebook",
    },
    plan: { diagnostics: [{ code: "SA009", message: "External fitted alias" }] },
    files: [],
    copies: [],
  };
  return {
    result,
    artifacts: {
      "regression-coverage.json": JSON.stringify({
        schema_version: "1.0",
        execution_status: "not_run",
        pipeline_scenarios: 2,
        node_scenarios: 1,
        model_reload_checks: 2,
        missing_pipeline_outputs: ["fitted_model"],
        missing_pipeline_expectations: true,
      }),
    },
    artifactErrors: [],
    timings: [],
  };
}

test("preview summaries preserve missing expectations and cannot claim execution", () => {
  const text = summaryMarkdown(input());
  assert.match(text, /fitted\\_model/);
  assert.match(text, /missing pipeline expectations.*Yes/);
  assert.match(text, /SA009/);
  assert.match(text, /Not run by the extension/);
  assert.match(text, /Installation.*Not checked/);
  assert.doesNotMatch(text, /Reported passed/);
});

test("imported success stays separate from current validation and human savings", () => {
  const current = input();
  const content = JSON.stringify(declaredJourney());
  current.evidence = importedEvidence("evidence.json", content);
  current.timings = [
    { operation: "plan", outcome: "planned", durationMs: 245, recordedAt: "2026-11-22T00:00:00Z" },
  ];
  const groups = summaryGroups(current);
  const validation = groups.find((group) => group.title === "Validation of this conversion")!;
  assert.ok(
    validation.rows.some((row) => row.label === "Tests" && row.value.startsWith("Not run")),
  );
  const text = summaryMarkdown(current);
  assert.match(text, /Reported passed/);
  assert.match(text, /Not verified; importing does not validate the current project/);
  assert.match(text, /includes Python startup and I\/O/);
  assert.match(text, /0\.245 s/);
  assert.match(text, /Training alone.*Not measured separately/);
  assert.match(text, /Human effort \/ savings.*Not measured/);
  assert.equal(current.evidence.sha256, createHash("sha256").update(content).digest("hex"));
});

test("functional node-case maps and boolean gaps retain their original report meaning", () => {
  const current = input();
  current.artifacts["regression-coverage.json"] = JSON.stringify({
    schema_version: "1.0",
    execution_status: "not_run",
    pipeline_scenarios: 1,
    node_scenarios: { prepare: 1, train: 0 },
    missing_node_expectations: ["train"],
    missing_memory_result_expectations: true,
    missing_pipeline_expectations: false,
  });
  const text = summaryMarkdown(current);
  assert.match(text, /Node scenarios: prepare.*1/);
  assert.match(text, /Node scenarios: train.*0/);
  assert.match(text, /missing memory result expectations.*Yes/);
  assert.match(text, /missing pipeline expectations.*No/);
  assert.match(text, /Tests.*Not run by the extension/);
});

for (const [label, mutate] of Object.entries<(data: Record<string, any>) => void>({
  "aggregate format": (data) => {
    delete data.case;
  },
  "coerced status": (data) => {
    data.status = ["passed"];
  },
  "coerced stage": (data) => {
    data.stages[0].status = ["passed"];
  },
  "unmatched exit code": (data) => {
    data.stages[0].returncode = 1;
  },
  "false control success": (data) => {
    data.stages.at(-1).returncode = 0;
  },
  "duplicate stage": (data) => {
    data.stages[0] = data.stages[1];
  },
  "missing stage": (data) => {
    data.stages.pop();
  },
  "missing duration": (data) => {
    delete data.stages[0].duration_ns;
  },
  "negative duration": (data) => {
    data.elapsed_ns = -1;
  },
  "string duration": (data) => {
    data.elapsed_ns = "100";
  },
  "unsafe duration": (data) => {
    data.elapsed_ns = Number.MAX_SAFE_INTEGER + 1;
  },
  "wrong test count": (data) => {
    data.passed_tests = 10;
  },
  "missing tests": (data) => {
    delete data.passed_tests;
  },
  "inferred savings": (data) => {
    data.human_savings = 42;
  },
  "scientific approval": (data) => {
    data.independent_scientific_oracle = true;
  },
  "changed source": (data) => {
    data.source_unchanged = false;
  },
  "wrong source hash": (data) => {
    data.source_inventory["workflow.ipynb"] = "invalid";
  },
})) {
  test(`execution import rejects ${label}`, () => {
    const data = declaredJourney();
    mutate(data);
    assert.throws(() => decodeExecutionEvidence(JSON.stringify(data)));
  });
}

test("partial, failed and interrupted attempts stay visible without made-up timings", () => {
  for (const status of ["started", "failed", "interrupted"]) {
    const data = declaredJourney();
    data.status = status;
    data.stages = [];
    delete data.elapsed_ns;
    delete data.passed_tests;
    data.error = { message: "Installation unavailable" };
    const current = input();
    current.evidence = importedEvidence("partial.json", JSON.stringify(data));
    const text = summaryMarkdown(current);
    assert.match(text, new RegExp(`Reported ${status}`));
    assert.match(text, /Total elapsed.*Not recorded/);
    assert.match(text, /Installation unavailable/);
  }
});

test("malformed static reports remain unavailable and never promote validation", () => {
  for (const content of ["{", '{"schema_version":"1.0","execution_status":"passed"}']) {
    const current = input();
    current.artifacts["regression-coverage.json"] = content;
    const text = summaryMarkdown(current);
    assert.match(text, /Unavailable/);
    assert.match(text, /Tests.*Not run by the extension/);
  }
});

test("report text cannot introduce Markdown commands, HTML or multiline entries", () => {
  const current = input();
  current.artifactErrors = ["[click](command:evil)\n<script>alert(1)</script>"];
  const text = summaryMarkdown(current);
  assert.doesNotMatch(text, /\[click\]\(command:evil\)/);
  assert.doesNotMatch(text, /<script>/);
  assert.doesNotMatch(text, /\n<script>/);
});

test("only known preview report files are displayed as static evidence", () => {
  const current = input();
  current.result!.files = [
    { path: "regression-coverage.json", content: "report", sha256: "a".repeat(64) },
    { path: "arbitrary.json", content: "ignore", sha256: "b".repeat(64) },
  ];
  assert.deepEqual(previewArtifacts(current.result!), { "regression-coverage.json": "report" });
});

test("local report reads are bounded, UTF-8 and read only", async () => {
  const base = path.resolve(__dirname, "../../../../generated");
  await fs.mkdir(base, { recursive: true });
  const directory = await fs.mkdtemp(path.join(base, "extension-summary-"));
  try {
    const filename = path.join(directory, "evidence.json");
    const content = JSON.stringify(declaredJourney());
    await fs.writeFile(filename, content, "utf8");
    assert.equal(await readLocalReport(filename), content);
    assert.equal(await fs.readFile(filename, "utf8"), content);
    await assert.rejects(readLocalReport(filename, 8), /bounded regular/);
    await fs.writeFile(filename, Buffer.from([0xff, 0xfe]));
    await assert.rejects(readLocalReport(filename));
    await assert.rejects(readLocalReport(directory));
  } finally {
    assert.equal(path.dirname(path.resolve(directory)), base);
    assert.ok(path.basename(directory).startsWith("extension-summary-"));
    await fs.rm(directory, { recursive: true });
  }
});
