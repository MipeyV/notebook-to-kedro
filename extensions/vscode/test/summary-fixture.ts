/** Synthetic declarations for presentation tests; never execution approval or measured evidence. */
export function declaredNodeTypes(schema = false, enforced = false): Record<string, any> {
  return {
    schema_version: "1.0",
    declaration: {
      schema_version: schema ? "1.1" : "1.0",
      source_sha256: "b".repeat(64),
      datasets: { raw: "pandas.DataFrame", features: "pandas.DataFrame", score: "float" },
      ...(schema
        ? {
            dataframes: {
              raw: {
                columns: [
                  { name: "income", dtype: "float64" },
                  { name: "age", dtype: "int64" },
                ],
                allow_extra_columns: true,
              },
            },
          }
        : {}),
    },
    untyped_datasets: ["model"],
    runtime_type_validation: "not_run",
    dataframe_schema_validation: schema ? "not_run" : "not_supported",
    ...(schema ? { unschematized_dataframes: ["features"] } : {}),
    ...(enforced
      ? {
          runtime_checks: {
            enabled: true,
            implementation: schema ? "node-types-runtime-v2" : "node-types-runtime-v1",
            scope: schema
              ? "declared_dataset_classes_and_dataframe_metadata"
              : "declared_dataset_classes",
            checked_tasks: ["task-0001", "task-0002"],
            ...(schema ? { schema_checked_tasks: ["task-0001"] } : {}),
          },
        }
      : {}),
  };
}

export function declaredJourney(): Record<string, any> {
  const names = [
    "reference.log",
    "build.log",
    "venv.log",
    "install.log",
    "runtime.json",
    "pytest.log",
    "kedro.log",
    "cli-reload.log",
    "false-oracle.log",
  ];
  return {
    schema_version: "1.0",
    case: "credit_pipeline",
    profile: "default",
    status: "passed",
    oracle_basis: "captured_original_source",
    independent_scientific_oracle: false,
    human_effort: null,
    baseline: null,
    human_savings: null,
    source_inventory: { "workflow.ipynb": "a".repeat(64) },
    elapsed_ns: 10_000_000_000,
    passed_tests: 12,
    cli_reload: "matched",
    false_oracle_control: "rejected_after_storage",
    source_unchanged: true,
    generated_project_unchanged: true,
    stages: names.map((name) => ({
      log: `C:\\synthetic\\${name}`,
      status: "passed",
      duration_ns: 1_000_000_000,
      expected_returncode: name === "false-oracle.log" ? 1 : 0,
      returncode: name === "false-oracle.log" ? 1 : 0,
    })),
  };
}
