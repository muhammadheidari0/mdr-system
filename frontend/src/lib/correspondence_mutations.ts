export interface CorrespondenceHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
}

export interface CorrespondenceActionPayload {
  action_type?: string;
  title?: string | null;
  description?: string | null;
  due_date?: string | null;
  status?: string;
  is_closed?: boolean;
}

export interface CorrespondenceSavePayload {
  project_code?: string | null;
  issuing_code?: string | null;
  category_code?: string | null;
  discipline_code?: string | null;
  doc_type?: string | null;
  direction?: string;
  reference_no?: string | null;
  subject?: string;
  sender?: string | null;
  recipient?: string | null;
  corr_date?: string | null;
  due_date?: string | null;
  status?: string;
  priority?: string;
  notes?: string | null;
}

export interface CorrespondenceAttachmentDownloadResult {
  blob: Blob;
  fileName: string | null;
}

export interface CorrespondenceMutationsBridge {
  saveCorrespondence(
    correspondenceId: number,
    payload: CorrespondenceSavePayload,
    deps: CorrespondenceHttpDeps
  ): Promise<Record<string, unknown>>;
  upsertAction(
    correspondenceId: number,
    actionId: number,
    payload: CorrespondenceActionPayload,
    deps: CorrespondenceHttpDeps
  ): Promise<Record<string, unknown>>;
  toggleActionClosed(
    actionId: number,
    checked: boolean,
    deps: CorrespondenceHttpDeps
  ): Promise<Record<string, unknown>>;
  deleteAction(actionId: number, deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
  uploadAttachment(
    correspondenceId: number,
    formData: FormData,
    deps: CorrespondenceHttpDeps
  ): Promise<Record<string, unknown>>;
  downloadAttachment(
    attachmentId: number,
    deps: CorrespondenceHttpDeps
  ): Promise<CorrespondenceAttachmentDownloadResult>;
  deleteAttachment(attachmentId: number, deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>>;
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
): Promise<Record<string, unknown>> {
  const response = await deps.fetch(url, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    if (detail) message = detail;
    throw new Error(message);
  }
  return asRecord(await parseJsonSafe(response));
}

function parseFileNameFromHeaders(headers: Headers): string | null {
  const disposition =
    headers.get("Content-Disposition") || headers.get("content-disposition") || "";
  const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?/i);
  if (!match) return null;
  const raw = match[1] || match[2] || "";
  if (!raw) return null;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

async function saveCorrespondence(
  correspondenceId: number,
  payload: CorrespondenceSavePayload,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(correspondenceId) || 0);
  const url = id > 0 ? `/api/v1/correspondence/${id}` : "/api/v1/correspondence/create";
  const method = id > 0 ? "PUT" : "POST";
  return requestJson(
    url,
    {
      method,
      body: JSON.stringify(payload),
    },
    deps
  );
}

async function upsertAction(
  correspondenceId: number,
  actionId: number,
  payload: CorrespondenceActionPayload,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const corrId = Math.max(0, Number(correspondenceId) || 0);
  const aid = Math.max(0, Number(actionId) || 0);
  const url = aid > 0 ? `/api/v1/correspondence/actions/${aid}` : `/api/v1/correspondence/${corrId}/actions`;
  const method = aid > 0 ? "PUT" : "POST";
  return requestJson(
    url,
    {
      method,
      body: JSON.stringify(payload),
    },
    deps
  );
}

async function toggleActionClosed(
  actionId: number,
  checked: boolean,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(actionId) || 0);
  return requestJson(
    `/api/v1/correspondence/actions/${id}`,
    {
      method: "PUT",
      body: JSON.stringify({
        is_closed: Boolean(checked),
        status: checked ? "Closed" : "Open",
      }),
    },
    deps
  );
}

async function deleteAction(actionId: number, deps: CorrespondenceHttpDeps): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(actionId) || 0);
  return requestJson(`/api/v1/correspondence/actions/${id}`, { method: "DELETE" }, deps);
}

async function uploadAttachment(
  correspondenceId: number,
  formData: FormData,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(correspondenceId) || 0);
  return requestJson(
    `/api/v1/correspondence/${id}/attachments/upload`,
    {
      method: "POST",
      body: formData,
    },
    deps
  );
}

async function downloadAttachment(
  attachmentId: number,
  deps: CorrespondenceHttpDeps
): Promise<CorrespondenceAttachmentDownloadResult> {
  const id = Math.max(0, Number(attachmentId) || 0);
  const response = await deps.fetch(`/api/v1/correspondence/attachments/${id}/download`);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    if (detail) message = detail;
    throw new Error(message);
  }
  const fileName = parseFileNameFromHeaders(response.headers);
  const blob = await response.blob();
  return { blob, fileName };
}

async function deleteAttachment(
  attachmentId: number,
  deps: CorrespondenceHttpDeps
): Promise<Record<string, unknown>> {
  const id = Math.max(0, Number(attachmentId) || 0);
  return requestJson(`/api/v1/correspondence/attachments/${id}`, { method: "DELETE" }, deps);
}

export function createCorrespondenceMutationsBridge(): CorrespondenceMutationsBridge {
  return {
    saveCorrespondence,
    upsertAction,
    toggleActionClosed,
    deleteAction,
    uploadAttachment,
    downloadAttachment,
    deleteAttachment,
  };
}
