import { strict as assert } from "node:assert";
import { promises as fs } from "node:fs";
import * as path from "node:path";
import { mock } from "node:test";
import * as vscode from "vscode";
import type { Envelope, PreviewFile } from "../src/bridge";
import type { ProjectController } from "../src/extension";

export async function run(): Promise<void> {
  const root = process.env.NTK_TEST_WORKSPACE!;
  const python = process.env.NTK_TEST_PYTHON!;
  assert.ok(root && python, "The host test requires a private workspace and an engine interpreter");
  const extension = vscode.extensions.getExtension<ProjectController>("mipeyv.notebook-to-kedro");
  assert.ok(extension, "Extension must be discoverable through its real manifest");
  const project = await extension.activate();
  const command = async (name: string, ...args: unknown[]) =>
    vscode.commands.executeCommand<Envelope | undefined>(`notebookToKedro.${name}`, ...args);
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "project.json")));
  await command("selectPython", vscode.Uri.file(python));
  const inspection = await command("inspect");
  assert.equal(inspection?.status, "inspected");
  assert.ok(project.getChildren().some((item) => item.label === "Source"));
  const preview = await command("preview");
  assert.equal(preview?.status, "planned");
  const file = (preview!.files as PreviewFile[]).find((item) => item.path.endsWith("nodes.py"))!;
  const document = await project.openPreview(file);
  assert.equal(document.uri.scheme, "notebook-to-kedro-preview");
  assert.equal(document.getText(), file.content);
  await vscode.window.showTextDocument(document);
  await vscode.commands.executeCommand("type", { text: "changed" });
  assert.equal(document.getText(), file.content);
  assert.equal(document.isDirty, false);
  await assert.rejects(fs.stat(path.join(root, "generated")));

  const destinationPrompt = mock.method(
    vscode.window,
    "showInputBox",
    async () => "generated/host-project",
  );
  const confirmation = mock.method(vscode.window, "showWarningMessage", async () => undefined);
  try {
    assert.equal(await command("generate"), undefined);
    await assert.rejects(fs.stat(path.join(root, "generated/host-project")));
    confirmation.mock.mockImplementation(async () => "Generate");
    const generated = await command("generate");
    assert.equal(generated?.status, "generated");
    assert.equal(generated?.execution_status, "not_run");
    assert.equal(
      await fs.readFile(path.join(root, "generated/host-project", file.path), "utf8"),
      file.content,
    );
    assert.ok(confirmation.mock.callCount() >= 2);
  } finally {
    destinationPrompt.mock.restore();
    confirmation.mock.restore();
  }

  await command("selectConfiguration", vscode.Uri.file(path.join(root, "notebook.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  assert.equal((await command("preview"))?.status, "planned");
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "blocked.json")));
  assert.equal((await command("inspect"))?.status, "blocked");
  const diagnostics = project.getChildren().find((item) => item.label.startsWith("Diagnostics"));
  assert.ok(diagnostics?.children?.length);
  assert.ok(project.getChildren().some((item) => item.label.includes("Inspection blocked")));

  await command("selectConfiguration", vscode.Uri.file(path.join(root, "project.json")));
  await command("preview");
  await vscode.commands.executeCommand("notebookToKedro.project.focus");
  console.log(
    "Extension-host checks passed: activation, commands, inspection, preview, read-only document, canceled generation, confirmed generation, notebook and blocked diagnostics.",
  );
  if (process.env.NTK_UI_REVIEW === "1") {
    await fs.writeFile(path.join(root, "ui-ready.txt"), "ready", "utf8");
    await new Promise((resolve) => setTimeout(resolve, 60_000));
  }
}
