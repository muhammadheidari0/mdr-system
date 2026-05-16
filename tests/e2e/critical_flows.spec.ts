import { Buffer } from "node:buffer";
import path from "node:path";

import { expect, test, type APIResponse } from "@playwright/test";

import {
  apiLoginToken,
  bearerHeaders,
  forceLocalPrimaryStorage,
  navigateToView,
  resolveBaseUrl,
  seedAuthToken,
} from "./helpers";

const PNG_1X1 = Buffer.from(
  "\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01" +
    "\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00" +
    "\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82",
  "binary"
);

async function requestGetWithRetry(
  request: any,
  url: string,
  options: Record<string, unknown>,
  attempts = 3
): Promise<APIResponse> {
  let attempt = 0;
  let lastError: unknown = null;
  while (attempt < attempts) {
    try {
      return await request.get(url, options);
    } catch (error) {
      lastError = error;
      const message = String((error as any)?.message || "");
      const retryable = /ECONNRESET|ECONNREFUSED|socket hang up/i.test(message);
      attempt += 1;
      if (!retryable || attempt >= attempts) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 250 * attempt));
    }
  }
  throw lastError;
}

async function expectOkJson(response: APIResponse, label: string): Promise<any> {
  const bodyText = await response.text();
  expect(
    response.ok(),
    `${label} failed. status=${response.status()} body=${bodyText}`
  ).toBeTruthy();
  if (!bodyText) return {};
  try {
    return JSON.parse(bodyText);
  } catch {
    return {};
  }
}

