export interface PermitQcHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
}

export interface PermitQcListQuery {
  module_key: string;
  skip?: number;
  limit?: number;
  status_code?: string;
  project_code?: string;
  discipline_code?: string;
  permit_no?: string;
  date_from?: string;
  date_to?: string;
}

export interface PermitQcDataBridge {
  requestJson(url: string, init: RequestInit | undefined, deps: PermitQcHttpDeps): Promise<unknown>;
  catalog(moduleKey: string, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  list(query: PermitQcListQuery, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  create(payload: Record<string, unknown>, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  get(permitId: number, moduleKey: string, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  update(permitId: number, payload: Record<string, unknown>, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  submit(permitId: number, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  resubmit(permitId: number, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  cancel(permitId: number, note: string, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  review(permitId: number, payload: Record<string, unknown>, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  listAttachments(permitId: number, moduleKey: string, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  uploadAttachment(
    permitId: number,
    moduleKey: string,
    formData: FormData,
    deps: PermitQcHttpDeps
  ): Promise<Record<string, unknown>>;
  deleteAttachment(
    permitId: number,
    moduleKey: string,
    attachmentId: number,
    deps: PermitQcHttpDeps
  ): Promise<Record<string, unknown>>;
  timeline(permitId: number, moduleKey: string, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  templates(deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  upsertTemplate(payload: Record<string, unknown>, deps: PermitQcHttpDeps): Promise<Record<string, unknown>>;
  upsertTemplateStation(
    templateId: number,
    payload: Record<string, unknown>,
    deps: PermitQcHttpDeps
  ): Promise<Record<string, unknown>>;
  upsertTemplateCheck(
    templateId: number,
    payload: Record<string, unknown>,
    deps: PermitQcHttpDeps
  ): Promise<Record<string, unknown>>;
  activateTemplate(
    templateId: number,
    payload: Record<string, unknown>,
    deps: PermitQcHttpDeps
  ): Promise<Record<string, unknown>>;
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
  deps: PermitQcHttpDeps
): Promise<unknown> {
  const response = await deps.fetch(url, init);
  if (!response.ok) {
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return parseJsonSafe(response);
}

async function catalog(moduleKey: string, deps: PermitQcHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(`/api/v1/permit-qc/catalog${toQuery({ module_key: moduleKey })}`, undefined, deps)
  );
}

async function list(query: PermitQcListQuery, deps: PermitQcHttpDeps): Promise<Record<string, unknown>> {
  const params: Record<string, unknown> = {
    skip: Math.max(0, Number(query.skip ?? 0) || 0),
    limit: Math.max(1, Number(query.limit ?? 100) || 100),
    ...query,
  };
  return asRecord(await requestJson(`/api/v1/permit-qc/list${toQuery(params)}`, undefined, deps));
}

async function create(payload: Record<string, unknown>, deps: PermitQcHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(
      "/api/v1/permit-qc/create",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function get(permitId: number, moduleKey: string, deps: PermitQcHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  return asRecord(
    await requestJson(`/api/v1/permit-qc/${id}${toQuery({ module_key: moduleKey })}`, undefined, deps)
  );
}

async function update(
  permitId: number,
  payload: Record<string, unknown>,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/${id}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function submit(permitId: number, deps: PermitQcHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  return asRecord(await requestJson(`/api/v1/permit-qc/${id}/submit`, { method: "POST" }, deps));
}

async function resubmit(permitId: number, deps: PermitQcHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  return asRecord(await requestJson(`/api/v1/permit-qc/${id}/resubmit`, { method: "POST" }, deps));
}

async function cancel(permitId: number, note: string, deps: PermitQcHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/${id}/cancel${toQuery({ note })}`,
      { method: "POST" },
      deps
    )
  );
}

async function review(
  permitId: number,
  payload: Record<string, unknown>,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/${id}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function listAttachments(
  permitId: number,
  moduleKey: string,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/${id}/attachments${toQuery({ module_key: moduleKey })}`,
      undefined,
      deps
    )
  );
}

async function uploadAttachment(
  permitId: number,
  moduleKey: string,
  formData: FormData,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  formData.set("module_key", String(moduleKey || "contractor"));
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/${id}/attachments`,
      {
        method: "POST",
        body: formData,
      },
      deps
    )
  );
}

async function deleteAttachment(
  permitId: number,
  moduleKey: string,
  attachmentId: number,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  const aid = Math.max(0, Number(attachmentId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/${id}/attachments${toQuery({
        module_key: moduleKey,
        attachment_id: aid,
      })}`,
      { method: "DELETE" },
      deps
    )
  );
}

async function timeline(
  permitId: number,
  moduleKey: string,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(permitId) || 0);
  return asRecord(
    await requestJson(`/api/v1/permit-qc/${id}/timeline${toQuery({ module_key: moduleKey })}`, undefined, deps)
  );
}

async function templates(deps: PermitQcHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson("/api/v1/permit-qc/templates", undefined, deps));
}

async function upsertTemplate(
  payload: Record<string, unknown>,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(
      "/api/v1/permit-qc/templates/upsert",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function upsertTemplateStation(
  templateId: number,
  payload: Record<string, unknown>,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(templateId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/templates/${id}/stations/upsert`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function upsertTemplateCheck(
  templateId: number,
  payload: Record<string, unknown>,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(templateId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/templates/${id}/checks/upsert`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function activateTemplate(
  templateId: number,
  payload: Record<string, unknown>,
  deps: PermitQcHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(templateId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/permit-qc/templates/${id}/activate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

export function createPermitQcDataBridge(): PermitQcDataBridge {
  return {
    requestJson,
    catalog,
    list,
    create,
    get,
    update,
    submit,
    resubmit,
    cancel,
    review,
    listAttachments,
    uploadAttachment,
    deleteAttachment,
    timeline,
    templates,
    upsertTemplate,
    upsertTemplateStation,
    upsertTemplateCheck,
    activateTemplate,
  };
}
