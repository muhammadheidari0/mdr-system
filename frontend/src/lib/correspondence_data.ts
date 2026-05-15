export interface CorrespondenceHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
}

export interface CorrespondenceListQuery {
  skip: number;
  limit: number;
  search?: string;
  issuing_code?: string;
  category_code?: string;
  tag_id?: string;
  direction?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
}

export interface CorrespondenceDataBridge {
  requestJson(url: string, init: RequestInit | undefined, deps: CorrespondenceHttpDeps): Promise<unknown>;
  loadCatalog(deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
  loadDashboard(deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
  loadList(query: CorrespondenceListQuery, deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
  loadSuggestions(search: string, deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
  listActions(correspondenceId: number, deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
  listAttachments(correspondenceId: number, deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
  listRelations(correspondenceId: number, deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
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

async function requestJson(
  url: string,
  init: RequestInit | undefined,
  deps: CorrespondenceHttpDeps
): Promise<unknown> {
  const response = await deps.fetch(url, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    if (detail) message = detail;
    throw new Error(message);
  }
  return parseJsonSafe(response);
}

async function loadCatalog(deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson("/api/v1/correspondence/catalog", undefined, deps));
}

async function loadDashboard(deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(await requestJson("/api/v1/correspondence/dashboard", undefined, deps));
}

async function loadList(
  query: CorrespondenceListQuery,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams();
  params.set("skip", String(Math.max(0, Number(query.skip) || 0)));
  params.set("limit", String(Math.max(1, Number(query.limit) || 20)));

  const optional = [
    "search",
    "issuing_code",
    "category_code",
    "tag_id",
    "direction",
    "status",
    "date_from",
    "date_to",
  ] as const;
  optional.forEach((key) => {
    const value = String(query[key] || "").trim();
    if (value) params.set(key, value);
  });

  return asRecord(await requestJson(`/api/v1/correspondence/list?${params.toString()}`, undefined, deps));
}

async function loadSuggestions(
  search: string,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams();
  const value = String(search || "").trim();
  if (value) params.set("q", value);
  params.set("limit", "8");
  return asRecord(await requestJson(`/api/v1/correspondence/suggestions?${params.toString()}`, undefined, deps));
}

async function listActions(
  correspondenceId: number,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(correspondenceId) || 0);
  return asRecord(await requestJson(`/api/v1/correspondence/${id}/actions`, undefined, deps));
}

async function listAttachments(
  correspondenceId: number,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(correspondenceId) || 0);
  return asRecord(await requestJson(`/api/v1/correspondence/${id}/attachments`, undefined, deps));
}

async function listRelations(
  correspondenceId: number,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(correspondenceId) || 0);
  return asRecord(await requestJson(`/api/v1/correspondence/${id}/relations`, undefined, deps));
}

export function createCorrespondenceDataBridge(): CorrespondenceDataBridge {
  return {
    requestJson,
    loadCatalog,
    loadDashboard,
    loadList,
    loadSuggestions,
    listActions,
    listAttachments,
    listRelations,
  };
}
