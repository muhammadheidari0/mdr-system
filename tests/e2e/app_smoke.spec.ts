import { expect, test, type APIRequestContext, type APIResponse, type Page } from "@playwright/test";

import {
  apiLoginToken,
  bearerHeaders,
  navigateToView,
  resolveBaseUrl,
  seedAuthToken,
} from "./helpers";

function uniqueSmokeCode(prefix: string): string {
  const stamp = Date.now().toString(36).toUpperCase();
  const random = Math.random().toString(36).replace(/[^a-z0-9]/gi, "").slice(2, 8).toUpperCase();
  return `${prefix}${stamp}${random}`;
}

async function expectOkJson(response: APIResponse, label: string): Promise<any> {
  const bodyText = await response.text();
  expect(response.ok(), `${label} failed. status=${response.status()} body=${bodyText}`).toBeTruthy();
  if (!bodyText) return {};
  try {
    return JSON.parse(bodyText);
  } catch {
    return {};
  }
}

async function loginTokenFor(
  request: APIRequestContext,
  baseUrl: string,
  email: string,
  password: string
): Promise<string> {
  const body = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/auth/login`, {
      form: {
        username: email,
        password,
      },
    }),
    `login limited user ${email}`
  );
  const token = String(body?.access_token || "").trim();
  expect(token).not.toEqual("");
  return token;
}

async function seedToken(page: Page, token: string): Promise<void> {
  await page.addInitScript(
    ([key, value]) => {
      window.localStorage.setItem(key, value);
    },
    ["access_token", token]
  );
}

async function createScopedUiUser(
  request: APIRequestContext,
  baseUrl: string,
  adminHeaders: Record<string, string>,
  orgType: "contractor" | "consultant" | "employer" | "dcc",
  organizationRole: "viewer" | "user" | "manager" = "viewer"
): Promise<{ id: number; email: string; password: string; token: string }> {
  const orgCode = uniqueSmokeCode(`E2E_${orgType.toUpperCase()}_`).slice(0, 48);
  const orgBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/organizations/upsert`, {
      headers: {
        ...adminHeaders,
        "Content-Type": "application/json",
      },
      data: {
        code: orgCode,
        name: `E2E ${orgType} ${orgCode}`,
        org_type: orgType,
        is_active: true,
      },
    }),
    `create ${orgType} organization for smoke`
  );
  const organizationId = Number(orgBody?.item?.id || orgBody?.id || 0);
  expect(organizationId).toBeGreaterThan(0);

  const email = `${uniqueSmokeCode(`ui_${orgType}_`).toLowerCase()}@mdr.local`;
  const password = `Pwd!${uniqueSmokeCode("SMK").slice(0, 14)}`;
  const userBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/users/`, {
      headers: {
        ...adminHeaders,
        "Content-Type": "application/json",
      },
      data: {
        email,
        password,
        full_name: `E2E ${orgType} viewer`,
        role: "viewer",
        organization_id: organizationId,
        organization_role: organizationRole,
        is_active: true,
      },
    }),
    `create ${orgType} scoped UI user`
  );
  const id = Number(userBody?.id || 0);
  expect(id).toBeGreaterThan(0);
  const token = await loginTokenFor(request, baseUrl, email, password);
  return { id, email, password, token };
}

async function getPermissionMatrix(
  request: APIRequestContext,
  baseUrl: string,
  adminHeaders: Record<string, string>,
  category: string
): Promise<{ matrix: Record<string, Record<string, boolean>>; permissions: string[] }> {
  const body = await expectOkJson(
    await request.get(`${baseUrl}/api/v1/settings/permissions/matrix?category=${encodeURIComponent(category)}`, {
      headers: adminHeaders,
    }),
    `get ${category} permission matrix`
  );
  expect(body?.category).toBe(category);
  return {
    matrix: body?.matrix || {},
    permissions: Array.isArray(body?.permissions) ? body.permissions.map((item: unknown) => String(item)) : [],
  };
}

async function savePermissionMatrix(
  request: APIRequestContext,
  baseUrl: string,
  adminHeaders: Record<string, string>,
  category: string,
  matrix: Record<string, Record<string, boolean>>
): Promise<void> {
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/permissions/matrix?category=${encodeURIComponent(category)}`, {
      headers: {
        ...adminHeaders,
        "Content-Type": "application/json",
      },
      data: {
        matrix,
      },
    }),
    `save ${category} permission matrix`
  );
}

