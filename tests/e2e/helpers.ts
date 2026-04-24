import { existsSync, readFileSync } from "node:fs";

import { expect, type APIRequestContext, type Page } from "@playwright/test";

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
    if (!key) continue;
    output[key] = value;
  }
  return output;
}

const dotEnv = loadDotEnv(".env");

function fromEnv(key: string, fallback = ""): string {
  const value = String(process.env[key] || dotEnv[key] || fallback).trim();
  return value;
}

export const adminEmail = fromEnv("TEST_ADMIN_EMAIL", "admin@mdr.local");
export const adminPassword = fromEnv("TEST_ADMIN_PASSWORD", "ChangeMe#12345");
const tokenCache = new Map<string, string>();
const LOGIN_RETRIES = 4;

export function resolveBaseUrl(baseURL: string | undefined): string {
  return String(baseURL || "http://127.0.0.1:8000").trim();
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function apiLoginToken(
  request: APIRequestContext,
  baseURL: string
): Promise<string> {
  const normalizedBaseUrl = resolveBaseUrl(baseURL);
  const cached = tokenCache.get(normalizedBaseUrl);
  if (cached) return cached;

  let lastStatus = 0;
  let lastBodyText = "";
  for (let attempt = 0; attempt <= LOGIN_RETRIES; attempt += 1) {
    const response = await request.post(`${normalizedBaseUrl}/api/v1/auth/login`, {
      form: {
        username: adminEmail,
        password: adminPassword,
      },
    });

    lastStatus = response.status();
    lastBodyText = await response.text();

    if (response.ok()) {
      const payload = JSON.parse(lastBodyText);
      const token = String(payload?.access_token || "").trim();
      expect(token, "access_token must exist in login response").not.toEqual("");
      tokenCache.set(normalizedBaseUrl, token);
      return token;
    }

    if (lastStatus !== 429 || attempt >= LOGIN_RETRIES) {
      break;
    }
    await sleep(350 * (attempt + 1));
  }

  expect(
    false,
    `API login failed for ${adminEmail}. status=${lastStatus} body=${lastBodyText}`
  ).toBeTruthy();
  return "";
}

export async function seedAuthToken(
  page: Page,
  request: APIRequestContext,
  baseURL: string
): Promise<void> {
  const token = await apiLoginToken(request, baseURL);
  await page.addInitScript(
    ([key, value]) => {
      window.localStorage.setItem(key, value);
    },
    ["access_token", token]
  );
}

export function bearerHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export async function waitForAppIdle(page: Page, timeout = 15_000): Promise<void> {
  await page
    .locator("#global-loader")
    .waitFor({ state: "hidden", timeout })
    .catch(() => undefined);
}

export async function navigateToView(
  page: Page,
  viewId: string,
  fallbackNavSelector?: string
): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  await waitForAppIdle(page, 5_000);
  await page
    .waitForFunction(() => Boolean((window as any).authManager?.user?.role), null, {
      timeout: 10_000,
    })
    .catch(() => undefined);

  const hasRuntimeNavigator = await page
    .waitForFunction(() => typeof (window as any).navigateTo === "function", null, {
      timeout: 10_000,
    })
    .then(() => true)
    .catch(() => false);

  if (hasRuntimeNavigator) {
    const navigated = await page
      .evaluate(async (targetViewId) => {
        await (window as any).navigateTo(targetViewId);
        return true;
      }, viewId)
      .catch(() => false);
    if (navigated) {
      await waitForAppIdle(page);
      const targetVisible = await page
        .locator(`#${viewId}`)
        .waitFor({ state: "visible", timeout: 2_000 })
        .then(() => true)
        .catch(() => false);
      if (targetVisible) return;
    }
  }

  if (fallbackNavSelector) {
    await page.locator(fallbackNavSelector).first().click();
  } else {
    throw new Error(`No runtime navigator available for ${viewId}`);
  }

  await waitForAppIdle(page);
}
