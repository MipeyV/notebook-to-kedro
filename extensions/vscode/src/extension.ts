import * as vscode from "vscode";
import * as path from "node:path";
import { createHash } from "node:crypto";
import { Envelope, Operation, PreviewFile, PreviewCopy, runEngine } from "./bridge";

interface Entry {
  label: string;
  description?: string;
  icon?: string;
  children?: Entry[];
  command?: vscode.Command;
}

export class ProjectController
  implements vscode.TreeDataProvider<Entry>, vscode.TextDocumentContentProvider
{
  private readonly changed = new vscode.EventEmitter<Entry | undefined>();
  readonly onDidChangeTreeData = this.changed.event;
  private readonly documents = new Map<string, string>();
  private configuration?: vscode.Uri;
  private result?: Envelope;
  private busy = false;
  private status = "Ready";
  private activeEngine?: AbortController;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly output: vscode.OutputChannel,
  ) {
    const saved = context.workspaceState.get<string>("configuration");
    if (saved) this.configuration = vscode.Uri.file(saved);
    context.subscriptions.push(this.changed);
  }

  private scope(): vscode.Uri | undefined {
    return this.configuration ?? vscode.workspace.workspaceFolders?.[0]?.uri;
  }

  private python(): string {
    return vscode.workspace
      .getConfiguration("notebookToKedro", this.scope())
      .get<string>("pythonPath", "");
  }

  private reset(): void {
    this.result = undefined;
    this.status = "Ready";
    void vscode.commands.executeCommand("setContext", "notebookToKedro.hasResult", false);
    this.changed.fire(undefined);
  }

  private available(): boolean {
    if (this.busy) {
      void vscode.window.showInformationMessage("An operation is already running.");
      return false;
    }
    if (!vscode.workspace.isTrusted) {
      throw new Error("Trust this workspace before starting the Python engine.");
    }
    return true;
  }

  async selectConfiguration(uri?: vscode.Uri): Promise<void> {
    if (!this.available()) return;
    const selected =
      uri ??
      (
        await vscode.window.showOpenDialog({
          title: "Choose Notebook to Kedro project configuration",
          canSelectMany: false,
          defaultUri: this.scope(),
          filters: { "JSON configuration": ["json"] },
        })
      )?.[0];
    if (!selected) return;
    if (selected.scheme !== "file") throw new Error("Choose a local configuration file.");
    this.configuration = selected;
    await this.context.workspaceState.update("configuration", selected.fsPath);
    this.reset();
  }

  async selectPython(uri?: vscode.Uri): Promise<void> {
    if (!this.available()) return;
    const selected =
      uri ??
      (
        await vscode.window.showOpenDialog({
          title: "Choose Python containing the Notebook to Kedro engine",
          canSelectMany: false,
          defaultUri: this.python() ? vscode.Uri.file(this.python()) : this.scope(),
        })
      )?.[0];
    if (!selected) return;
    if (selected.scheme !== "file") throw new Error("Choose a local Python interpreter.");
    const folder = this.scope() && vscode.workspace.getWorkspaceFolder(this.scope()!);
    await vscode.workspace
      .getConfiguration("notebookToKedro", this.scope())
      .update(
        "pythonPath",
        selected.fsPath,
        folder ? vscode.ConfigurationTarget.WorkspaceFolder : vscode.ConfigurationTarget.Global,
      );
    this.reset();
  }

  settingsChanged(): void {
    this.reset();
  }

  async editConfiguration(): Promise<void> {
    if (!this.configuration) {
      await this.selectConfiguration();
    }
    if (this.configuration)
      await vscode.window.showTextDocument(
        await vscode.workspace.openTextDocument(this.configuration),
      );
  }

  private async request(
    operation: Operation,
    signal?: AbortSignal,
    destination?: string,
  ): Promise<Envelope> {
    if (!this.configuration) throw new Error("Choose a project configuration first.");
    const python = this.python();
    if (!python)
      throw new Error("Choose the Python interpreter containing the Notebook to Kedro engine.");
    this.output.appendLine(`${new Date().toISOString()} ${operation} ${this.configuration.fsPath}`);
    const active = new AbortController();
    this.activeEngine = active;
    const abort = () => active.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) active.abort();
    let result: Envelope;
    try {
      result = await runEngine({
        python,
        configuration: this.configuration.fsPath,
        operation,
        signal: active.signal,
        destination,
      });
    } finally {
      signal?.removeEventListener("abort", abort);
      this.activeEngine = undefined;
    }
    this.result = result;
    this.status =
      result.status === "blocked"
        ? "Inspection blocked · review diagnostics"
        : result.status === "planned"
          ? "Preview ready"
          : result.status === "generated"
            ? "Project generated"
            : "Source inspected";
    this.output.appendLine(this.status);
    await vscode.commands.executeCommand("setContext", "notebookToKedro.hasResult", true);
    this.changed.fire(undefined);
    return result;
  }

  async operate(operation: "inspect" | "plan"): Promise<Envelope | undefined> {
    if (!this.available()) return;
    this.busy = true;
    this.result = undefined;
    this.status = operation === "inspect" ? "Inspecting source…" : "Preparing file preview…";
    this.changed.fire(undefined);
    try {
      return await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: this.status,
          cancellable: true,
        },
        async (_progress, token) => {
          const controller = new AbortController();
          const subscription = token.onCancellationRequested(() => controller.abort());
          try {
            return await this.request(operation, controller.signal);
          } finally {
            subscription.dispose();
          }
        },
      );
    } finally {
      this.busy = false;
      this.changed.fire(undefined);
    }
  }

  async generate(): Promise<Envelope | undefined> {
    if (!this.available()) return;
    this.busy = true;
    this.result = undefined;
    this.status = "Preparing generation…";
    this.changed.fire(undefined);
    try {
      const preview = await this.request("plan");
      const root = preview.configuration.project_root;
      const folder = await vscode.window.showInputBox({
        title: "Generate Kedro project",
        value: "generated/kedro_project",
        prompt: `New destination inside ${root}`,
        validateInput: (value) => {
          const relative = path.relative(root, path.resolve(root, value));
          return !value.trim() ||
            !relative ||
            relative === ".." ||
            relative.startsWith(`..${path.sep}`) ||
            path.isAbsolute(relative)
            ? "Choose a new folder inside the project root."
            : undefined;
        },
      });
      if (!folder) return;
      const destination = path.resolve(root, folder);
      const answer = await vscode.window.showWarningMessage(
        `Generate Kedro project in ${destination}?`,
        {
          modal: true,
          detail: `${preview.files!.length + preview.copies!.length} files. Source: ${preview.configuration.source}. Generation uses the current saved source and configuration.`,
        },
        "Generate",
      );
      if (answer !== "Generate") return;
      const generated = await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "Generating Kedro project…",
          cancellable: false,
        },
        () => this.request("generate", undefined, destination),
      );
      void vscode.window.showInformationMessage(`Kedro project generated in ${destination}`);
      return generated;
    } finally {
      this.busy = false;
      this.changed.fire(undefined);
    }
  }

  async guarded<T>(action: () => Promise<T>): Promise<T | undefined> {
    try {
      return await action();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.result = undefined;
      void vscode.commands.executeCommand("setContext", "notebookToKedro.hasResult", false);
      this.status =
        message === "Operation canceled."
          ? "Operation canceled"
          : "Operation failed · see Engine Output";
      this.output.appendLine(message);
      this.changed.fire(undefined);
      if (message !== "Operation canceled.") {
        const answer = await vscode.window.showErrorMessage(message, "Show Engine Output");
        if (answer) this.output.show(true);
      }
      return undefined;
    }
  }

  getTreeItem(entry: Entry): vscode.TreeItem {
    const item = new vscode.TreeItem(
      entry.label,
      entry.children
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.None,
    );
    item.description = entry.description;
    item.tooltip = entry.description ? `${entry.label}\n${entry.description}` : entry.label;
    item.command = entry.command;
    if (entry.icon) item.iconPath = new vscode.ThemeIcon(entry.icon);
    return item;
  }

  getChildren(entry?: Entry): Entry[] {
    if (entry) return entry.children ?? [];
    if (!this.configuration) return [];
    const action = (label: string, command: string, icon: string, description?: string): Entry => ({
      label,
      description,
      icon,
      command: { command: `notebookToKedro.${command}`, title: label },
    });
    const entries: Entry[] = [
      action("Configuration", "editConfiguration", "json", this.configuration.fsPath),
      action(
        "Python interpreter",
        "selectPython",
        "terminal",
        this.python() || "Choose interpreter",
      ),
      {
        label: "Operations",
        children: [
          action("Inspect source", "inspect", "search"),
          action("Preview files", "preview", "open-preview"),
          action("Generate project", "generate", "new-folder"),
        ],
      },
      { label: this.status, icon: this.busy ? "loading~spin" : "info" },
    ];
    if (!this.result) return entries;
    entries.push({
      label: "Source",
      description: this.result.configuration.source,
      icon: "file-code",
    });
    const analysis =
      this.result.analysis ??
      (this.result.plan?.analysis as Record<string, unknown> | undefined) ??
      this.result.plan;
    const diagnostics = (Array.isArray(analysis?.diagnostics) ? analysis.diagnostics : []).filter(
      (item: any): item is { code: string; message: string } =>
        item && typeof item.code === "string" && typeof item.message === "string",
    );
    if (diagnostics.length)
      entries.push({
        label: `Diagnostics (${diagnostics.length})`,
        children: diagnostics.map((item) => ({
          label: item.code,
          description: item.message,
          icon: "warning",
        })),
      });
    if (this.result.operation === "plan") {
      entries.push({
        label: "Generated files",
        children: (this.result.files as PreviewFile[]).map((file) => ({
          label: file.path,
          icon: "file",
          command: {
            command: "notebookToKedro.openPreview",
            title: "Open preview",
            arguments: [file],
          },
        })),
      });
      const copies = this.result.copies as PreviewCopy[];
      if (copies.length)
        entries.push({
          label: "Copied inputs",
          children: copies.map((copy) => ({
            label: copy.destination,
            description: copy.source,
            icon: "files",
          })),
        });
    } else if (this.result.operation === "generate") {
      entries.push({
        label: "Generated files",
        children: (this.result.files as string[]).map((file) => ({
          label: file,
          icon: "file",
          command: {
            command: "vscode.open",
            title: "Open generated file",
            arguments: [vscode.Uri.file(path.join(this.result!.destination!, file))],
          },
        })),
      });
    }
    entries.push(action("Open operation report", "showReport", "json"));
    return entries;
  }

  async openPreview(file: PreviewFile): Promise<vscode.TextDocument> {
    return this.openDocument(file.path, file.content);
  }

  async showReport(): Promise<void> {
    if (this.result)
      await this.openDocument("operation.json", JSON.stringify(this.result, null, 2) + "\n");
  }

  private async openDocument(name: string, content: string): Promise<vscode.TextDocument> {
    const hash = createHash("sha256").update(content).digest("hex");
    const uri = vscode.Uri.from({ scheme: "notebook-to-kedro-preview", path: `/${hash}/${name}` });
    this.documents.set(uri.toString(), content);
    const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document, { preview: true });
    return document;
  }

  provideTextDocumentContent(uri: vscode.Uri): string {
    const content = this.documents.get(uri.toString());
    if (content === undefined) throw new Error("Preview expired. Run Preview Files again.");
    return content;
  }

  closeDocument(document: vscode.TextDocument): void {
    this.documents.delete(document.uri.toString());
  }

  dispose(): void {
    this.activeEngine?.abort();
    this.documents.clear();
  }
}

