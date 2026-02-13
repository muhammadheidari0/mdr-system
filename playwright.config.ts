import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:8000";
const parsedBaseURL = new URL(baseURL);
const webServerHost = parsedBaseURL.hostname || "127.0.0.1";
const webServerPort = Number(parsedBaseURL.port || "8000");
const useSystemChrome = process.env.PW_USE_SYSTEM_CHROME === "1";
const systemChromeExecutable = String(process.env.PW_CHROME_EXECUTABLE_PATH || "").trim();
const venvPython =
  process.platform === "win32"
    ? resolve(".venv", "Scripts", "python.exe")
    : resolve(".venv", "bin", "python");
const pythonExecutable = String(process.env.E2E_PYTHON || "").trim() || (existsSync(venvPython) ? venvPython : "python");
const e2eDatabaseUrl =
  String(process.env.DATABASE_URL || "").trim() ||
  "postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app";

const launchOptions = systemChromeExecutable
  ? { executablePath: systemChromeExecutable }
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
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ["list"],
    ["html", { outputFolder: "reports/playwright-html", open: "never" }],
  ],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: useSystemChrome ? "off" : "retain-on-failure",
    channel: useSystemChrome ? "chrome" : undefined,
    launchOptions,
  },
  webServer: {
    command: `"${pythonExecutable}" -m uvicorn app.main:app --host ${webServerHost} --port ${webServerPort}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      APP_ENV: process.env.APP_ENV || "test",
      DATABASE_URL: e2eDatabaseUrl,
      RATE_LIMIT_MAX_REQUESTS: process.env.RATE_LIMIT_MAX_REQUESTS || "5000",
      RATE_LIMIT_WINDOW_SECONDS: process.env.RATE_LIMIT_WINDOW_SECONDS || "60",
    },
  },
});
