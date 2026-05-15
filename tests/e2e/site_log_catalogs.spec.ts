import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type Locator,
  type Page,
} from "@playwright/test";

import {
  apiLoginToken,
  bearerHeaders,
  navigateToView,
  resolveBaseUrl,
  seedAuthToken,
} from "./helpers";

type SiteLogContext = {
  projectCode: string;
  disciplineCode: string;
  organizationId: number;
  organizationName: string;
  contractId: number;
  contractNumber: string;
  contractSubject: string;
  blockId: number;
  blockCode: string;
  blockName: string;
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

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

async function ensureSiteLogContext(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>
): Promise<SiteLogContext> {
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };
  const projectCode = uniqueCode("SLP", 8);
  const disciplineCode = uniqueCode("SD", 5);
  const blockCode = uniqueCode("BLK", 7);
  const blockName = `Workshop Block ${blockCode}`;
  const organizationCode = uniqueCode("SLCO", 10);
  const organizationName = `Site Log Contractor ${organizationCode}`;
  const contractNumber = uniqueCode("CN", 8);
  const contractSubject = `Workshop package ${uniqueCode("PKG", 6)}`;

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

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/blocks/upsert`, {
      headers: jsonHeaders,
      data: {
        project_code: projectCode,
        code: blockCode,
        name_e: blockName,
        name_p: blockName,
        sort_order: 10,
        is_active: true,
      },
    }),
    "settings block upsert (site log e2e)"
  );

  const blocksBody = await expectOkJson(
    await request.get(`${baseUrl}/api/v1/settings/blocks?project_code=${encodeURIComponent(projectCode)}`, {
      headers,
    }),
    "settings blocks list (site log e2e)"
  );
  const blockRow =
    (Array.isArray(blocksBody?.items) ? blocksBody.items : []).find(
      (item: any) => String(item?.code || "").trim().toUpperCase() === blockCode
    ) || null;
  const blockId = Number(blockRow?.id || 0);
  expect(blockId).toBeGreaterThan(0);

  const orgBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/organizations/upsert`, {
      headers: jsonHeaders,
      data: {
        code: organizationCode,
        name: organizationName,
        org_type: "contractor",
        is_active: true,
        contracts: [
          {
            contract_number: contractNumber,
            subject: contractSubject,
            block_id: blockId,
          },
        ],
      },
    }),
    "settings organization upsert (site log e2e)"
  );

  const organizationId = Number(orgBody?.item?.id || orgBody?.id || 0);
  const contracts = Array.isArray(orgBody?.item?.contracts) ? orgBody.item.contracts : [];
  const contractRow = contracts[0] || null;
  const contractId = Number(contractRow?.id || 0);
  expect(organizationId).toBeGreaterThan(0);
  expect(contractId).toBeGreaterThan(0);

  return {
    projectCode,
    disciplineCode,
    organizationId,
    organizationName,
    contractId,
    contractNumber,
    contractSubject,
    blockId,
    blockCode,
    blockName,
  };
}

async function seedQcSources(
  request: APIRequestContext,
  baseUrl: string,
  adminHeaders: Record<string, string>,
  context: SiteLogContext
): Promise<void> {
  const jsonAdminHeaders = { ...adminHeaders, "Content-Type": "application/json" };

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/comm-items/create`, {
      headers: jsonAdminHeaders,
      data: {
        item_type: "TECH",
        project_code: context.projectCode,
        discipline_code: context.disciplineCode,
        organization_id: context.organizationId,
        contractor_org_id: context.organizationId,
        title: `Site log IR ${Date.now()}`,
        status_code: "DRAFT",
        priority: "NORMAL",
        tech: {
          tech_subtype_code: "IR",
        },
      },
    }),
    "tech IR create (site log qc seed)"
  );

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/comm-items/create`, {
      headers: jsonAdminHeaders,
      data: {
        item_type: "NCR",
        project_code: context.projectCode,
        discipline_code: context.disciplineCode,
        organization_id: context.organizationId,
        contractor_org_id: context.organizationId,
        title: `Site log NCR ${Date.now()}`,
        status_code: "ISSUED",
        priority: "NORMAL",
        ncr: {
          kind: "NCR",
          severity: "MAJOR",
          nonconformance_text:
            "Nonconformance details are documented with enough text for the site log QC snapshot.",
          rectification_method: "Repair, inspect, and close after consultant confirmation.",
        },
      },
    }),
    "ncr create (site log qc seed)"
  );
}

async function upsertLegacyCatalogViaApi(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>,
  catalogType: "role" | "work_section" | "equipment" | "equipment_status" | "attachment_type" | "issue_type",
  code: string,
  label: string,
  sortOrder: number,
  itemId?: number
): Promise<number> {
  const body = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/site-log-catalogs/upsert`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        id: itemId || null,
        catalog_type: catalogType,
        code,
        label,
        sort_order: sortOrder,
        is_active: true,
      },
    }),
    `legacy site-log catalog upsert (${catalogType})`
  );
  return Number(body?.item?.id || 0);
}

async function deleteLegacyCatalogViaApi(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>,
  catalogType: "role" | "work_section" | "equipment" | "equipment_status" | "attachment_type" | "issue_type",
  itemId: number
): Promise<void> {
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/site-log-catalogs/delete`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        id: itemId,
        catalog_type: catalogType,
      },
    }),
    "legacy site-log catalog delete"
  );
}

