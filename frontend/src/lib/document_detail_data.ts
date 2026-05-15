// @ts-nocheck
export async function requestJson(url: string, init: RequestInit = {}) {
  const fetchFn = (window as any).fetchWithAuth || window.fetch.bind(window);
  const response = await fetchFn(url, init);
  let payload: any = null;
  try {
    payload = await response.json();
  } catch (_) {
    payload = null;
  }
  if (!response.ok) {
    const message = String(payload?.detail || payload?.message || `Request failed (${response.status})`).trim();
    throw new Error(message || `Request failed (${response.status})`);
  }
  return payload;
}

export function documentPreviewUrl(documentId: number): string {
  return `/api/v1/archive/documents/${Number(documentId || 0)}/preview`;
}

export function archiveDownloadUrl(fileId: number): string {
  return `/api/v1/archive/download/${Number(fileId || 0)}`;
}

export async function requestBlob(url: string, init: RequestInit = {}) {
  const fetchFn = (window as any).fetchWithAuth || window.fetch.bind(window);
  const response = await fetchFn(url, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = String(payload?.detail || payload?.message || message).trim();
    } catch (_) {}
    throw new Error(message);
  }
  return response.blob();
}

export async function loadDocumentDetail(documentId: number) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}`);
}

export async function updateDocumentMetadata(documentId: number, payload: Record<string, unknown>) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export async function loadArchiveFormData() {
  return requestJson("/api/v1/archive/form-data");
}

export async function previewDocumentReclassification(documentId: number, payload: Record<string, unknown>) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/reclassify/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export async function reclassifyDocument(documentId: number, payload: Record<string, unknown>) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/reclassify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export async function replaceArchiveFile(fileId: number, file: File, status = "") {
  const form = new FormData();
  form.append("file", file);
  if (String(status || "").trim()) {
    form.append("status", String(status || "").trim());
  }
  return requestJson(`/api/v1/archive/files/${Number(fileId || 0)}/replace`, {
    method: "POST",
    body: form,
  });
}

export async function addArchiveRevisionFile(revisionId: number, file: File, fileKind = "pdf", status = "") {
  const form = new FormData();
  form.append("file", file);
  form.append("file_kind", String(fileKind || "pdf").trim() || "pdf");
  if (String(status || "").trim()) {
    form.append("status", String(status || "").trim());
  }
  return requestJson(`/api/v1/archive/revisions/${Number(revisionId || 0)}/files`, {
    method: "POST",
    body: form,
  });
}

export async function loadArchiveFilePublicShare(fileId: number) {
  return requestJson(`/api/v1/archive/files/${Number(fileId || 0)}/public-share`);
}

export async function createArchiveFilePublicShare(fileId: number, payload: Record<string, unknown> = {}) {
  return requestJson(`/api/v1/archive/files/${Number(fileId || 0)}/public-share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export async function revokeArchiveFilePublicShare(fileId: number) {
  return requestJson(`/api/v1/archive/files/${Number(fileId || 0)}/public-share`, {
    method: "DELETE",
  });
}

export async function fetchDocumentPreviewBlob(documentId: number) {
  return requestBlob(documentPreviewUrl(documentId));
}

export async function fetchArchiveFileBlob(fileId: number) {
  return requestBlob(archiveDownloadUrl(fileId));
}

export async function deleteDocument(documentId: number) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}`, {
    method: "DELETE",
  });
}

export async function loadDocumentActivity(documentId: number, skip = 0, limit = 50) {
  const qs = new URLSearchParams({
    skip: String(Math.max(0, Number(skip || 0))),
    limit: String(Math.max(1, Number(limit || 50))),
  });
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/activity?${qs.toString()}`);
}

export async function loadDocumentComments(documentId: number) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/comments`);
}

export async function createDocumentComment(documentId: number, body: string, parentId: number | null = null) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      body: String(body || ""),
      parent_id: parentId ?? null,
    }),
  });
}

export async function updateDocumentComment(documentId: number, commentId: number, body: string) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/comments/${Number(commentId || 0)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body: String(body || "") }),
  });
}

export async function deleteDocumentComment(documentId: number, commentId: number) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/comments/${Number(commentId || 0)}`, {
    method: "DELETE",
  });
}

export async function loadDocumentTransmittals(documentId: number, skip = 0, limit = 20) {
  const qs = new URLSearchParams({
    skip: String(Math.max(0, Number(skip || 0))),
    limit: String(Math.max(1, Number(limit || 20))),
  });
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/transmittals?${qs.toString()}`);
}

export async function loadDocumentRelations(documentId: number) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/relations`);
}

export async function createDocumentRelation(
  documentId: number,
  targetCode: string,
  relationType = "related",
  notes = "",
  targetEntityType = "document",
) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/relations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target_entity_type: String(targetEntityType || "document"),
      target_code: String(targetCode || "").trim(),
      relation_type: String(relationType || "related"),
      notes: String(notes || ""),
    }),
  });
}

export async function deleteDocumentRelation(documentId: number, relationId: string | number) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/relations/${encodeURIComponent(String(relationId || ""))}`, {
    method: "DELETE",
  });
}

export async function loadTagsCatalog() {
  return requestJson("/api/v1/archive/tags");
}

export async function createTag(name: string, color = "") {
  return requestJson("/api/v1/archive/tags", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: String(name || ""),
      color: String(color || ""),
    }),
  });
}

export async function loadDocumentTags(documentId: number) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/tags`);
}

export async function assignDocumentTag(
  documentId: number,
  payload: { tag_id?: number | null; tag_name?: string | null; color?: string | null },
) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/tags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export async function removeDocumentTag(documentId: number, tagId: number) {
  return requestJson(`/api/v1/archive/documents/${Number(documentId || 0)}/tags/${Number(tagId || 0)}`, {
    method: "DELETE",
  });
}
