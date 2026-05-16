export interface TransmittalMutationHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
}

export interface TransmittalDocumentPayload {
  document_code: string;
  revision: string;
  status: string;
  file_kind?: string;
  remarks?: string;
  electronic_copy: boolean;
  hard_copy: boolean;
}

export interface TransmittalSavePayload {
  project_code: string;
  sender: string;
  receiver: string;
  direction?: string;
  subject?: string;
  notes?: string;
  issue_now?: boolean;
  documents: TransmittalDocumentPayload[];
}

export interface TransmittalMutationsBridge {
  getDetail(transmittalId: string, deps: TransmittalMutationHttpDeps): Promise<Record<string, unknown>>;
  create(payload: TransmittalSavePayload, deps: TransmittalMutationHttpDeps): Promise<Record<string, unknown>>;
  update(
    transmittalId: string,
    payload: TransmittalSavePayload,
    deps: TransmittalMutationHttpDeps
  ): Promise<Record<string, unknown>>;
  issue(transmittalId: string, deps: TransmittalMutationHttpDeps): Promise<Record<string, unknown>>;
  voidItem(
    transmittalId: string,
    reason: string,
    deps: TransmittalMutationHttpDeps
  ): Promise<Record<string, unknown>>;
  previewCover(transmittalId: string, deps: TransmittalMutationHttpDeps): Promise<{ html: string; fileName: string }>;
  downloadCover(transmittalId: string, deps: TransmittalMutationHttpDeps): Promise<Blob>;
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
  deps: TransmittalMutationHttpDeps
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

async function getDetail(transmittalId: string, deps: TransmittalMutationHttpDeps): Promise<Record<string, unknown>> {
  const id = String(transmittalId || "").trim();
  return requestJson(`/api/v1/transmittal/item/${encodeURIComponent(id)}`, undefined, deps);
}

async function create(payload: TransmittalSavePayload, deps: TransmittalMutationHttpDeps): Promise<Record<string, unknown>> {
  return requestJson(
    "/api/v1/transmittal/create",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    deps
  );
}

async function update(
  transmittalId: string,
  payload: TransmittalSavePayload,
  deps: TransmittalMutationHttpDeps
): Promise<Record<string, unknown>> {
  const id = String(transmittalId || "").trim();
  return requestJson(
    `/api/v1/transmittal/item/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    deps
  );
}

async function issue(transmittalId: string, deps: TransmittalMutationHttpDeps): Promise<Record<string, unknown>> {
  const id = String(transmittalId || "").trim();
  return requestJson(
    `/api/v1/transmittal/item/${encodeURIComponent(id)}/issue`,
    { method: "POST" },
    deps
  );
}

async function voidItem(
  transmittalId: string,
  reason: string,
  deps: TransmittalMutationHttpDeps
): Promise<Record<string, unknown>> {
  const id = String(transmittalId || "").trim();
  return requestJson(
    `/api/v1/transmittal/item/${encodeURIComponent(id)}/void`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    },
    deps
  );
}

async function downloadCover(transmittalId: string, deps: TransmittalMutationHttpDeps): Promise<Blob> {
  const id = String(transmittalId || "").trim();
  const response = await deps.fetch(`/api/v1/transmittal/${encodeURIComponent(id)}/download-cover`);
  if (!response.ok) {
    let message = "Download failed";
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    if (detail) message = detail;
    throw new Error(message);
  }
  return response.blob();
}

async function previewCover(
  transmittalId: string,
  deps: TransmittalMutationHttpDeps
): Promise<{ html: string; fileName: string }> {
  const id = String(transmittalId || "").trim();
  const response = await deps.fetch(`/api/v1/transmittal/${encodeURIComponent(id)}/print-preview`);
  if (!response.ok) {
    let message = "Preview failed";
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    if (detail) message = detail;
    throw new Error(message);
  }
  return {
    html: await response.text(),
    fileName: `Transmittal_${id}.html`,
  };
}

export function createTransmittalMutationsBridge(): TransmittalMutationsBridge {
  return {
    getDetail,
    create,
    update,
    issue,
    voidItem,
    previewCover,
    downloadCover,
  };
}
