import type {
  CorrespondenceActionPayload,
  CorrespondenceSavePayload,
} from "./correspondence_mutations";

export interface CorrespondenceCatalogIssuingRow {
  code?: string | null;
  project_code?: string | null;
}

export interface CorrespondenceFormValues {
  id: string;
  issuing_code: string;
  category_code: string;
  direction: "I" | "O";
  project_code: string;
  tag_id: string;
  reference_no: string;
  subject: string;
  sender: string;
  recipient: string;
  corr_date: string;
  due_date: string;
  status: string;
  priority: string;
  notes: string;
}

export interface CorrespondenceFormInput {
  project_code?: unknown;
  issuing_code?: unknown;
  category_code?: unknown;
  tag_id?: unknown;
  direction?: unknown;
  reference_no?: unknown;
  subject?: unknown;
  sender?: unknown;
  recipient?: unknown;
  corr_date?: unknown;
  due_date?: unknown;
  status?: unknown;
  priority?: unknown;
  notes?: unknown;
}

export interface CorrespondenceActionFormInput {
  action_type?: unknown;
  title?: unknown;
  description?: unknown;
  due_date?: unknown;
  status?: unknown;
}

export interface CorrespondenceActionEditorValues {
  id: string;
  action_type: string;
  title: string;
  due_date: string;
  status: string;
  description: string;
  submit_mode: "create" | "edit";
}

export interface CorrespondenceFormBridge {
  normalizeDirection(value: unknown): "I" | "O";
  toInputDate(value: unknown): string;
  toIsoDate(value: unknown): string | null;
  resolveProjectFromIssuing(
    issuingCode: string,
    issuingRows: CorrespondenceCatalogIssuingRow[] | null | undefined
  ): string;
  createDefaultValues(today?: Date | string | null): CorrespondenceFormValues;
  buildPayload(input: CorrespondenceFormInput): CorrespondenceSavePayload;
  normalizeEditValues(item: Record<string, unknown> | null | undefined): CorrespondenceFormValues;
  createActionEditorDefaults(): CorrespondenceActionEditorValues;
  buildActionPayload(input: CorrespondenceActionFormInput): CorrespondenceActionPayload;
  normalizeActionEditValues(
    item: Record<string, unknown> | null | undefined
  ): CorrespondenceActionEditorValues;
}

function trimString(value: unknown): string {
  return String(value ?? "").trim();
}

function upperCode(value: unknown): string {
  return trimString(value).toUpperCase();
}

function normalizeDirection(value: unknown): "I" | "O" {
  return ["I", "IN", "INBOUND"].includes(upperCode(value)) ? "I" : "O";
}

function toInputDate(value: unknown): string {
  const raw = trimString(value);
  if (!raw) return "";
  if (raw.includes("T")) {
    return raw.split("T")[0];
  }
  return raw.slice(0, 10);
}

function toIsoDate(value: unknown): string | null {
  const raw = trimString(value);
  return raw ? `${raw}T00:00:00` : null;
}

function toDateSeed(today?: Date | string | null): string {
  let date: Date | null = null;
  if (today instanceof Date) {
    date = Number.isNaN(today.getTime()) ? null : today;
  } else if (typeof today === "string") {
    const raw = trimString(today);
    if (raw) {
      const parsed = new Date(`${raw}T00:00:00`);
      date = Number.isNaN(parsed.getTime()) ? null : parsed;
    }
  }
  if (!date) date = new Date();

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function resolveProjectFromIssuing(
  issuingCode: string,
  issuingRows: CorrespondenceCatalogIssuingRow[] | null | undefined
): string {
  const normalizedIssuing = upperCode(issuingCode);
  if (!normalizedIssuing || !Array.isArray(issuingRows)) return "";

  const row = issuingRows.find(
    (item) => upperCode(item?.code) === normalizedIssuing
  );
  return upperCode(row?.project_code);
}

function createDefaultValues(today?: Date | string | null): CorrespondenceFormValues {
  return {
    id: "",
    issuing_code: "",
    category_code: "",
    direction: "O",
    project_code: "",
    tag_id: "",
    reference_no: "",
    subject: "",
    sender: "",
    recipient: "",
    corr_date: toDateSeed(today),
    due_date: "",
    status: "Open",
    priority: "Normal",
    notes: "",
  };
}

function buildPayload(input: CorrespondenceFormInput): CorrespondenceSavePayload {
  const categoryCode = upperCode(input.category_code);
  return {
    project_code: upperCode(input.project_code) || null,
    issuing_code: upperCode(input.issuing_code) || null,
    category_code: categoryCode || null,
    tag_id: Number(String(input.tag_id ?? "").trim() || 0) || null,
    doc_type: categoryCode || null,
    direction: normalizeDirection(input.direction),
    reference_no: trimString(input.reference_no) || null,
    subject: trimString(input.subject),
    sender: trimString(input.sender) || null,
    recipient: trimString(input.recipient) || null,
    corr_date: toIsoDate(input.corr_date),
    due_date: toIsoDate(input.due_date),
    status: trimString(input.status) || "Open",
    priority: trimString(input.priority) || "Normal",
    notes: trimString(input.notes) || null,
  };
}

function normalizeEditValues(
  item: Record<string, unknown> | null | undefined
): CorrespondenceFormValues {
  const record = item && typeof item === "object" ? item : {};
  return {
    id: String(record.id ?? ""),
    issuing_code: String(record.issuing_code ?? ""),
    category_code: String(record.category_code ?? ""),
    direction: normalizeDirection(record.direction),
    project_code: String(record.project_code ?? ""),
    tag_id: String(record.tag_id ?? ""),
    reference_no: String(record.reference_no ?? ""),
    subject: String(record.subject ?? ""),
    sender: String(record.sender ?? ""),
    recipient: String(record.recipient ?? ""),
    corr_date: toInputDate(record.corr_date),
    due_date: toInputDate(record.due_date),
    status: trimString(record.status) || "Open",
    priority: trimString(record.priority) || "Normal",
    notes: String(record.notes ?? ""),
  };
}

function createActionEditorDefaults(): CorrespondenceActionEditorValues {
  return {
    id: "",
    action_type: "task",
    title: "",
    due_date: "",
    status: "Open",
    description: "",
    submit_mode: "create",
  };
}

function buildActionPayload(input: CorrespondenceActionFormInput): CorrespondenceActionPayload {
  const status = trimString(input.status) || "Open";
  return {
    action_type: trimString(input.action_type) || "task",
    title: trimString(input.title) || null,
    description: trimString(input.description) || null,
    due_date: toIsoDate(input.due_date),
    status,
    is_closed: status.toLowerCase() === "closed",
  };
}

function normalizeActionEditValues(
  item: Record<string, unknown> | null | undefined
): CorrespondenceActionEditorValues {
  const record = item && typeof item === "object" ? item : {};
  return {
    id: String(record.id ?? ""),
    action_type: trimString(record.action_type) || "task",
    title: String(record.title ?? ""),
    due_date: toInputDate(record.due_date),
    status: trimString(record.status) || "Open",
    description: String(record.description ?? ""),
    submit_mode: "edit",
  };
}

export function createCorrespondenceFormBridge(): CorrespondenceFormBridge {
  return {
    normalizeDirection,
    toInputDate,
    toIsoDate,
    resolveProjectFromIssuing,
    createDefaultValues,
    buildPayload,
    normalizeEditValues,
    createActionEditorDefaults,
    buildActionPayload,
    normalizeActionEditValues,
  };
}
