import { Buffer } from "node:buffer";
import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext, type APIResponse, type Page } from "@playwright/test";

import { apiLoginToken, bearerHeaders, navigateToView, resolveBaseUrl, seedAuthToken } from "./helpers";

type ArchiveSeedContext = {
  projectCode: string;
  disciplineCode: string;
  phaseCode: string;
  packageCode: string;
  blockCode: string;
  levelCode: string;
  mdrCode: string;
};

type SeededDocument = {
  documentId: number;
  docNumber: string;
  fileId: number;
};

function randomCode(size = 6): string {
  return Math.random().toString(36).replace(/[^a-z0-9]/gi, "").toUpperCase().slice(0, size) || "E2E001";
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

async function resolveArchiveSeedContext(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>
): Promise<ArchiveSeedContext> {
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };
  const projectCode = "E2E";
  const disciplineCode = "GN";
  const phaseCode = "X";
  const packageCode = "00";
  const blockCode = "T";
  const levelCode = "GEN";
  const mdrCode = "E";

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/projects/upsert`, {
      headers: jsonHeaders,
      data: {
        code: projectCode,
        project_name: "E2E",
        name_e: "E2E",
        is_active: true,
      },
    }),
    "settings projects upsert (e2e)"
  );

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/disciplines/upsert`, {
      headers: jsonHeaders,
      data: {
        code: disciplineCode,
        name_e: "General",
        name_p: "General",
      },
    }),
    "settings disciplines upsert (e2e)"
  );

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/phases/upsert`, {
      headers: jsonHeaders,
      data: {
        ph_code: phaseCode,
        name_e: "Phase X",
        name_p: "Phase X",
      },
    }),
    "settings phases upsert (e2e)"
  );

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/mdr-categories/upsert`, {
      headers: jsonHeaders,
      data: {
        code: mdrCode,
        name_e: "Engineering",
        name_p: "Engineering",
        folder_name: "Engineering",
        is_active: true,
      },
    }),
    "settings mdr-categories upsert (e2e)"
  );

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/levels/upsert`, {
      headers: jsonHeaders,
      data: {
        code: levelCode,
        name_e: "General",
        name_p: "General",
        sort_order: 10,
      },
    }),
    "settings levels upsert (e2e)"
  );

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/blocks/upsert`, {
      headers: jsonHeaders,
      data: {
        project_code: projectCode,
        code: blockCode,
        name_e: "Tower",
        name_p: "Tower",
        is_active: true,
      },
    }),
    "settings blocks upsert (e2e)"
  );

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/packages/upsert`, {
      headers: jsonHeaders,
      data: {
        discipline_code: disciplineCode,
        package_code: packageCode,
        name_e: "Pkg 00",
        name_p: "Pkg 00",
      },
    }),
    "settings packages upsert (e2e)"
  );

  return {
    projectCode,
    disciplineCode,
    phaseCode,
    packageCode,
    blockCode,
    levelCode,
    mdrCode,
  };
}

async function seedDocumentWithPdf(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>,
  context: ArchiveSeedContext,
  label: string
): Promise<SeededDocument> {
  const random = randomCode(5);
  const compactPackage = context.packageCode.replace(/[^A-Z0-9]/g, "").slice(0, 4) || "00";
  const docNumber = `${context.projectCode}-${context.mdrCode}${context.disciplineCode}${compactPackage}${random}-${context.blockCode}${context.levelCode}`;
  const subject = `${label}-${Date.now()}-${randomCode(4)}`;

  const registerBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/archive/register-document`, {
      headers,
      form: {
        doc_number: docNumber,
        project_code: context.projectCode,
        mdr_code: context.mdrCode,
        phase: context.phaseCode,
        discipline: context.disciplineCode,
        package: context.packageCode,
        block: context.blockCode,
        level: context.levelCode,
        subject_e: subject,
      },
    }),
    "archive register-document"
  );
  const documentId = Number(registerBody?.document_id || 0);
  expect(documentId, "seed document id").toBeGreaterThan(0);

  const uploadBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/archive/upload`, {
      headers,
      multipart: {
        document_id: String(documentId),
        revision: "00",
        status: "IFA",
        file_kind: "pdf",
        file: {
          name: `${label.toLowerCase()}-${random}.pdf`,
          mimeType: "application/pdf",
          buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", "utf8"),
        },
      },
    }),
    "archive upload"
  );
  const fileId = Number(uploadBody?.file_id || 0);
  expect(fileId, "seed uploaded file id").toBeGreaterThan(0);

  return { documentId, docNumber, fileId };
}

async function ensureStoragePathsForE2E(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>
): Promise<void> {
  const baseAllowedRoot = path.resolve(process.cwd(), "archive_storage");
  const technicalPath = path.join(baseAllowedRoot, "e2e_mdr");
  const correspondencePath = path.join(baseAllowedRoot, "e2e_corr");
  mkdirSync(technicalPath, { recursive: true });
  mkdirSync(correspondencePath, { recursive: true });

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/storage-paths`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        mdr_storage_path: technicalPath,
        correspondence_storage_path: correspondencePath,
      },
    }),
    "settings storage paths upsert for e2e"
  );
}

