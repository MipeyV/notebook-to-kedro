import { strict as assert } from "node:assert";
import { promises as fs } from "node:fs";
import * as path from "node:path";
import { mock } from "node:test";
import * as vscode from "vscode";
import type { ProjectController } from "../src/extension";
import type { ValidationOutcome } from "../src/validation";

/** Execute only the copied tiny synthetic case, after exercising cancellation at confirmation. */
export async function checkGeneratedValidation(
  root: string,
  python: string,
  controller: ProjectController,
): Promise<void> {
  const base = path.join(root, "model_reload");
  const configuration = vscode.Uri.file(path.join(base, "project.json"));
  const generated = path.join(base, "generated/project");
  const attempt = path.join(base, "generated/validation");
  const command = (name: string) => vscode.commands.executeCommand(`notebookToKedro.${name}`);
  await vscode.commands.executeCommand("notebookToKedro.selectConfiguration", configuration);
  const prompt = mock.method(
    vscode.window,
    "showInputBox",
    async (options?: vscode.InputBoxOptions) =>
      options?.title === "Validation worker timeout in seconds"
        ? "60"
        : options?.title?.startsWith("New validation")
          ? "generated/validation"
          : "generated/project",
  );
  const confirm = mock.method(vscode.window, "showWarningMessage", async () => "Generate");
  const picker = mock.method(
    vscode.window,
    "showOpenDialog",
    async (options?: vscode.OpenDialogOptions) => [
      vscode.Uri.file(options?.canSelectFolders ? generated : python),
    ],
  );
  try {
    assert.equal(((await command("generate")) as { status: string }).status, "generated");
    confirm.mock.mockImplementation(async () => undefined);
    assert.equal(await command("validateGenerated"), undefined);
    await assert.rejects(fs.stat(attempt));
    const review = vscode.window.activeTextEditor!.document;
    assert.match(review.getText(), /validation-plan/);
    const before = review.getText();
    await vscode.commands.executeCommand("type", { text: "changed" });
    assert.equal(review.getText(), before);
    confirm.mock.mockImplementation(async () => "Run tests");
    const outcome = await vscode.commands.executeCommand<ValidationOutcome>(
      "notebookToKedro.validateGenerated",
    );
    assert.ok(["passed", "environment_missing"].includes(outcome.status), JSON.stringify(outcome));
    const report = JSON.parse(await fs.readFile(path.join(attempt, "report.json"), "utf8"));
    assert.equal(report.status, outcome.status);
    assert.equal(report.original_unchanged, true);
    assert.equal(report.snapshot_unchanged, true);
    const summary = (await controller.showSummary())!.getText();
    assert.match(summary, /Explicit generated-project test run/);
    assert.ok(summary.includes(outcome.status.replaceAll("_", "\\_")));
    assert.match(summary, /static not\\_run manifests unchanged/);
    await command("showValidationReport");
    const displayedReport = vscode.window.activeTextEditor!.document;
    assert.equal(displayedReport.uri.scheme, "notebook-to-kedro-preview");
    assert.equal(JSON.parse(displayedReport.getText()).plan_sha256, outcome.plan_sha256);
    await command("showValidationLog");
    const log = vscode.window.activeTextEditor!.document;
    assert.equal(log.uri.scheme, "notebook-to-kedro-preview");
    assert.match(log.getText(), outcome.status === "passed" ? /passed/ : /Missing distributions/);
    await command("inspect");
    assert.doesNotMatch(
      (await controller.showSummary())!.getText(),
      /Explicit generated-project test run/,
    );
    console.log(
      `Generated validation host checks passed: confirmation cancel, review, explicit ${outcome.status}, durable evidence, read-only logs and snapshot reset.`,
    );
  } finally {
    picker.mock.restore();
    confirm.mock.restore();
    prompt.mock.restore();
  }
}
