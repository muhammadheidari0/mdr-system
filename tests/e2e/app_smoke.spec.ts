import { expect, test } from "@playwright/test";

import { resolveBaseUrl, seedAuthToken } from "./helpers";

test("public login page loads", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator("#loginForm")).toBeVisible();
  await expect(page.locator("#email")).toBeVisible();
  await expect(page.locator("#password")).toBeVisible();
});

test("authenticated user can navigate primary views", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  await seedAuthToken(page, request, resolvedBaseUrl);

  await page.goto("/");
  await expect(page.locator("#view-dashboard")).toHaveClass(/active/);

  await page.locator("#nav-edms").click();
  await expect(page.locator("#view-edms")).toHaveClass(/active/);

  await page.locator("#nav-reports").click();
  await expect(page.locator("#view-reports")).toHaveClass(/active/);

  await expect(page.locator("#nav-settings")).toBeVisible();
  await page.locator("#nav-settings").click();
  await expect(page.locator("#view-settings")).toHaveClass(/active/);
});

test("authenticated user can switch contractor and consultant tabs", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  await seedAuthToken(page, request, resolvedBaseUrl);

  await page.goto("/");

  await page.locator("#nav-contractor").click();
  await expect(page.locator("#view-contractor")).toHaveClass(/active/);
  await expect(page.locator(".contractor-tab-btn[data-contractor-tab='requests']")).toBeVisible();
  await page.locator(".contractor-tab-btn[data-contractor-tab='requests']").click();
  await expect(page.locator("#contractor-panel-requests")).toHaveClass(/active/);

  await page.locator("#nav-consultant").click();
  await expect(page.locator("#view-consultant")).toHaveClass(/active/);
  await expect(page.locator(".consultant-tab-btn[data-consultant-tab='defects']")).toBeVisible();
  await page.locator(".consultant-tab-btn[data-consultant-tab='defects']").click();
  await expect(page.locator("#consultant-panel-defects")).toHaveClass(/active/);
});
