import * as vscode from "vscode";
import {
  prepareValidation,
  runValidation,
  type ValidationOutcome,
  type ValidationRequest,
} from "./validation";

interface ValidationUI {
  configuration: vscode.Uri;
  enginePython: string;
  project?: string;
  active: AbortController;
  showReview: (content: string) => Promise<unknown>;
}

/** Explicit review/confirmation only; snapshot and test execution rules live in the engine. */
export async function chooseAndValidate(ui: ValidationUI): Promise<ValidationOutcome | undefined> {
  const project = (
    await vscode.window.showOpenDialog({
      title: "Choose the generated notebook project to validate",
      canSelectFolders: true,
      canSelectFiles: false,
      canSelectMany: false,
      defaultUri: ui.project ? vscode.Uri.file(ui.project) : ui.configuration,
    })
  )?.[0];
  if (!project) return;
  const python = (
    await vscode.window.showOpenDialog({
      title: "Choose the existing Python runtime for generated tests",
      canSelectFolders: false,
      canSelectFiles: true,
      canSelectMany: false,
      defaultUri: vscode.Uri.file(ui.enginePython),
    })
  )?.[0];
  if (!python) return;
  if (project.scheme !== "file" || python.scheme !== "file")
    throw new Error("Choose local project and Python paths.");
  const timeout = await vscode.window.showInputBox({
    title: "Validation worker timeout in seconds",
    value: "300",
    validateInput: (value) =>
      /^[0-9]+$/.test(value) && Number(value) >= 1 && Number(value) <= 600
        ? undefined
        : "Enter an integer from 1 to 600.",
  });
  if (timeout === undefined) return;
  const output = await vscode.window.showInputBox({
    title: "New validation attempt directory (relative to configured project root)",
    value: `generated/validation-${Date.now()}`,
    prompt: "The engine keeps a private copy, bounded log and separate execution report here.",
    validateInput: (value) => (value.trim() ? undefined : "Enter a new attempt directory."),
  });
  if (!output) return;
  const request: ValidationRequest = {
    configuration: ui.configuration.fsPath,
    enginePython: ui.enginePython,
    project: project.fsPath,
    python: python.fsPath,
    output,
    timeout: Number(timeout),
    signal: ui.active.signal,
  };
  const progress = <T>(title: string, action: () => Promise<T>) =>
    vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title,
        cancellable: true,
      },
      async (_progress, token) => {
        const subscription = token.onCancellationRequested(() => ui.active.abort());
        try {
          return await action();
        } finally {
          subscription.dispose();
        }
      },
    );
  const plan = await progress("Preparing generated-project validation", () =>
    prepareValidation(request),
  );
  if (ui.active.signal.aborted) return;
  await ui.showReview(JSON.stringify(plan, null, 2));
  const confirm = await vscode.window.showWarningMessage(
    "Run the reviewed generated notebook tests?",
    {
      modal: true,
      detail: `${plan.execution_notice}\n\nProject: ${plan.project}\nPython: ${plan.python}\nTimeout: ${plan.timeout_seconds} s\nOutput: ${plan.output}\nSnapshot files: ${plan.files.length}\nReview SHA-256: ${plan.plan_sha256}`,
    },
    "Run tests",
  );
  if (confirm !== "Run tests") return;
  return progress("Running delivered notebook tests", () => runValidation(request, plan));
}
