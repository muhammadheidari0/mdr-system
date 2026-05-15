export interface ProjectControlHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
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

export function toQuery(params: Record<string, unknown>): string {
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
    searchParams.set(key, String(rawValue));
  });
  const encoded = searchParams.toString();
  return encoded ? `?${encoded}` : "";
}

async function requestJson(url: string, init: RequestInit | undefined, deps: ProjectControlHttpDeps): Promise<unknown> {
  const response = await deps.fetch(url, init);
  if (!response.ok) {
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return parseJsonSafe(response);
}

export async function listMeasurements(
  params: Record<string, unknown>,
  deps: ProjectControlHttpDeps
): Promise<Record<string, unknown>> {
  return asRecord(await requestJson(`/api/v1/project-control/activity-measurements${toQuery(params)}`, undefined, deps));
}

export async function patchMeasurement(
  rowId: number,
  payload: Record<string, unknown>,
  deps: ProjectControlHttpDeps
): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(
      `/api/v1/project-control/activity-measurements/${Number(rowId || 0)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      deps
    )
  );
}

export async function transitionMeasurement(
  rowId: number,
  target: string,
  deps: ProjectControlHttpDeps
): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(
      `/api/v1/project-control/activity-measurements/${Number(rowId || 0)}/transition`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target }),
      },
      deps
    )
  );
}

export async function getSourceReport(rowId: number, deps: ProjectControlHttpDeps): Promise<Record<string, unknown>> {
  return asRecord(
    await requestJson(`/api/v1/project-control/activity-measurements/${Number(rowId || 0)}/source-report`, undefined, deps)
  );
}

export function csvUrl(shape: "wide" | "long", params: Record<string, unknown>): string {
  return `/api/v1/project-control/activity-measurements.csv${toQuery({ ...params, shape })}`;
}
