export interface TransmittalDataHttpDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
}

export interface TransmittalStatsPayload {
  total_transmittals: number;
  this_month: number;
  last_created: string;
}

export interface TransmittalPartyOption {
  code: string;
  label: string;
  is_active?: boolean;
  sort_order?: number;
}

export interface TransmittalOptionsPayload {
  direction_options: TransmittalPartyOption[];
  recipient_options: TransmittalPartyOption[];
}

export interface TransmittalListItem {
  id?: string;
  transmittal_no?: string;
  subject?: string;
  doc_count?: number;
  status?: string;
  created_at?: string;
  void_reason?: string | null;
  voided_by?: string | null;
  voided_at?: string | null;
  [key: string]: unknown;
}

export interface NextNumberInput {
  projectCode: string;
  sender: string;
  receiver: string;
}

export interface SearchEligibleInput {
  projectCode: string;
  disciplineCode: string;
  q: string;
  limit?: number;
}

export interface EligibleDocItem {
  doc_number?: string;
  doc_title?: string;
  project_code?: string;
  discipline_code?: string | null;
  revision?: string;
  status?: string;
  default_file_kind?: string;
  file_kind?: string;
  file_options?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface TransmittalDataBridge {
  requestJson(url: string, init: RequestInit | undefined, deps: TransmittalDataHttpDeps): Promise<unknown>;
  loadStats(deps: TransmittalDataHttpDeps): Promise<TransmittalStatsPayload>;
  loadList(deps: TransmittalDataHttpDeps): Promise<TransmittalListItem[]>;
  loadOptions(deps: TransmittalDataHttpDeps): Promise<TransmittalOptionsPayload>;
  getNextNumber(input: NextNumberInput, deps: TransmittalDataHttpDeps): Promise<string>;
  searchEligibleDocs(input: SearchEligibleInput, deps: TransmittalDataHttpDeps): Promise<EligibleDocItem[]>;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function normalizeCode(input: unknown): string {
  return String(input || "").trim().toUpperCase();
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
  deps: TransmittalDataHttpDeps
): Promise<unknown> {
  const response = await deps.fetch(url, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    const body = asRecord(await parseJsonSafe(response.clone()));
    const detail = String(body.detail || body.message || "").trim();
    if (detail) {
      message = detail;
    }
    throw new Error(message);
  }
  return parseJsonSafe(response);
}

async function loadStats(deps: TransmittalDataHttpDeps): Promise<TransmittalStatsPayload> {
  const body = asRecord(await requestJson("/api/v1/transmittal/stats/summary", undefined, deps));
  return {
    total_transmittals: Number(body.total_transmittals ?? 0),
    this_month: Number(body.this_month ?? 0),
    last_created: String(body.last_created || "-"),
  };
}

async function loadList(deps: TransmittalDataHttpDeps): Promise<TransmittalListItem[]> {
  return asArray<TransmittalListItem>(await requestJson("/api/v1/transmittal/", undefined, deps));
}

async function loadOptions(deps: TransmittalDataHttpDeps): Promise<TransmittalOptionsPayload> {
  const body = asRecord(await requestJson("/api/v1/transmittal/options", undefined, deps));
  return {
    direction_options: asArray<TransmittalPartyOption>(body.direction_options),
    recipient_options: asArray<TransmittalPartyOption>(body.recipient_options),
  };
}

async function getNextNumber(input: NextNumberInput, deps: TransmittalDataHttpDeps): Promise<string> {
  const projectCode = normalizeCode(input.projectCode);
  if (!projectCode) return "";

  const sender = normalizeCode(input.sender) || "O";
  const receiver = normalizeCode(input.receiver) || "C";
  const qs = new URLSearchParams({
    project_code: projectCode,
    sender,
    receiver,
  });
  const body = asRecord(await requestJson(`/api/v1/transmittal/next-number?${qs.toString()}`, undefined, deps));
  return String(body.transmittal_no || "").trim();
}

async function searchEligibleDocs(
  input: SearchEligibleInput,
  deps: TransmittalDataHttpDeps
): Promise<EligibleDocItem[]> {
  const projectCode = normalizeCode(input.projectCode);
  if (!projectCode) return [];

  const qs = new URLSearchParams({
    project_code: projectCode,
    discipline_code: normalizeCode(input.disciplineCode),
    q: String(input.q || "").trim(),
    limit: String(Math.max(1, Math.min(100, Number(input.limit || 30)))),
  });
  return asArray<EligibleDocItem>(
    await requestJson(`/api/v1/transmittal/eligible-docs?${qs.toString()}`, undefined, deps)
  );
}

export function createTransmittalDataBridge(): TransmittalDataBridge {
  return {
    requestJson,
    loadStats,
    loadList,
    loadOptions,
    getNextNumber,
    searchEligibleDocs,
  };
}
