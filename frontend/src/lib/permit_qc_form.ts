export interface PermitQcFormBridge {
  norm(value: unknown): string;
  upper(value: unknown): string;
  toInt(value: unknown): number | null;
  toIsoDate(value: unknown): string | null;
  buildCreatePayload(moduleKey: string, payload: Record<string, unknown>): Record<string, unknown>;
  buildUpdatePayload(payload: Record<string, unknown>): Record<string, unknown>;
  buildReviewPayload(payload: Record<string, unknown>): Record<string, unknown>;
}

function norm(value: unknown): string {
  return String(value ?? "").trim();
}

function upper(value: unknown): string {
  return norm(value).toUpperCase();
}

function toInt(value: unknown): number | null {
  const raw = norm(value);
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  const integer = Math.trunc(parsed);
  return integer > 0 ? integer : null;
}

function toIsoDate(value: unknown): string | null {
  const raw = norm(value);
  if (!raw) return null;
  if (raw.includes("T")) return raw;
  return `${raw}T00:00:00`;
}

function pickString(payload: Record<string, unknown>, key: string): string | undefined {
  if (!(key in payload)) return undefined;
  const value = norm(payload[key]);
  return value || "";
}

function buildCreatePayload(moduleKey: string, payload: Record<string, unknown>): Record<string, unknown> {
  return {
    module_key: norm(moduleKey) || "contractor",
    permit_no: norm(payload.permit_no),
    permit_date: toIsoDate(payload.permit_date),
    title: norm(payload.title),
    description: norm(payload.description) || null,
    wall_name: norm(payload.wall_name) || null,
    floor_label: norm(payload.floor_label) || null,
    elevation_start: norm(payload.elevation_start) || null,
    elevation_end: norm(payload.elevation_end) || null,
    project_code: upper(payload.project_code),
    discipline_code: upper(payload.discipline_code),
    template_id: toInt(payload.template_id),
    consultant_org_id: toInt(payload.consultant_org_id),
  };
}

function buildUpdatePayload(payload: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const permitNo = pickString(payload, "permit_no");
  if (permitNo !== undefined) out.permit_no = permitNo;
  if ("permit_date" in payload) out.permit_date = toIsoDate(payload.permit_date);
  const title = pickString(payload, "title");
  if (title !== undefined) out.title = title;
  if ("description" in payload) out.description = norm(payload.description) || null;
  if ("wall_name" in payload) out.wall_name = norm(payload.wall_name) || null;
  if ("floor_label" in payload) out.floor_label = norm(payload.floor_label) || null;
  if ("elevation_start" in payload) out.elevation_start = norm(payload.elevation_start) || null;
  if ("elevation_end" in payload) out.elevation_end = norm(payload.elevation_end) || null;
  if ("project_code" in payload) out.project_code = upper(payload.project_code);
  if ("discipline_code" in payload) out.discipline_code = upper(payload.discipline_code);
  if ("template_id" in payload) out.template_id = toInt(payload.template_id);
  if ("consultant_org_id" in payload) out.consultant_org_id = toInt(payload.consultant_org_id);
  return out;
}

function buildReviewPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const action = upper(payload.action) || "APPROVE";
  const checks = Array.isArray(payload.checks) ? payload.checks : [];
  return {
    station_id: toInt(payload.station_id),
    action,
    note: norm(payload.note) || null,
    checks: checks
      .map((item) => {
        const row = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
        return {
          check_id: toInt(row.check_id),
          value_text: norm(row.value_text) || null,
          value_bool: typeof row.value_bool === "boolean" ? row.value_bool : null,
          value_number: Number.isFinite(Number(row.value_number)) ? Number(row.value_number) : null,
          value_date: toIsoDate(row.value_date),
          note: norm(row.note) || null,
        };
      })
      .filter((item) => Number(item.check_id) > 0),
  };
}

export function createPermitQcFormBridge(): PermitQcFormBridge {
  return {
    norm,
    upper,
    toInt,
    toIsoDate,
    buildCreatePayload,
    buildUpdatePayload,
    buildReviewPayload,
  };
}
