import * as vscode from "vscode";
import * as path from "node:path";
import * as os from "node:os";
import { randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";
import { relativeFile, runEngine, type Envelope } from "./bridge";

function relativeSelection(root: string, uri: vscode.Uri): string {
  if (uri.scheme !== "file") throw new Error("Choose a local file.");
  const relative = path.relative(root, uri.fsPath).split(path.sep).join("/");
  if (!relativeFile(relative))
    throw new Error("Choose source and settings files inside the project folder.");
  return relative;
}

async function chooseFile(
  title: string,
  root: vscode.Uri,
  extensions: string[],
): Promise<vscode.Uri | undefined> {
  return (
    await vscode.window.showOpenDialog({
      title,
      defaultUri: root,
      canSelectMany: false,
      filters: { "Project files": extensions },
    })
  )?.[0];
}

async function optionalFile(
  title: string,
  root: vscode.Uri,
  defaultLabel: string,
): Promise<vscode.Uri | null | undefined> {
  const choice = await vscode.window.showQuickPick(
    [
      { label: defaultLabel, choose: false },
      { label: "Choose an existing JSON file", choose: true },
    ],
    { title, ignoreFocusOut: true },
  );
  if (!choice) return undefined;
  return choice.choose ? chooseFile(title, root, ["json"]) : null;
}

async function writeNewConfiguration(filename: string, content: string): Promise<void> {
  const handle = await fs.open(filename, "wx");
  try {
    await handle.writeFile(content, "utf8");
  } catch (error) {
    await handle.close();
    await fs.unlink(filename);
    throw error;
  }
  await handle.close();
}

export interface CreatedConfiguration {
  uri: vscode.Uri;
  inspection: Envelope;
}

export async function createConfiguration(
  python: string,
  initialFolder: vscode.Uri | undefined,
  signal: AbortSignal,
): Promise<CreatedConfiguration | undefined> {
  const root = (
    await vscode.window.showOpenDialog({
      title: "Choose the ML project folder",
      defaultUri: initialFolder,
      canSelectFolders: true,
      canSelectFiles: false,
      canSelectMany: false,
    })
  )?.[0];
  if (!root) return;
  if (root.scheme !== "file") throw new Error("Choose a local project folder.");
  const source = await chooseFile("Choose the notebook or Python source", root, ["ipynb", "py"]);
  if (!source) return;
  let kind: "notebook" | "functional" = "functional";
  if (path.extname(source.fsPath).toLowerCase() === ".ipynb") {
    const choice = await vscode.window.showQuickPick(
      [
        {
          label: "Procedural notebook",
          description: "Top-to-bottom notebook conversion",
          sourceKind: "notebook" as const,
        },
        {
          label: "Functional workflow",
          description: "Explicit functions and configured entrypoint",
          sourceKind: "functional" as const,
        },
      ],
      { title: "Choose the source interpretation", ignoreFocusOut: true },
    );
    if (!choice) return;
    kind = choice.sourceKind;
  }
  const settings: Record<string, string> = {
    schema_version: "1.0",
    project_root: root.fsPath,
    source_kind: kind,
    source: relativeSelection(root.fsPath, source),
    package_name: "generated_project",
  };
  if (kind === "functional") {
    const workflowStep = await vscode.window.showQuickPick(
      [
        {
          label: "Inspect functions first",
          description: "Add workflow I/O before previewing or generating",
          choose: false,
        },
        { label: "Choose existing workflow I/O configuration", choose: true },
      ],
      { title: "Workflow setup", ignoreFocusOut: true },
    );
    if (!workflowStep) return;
    if (workflowStep.choose) {
      const workflow = await chooseFile("Choose the workflow I/O configuration", root, ["json"]);
      if (!workflow) return;
      settings.workflow_configuration = relativeSelection(root.fsPath, workflow);
    }
  }
  const packageName = await vscode.window.showInputBox({
    title: "Generated Python package name",
    value: "generated_project",
    ignoreFocusOut: true,
    validateInput: (value) => (value.trim() ? undefined : "Enter a Python package name."),
  });
  if (packageName === undefined) return;
  settings.package_name = packageName;
  const profile = await optionalFile("Architecture profile", root, "Use default Kedro naming");
  if (profile === undefined) return;
  if (profile) settings.architecture_profile = relativeSelection(root.fsPath, profile);
  if (kind === "functional") {
    const regression = await optionalFile(
      "Optional regression expectations",
      root,
      "Add expectations later",
    );
    if (regression === undefined) return;
    if (regression) settings.regression_contract = relativeSelection(root.fsPath, regression);
  }
  const destination = await vscode.window.showSaveDialog({
    title: "Create project configuration",
    defaultUri: vscode.Uri.joinPath(root, "notebook-to-kedro.json"),
    filters: { "JSON configuration": ["json"] },
  });
  if (!destination) return;
  if (destination.scheme !== "file") throw new Error("Choose a local configuration destination.");
  const temporary = path.join(os.tmpdir(), `notebook-to-kedro-${randomUUID()}.json`);
  await fs.writeFile(temporary, JSON.stringify(settings), { encoding: "utf8", flag: "wx" });
  let inspection: Envelope;
  try {
    inspection = await runEngine({
      python,
      configuration: temporary,
      operation: "inspect",
      signal,
    });
  } finally {
    await fs.unlink(temporary);
  }
  if (signal.aborted) throw new Error("Operation canceled.");
  settings.project_root =
    path.relative(path.dirname(destination.fsPath), root.fsPath).split(path.sep).join("/") || ".";
  await writeNewConfiguration(destination.fsPath, JSON.stringify(settings, null, 2) + "\n");
  return { uri: destination, inspection };
}
