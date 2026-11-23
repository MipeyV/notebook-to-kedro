import { open } from "node:fs/promises";
import { createHash } from "node:crypto";
import type { Envelope, Operation, PreviewFile } from "./bridge";
import { nodeTypeSummary } from "./type-summary";
import type { ValidationOutcome } from "./validation";

export const REPORT_LIMIT = 8 * 1024 * 1024;
export const ARTIFACT_NAMES = [
  "regression-coverage.json",
  "model-output.json",
  "node-types.json",
] as const;

export interface OperationTiming {
  operation: Operation;
  outcome: string;
  durationMs: number;
  recordedAt: string;
  detail?: string;
}
export interface SummaryGroup {
  title: string;
  rows: { label: string; value: string }[];
}
interface Stage {
  name: string;
  status: "started" | "passed" | "failed";
  durationNs?: number;
}
export interface ExecutionEvidence {
  caseName: string;
  profile: string;
  status: string;
  sourceSha256: string;
  stages: Stage[];
  elapsedNs?: number;
  passedTests?: number;
  error?: string;
}
export interface ImportedEvidence {
  filename: string;
  sha256: string;
  importedAt: string;
  report: ExecutionEvidence;
}
export interface SummaryInput {
  validation?: ValidationOutcome;
  result?: Envelope;
  artifacts: Record<string, string>;
  artifactErrors: string[];
  timings: OperationTiming[];
  evidence?: ImportedEvidence;
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function nanoseconds(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
const stageNames = new Set([
  "reference.log",
  "build.log",
  "venv.log",
  "install.log",
  "runtime.json",
  "pytest.log",
  "kedro.log",
  "cli-reload.log",
  "false-oracle.log",
]);

/** Decode only the existing fixed financial journey format; never authenticate its claims. */
export function decodeExecutionEvidence(content: string): ExecutionEvidence {
  const data: unknown = JSON.parse(content);
  const invalid = () =>
    new Error("Unsupported or inconsistent financial journey evidence.json report.");
  if (
    !object(data) ||
    data.schema_version !== "1.0" ||
    typeof data.case !== "string" ||
    !["credit_pipeline", "lapse_calibrated_vote"].includes(data.case) ||
    typeof data.profile !== "string" ||
    !["default", "custom"].includes(data.profile) ||
    typeof data.status !== "string" ||
    !["started", "passed", "failed", "interrupted"].includes(data.status) ||
    data.oracle_basis !== "captured_original_source" ||
    data.independent_scientific_oracle !== false ||
    data.human_effort !== null ||
    data.baseline !== null ||
    data.human_savings !== null ||
    !object(data.source_inventory) ||
    typeof data.source_inventory["workflow.ipynb"] !== "string" ||
    !/^[a-f0-9]{64}$/.test(data.source_inventory["workflow.ipynb"]) ||
    !Array.isArray(data.stages) ||
    data.stages.length > stageNames.size ||
    (data.elapsed_ns !== undefined && !nanoseconds(data.elapsed_ns)) ||
    (data.passed_tests !== undefined && !nanoseconds(data.passed_tests))
  )
    throw invalid();
  const seen = new Set<string>();
  const stages: Stage[] = data.stages.map((stage: unknown) => {
    if (!object(stage) || typeof stage.log !== "string") throw invalid();
    const name = stage.log.split(/[\\/]/).at(-1)!;
    const expected = name === "false-oracle.log" ? 1 : 0;
    if (
      !stageNames.has(name) ||
      seen.has(name) ||
      typeof stage.status !== "string" ||
      !["started", "passed", "failed"].includes(stage.status) ||
      stage.expected_returncode !== expected ||
      (stage.duration_ns !== undefined && !nanoseconds(stage.duration_ns)) ||
      (stage.status === "started" && stage.returncode !== undefined) ||
      (stage.status === "passed" && stage.returncode !== expected) ||
      (stage.status === "failed" &&
        (!Number.isInteger(stage.returncode) || stage.returncode === expected))
    )
      throw invalid();
    seen.add(name);
    return {
      name,
      status: stage.status as Stage["status"],
      durationNs: stage.duration_ns as number | undefined,
    };
  });
  if (
    data.passed_tests !== undefined &&
    (data.passed_tests !== 12 ||
      !stages.some((stage) => stage.name === "pytest.log" && stage.status === "passed"))
  )
    throw invalid();
  if (
    data.status === "passed" &&
    (stages.length !== stageNames.size ||
      stages.some((stage) => stage.status !== "passed") ||
      stages.some((stage) => stage.durationNs === undefined) ||
      data.elapsed_ns === undefined ||
      data.passed_tests !== 12 ||
      data.cli_reload !== "matched" ||
      data.false_oracle_control !== "rejected_after_storage" ||
      data.source_unchanged !== true ||
      data.generated_project_unchanged !== true)
  )
    throw invalid();
  return {
    caseName: String(data.case),
    profile: String(data.profile),
    status: String(data.status),
    sourceSha256: data.source_inventory["workflow.ipynb"],
    stages,
    elapsedNs: data.elapsed_ns as number | undefined,
    passedTests: data.passed_tests as number | undefined,
    error:
      object(data.error) && typeof data.error.message === "string"
        ? data.error.message.slice(0, 1024)
        : undefined,
  };
}

/** Bound actual reads, even if a file grows after stat; this performs no project execution. */
export async function readLocalReport(
  filename: string,
  limit = REPORT_LIMIT,
  strictUtf8 = true,
): Promise<string> {
  const handle = await open(filename, "r");
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.size > limit)
      throw new Error("Choose a bounded regular report file.");
    const buffer = Buffer.alloc(limit + 1);
    let size = 0;
    while (size <= limit) {
      const result = await handle.read(buffer, size, buffer.length - size, null);
      if (result.bytesRead === 0) break;
      size += result.bytesRead;
    }
    if (size > limit) throw new Error("Report exceeds its byte limit.");
    return new TextDecoder("utf-8", { fatal: strictUtf8, ignoreBOM: true }).decode(
      buffer.subarray(0, size),
    );
  } finally {
    await handle.close();
  }
}

