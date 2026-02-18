export interface SiteLogsHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
}

export interface SiteLogsListQuery {
  skip?: number;
  limit?: number;
  module_key?: string;
  tab_key?: string;
  search?: string;
  project_code?: string;
  discipline_code?: string;
  log_type?: string;
  status_code?: string;
  log_date_from?: string;
  log_date_to?: string;
}

export interface SiteLogsDataBridge {
  requestJson(url: string, init: RequestInit | undefined, deps: SiteLogsHttpDeps): Promise<unknown>;
  catalog(deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  list(query: SiteLogsListQuery, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  create(payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  update(logId: number, payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  get(logId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  submit(logId: number, payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  verify(logId: number, payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  timeline(logId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  listComments(logId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  createComment(logId: number, payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  listAttachments(logId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  uploadAttachment(logId: number, formData: FormData, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  deleteAttachment(logId: number, attachmentId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  reportVolume(params: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  reportVariance(params: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
  reportProgress(params: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>>;
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

async function requestJson(url: string, init: RequestInit | undefined, deps: SiteLogsHttpDeps): Promise<unknown> {
  const response = await deps.fetch(url, init);
  if (!response.ok) {
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return parseJsonSafe(response);
}

async function catalog(deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson("/api/v1/site-logs/catalog", undefined, deps));
}

async function list(query: SiteLogsListQuery, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const params: Record<string, unknown> = {
    skip: Math.max(0, Number(query.skip ?? 0) || 0),
    limit: Math.max(1, Number(query.limit ?? 100) || 100),
    ...query,
  };
  return asRecord(await requestJson(`/api/v1/site-logs/list${toQuery(params)}`, undefined, deps));
}

async function create(payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(
      "/api/v1/site-logs/create",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function update(logId: number, payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/site-logs/${id}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function get(logId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(await requestJson(`/api/v1/site-logs/${id}`, undefined, deps));
}

async function submit(logId: number, payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/site-logs/${id}/submit`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function verify(logId: number, payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/site-logs/${id}/verify`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function timeline(logId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(await requestJson(`/api/v1/site-logs/${id}/timeline`, undefined, deps));
}

async function listComments(logId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(await requestJson(`/api/v1/site-logs/${id}/comments`, undefined, deps));
}

async function createComment(logId: number, payload: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/site-logs/${id}/comments`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

async function listAttachments(logId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(await requestJson(`/api/v1/site-logs/${id}/attachments`, undefined, deps));
}

async function uploadAttachment(logId: number, formData: FormData, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  return asRecord(
    await requestJson(
      `/api/v1/site-logs/${id}/attachments`,
      {
        method: "POST",
        body: formData,
      },
      deps
    )
  );
}

async function deleteAttachment(logId: number, attachmentId: number, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(logId) || 0);
  const aid = Math.max(0, Number(attachmentId) || 0);
  return asRecord(await requestJson(`/api/v1/site-logs/${id}/attachments${toQuery({ attachment_id: aid })}`, { method: "DELETE" }, deps));
}

async function reportVolume(params: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson(`/api/v1/site-logs/reports/volume${toQuery(params)}`, undefined, deps));
}

async function reportVariance(params: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson(`/api/v1/site-logs/reports/variance${toQuery(params)}`, undefined, deps));
}

async function reportProgress(params: Record<string, unknown>, deps: SiteLogsHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson(`/api/v1/site-logs/reports/progress${toQuery(params)}`, undefined, deps));
}

export function createSiteLogsDataBridge(): SiteLogsDataBridge {
  return {
    requestJson,
    catalog,
    list,
    create,
    update,
    get,
    submit,
    verify,
    timeline,
    listComments,
    createComment,
    listAttachments,
    uploadAttachment,
    deleteAttachment,
    reportVolume,
    reportVariance,
    reportProgress,
  };
}
