import { expect, test, type APIRequestContext, type APIResponse, type Page } from "@playwright/test";

import {
  apiLoginToken,
  bearerHeaders,
  navigateToView,
  resolveBaseUrl,
  seedAuthToken,
} from "./helpers";

type ReportsContext = {
  projectCode: string;
  disciplineCode: string;
  organizationId: number;
  organizationName: string;
};

function uniqueCode(prefix: string, size = 8): string {
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

async function seedReportsContext(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>
): Promise<ReportsContext> {
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };
  const projectCode = uniqueCode("RPTP", 10);
  const disciplineCode = uniqueCode("RPD", 8);
  const organizationCode = uniqueCode("RPTO", 10);
  const organizationName = `Reports Contractor ${organizationCode}`;

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
    "reports project upsert"
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
    "reports discipline upsert"
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
    "reports organization upsert"
  );
  const organizationId = Number(orgBody?.item?.id || orgBody?.id || 0);
  expect(organizationId).toBeGreaterThan(0);

  return { projectCode, disciplineCode, organizationId, organizationName };
}

async function createSiteLogForReport(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>,
  context: ReportsContext,
  statusCode: "DRAFT" | "SUBMITTED",
  logType: "DAILY" | "WEEKLY",
  claimedCount: number,
  progressPct: number
): Promise<{ id: number; logNo: string }> {
  const body = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/site-logs/create`, {
      headers: { ...headers, "Content-Type": "application/json" },
      data: {
        log_type: logType,
        project_code: context.projectCode,
        discipline_code: context.disciplineCode,
        organization_id: context.organizationId,
        log_date: `${new Date().toISOString().slice(0, 10)}T00:00:00`,
        status_code: statusCode,
        current_work_summary: `Reports center ${statusCode}`,
        next_plan_summary: "Continue planned work",
        manpower_rows: [
          {
            role_code: "WORKER",
            role_label: "Worker",
            claimed_count: claimedCount,
            claimed_hours: claimedCount * 8,
            sort_order: 0,
          },
        ],
        equipment_rows: [
          {
            equipment_code: "CRN",
            equipment_label: "Crane",
            claimed_count: 1,
            claimed_status: "ACTIVE",
            claimed_hours: 6,
            sort_order: 0,
          },
        ],
        activity_rows: [
          {
            activity_code: `ACT-${statusCode}`,
            activity_title: `Activity ${statusCode}`,
            claimed_progress_pct: progressPct,
            location: "Zone A",
            unit: "percent",
            personnel_count: claimedCount,
            sort_order: 0,
          },
        ],
        material_rows: [
          {
            material_code: "CEM",
            title: `Cement ${statusCode}`,
            unit: "bag",
            incoming_quantity: 3,
            consumed_quantity: 2,
            cumulative_quantity: 9,
            sort_order: 0,
          },
        ],
        issue_rows: [
          {
            issue_type: "ACCESS",
            description: `Issue ${statusCode}`,
            status: "OPEN",
            sort_order: 0,
          },
        ],
      },
    }),
    `create ${statusCode} site log for reports`
  );
  const data = body?.data || {};
  const id = Number(data?.id || 0);
  const logNo = String(data?.log_no || "").trim();
  expect(id).toBeGreaterThan(0);
  expect(logNo).not.toEqual("");
  return { id, logNo };
}

async function waitForSelectOption(page: Page, selector: string, value: string): Promise<void> {
  await page.waitForFunction(
    ({ selector: rawSelector, value: rawValue }) => {
      const select = document.querySelector(rawSelector) as HTMLSelectElement | null;
      if (!select) return false;
      return Array.from(select.options).some((option) => option.value === rawValue);
    },
    { selector, value },
    { timeout: 20_000 }
  );
}

test("report center shows site log analytical table", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await seedReportsContext(request, resolvedBaseUrl, headers);
  const draft = await createSiteLogForReport(request, resolvedBaseUrl, headers, context, "DRAFT", "DAILY", 5, 35);
  const submitted = await createSiteLogForReport(request, resolvedBaseUrl, headers, context, "SUBMITTED", "WEEKLY", 8, 60);

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await navigateToView(page, "view-reports", '[data-nav-target="view-reports"]');

  await expect(page.locator("#view-reports")).toBeVisible();
  await expect(page.locator('[data-report-tab-target="site-log"]')).toHaveClass(/active/);
  await expect(page.locator("#reports-tab-site-log")).toBeVisible();

  await waitForSelectOption(page, "#rpt-site-project", context.projectCode);
  await page.locator("#rpt-site-project").selectOption(context.projectCode);
  await page.locator('[data-report-action="site-log-generate"]').first().click();

  await expect(page.locator("#rpt-site-table-body")).toContainText(draft.logNo, { timeout: 20_000 });
  await expect(page.locator("#rpt-site-table-body")).toContainText(submitted.logNo);
  await expect(page.locator("#rpt-site-kpi-total")).not.toHaveText("0");

  await page.locator("#rpt-site-status").selectOption("DRAFT");
  await page.locator('[data-report-action="site-log-generate"]').first().click();
  await expect(page.locator("#rpt-site-table-body")).toContainText(draft.logNo, { timeout: 20_000 });
  await expect(page.locator("#rpt-site-table-body")).not.toContainText(submitted.logNo);

  await page.locator('[data-report-section="manpower"]').click();
  await expect(page.locator('[data-report-section="manpower"]')).toHaveClass(/active/);
  await expect(page.locator("#rpt-site-section-title")).toContainText("نفرات");
  await expect(page.locator("#rpt-site-table-body")).toContainText("Worker", { timeout: 20_000 });

  await page.locator('[data-report-section="material"]').click();
  await expect(page.locator("#rpt-site-section-title")).toContainText("مصالح");
  await expect(page.locator("#rpt-site-table-body")).toContainText("Cement DRAFT", { timeout: 20_000 });

  await page.locator('[data-report-section="activity"]').click();
  await expect(page.locator("#rpt-site-section-title")).toContainText("فعالیت");
  await expect(page.locator("#rpt-site-table-body")).toContainText("Activity DRAFT", { timeout: 20_000 });

  await expect(page.locator('[data-report-tab-target="powerbi"]')).toHaveCount(0);
  await expect(page.locator("#reports-tab-powerbi")).toHaveCount(0);

  await page.locator('[data-report-tab-target="comm"]').click();
  await expect(page.locator("#reports-tab-comm")).toBeVisible();
  await expect(page.locator("#rpt-aging-table")).toBeVisible();
});
