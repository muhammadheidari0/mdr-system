import { expect, test, type APIRequestContext, type APIResponse, type Page } from "@playwright/test";

import { apiLoginToken, bearerHeaders, navigateToView, resolveBaseUrl, seedAuthToken } from "./helpers";

type SiteLogContext = {
  projectCode: string;
  disciplineCode: string;
  organizationId: number;
  organizationName: string;
};

function uniqueCode(prefix: string, size = 6): string {
  const random = Math.random().toString(36).replace(/[^a-z0-9]/gi, "").toUpperCase();
  const stamp = Date.now().toString(36).toUpperCase();
  return `${prefix}${stamp}${random}`.slice(0, Math.max(prefix.length + 2, size));
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

async function ensureSiteLogContext(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>
): Promise<SiteLogContext> {
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };
  const projectCode = uniqueCode("SLP", 8);
  const disciplineCode = uniqueCode("SD", 5);
  const organizationCode = uniqueCode("SLCO", 10);
  const organizationName = `Site Log Contractor ${organizationCode}`;

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/projects/upsert`, {
      headers: jsonHeaders,
      data: {
        code: projectCode,
        project_name: projectCode,
        name_e: projectCode,
        is_active: true,
      },
    }),
    "settings project upsert (site log e2e)"
  );

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/disciplines/upsert`, {
      headers: jsonHeaders,
      data: {
        code: disciplineCode,
        name_e: disciplineCode,
        name_p: disciplineCode,
      },
    }),
    "settings discipline upsert (site log e2e)"
  );

  const orgBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/organizations/upsert`, {
      headers: jsonHeaders,
      data: {
        code: organizationCode,
        name: organizationName,
        org_type: "contractor",
        is_active: true,
      },
    }),
    "settings organization upsert (site log e2e)"
  );

  const organizationId = Number(orgBody?.item?.id || orgBody?.id || 0);
  expect(organizationId).toBeGreaterThan(0);

  return {
    projectCode,
    disciplineCode,
    organizationId,
    organizationName,
  };
}

async function gotoContractorSettings(page: Page): Promise<void> {
  await navigateToView(page, "view-contractor-settings", '[data-nav-target="view-contractor"]');
  await expect(page.locator("#view-contractor-settings")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#contractorSiteLogCatalogsRoot")).toBeVisible({ timeout: 20_000 });
}

async function gotoContractor(page: Page): Promise<void> {
  await navigateToView(page, "view-contractor", '[data-nav-target="view-contractor"]');
  await expect(page.locator("#view-contractor")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#contractor-panel-execution .site-logs-card")).toBeVisible({ timeout: 20_000 });
}

async function saveCatalogViaUi(
  page: Page,
  catalogType: "role" | "equipment" | "equipment_status",
  code: string,
  label: string,
  sortOrder: number
): Promise<void> {
  const card = page.locator(`[data-catalog-type="${catalogType}"]`).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.locator('[data-catalog-form-field="code"]').fill(code);
  await card.locator('[data-catalog-form-field="label"]').fill(label);
  await card.locator('[data-catalog-form-field="sort_order"]').fill(String(sortOrder));
  const activeCheckbox = card.locator('[data-catalog-form-field="is_active"]');
  if (!(await activeCheckbox.isChecked())) {
    await activeCheckbox.check();
  }
  await card.locator('[data-contractor-catalog-action="save-item"]').click();
  await expect(card.locator("tbody")).toContainText(label, { timeout: 15_000 });
}

async function updateCatalogLabelViaUi(
  page: Page,
  catalogType: "role" | "equipment" | "equipment_status",
  code: string,
  nextLabel: string
): Promise<void> {
  const card = page.locator(`[data-catalog-type="${catalogType}"]`).first();
  const editButton = card.locator(
    `[data-contractor-catalog-action="edit-item"][data-item-code="${code}"]`
  ).first();
  await expect(editButton).toBeVisible({ timeout: 15_000 });
  await editButton.click();
  await card.locator('[data-catalog-form-field="label"]').fill(nextLabel);
  await card.locator('[data-contractor-catalog-action="save-item"]').click();
  await expect(card.locator("tbody")).toContainText(nextLabel, { timeout: 15_000 });
}

async function deleteCatalogViaUi(
  page: Page,
  catalogType: "role" | "equipment" | "equipment_status",
  code: string
): Promise<void> {
  const card = page.locator(`[data-catalog-type="${catalogType}"]`).first();
  const row = card.locator("tbody tr", { hasText: code }).first();
  const deleteButton = row.locator('[data-contractor-catalog-action="delete-item"]').first();
  await expect(deleteButton).toBeVisible({ timeout: 15_000 });
  page.once("dialog", (dialog) => dialog.accept());
  await deleteButton.click();
  await expect(row).toContainText("غیرفعال", { timeout: 15_000 });
}

async function openCreateSiteLogForm(page: Page): Promise<void> {
  await page.locator('#contractor-panel-execution [data-sl-action="open-form"]').first().click();
  await expect(page.locator("#sl-drawer-contractor-execution .sl-drawer-panel")).toBeVisible({
    timeout: 15_000,
  });
}

async function closeSiteLogForm(page: Page): Promise<void> {
  const closeButton = page.locator('#sl-drawer-contractor-execution [data-sl-action="close-form"]').first();
  if (await closeButton.isVisible().catch(() => false)) {
    await closeButton.click();
  }
}

async function searchContractorSiteLogs(page: Page, query: string): Promise<void> {
  const searchInput = page.locator("#sl-filter-search-contractor-execution");
  await searchInput.fill(query);
  await page.waitForTimeout(700);
}

async function createLegacyDraft(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>,
  context: SiteLogContext
): Promise<{ id: number; logNo: string; legacyRole: string; legacyEquipment: string; legacyStatus: string }> {
  const legacyRole = `Legacy Role ${uniqueCode("LR", 6)}`;
  const legacyEquipment = `Legacy Equip ${uniqueCode("LE", 6)}`;
  const legacyStatus = uniqueCode("legacy_status_", 18).toUpperCase();
  const createBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/site-logs/create`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        log_type: "DAILY",
        project_code: context.projectCode,
        discipline_code: context.disciplineCode,
        organization_id: context.organizationId,
        log_date: new Date().toISOString().slice(0, 10) + "T00:00:00",
        weather: "CLEAR",
        summary: `Legacy draft ${Date.now()}`,
        manpower_rows: [
          {
            role_label: legacyRole,
            claimed_count: 2,
            claimed_hours: 8.0,
            sort_order: 0,
          },
        ],
        equipment_rows: [
          {
            equipment_label: legacyEquipment,
            claimed_status: legacyStatus,
            claimed_hours: 6.0,
            sort_order: 0,
          },
        ],
        activity_rows: [],
      },
    }),
    "site log legacy draft create"
  );

  const data = createBody?.data || {};
  const id = Number(data?.id || 0);
  const logNo = String(data?.log_no || "").trim();
  expect(id).toBeGreaterThan(0);
  expect(logNo).not.toEqual("");
  return { id, logNo, legacyRole, legacyEquipment, legacyStatus };
}