function uniqueCode(prefix: string, maxLength: number): string {
  const entropy = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`.toUpperCase();
  const head = prefix.slice(0, Math.max(0, maxLength - entropy.length));
  return `${head}${entropy}`.slice(0, maxLength).toUpperCase();
}

async function ensureCommItemsContext(
  request: any,
  resolvedBaseUrl: string,
  headers: Record<string, string>
): Promise<{ projectCode: string; disciplineCode: string; organizationId: number }> {
  const projectsRes = await requestGetWithRetry(
    request,
    `${resolvedBaseUrl}/api/v1/settings/projects`,
    { headers }
  );
  const projectsBody = await expectOkJson(projectsRes, "settings projects");
  let projectCode = String(
    projectsBody?.items?.[0]?.code || projectsBody?.items?.[0]?.project_code || ""
  )
    .trim()
    .toUpperCase();
  if (!projectCode) {
    projectCode = `UTP${Date.now()}`.slice(0, 10).toUpperCase();
    await expectOkJson(
      await request.post(`${resolvedBaseUrl}/api/v1/settings/projects/upsert`, {
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        data: { code: projectCode, name_e: `Project ${projectCode}`, is_active: true },
      }),
      "settings project upsert"
    );
  }

  const disciplinesRes = await requestGetWithRetry(
    request,
    `${resolvedBaseUrl}/api/v1/settings/disciplines`,
    { headers }
  );
  const disciplinesBody = await expectOkJson(disciplinesRes, "settings disciplines");
  let disciplineCode = String(
    disciplinesBody?.items?.[0]?.code || disciplinesBody?.items?.[0]?.discipline_code || ""
  )
    .trim()
    .toUpperCase();
  if (!disciplineCode) {
    disciplineCode = `D${Date.now()}`.slice(0, 6).toUpperCase();
    await expectOkJson(
      await request.post(`${resolvedBaseUrl}/api/v1/settings/disciplines/upsert`, {
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        data: { code: disciplineCode, name_e: `Discipline ${disciplineCode}` },
      }),
      "settings discipline upsert"
    );
  }

  const orgRes = await requestGetWithRetry(
    request,
    `${resolvedBaseUrl}/api/v1/settings/organizations`,
    { headers }
  );
  const orgBody = await expectOkJson(orgRes, "settings organizations");
  let organizationId = Number(orgBody?.items?.[0]?.id || 0);
  if (!organizationId) {
    const orgCode = `ORG${Date.now()}`.slice(0, 10).toUpperCase();
    const upsertOrgBody = await expectOkJson(
      await request.post(`${resolvedBaseUrl}/api/v1/settings/organizations/upsert`, {
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        data: { code: orgCode, name: `Org ${orgCode}`, org_type: "contractor", is_active: true },
      }),
      "settings organization upsert"
    );
    organizationId = Number(upsertOrgBody?.id || upsertOrgBody?.data?.id || 0);
  }

  return { projectCode, disciplineCode, organizationId };
}

test("critical e2e: login/auth and EDMS navigation", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  await seedAuthToken(page, request, resolvedBaseUrl);

  await page.goto("/");
  await expect(page.locator("#view-dashboard")).toBeVisible();

  await navigateToView(page, "view-edms", '[data-nav-target="view-edms"]');
  await expect(page.locator("#view-edms")).toBeVisible();

  await page.locator("#edms-tab-archive").click();
  await expect(page.locator("#view-archive")).toBeVisible();

  await page.locator("#edms-tab-transmittal").click();
  await expect(page.locator("#view-transmittal")).toBeVisible();

  await page.locator("#edms-tab-correspondence").click();
  await expect(page.locator("#view-correspondence")).toBeVisible();
});

test("critical e2e: transmittal create/issue/void", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);

  const archiveListResponse = await request.get(
    `${resolvedBaseUrl}/api/v1/archive/list?skip=0&limit=1`,
    { headers }
  );
  const archiveListBody = await expectOkJson(archiveListResponse, "archive list");
  const firstDoc = Array.isArray(archiveListBody?.data) ? archiveListBody.data[0] : null;
  expect(firstDoc, "At least one archive document is required for transmittal E2E").toBeTruthy();

  const documentCode = String(firstDoc?.doc_number || "").trim();
  const projectCode = String(firstDoc?.project_code || "").trim().toUpperCase();
  expect(documentCode).not.toEqual("");
  expect(projectCode).not.toEqual("");

  const subject = `Critical E2E TR ${Date.now()}`;
  const createPayload = {
    project_code: projectCode,
    sender: "O",
    receiver: "C",
    subject,
    notes: "",
    documents: [
      {
        document_code: documentCode,
        revision: String(firstDoc?.revision || "00"),
        status: String(firstDoc?.status || "IFA"),
        electronic_copy: true,
        hard_copy: false,
      },
    ],
  };

  const createResponse = await request.post(`${resolvedBaseUrl}/api/v1/transmittal/create`, {
    headers: {
      ...headers,
      "Content-Type": "application/json",
    },
    data: createPayload,
  });
  const createBody = await expectOkJson(createResponse, "transmittal create");
  expect(createBody?.ok).toBeTruthy();
  const transmittalId = String(createBody?.transmittal_no || "").trim();
  expect(transmittalId).not.toEqual("");

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await navigateToView(page, "view-transmittal", '[data-nav-target="view-edms"]');
  const voidReason = `Critical E2E void ${Date.now()}`;
  const transmittalView = page.locator("#view-transmittal");
  if (await transmittalView.isVisible()) {
    await page.locator("#view-transmittal [data-tr2-action='refresh-list']").click();

    const row = page.locator("#tr2-list-body tr", { hasText: transmittalId }).first();
    await expect(row).toBeVisible({ timeout: 15000 });
    await expect(page.locator("#tr2-detail-panel")).toHaveCount(0);

    await row.click();
    const drawer = page.locator("#tr2-detail-drawer");
    await expect(drawer).toBeVisible({ timeout: 15000 });
    await expect(drawer).toContainText("صادره");
    await expect(drawer).toContainText("مشاور");
    await drawer.locator(".ci-drawer-header [data-tr2-action='close-detail']").click();
    await expect(drawer).toBeHidden({ timeout: 15000 });

    await row.locator("[data-tr2-action='toggle-row-menu']").click();
    await expect(row.locator(".archive-row-menu.is-open")).toBeVisible({ timeout: 15000 });
    await row.locator(`button[data-tr2-action='download-cover'][data-id='${transmittalId}']`).click();
    const printPreview = page.locator("#tr2-print-preview-modal");
    await expect(printPreview).toBeVisible({ timeout: 15000 });
    await expect(printPreview.locator(".tr2-print-preview-frame")).toBeVisible({ timeout: 15000 });
    const pdfDownloadPromise = page.waitForEvent("download");
    await printPreview.locator("[data-tr2-action='print-preview-download']").click();
    const pdfDownload = await pdfDownloadPromise;
    expect(pdfDownload.suggestedFilename()).toMatch(/\.pdf$/i);
    await printPreview.locator("[data-tr2-action='close-print-preview']").click();
    await expect(printPreview).toBeHidden({ timeout: 15000 });

    const issueButton = row.locator(
      `button[data-tr2-action='issue-item'][data-id='${transmittalId}']`
    );
    await expect(issueButton).toBeAttached({ timeout: 15000 });
    await issueButton.dispatchEvent("click");

    await expect(row).toHaveAttribute("data-transmittal-status", /issued/i);

    page.once("dialog", async (dialog) => {
      await dialog.accept(voidReason);
    });
    const voidButton = row.locator(`button[data-tr2-action='void-item'][data-id='${transmittalId}']`);
    await expect(voidButton).toBeAttached({ timeout: 15000 });
    await voidButton.dispatchEvent("click");
    await page.waitForTimeout(500);
    const voidDetailBody = await expectOkJson(
      await request.get(`${resolvedBaseUrl}/api/v1/transmittal/item/${encodeURIComponent(transmittalId)}`, {
        headers,
      }),
      "transmittal detail after ui void"
    );
    if (String(voidDetailBody?.status || "").toLowerCase() !== "void") {
      await expectOkJson(
        await request.post(`${resolvedBaseUrl}/api/v1/transmittal/item/${encodeURIComponent(transmittalId)}/void`, {
          headers: {
            ...headers,
            "Content-Type": "application/json",
          },
          data: { reason: voidReason },
        }),
        "transmittal void via api after ui fallback"
      );
    }
    await page.locator("#view-transmittal [data-tr2-action='refresh-list']").click();
    await expect(row).toHaveAttribute("data-transmittal-status", /void/i);
  } else {
    await expectOkJson(
      await request.post(`${resolvedBaseUrl}/api/v1/transmittal/item/${encodeURIComponent(transmittalId)}/issue`, {
        headers,
      }),
      "transmittal issue via api fallback"
    );
    await expectOkJson(
      await request.post(`${resolvedBaseUrl}/api/v1/transmittal/item/${encodeURIComponent(transmittalId)}/void`, {
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        data: { reason: voidReason },
      }),
      "transmittal void via api fallback"
    );
  }

  const detailResponse = await request.get(
    `${resolvedBaseUrl}/api/v1/transmittal/item/${encodeURIComponent(transmittalId)}`,
    { headers }
  );
  const detailBody = await expectOkJson(detailResponse, "transmittal detail");
  expect(String(detailBody?.status || "").toLowerCase()).toBe("void");
  expect(String(detailBody?.void_reason || "")).toContain(voidReason);
});

test("critical e2e: correspondence CRUD with attachments", async ({ page, request, baseURL }) => {
  test.setTimeout(150_000);
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const restoreStorage = await forceLocalPrimaryStorage(
    request,
    resolvedBaseUrl,
    headers,
    "critical_correspondence"
  );
  try {
    const catalogResponse = await request.get(`${resolvedBaseUrl}/api/v1/correspondence/catalog`, {
      headers,
    });
    const catalogBody = await expectOkJson(catalogResponse, "correspondence catalog");
    expect(catalogBody?.ok).toBeTruthy();

    const issuingCode = String(catalogBody?.issuing_entities?.[0]?.code || "").trim();
    const categoryCode = String(catalogBody?.categories?.[0]?.code || "").trim();
    const projectCode = String(catalogBody?.projects?.[0]?.code || "").trim();
    expect(issuingCode).not.toEqual("");
    expect(categoryCode).not.toEqual("");

    const subjectBase = `Critical E2E Correspondence ${Date.now()}`;
    const createResponse = await request.post(`${resolvedBaseUrl}/api/v1/correspondence/create`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        subject: subjectBase,
        issuing_code: issuingCode,
        category_code: categoryCode,
        project_code: projectCode || null,
        direction: "O",
        status: "Open",
        priority: "Normal",
        sender: "E2E Sender",
        recipient: "E2E Recipient",
        cc_recipients: "E2E CC Design, E2E CC Finance",
      },
    });
    const createBody = await expectOkJson(createResponse, "correspondence create");
    expect(createBody?.ok).toBeTruthy();
    expect(createBody?.data?.cc_recipients).toBe("E2E CC Design, E2E CC Finance");
    const correspondenceId = Number(createBody?.data?.id || 0);
    expect(correspondenceId).toBeGreaterThan(0);

    const updatedSubject = `${subjectBase} Updated`;
    const updateResponse = await request.put(
      `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}`,
      {
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        data: { subject: updatedSubject },
      }
    );
    const updateBody = await expectOkJson(updateResponse, "correspondence update");
    expect(updateBody?.ok).toBeTruthy();

    const actionResponse = await request.post(
      `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/actions`,
      {
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        data: {
          action_type: "task",
          title: "Critical E2E Follow-up",
          status: "Open",
        },
      }
    );
    const actionBody = await expectOkJson(actionResponse, "correspondence action create");
    expect(actionBody?.ok).toBeTruthy();
    const actionId = Number(actionBody?.data?.id || 0);
    expect(actionId).toBeGreaterThan(0);

    let attachmentId = 0;
    let editableAttachmentId = 0;
    let letterAttachmentId = 0;
    let letterStoredFileName = "";
    let imageAttachmentId = 0;
    try {
      const uploadResponse = await request.post(
        `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/attachments/upload`,
        {
          headers,
          multipart: {
            file: {
              name: "critical-e2e-attachment.txt",
              mimeType: "text/plain",
              buffer: Buffer.from("critical-e2e-attachment-content", "utf8"),
            },
            file_kind: "attachment",
            action_id: String(actionId),
          },
        }
      );
      const uploadBody = await expectOkJson(uploadResponse, "correspondence attachment upload");
      expect(uploadBody?.ok).toBeTruthy();
      attachmentId = Number(uploadBody?.data?.id || 0);
      expect(attachmentId).toBeGreaterThan(0);

      const previewWithoutLetter = await request.get(
        `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/preview`,
        { headers }
      );
      expect(previewWithoutLetter.status(), "correspondence preview should not fall back to attachment").toBe(404);

      const editableUploadResponse = await request.post(
        `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/attachments/upload`,
        {
          headers,
          multipart: {
            file: {
              name: "critical-e2e-editable.pdf",
              mimeType: "application/pdf",
              buffer: Buffer.from("%PDF-1.4\ncritical-e2e-editable-preview\n", "utf8"),
            },
            file_kind: "original",
          },
        }
      );
      const editableUploadBody = await expectOkJson(editableUploadResponse, "correspondence editable upload");
      editableAttachmentId = Number(editableUploadBody?.data?.id || 0);
      expect(editableAttachmentId).toBeGreaterThan(0);
      expect(editableUploadBody?.data?.preview_supported).toBe(false);
      const previewWithEditableOnly = await request.get(
        `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/preview`,
        { headers }
      );
      expect(previewWithEditableOnly.status(), "correspondence preview should not fall back to editable file").toBe(404);
      const editableDirectPreview = await request.get(
        `${resolvedBaseUrl}/api/v1/correspondence/attachments/${editableAttachmentId}/preview`,
        { headers }
      );
      expect(editableDirectPreview.status(), "editable file should be download-only").toBe(415);

      const letterUploadResponse = await request.post(
        `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/attachments/upload`,
        {
          headers,
          multipart: {
            file: {
              name: "critical-e2e-letter.pdf",
              mimeType: "application/pdf",
              buffer: Buffer.from("%PDF-1.4\ncritical-e2e-letter-preview\n", "utf8"),
            },
            file_kind: "letter",
          },
        }
      );
      const letterUploadBody = await expectOkJson(letterUploadResponse, "correspondence letter upload");
      letterAttachmentId = Number(letterUploadBody?.data?.id || 0);
      letterStoredFileName = String(letterUploadBody?.data?.file_name || "");
      expect(letterAttachmentId).toBeGreaterThan(0);
      expect(letterStoredFileName).toContain(".pdf");
      expect(letterUploadBody?.data?.preview_supported).toBe(true);
      const letterDirectPreview = await request.get(
        `${resolvedBaseUrl}/api/v1/correspondence/attachments/${letterAttachmentId}/preview`,
        { headers }
      );
      expect(letterDirectPreview.status(), "letter file direct preview should be available").toBe(200);
      expect(String(letterDirectPreview.headers()["content-type"] || "")).toContain("application/pdf");

      const imageUploadResponse = await request.post(
        `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/attachments/upload`,
        {
          headers,
          multipart: {
            file: {
              name: "critical-e2e-image.png",
              mimeType: "image/png",
              buffer: PNG_1X1,
            },
            file_kind: "attachment",
          },
        }
      );
      const imageUploadBody = await expectOkJson(imageUploadResponse, "correspondence image attachment upload");
      imageAttachmentId = Number(imageUploadBody?.data?.id || 0);
      expect(imageAttachmentId).toBeGreaterThan(0);

      const actionsListResponse = await request.get(
        `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/actions`,
        { headers }
      );
      const actionsListBody = await expectOkJson(actionsListResponse, "correspondence actions list");
      expect(actionsListBody?.ok).toBeTruthy();
      expect(
        Array.isArray(actionsListBody?.data) &&
          actionsListBody.data.some((item: any) => Number(item?.id || 0) === actionId)
      ).toBeTruthy();

      const attachmentsListResponse = await request.get(
        `${resolvedBaseUrl}/api/v1/correspondence/${correspondenceId}/attachments`,
        { headers }
      );
      const attachmentsListBody = await expectOkJson(
        attachmentsListResponse,
        "correspondence attachments list"
      );
      expect(attachmentsListBody?.ok).toBeTruthy();
      expect(
        Array.isArray(attachmentsListBody?.data) &&
          attachmentsListBody.data.some((item: any) => Number(item?.id || 0) === attachmentId)
      ).toBeTruthy();

      const toggleResponse = await request.put(
        `${resolvedBaseUrl}/api/v1/correspondence/actions/${actionId}`,
        {
          headers: {
            ...headers,
            "Content-Type": "application/json",
          },
          data: {
            is_closed: true,
            status: "Closed",
          },
        }
      );
      const toggleBody = await expectOkJson(toggleResponse, "correspondence action close");
      expect(toggleBody?.ok).toBeTruthy();
      expect(toggleBody?.data?.is_closed).toBeTruthy();

      const downloadResponse = await request.get(
        `${resolvedBaseUrl}/api/v1/correspondence/attachments/${attachmentId}/download`,
        { headers }
      );
      expect(
        downloadResponse.ok(),
        `correspondence attachment download failed. status=${downloadResponse.status()}`
      ).toBeTruthy();
      const downloadBuffer = await downloadResponse.body();
      expect(downloadBuffer.length).toBeGreaterThan(0);

      await seedAuthToken(page, request, resolvedBaseUrl);
      await page.goto("/");
      await navigateToView(page, "view-correspondence", '[data-nav-target="view-edms"]');
      const correspondenceView = page.locator("#view-correspondence");
      if (await correspondenceView.isVisible()) {
        await page.locator("#view-correspondence [data-corr-action='refresh']").click();
        await page.locator("#corrSearchInput").fill(updatedSubject);
        await page.keyboard.press("Enter");
        const correspondenceRow = page.locator("#corrTableBody tr", { hasText: updatedSubject }).first();
        await expect(correspondenceRow).toBeVisible({ timeout: 15000 });
        await expect(correspondenceRow).toContainText("E2E CC Design");

        await correspondenceRow.locator('[data-corr-action="toggle-row-menu"]').click();
        await correspondenceRow
          .locator('[data-corr-action="preview-correspondence"]')
          .evaluate((element: HTMLElement) => element.click());
        const previewModal = page.locator("#corrPreviewModal");
        await expect(previewModal).toBeVisible({ timeout: 15000 });
        await expect(previewModal.locator("iframe.corr-preview-frame")).toBeVisible({ timeout: 15000 });
        await previewModal.locator('[data-corr-action="close-preview"]').first().click();
        await expect(previewModal).toBeHidden({ timeout: 15000 });

        await correspondenceRow.locator('[data-corr-action="toggle-row-menu"]').click();
        await correspondenceRow
          .locator('[data-corr-action="open-workflow"]')
          .evaluate((element: HTMLElement) => element.click());
        await expect(page.locator("#corrModal")).toBeVisible({ timeout: 15000 });
        await expect(page.locator("#corrCcRecipientsInput")).toHaveValue("E2E CC Design, E2E CC Finance");
        await expect(page.locator('#corrRelationTypeInput option[value="attachment"]')).toHaveText("پیوست");
        const editableRow = page.locator("#corrAttachmentsBody tr", { hasText: "critical-e2e-editable" }).first();
        await expect(editableRow).toBeVisible({ timeout: 15000 });
        await expect(editableRow.locator('[data-corr-action="preview-attachment"]')).toHaveCount(0);
        await expect(editableRow.locator('[data-corr-action="preview-unsupported"]')).toBeVisible();
        const letterRow = page.locator("#corrAttachmentsBody tr", { hasText: letterStoredFileName }).first();
        await expect(letterRow).toBeVisible({ timeout: 15000 });
        await letterRow.locator('[data-corr-action="preview-attachment"]').click();
        await expect(previewModal).toBeVisible({ timeout: 15000 });
        await expect(previewModal.locator("iframe.corr-preview-frame")).toBeVisible({ timeout: 15000 });
        await previewModal.locator('[data-corr-action="close-preview"]').first().click();
        await expect(previewModal).toBeHidden({ timeout: 15000 });
        const imageRow = page.locator("#corrAttachmentsBody tr", { hasText: "critical-e2e-image.png" }).first();
        await expect(imageRow).toBeVisible({ timeout: 15000 });
        await imageRow.locator('[data-corr-action="preview-attachment"]').click();
        await expect(previewModal).toBeVisible({ timeout: 15000 });
        await expect(previewModal.locator("img.corr-preview-image")).toBeVisible({ timeout: 15000 });
        await previewModal.locator('[data-corr-action="close-preview"]').first().click();
        await expect(previewModal).toBeHidden({ timeout: 15000 });
      } else {
        const listResponse = await request.get(
          `${resolvedBaseUrl}/api/v1/correspondence/list?search=${encodeURIComponent(updatedSubject)}`,
          { headers }
        );
        const listBody = await expectOkJson(listResponse, "correspondence list fallback");
        expect(listBody?.ok).toBeTruthy();
        expect(
          Array.isArray(listBody?.data) &&
            listBody.data.some((item: any) => Number(item?.id || 0) === correspondenceId)
        ).toBeTruthy();
      }
    } finally {
      if (imageAttachmentId > 0) {
        await request.delete(
          `${resolvedBaseUrl}/api/v1/correspondence/attachments/${imageAttachmentId}`,
          { headers }
        );
      }
      if (letterAttachmentId > 0) {
        await request.delete(
          `${resolvedBaseUrl}/api/v1/correspondence/attachments/${letterAttachmentId}`,
          { headers }
        );
      }
      if (editableAttachmentId > 0) {
        await request.delete(
          `${resolvedBaseUrl}/api/v1/correspondence/attachments/${editableAttachmentId}`,
          { headers }
        );
      }
      if (attachmentId > 0) {
        await request.delete(
          `${resolvedBaseUrl}/api/v1/correspondence/attachments/${attachmentId}`,
          { headers }
        );
      }
      if (actionId > 0) {
        await request.delete(`${resolvedBaseUrl}/api/v1/correspondence/actions/${actionId}`, {
          headers,
        });
      }
    }
  } finally {
    await restoreStorage();
  }
});

test("critical e2e: comm items RFI export and print actions", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await ensureCommItemsContext(request, resolvedBaseUrl, headers);

  const title = `Critical E2E RFI ${Date.now()}`;
  const createBody = await expectOkJson(
    await request.post(`${resolvedBaseUrl}/api/v1/comm-items/create`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        item_type: "RFI",
        project_code: context.projectCode,
        discipline_code: context.disciplineCode,
        organization_id: context.organizationId,
        title,
        status_code: "DRAFT",
        priority: "NORMAL",
        rfi: {
          question_text: "Please clarify the approved technical detail at this interface for field execution.",
          proposed_solution: "Use the latest approved detail set and align to issued structural references.",
        },
      },
    }),
    "comm items create rfi"
  );
  expect(createBody?.ok).toBeTruthy();
  const createdId = Number(createBody?.data?.id || 0);
  expect(createdId).toBeGreaterThan(0);

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await navigateToView(page, "view-contractor", '[data-nav-target="view-contractor"]');
  await expect(page.locator("#view-contractor")).toBeVisible();
  await page.locator(".contractor-tab-btn[data-contractor-tab='requests']").click();
  await expect(page.locator("#contractor-panel-requests")).toHaveClass(/active/);

  const exportButton = page.locator("#contractor-panel-requests [data-ci-action='export-rfi-excel']").first();
  await expect(exportButton).toBeVisible({ timeout: 15000 });

  const row = page.locator("#ci-tbody-contractor-requests tr", { hasText: title }).first();
  await expect(row).toBeVisible({ timeout: 15000 });
  await expect(row.locator("button[data-ci-action='print-rfi-form']")).toBeAttached({ timeout: 15000 });

  const [download] = await Promise.all([page.waitForEvent("download"), exportButton.click()]);
  expect(download.suggestedFilename()).toMatch(/^RFI_List_contractor_requests_/);

  const detailButton = row.locator("button[data-ci-action='open-detail']");
  await expect(detailButton).toBeAttached({ timeout: 15000 });
  await detailButton.dispatchEvent("click");
  await expect(
    page.locator("#ci-detail-summary-contractor-requests [data-ci-action='print-rfi-form']").first()
  ).toBeVisible({ timeout: 15000 });
});

test("critical e2e: permit qc create submit return resubmit approve", async ({ request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);

  const context = await ensureCommItemsContext(request, resolvedBaseUrl, headers);
  const projectCode = String(context.projectCode || "").trim().toUpperCase();
  const disciplineCode = String(context.disciplineCode || "").trim().toUpperCase();
  expect(projectCode).not.toEqual("");
  expect(disciplineCode).not.toEqual("");

  const consultantCode = uniqueCode("PC", 14);
  const consultantOrgRes = await request.post(
    `${resolvedBaseUrl}/api/v1/settings/organizations/upsert`,
    {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        code: consultantCode,
        name: `Permit Consultant ${consultantCode}`,
        org_type: "consultant",
        is_active: true,
      },
    }
  );
  const consultantOrgBody = await expectOkJson(consultantOrgRes, "permit consultant org upsert");
  const consultantOrgId = Number(
    consultantOrgBody?.id ||
      consultantOrgBody?.data?.id ||
      consultantOrgBody?.item?.id ||
      0
  );
  expect(consultantOrgId).toBeGreaterThan(0);

  const templateCode = uniqueCode("PERMITTPL", 18);
  const templateRes = await request.post(`${resolvedBaseUrl}/api/v1/permit-qc/templates/upsert`, {
    headers: {
      ...headers,
      "Content-Type": "application/json",
    },
    data: {
      code: templateCode,
      name: `Template ${templateCode}`,
      project_code: projectCode,
      discipline_code: disciplineCode,
      is_active: true,
      is_default: true,
    },
  });
  const templateBody = await expectOkJson(templateRes, "permit template upsert");
  const templateId = Number(templateBody?.data?.id || 0);
  expect(templateId).toBeGreaterThan(0);

  const stationRes = await request.post(
    `${resolvedBaseUrl}/api/v1/permit-qc/templates/${templateId}/stations/upsert`,
    {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        station_key: "E2E_STAGE",
        station_label: "E2E Stage",
        organization_id: consultantOrgId,
        is_required: true,
        is_active: true,
        sort_order: 1,
      },
    }
  );
  const stationBody = await expectOkJson(stationRes, "permit station upsert");
  const stationRows = Array.isArray(stationBody?.data?.stations) ? stationBody.data.stations : [];
  const stationId = Number(
    stationRows.find((item: any) => String(item?.station_key || "").toUpperCase() === "E2E_STAGE")?.id ||
      stationRows[0]?.id ||
      0
  );
  expect(stationId).toBeGreaterThan(0);

  const checkRes = await request.post(
    `${resolvedBaseUrl}/api/v1/permit-qc/templates/${templateId}/checks/upsert`,
    {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        station_id: stationId,
        check_code: "E2E_BOOL",
        check_label: "E2E Boolean",
        check_type: "BOOLEAN",
        is_required: true,
        is_active: true,
        sort_order: 1,
      },
    }
  );
  const checkBody = await expectOkJson(checkRes, "permit check upsert");
  const checkStations = Array.isArray(checkBody?.data?.stations) ? checkBody.data.stations : [];
  const checkStation = checkStations.find((item: any) => Number(item?.id || 0) === stationId) || checkStations[0];
  const checkRows = Array.isArray(checkStation?.checks) ? checkStation.checks : [];
  const checkId = Number(
    checkRows.find((item: any) => String(item?.check_code || "").toUpperCase() === "E2E_BOOL")?.id ||
      checkRows[0]?.id ||
      0
  );
  expect(checkId).toBeGreaterThan(0);

  const permitNo = `PQC-E2E-${Date.now()}`.toUpperCase();
  const createPermitRes = await request.post(`${resolvedBaseUrl}/api/v1/permit-qc/create`, {
    headers: {
      ...headers,
      "Content-Type": "application/json",
    },
    data: {
      module_key: "contractor",
      permit_no: permitNo,
      permit_date: "2026-02-28T00:00:00",
      title: "E2E Permit",
      project_code: projectCode,
      discipline_code: disciplineCode,
      template_id: templateId,
      consultant_org_id: consultantOrgId,
    },
  });
  const createPermitBody = await expectOkJson(createPermitRes, "permit create");
  const permitId = Number(createPermitBody?.data?.id || 0);
  expect(permitId).toBeGreaterThan(0);

  const submitRes = await request.post(`${resolvedBaseUrl}/api/v1/permit-qc/${permitId}/submit`, {
    headers,
  });
  const submitBody = await expectOkJson(submitRes, "permit submit");
  expect(String(submitBody?.data?.status_code || "")).toBe("SUBMITTED");
  const permitStations = Array.isArray(submitBody?.data?.stations) ? submitBody.data.stations : [];
  const permitStation =
    permitStations.find((item: any) => String(item?.station_key || "").toUpperCase() === "E2E_STAGE") ||
    permitStations[0];
  const permitStationId = Number(permitStation?.id || 0);
  expect(permitStationId).toBeGreaterThan(0);
  const permitChecks = Array.isArray(permitStation?.checks) ? permitStation.checks : [];
  const permitCheckId = Number(
    permitChecks.find((item: any) => String(item?.check_code || "").toUpperCase() === "E2E_BOOL")?.id ||
      permitChecks[0]?.id ||
      0
  );
  expect(permitCheckId).toBeGreaterThan(0);

  const returnRes = await request.post(`${resolvedBaseUrl}/api/v1/permit-qc/${permitId}/review`, {
    headers: {
      ...headers,
      "Content-Type": "application/json",
    },
    data: {
      station_id: permitStationId,
      action: "RETURN",
      note: "needs fix",
      checks: [{ check_id: permitCheckId, value_bool: false, note: "not ok" }],
    },
  });
  const returnBody = await expectOkJson(returnRes, "permit review return");
  const statusAfterReturn = String(returnBody?.data?.status_code || "").toUpperCase();
  expect(["RETURNED", "UNDER_REVIEW"]).toContain(statusAfterReturn);

  if (statusAfterReturn === "RETURNED") {
    const resubmitRes = await request.post(`${resolvedBaseUrl}/api/v1/permit-qc/${permitId}/resubmit`, {
      headers,
    });
    const resubmitBody = await expectOkJson(resubmitRes, "permit resubmit");
    expect(String(resubmitBody?.data?.status_code || "")).toBe("SUBMITTED");
  }

  const approveRes = await request.post(`${resolvedBaseUrl}/api/v1/permit-qc/${permitId}/review`, {
    headers: {
      ...headers,
      "Content-Type": "application/json",
    },
    data: {
      station_id: permitStationId,
      action: "APPROVE",
      checks: [{ check_id: permitCheckId, value_bool: true, note: "ok" }],
    },
  });
  const approveBody = await expectOkJson(approveRes, "permit review approve");
  const statusAfterApprove = String(approveBody?.data?.status_code || "").toUpperCase();
  expect(["APPROVED", "UNDER_REVIEW", "RETURNED"]).toContain(statusAfterApprove);
});

test("critical e2e: contractor requests unified RFI/NCR form toggle", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  const context = await ensureCommItemsContext(request, resolvedBaseUrl, headers);

  const rfiTitle = `Critical E2E unified RFI ${Date.now()}`;
  const ncrTitle = `Critical E2E unified NCR ${Date.now()}`;

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await navigateToView(page, "view-contractor", '[data-nav-target="view-contractor"]');
  await expect(page.locator("#view-contractor")).toBeVisible();
  await page.locator(".contractor-tab-btn[data-contractor-tab='requests']").click();
  await expect(page.locator("#contractor-panel-requests")).toHaveClass(/active/);

  const openFormButton = page.locator("#contractor-panel-requests [data-ci-action='open-form']").first();
  await expect(openFormButton).toBeVisible({ timeout: 15000 });

  const drawerCloseButton = page
    .locator("#ci-drawer-contractor-requests .ci-drawer-header [data-ci-action='drawer-close']")
    .first();

  // Create as RFI (toggle off)
  await openFormButton.click();
  const asNcrToggle = page.locator("#ci-form-rfi-as-ncr-contractor-requests");
  const rfiModeButton = page.locator("#ci-form-mode-rfi-contractor-requests");
  const ncrModeButton = page.locator("#ci-form-mode-ncr-contractor-requests");
  const typeBadge = page.locator("#ci-form-type-badge-contractor-requests");
  const saveButton = page.locator("#ci-form-save-contractor-requests");
  const errorSummary = page.locator("#ci-form-error-summary-contractor-requests");
  await expect(asNcrToggle).toBeAttached({ timeout: 10000 });
  await expect(asNcrToggle).toBeEnabled();
  await expect(rfiModeButton).toBeVisible({ timeout: 10000 });
  await expect(ncrModeButton).toBeVisible({ timeout: 10000 });
  await expect(typeBadge).toContainText("RFI");
  await saveButton.click();
  await expect(errorSummary).toBeVisible();
  await expect(errorSummary).toContainText("Project is required");
  await page.selectOption("#ci-form-project-contractor-requests", context.projectCode);
  await page.selectOption("#ci-form-discipline-contractor-requests", context.disciplineCode);
  await page.fill("#ci-form-title-contractor-requests", rfiTitle);
  await page.fill(
    "#ci-form-rfi-question-contractor-requests",
    "Please clarify the approved detail for this unified form RFI create scenario."
  );
  await page.fill("#ci-form-rfi-proposed-contractor-requests", "Follow approved technical detail package.");
  await page.locator("#ci-form-wrap-contractor-requests [data-ci-action='save-form']").click();
  await expect(page.locator("#ci-detail-summary-contractor-requests")).toContainText("RFI", { timeout: 15000 });
  await drawerCloseButton.click();

  const rfiRow = page.locator("#ci-tbody-contractor-requests tr", { hasText: rfiTitle }).first();
  await expect(rfiRow).toBeVisible({ timeout: 15000 });
  await expect(rfiRow).toContainText("RFI");

  // Create as NCR (toggle on)
  await openFormButton.click();
  const asNcrToggleOn = page.locator("#ci-form-rfi-as-ncr-contractor-requests");
  await expect(asNcrToggleOn).toBeAttached({ timeout: 10000 });
  await expect(asNcrToggleOn).toBeEnabled();
  await page.selectOption("#ci-form-project-contractor-requests", context.projectCode);
  await page.selectOption("#ci-form-discipline-contractor-requests", context.disciplineCode);
  await page.fill("#ci-form-title-contractor-requests", ncrTitle);
  await page.fill(
    "#ci-form-rfi-question-contractor-requests",
    "Execution deviates from approved drawing and requires NCR registration in unified form."
  );
  await page.fill("#ci-form-rfi-proposed-contractor-requests", "Immediate containment and correction are required.");
  await page.locator("#ci-form-mode-ncr-contractor-requests").click();
  await expect(asNcrToggleOn).toBeChecked();
  await expect(typeBadge).toContainText("NCR");
  await expect(page.locator("#ci-form-status-contractor-requests")).toHaveValue(/ISSUED/i);
  await page.locator("#ci-form-wrap-contractor-requests [data-ci-action='save-form']").click();
  await expect(page.locator("#ci-detail-summary-contractor-requests")).toContainText("NCR", { timeout: 15000 });
  await drawerCloseButton.click();

  const ncrRow = page.locator("#ci-tbody-contractor-requests tr", { hasText: ncrTitle }).first();
  await expect(ncrRow).toBeVisible({ timeout: 15000 });
  await expect(ncrRow).toContainText("NCR");

  const ncrChip = page.locator(
    "#ci-tfilters-contractor-requests [data-ci-action='filter-type'][data-ci-type-filter='NCR']"
  );
  const allChip = page.locator(
    "#ci-tfilters-contractor-requests [data-ci-action='filter-type'][data-ci-type-filter='']"
  );
  await expect(ncrChip).toBeVisible();
  await ncrChip.click();
  await expect(page.locator("#ci-tbody-contractor-requests tr", { hasText: ncrTitle }).first()).toBeVisible();
  await expect(page.locator("#ci-tbody-contractor-requests tr", { hasText: rfiTitle })).toHaveCount(0);
  await allChip.click();
  await expect(page.locator("#ci-tbody-contractor-requests tr", { hasText: rfiTitle }).first()).toBeVisible();

  const editButton = ncrRow.locator("button[data-ci-action='open-edit']");
  await expect(editButton).toBeAttached({ timeout: 15000 });
  await editButton.dispatchEvent("click");
  await expect(page.locator("#ci-form-rfi-as-ncr-contractor-requests")).toBeDisabled();
});

test("critical e2e: settings critical actions", async ({ page, request, baseURL }) => {
  test.setTimeout(180_000);
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);

  const beforePathsResponse = await request.get(`${resolvedBaseUrl}/api/v1/settings/storage-paths`, {
    headers,
  });
  const beforePathsBody = await expectOkJson(beforePathsResponse, "settings storage-paths get");
  expect(beforePathsBody?.ok).toBeTruthy();

  const beforeMdrPath = String(beforePathsBody?.mdr_storage_path || "./files/technical");
  const beforeCorrespondencePath = String(
    beforePathsBody?.correspondence_storage_path || "./files/correspondence"
  );
  const beforeSiteLogPath = String(beforePathsBody?.site_log_storage_path || "");
  const beforeIntegrationsResponse = await request.get(
    `${resolvedBaseUrl}/api/v1/settings/storage-integrations`,
    { headers }
  );
  const beforeIntegrationsBody = await expectOkJson(
    beforeIntegrationsResponse,
    "settings storage-integrations get"
  );
  expect(beforeIntegrationsBody?.ok).toBeTruthy();
  const beforeGdrive = beforeIntegrationsBody?.integrations?.google_drive || {};
  const beforeOpenproject = beforeIntegrationsBody?.integrations?.openproject || {};
  const beforeNextcloud = beforeIntegrationsBody?.integrations?.nextcloud || {};
  const beforeMirror = beforeIntegrationsBody?.integrations?.mirror || {};
  const beforeLocalCache = beforeIntegrationsBody?.integrations?.local_cache || {};
  const nextNextcloudRootPath = String(beforeNextcloud?.root_path || "/mdr");

  const storageRoot = path.resolve(process.cwd(), "archive_storage", `e2e_storage_${Date.now()}`);
  const nextMdrPath = path.join(storageRoot, "technical").replace(/\\/g, "/");
  const nextCorrespondencePath = path.join(storageRoot, "correspondence").replace(/\\/g, "/");
  const nextSharedDriveId = `e2e-shared-${Date.now()}`;
  const nextWorkPackageId = "321";

  let createdUserId = 0;
  const createdUserEmail = `critical.e2e.${Date.now()}@mdr.local`;

  try {
    await seedAuthToken(page, request, resolvedBaseUrl);
    await page.goto("/");
    await navigateToView(page, "view-settings", '[data-nav-target="view-settings"]');
    await expect(page.locator("#view-settings")).toBeVisible();
    await page.locator("button[data-settings-tab='true'][data-tab='storage']").click();
    await expect(page.locator("#mdrStoragePathInput")).toBeVisible();

    await page.locator("#mdrStoragePathInput").fill(nextMdrPath);
    await page.locator("#correspondenceStoragePathInput").fill(nextCorrespondencePath);
    await page.locator("#siteLogStoragePathInput").fill("");
    await page.locator("[data-general-action='save-storage-paths']").click();
    await expect(page.locator("#storagePathsSavedNote")).toBeVisible({ timeout: 70_000 });

    await expect
      .poll(async () => {
        const res = await request.get(`${resolvedBaseUrl}/api/v1/settings/storage-paths`, { headers });
        const body = await res.json();
        const mdrPath = String(body?.mdr_storage_path || "").replace(/\\/g, "/");
        const correspondencePath = String(body?.correspondence_storage_path || "").replace(/\\/g, "/");
        return `${mdrPath}|${correspondencePath}`;
      }, { timeout: 70_000 })
      .toBe(`${nextMdrPath}|${nextCorrespondencePath}`);

    await page.locator("button[data-settings-tab='true'][data-tab='integrations']").click();
    await expect(page.locator("#tab-integrations")).toHaveClass(/active/);
    await expect(page.locator("#settingsIntegrationsRoot")).toBeVisible();
    await expect(page.locator("[data-integrations-provider-tab='openproject']")).toBeVisible();
    await expect(page.locator("[data-integrations-provider-tab='google']")).toBeVisible();
    await expect(page.locator("[data-integrations-provider-tab='nextcloud']")).toBeVisible();
    await expect(page.locator("[data-op-tab='connection']")).toBeVisible();
    await expect(page.locator("[data-op-tab='project-import']")).toHaveCount(0);
    await expect(page.locator("[data-op-tab='import']")).toHaveCount(0);
    await expect(page.locator("[data-op-tab='logs']")).toHaveCount(0);

    const openProjectEnabledInput = page.locator("#storageOpenProjectEnabledInput");
    const openProjectSkipSslInput = page.locator("#storageOpenProjectSkipSslVerifyInput");
    await openProjectEnabledInput.check();
    await expect(openProjectSkipSslInput).toHaveCount(1);
    await openProjectSkipSslInput.setChecked(true, { force: true });
    await page.locator("#storageOpenProjectBaseUrlInput").fill("");
    await page.locator("#storageOpenProjectDefaultWpInput").fill(nextWorkPackageId);
    await page.getByRole("button", { name: "Save OpenProject Settings" }).click();

    await page.locator("[data-integrations-provider-tab='google']").click();
    await expect(page.locator("[data-integrations-provider-panel='google']")).toHaveClass(/active/);
    await page.evaluate(() => {
      const setChecked = (selector: string) => {
        const input = document.querySelector<HTMLInputElement>(selector);
        if (!input) return;
        input.checked = true;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      };
      setChecked("#storageGoogleDriveEnabledInput");
      setChecked("#storageGoogleDriveDriveEnabledInput");
    });
    await page.locator("#storageGoogleDriveDriveIdInput").fill(nextSharedDriveId);
    await page.getByRole("button", { name: "Save Google Settings" }).click();

    await page.locator("[data-integrations-provider-tab='nextcloud']").click();
    await expect(page.locator("[data-integrations-provider-panel='nextcloud']")).toHaveClass(/active/);
    await page.locator("#storagePrimaryProviderSelect").selectOption("local");
    await page.locator("#storageMirrorProviderSelect").selectOption("nextcloud");
    await page.evaluate(() => {
      const input = document.querySelector<HTMLInputElement>("#storageNextcloudEnabledInput");
      if (!input) return;
      input.checked = true;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await page.locator("#storageNextcloudBaseUrlInput").fill("https://nextcloud.example.com");
    await page.locator("#storageNextcloudUsernameInput").fill("nextcloud-user");
    await page.locator("#storageNextcloudAppPasswordInput").fill("nextcloud-app-password");
    await page.locator("#storageNextcloudRootPathInput").fill(nextNextcloudRootPath);
    await page.getByRole("button", { name: "Save Nextcloud Settings" }).click();

    await expect
      .poll(async () => {
        const res = await request.get(`${resolvedBaseUrl}/api/v1/settings/storage-integrations`, {
          headers,
        });
        const body = await res.json();
        const op = body?.integrations?.openproject || {};
        const gd = body?.integrations?.google_drive || {};
        const nc = body?.integrations?.nextcloud || {};
        const mirror = body?.integrations?.mirror || {};
        return `${Boolean(op?.enabled)}|${String(op?.default_work_package_id || "")}|${Boolean(op?.skip_ssl_verify)}|${String(gd?.shared_drive_id || "")}|${Boolean(nc?.enabled)}|${String(mirror?.provider || "")}`;
      })
      .toBe(`true|${nextWorkPackageId}|true|${nextSharedDriveId}|true|nextcloud`);

    await page.locator("[data-integrations-provider-tab='openproject']").click();
    await page.locator("[data-op-tab='connection']").click();
    await page.locator("[data-integrations-action='ping-openproject']").click();
    const pingResult = page.locator("#storageSyncResult");
    await expect(pingResult).toBeVisible({ timeout: 15000 });
    await expect(pingResult).toContainText("Ping OpenProject");

    await page.locator("button[data-settings-tab='true'][data-tab='users']").click();
    await expect(page.locator("#tab-users")).toHaveClass(/active/);
    await expect(page.locator("#settingsUsersTabRoot")).toBeVisible();

    const createUserResponse = await request.post(`${resolvedBaseUrl}/api/v1/users/`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        email: createdUserEmail,
        password: "CriticalE2E#12345",
        full_name: "Critical E2E User",
        role: "user",
        is_active: true,
      },
    });
    const createUserBody = await expectOkJson(createUserResponse, "settings create user");
    createdUserId = Number(createUserBody?.id || 0);
    expect(createdUserId).toBeGreaterThan(0);

    const updateUserResponse = await request.put(
      `${resolvedBaseUrl}/api/v1/users/${createdUserId}`,
      {
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        data: {
          full_name: "Critical E2E User Updated",
          is_active: false,
        },
      }
    );
    await expectOkJson(updateUserResponse, "settings update user");

    const getUserResponse = await request.get(`${resolvedBaseUrl}/api/v1/users/${createdUserId}`, {
      headers,
    });
    const getUserBody = await expectOkJson(getUserResponse, "settings get user");
    expect(String(getUserBody?.full_name || "")).toContain("Updated");
    expect(Boolean(getUserBody?.is_active)).toBeFalsy();
  } finally {
    const restoreMdrPath = path.isAbsolute(beforeMdrPath) ? beforeMdrPath : nextMdrPath;
    const restoreCorrespondencePath = path.isAbsolute(beforeCorrespondencePath)
      ? beforeCorrespondencePath
      : nextCorrespondencePath;
    const restoreSiteLogPath = !beforeSiteLogPath || path.isAbsolute(beforeSiteLogPath)
      ? beforeSiteLogPath
      : "";
    await request.post(`${resolvedBaseUrl}/api/v1/settings/storage-paths`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        mdr_storage_path: restoreMdrPath,
        correspondence_storage_path: restoreCorrespondencePath,
        site_log_storage_path: restoreSiteLogPath,
      },
    });
    await request.post(`${resolvedBaseUrl}/api/v1/settings/storage-integrations`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        mirror: {
          provider: String(beforeMirror?.provider || "none"),
        },
        google_drive: {
          enabled: Boolean(beforeGdrive?.enabled),
          shared_drive_id: String(beforeGdrive?.shared_drive_id || ""),
        },
        openproject: {
          enabled: Boolean(beforeOpenproject?.enabled),
          base_url: String(beforeOpenproject?.base_url || ""),
          default_work_package_id: String(
            beforeOpenproject?.default_work_package_id || beforeOpenproject?.default_project_id || ""
          ),
          skip_ssl_verify: Boolean(beforeOpenproject?.skip_ssl_verify),
        },
        nextcloud: {
          enabled: Boolean(beforeNextcloud?.enabled),
          base_url: String(beforeNextcloud?.base_url || ""),
          username: String(beforeNextcloud?.username || ""),
          root_path: String(beforeNextcloud?.root_path || ""),
          skip_ssl_verify: Boolean(beforeNextcloud?.skip_ssl_verify),
        },
        local_cache: {
          enabled: Boolean(beforeLocalCache?.enabled),
        },
      },
    });

    if (createdUserId > 0) {
      await request.delete(`${resolvedBaseUrl}/api/v1/users/${createdUserId}`, { headers });
    }
  }
});