async function gotoContractorSettings(page: Page): Promise<void> {
  await gotoContractor(page);
  const settingsButton = page
    .locator('#view-contractor [data-nav-target="view-contractor-settings"]')
    .first();
  await expect(settingsButton).toBeVisible({ timeout: 20_000 });
  await settingsButton.click();
  await expect(page.locator("#view-contractor-settings")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#contractorSiteLogCatalogsRoot")).toBeVisible({ timeout: 20_000 });
}

async function gotoConsultantActivitySettings(page: Page): Promise<void> {
  await gotoConsultantInspection(page);
  const settingsButton = page
    .locator('#view-consultant [data-nav-target="view-consultant-settings"]')
    .first();
  await expect(settingsButton).toBeVisible({ timeout: 20_000 });
  await settingsButton.click();
  await expect(page.locator("#view-consultant-settings")).toBeVisible({ timeout: 20_000 });
  const activityTab = page.locator('[data-consultant-settings-tab="site-log-activity"]').first();
  await expect(activityTab).toBeVisible({ timeout: 20_000 });
  await activityTab.click();
  await expect(page.locator("#consultant-settings-tab-site-log-activity")).toHaveClass(/active/);
  await expect(page.locator("#consultantSiteLogActivityCatalogRoot")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".consultant-activity-subtab")).toHaveCount(3, { timeout: 20_000 });
  await expect(page.locator('[data-catalog-type="activity"]')).toBeVisible({ timeout: 20_000 });
}

async function gotoContractor(page: Page): Promise<void> {
  await navigateToView(page, "view-contractor", '[data-nav-target="view-contractor"]');
  await expect(page.locator("#view-contractor")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#contractor-panel-execution .site-logs-card")).toBeVisible({ timeout: 20_000 });
}

async function gotoConsultantInspection(page: Page): Promise<void> {
  await navigateToView(page, "view-consultant", '[data-nav-target="view-consultant"]');
  await expect(page.locator("#view-consultant")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#consultant-panel-inspection .site-logs-card")).toBeVisible({
    timeout: 20_000,
  });
}

async function saveCatalogViaUi(
  page: Page,
  catalogType: "role" | "work_section" | "equipment" | "equipment_status" | "attachment_type" | "issue_type",
  code: string,
  label: string,
  sortOrder: number
): Promise<void> {
  await page.locator(`[data-contractor-catalog-action="switch-catalog"][data-catalog-type="${catalogType}"]`).click();
  const panel = page.locator(`.contractor-report-catalog-panel[data-catalog-type="${catalogType}"]`).first();
  await expect(panel).toBeVisible({ timeout: 15_000 });
  await panel.locator('[data-contractor-catalog-action="open-drawer"]').click();
  const drawer = page.locator(`[data-contractor-catalog-drawer] [data-catalog-type="${catalogType}"]`).first();
  await expect(drawer).toBeVisible({ timeout: 15_000 });
  await drawer.locator('[data-catalog-form-field="code"]').fill(code);
  await drawer.locator('[data-catalog-form-field="label"]').fill(label);
  await drawer.locator('[data-catalog-form-field="sort_order"]').fill(String(sortOrder));
  const activeCheckbox = drawer.locator('[data-catalog-form-field="is_active"]');
  if (!(await activeCheckbox.isChecked())) {
    await activeCheckbox.check();
  }
  await drawer.locator('[data-contractor-catalog-action="save-item"]').click();
  await expect(panel.locator("tbody")).toContainText(label, { timeout: 15_000 });
}

async function updateCatalogLabelViaUi(
  page: Page,
  catalogType: "role" | "work_section" | "equipment" | "equipment_status" | "attachment_type" | "issue_type",
  code: string,
  nextLabel: string
): Promise<void> {
  await page.locator(`[data-contractor-catalog-action="switch-catalog"][data-catalog-type="${catalogType}"]`).click();
  const panel = page.locator(`.contractor-report-catalog-panel[data-catalog-type="${catalogType}"]`).first();
  const editButton = panel.locator(
    `[data-contractor-catalog-action="edit-item"][data-item-code="${code}"]`
  ).first();
  await expect(editButton).toBeVisible({ timeout: 15_000 });
  await editButton.click();
  const drawer = page.locator(`[data-contractor-catalog-drawer] [data-catalog-type="${catalogType}"]`).first();
  await expect(drawer).toBeVisible({ timeout: 15_000 });
  await drawer.locator('[data-catalog-form-field="label"]').fill(nextLabel);
  await drawer.locator('[data-contractor-catalog-action="save-item"]').click();
  await expect(panel.locator("tbody")).toContainText(nextLabel, { timeout: 15_000 });
}

async function deleteCatalogViaUi(
  page: Page,
  catalogType: "role" | "work_section" | "equipment" | "equipment_status" | "attachment_type" | "issue_type",
  code: string
): Promise<void> {
  await page.locator(`[data-contractor-catalog-action="switch-catalog"][data-catalog-type="${catalogType}"]`).click();
  const panel = page.locator(`.contractor-report-catalog-panel[data-catalog-type="${catalogType}"]`).first();
  const row = panel.locator("tbody tr", { hasText: code }).first();
  const deleteButton = row.locator('[data-contractor-catalog-action="toggle-item-active"]').first();
  await expect(deleteButton).toBeVisible({ timeout: 15_000 });
  page.once("dialog", (dialog) => dialog.accept());
  await deleteButton.click();
  await expect(
    panel.locator(`[data-contractor-catalog-action="edit-item"][data-item-code="${code}"]`).first()
  ).toHaveAttribute("data-item-is-active", "0", { timeout: 15_000 });
}

