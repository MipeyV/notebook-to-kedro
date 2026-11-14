import { strict as assert } from "node:assert";
import { createHash } from "node:crypto";
import * as path from "node:path";
import { test } from "node:test";
import { decodeEnvelope, engineArguments, relativeFile, type Operation } from "../src/bridge";

const configuration = {
  project_root: path.resolve("project"),
  source: "workflow.py",
  source_kind: "functional",
};
const content = "value = 1\n";
const file = {
  path: "src/project/nodes.py",
  content,
  sha256: createHash("sha256").update(content).digest("hex"),
};
const plan = {
  schema_version: "1.0",
  operation: "plan",
  status: "planned",
  configuration,
  execution_status: "not_run",
  plan: {},
  files: [file],
  copies: [],
};

test("preview transport preserves Unicode and complete file contents", () => {
  assert.deepEqual(decodeEnvelope(JSON.stringify(plan), "plan", 0).files, [file]);
  const unicode = "def café():\n    return 'étude'\n";
  const changed = {
    ...file,
    content: unicode,
    sha256: createHash("sha256").update(unicode).digest("hex"),
  };
  assert.equal(
    (
      decodeEnvelope(JSON.stringify({ ...plan, files: [changed] }), "plan", 0)
        .files![0] as typeof file
    ).content,
    unicode,
  );
});

for (const name of [
  "../escape.py",
  "/absolute.py",
  "C:relative.py",
  "\\server\\file",
  "src/../node.py",
  "",
  "src//file.py",
]) {
  test(`preview paths reject ${JSON.stringify(name)}`, () => {
    assert.equal(relativeFile(name), false);
    assert.throws(() =>
      decodeEnvelope(JSON.stringify({ ...plan, files: [{ ...file, path: name }] }), "plan", 0),
    );
  });
}

for (const [label, change] of Object.entries({
  schema: { schema_version: "2.0" },
  operation: { operation: "generate" },
  execution: { execution_status: "passed" },
  root: { configuration: { ...configuration, project_root: "relative" } },
  source: { configuration: { ...configuration, source: "../outside.py" } },
  kind: { configuration: { ...configuration, source_kind: "prompt" } },
  status: { status: "ready" },
  files: { files: null },
  hash: { files: [{ ...file, sha256: "0".repeat(64) }] },
  duplicate: { files: [file, file] },
  copies: { copies: [{ source: "data.json", destination: file.path, sha256: "0".repeat(64) }] },
  escapingCopy: {
    copies: [{ source: "../outside.json", destination: "data/input.json", sha256: "0".repeat(64) }],
  },
})) {
  test(`invalid ${label} is rejected before the UI consumes it`, () => {
    assert.throws(() => decodeEnvelope(JSON.stringify({ ...plan, ...change }), "plan", 0));
  });
}

test("blocked inspection is a usable structured result with exit code one", () => {
  const inspection = {
    ...plan,
    operation: "inspect",
    status: "blocked",
    analysis: { diagnostics: [] },
  };
  assert.equal(decodeEnvelope(JSON.stringify(inspection), "inspect", 1).status, "blocked");
  assert.throws(() => decodeEnvelope(JSON.stringify(inspection), "inspect", 0));
});

test("a generation result reports publication and unverified installation", () => {
  const generated = {
    ...plan,
    operation: "generate",
    status: "generated",
    installation_status: "not_checked",
    destination: path.resolve("project/generated"),
    files: [file.path],
  };
  assert.equal(decodeEnvelope(JSON.stringify(generated), "generate", 0).status, "generated");
  assert.throws(() =>
    decodeEnvelope(JSON.stringify({ ...generated, installation_status: "passed" }), "generate", 0),
  );
  assert.throws(() => decodeEnvelope(JSON.stringify(generated), "generate", 1));
});

test("Python arguments remain separate values, including spaces and shell characters", () => {
  const request = {
    python: path.resolve("Python with spaces/python.exe"),
    configuration: path.resolve("project with spaces/a; $(ignored).json"),
    operation: "plan" as const,
  };
  const args = engineArguments(request);
  assert.deepEqual(args.slice(0, 6), ["-I", "-X", "utf8", "-u", "-m", "notebook_to_kedro.cli"]);
  assert.equal(args.at(-1), request.configuration);
  assert.throws(() => engineArguments({ ...request, python: "python" }));
  assert.throws(() => engineArguments({ ...request, destination: "unexpected" }));
  assert.throws(() => engineArguments({ ...request, operation: "generate" }));
});

test("malformed and failed responses remain failures", () => {
  assert.throws(() => decodeEnvelope("not-json", "plan", 0));
  assert.throws(() => decodeEnvelope("null", "plan", 0));
  for (const operation of ["inspect", "plan", "generate"] as Operation[]) {
    assert.throws(() => decodeEnvelope(JSON.stringify(plan), operation, 2));
  }
});
