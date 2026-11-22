import { strict as assert } from "node:assert";
import { promises as fs } from "node:fs";
import * as path from "node:path";
import { mock } from "node:test";
import * as vscode from "vscode";
import type { Envelope, PreviewFile } from "../src/bridge";
import type { ProjectController } from "../src/extension";
import { checkConfigurationWizard } from "./setup-host";
import { declaredJourney } from "./summary-fixture";

export async function run(): Promise<void> {
  const root = process.env.NTK_TEST_WORKSPACE!;
  const python = process.env.NTK_TEST_PYTHON!;
  if (process.env.NTK_TEST_EMPTY_WINDOW === "1")
    assert.equal(vscode.workspace.workspaceFolders, undefined);
  assert.ok(root && python, "The host test requires a private workspace and an engine interpreter");
  const extension = vscode.extensions.getExtension<ProjectController>("mipeyv.notebook-to-kedro");
  assert.ok(extension, "Extension must be discoverable through its real manifest");
  const command = async (name: string, ...args: unknown[]) =>
    vscode.commands.executeCommand<Envelope | undefined>(`notebookToKedro.${name}`, ...args);
  await vscode.commands.executeCommand("workbench.action.closeSidebar");
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "project.json")));
  assert.equal(
    extension.isActive,
    true,
    "Selecting configuration must activate the installed commands",
  );
  const project = extension.exports;
  const visibleDeadline = Date.now() + 5000;
  while (!project.isViewVisible && Date.now() < visibleDeadline)
    await new Promise((resolve) => setTimeout(resolve, 25));
  assert.equal(project.isViewVisible, true, "Selecting configuration must reveal the results view");
  assert.ok(project.getChildren().some((item) => item.label === "Configuration selected"));
  await command("selectPython", vscode.Uri.file(python));
  await checkConfigurationWizard(root);
  // Unexpected engine errors must fail the host test instead of waiting for a dialog dismissal.
  mock.method(vscode.window, "showErrorMessage", async (message: string) => {
    throw new Error(message);
  });
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "project.json")));
  const inspection = await command("inspect");
  assert.equal(inspection?.status, "inspected");
  assert.match(vscode.window.activeTextEditor!.document.getText(), /inspect: inspected/);
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
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "artifacts.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  const artifactPreview = await command("preview");
  assert.equal(artifactPreview?.status, "planned");
  assert.equal(artifactPreview?.plan?.schema_version, "1.5");
  const artifactManifest = JSON.parse(
    (artifactPreview!.files as PreviewFile[]).find(
      (item) => item.path === "functional-workflow.json",
    )!.content,
  );
  assert.equal(artifactManifest.artifact_policy.mode, "check_before_owner_call");
  assert.equal(artifactManifest.artifact_policy.runtime_validation, "not_run");
  assert.ok(
    (artifactPreview!.files as PreviewFile[]).some((item) => item.path === "artifact-policy.json"),
  );
  await assert.rejects(fs.stat(path.join(root, "artifacts")));
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "distribution.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  const distributionPreview = await command("preview");
  assert.equal(distributionPreview?.status, "planned");
  assert.equal(distributionPreview?.plan?.schema_version, "1.6");
  const distributionManifest = JSON.parse(
    (distributionPreview!.files as PreviewFile[]).find(
      (item) => item.path === "functional-workflow.json",
    )!.content,
  );
  assert.equal(distributionManifest.configuration.schema_version, "1.7");
  assert.equal(
    distributionManifest.application_distribution.name,
    "synthetic-distribution-example",
  );
  assert.equal(distributionManifest.application_distribution.build_status, "not_run");
  assert.equal(distributionManifest.source_module, "application/src/distribution_ml/workflow.py");
  const applicationCopies = project.getChildren().find((item) => item.label === "Files to copy");
  assert.ok(
    applicationCopies?.children?.some((item) => item.label === "application/pyproject.toml"),
  );
  assert.ok(
    applicationCopies?.children?.some((item) => item.label === "application/application.lock"),
  );
  await assert.rejects(fs.stat(path.join(root, "application")));
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "project.json")));
  await command("inspect");
  assert.ok(project.getChildren().some((item) => item.label === "Source"));
  const preview = await command("preview");
  assert.equal(preview?.status, "planned");
  assert.match(vscode.window.activeTextEditor!.document.getText(), /plan: planned/);
  const file = (preview!.files as PreviewFile[]).find((item) => item.path.endsWith("nodes.py"))!;
  const summary = await project.showSummary();
  assert.ok(summary);
  assert.match(summary.getText(), /Last recorded conversion/);
  assert.match(summary.getText(), /Not run by the extension/);
  assert.match(summary.getText(), /Session process timings/);
  assert.match(summary.getText(), /plan: planned/);
  const beforeTyping = summary.getText();
  await vscode.commands.executeCommand("type", { text: "changed" });
  assert.equal(summary.getText(), beforeTyping);
  assert.equal(summary.isDirty, false);
  const executionPath = path.join(root, "declared-evidence.json");
  await fs.writeFile(executionPath, JSON.stringify(declaredJourney()), "utf8");
  await command("importExecutionReport", vscode.Uri.file(executionPath));
  const imported = await project.showSummary();
  assert.match(imported!.getText(), /Reported passed/);
  assert.match(
    imported!.getText(),
    /Not verified; importing does not validate the current project/,
  );
  assert.match(imported!.getText(), /Tests.*Not run by the extension/);
  assert.equal(await fs.readFile(executionPath, "utf8"), JSON.stringify(declaredJourney()));
  const malformed = path.join(root, "malformed-evidence.json");
  await fs.writeFile(malformed, "{}", "utf8");
  const importErrorDialog = mock.method(vscode.window, "showErrorMessage", async () => undefined);
  try {
    await command("importExecutionReport", vscode.Uri.file(malformed));
    assert.equal((await project.showSummary())!.getText(), imported!.getText());
  } finally {
    importErrorDialog.mock.restore();
  }
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
    assert.match(vscode.window.activeTextEditor!.document.getText(), /Published files/);
    assert.equal(generated?.execution_status, "not_run");
    const publishedSummary = (await project.showSummary())!.getText();
    assert.match(publishedSummary, /Published files/);
    assert.match(publishedSummary, /Supplied regression report.*Available/);
    assert.match(publishedSummary, /Installation.*Not checked/);
    assert.match(publishedSummary, /generate: generated/);
    assert.equal(
      await fs.readFile(path.join(root, "generated/host-project", file.path), "utf8"),
      file.content,
    );
    assert.ok(confirmation.mock.callCount() >= 2);
  } finally {
    destinationPrompt.mock.restore();
    confirmation.mock.restore();
  }

  const originalOpen = fs.open;
  const readFailure = mock.method(fs, "open", async (...args: Parameters<typeof fs.open>) => {
    if (String(args[0]).endsWith("regression-coverage.json"))
      throw new Error("Simulated report read refusal");
    return originalOpen(...args);
  });
  const repeatDestination = mock.method(
    vscode.window,
    "showInputBox",
    async () => "generated/report-read-failure",
  );
  const repeatConfirmation = mock.method(
    vscode.window,
    "showWarningMessage",
    async () => "Generate",
  );
  try {
    const generated = await command("generate");
    assert.equal(generated?.status, "generated");
    assert.match((await project.showSummary())!.getText(), /Simulated report read refusal/);
    assert.ok((await fs.stat(path.join(root, "generated/report-read-failure"))).isDirectory());
  } finally {
    readFailure.mock.restore();
    repeatDestination.mock.restore();
    repeatConfirmation.mock.restore();
  }

  const displayDestination = mock.method(
    vscode.window,
    "showInputBox",
    async () => "generated/display-failure",
  );
  const displayConfirmation = mock.method(
    vscode.window,
    "showWarningMessage",
    async () => "Generate",
  );
  const failedDisplay = mock.method(project, "showSummary", async () => {
    throw new Error("Simulated editor display failure");
  });
  try {
    assert.equal((await command("generate"))?.status, "generated");
    assert.ok((await fs.stat(path.join(root, "generated/display-failure"))).isDirectory());
  } finally {
    failedDisplay.mock.restore();
    displayDestination.mock.restore();
    displayConfirmation.mock.restore();
  }
  assert.match((await project.showSummary())!.getText(), /Published files/);

  await command("selectConfiguration", vscode.Uri.file(path.join(root, "notebook.json")));
  assert.equal((await command("inspect"))?.status, "inspected");
  assert.equal((await command("preview"))?.status, "planned");
  await command("selectConfiguration", vscode.Uri.file(path.join(root, "blocked.json")));
  assert.equal((await command("inspect"))?.status, "blocked");
  const diagnostics = project.getChildren().find((item) => item.label.startsWith("Diagnostics"));
  assert.ok(diagnostics?.children?.length);
  assert.ok(project.getChildren().some((item) => item.label.includes("Inspection blocked")));
  assert.match((await project.showSummary())!.getText(), /blocked/);

  await command("selectPython", vscode.Uri.file(path.join(root, "missing-python")));
  const expectedFailure = mock.method(vscode.window, "showErrorMessage", async () => undefined);
  try {
    await command("preview");
    assert.match((await project.showSummary())!.getText(), /plan: failed/);
    assert.match((await project.showSummary())!.getText(), /missing-python/);
    assert.match((await project.showSummary())!.getText(), /No successful operation recorded/);
  } finally {
    expectedFailure.mock.restore();
    await command("selectPython", vscode.Uri.file(python));
  }
  assert.equal(await project.showSummary(), undefined);
  const canceledProgress = mock.method(
    vscode.window,
    "withProgress",
    async (_options: any, task: any) => {
      const cancellation = new vscode.CancellationTokenSource();
      const pending = task({ report: () => undefined }, cancellation.token);
      cancellation.cancel();
      try {
        return await pending;
      } finally {
        cancellation.dispose();
      }
    },
  );
  try {
    await command("inspect");
    assert.match((await project.showSummary())!.getText(), /inspect: canceled/);
  } finally {
    canceledProgress.mock.restore();
  }

  await command("selectConfiguration", vscode.Uri.file(path.join(root, "project.json")));
  await command("preview");
  await vscode.commands.executeCommand("notebookToKedro.project.focus");
  console.log(
    "Extension-host checks passed: activation, commands, inspection, preview, read-only summary, separate imported execution evidence, failed report preservation, failed process timings, canceled/confirmed generation, post-publication report errors, notebook and blocked diagnostics.",
  );
  console.log(
    `Visible feedback checks passed; mode=${process.env.NTK_TEST_EMPTY_WINDOW === "1" ? "empty-window" : "folder"}`,
  );
  if (process.env.NTK_UI_REVIEW === "1") {
    await fs.writeFile(path.join(root, "ui-ready.txt"), "ready", "utf8");
    await new Promise((resolve) => setTimeout(resolve, 60_000));
  }
  mock.restoreAll();
}
