import { strict as assert } from "node:assert";
import { promises as fs } from "node:fs";
import * as path from "node:path";
import { mock } from "node:test";
import * as vscode from "vscode";
import type { Envelope } from "../src/bridge";

export async function checkConfigurationWizard(root: string): Promise<void> {
  let source = "examples/functional_workflow/workflow.py";
  let mode = "functional";
  let destination = path.join(root, "created.json");
  let cancel = "";
  let packageName = "configured_project";
  let optional = false;
  let inspectOnly = false;
  let selectedRoot = root;
  const errors: string[] = [];
  const open = mock.method(vscode.window, "showOpenDialog", async (options: any) => {
    if (cancel === options.title || cancel === `file:${options.title}`) return undefined;
    const filenames: Record<string, string> = {
      "Choose the ML project folder": selectedRoot,
      "Choose the notebook or Python source": path.join(selectedRoot, source),
      "Choose the workflow I/O configuration": path.join(
        selectedRoot,
        "examples/functional_workflow/workflow.json",
      ),
      "Architecture profile": path.join(selectedRoot, "profile.json"),
      "Optional regression expectations": path.join(
        selectedRoot,
        "examples/functional_workflow/regression.json",
      ),
    };
    assert.ok(filenames[options.title], `Unexpected file chooser: ${options.title}`);
    return [vscode.Uri.file(filenames[options.title])];
  });
  const pick = mock.method(vscode.window, "showQuickPick", async (items: any, options: any) => {
    if (cancel === options.title) return undefined;
    if (options.title === "Choose the source interpretation")
      return items.find((item: any) => item.sourceKind === mode);
    return items.find(
      (item: any) => item.choose === (options.title === "Workflow setup" ? !inspectOnly : optional),
    );
  });
  const input = mock.method(vscode.window, "showInputBox", async () =>
    cancel === "package" ? undefined : packageName,
  );
  const save = mock.method(vscode.window, "showSaveDialog", async () =>
    cancel === "save" ? undefined : vscode.Uri.file(destination),
  );
  const error = mock.method(vscode.window, "showErrorMessage", async (message: string) => {
    errors.push(message);
    return undefined;
  });
  const command = () =>
    vscode.commands.executeCommand<Envelope | undefined>("notebookToKedro.createConfiguration");
  try {
    const original = await fs.readFile(path.join(root, source), "utf8");
    const created = await command();
    assert.equal(created?.status, "inspected");
    const settings = JSON.parse(await fs.readFile(destination, "utf8"));
    assert.equal(settings.project_root, ".");
    assert.equal(settings.source_kind, "functional");
    assert.equal(settings.source, source);
    assert.equal(settings.package_name, packageName);
    assert.equal(settings.architecture_profile, undefined);
    assert.equal(settings.regression_contract, undefined);
    assert.equal(await fs.readFile(path.join(root, source), "utf8"), original);
    assert.equal(
      (await vscode.commands.executeCommand<Envelope>("notebookToKedro.preview")).status,
      "planned",
    );

    const prior = await fs.readFile(destination, "utf8");
    assert.equal(await command(), undefined);
    assert.equal(await fs.readFile(destination, "utf8"), prior);
    assert.ok(errors.pop()?.includes("EEXIST"));

    destination = path.join(root, "never-created.json");
    for (const step of [
      "Choose the ML project folder",
      "Choose the notebook or Python source",
      "Choose the workflow I/O configuration",
      "Workflow setup",
      "package",
      "Architecture profile",
      "Optional regression expectations",
      "save",
    ]) {
      cancel = step;
      assert.equal(await command(), undefined, `Cancellation at ${step}`);
      await assert.rejects(fs.stat(destination));
    }
    cancel = "";
    packageName = "class";
    assert.equal(await command(), undefined);
    await assert.rejects(fs.stat(destination));
    assert.ok(errors.pop()?.includes("LO001"));
    packageName = "configured_project";

    optional = true;
    for (const step of ["file:Architecture profile", "file:Optional regression expectations"]) {
      cancel = step;
      assert.equal(await command(), undefined);
      await assert.rejects(fs.stat(destination));
    }
    cancel = "";
    source = "../outside.py";
    assert.equal(await command(), undefined);
    assert.ok(errors.pop()?.includes("inside the project folder"));
    await assert.rejects(fs.stat(destination));
    optional = false;

    source = "source.ipynb";
    mode = "notebook";
    cancel = "Choose the source interpretation";
    assert.equal(await command(), undefined);
    await assert.rejects(fs.stat(destination));
    cancel = "";
    destination = path.join(root, "created-notebook.json");
    assert.equal((await command())?.status, "inspected");
    assert.equal(
      JSON.parse(await fs.readFile(destination, "utf8")).workflow_configuration,
      undefined,
    );

    source = "examples/functional_workflow/workflow.ipynb";
    mode = "functional";
    optional = true;
    destination = path.join(root, "created-functional-notebook.json");
    assert.equal((await command())?.status, "inspected");
    const full = JSON.parse(await fs.readFile(destination, "utf8"));
    assert.equal(full.architecture_profile, "profile.json");
    assert.equal(full.regression_contract, "examples/functional_workflow/regression.json");
    assert.equal(
      (await vscode.commands.executeCommand<Envelope>("notebookToKedro.preview")).status,
      "planned",
    );

    source = "blocked.py";
    inspectOnly = true;
    destination = path.join(root, "created-blocked.json");
    assert.equal((await command())?.status, "blocked");
    assert.ok(await fs.stat(destination));
    assert.equal(
      JSON.parse(await fs.readFile(destination, "utf8")).workflow_configuration,
      undefined,
    );
    assert.equal(await vscode.commands.executeCommand("notebookToKedro.preview"), undefined);
    assert.ok(errors.pop()?.includes("require workflow_configuration"));
    selectedRoot = await fs.mkdtemp(path.join(path.dirname(root), "vscode-setup-"));
    source = "source.py";
    optional = false;
    await fs.writeFile(
      path.join(selectedRoot, source),
      "def workflow():\n    value = 1\n    return value\n",
      "utf8",
    );
    destination = path.join(selectedRoot, "project.json");
    assert.equal((await command())?.status, "inspected");
    const selectedPython = vscode.workspace
      .getConfiguration("notebookToKedro", vscode.Uri.file(destination))
      .get<string>("pythonPath")!;
    assert.equal(path.relative(selectedPython, process.env.NTK_TEST_PYTHON!), "");
    assert.equal(errors.length, 0, errors.join("\n"));
    console.log(
      "Configuration wizard checks passed: defaults, source kinds, optional files, cancellation, invalid package, no overwrite and blocked inspection.",
    );
  } finally {
    open.mock.restore();
    pick.mock.restore();
    input.mock.restore();
    save.mock.restore();
    error.mock.restore();
  }
}
