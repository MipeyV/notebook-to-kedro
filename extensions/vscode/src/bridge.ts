import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import * as path from "node:path";

export type Operation = "inspect" | "plan" | "generate";
export interface PreviewFile {
  path: string;
  content: string;
  sha256: string;
}
export interface PreviewCopy {
  source: string;
  destination: string;
  sha256: string;
}
export interface Envelope {
  schema_version: "1.0";
  operation: Operation;
  status: "inspected" | "blocked" | "planned" | "generated";
  configuration: {
    project_root: string;
    source: string;
    source_kind: string;
    [key: string]: unknown;
  };
  execution_status: "not_run";
  analysis?: Record<string, unknown>;
  plan?: Record<string, unknown>;
  files?: PreviewFile[] | string[];
  copies?: PreviewCopy[];
  destination?: string;
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function relativeFile(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    !/[\\:]/.test(value) &&
    !path.posix.isAbsolute(value) &&
    path.posix.normalize(value) === value &&
    !value.split("/").some((part) => part === ".." || part === "." || part === "")
  );
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

export function decodeEnvelope(stdout: string, operation: Operation, exitCode: number): Envelope {
  const data: unknown = JSON.parse(stdout);
  if (
    !object(data) ||
    data.schema_version !== "1.0" ||
    data.operation !== operation ||
    data.execution_status !== "not_run" ||
    !object(data.configuration) ||
    typeof data.configuration.project_root !== "string" ||
    !path.isAbsolute(data.configuration.project_root) ||
    !relativeFile(data.configuration.source) ||
    !["functional", "notebook"].includes(String(data.configuration.source_kind))
  ) {
    throw new Error(
      "Incompatible engine response. Install an engine with local operation schema 1.0.",
    );
  }
  if (operation === "inspect") {
    if (
      !object(data.analysis) ||
      !["inspected", "blocked"].includes(String(data.status)) ||
      exitCode !== (data.status === "blocked" ? 1 : 0)
    )
      throw new Error("Invalid inspection response.");
  } else if (operation === "plan") {
    if (
      exitCode !== 0 ||
      data.status !== "planned" ||
      !object(data.plan) ||
      !Array.isArray(data.files) ||
      !Array.isArray(data.copies)
    ) {
      throw new Error("Invalid preview response.");
    }
    const targets = new Set<string>();
    for (const file of data.files) {
      if (
        !object(file) ||
        !relativeFile(file.path) ||
        typeof file.content !== "string" ||
        !sha(file.sha256) ||
        createHash("sha256").update(file.content, "utf8").digest("hex") !== file.sha256 ||
        targets.has(file.path)
      ) {
        throw new Error("Invalid file preview or content hash.");
      }
      targets.add(file.path);
    }
    for (const copy of data.copies) {
      if (
        !object(copy) ||
        !relativeFile(copy.source) ||
        !relativeFile(copy.destination) ||
        !sha(copy.sha256) ||
        targets.has(copy.destination)
      ) {
        throw new Error("Invalid input-copy preview.");
      }
      targets.add(copy.destination);
    }
  } else if (
    exitCode !== 0 ||
    data.status !== "generated" ||
    data.installation_status !== "not_checked" ||
    typeof data.destination !== "string" ||
    !path.isAbsolute(data.destination) ||
    !Array.isArray(data.files) ||
    !data.files.every(relativeFile)
  ) {
    throw new Error("Invalid generation response.");
  }
  return data as unknown as Envelope;
}

export interface EngineRequest {
  python: string;
  configuration: string;
  operation: Operation;
  destination?: string;
  signal?: AbortSignal;
}

export function engineArguments(request: EngineRequest): string[] {
  if (!path.isAbsolute(request.python) || !path.isAbsolute(request.configuration)) {
    throw new Error("Choose absolute local Python and configuration paths.");
  }
  if ((request.operation === "generate") !== (request.destination !== undefined)) {
    throw new Error("Generation requires a destination; read-only operations accept none.");
  }
  return [
    "-I",
    "-X",
    "utf8",
    "-u",
    "-m",
    "notebook_to_kedro.cli",
    "project",
    request.operation,
    request.configuration,
    ...(request.destination === undefined ? [] : [request.destination]),
  ];
}

export function runEngine(request: EngineRequest): Promise<Envelope> {
  const args = engineArguments(request);
  return new Promise((resolve, reject) => {
    execFile(
      request.python,
      args,
      {
        cwd: path.dirname(request.configuration),
        encoding: "utf8",
        shell: false,
        windowsHide: true,
        timeout: 120_000,
        maxBuffer: 64 * 1024 * 1024,
        signal: request.signal,
      },
      (error, stdout, stderr) => {
        if (request.signal?.aborted) {
          reject(new Error("Operation canceled."));
          return;
        }
        if (error && error.code !== 1) {
          reject(new Error(stderr.trim() || error.message));
          return;
        }
        try {
          resolve(decodeEnvelope(stdout, request.operation, error ? 1 : 0));
        } catch (failure) {
          reject(
            new Error(
              stderr.trim() || (failure instanceof Error ? failure.message : String(failure)),
            ),
          );
        }
      },
    );
  });
}
