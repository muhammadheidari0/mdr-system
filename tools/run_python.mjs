import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";

function candidateList() {
  const candidates = [];
  const configured = String(process.env.PYTHON_BIN || "").trim();
  if (configured) {
    candidates.push(configured);
  }

  const venvPython =
    process.platform === "win32"
      ? resolve(process.cwd(), ".venv", "Scripts", "python.exe")
      : resolve(process.cwd(), ".venv", "bin", "python");
  if (existsSync(venvPython)) {
    candidates.push(venvPython);
  }

  candidates.push("python", "python3");
  return Array.from(new Set(candidates));
}

function shouldTryNextCandidate(status, stdout, stderr) {
  if (status === 0) {
    return false;
  }
  const text = `${stdout || ""}\n${stderr || ""}`.toLowerCase();
  return text.includes("no module named");
}

function childEnv() {
  const env = { ...process.env };
  const debug = String(env.DEBUG || "").trim().toLowerCase();
  const validDebugValues = new Set(["", "1", "true", "yes", "on", "0", "false", "no", "off"]);
  if (!validDebugValues.has(debug)) {
    delete env.DEBUG;
  }
  return env;
}

const args = process.argv.slice(2);
if (!args.length) {
  console.error("Usage: node tools/run_python.mjs <python-args...>");
  process.exit(2);
}

const candidates = candidateList();
let lastStatus = 1;

for (let i = 0; i < candidates.length; i += 1) {
  const pythonBin = candidates[i];
  const result = spawnSync(pythonBin, args, {
    encoding: "utf-8",
    env: childEnv(),
    stdio: "pipe",
  });

  if (result.error) {
    continue;
  }

  if (result.stdout) {
    process.stdout.write(result.stdout);
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }

  const status = typeof result.status === "number" ? result.status : 1;
  lastStatus = status;

  if (!shouldTryNextCandidate(status, result.stdout, result.stderr)) {
    process.exit(status);
  }

  if (i < candidates.length - 1) {
    console.error(`[run_python] ${pythonBin} missing modules, trying next candidate...`);
  }
}

process.exit(lastStatus);
