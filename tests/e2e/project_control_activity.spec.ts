import { expect, test, type APIRequestContext, type APIResponse, type Page } from "@playwright/test";

import {
  apiLoginToken,
  bearerHeaders,
  navigateToView,
  resolveBaseUrl,
  seedAuthToken,
} from "./helpers";

type ProjectControlContext = {
  projectCode: string;
  disciplineCode: string;
  organizationId: number;
  activityCode: string;
  mappingId: number;
  templateCode: string;
  logId: number;
  logNo: string;
};

function uniqueCode(prefix: string, size = 10): string {
  const stamp = Date.now().toString(36).toUpperCase();
  const random = Math.random().toString(36).replace(/[^a-z0-9]/gi, "").toUpperCase();
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

async function expectOkText(response: APIResponse, label: string): Promise<string> {
  const bodyText = await response.text();
  expect(response.ok(), `${label} failed. status=${response.status()} body=${bodyText}`).toBeTruthy();
  return bodyText;
}

async function seedProjectControlActivity(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>
): Promise<ProjectControlContext> {
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };
  const projectCode = uniqueCode("PCP", 10);
  const disciplineCode = uniqueCode("PCD", 8);
  const organizationCode = uniqueCode("PCO", 10);
  const activityCode = uniqueCode("PCA", 10);
  const templateCode = uniqueCode("PMS", 10);

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
    "project control project upsert"
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
    "project control discipline upsert"
  );

  const orgBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/organizations/upsert`, {
      headers: jsonHeaders,
      data: {
        code: organizationCode,
        name: `Project Control Contractor ${organizationCode}`,
        org_type: "contractor",
        is_active: true,
      },
    }),
    "project control organization upsert"
  );
  const organizationId = Number(orgBody?.item?.id || orgBody?.id || 0);
  expect(organizationId).toBeGreaterThan(0);

  const activityBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/site-log-activity-catalog/upsert`, {
      headers: jsonHeaders,
      data: {
        project_code: projectCode,
        organization_id: organizationId,
        activity_code: activityCode,
        activity_title: "E2E project control activity",
        default_location: "Deck A",
        default_unit: "m3",
        sort_order: 10,
        is_active: true,
      },
    }),
    "project control activity upsert"
  );
  const activityId = Number(activityBody?.item?.id || 0);
  expect(activityId).toBeGreaterThan(0);

  const templateBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/site-log-pms/templates/upsert`, {
      headers: jsonHeaders,
      data: {
        code: templateCode,
        title: "E2E PMS",
        sort_order: 10,
        is_active: true,
        steps: [
          { step_code: "WORK", step_title: "Work Done", weight_pct: 70, sort_order: 10, is_active: true },
          { step_code: "QC", step_title: "QC Passed", weight_pct: 30, sort_order: 20, is_active: true },
        ],
      },
    }),
    "project control pms template upsert"
  );
  const templateId = Number(templateBody?.item?.id || 0);
  expect(templateId).toBeGreaterThan(0);

  const mappingBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/site-log-pms/mappings/apply`, {
      headers: jsonHeaders,
      data: { activity_ids: [activityId], template_id: templateId, overwrite: false },
    }),
    "project control pms mapping apply"
  );
  const mappingId = Number((mappingBody?.items || [])[0]?.pms_mapping_id || 0);
  expect(mappingId).toBeGreaterThan(0);

  const createBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/site-logs/create`, {
      headers: jsonHeaders,
      data: {
        log_type: "DAILY",
        project_code: projectCode,
        discipline_code: disciplineCode,
        organization_id: organizationId,
        log_date: `${new Date().toISOString().slice(0, 10)}T00:00:00`,
        weather: "CLEAR",
        current_work_summary: "E2E contractor submitted activity for project control.",
        activity_rows: [
          {
            activity_code: activityCode,
            activity_title: "E2E project control activity",
            source_system: "CATALOG",
            pms_mapping_id: mappingId,
            pms_step_code: "WORK",
            location: "Deck A",
            unit: "m3",
            today_quantity: 12.5,
            cumulative_quantity: 44,
            claimed_progress_pct: 42,
            sort_order: 0,
          },
        ],
      },
    }),
    "project control site log create"
  );
  const logId = Number(createBody?.data?.id || 0);
  const logNo = String(createBody?.data?.log_no || "").trim();
  expect(logId).toBeGreaterThan(0);
  expect(logNo).not.toEqual("");

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/site-logs/${logId}/submit`, {
      headers: jsonHeaders,
      data: { note: "E2E submit" },
    }),
    "project control site log submit"
  );

  return { projectCode, disciplineCode, organizationId, activityCode, mappingId, templateCode, logId, logNo };
}

