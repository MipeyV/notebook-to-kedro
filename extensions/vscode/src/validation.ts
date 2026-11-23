import { execFile } from "node:child_process";
import * as path from "node:path";

export interface ValidationRequest {
  enginePython: string;
  configuration: string;
  project: string;
  python: string;
  output: string;
  timeout: number;
  signal?: AbortSignal;
}
export interface ValidationPlan {
  schema_version: "1.0";
  operation: "validation-plan";
  execution_status: "not_run";
  plan_sha256: string;
  project: string;
  python: string;
  output: string;
  timeout_seconds: number;
  files: { path: string; sha256: string; size: number }[];
  tests: string[];
  execution_notice: string;
}
export interface ValidationOutcome {
  schema_version: "1.0";
  operation: "validate";
  status: string;
  plan_sha256: string;
  project: string;
  python: string;
  output: string;
  duration_ns: number;
  worker_duration_ns: number | null;
  returncode: number | null;
  tests: Record<"tests" | "passed" | "failed" | "errors" | "skipped", number> | null;
  environment: Record<string, unknown> | null;
  original_unchanged: boolean;
  snapshot_unchanged: boolean;
  inputs_unchanged: boolean;
  python_unchanged: boolean;
  log: "tests.log";
  log_truncated: boolean;
  error: string | null;
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function digest(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}
function count(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
function samePath(value: unknown, expected: string): boolean {
  if (typeof value !== "string" || !path.isAbsolute(value)) return false;
  const normalize = (file: string) =>
    process.platform === "win32" ? path.resolve(file).toLowerCase() : path.resolve(file);
  return normalize(value) === normalize(expected);
}
const outcomes = new Set([
  "passed",
  "failed",
  "no_passing_tests",
  "runner_error",
  "environment_missing",
  "timed_out",
  "canceled",
  "cleanup_incomplete",
  "drifted",
]);

export function validationArguments(request: ValidationRequest, approved?: string): string[] {
  if (
    ![request.enginePython, request.configuration, request.python, request.project].every(
      path.isAbsolute,
    ) ||
    !Number.isInteger(request.timeout) ||
    request.timeout < 1 ||
    request.timeout > 600 ||
    (approved !== undefined && !digest(approved))
  )
    throw new Error(
      "Choose absolute configuration/project/Python paths and a 1..600 second budget.",
    );
  return [
    "-I",
    "-X",
    "utf8",
    "-u",
    "-m",
    "notebook_to_kedro.cli",
    "project",
    approved === undefined ? "validation-plan" : "validate",
    request.configuration,
    request.project,
    "--python",
    request.python,
    "--output",
    request.output,
    "--timeout",
    String(request.timeout),
    ...(approved === undefined ? [] : ["--approved-sha256", approved, "--cancellable-stdin"]),
  ];
}

export function decodeValidationPlan(content: string, request: ValidationRequest): ValidationPlan {
  const data: unknown = JSON.parse(content);
  if (
    !object(data) ||
    data.schema_version !== "1.0" ||
    data.operation !== "validation-plan" ||
    data.execution_status !== "not_run" ||
    !digest(data.plan_sha256) ||
    !samePath(data.project, request.project) ||
    !samePath(data.python, request.python) ||
    typeof data.output !== "string" ||
    !path.isAbsolute(data.output) ||
    data.timeout_seconds !== request.timeout ||
    !Array.isArray(data.files) ||
    !data.files.length ||
    !data.files.every(
      (file) =>
        object(file) && typeof file.path === "string" && digest(file.sha256) && count(file.size),
    ) ||
    !Array.isArray(data.tests) ||
    data.tests.length !== 1 ||
    data.tests[0] !== "tests/test_notebook_regressions.py" ||
    typeof data.execution_notice !== "string"
  )
    throw new Error("Invalid generated validation review.");
  return data as unknown as ValidationPlan;
}

export function decodeValidationOutcome(
  content: string,
  plan: ValidationPlan,
  exitCode: number,
): ValidationOutcome {
  const data: unknown = JSON.parse(content);
  if (
    !object(data) ||
    data.schema_version !== "1.0" ||
    data.operation !== "validate" ||
    typeof data.status !== "string" ||
    !outcomes.has(data.status) ||
    data.plan_sha256 !== plan.plan_sha256 ||
    !samePath(data.project, plan.project) ||
    !samePath(data.python, plan.python) ||
    !samePath(data.output, plan.output) ||
    !count(data.duration_ns) ||
    (data.worker_duration_ns !== null && !count(data.worker_duration_ns)) ||
    data.log !== "tests.log" ||
    typeof data.log_truncated !== "boolean" ||
    !["original_unchanged", "snapshot_unchanged", "inputs_unchanged", "python_unchanged"].every(
      (name) => typeof data[name] === "boolean",
    ) ||
    (data.error !== null && typeof data.error !== "string") ||
    (data.returncode !== null && !Number.isInteger(data.returncode)) ||
    (data.environment !== null && !object(data.environment)) ||
    exitCode !== (data.status === "passed" ? 0 : 1)
  )
    throw new Error("Invalid generated validation outcome.");
  if (data.tests !== null) {
    const tests = data.tests;
    if (
      !object(tests) ||
      !["tests", "passed", "failed", "errors", "skipped"].every((key) => count(tests[key])) ||
      tests.tests !==
        Number(tests.passed) + Number(tests.failed) + Number(tests.errors) + Number(tests.skipped)
    )
      throw new Error("Inconsistent generated test counts.");
  }
  if (
    data.status === "passed" &&
    (!object(data.tests) ||
      Number(data.tests.passed) < 1 ||
      data.tests.failed !== 0 ||
      data.tests.errors !== 0 ||
      data.returncode !== 0 ||
      data.error !== null ||
      ![
        data.original_unchanged,
        data.snapshot_unchanged,
        data.inputs_unchanged,
        data.python_unchanged,
      ].every((value) => value === true) ||
      !object(data.environment) ||
      !Array.isArray(data.environment.missing) ||
      data.environment.missing.length !== 0)
  )
    throw new Error("Incomplete passing validation evidence.");
  return data as unknown as ValidationOutcome;
}

function invoke(
  request: ValidationRequest,
  approved?: string,
): Promise<{ stdout: string; code: number }> {
  const args = validationArguments(request, approved);
  if (request.signal?.aborted)
    return Promise.reject(new Error("Validation canceled before launch."));
  return new Promise((resolve, reject) => {
    const child = execFile(
      request.enginePython,
      args,
      {
        cwd: path.dirname(request.configuration),
        windowsHide: true,
        shell: false,
        encoding: "utf8",
        timeout: approved === undefined ? 120_000 : (request.timeout + 150) * 1000,
        maxBuffer: 8 * 1024 * 1024,
      },
      (error, stdout, stderr) => {
        request.signal?.removeEventListener("abort", cancel);
        if (error && (error.code !== 1 || !stdout.trim()))
          reject(new Error(stderr.trim() || error.message));
        else resolve({ stdout, code: error ? 1 : 0 });
      },
    );
    const cancel = () => {
      if (approved === undefined) child.kill();
      else child.stdin?.end("cancel\n");
    };
    child.stdin?.on("error", () => {
      /* A completed engine may close stdin before cancellation arrives. */
    });
    request.signal?.addEventListener("abort", cancel, { once: true });
    if (request.signal?.aborted) cancel();
  });
}

export async function prepareValidation(request: ValidationRequest): Promise<ValidationPlan> {
  const result = await invoke(request);
  if (result.code !== 0) throw new Error(result.stdout || "Validation preparation failed.");
  return decodeValidationPlan(result.stdout, request);
}
export async function runValidation(
  request: ValidationRequest,
  plan: ValidationPlan,
): Promise<ValidationOutcome> {
  const result = await invoke({ ...request, output: plan.output }, plan.plan_sha256);
  return decodeValidationOutcome(result.stdout, plan, result.code);
}