async function saveActivityCatalogViaUi(
  page: Page,
  context: SiteLogContext,
  activityCode: string,
  activityTitle: string,
  defaultLocation: string,
  defaultUnit: string,
  sortOrder: number
): Promise<void> {
  const card = page.locator('[data-catalog-type="activity"]').first();
  const root = page.locator("#consultantSiteLogActivityCatalogRoot");
  const waitForCatalogIdle = async () => {
    await expect(root).not.toHaveClass(/is-loading/, { timeout: 15_000 });
    await expect(card).toBeVisible({ timeout: 15_000 });
  };
  await expect(card).toBeVisible({ timeout: 20_000 });

  await card.locator('[data-contractor-catalog-filter="project_code"]').selectOption(context.projectCode);
  await waitForCatalogIdle();
  await card.locator('[data-contractor-catalog-filter="organization_id"]').selectOption(String(context.organizationId));
  await waitForCatalogIdle();
  const filterContract = card.locator('[data-contractor-catalog-filter="organization_contract_id"]');
  await expect(filterContract.locator(`option[value="${context.contractId}"]`)).toHaveCount(1, {
    timeout: 15_000,
  });
  await filterContract.selectOption(String(context.contractId));
  await waitForCatalogIdle();

  await card.locator('[data-contractor-catalog-action="open-activity-drawer"]').click();
  const drawer = page.locator("[data-activity-form-scope]").first();
  await expect(drawer).toBeVisible({ timeout: 15_000 });
  await drawer.locator('[data-activity-form-field="project_code"]').selectOption(context.projectCode);
  await drawer.locator('[data-activity-form-field="organization_id"]').selectOption(String(context.organizationId));
  const formContract = drawer.locator('[data-activity-form-field="organization_contract_id"]');
  await expect(formContract.locator(`option[value="${context.contractId}"]`)).toHaveCount(1, {
    timeout: 15_000,
  });
  await formContract.selectOption(String(context.contractId));
  await drawer.locator('[data-activity-form-field="activity_code"]').fill(activityCode);
  await drawer.locator('[data-activity-form-field="activity_title"]').fill(activityTitle);
  await drawer.locator('[data-activity-form-field="default_location"]').fill(defaultLocation);
  await drawer.locator('[data-activity-form-field="default_unit"]').fill(defaultUnit);
  await drawer.locator('[data-activity-form-field="sort_order"]').fill(String(sortOrder));
  await drawer.locator('[data-contractor-catalog-action="save-activity"]').click();
  await expect(card.locator("tbody")).toContainText(activityTitle, { timeout: 15_000 });
}

async function openCreateSiteLogForm(page: Page): Promise<void> {
  await page.locator('#contractor-panel-execution [data-sl-action="open-form"]').first().click();
  await expect(page.locator("#sl-drawer-contractor-execution .sl-drawer-panel")).toBeVisible({
    timeout: 15_000,
  });
}

async function closeSiteLogForm(page: Page): Promise<void> {
  const closeButton = page.locator(
    '#sl-drawer-contractor-execution [data-sl-action="close-form"]'
  ).first();
  if (await closeButton.isVisible().catch(() => false)) {
    await closeButton.click();
  }
}

async function searchContractorSiteLogs(page: Page, query: string): Promise<void> {
  const searchInput = page.locator("#sl-filter-search-contractor-execution");
  await searchInput.fill(query);
  await page.waitForTimeout(700);
}