export function importedEvidence(filename: string, content: string): ImportedEvidence {
  return {
    filename,
    report: decodeExecutionEvidence(content),
    sha256: createHash("sha256").update(content, "utf8").digest("hex"),
    importedAt: new Date().toISOString(),
  };
}

export function previewArtifacts(result: Envelope): Record<string, string> {
  return Object.fromEntries(
    (result.files as PreviewFile[])
      .filter((file) => ARTIFACT_NAMES.includes(file.path as (typeof ARTIFACT_NAMES)[number]))
      .map((file) => [file.path, file.content]),
  );
}

function seconds(milliseconds: number): string {
  return `${(milliseconds / 1000).toFixed(3)} s`;
}
function jsonArtifact(content: string | undefined): Record<string, unknown> | undefined {
  if (content === undefined) return undefined;
  const data: unknown = JSON.parse(content);
  if (!object(data) || data.schema_version !== "1.0" || data.execution_status !== "not_run") {
    throw new Error("Unsupported static report status/schema");
  }
  return data;
}

/** Present existing facts and report fields; no transformation, comparator or execution rules. */
export function summaryGroups(input: SummaryInput): SummaryGroup[] {
  const { result, evidence } = input;
  const groups: SummaryGroup[] = [
    {
      title: "Last recorded conversion",
      rows: result
        ? [
            { label: "Source", value: result.configuration.source },
            { label: "Operation", value: `${result.operation}: ${result.status}` },
            ...(result.operation === "plan"
              ? [
                  { label: "Proposed text files", value: String(result.files!.length) },
                  { label: "Proposed copies", value: String(result.copies!.length) },
                ]
              : result.operation === "generate"
                ? [
                    {
                      label: "Published files (including copies)",
                      value: String(result.files!.length),
                    },
                  ]
                : []),
            ...(result.destination ? [{ label: "Destination", value: result.destination }] : []),
          ]
        : [{ label: "Conversion", value: "No successful operation recorded" }],
    },
  ];
  const validation: SummaryGroup = {
    title: "Validation of this conversion",
    rows: [
      { label: "Installation", value: "Not checked" },
      { label: "Training / pipeline execution", value: "Not run by static operations" },
      { label: "Tests", value: "Not run by static operations" },
      { label: "Model reload", value: "Not run by static operations" },
    ],
  };
  if (result) {
    const analysis =
      result.analysis ?? (object(result.plan?.analysis) ? result.plan.analysis : result.plan);
    if (Array.isArray(analysis?.diagnostics)) {
      const diagnostics = analysis.diagnostics.filter(
        (item) => object(item) && typeof item.code === "string" && typeof item.message === "string",
      );
      groups.push({
        title: "Source diagnostics",
        rows: diagnostics.map((item) => ({
          label: String(item.code ?? "Diagnostic"),
          value: String(item.message ?? ""),
        })),
      });
    }
    try {
      const regression = jsonArtifact(input.artifacts["regression-coverage.json"]);
      validation.rows.push({
        label: "Supplied regression report",
        value: regression ? "Available; tests not run" : "Not available for this operation",
      });
      if (regression) {
        for (const key of [
          "pipeline_scenarios",
          "pipeline_exception_scenarios",
          "node_scenarios",
          "node_exception_scenarios",
          "model_reload_checks",
        ]) {
          if (nanoseconds(regression[key]))
            validation.rows.push({
              label: key.replaceAll("_", " "),
              value: String(regression[key]),
            });
        }
        if (object(regression.node_scenarios)) {
          for (const [name, count] of Object.entries(regression.node_scenarios)) {
            if (nanoseconds(count))
              validation.rows.push({ label: `Node scenarios: ${name}`, value: String(count) });
          }
        }
        for (const [key, value] of Object.entries(regression)) {
          if (key.startsWith("missing_") && typeof value === "boolean") {
            validation.rows.push({ label: key.replaceAll("_", " "), value: value ? "Yes" : "No" });
          }
          if (
            key.startsWith("missing_") &&
            Array.isArray(value) &&
            value.every((item) => typeof item === "string")
          ) {
            validation.rows.push({
              label: key.replaceAll("_", " "),
              value: value.length ? value.join(", ") : "None reported",
            });
          }
        }
      }
      const model = jsonArtifact(input.artifacts["model-output.json"]);
      if (model && typeof model.source_symbol === "string")
        validation.rows.push({ label: "Declared model output", value: model.source_symbol });
    } catch (error) {
      validation.rows.push({
        label: "Static reports",
        value: `Unavailable: ${error instanceof Error ? error.message : String(error)}`,
      });
    }
  }
  for (const message of input.artifactErrors)
    validation.rows.push({ label: "Report read", value: message });
  if (result) groups.push(nodeTypeSummary(input.artifacts["node-types.json"]));
  groups.push(validation, {
    title: "Session process timings (includes Python startup and I/O)",
    rows: input.timings.map((timing) => ({
      label: `${timing.operation}: ${timing.outcome}`,
      value: `${seconds(timing.durationMs)} at ${timing.recordedAt}${timing.detail ? `: ${timing.detail}` : ""}`,
    })),
  });
  if (input.validation) {
    const run = input.validation;
    groups.push({
      title: "Explicit generated-project test run",
      rows: [
        { label: "Outcome", value: run.status },
        { label: "Original generated project", value: run.project },
        { label: "Review SHA-256", value: run.plan_sha256 },
        { label: "Attempt / evidence directory", value: run.output },
        { label: "Selected runtime Python", value: run.python },
        ...(typeof run.environment?.version === "string"
          ? [{ label: "Runtime Python version", value: run.environment.version }]
          : []),
        ...(Array.isArray(run.environment?.missing) &&
        run.environment.missing.every((item) => typeof item === "string")
          ? [
              {
                label: "Missing distributions",
                value: run.environment.missing.length
                  ? run.environment.missing.join(", ")
                  : "None reported",
              },
            ]
          : []),
        {
          label: "Attempt runtime phase (copy, worker, evidence and postflight)",
          value: seconds(run.duration_ns / 1e6),
        },
        {
          label: "Worker supervision (environment, tests and cleanup)",
          value:
            run.worker_duration_ns === null
              ? "Not completed"
              : seconds(run.worker_duration_ns / 1e6),
        },
        ...Object.entries(run.tests ?? {}).map(([label, value]) => ({
          label: `Supplied tests: ${label}`,
          value: String(value),
        })),
        {
          label: "Input / original / copy / Python identities unchanged",
          value: `${run.inputs_unchanged} / ${run.original_unchanged} / ${run.snapshot_unchanged} / ${run.python_unchanged}`,
        },
        {
          label: "Log",
          value: `${run.output}/tests.log${run.log_truncated ? " (truncated)" : ""}`,
        },
        ...(run.error ? [{ label: "Runner error", value: run.error }] : []),
        {
          label: "Dependency constraints / installation",
          value: "Constraints not evaluated; no installation performed",
        },
        {
          label: "Scope",
          value:
            "Supplied tests in a private copy; scientific acceptance not established; static not_run manifests unchanged",
        },
      ],
    });
  }
  if (!input.timings.length) groups.at(-1)!.rows.push({ label: "Timings", value: "Not recorded" });
  if (evidence) {
    const report = evidence.report;
    groups.push(
      {
        title: "Imported execution report (separate run)",
        rows: [
          { label: "Report", value: evidence.filename },
          { label: "Snapshot SHA-256", value: evidence.sha256 },
          { label: "Imported at", value: evidence.importedAt },
          { label: "Case / profile", value: `${report.caseName} / ${report.profile}` },
          { label: "Outcome", value: `Reported ${report.status}` },
          { label: "Source SHA-256", value: report.sourceSha256 },
          {
            label: "Binding to this configuration",
            value: "Not verified; importing does not validate the current project",
          },
          {
            label: "Prediction reference",
            value:
              "Captured original-source validation probes; scientific acceptance not established",
          },
          ...(report.passedTests === undefined
            ? []
            : [{ label: "Delivered tests", value: `${report.passedTests} reported passing` }]),
          ...(report.error === undefined ? [] : [{ label: "Reported error", value: report.error }]),
        ],
      },
      {
        title: "Imported run timings (included in total elapsed)",
        rows: [
          {
            label: "Total elapsed",
            value:
              report.elapsedNs === undefined ? "Not recorded" : seconds(report.elapsedNs / 1e6),
          },
          ...report.stages.map((stage) => ({
            label: `${stage.name}: reported ${stage.status}`,
            value:
              stage.durationNs === undefined ? "Not recorded" : seconds(stage.durationNs / 1e6),
          })),
          {
            label: "Training alone",
            value: "Not measured separately; included in tests / Kedro pipeline",
          },
          { label: "Human effort / savings", value: "Not measured" },
        ],
      },
    );
  } else
    groups.push({
      title: "Execution evidence",
      rows: [{ label: "Imported report", value: "None selected" }],
    });
  return groups;
}

function markdownText(value: string): string {
  return value.replace(/[\r\n\u0000-\u001f\u007f]/g, " ").replace(/[\\`*_{}\[\]()<>#!|]/g, "\\$&");
}
export function summaryMarkdown(input: SummaryInput): string {
  return (
    "# Conversion and validation summary\n\n" +
    summaryGroups(input)
      .map(
        (group) =>
          `## ${group.title}\n\n` +
          group.rows
            .map((row) => `- **${markdownText(row.label)}:** ${markdownText(row.value)}\n`)
            .join(""),
      )
      .join("\n") +
    "\nSnapshots are not refreshed by file edits. Run Inspect or Preview again for new saved inputs.\n"
  );
}
