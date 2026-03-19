#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

function printUsage() {
  console.log(
    [
      "Chinese Encoding Guard CLI",
      "",
      "Usage:",
      "  ceg check [args...]",
      "  ceg fix [args...]",
      "",
      "Examples:",
      "  ceg check --paths ./frontend/src --strict",
      "  ceg check --git-tracked --strict",
      "  ceg fix --paths ./backend/src/main/resources",
      "  ceg fix --git-tracked",
      "  ceg fix --paths ./some/file.sql --dry-run",
      "",
      "Pass-through:",
      "  All args after check/fix are passed to the Python scripts.",
      "  check -> scripts/check_encoding.py",
      "  fix   -> scripts/fix_to_utf8.py"
    ].join("\n")
  );
}

function resolvePython() {
  const candidates =
    process.platform === "win32"
      ? [
          { cmd: "py", prefixArgs: ["-3"] },
          { cmd: "python", prefixArgs: [] },
          { cmd: "python3", prefixArgs: [] }
        ]
      : [
          { cmd: "python3", prefixArgs: [] },
          { cmd: "python", prefixArgs: [] }
        ];

  for (const candidate of candidates) {
    const test = spawnSync(candidate.cmd, [...candidate.prefixArgs, "--version"], {
      stdio: "ignore"
    });
    if (!test.error && test.status === 0) {
      return candidate;
    }
  }
  return null;
}

function main() {
  const args = process.argv.slice(2);
  const command = args[0];
  const passthrough = args.slice(1);

  if (!command || command === "--help" || command === "-h" || command === "help") {
    printUsage();
    process.exit(0);
  }

  const scriptByCommand = {
    check: path.resolve(
      __dirname,
      "..",
      "skills",
      "chinese-encoding-guard",
      "scripts",
      "check_encoding.py"
    ),
    fix: path.resolve(
      __dirname,
      "..",
      "skills",
      "chinese-encoding-guard",
      "scripts",
      "fix_to_utf8.py"
    )
  };

  const scriptPath = scriptByCommand[command];
  if (!scriptPath) {
    console.error(`Unknown command: ${command}`);
    printUsage();
    process.exit(1);
  }

  const python = resolvePython();
  if (!python) {
    console.error(
      "Python was not found. Install Python 3 first, then retry."
    );
    process.exit(1);
  }

  const run = spawnSync(
    python.cmd,
    [...python.prefixArgs, scriptPath, ...passthrough],
    { stdio: "inherit" }
  );

  if (run.error) {
    console.error(`Failed to run Python script: ${run.error.message}`);
    process.exit(1);
  }

  process.exit(typeof run.status === "number" ? run.status : 1);
}

main();