async function searchConsultantSiteLogs(page: Page, query: string): Promise<void> {
  const searchInput = page.locator("#sl-filter-search-consultant-inspection");
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
        log_date: `${todayIsoDate()}T00:00:00`,
        weather: "CLEAR",
        current_work_summary: `Legacy draft ${Date.now()}`,
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

async function createSubmittedSiteLog(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>,
  context: SiteLogContext
): Promise<{
  id: number;
  logNo: string;
  roleLabel: string;
  activityTitle: string;
  materialTitle: string;
  currentWorkSummary: string;
}> {
  const roleLabel = `Verify Role ${uniqueCode("VR", 8)}`;
  const activityCode = uniqueCode("CV", 10);
  const activityTitle = `Verify Activity ${activityCode}`;
  const materialTitle = `Verify Material ${uniqueCode("MT", 8)}`;
  const currentWorkSummary = `Submitted for consultant verify ${Date.now()}`;
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
        organization_contract_id: context.contractId,
        log_date: `${todayIsoDate()}T00:00:00`,
        shift: "DAY",
        weather: "CLEAR",
        current_work_summary: currentWorkSummary,
        next_plan_summary: "Consultant will verify manpower and review supporting rows.",
        manpower_rows: [
          {
            role_label: roleLabel,
            claimed_count: 3,
            claimed_hours: 8,
            sort_order: 0,
          },
        ],
        equipment_rows: [],
        activity_rows: [
          {
            activity_code: activityCode,
            activity_title: activityTitle,
            source_system: "MANUAL",
            location: "Block B",
            unit: "m3",
            today_quantity: 2,
            cumulative_quantity: 5,
            activity_status: "DONE",
            sort_order: 0,
          },
        ],
        material_rows: [
          {
            material_code: "MT-VFY",
            title: materialTitle,
            unit: "Ton",
            incoming_quantity: 1,
            consumed_quantity: 1,
            cumulative_quantity: 2,
            sort_order: 0,
          },
        ],
        issue_rows: [],
        attachment_rows: [],
      },
    }),
    "site log submitted seed create"
  );

  const data = createBody?.data || {};
  const id = Number(data?.id || 0);
  const logNo = String(data?.log_no || "").trim();
  expect(id).toBeGreaterThan(0);
  expect(logNo).not.toEqual("");

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/site-logs/${id}/submit`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        note: "Submitted for consultant E2E verification.",
      },
    }),
    "site log submit for consultant e2e"
  );

  return { id, logNo, roleLabel, activityTitle, materialTitle, currentWorkSummary };
}

async function qcCardValues(page: Page): Promise<string> {
  const values = await page.locator("#sl-qc-cards-contractor-execution .sl-qc-card strong").allInnerTexts();
  return values.map((value) => value.trim()).join(",");
}

async function printPopupText(page: Page, printButton: Locator): Promise<string> {
  const popupPromise = page.waitForEvent("popup");
  await printButton.click();
  const popup = await popupPromise;
  let text = "";
  await expect
    .poll(async () => {
      text = await popup.locator("body").innerText().catch(() => "");
      return text.length;
    }, { timeout: 15_000 })
    .toBeGreaterThan(0);
  await popup.close();
  return text;
}

test("e2e smoke: site log catalogs feed dropdowns and refresh after updates", async ({
  page,
  request,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await ensureSiteLogContext(request, resolvedBaseUrl, headers);

  const roleCode = uniqueCode("ROLE", 16);
  const workSectionCode = uniqueCode("WSEC", 16);
  const equipmentCode = uniqueCode("EQ", 16);
  const statusCode = uniqueCode("STAT", 16);
  const roleLabel = `Role ${roleCode}`;
  const workSectionLabel = `Work Section ${workSectionCode}`;
  const equipmentLabel = `Equipment ${equipmentCode}`;
  const statusLabel = `Status ${statusCode}`;
  const updatedRoleLabel = `${roleLabel} Updated`;
  const currentWorkSummary = `Site log smoke current ${Date.now()}`;
  const nextPlanSummary = `Site log smoke next ${Date.now()}`;

  const roleItemId = await upsertLegacyCatalogViaApi(
    request,
    resolvedBaseUrl,
    headers,
    "role",
    roleCode,
    roleLabel,
    10
  );
  const equipmentItemId = await upsertLegacyCatalogViaApi(
    request,
    resolvedBaseUrl,
    headers,
    "equipment",
    equipmentCode,
    equipmentLabel,
    20
  );
  const workSectionItemId = await upsertLegacyCatalogViaApi(
    request,
    resolvedBaseUrl,
    headers,
    "work_section",
    workSectionCode,
    workSectionLabel,
    25
  );
  const statusItemId = await upsertLegacyCatalogViaApi(
    request,
    resolvedBaseUrl,
    headers,
    "equipment_status",
    statusCode,
    statusLabel,
    30
  );
  expect(roleItemId).toBeGreaterThan(0);
  expect(workSectionItemId).toBeGreaterThan(0);
  expect(equipmentItemId).toBeGreaterThan(0);
  expect(statusItemId).toBeGreaterThan(0);

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");

  await gotoContractor(page);
  await openCreateSiteLogForm(page);

  await page.selectOption("#sl-form-project-contractor-execution", context.projectCode);
  await page.selectOption("#sl-form-organization-contractor-execution", String(context.organizationId));
  await page.fill("#sl-form-current-work-contractor-execution", currentWorkSummary);
  await page.fill("#sl-form-next-plan-contractor-execution", nextPlanSummary);

  const roleInput = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="role_label"]'
  ).first();
  const equipmentInput = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-field="equipment_label"]'
  ).first();
  const workSectionInput = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="work_section_label"]'
  ).first();
  const statusInput = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-target-field="claimed_status"]'
  ).first();
  const statusStoredInput = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-field="claimed_status"]'
  ).first();

  await expect(roleInput).toHaveAttribute("data-sl-typeahead", "catalog");
  await expect(workSectionInput).toHaveAttribute("data-sl-typeahead", "catalog");
  await expect(equipmentInput).toHaveAttribute("data-sl-typeahead", "catalog");
  await expect(statusInput).toHaveAttribute("data-sl-typeahead", "catalog");
  await expect(
    page.locator(`#sl-form-manpower-body-contractor-execution datalist option[value="${roleLabel}"]`)
  ).toHaveCount(1);
  await expect(
    page.locator(`#sl-form-manpower-body-contractor-execution datalist option[value="${workSectionLabel}"]`)
  ).toHaveCount(1);
  await expect(
    page.locator(`#sl-form-equipment-body-contractor-execution datalist option[value="${equipmentLabel}"]`)
  ).toHaveCount(1);

  await roleInput.fill(roleLabel);
  await workSectionInput.fill(workSectionLabel);
  await equipmentInput.fill(equipmentLabel);
  await statusInput.fill(statusCode);
  await expect(statusStoredInput).toHaveValue(statusCode);

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
  expect(String(savedData?.current_work_summary || "")).toBe(currentWorkSummary);
  expect(String(savedData?.next_plan_summary || "")).toBe(nextPlanSummary);
  expect(String(savedData?.manpower_rows?.[0]?.role_label || "")).toBe(roleLabel);
  expect(String(savedData?.manpower_rows?.[0]?.work_section_label || "")).toBe(workSectionLabel);
  expect(String(savedData?.equipment_rows?.[0]?.equipment_label || "")).toBe(equipmentLabel);
  expect(String(savedData?.equipment_rows?.[0]?.claimed_status || "")).toBe(statusCode);

  await closeSiteLogForm(page);

  await upsertLegacyCatalogViaApi(
    request,
    resolvedBaseUrl,
    headers,
    "role",
    roleCode,
    updatedRoleLabel,
    10,
    roleItemId
  );

  await page.reload();
  await gotoContractor(page);
  await openCreateSiteLogForm(page);
  const refreshedRoleInput = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="role_label"]'
  ).first();
  await expect(refreshedRoleInput).toHaveAttribute("data-sl-typeahead", "catalog");
  await expect(
    page.locator(`#sl-form-manpower-body-contractor-execution datalist option[value="${updatedRoleLabel}"]`)
  ).toHaveCount(1);
  await expect(
    page.locator(`#sl-form-manpower-body-contractor-execution datalist option[value="${roleLabel}"]`)
  ).toHaveCount(0);
  await closeSiteLogForm(page);

  await deleteLegacyCatalogViaApi(request, resolvedBaseUrl, headers, "role", roleItemId);

  await page.reload();
  await gotoContractor(page);
  await openCreateSiteLogForm(page);
  const afterDeleteRoleInput = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="role_label"]'
  ).first();
  await expect(afterDeleteRoleInput).toHaveAttribute("data-sl-typeahead", "catalog");
  await expect(
    page.locator(`#sl-form-manpower-body-contractor-execution datalist option[value="${updatedRoleLabel}"]`)
  ).toHaveCount(0);
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
  await row
    .locator('[data-sl-action="open-edit"]')
    .evaluate((element) => (element as HTMLElement).click());
  await expect(page.locator("#sl-drawer-contractor-execution .sl-drawer-panel")).toBeVisible({
    timeout: 15_000,
  });

  const roleInput = page.locator(
    '#sl-form-manpower-body-contractor-execution [data-sl-field="role_label"]'
  ).first();
  const equipmentInput = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-field="equipment_label"]'
  ).first();
  const statusInput = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-target-field="claimed_status"]'
  ).first();
  const statusStoredInput = page.locator(
    '#sl-form-equipment-body-contractor-execution [data-sl-field="claimed_status"]'
  ).first();

  await expect(roleInput).toHaveValue(legacyDraft.legacyRole);
  await expect(equipmentInput).toHaveValue(legacyDraft.legacyEquipment);
  await expect(statusInput).toHaveValue(legacyDraft.legacyStatus);
  await expect(statusStoredInput).toHaveValue(legacyDraft.legacyStatus);

  const updatedCurrentWork = `Legacy current work updated ${Date.now()}`;
  await page.fill("#sl-form-current-work-contractor-execution", updatedCurrentWork);
  await page.locator('#sl-form-wrap-contractor-execution [data-sl-action="save-form"]').click();
  await expect
    .poll(async () => {
      const updatedLog = await expectOkJson(
        await request.get(`${resolvedBaseUrl}/api/v1/site-logs/${legacyDraft.id}`, { headers }),
        "site log get after legacy ui save"
      );
      return String(updatedLog?.data?.current_work_summary || "");
    })
    .toBe(updatedCurrentWork);

  const updatedLog = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/site-logs/${legacyDraft.id}`, { headers }),
    "site log get after legacy ui save final"
  );
  const updatedData = updatedLog?.data || {};
  expect(String(updatedData?.manpower_rows?.[0]?.role_label || "")).toBe(legacyDraft.legacyRole);
  expect(String(updatedData?.equipment_rows?.[0]?.equipment_label || "")).toBe(legacyDraft.legacyEquipment);
  expect(String(updatedData?.equipment_rows?.[0]?.claimed_status || "")).toBe(legacyDraft.legacyStatus);
});

test("e2e: extended site log report flow covers contract activity catalog qc and attachments", async ({
  page,
  request,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await ensureSiteLogContext(request, resolvedBaseUrl, headers);
  await seedQcSources(request, resolvedBaseUrl, headers, context);

  const activityCode = uniqueCode("ACT", 16);
  const activityTitle = `Activity ${activityCode}`;
  const defaultLocation = "Block B";
  const defaultUnit = "Ton";
  const currentWorkSummary = `Current work ${Date.now()}`;
  const nextPlanSummary = `Next plan ${Date.now()}`;
  const qcNote = `QC note ${Date.now()}`;
  const materialTitle = "Rebar A3 Size 20";
  const issueDescription = "Delay in slab formwork delivery";
  const attachmentTypeCode = uniqueCode("AT", 12);
  const attachmentTypeLabel = `Attachment ${attachmentTypeCode}`;
  const attachmentTitle = "IR Photo";
  const attachmentReference = `PH-${uniqueCode("REF", 12)}`;
  const attachmentFileName = `${attachmentReference}.pdf`;
  const deletedAttachmentFileName = `${attachmentReference}-delete.txt`;

  await upsertLegacyCatalogViaApi(
    request,
    resolvedBaseUrl,
    headers,
    "attachment_type",
    attachmentTypeCode,
    attachmentTypeLabel,
    10
  );

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");

  await gotoConsultantActivitySettings(page);
  await saveActivityCatalogViaUi(
    page,
    context,
    activityCode,
    activityTitle,
    defaultLocation,
    defaultUnit,
    10
  );

  await gotoContractor(page);
  await openCreateSiteLogForm(page);

  await page.selectOption("#sl-form-project-contractor-execution", context.projectCode);
  await page.selectOption("#sl-form-organization-contractor-execution", String(context.organizationId));
  const contractSelect = page.locator("#sl-form-contract-subject-contractor-execution");
  await expect(contractSelect.locator(`option[value="${context.contractId}"]`)).toHaveCount(1, {
    timeout: 15_000,
  });
  await contractSelect.selectOption(String(context.contractId));
  await expect(page.locator("#sl-form-contract-number-contractor-execution")).toHaveValue(
    context.contractNumber
  );
  await expect(page.locator("#sl-form-contract-block-contractor-execution")).toHaveValue(
    context.blockName
  );

  await page.selectOption("#sl-form-shift-contractor-execution", "DAY");
  await page.selectOption("#sl-form-weather-contractor-execution", "CLEAR");
  await page.fill("#sl-form-current-work-contractor-execution", currentWorkSummary);
  await page.fill("#sl-form-next-plan-contractor-execution", nextPlanSummary);

  await expect.poll(() => qcCardValues(page), { timeout: 20_000 }).toBe("0,1,0,1");
  await page.fill("#sl-form-qc-open-punch-contractor-execution", "3");
  await expect.poll(() => qcCardValues(page), { timeout: 15_000 }).toBe("0,1,3,1");
  await page.fill("#sl-form-qc-note-contractor-execution", qcNote);

  const activityPicker = page.locator("#sl-activity-picker-contractor-execution");
  const activityPickerList = page.locator("#sl-activity-picker-list-contractor-execution");
  await expect
    .poll(
      async () =>
        await activityPickerList.locator("option").evaluateAll((options) =>
          options.map((option) => (option as HTMLOptionElement).value).join(" | ")
        ),
      { timeout: 20_000 }
    )
    .toContain(activityCode);
  await activityPicker.fill(activityCode);
  await page.locator('#sl-form-wrap-contractor-execution [data-sl-action="add-activity-option"]').click();

  const activityRows = page.locator("#sl-form-activity-body-contractor-execution tr[data-sl-row-index]");
  await expect(activityRows).toHaveCount(2);
  const catalogActivityRow = activityRows.nth(1);
  await expect(catalogActivityRow.locator('[data-sl-field="activity_code"]')).toHaveValue(activityCode);
  await expect(catalogActivityRow.locator('[data-sl-field="activity_title"]')).toHaveValue(activityTitle);
  await expect(catalogActivityRow.locator('[data-sl-field="location"]')).toHaveValue(defaultLocation);
  await expect(catalogActivityRow.locator('[data-sl-field="unit"]')).toHaveValue(defaultUnit);
  await catalogActivityRow.locator('[data-sl-field="personnel_count"]').fill("12");
  await catalogActivityRow.locator('[data-sl-field="today_quantity"]').fill("4.8");
  await catalogActivityRow.locator('[data-sl-field="cumulative_quantity"]').fill("18.2");
  await catalogActivityRow.locator('[data-sl-field="activity_status"]').fill("IN_PROGRESS");
  await catalogActivityRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await catalogActivityRow.locator('[data-sl-action="toggle-row-detail"]').click();
  await page
    .locator('#sl-form-activity-body-contractor-execution tr[data-sl-row-detail-for="1"] [data-sl-field="note"]')
    .fill("Catalog seeded row");

  const materialRow = page.locator("#sl-form-material-body-contractor-execution tr[data-sl-row-index]").first();
  await materialRow.locator('[data-sl-field="material_code"]').fill("MT-22");
  await materialRow.locator('[data-sl-field="title"]').fill(materialTitle);
  await materialRow.locator('[data-sl-field="unit"]').fill("Ton");
  await materialRow.locator('[data-sl-field="incoming_quantity"]').fill("6");
  await materialRow.locator('[data-sl-field="consumed_quantity"]').fill("4.8");
  await materialRow.locator('[data-sl-field="cumulative_quantity"]').fill("18.2");
  await materialRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await materialRow.locator('[data-sl-action="toggle-row-detail"]').click();
  await page
    .locator('#sl-form-material-body-contractor-execution tr[data-sl-row-detail-for="0"] [data-sl-field="note"]')
    .fill("Warehouse B delivery");

  const issueRow = page.locator("#sl-form-issue-body-contractor-execution tr[data-sl-row-index]").first();
  await issueRow.locator('[data-sl-target-field="issue_type"]').fill("MATERIAL");
  await expect(issueRow.locator('[data-sl-field="issue_type"]')).toHaveValue("MATERIAL");
  await issueRow.locator('[data-sl-field="description"]').fill(issueDescription);
  await issueRow.locator('[data-sl-field="responsible_party"]').fill("Contractor");
  await issueRow.locator('[data-sl-field="due_date"]').fill(todayIsoDate());
  await issueRow.locator('[data-sl-field="status"]').fill("OPEN");
  await issueRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await issueRow.locator('[data-sl-action="toggle-row-detail"]').click();
  await page
    .locator('#sl-form-issue-body-contractor-execution tr[data-sl-row-detail-for="0"] [data-sl-field="note"]')
    .fill("Follow-up with procurement");

  await page
    .locator('#sl-section-report_attachment-contractor-execution [data-sl-action="toggle-section"]')
    .click();
  const attachmentRow = page.locator("#sl-form-report_attachment-body-contractor-execution tr[data-sl-row-index]").first();
  await attachmentRow.locator('[data-sl-target-field="attachment_type"]').fill(attachmentTypeCode);
  await expect(attachmentRow.locator('[data-sl-field="attachment_type"]')).toHaveValue(attachmentTypeCode);
  await attachmentRow.locator('[data-sl-field="title"]').fill(attachmentTitle);
  await attachmentRow.locator('[data-sl-field="reference_no"]').fill(attachmentReference);
  await attachmentRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await attachmentRow.locator('[data-sl-action="toggle-row-detail"]').click();
  await page
    .locator('#sl-form-report_attachment-body-contractor-execution tr[data-sl-row-detail-for="0"] [data-sl-field="note"]')
    .fill("Captured during QC inspection");

  await page.locator('#sl-form-wrap-contractor-execution [data-sl-action="save-form"]').click();
  await expect
    .poll(async () => Number(await page.locator("#sl-form-id-contractor-execution").inputValue() || 0), {
      timeout: 20_000,
    })
    .toBeGreaterThan(0);
  const logId = Number(await page.locator("#sl-form-id-contractor-execution").inputValue() || 0);

  await attachmentRow.locator(`input[data-sl-report-attachment-file="0"]`).setInputFiles({
    name: attachmentFileName,
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"),
  });
  await attachmentRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await attachmentRow.locator('[data-sl-action="upload-report-attachment-row"]').click();
  await expect(attachmentRow.locator(".sl-row-file-status.has-files")).toContainText(/1|۱/, { timeout: 20_000 });
  await attachmentRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await expect(attachmentRow.locator(".sl-row-file-item", { hasText: attachmentFileName })).toBeVisible({
    timeout: 20_000,
  });
  const firstFileItem = attachmentRow.locator(".sl-row-file-item", { hasText: attachmentFileName });
  await expect(firstFileItem.locator("a", { hasText: "مشاهده" })).toHaveAttribute("href", /\/preview$/);
  await expect(firstFileItem.locator("a", { hasText: "دانلود" })).toHaveAttribute("href", /\/download$/);
  await expect(firstFileItem.locator('[data-sl-action="delete-attachment"]')).toBeVisible();

  await attachmentRow.locator(`input[data-sl-report-attachment-file="0"]`).setInputFiles({
    name: deletedAttachmentFileName,
    mimeType: "text/plain",
    buffer: Buffer.from(`delete me ${attachmentReference}`),
  });
  await attachmentRow.locator('[data-sl-action="upload-report-attachment-row"]').click();
  await expect(attachmentRow.locator(".sl-row-file-status.has-files")).toContainText(/2|۲/, { timeout: 20_000 });
  await attachmentRow.locator('[data-sl-action="toggle-row-menu"]').click();
  const deletedFileItem = attachmentRow.locator(".sl-row-file-item", { hasText: deletedAttachmentFileName });
  await expect(deletedFileItem).toBeVisible({ timeout: 20_000 });
  await deletedFileItem.locator('[data-sl-action="delete-attachment"]').click();
  await expect(deletedFileItem).toHaveCount(0, { timeout: 20_000 });
  await attachmentRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await expect(firstFileItem).toBeVisible();

  const savedLog = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/site-logs/${logId}`, { headers }),
    "site log get after extended ui save"
  );
  const savedData = savedLog?.data || {};
  expect(Number(savedData?.organization_contract_id || 0)).toBe(context.contractId);
  expect(String(savedData?.contract_number || "")).toBe(context.contractNumber);
  expect(String(savedData?.contract_subject || "")).toBe(context.contractSubject);
  expect(String(savedData?.contract_block || "")).toBe(context.blockName);
  expect(String(savedData?.shift || "")).toBe("DAY");
  expect(String(savedData?.current_work_summary || "")).toBe(currentWorkSummary);
  expect(String(savedData?.next_plan_summary || "")).toBe(nextPlanSummary);
  expect(Number(savedData?.qc_test_count || 0)).toBe(0);
  expect(Number(savedData?.qc_inspection_count || 0)).toBeGreaterThanOrEqual(1);
  expect(Number(savedData?.qc_open_ncr_count || 0)).toBeGreaterThanOrEqual(1);
  expect(Number(savedData?.qc_open_punch_count || 0)).toBe(3);
  expect(String(savedData?.qc_summary_note || "")).toBe(qcNote);
  expect(String(savedData?.activity_rows?.[0]?.activity_code || "")).toBe(activityCode);
  expect(String(savedData?.activity_rows?.[0]?.source_system || "")).toBe("CATALOG");
  expect(String(savedData?.activity_rows?.[0]?.activity_title || "")).toBe(activityTitle);
  expect(Number(savedData?.activity_rows?.[0]?.personnel_count || 0)).toBe(12);
  expect(String(savedData?.material_rows?.[0]?.title || "")).toBe(materialTitle);
  expect(String(savedData?.issue_rows?.[0]?.description || "")).toBe(issueDescription);
  expect(String(savedData?.issue_rows?.[0]?.issue_type || "")).toBe("MATERIAL");
  expect(String(savedData?.attachment_rows?.[0]?.title || "")).toBe(attachmentTitle);
  expect(String(savedData?.attachment_rows?.[0]?.attachment_type || "")).toBe(attachmentTypeCode);
  expect(String(savedData?.attachment_rows?.[0]?.attachment_files?.[0]?.file_name || "")).toBe(attachmentFileName);
  const logNo = String(savedData?.log_no || "").trim();
  expect(logNo).not.toEqual("");

  await closeSiteLogForm(page);
  await searchContractorSiteLogs(page, logNo);
  const savedRow = page.locator("#sl-tbody-contractor-execution tr", { hasText: logNo }).first();
  await expect(savedRow).toBeVisible({ timeout: 20_000 });
  await savedRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await savedRow.locator('[data-sl-action="open-detail"]').click();

  const detailWrap = page.locator("#sl-detail-wrap-contractor-execution");
  await expect(detailWrap).toBeVisible({ timeout: 15_000 });
  await expect(detailWrap).toContainText(context.contractSubject);
  await expect(detailWrap).toContainText(activityTitle);
  await expect(detailWrap).toContainText(materialTitle);
  await expect(detailWrap).toContainText(issueDescription);
  await expect(detailWrap).toContainText(attachmentTitle);
  await expect(detailWrap).toContainText(qcNote);
  const detailFileItem = detailWrap.locator(".sl-report-file-item", { hasText: attachmentFileName }).first();
  await expect(detailFileItem.locator(".sl-report-file-link")).toHaveAttribute("href", /\/preview$/);
  await expect(detailFileItem.locator(".sl-report-file-action")).toHaveAttribute("href", /\/download$/);
  await detailFileItem.locator(".sl-report-file-link").click();
  const previewModal = page.locator("#slPreviewModal");
  await expect(previewModal).toBeVisible({ timeout: 15_000 });
  await expect(previewModal.locator("#slPreviewTitle")).toContainText(attachmentFileName);
  await expect(previewModal.locator(".sl-preview-frame")).toBeVisible();
  await previewModal.locator("[data-sl-preview-close]").last().click();
  await expect(previewModal).toBeHidden();

  await expect(detailWrap.locator('[data-sl-action="print-detail-summary"]')).toHaveCount(0);
  const pdfDownloadPromise = page.waitForEvent("download");
  await detailWrap.locator('[data-sl-action="download-detail-pdf"]').click();
  const pdfDownload = await pdfDownloadPromise;
  expect(pdfDownload.suggestedFilename()).toMatch(/\.pdf$/i);

  const fullPrintText = await printPopupText(
    page,
    detailWrap.locator('[data-sl-action="print-detail-full"]')
  );
  expect(fullPrintText).toContain(currentWorkSummary);
  expect(fullPrintText).toContain(activityTitle);
  expect(fullPrintText).toContain(materialTitle);
  expect(fullPrintText).toContain(issueDescription);
  expect(fullPrintText).not.toContain(attachmentTitle);
  expect(fullPrintText).toContain(qcNote);
});

