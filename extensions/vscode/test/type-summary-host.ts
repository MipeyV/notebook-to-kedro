import { strict as assert } from "node:assert";
import { promises as fs } from "node:fs";
import * as path from "node:path";
import { mock } from "node:test";
import * as vscode from "vscode";
import type { Envelope } from "../src/bridge";
import type { ProjectController } from "../src/extension";

/** Real static engine reports, including post-publication reads; never execute the ML source. */
export async function checkTypeSummary(
  root: string,
  project: ProjectController,
  command: (name: string, ...args: unknown[]) => Thenable<Envelope | undefined>,
): Promise<void> {
  const directory = path.join(root, "credit_pipeline");
  for (const [settings, expected] of [
    ["project-typed.json", /Runtime enforcement.*Not requested/],
    ["project-checked.json", /Runtime enforcement.*Prepared; not run/],
    ["project-schema-checked.json", /Tasks with metadata checks.*task-0001, task-0009/],
  ] as const) {
    await command("selectConfiguration", vscode.Uri.file(path.join(directory, settings)));
    assert.equal((await command("preview"))?.status, "planned");
    const text = (await project.showSummary())!.getText();
    assert.match(text, /Declared dataset classes.*28/);
    assert.match(text, /Type: fitted\\_model.*sklearn.pipeline.Pipeline/);
    assert.match(text, /Untyped datasets.*numeric\\_columns/);
    assert.match(text, expected);
    assert.match(text, /Runtime type validation.*Not run/);
    assert.doesNotMatch(text, /Type report.*Unavailable/);
  }
  const summary = (await project.showSummary())!.getText();
  assert.match(summary, /Ordered columns: raw.*snapshot\\_month: int64; followup\\_months: int64/);
  assert.match(summary, /Declared DataFrames without schemas.*X\\_test/);
  assert.ok(
    project.getChildren().some((item) => item.label === "Declared dataset types and schemas"),
  );

  const prompt = mock.method(vscode.window, "showInputBox", async () => "generated/schema-summary");
  const confirmation = mock.method(vscode.window, "showWarningMessage", async () => "Generate");
  try {
    assert.equal((await command("generate"))?.status, "generated");
    const published = (await project.showSummary())!.getText();
    assert.match(published, /Declared DataFrame schemas.*2/);
    assert.match(published, /Runtime enforcement.*Prepared; not run/);
    assert.match(published, /Published files/);
    const reportPath = path.join(directory, "generated/schema-summary/node-types.json");
    const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
    assert.equal(report.runtime_type_validation, "not_run");
    assert.equal(report.dataframe_schema_validation, "not_run");

    prompt.mock.mockImplementation(async () => "generated/schema-summary-read-failure");
    const originalOpen = fs.open;
    const failure = mock.method(fs, "open", async (...args: Parameters<typeof fs.open>) => {
      if (String(args[0]).endsWith("node-types.json")) throw new Error("Type report read refused");
      return originalOpen(...args);
    });
    try {
      assert.equal((await command("generate"))?.status, "generated");
      const text = (await project.showSummary())!.getText();
      assert.match(text, /Type report read refused/);
      assert.match(text, /Type report.*Not available/);
      assert.match(text, /Supplied regression report.*Available/);
      assert.ok(
        (
          await fs.stat(path.join(directory, "generated/schema-summary-read-failure"))
        ).isDirectory(),
      );
    } finally {
      failure.mock.restore();
    }
  } finally {
    prompt.mock.restore();
    confirmation.mock.restore();
  }
}