export function activate(context: vscode.ExtensionContext): ProjectController {
  const output = vscode.window.createOutputChannel("Notebook to Kedro");
  const project = new ProjectController(context, output);
  const command = (name: string, handler: (...args: any[]) => Promise<unknown>) =>
    context.subscriptions.push(
      vscode.commands.registerCommand(`notebookToKedro.${name}`, (...args: any[]) =>
        project.guarded(() => handler(...args)),
      ),
    );
  command("selectConfiguration", (uri?: vscode.Uri) => project.selectConfiguration(uri));
  command("selectPython", (uri?: vscode.Uri) => project.selectPython(uri));
  command("editConfiguration", () => project.editConfiguration());
  command("inspect", () => project.operate("inspect"));
  command("preview", () => project.operate("plan"));
  command("generate", () => project.generate());
  command("showReport", () => project.showReport());
  command("openPreview", (file: PreviewFile) => project.openPreview(file));
  context.subscriptions.push(
    output,
    new vscode.Disposable(() => project.dispose()),
    vscode.commands.registerCommand("notebookToKedro.showLogs", () => output.show(true)),
    vscode.window.createTreeView("notebookToKedro.project", { treeDataProvider: project }),
    vscode.workspace.registerTextDocumentContentProvider("notebook-to-kedro-preview", project),
    vscode.workspace.onDidCloseTextDocument((document) => project.closeDocument(document)),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("notebookToKedro")) project.settingsChanged();
    }),
  );
  return project;
}