test("e2e smoke: site log catalogs feed dropdowns and refresh after updates", async ({ page, request, baseURL }) => {
  test.setTimeout(180_000);
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await ensureSiteLogContext(request, resolvedBaseUrl, headers);

  const roleCode = uniqueCode("ROLE", 10);
  const equipmentCode = uniqueCode("EQ", 8);
  const statusCode = uniqueCode("STAT", 8);
  const roleLabel = `نقش ${roleCode}`;
  const equipmentLabel = `تجهیز ${equipmentCode}`;
  const statusLabel = `وضعیت ${statusCode}`;
  const updatedRoleLabel = `${roleLabel} به‌روزشده`;
  const summary = `Site log smoke ${Date.now()}`;

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");

  await gotoContractorSettings(page);
  await saveCatalogViaUi(page, "role", roleCode, roleLabel, 10);
  await saveCatalogViaUi(page, "equipment", equipmentCode, equipmentLabel, 20);
  await saveCatalogViaUi(page, "equipment_status", statusCode, statusLabel, 30);

  await gotoContractor(page);
  await openCreateSiteLogForm(page);

  await page.selectOption("#sl-form-project-contractor-execution", context.projectCode);
  await page.selectOption("#sl-form-discipline-contractor-execution", context.disciplineCode);
  await page.selectOption("#sl-form-organization-contractor-execution", String(context.organizationId));
  await page.fill("#sl-form-summary-contractor-execution", summary);

  const roleSelect = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="role_label"]'
  ).first();
  const equipmentSelect = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-field="equipment_label"]'
  ).first();
  const statusSelect = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-field="claimed_status"]'
  ).first();

  await expect(roleSelect.locator(`option[value="${roleLabel}"]`)).toHaveCount(1);
  await expect(equipmentSelect.locator(`option[value="${equipmentLabel}"]`)).toHaveCount(1);
  await expect(statusSelect.locator(`option[value="${statusCode}"]`)).toHaveCount(1);

  await roleSelect.selectOption(roleLabel);
  await equipmentSelect.selectOption(equipmentLabel);
  await statusSelect.selectOption(statusCode);

  await page.locator('#sl-form-wrap-contractor-execution [data-sl-action="save-form"]').click();

  await expect
    .poll(async () => Number(await page.locator("#sl-form-id-contractor-execution").inputValue() || 0), {
      timeout: 15_000,
    })
    .toBeGreaterThan(0);
  const logId = Number(await page.locator("#sl-form-id-contractor-execution").inputValue() || 0);

  const savedLog = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/site-logs/${logId}`, { headers }),
    "site log get after ui save"
  );
  const savedData = savedLog?.data || {};
  expect(String(savedData?.summary || "")).toBe(summary);
  expect(String(savedData?.manpower_rows?.[0]?.role_label || "")).toBe(roleLabel);
  expect(String(savedData?.equipment_rows?.[0]?.equipment_label || "")).toBe(equipmentLabel);
  expect(String(savedData?.equipment_rows?.[0]?.claimed_status || "")).toBe(statusCode);

  await closeSiteLogForm(page);

  await gotoContractorSettings(page);
  await updateCatalogLabelViaUi(page, "role", roleCode, updatedRoleLabel);

  await gotoContractor(page);
  await openCreateSiteLogForm(page);
  const refreshedRoleSelect = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="role_label"]'
  ).first();
  await expect(refreshedRoleSelect.locator(`option[value="${updatedRoleLabel}"]`)).toHaveCount(1);
  await expect(refreshedRoleSelect.locator(`option[value="${roleLabel}"]`)).toHaveCount(0);
  await closeSiteLogForm(page);

  await gotoContractorSettings(page);
  await deleteCatalogViaUi(page, "role", roleCode);

  await gotoContractor(page);
  await openCreateSiteLogForm(page);
  const afterDeleteRoleSelect = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="role_label"]'
  ).first();
  await expect(afterDeleteRoleSelect.locator(`option[value="${updatedRoleLabel}"]`)).toHaveCount(0);
});

test("e2e smoke: legacy free-text site log values stay editable in dropdown form", async ({
  page,
  request,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await ensureSiteLogContext(request, resolvedBaseUrl, headers);
  const legacyDraft = await createLegacyDraft(request, resolvedBaseUrl, headers, context);

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await gotoContractor(page);

  await searchContractorSiteLogs(page, legacyDraft.logNo);
  const row = page.locator("#sl-tbody-contractor-execution tr", { hasText: legacyDraft.logNo }).first();
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.locator('[data-sl-action="open-edit"]').click();
  await expect(page.locator("#sl-drawer-contractor-execution .sl-drawer-panel")).toBeVisible({
    timeout: 15_000,
  });

  const roleSelect = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="role_label"]'
  ).first();
  const equipmentSelect = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-field="equipment_label"]'
  ).first();
  const statusSelect = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-field="claimed_status"]'
  ).first();

  await expect(roleSelect).toHaveValue(legacyDraft.legacyRole);
  await expect(equipmentSelect).toHaveValue(legacyDraft.legacyEquipment);
  await expect(statusSelect).toHaveValue(legacyDraft.legacyStatus);
  await expect(roleSelect.locator("option:checked")).toContainText("مقدار قبلی");
  await expect(equipmentSelect.locator("option:checked")).toContainText("مقدار قبلی");
  await expect(statusSelect.locator("option:checked")).toContainText("مقدار قبلی");

  const updatedSummary = `Legacy summary updated ${Date.now()}`;
  await page.fill("#sl-form-summary-contractor-execution", updatedSummary);
  await page.locator('#sl-form-wrap-contractor-execution [data-sl-action="save-form"]').click();

  const updatedLog = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/site-logs/${legacyDraft.id}`, { headers }),
    "site log get after legacy ui save"
  );
  const updatedData = updatedLog?.data || {};
  expect(String(updatedData?.summary || "")).toBe(updatedSummary);
  expect(String(updatedData?.manpower_rows?.[0]?.role_label || "")).toBe(legacyDraft.legacyRole);
  expect(String(updatedData?.equipment_rows?.[0]?.equipment_label || "")).toBe(legacyDraft.legacyEquipment);
  expect(String(updatedData?.equipment_rows?.[0]?.claimed_status || "")).toBe(legacyDraft.legacyStatus);
});