async function openModuleSettings(
  page: Page,
  hubViewId: "view-contractor" | "view-consultant",
  settingsViewId: "view-contractor-settings" | "view-consultant-settings",
  expectedRootSelector: string
): Promise<void> {
  await navigateToView(page, hubViewId, `[data-nav-target="${hubViewId}"]`);
  await expect(page.locator(`#${hubViewId}`)).toBeVisible({ timeout: 20_000 });
  const settingsButton = page.locator(`#${hubViewId} [data-nav-target="${settingsViewId}"]`).first();
  await expect(settingsButton).toBeVisible({ timeout: 20_000 });
  await settingsButton.click();
  await expect(page.locator(`#${settingsViewId}`)).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(expectedRootSelector)).toBeVisible({ timeout: 20_000 });
}

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

test("authenticated admin can open EDMS forms monitoring tab", async ({
  page,
  request,
  baseURL,
}) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);

  const navigationBody = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/auth/navigation`, { headers }),
    "admin navigation with EDMS forms tab"
  );
  expect(navigationBody?.edms_tabs?.forms).toBe(true);
  expect(navigationBody?.edms_tabs?.meeting_minutes).toBe(true);

  const listBody = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/edms/forms/list?limit=5`, { headers }),
    "EDMS forms list endpoint"
  );
  expect(listBody?.ok).toBeTruthy();
  expect(Array.isArray(listBody?.data)).toBeTruthy();

  const minutesListBody = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/meeting-minutes/list?limit=5`, { headers }),
    "meeting minutes list endpoint"
  );
  expect(minutesListBody?.ok).toBeTruthy();
  expect(Array.isArray(minutesListBody?.data)).toBeTruthy();

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await navigateToView(page, "view-edms", '[data-nav-target="view-edms"]');
  await expect(page.locator("#view-edms")).toBeVisible();

  await expect(page.locator("#edms-tab-meeting-minutes")).toBeVisible({ timeout: 20_000 });
  await page.locator("#edms-tab-meeting-minutes").click();
  await expect(page.locator("#view-meeting-minutes")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#meetingMinutesTableBody")).toBeVisible();

  const listResponsePromise = page
    .waitForResponse(
      (response) =>
        response.url().includes("/api/v1/edms/forms/list") &&
        response.request().method() === "GET",
      { timeout: 15_000 }
    )
    .catch(() => null);

  await expect(page.locator("#edms-tab-forms")).toBeVisible({ timeout: 20_000 });
  await page.locator("#edms-tab-forms").click();
  await expect(page.locator("#view-edms-forms")).toBeVisible({ timeout: 20_000 });

  const listResponse = await listResponsePromise;
  if (listResponse) {
    expect(listResponse.ok(), `EDMS forms UI request failed: ${listResponse.status()}`).toBeTruthy();
  }
  await expect(page.locator("#edmsFormsTotal")).toBeVisible();
  await expect(page.locator("#edmsFormsTableBody")).toBeVisible();
  await expect
    .poll(async () => (await page.locator("#edmsFormsTableBody").innerText()).trim().length)
    .toBeGreaterThan(0);
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

test("authenticated admin can access module settings and system settings tabs", async ({
  page,
  request,
  baseURL,
}) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  await seedAuthToken(page, request, resolvedBaseUrl);

  await page.goto("/");

  await openModuleSettings(
    page,
    "view-contractor",
    "view-contractor-settings",
    "#contractorSiteLogCatalogsRoot"
  );
  await expect(page.locator('[data-contractor-settings-tab="report-settings"]')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".contractor-catalog-subtab")).toHaveCount(6);
  await expect(page.locator(".contractor-report-catalog-panel")).toBeVisible({ timeout: 20_000 });

  await openModuleSettings(
    page,
    "view-consultant",
    "view-consultant-settings",
    "#consultantOpenProjectOpsRoot"
  );
  await page.locator('[data-consultant-settings-tab="site-log-activity"]').click();
  await expect(page.locator("#consultantSiteLogActivityCatalogRoot")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".consultant-activity-subtab")).toHaveCount(3);
  await expect(page.locator('[data-catalog-type="activity"]')).toBeVisible({ timeout: 20_000 });

  await expect(page.locator("#nav-settings")).toBeVisible({ timeout: 20_000 });
  await navigateToView(page, "view-settings", '[data-nav-target="view-settings"]');
  await expect(page.locator("#view-settings")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#settingsUsersTabRoot")).toBeVisible({ timeout: 20_000 });

  await page.locator('#view-settings [data-settings-tab][data-tab="organizations"]').click();
  await expect(page.locator("#tab-organizations")).toHaveClass(/active/);
  await expect(page.locator("#settingsOrganizationsTabRoot")).toBeVisible({ timeout: 20_000 });

  await page.locator('#view-settings [data-settings-tab][data-tab="permissions"]').click();
  await expect(page.locator("#tab-permissions")).toHaveClass(/active/);
  await expect(page.locator("#settingsPermissionsTabRoot")).toBeVisible({ timeout: 20_000 });
});

test("limited contractor viewer cannot access hidden hubs or settings views", async ({
  page,
  request,
  baseURL,
}) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const adminToken = await apiLoginToken(request, resolvedBaseUrl);
  const adminHeaders = bearerHeaders(adminToken);
  const matrixPayload = await getPermissionMatrix(request, resolvedBaseUrl, adminHeaders, "contractor");
  const originalMatrix = JSON.parse(JSON.stringify(matrixPayload.matrix || {})) as Record<
    string,
    Record<string, boolean>
  >;
  const availablePermissions = new Set(matrixPayload.permissions);
  const workingMatrix = JSON.parse(JSON.stringify(originalMatrix || {})) as Record<
    string,
    Record<string, boolean>
  >;
  workingMatrix.viewer = { ...(workingMatrix.viewer || {}) };

  const setViewerPermission = (permission: string, allowed: boolean) => {
    if (availablePermissions.has(permission)) {
      workingMatrix.viewer[permission] = allowed;
    }
  };

  [
    "dashboard:read",
    "hub_contractor:read",
    "module_site_logs_contractor:read",
    "site_logs:read",
  ].forEach((permission) => setViewerPermission(permission, true));

  [
    "settings:read",
    "module_settings_edms:read",
    "module_settings_contractor:read",
    "module_settings_consultant:read",
    "hub_edms:read",
    "module_archive:read",
    "module_transmittal:read",
    "module_correspondence:read",
    "hub_consultant:read",
    "module_site_logs_consultant:read",
    "module_comm_items_consultant:read",
    "module_permit_qc_consultant:read",
  ].forEach((permission) => setViewerPermission(permission, false));

  let limitedUser: { id: number; email: string; password: string; token: string } | null = null;
  await savePermissionMatrix(request, resolvedBaseUrl, adminHeaders, "contractor", workingMatrix);

  try {
    limitedUser = await createScopedUiUser(
      request,
      resolvedBaseUrl,
      adminHeaders,
      "contractor",
      "viewer"
    );
    const navigationBody = await expectOkJson(
      await request.get(`${resolvedBaseUrl}/api/v1/auth/navigation`, {
        headers: bearerHeaders(limitedUser.token),
      }),
      "limited contractor navigation"
    );
    expect(navigationBody?.permission_category).toBe("contractor");
    expect(navigationBody?.hubs?.contractor).toBe(true);
    expect(navigationBody?.hubs?.consultant).toBe(false);
    expect(navigationBody?.hubs?.edms).toBe(false);
    expect(navigationBody?.module_settings_visibility?.contractor).toBe(false);
    expect(navigationBody?.module_settings_visibility?.consultant).toBe(false);

    await seedToken(page, limitedUser.token);
    await page.goto("/");

    await expect(page.locator("#view-contractor")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("#nav-contractor")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("#nav-settings")).toBeHidden();
    await expect(page.locator("#nav-consultant")).toBeHidden();
    await expect(page.locator("#nav-edms")).toBeHidden();
    await expect(page.locator('#view-contractor [data-nav-target="view-contractor-settings"]')).toBeHidden();

    const settingsNavigationBlocked = await page.evaluate(async () => {
      try {
        await (window as any).navigateTo("view-settings");
        return false;
      } catch {
        return true;
      }
    });
    expect(settingsNavigationBlocked).toBe(true);
    await expect(page.locator("#view-settings")).toBeHidden();

    await page.evaluate(async () => {
      try {
        await (window as any).navigateTo("view-consultant");
      } catch {
      }
    });
    await expect(page.locator("#view-consultant")).toBeHidden();
    await expect(page.locator("#view-contractor")).toBeVisible();
  } finally {
    await savePermissionMatrix(request, resolvedBaseUrl, adminHeaders, "contractor", originalMatrix);
    if (limitedUser) {
      await request.delete(`${resolvedBaseUrl}/api/v1/users/${limitedUser.id}`, {
        headers: adminHeaders,
      });
    }
  }
});
