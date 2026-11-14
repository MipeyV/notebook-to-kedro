const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const repository = path.resolve(__dirname, "../../..");
const output = path.join(repository, "generated/notebook-to-kedro-0.1.0.vsix");
fs.mkdirSync(path.dirname(output), { recursive: true });
const manifest = require("@vscode/vsce/package.json");
const executable = path.join(
  path.dirname(require.resolve("@vscode/vsce/package.json")),
  manifest.bin.vsce,
);
const result = spawnSync(
  process.execPath,
  [executable, "package", "--no-dependencies", "--out", output],
  { stdio: "inherit", windowsHide: true },
);
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
