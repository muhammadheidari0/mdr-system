import { expect, test, type APIRequestContext, type APIResponse } from "@playwright/test";

import { apiLoginToken, bearerHeaders, resolveBaseUrl } from "./helpers";

type SeedContext = {
  projectCode: string;
  disciplineCode: string;
  phaseCode: string;
  mdrCode: string;
  packageCode: string;
  blockCode: string;
  levelCode: string;
  issuingCode: string;
  categoryCode: string;
};

function randomCode(size = 6): string {
  return (
    Math.random()
      .toString(36)
      .replace(/[^a-z0-9]/gi, "")
      .toUpperCase()
      .slice(0, size) || "E2E001"
  );
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

async function seedContext(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>
): Promise<SeedContext> {
  const suffix = randomCode(4);
  const projectCode = `E2R${suffix}`;
  const disciplineCode = "GN";
  const phaseCode = "X";
  const mdrCode = "E";
  const packageCode = "00";
  const blockCode = "T";
  const levelCode = "GEN";
  const issuingCode = projectCode;
  const categoryCode = "CO";
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/projects/upsert`, {
      headers: jsonHeaders,
      data: { code: projectCode, project_name: projectCode, name_e: projectCode, is_active: true },
    }),
    "settings projects upsert"
  );
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/disciplines/upsert`, {
      headers: jsonHeaders,
      data: { code: disciplineCode, name_e: "General", name_p: "General" },
    }),
    "settings disciplines upsert"
  );
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/phases/upsert`, {
      headers: jsonHeaders,
      data: { ph_code: phaseCode, name_e: "Phase X", name_p: "Phase X" },
    }),
    "settings phases upsert"
  );
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/mdr-categories/upsert`, {
      headers: jsonHeaders,
      data: { code: mdrCode, name_e: "Engineering", name_p: "Engineering", folder_name: "Engineering", is_active: true },
    }),
    "settings mdr-categories upsert"
  );
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/levels/upsert`, {
      headers: jsonHeaders,
      data: { code: levelCode, name_e: "General", name_p: "General", sort_order: 10 },
    }),
    "settings levels upsert"
  );
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/blocks/upsert`, {
      headers: jsonHeaders,
      data: { project_code: projectCode, code: blockCode, name_e: "Tower", name_p: "Tower", is_active: true },
    }),
    "settings blocks upsert"
  );
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/packages/upsert`, {
      headers: jsonHeaders,
      data: { discipline_code: disciplineCode, package_code: packageCode, name_e: "Pkg 00", name_p: "Pkg 00" },
    }),
    "settings packages upsert"
  );
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/correspondence-issuing/upsert`, {
      headers: jsonHeaders,
      data: { code: issuingCode, name_e: projectCode, name_p: projectCode, project_code: projectCode, is_active: true },
    }),
    "settings correspondence issuing upsert"
  );
  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/settings/correspondence-categories/upsert`, {
      headers: jsonHeaders,
      data: { code: categoryCode, name_e: "Correspondence", name_p: "Correspondence", is_active: true },
    }),
    "settings correspondence category upsert"
  );

  return {
    projectCode,
    disciplineCode,
    phaseCode,
    mdrCode,
    packageCode,
    blockCode,
    levelCode,
    issuingCode,
    categoryCode,
  };
}

async function seedDocument(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>,
  context: SeedContext
): Promise<{ documentId: number; docNumber: string }> {
  const docNumber = `${context.projectCode}-${context.mdrCode}${context.disciplineCode}${randomCode(4)}01-${context.blockCode}${context.levelCode}`;
  const body = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/archive/register-document`, {
      headers,
      form: {
        doc_number: docNumber,
        project_code: context.projectCode,
        mdr_code: context.mdrCode,
        phase: context.phaseCode,
        discipline: context.disciplineCode,
        "package": context.packageCode,
        block: context.blockCode,
        level: context.levelCode,
        subject_e: `Correspondence relation ${randomCode(4)}`,
      },
    }),
    "archive register-document"
  );
  const documentId = Number(body?.document_id || 0);
  expect(documentId, "seed document id").toBeGreaterThan(0);
  return { documentId, docNumber: String(body?.doc_number || docNumber) };
}

