import type { SummaryGroup } from "./summary";

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
function mapping(value: unknown): value is Record<string, string> {
  return object(value) && Object.values(value).every((item) => typeof item === "string");
}
function names(value: string[]): string {
  return value.length ? value.join(", ") : "None reported";
}

/** Present the engine's declaration report, never infer types or validate live data. */
export function nodeTypeSummary(content: string | undefined): SummaryGroup {
  const group: SummaryGroup = { title: "Declared dataset types and schemas", rows: [] };
  if (content === undefined) {
    group.rows.push({ label: "Type report", value: "Not available for this operation" });
    return group;
  }
  try {
    const data: unknown = JSON.parse(content);
    if (
      !object(data) ||
      data.schema_version !== "1.0" ||
      data.runtime_type_validation !== "not_run" ||
      !object(data.declaration) ||
      (data.declaration.schema_version !== "1.0" && data.declaration.schema_version !== "1.1") ||
      typeof data.declaration.source_sha256 !== "string" ||
      !/^[a-f0-9]{64}$/.test(data.declaration.source_sha256) ||
      !mapping(data.declaration.datasets) ||
      !strings(data.untyped_datasets)
    )
      throw new Error("Unsupported type report schema/status or declaration");
    const declaration = data.declaration;
    const datasets = declaration.datasets as Record<string, string>;
    const hasFrames = declaration.schema_version === "1.1";
    if (data.dataframe_schema_validation !== (hasFrames ? "not_run" : "not_supported"))
      throw new Error("Unsupported DataFrame schema validation status");
    const rows: SummaryGroup["rows"] = [
      { label: "Declaration version", value: String(declaration.schema_version) },
      { label: "Source SHA-256", value: declaration.source_sha256 as string },
      { label: "Declared dataset classes", value: String(Object.keys(datasets).length) },
      ...Object.entries(datasets).map(([dataset, type]) => ({
        label: `Type: ${dataset}`,
        value: type,
      })),
      { label: "Untyped datasets", value: names(data.untyped_datasets) },
      { label: "Runtime type validation", value: "Not run" },
    ];
    if (hasFrames) {
      if (!object(declaration.dataframes) || !strings(data.unschematized_dataframes))
        throw new Error("Unsupported DataFrame schema report");
      rows.push({
        label: "Declared DataFrame schemas",
        value: String(Object.keys(declaration.dataframes).length),
      });
      for (const [dataset, frame] of Object.entries(declaration.dataframes)) {
        if (
          !object(frame) ||
          !Array.isArray(frame.columns) ||
          typeof frame.allow_extra_columns !== "boolean"
        )
          throw new Error("Unsupported DataFrame metadata declaration");
        const columns = frame.columns.map((column: unknown) => {
          if (
            !object(column) ||
            typeof column.name !== "string" ||
            typeof column.dtype !== "string"
          )
            throw new Error("Unsupported DataFrame column declaration");
          return `${column.name}: ${column.dtype}`;
        });
        rows.push(
          { label: `Ordered columns: ${dataset}`, value: columns.join("; ") },
          {
            label: `Extra columns: ${dataset}`,
            value: frame.allow_extra_columns ? "Allowed" : "Rejected",
          },
        );
      }
      rows.push(
        {
          label: "Declared DataFrames without schemas",
          value: names(data.unschematized_dataframes),
        },
        { label: "DataFrame metadata validation", value: "Not run" },
      );
    } else
      rows.push({
        label: "DataFrame metadata validation",
        value: "Not supported by declaration 1.0",
      });
    if (data.runtime_checks === undefined) {
      rows.push({ label: "Runtime enforcement", value: "Not requested (declarations only)" });
    } else {
      const checks = data.runtime_checks;
      if (
        !object(checks) ||
        checks.enabled !== true ||
        checks.implementation !== (hasFrames ? "node-types-runtime-v2" : "node-types-runtime-v1") ||
        checks.scope !==
          (hasFrames
            ? "declared_dataset_classes_and_dataframe_metadata"
            : "declared_dataset_classes") ||
        !strings(checks.checked_tasks) ||
        (hasFrames && !strings(checks.schema_checked_tasks))
      )
        throw new Error("Unsupported prepared runtime policy");
      rows.push(
        { label: "Runtime enforcement", value: "Prepared; not run" },
        { label: "Tasks with class checks", value: names(checks.checked_tasks) },
      );
      if (hasFrames)
        rows.push({
          label: "Tasks with metadata checks",
          value: names(checks.schema_checked_tasks as string[]),
        });
    }
    rows.push({
      label: "Row values / index / null counts / fitted state",
      value: "Not checked by this contract",
    });
    group.rows = rows;
  } catch (error) {
    group.rows = [
      {
        label: "Type report",
        value: `Unavailable: ${error instanceof Error ? error.message : String(error)}`,
      },
    ];
  }
  return group;
}