async function gotoArchive(page: Page): Promise<void> {
  await navigateToView(page, "view-archive", '[data-nav-target="view-edms"]');
  await expect(page.locator("#view-archive")).toBeVisible({ timeout: 20_000 });
}

async function searchArchiveByDocNumber(page: Page, docNumber: string): Promise<void> {
  const searchInput = page.locator("#archiveSearchInput");
  await searchInput.fill(docNumber);
  await page.waitForTimeout(850);
}

async function archiveRow(page: Page, docNumber: string) {
  return page.locator("#archiveTableBody tr", { hasText: docNumber }).first();
}

async function openArchiveRowMenu(page: Page, docNumber: string) {
  await searchArchiveByDocNumber(page, docNumber);
  const row = await archiveRow(page, docNumber);
  await expect(row).toBeVisible({ timeout: 20_000 });
  const trigger = row.locator('[data-archive-action="toggle-row-menu"]');
  await trigger.click();
  await expect(row.locator(".archive-row-menu.is-open")).toBeVisible();
  return row;
}

async function openDetailByArchiveRowMenu(page: Page, docNumber: string, mode: "open" | "edit"): Promise<void> {
  await openArchiveRowMenu(page, docNumber);
  const action = mode === "edit" ? "edit-detail" : "open-detail";
  await page.locator(`.archive-row-menu.is-open [data-archive-action="${action}"]`).first().click({ force: true });
  await expect(page.locator("#view-document-detail")).toBeVisible();
  await expect(page.locator("#docDetailDocNumber")).toContainText(docNumber);
}

async function expectTransmittalPrefill(page: Page, docNumber: string): Promise<void> {
  await expect(page.locator("#view-transmittal")).toBeVisible();
  await expect(page.locator("#tr2-create-mode")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("#tr2-docs-body")).toContainText(docNumber);
}

