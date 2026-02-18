export interface CommItemsHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
}

export interface CommItemsListQuery {
  skip?: number;
  limit?: number;
  search?: string;
  module_key?: string;
  tab_key?: string;
  project_code?: string;
  discipline_code?: string;
  item_type?: string;
  status_code?: string;
  priority?: string;
  recipient_org_id?: number;
  assignee_user_id?: number;
  tech_subtype_code?: string;
  overdue_only?: boolean;
  claim_only?: boolean;
  impact_only?: boolean;
  include_non_claim_control?: boolean;
  include_non_impact_control?: boolean;
  has_reference_attachments?: boolean;
  has_response_attachments?: boolean;
  attachment_type?: string;
}

export interface CommItemsDataBridge {
  requestJson(url: string, init: RequestInit | undefined, deps: CommItemsHttpDeps): Promise<unknown>;
  catalog(deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  list(query: CommItemsListQuery, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  create(payload: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  update(itemId: number, payload: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  get(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  transition(itemId: number, payload: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  timeline(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  listComments(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  createComment(itemId: number, payload: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  listAttachments(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  uploadAttachment(itemId: number, formData: FormData, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  deleteAttachment(itemId: number, attachmentId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  listRelations(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  createRelation(itemId: number, payload: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  deleteRelation(itemId: number, relationId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  reportAging(params: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  reportCycleTime(params: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  reportImpactSignals(params: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
  reportClaimCandidates(params: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>>;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

async function parseJsonSafe(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function toQuery(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, rawValue]) => {
    if (rawValue === null || rawValue === undefined) return;
    if (typeof rawValue === "string") {
      const value = rawValue.trim();
      if (!value) return;
      searchParams.set(key, value);
      return;
    }
    if (typeof rawValue === "number") {
      if (!Number.isFinite(rawValue)) return;
      searchParams.set(key, String(rawValue));
      return;
    }
    if (typeof rawValue === "boolean") {
      searchParams.set(key, rawValue ? "true" : "false");
      return;
    }
    searchParams.set(key, String(rawValue));
  });
  const encoded = searchParams.toString();
  return encoded ? `?${encoded}` : "";
}

async function requestJson(
  url: string,
  init: RequestInit | undefined,
  deps: CommItemsHttpDeps
): Promise<unknown> {
  const response = await deps.fetch(url, init);
  if (!response.ok) {
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return parseJsonSafe(response);
}

async function catalog(deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson("/api/v1/comm-items/catalog", undefined, deps));
}

async function list(query: CommItemsListQuery, deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  const params: Record<string, unknown> = {
    skip: Math.max(0, Number(query.skip ?? 0) || 0),
    limit: Math.max(1, Number(query.limit ?? 100) || 100),
    ...query,
  };
  return asRecord(await requestJson(`/api/v1/comm-items/list${toQuery(params)}`, undefined, deps));
}

async function create(payload: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(
      "/api/v1/comm-items/create",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function update(
  itemId: number,
  payload: Record<string, unknown>,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/comm-items/${id}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function get(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(await requestJson(`/api/v1/comm-items/${id}`, undefined, deps));
}

async function transition(
  itemId: number,
  payload: Record<string, unknown>,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/comm-items/${id}/transition`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function timeline(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(await requestJson(`/api/v1/comm-items/${id}/timeline`, undefined, deps));
}

async function listComments(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(await requestJson(`/api/v1/comm-items/${id}/comments`, undefined, deps));
}

async function createComment(
  itemId: number,
  payload: Record<string, unknown>,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/comm-items/${id}/comments`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function listAttachments(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(await requestJson(`/api/v1/comm-items/${id}/attachments`, undefined, deps));
}

async function uploadAttachment(
  itemId: number,
  formData: FormData,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/comm-items/${id}/attachments`,
      {
        method: "POST",
        body: formData,
      },
      deps
    )
  );
}

async function deleteAttachment(
  itemId: number,
  attachmentId: number,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  const aid = Math.max(0, Number(attachmentId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/comm-items/${id}/attachments${toQuery({ attachment_id: aid })}`,
      { method: "DELETE" },
      deps
    )
  );
}

async function listRelations(itemId: number, deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(await requestJson(`/api/v1/comm-items/${id}/relations`, undefined, deps));
}

async function createRelation(
  itemId: number,
  payload: Record<string, unknown>,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/comm-items/${id}/relations`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function deleteRelation(
  itemId: number,
  relationId: number,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(itemId) || 0);
  const rid = Math.max(0, Number(relationId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/comm-items/${id}/relations${toQuery({ relation_id: rid })}`,
      { method: "DELETE" },
      deps
    )
  );
}

async function reportAging(params: Record<string, unknown>, deps: CommItemsHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson(`/api/v1/comm-items/reports/aging${toQuery(params)}`, undefined, deps));
}

async function reportCycleTime(
  params: Record<string, unknown>,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  return asRecord(await requestJson(`/api/v1/comm-items/reports/cycle-time${toQuery(params)}`, undefined, deps));
}

async function reportClaimCandidates(
  params: Record<string, unknown>,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(`/api/v1/comm-items/reports/claim-candidates${toQuery(params)}`, undefined, deps)
  );
}

async function reportImpactSignals(
  params: Record<string, unknown>,
  deps: CommItemsHttpDeps
): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(`/api/v1/comm-items/reports/impact-signals${toQuery(params)}`, undefined, deps)
  );
}

export function createCommItemsDataBridge(): CommItemsDataBridge {
  return {
    requestJson,
    catalog,
    list,
    create,
    update,
    get,
    transition,
    timeline,
    listComments,
    createComment,
    listAttachments,
    uploadAttachment,
    deleteAttachment,
    listRelations,
    createRelation,
    deleteRelation,
    reportAging,
    reportCycleTime,
    reportImpactSignals,
    reportClaimCandidates,
  };
}
