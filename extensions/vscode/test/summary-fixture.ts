/** Synthetic declarations for presentation tests; never execution approval or measured evidence. */
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
