import { defineConfig } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

function loadDotEnv(path: string): Record<string, string> {
  if (!existsSync(path)) return {};
  const output: Record<string, string> = {};
  const content = readFileSync(path, "utf8");
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim();
    if (key) output[key] = value;
  }
  return output;
}

function fromEnv(key: string, fallback = ""): string {
  return String(process.env[key] || dotEnv[key] || fallback).trim();
}

function boolEnvForServer(key: string, fallback: string): string {
  const value = fromEnv(key, fallback).toLowerCase();
  return ["1", "true", "yes", "on", "0", "false", "no", "off"].includes(value)
    ? value
    : fallback;
}

function firstExistingPath(paths: string[]): string {
  for (const path of paths) {
    const trimmed = String(path || "").trim();
    if (trimmed && existsSync(trimmed)) return trimmed;
  }
  return "";
}

function findSystemBrowserExecutable(): string {
  if (process.platform !== "win32") return "";
  return firstExistingPath([
    `${process.env.PROGRAMFILES || "C:\\Program Files"}\\Google\\Chrome\\Application\\chrome.exe`,
    `${process.env["PROGRAMFILES(X86)"] || "C:\\Program Files (x86)"}\\Google\\Chrome\\Application\\chrome.exe`,
    `${process.env.LOCALAPPDATA || ""}\\Google\\Chrome\\Application\\chrome.exe`,
    `${process.env.PROGRAMFILES || "C:\\Program Files"}\\Microsoft\\Edge\\Application\\msedge.exe`,
    `${process.env["PROGRAMFILES(X86)"] || "C:\\Program Files (x86)"}\\Microsoft\\Edge\\Application\\msedge.exe`,
  ]);
}

const dotEnv = loadDotEnv(".env");
const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:8010";
const parsedBaseURL = new URL(baseURL);
const webServerHost = parsedBaseURL.hostname || "127.0.0.1";
const webServerPort = Number(parsedBaseURL.port || "8000");
const requestedSystemChrome = process.env.PW_USE_SYSTEM_CHROME === "1";
const configuredSystemBrowser = String(process.env.PW_CHROME_EXECUTABLE_PATH || "").trim();
const systemBrowserExecutable = firstExistingPath([configuredSystemBrowser]) || (!process.env.CI ? findSystemBrowserExecutable() : "");
const useSystemBrowser = Boolean(systemBrowserExecutable) || requestedSystemChrome;
const venvPython =
  process.platform === "win32"
    ? resolve(".venv", "Scripts", "python.exe")
    : resolve(".venv", "bin", "python");
const pythonExecutable = String(process.env.E2E_PYTHON || "").trim() || (existsSync(venvPython) ? venvPython : "python");
const e2eDatabaseUrl =
  fromEnv("DATABASE_URL") ||
  "postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app";
const configuredWorkers = Number.parseInt(String(process.env.E2E_WORKERS || "1"), 10);
const e2eWorkers = Number.isFinite(configuredWorkers) && configuredWorkers > 0 ? configuredWorkers : 1;
const testAdminEmail = fromEnv("TEST_ADMIN_EMAIL", "admin@mdr.local");
const testAdminPassword = fromEnv("TEST_ADMIN_PASSWORD");
const shouldSyncAdmin = String(process.env.E2E_SYNC_ADMIN || "1").trim() !== "0" && Boolean(testAdminPassword);
const serverCommandPrefix = shouldSyncAdmin ? `"${pythonExecutable}" create_admin.py && ` : "";

const launchOptions = systemBrowserExecutable
  ? { executablePath: systemBrowserExecutable }
  : undefined;

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 90_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : e2eWorkers,
  reporter: [
    ["list"],
    ["html", { outputFolder: "reports/playwright-html", open: "never" }],
  ],
  use: {
    baseURL,
    acceptDownloads: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: useSystemBrowser ? "off" : "retain-on-failure",
    channel: requestedSystemChrome && !systemBrowserExecutable ? "chrome" : undefined,
    launchOptions,
  },
  webServer: {
    command: `${serverCommandPrefix}"${pythonExecutable}" -m uvicorn app.main:app --host ${webServerHost} --port ${webServerPort}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      APP_ENV: process.env.APP_ENV || "test",
      DEBUG: boolEnvForServer("DEBUG", "false"),
      DATABASE_URL: e2eDatabaseUrl,
      ADMIN_EMAIL: fromEnv("ADMIN_EMAIL", testAdminEmail),
      ADMIN_PASSWORD: fromEnv("ADMIN_PASSWORD", testAdminPassword),
      TEST_ADMIN_EMAIL: testAdminEmail,
      TEST_ADMIN_PASSWORD: testAdminPassword,
      RATE_LIMIT_MAX_REQUESTS: process.env.RATE_LIMIT_MAX_REQUESTS || "5000",
      RATE_LIMIT_WINDOW_SECONDS: process.env.RATE_LIMIT_WINDOW_SECONDS || "60",
    },
  },
});