async function openProjectControlActivity(page: Page, context: ProjectControlContext): Promise<void> {
  await navigateToView(page, "view-consultant", '[data-nav-target="view-consultant"]');
  await expect(page.locator("#view-consultant")).toBeVisible({ timeout: 20_000 });
  await page.locator(".consultant-tab-btn[data-consultant-tab='control']").click();
  await expect(page.locator("#consultant-panel-control")).toHaveClass(/active/, { timeout: 20_000 });
  const root = page.locator(".project-control-root[data-module='consultant'][data-tab='control']");
  await expect(root).toBeVisible({ timeout: 20_000 });
  await expect(root.locator("[data-pc-section='activity']")).toBeVisible({ timeout: 20_000 });
  await root.locator("[data-pc-section='activity']").click();
  await root.locator("[data-pc-filter='project']").fill(context.projectCode);
  await root.locator("[data-pc-filter='discipline']").fill(context.disciplineCode);
  await root.locator("[data-pc-filter='activity_code']").fill(context.activityCode);
  await root.locator("[data-pc-action='run']").first().click();
  await expect(root.locator("[data-pc-table]")).toContainText(context.activityCode, { timeout: 20_000 });
  await expect(root.locator("[data-pc-table]")).toContainText(context.logNo);
}

test("project control activity measurements can be edited, verified, drilled down, and exported", async ({
  page,
  request,
  baseURL,
}) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await seedProjectControlActivity(request, resolvedBaseUrl, headers);

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await openProjectControlActivity(page, context);

  const root = page.locator(".project-control-root[data-module='consultant'][data-tab='control']");
  const table = root.locator("[data-pc-table]");

  const supervisorToday = table.locator("[data-pcm-field='supervisor_today_quantity']").first();
  const supervisorPatch = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/project-control/activity-measurements/") &&
        response.request().method() === "PATCH" &&
        String(response.request().postData() || "").includes("supervisor_today_quantity"),
      { timeout: 20_000 }
    ),
    supervisorToday.fill("11"),
  ]);
  expect(supervisorPatch[0].ok(), await supervisorPatch[0].text()).toBeTruthy();
  await expect(table).toContainText("اندازه‌گیری‌شده", { timeout: 20_000 });

  const verifiedProgress = table.locator("[data-pcm-field='verified_progress_pct']").first();
  const verifiedPatch = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/project-control/activity-measurements/") &&
        response.request().method() === "PATCH" &&
        String(response.request().postData() || "").includes("verified_progress_pct"),
      { timeout: 20_000 }
    ),
    verifiedProgress.fill("40"),
  ]);
  expect(verifiedPatch[0].ok(), await verifiedPatch[0].text()).toBeTruthy();

  const qcSelect = table.locator("[data-pcm-field='qc_status']").first();
  const qcPatch = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/project-control/activity-measurements/") &&
        response.request().method() === "PATCH" &&
        String(response.request().postData() || "").includes("qc_status"),
      { timeout: 20_000 }
    ),
    qcSelect.selectOption("PASSED"),
  ]);
  expect(qcPatch[0].ok(), await qcPatch[0].text()).toBeTruthy();
  await expect(qcSelect).toHaveValue("PASSED");

  const transition = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/project-control/activity-measurements/") &&
        response.url().includes("/transition") &&
        response.request().method() === "POST",
      { timeout: 20_000 }
    ),
    table.locator("[data-pc-action='finalize']").first().click(),
  ]);
  expect(transition[0].ok(), await transition[0].text()).toBeTruthy();
  await expect(table).toContainText("نهایی‌شده", { timeout: 20_000 });
  await expect(table.locator("[data-pc-action='finalize']").first()).toBeDisabled();
  await expect(table.locator("[data-pcm-field='supervisor_today_quantity']").first()).toBeDisabled();

  await table.locator("[data-pc-action='source']").first().click();
  await expect(root.locator("[data-pc-drawer]")).toContainText("گزارش مبدا", { timeout: 20_000 });
  await expect(root.locator("[data-pc-drawer]")).toContainText(context.logNo);

  const csvText = await expectOkText(
    await request.get(
      `${resolvedBaseUrl}/api/v1/project-control/activity-measurements.csv?project_code=${encodeURIComponent(
        context.projectCode
      )}&activity_code=${encodeURIComponent(context.activityCode)}&shape=long`,
      { headers }
    ),
    "project control csv long request"
  );
  expect(csvText).toContain("step_code");
  expect(csvText).toContain(context.activityCode);
  expect(csvText).toContain("WORK");
  expect(csvText).toContain("QC");
});
