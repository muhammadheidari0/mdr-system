import { expect, test } from "@playwright/test";

import { navigateToView, resolveBaseUrl, seedAuthToken } from "./helpers";

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
  await expect(page.locator("#view-dashboard")).toBeVisible();

  await navigateToView(page, "view-edms", '[data-nav-target="view-edms"]');
  await expect(page.locator("#view-edms")).toBeVisible();

  await navigateToView(page, "view-reports", '[data-nav-target="view-reports"]');
  await expect(page.locator("#view-reports")).toBeVisible();

  await expect(page.locator("#nav-settings")).toBeVisible();
  await navigateToView(page, "view-settings", '[data-nav-target="view-settings"]');
  await expect(page.locator("#view-settings")).toBeVisible();
});

test("authenticated user can switch contractor and consultant tabs", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  await seedAuthToken(page, request, resolvedBaseUrl);

  await page.goto("/");

  await navigateToView(page, "view-contractor", '[data-nav-target="view-contractor"]');
  await expect(page.locator("#view-contractor")).toBeVisible();
  await expect(page.locator(".contractor-tab-btn[data-contractor-tab='requests']")).toBeVisible();
  await page.locator(".contractor-tab-btn[data-contractor-tab='requests']").click();
  await expect(page.locator("#contractor-panel-requests")).toHaveClass(/active/);

  await navigateToView(page, "view-consultant", '[data-nav-target="view-consultant"]');
  await expect(page.locator("#view-consultant")).toBeVisible();
  await expect(page.locator(".consultant-tab-btn[data-consultant-tab='defects']")).toBeVisible();
  await page.locator(".consultant-tab-btn[data-consultant-tab='defects']").click();
  await expect(page.locator("#consultant-panel-defects")).toHaveClass(/active/);
});
