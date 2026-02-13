import { Buffer } from "node:buffer";

import { expect, test, type APIResponse } from "@playwright/test";

import { apiLoginToken, bearerHeaders, resolveBaseUrl, seedAuthToken } from "./helpers";

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

test("critical e2e: login/auth and EDMS navigation", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  await seedAuthToken(page, request, resolvedBaseUrl);

  await page.goto("/");
  await expect(page.locator("#view-dashboard")).toHaveClass(/active/);

  await page.locator("#nav-edms").click();
  await expect(page.locator("#view-edms")).toHaveClass(/active/);

  await page.locator("#edms-tab-archive").click();
  await expect(page.locator("#view-archive")).toHaveClass(/active/);

  await page.locator("#edms-tab-transmittal").click();
  await expect(page.locator("#view-transmittal")).toHaveClass(/active/);

  await page.locator("#edms-tab-correspondence").click();
  await expect(page.locator("#view-correspondence")).toHaveClass(/active/);
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
  await page.locator("#nav-edms").click();
  await page.locator("#edms-tab-transmittal").click();
  await page.locator("#view-transmittal [data-tr2-action='refresh-list']").click();

  const issueButton = page.locator(
    `#view-transmittal button[data-tr2-action='issue-item'][data-id='${transmittalId}']`
  );
  await expect(issueButton).toBeVisible({ timeout: 15000 });
  await issueButton.click();

  const row = page.locator("#tr2-list-body tr", { hasText: transmittalId }).first();
  await expect(row).toContainText(/issued/i);

  const voidReason = `Critical E2E void ${Date.now()}`;
  page.once("dialog", async (dialog) => {
    await dialog.accept(voidReason);
  });
  await page
    .locator(`#view-transmittal button[data-tr2-action='void-item'][data-id='${transmittalId}']`)
    .click();
  await expect(row).toContainText(/void/i);

  const detailResponse = await request.get(
    `${resolvedBaseUrl}/api/v1/transmittal/item/${encodeURIComponent(transmittalId)}`,
    { headers }
  );
  const detailBody = await expectOkJson(detailResponse, "transmittal detail");
  expect(String(detailBody?.status || "").toLowerCase()).toBe("void");
  expect(String(detailBody?.void_reason || "")).toContain(voidReason);
});

test("critical e2e: correspondence CRUD with attachments", async ({ page, request, baseURL }) => {
  const resolvedBaseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, resolvedBaseUrl);
  const headers = bearerHeaders(token);

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
    },
  });
  const createBody = await expectOkJson(createResponse, "correspondence create");
  expect(createBody?.ok).toBeTruthy();
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
    await page.locator("#nav-edms").click();
    await page.locator("#edms-tab-correspondence").click();
    await page.locator("#view-correspondence [data-corr-action='refresh']").click();
    await page.locator("#corrSearchInput").fill(updatedSubject);
    await page.keyboard.press("Enter");
    await expect(page.locator("#corrTableBody tr", { hasText: updatedSubject }).first()).toBeVisible({
      timeout: 15000,
    });
  } finally {
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
});

test("critical e2e: settings critical actions", async ({ page, request, baseURL }) => {
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

  const nextMdrPath = `./files/e2e_technical_${Date.now()}`;
  const nextCorrespondencePath = `./files/e2e_correspondence_${Date.now()}`;

  let createdUserId = 0;
  const createdUserEmail = `critical.e2e.${Date.now()}@mdr.local`;

  try {
    await seedAuthToken(page, request, resolvedBaseUrl);
    await page.goto("/");
    await page.locator("#nav-settings").click();
    await expect(page.locator("#view-settings")).toHaveClass(/active/);

    await page.locator("#mdrStoragePathInput").fill(nextMdrPath);
    await page.locator("#correspondenceStoragePathInput").fill(nextCorrespondencePath);
    await page.locator("[data-general-action='save-storage-paths']").click();

    await expect
      .poll(async () => {
        const res = await request.get(`${resolvedBaseUrl}/api/v1/settings/storage-paths`, { headers });
        const body = await res.json();
        return `${body?.mdr_storage_path || ""}|${body?.correspondence_storage_path || ""}`;
      })
      .toBe(`${nextMdrPath}|${nextCorrespondencePath}`);

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
    await request.post(`${resolvedBaseUrl}/api/v1/settings/storage-paths`, {
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      data: {
        mdr_storage_path: beforeMdrPath,
        correspondence_storage_path: beforeCorrespondencePath,
      },
    });

    if (createdUserId > 0) {
      await request.delete(`${resolvedBaseUrl}/api/v1/users/${createdUserId}`, { headers });
    }
  }
});

