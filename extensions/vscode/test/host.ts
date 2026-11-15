import { strict as assert } from "node:assert";
import { promises as fs } from "node:fs";
import * as path from "node:path";
import { mock } from "node:test";
import * as vscode from "vscode";
import type { Envelope, PreviewFile } from "../src/bridge";
import type { ProjectController } from "../src/extension";
import { checkConfigurationWizard } from "./setup-host";

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
  await checkConfigurationWizard(root);
  // Unexpected engine errors must fail the host test instead of waiting for a dialog dismissal.
  mock.method(vscode.window, "showErrorMessage", async (message: string) => {
    throw new Error(message);
  });
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "project.json")));
  const inspection = await command("inspect");
  assert.equal(inspection?.status, "inspected");
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "expression-returns.json")));
  const expressions = await command("inspect");
  assert.equal(expressions?.schema_version, "1.0");
  assert.equal(expressions?.analysis?.schema_version, "1.1");
  assert.equal(expressions?.status, "inspected");
  assert.equal((await command("preview"))?.status, "planned");
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "candidate.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  const candidatePreview = await command("preview");
  assert.equal(candidatePreview?.schema_version, "1.0");
  assert.equal(candidatePreview?.status, "planned");
  const candidateParameters = (candidatePreview!.files as PreviewFile[]).find(
    (item) => item.path === "conf/base/parameters.yml",
  )!;
  assert.equal(JSON.parse(candidateParameters.content).candidate.seed, 42);
  assert.equal(JSON.parse(candidateParameters.content).candidate.phase, "validation");
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "ordered-join.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  const orderedPreview = await command("preview");
  assert.equal(orderedPreview?.schema_version, "1.0");
  assert.equal(orderedPreview?.plan?.schema_version, "1.1");
  assert.equal(orderedPreview?.status, "planned");
  const orderedFiles = orderedPreview!.files as PreviewFile[];
  const orderedPipeline = orderedFiles.find((item) => item.path.endsWith("/pipeline.py"))!;
  assert.ok(orderedPipeline.content.includes("_AfterPrevious"));
  const orderedManifest = JSON.parse(
    orderedFiles.find((item) => item.path === "functional-workflow.json")!.content,
  );
  assert.equal(orderedManifest.configuration.schema_version, "1.2");
  assert.equal(orderedManifest.ordering.policy, "source_order");
  assert.equal(orderedManifest.ordering_inputs.length, 1);
  assert.equal(orderedManifest.ordering_inputs[0].forwarded_to_function, false);
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "package.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  const packagePreview = await command("preview");
  assert.equal(packagePreview?.status, "planned");
  assert.equal(packagePreview?.plan?.schema_version, "1.2");
  const packageCopies = project.getChildren().find((item) => item.label === "Files to copy");
  assert.ok(packageCopies?.children?.some((item) => item.label === "src/example_ml/workflow.py"));
  const packageManifest = JSON.parse(
    (packagePreview!.files as PreviewFile[]).find(
      (item) => item.path === "functional-workflow.json",
    )!.content,
  );
  assert.equal(packageManifest.source_package.module, "example_ml.workflow");
  assert.equal(packageManifest.source_module, "src/example_ml/workflow.py");
  assert.equal(packageManifest.source_package.distribution_metadata_status, "not_reconstructed");
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "files.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  const fileInputPreview = await command("preview");
  assert.equal(fileInputPreview?.status, "planned");
  assert.equal(fileInputPreview?.plan?.schema_version, "1.3");
  const inputCopies = project.getChildren().find((item) => item.label === "Files to copy");
  assert.ok(
    inputCopies?.children?.some(
      (item) => item.label === "data/01_raw/snapshot_path/measurements.metadata.json",
    ),
  );
  const inputManifest = JSON.parse(
    (fileInputPreview!.files as PreviewFile[]).find(
      (item) => item.path === "functional-workflow.json",
    )!.content,
  );
  assert.equal(inputManifest.file_inputs[0].validation_status, "hashed_not_loaded");
  assert.equal(inputManifest.file_reference_destinations[0].load_policy, "path_string");
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "memory.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  const memoryPreview = await command("preview");
  assert.equal(memoryPreview?.status, "planned");
  assert.equal(memoryPreview?.plan?.schema_version, "1.4");
  const memoryManifest = JSON.parse(
    (memoryPreview!.files as PreviewFile[]).find(
      (item) => item.path === "functional-workflow.json",
    )!.content,
  );
  assert.equal(memoryManifest.result_boundary.mode, "memory");
  assert.equal(memoryManifest.result_boundary.persistence, "none");
  const memoryCatalog = JSON.parse(
    (memoryPreview!.files as PreviewFile[]).find((item) => item.path === "conf/base/catalog.yml")!
      .content,
  );
  assert.deepEqual(memoryCatalog.result, { type: "MemoryDataset", copy_mode: "assign" });
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "project.json")));
  await command("inspect");
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
  mock.restoreAll();
}
