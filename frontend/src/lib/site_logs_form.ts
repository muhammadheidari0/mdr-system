export interface SiteLogsFormBridge {
  normalize(value: unknown): string;
  upper(value: unknown): string;
  toIsoDate(value: unknown): string | null;
  toInt(value: unknown): number | null;
  toFloat(value: unknown): number | null;
  defaultLogType(moduleKey: unknown, tabKey: unknown): string;
  validateBase(input: Record<string, unknown>): string[];
  validateForSubmit(input: Record<string, unknown>): string[];
  sanitizeManpowerRows(rows: unknown): Record<string, unknown>[];
  sanitizeEquipmentRows(rows: unknown): Record<string, unknown>[];
  sanitizeActivityRows(rows: unknown): Record<string, unknown>[];
  buildCreatePayload(input: Record<string, unknown>): Record<string, unknown>;
  buildUpdatePayload(input: Record<string, unknown>): Record<string, unknown>;
  buildVerifyPayload(input: Record<string, unknown>): Record<string, unknown>;
}

function normalize(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function upper(value: unknown): string {
  return String(value ?? "").trim().toUpperCase();
}

function toIsoDate(value: unknown): string | null {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  if (raw.includes("T")) return raw;
  return `${raw}T00:00:00`;
}

function toInt(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  const integer = Math.trunc(parsed);
  return integer >= 0 ? integer : null;
}

function toFloat(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

function asRow(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function defaultLogType(moduleKey: unknown, tabKey: unknown): string {
  const key = `${normalize(moduleKey)}:${normalize(tabKey)}`;
  if (key === "contractor:execution") return "DAILY";
  if (key === "consultant:inspection") return "DAILY";
  return "DAILY";
}

function sanitizeManpowerRows(rows: unknown): Record<string, unknown>[] {
  return asArray(rows)
    .map((raw, index) => {
      const row = asRow(raw);
      const out: Record<string, unknown> = {
        role_code: upper(row.role_code) || null,
        role_label: String(row.role_label ?? "").trim() || null,
        claimed_count: toInt(row.claimed_count),
        claimed_hours: toFloat(row.claimed_hours),
        verified_count: toInt(row.verified_count),
        verified_hours: toFloat(row.verified_hours),
        note: String(row.note ?? "").trim() || null,
        sort_order: toInt(row.sort_order) ?? index,
      };
      const meaningful =
        !!out.role_code ||
        !!out.role_label ||
        out.claimed_count !== null ||
        out.claimed_hours !== null ||
        out.verified_count !== null ||
        out.verified_hours !== null ||
        !!out.note;
      return meaningful ? out : null;
    })
    .filter((row): row is Record<string, unknown> => !!row);
}

function sanitizeEquipmentRows(rows: unknown): Record<string, unknown>[] {
  return asArray(rows)
    .map((raw, index) => {
      const row = asRow(raw);
      const out: Record<string, unknown> = {
        equipment_code: upper(row.equipment_code) || null,
        equipment_label: String(row.equipment_label ?? "").trim() || null,
        claimed_status: upper(row.claimed_status) || null,
        claimed_hours: toFloat(row.claimed_hours),
        verified_status: upper(row.verified_status) || null,
        verified_hours: toFloat(row.verified_hours),
        note: String(row.note ?? "").trim() || null,
        sort_order: toInt(row.sort_order) ?? index,
      };
      const meaningful =
        !!out.equipment_code ||
        !!out.equipment_label ||
        !!out.claimed_status ||
        out.claimed_hours !== null ||
        !!out.verified_status ||
        out.verified_hours !== null ||
        !!out.note;
      return meaningful ? out : null;
    })
    .filter((row): row is Record<string, unknown> => !!row);
}

function sanitizeActivityRows(rows: unknown): Record<string, unknown>[] {
  return asArray(rows)
    .map((raw, index) => {
      const row = asRow(raw);
      const out: Record<string, unknown> = {
        activity_code: upper(row.activity_code) || null,
        activity_title: String(row.activity_title ?? "").trim() || null,
        source_system: upper(row.source_system) || "MANUAL",
        external_ref: String(row.external_ref ?? "").trim() || null,
        claimed_progress_pct: toFloat(row.claimed_progress_pct),
        verified_progress_pct: toFloat(row.verified_progress_pct),
        note: String(row.note ?? "").trim() || null,
        sort_order: toInt(row.sort_order) ?? index,
      };
      const meaningful =
        !!out.activity_code ||
        !!out.activity_title ||
        !!out.external_ref ||
        out.claimed_progress_pct !== null ||
        out.verified_progress_pct !== null ||
        !!out.note;
      return meaningful ? out : null;
    })
    .filter((row): row is Record<string, unknown> => !!row);
}

function hasAnyRows(input: Record<string, unknown>): boolean {
  return (
    sanitizeManpowerRows(input.manpower_rows).length > 0 ||
    sanitizeEquipmentRows(input.equipment_rows).length > 0 ||
    sanitizeActivityRows(input.activity_rows).length > 0
  );
}

function validateBase(input: Record<string, unknown>): string[] {
  const errors: string[] = [];
  if (!upper(input.project_code)) errors.push("انتخاب پروژه الزامی است.");
  if (!upper(input.discipline_code)) errors.push("انتخاب دیسیپلین الزامی است.");
  if (!toIsoDate(input.log_date)) errors.push("تاریخ گزارش الزامی است.");
  if (!upper(input.log_type)) errors.push("نوع گزارش الزامی است.");
  return errors;
}

function validateForSubmit(input: Record<string, unknown>): string[] {
  const errors = validateBase(input);
  if (!hasAnyRows(input)) errors.push("قبل از ارسال، حداقل یک ردیف باید ثبت شود.");
  return errors;
}

function buildCreatePayload(input: Record<string, unknown>): Record<string, unknown> {
  return {
    log_type: upper(input.log_type),
    project_code: upper(input.project_code),
    discipline_code: upper(input.discipline_code),
    organization_id: toInt(input.organization_id),
    log_date: toIsoDate(input.log_date),
    weather: upper(input.weather) || null,
    summary: String(input.summary ?? "").trim() || null,
    status_code: upper(input.status_code) || "DRAFT",
    manpower_rows: sanitizeManpowerRows(input.manpower_rows),
    equipment_rows: sanitizeEquipmentRows(input.equipment_rows),
    activity_rows: sanitizeActivityRows(input.activity_rows),
  };
}

function buildUpdatePayload(input: Record<string, unknown>): Record<string, unknown> {
  const payload = buildCreatePayload(input);
  delete payload.status_code;
  return payload;
}

function buildVerifyPayload(input: Record<string, unknown>): Record<string, unknown> {
  const manpower = sanitizeManpowerRows(input.manpower_rows).map((row) => ({
    sort_order: row.sort_order,
    verified_count: row.verified_count,
    verified_hours: row.verified_hours,
    note: row.note,
  }));
  const equipment = sanitizeEquipmentRows(input.equipment_rows).map((row) => ({
    sort_order: row.sort_order,
    verified_status: row.verified_status,
    verified_hours: row.verified_hours,
    note: row.note,
  }));
  const activity = sanitizeActivityRows(input.activity_rows).map((row) => ({
    sort_order: row.sort_order,
    verified_progress_pct: row.verified_progress_pct,
    note: row.note,
  }));
  return {
    note: String(input.note ?? "").trim() || null,
    manpower_rows: manpower,
    equipment_rows: equipment,
    activity_rows: activity,
  };
}

export function createSiteLogsFormBridge(): SiteLogsFormBridge {
  return {
    normalize,
    upper,
    toIsoDate,
    toInt,
    toFloat,
    defaultLogType,
    validateBase,
    validateForSubmit,
    sanitizeManpowerRows,
    sanitizeEquipmentRows,
    sanitizeActivityRows,
    buildCreatePayload,
    buildUpdatePayload,
    buildVerifyPayload,
  };
}
