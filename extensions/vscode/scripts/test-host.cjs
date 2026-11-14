const fs = require("node:fs/promises");
const path = require("node:path");
const { runTests } = require("@vscode/test-electron");

async function main() {
  if (!process.env.NTK_TEST_PYTHON) throw new Error("Set NTK_TEST_PYTHON to an engine interpreter");
  const repository = path.resolve(__dirname, "../../..");
  const generated = path.join(repository, "generated");
  await fs.mkdir(generated, { recursive: true });
  const workspace = await fs.mkdtemp(path.join(generated, "vscode-host-"));
  await fs.cp(
    path.join(repository, "examples/functional_workflow"),
    path.join(workspace, "examples/functional_workflow"),
    { recursive: true },
  );
  await fs.copyFile(
    path.join(repository, "examples/kedro_profiles/team_training.json"),
    path.join(workspace, "profile.json"),
  );
  await fs.copyFile(
    path.join(repository, "tests/fixtures/notebooks/simple_training.ipynb"),
    path.join(workspace, "source.ipynb"),
  );
  await fs.writeFile(
    path.join(workspace, "blocked.py"),
    "print('unsupported top-level statement')\n",
  );
  const config = {
    schema_version: "1.0",
    project_root: ".",
    source_kind: "functional",
    source: "examples/functional_workflow/workflow.py",
    workflow_configuration: "examples/functional_workflow/workflow.json",
    architecture_profile: "profile.json",
    regression_contract: "examples/functional_workflow/regression.json",
  };
  await fs.writeFile(path.join(workspace, "project.json"), JSON.stringify(config));
  await fs.writeFile(
    path.join(workspace, "blocked.json"),
    JSON.stringify({ ...config, source: "blocked.py" }),
  );
  await fs.writeFile(
    path.join(workspace, "notebook.json"),
    JSON.stringify({
      schema_version: "1.0",
      project_root: ".",
      source_kind: "notebook",
      source: "source.ipynb",
    }),
  );
  await runTests({
    version: "1.145.3",
    vscodeExecutablePath: process.env.VSCODE_EXECUTABLE_PATH,
    extensionDevelopmentPath: path.resolve(__dirname, ".."),
    extensionTestsPath: path.resolve(__dirname, "../dist/test/host.js"),
    launchArgs: [
      workspace,
      "--user-data-dir",
      path.join(workspace, "user-data"),
      "--extensions-dir",
      path.join(workspace, "extensions"),
      "--disable-extensions",
      "--disable-workspace-trust",
      "--skip-welcome",
      "--skip-release-notes",
      "--disable-gpu",
    ],
    extensionTestsEnv: {
      ELECTRON_RUN_AS_NODE: undefined,
      NTK_TEST_WORKSPACE: workspace,
      NTK_TEST_PYTHON: process.env.NTK_TEST_PYTHON,
      NTK_UI_REVIEW: process.env.NTK_UI_REVIEW,
    },
  });
  console.log(`Host test workspace: ${workspace}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