test("document detail e2e: metadata, preview, comments, relations, tags, send and delete", async ({
  page,
  request,
  baseURL,
}) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  await ensureStoragePathsForE2E(request, resolvedBaseUrl, headers);
  const seedContext = await resolveArchiveSeedContext(request, resolvedBaseUrl, headers);
  const mainDoc = await seedDocumentWithPdf(request, resolvedBaseUrl, headers, seedContext, "DocDetailMain");
  const targetDoc = await seedDocumentWithPdf(request, resolvedBaseUrl, headers, seedContext, "DocDetailTarget");

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await gotoArchive(page);

  await openDetailByArchiveRowMenu(page, mainDoc.docNumber, "open");

  await page.locator('[data-doc-detail-action="edit-toggle"]').click();
  await expect(page.locator('[data-doc-detail-action="save-metadata"]')).toBeVisible();
  const updatedSubject = `E2E Updated Subject ${Date.now()}`;
  await page.locator("#docDetailField_subject").fill(updatedSubject);
  await page.locator('[data-doc-detail-action="save-metadata"]').click();
  await expect(page.locator("#docDetailPanelMetadata")).toContainText(updatedSubject);

  const detailAfterUpdate = await expectOkJson(
    await request.get(`${resolvedBaseUrl}/api/v1/archive/documents/${mainDoc.documentId}`, { headers }),
    "document detail after metadata update"
  );
  expect(String(detailAfterUpdate?.document?.subject || "")).toContain(updatedSubject);

  await page.locator('[data-doc-detail-tab="preview"]').click();
  const previewFrame = page.locator("#docDetailPanelPreview iframe.doc-preview-frame");
  await expect(previewFrame).toBeVisible();
  await expect(previewFrame).toHaveAttribute(
    "src",
    new RegExp(`/api/v1/archive/documents/${mainDoc.documentId}/preview`)
  );

  await page.locator('[data-doc-detail-tab="comments"]').click();
  const commentText = `E2E comment ${Date.now()}`;
  await page.locator("#docDetailCommentInput").fill(commentText);
  await page.locator('[data-doc-detail-action="add-comment"]').click();
  await expect(page.locator("#docDetailPanelComments")).toContainText(commentText);

  const replyText = `E2E reply ${Date.now()}`;
  page.once("dialog", async (dialog) => {
    await dialog.accept(replyText);
  });
  await page.locator('[data-doc-detail-action="reply-comment"]').first().click();
  await expect(page.locator("#docDetailPanelComments")).toContainText(replyText);

  const editedText = `E2E comment edited ${Date.now()}`;
  page.once("dialog", async (dialog) => {
    await dialog.accept(editedText);
  });
  await page.locator('[data-doc-detail-action="edit-comment"]').first().click();
  await expect(page.locator("#docDetailPanelComments")).toContainText(editedText);

  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.locator('[data-doc-detail-action="delete-comment"]').first().click();
  await expect(page.locator("#docDetailPanelComments .doc-comment-body.is-deleted").first()).toBeVisible();

  await page.locator('[data-doc-detail-tab="relations"]').click();
  await page.locator("#docDetailRelationTarget").fill(String(targetDoc.documentId));
  await page.locator('[data-doc-detail-action="add-relation"]').click();
  await expect(page.locator("#docDetailPanelRelations")).toContainText(targetDoc.docNumber);

  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.locator('[data-doc-detail-action="remove-relation"]').first().click();
  await expect(page.locator("#docDetailPanelRelations")).not.toContainText(targetDoc.docNumber);

  const tagName = `e2e-tag-${randomCode(4).toLowerCase()}`;
  await page.locator("#docDetailTagInput").fill(tagName);
  await page.locator('[data-doc-detail-action="add-tag"]').click();
  await expect(page.locator("#docDetailTags .doc-tag-chip", { hasText: tagName })).toBeVisible();
  await page.locator("#docDetailTags [data-doc-detail-action='remove-tag']").first().click();
  await expect(page.locator("#docDetailTags .doc-tag-chip", { hasText: tagName })).toHaveCount(0);

  await page.locator('[data-doc-detail-action="send-transmittal"]').click();
  await expectTransmittalPrefill(page, mainDoc.docNumber);

  await page.evaluate(async (documentId) => {
    if (typeof (window as any).navigateToDocumentDetail === "function") {
      await (window as any).navigateToDocumentDetail(documentId);
    }
  }, mainDoc.documentId);
  await expect(page.locator("#view-document-detail")).toBeVisible();

  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.locator('[data-doc-detail-action="delete-document"]').click();
  await expect(page.locator("#docDetailDeletedBanner")).toBeVisible();

  await page.locator('[data-doc-detail-action="go-back"]').click();
  await expect(page.locator("#view-archive")).toBeVisible();
  await searchArchiveByDocNumber(page, mainDoc.docNumber);
  await expect(page.locator("#archiveTableBody tr", { hasText: mainDoc.docNumber })).toHaveCount(0);
});

test("archive row menu e2e: open, edit, send transmittal, delete", async ({
  page,
  request,
  baseURL,
}) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);
  await ensureStoragePathsForE2E(request, resolvedBaseUrl, headers);
  const seedContext = await resolveArchiveSeedContext(request, resolvedBaseUrl, headers);
  const rowDoc = await seedDocumentWithPdf(request, resolvedBaseUrl, headers, seedContext, "DocDetailRowMenu");

  await seedAuthToken(page, request, resolvedBaseUrl);
  await page.goto("/");
  await gotoArchive(page);

  await openDetailByArchiveRowMenu(page, rowDoc.docNumber, "open");
  await expect(page.locator('[data-doc-detail-action="save-metadata"]')).toHaveCount(0);
  await page.locator('[data-doc-detail-action="go-back"]').click();
  await expect(page.locator("#view-archive")).toBeVisible();

  await openDetailByArchiveRowMenu(page, rowDoc.docNumber, "edit");
  await expect(page.locator('[data-doc-detail-action="save-metadata"]')).toBeVisible();
  await page.locator('[data-doc-detail-action="cancel-edit"]').click();
  await page.locator('[data-doc-detail-action="go-back"]').click();
  await expect(page.locator("#view-archive")).toBeVisible();

  await openArchiveRowMenu(page, rowDoc.docNumber);
  await page
    .locator(".archive-row-menu.is-open [data-archive-action='send-transmittal']")
    .first()
    .click({ force: true });
  await expectTransmittalPrefill(page, rowDoc.docNumber);

  await gotoArchive(page);
  await openArchiveRowMenu(page, rowDoc.docNumber);
  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page
    .locator(".archive-row-menu.is-open [data-archive-action='delete-document']")
    .first()
    .click({ force: true });
  await searchArchiveByDocNumber(page, rowDoc.docNumber);
  await expect(page.locator("#archiveTableBody tr", { hasText: rowDoc.docNumber })).toHaveCount(0);
});