test("e2e: consultant inspection verifies submitted site log detail rows", async ({
  page,
  request,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await ensureSiteLogContext(request, resolvedBaseUrl, headers);
  const submitted = await createSubmittedSiteLog(request, resolvedBaseUrl, headers, context);
  const verifyNote = `Consultant adjusted manpower ${Date.now()}`;

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await gotoConsultantInspection(page);

  await searchConsultantSiteLogs(page, submitted.logNo);
  const submittedRow = page.locator("#sl-tbody-consultant-inspection tr", { hasText: submitted.logNo }).first();
  await expect(submittedRow).toBeVisible({ timeout: 20_000 });
  await submittedRow
    .locator('[data-sl-action="open-verify"]')
    .evaluate((element) => (element as HTMLElement).click());

  await expect(page.locator("#sl-drawer-consultant-inspection .sl-drawer-panel")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator("#sl-form-status-consultant-inspection")).toHaveValue("SUBMITTED");
  await expect(
    page.locator('#sl-form-manpower-body-consultant-inspection [data-sl-field="role_label"]').first()
  ).toHaveValue(submitted.roleLabel);

  const manpowerRow = page.locator("#sl-form-manpower-body-consultant-inspection tr[data-sl-row-index]").first();
  await manpowerRow.locator('[data-sl-field="verified_count"]').fill("2");
  await manpowerRow.locator('[data-sl-field="verified_hours"]').fill("7.5");
  await manpowerRow.locator('[data-sl-action="toggle-row-menu"]').click();
  await manpowerRow.locator('[data-sl-action="toggle-row-detail"]').click();
  await page
    .locator('#sl-form-manpower-body-consultant-inspection tr[data-sl-row-detail-for="0"] [data-sl-field="note"]')
    .fill(verifyNote);
  await page.locator("#sl-comment-input-consultant-inspection").fill("Verified by consultant E2E.");
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("تایید");
    await dialog.accept();
  });
  await page.locator('#sl-form-wrap-consultant-inspection [data-sl-action="verify-form"]').click();

  await expect
    .poll(async () => {
      const verifiedLog = await expectOkJson(
        await request.get(`${resolvedBaseUrl}/api/v1/site-logs/${submitted.id}`, { headers }),
        "site log get while waiting for consultant verify"
      );
      return String(verifiedLog?.data?.status_code || "");
    }, { timeout: 20_000 })
    .toBe("VERIFIED");

  const verifiedLog = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/site-logs/${submitted.id}`, { headers }),
    "site log get after consultant verify"
  );
  const verifiedData = verifiedLog?.data || {};
  expect(Number(verifiedData?.manpower_rows?.[0]?.verified_count || 0)).toBe(2);
  expect(Number(verifiedData?.manpower_rows?.[0]?.verified_hours || 0)).toBe(7.5);
  expect(String(verifiedData?.manpower_rows?.[0]?.note || "")).toBe(verifyNote);

  await page.locator('#sl-drawer-consultant-inspection [data-sl-action="close-form"]').first().click();
  await page.selectOption("#sl-filter-status-consultant-inspection", "VERIFIED");
  await searchConsultantSiteLogs(page, submitted.logNo);
  const verifiedRow = page.locator("#sl-tbody-consultant-inspection tr", { hasText: submitted.logNo }).first();
  await expect(verifiedRow).toBeVisible({ timeout: 20_000 });
  await verifiedRow
    .locator('[data-sl-action="open-detail"]')
    .evaluate((element) => (element as HTMLElement).click());

  const detailWrap = page.locator("#sl-detail-wrap-consultant-inspection");
  await expect(detailWrap).toBeVisible({ timeout: 15_000 });
  await expect(detailWrap).toContainText(submitted.currentWorkSummary);
  await expect(detailWrap).toContainText(submitted.activityTitle);
  await expect(detailWrap).toContainText(submitted.materialTitle);
  await expect(detailWrap).toContainText(verifyNote);
});