async function seedTransmittal(
  request: APIRequestContext,
  baseUrl: string,
  headers: Record<string, string>,
  context: SeedContext,
  docNumber: string
): Promise<string> {
  const body = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/transmittal/create`, {
      headers: { ...headers, "Content-Type": "application/json" },
      data: {
        project_code: context.projectCode,
        sender: "O",
        receiver: "C",
        subject: `Relation traceability ${randomCode(4)}`,
        issue_now: false,
        documents: [
          {
            document_code: docNumber,
            revision: "00",
            status: "IFA",
            electronic_copy: true,
            hard_copy: false,
          },
        ],
      },
    }),
    "transmittal create"
  );
  const transmittalNo = String(body?.transmittal_no || "");
  expect(transmittalNo, "seed transmittal number").not.toEqual("");
  return transmittalNo;
}

test("correspondence relations e2e: link document and transmittal, delete link, verify traceability", async ({
  request,
  baseURL,
}) => {
  test.setTimeout(120_000);
  const baseUrl = resolveBaseUrl(baseURL);
  const token = await apiLoginToken(request, baseUrl);
  const headers = bearerHeaders(token);
  const jsonHeaders = { ...headers, "Content-Type": "application/json" };
  const context = await seedContext(request, baseUrl, headers);
  const document = await seedDocument(request, baseUrl, headers, context);
  const transmittalNo = await seedTransmittal(request, baseUrl, headers, context, document.docNumber);
  const referenceNo = `${context.projectCode}-CO-O-${randomCode(6)}`;

  const createBody = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/correspondence/create`, {
      headers: jsonHeaders,
      data: {
        project_code: context.projectCode,
        issuing_code: context.issuingCode,
        category_code: context.categoryCode,
        discipline_code: context.disciplineCode,
        doc_type: "Correspondence",
        direction: "O",
        reference_no: referenceNo,
        subject: `Relation correspondence ${randomCode(4)}`,
        sender: "DCC",
        recipient: "Engineering",
        status: "Open",
        priority: "Normal",
      },
    }),
    "correspondence create"
  );
  const correspondenceId = Number(createBody?.data?.id || 0);
  expect(correspondenceId, "created correspondence id").toBeGreaterThan(0);

  const openedBody = await expectOkJson(
    await request.get(`${baseUrl}/api/v1/correspondence/list?search=${encodeURIComponent(referenceNo)}`, {
      headers,
    }),
    "correspondence open by search"
  );
  expect(
    (openedBody?.data || []).some((item: any) => Number(item?.id || 0) === correspondenceId),
    "created correspondence appears in list/search"
  ).toBeTruthy();

  await expectOkJson(
    await request.post(`${baseUrl}/api/v1/correspondence/${correspondenceId}/relations`, {
      headers: jsonHeaders,
      data: { target_entity_type: "document", target_code: document.docNumber, relation_type: "references" },
    }),
    "correspondence link document"
  );
  const transmittalRelation = await expectOkJson(
    await request.post(`${baseUrl}/api/v1/correspondence/${correspondenceId}/relations`, {
      headers: jsonHeaders,
      data: { target_entity_type: "transmittal", target_code: transmittalNo, relation_type: "related" },
    }),
    "correspondence link transmittal"
  );
  const transmittalRelationId = String(transmittalRelation?.data?.id || "");
  expect(transmittalRelationId).toMatch(/^external:/);

  const relationsBody = await expectOkJson(
    await request.get(`${baseUrl}/api/v1/correspondence/${correspondenceId}/relations`, { headers }),
    "correspondence list relations"
  );
  const relationKeys = new Set(
    (relationsBody?.data || []).map((item: any) => `${String(item?.target_entity_type || "")}:${String(item?.target_code || "")}`)
  );
  expect(relationKeys.has(`document:${document.docNumber}`)).toBeTruthy();
  expect(relationKeys.has(`transmittal:${transmittalNo}`)).toBeTruthy();

  const transmittalDetail = await expectOkJson(
    await request.get(`${baseUrl}/api/v1/transmittal/item/${encodeURIComponent(transmittalNo)}`, { headers }),
    "transmittal detail reciprocal relations"
  );
  expect(
    (transmittalDetail?.correspondence_relations || []).some((item: any) => item?.reference_no === referenceNo),
    "transmittal detail shows reciprocal correspondence link"
  ).toBeTruthy();

  await expectOkJson(
    await request.delete(
      `${baseUrl}/api/v1/correspondence/${correspondenceId}/relations/${encodeURIComponent(transmittalRelationId)}`,
      { headers }
    ),
    "correspondence delete transmittal relation"
  );
  const relationsAfterDelete = await expectOkJson(
    await request.get(`${baseUrl}/api/v1/correspondence/${correspondenceId}/relations`, { headers }),
    "correspondence list relations after delete"
  );
  const directTransmittalRelations = (relationsAfterDelete?.data || []).filter(
    (item: any) => item?.target_entity_type === "transmittal" && !item?.inferred
  );
  expect(directTransmittalRelations).toHaveLength(0);

  const documentDetail = await expectOkJson(
    await request.get(`${baseUrl}/api/v1/archive/documents/${document.documentId}`, { headers }),
    "document detail relation trace"
  );
  expect(
    ((documentDetail?.relations || {}).outgoing || []).some(
      (item: any) => item?.target_entity_type === "correspondence" && item?.target_code === referenceNo
    ),
    "document detail still shows correspondence relation"
  ).toBeTruthy();
});
