import { formatShamsiDate, formatShamsiDateTime } from "./persian_datetime";

export interface SiteLogsStateBridge {
  esc(value: unknown): string;
  statusClass(value: unknown): string;
  renderRows(
    body: HTMLElement | null,
    rows: Record<string, unknown>[],
    options: { canEdit: boolean; canVerify: boolean }
  ): boolean;
  renderStats(moduleKey: string, rows: Record<string, unknown>[], total: number): boolean;
  renderComments(host: HTMLElement | null, rows: Record<string, unknown>[]): boolean;
  renderAttachments(host: HTMLElement | null, payload: Record<string, unknown>): boolean;
}

function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalize(value: unknown): string {
  return String(value ?? "").trim().toUpperCase();
}

function statusClass(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/_/g, "-");
}

function logTypeLabel(value: unknown): string {
  const code = normalize(value);
  if (code === "DAILY") return "روزانه";
  if (code === "WEEKLY") return "هفتگی";
  if (code === "SAFETY_INCIDENT") return "ایمنی";
  return code || "-";
}

function statusLabel(value: unknown): string {
  const code = normalize(value);
  if (code === "DRAFT") return "پیش‌نویس";
  if (code === "SUBMITTED") return "ارسال‌شده";
  if (code === "VERIFIED") return "تاییدشده";
  return code || "-";
}

function renderRows(
  body: HTMLElement | null,
  rows: Record<string, unknown>[],
  options: { canEdit: boolean; canVerify: boolean }
): boolean {
  if (!(body instanceof HTMLElement)) return false;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="10" class="center-text" style="padding:24px;color:#64748b;">گزارشی یافت نشد.</td></tr>';
    return true;
  }
  body.innerHTML = rows
    .map((row, index) => {
      const logId = Number(row.id || 0);
      const status = normalize(row.status_code);
      const canEditRow = options.canEdit && status === "DRAFT";
      const canVerifyRow = options.canVerify && status === "SUBMITTED";
      return `
        <tr>
          <td>${index + 1}</td>
          <td style="font-family:monospace;">${esc(row.log_no || "-")}</td>
          <td>${esc(logTypeLabel(row.log_type))}</td>
          <td>${esc(formatShamsiDate(row.log_date))}</td>
          <td><span class="module-crud-status is-${statusClass(row.status_code)}">${esc(statusLabel(row.status_code))}</span></td>
          <td>${Number(row.manpower_count || 0)}</td>
          <td>${Number(row.equipment_count || 0)}</td>
          <td>${Number(row.activity_count || 0)}</td>
          <td>${esc(row.organization_name || "-")}</td>
          <td>
            <div class="module-crud-actions">
              ${canEditRow ? `<button type="button" class="btn-archive-icon" data-sl-action="open-edit" data-sl-id="${logId}">ویرایش</button>` : ""}
              ${canVerifyRow ? `<button type="button" class="btn-archive-icon" data-sl-action="open-verify" data-sl-id="${logId}">تایید</button>` : ""}
              <button type="button" class="btn-archive-icon" data-sl-action="open-detail" data-sl-id="${logId}">جزئیات</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
  return true;
}

function renderStats(moduleKey: string, rows: Record<string, unknown>[], total: number): boolean {
  const isConsultant = String(moduleKey || "").trim().toLowerCase() === "consultant";
  const map = isConsultant
    ? {
        total: "consultant-stat-total",
        open: "consultant-stat-open",
        waiting: "consultant-stat-waiting",
        overdue: "consultant-stat-overdue",
      }
    : {
        total: "contractor-stat-total",
        open: "contractor-stat-open",
        waiting: "contractor-stat-waiting",
        overdue: "contractor-stat-overdue",
      };

  const open = rows.filter((row) => ["DRAFT", "SUBMITTED"].includes(normalize(row.status_code))).length;
  const waiting = rows.filter((row) => normalize(row.status_code) === "SUBMITTED").length;
  const overdue = 0;

  const values: Record<string, number> = {
    total: Math.max(0, Number(total || 0) || rows.length),
    open,
    waiting,
    overdue,
  };
  Object.entries(map).forEach(([key, id]) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = String(values[key] ?? 0);
  });
  return true;
}

function renderComments(host: HTMLElement | null, rows: Record<string, unknown>[]): boolean {
  if (!(host instanceof HTMLElement)) return false;
  if (!rows.length) {
    host.innerHTML = '<div style="color:#64748b;">یادداشتی ثبت نشده است.</div>';
    return true;
  }
  host.innerHTML = rows
    .map(
      (row) => `
      <div class="archive-card" style="padding:10px 12px;margin-bottom:8px;">
        <div style="font-size:0.82rem;color:#64748b;">${esc(row.created_by_name || row.created_by_id || "-")} • ${esc(
        formatShamsiDateTime(row.created_at)
      )}</div>
        <div style="margin-top:6px;">${esc(row.comment_text || "")}</div>
      </div>
    `
    )
    .join("");
  return true;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

function sectionLabel(code: string): string {
  const normalized = normalize(code);
  if (normalized === "GENERAL") return "عمومی";
  if (normalized === "MANPOWER") return "نفرات";
  if (normalized === "EQUIPMENT") return "تجهیزات";
  if (normalized === "ACTIVITY") return "فعالیت‌ها";
  return normalized || "-";
}

function renderAttachments(host: HTMLElement | null, payload: Record<string, unknown>): boolean {
  if (!(host instanceof HTMLElement)) return false;
  const grouped = asRecord(payload.grouped);
  const sections = ["GENERAL", "MANPOWER", "EQUIPMENT", "ACTIVITY"];
  const html = sections
    .map((section) => {
      const rows = asArray(grouped[section]);
      if (!rows.length) {
        return `
          <div class="archive-card" style="padding:10px;margin-bottom:8px;">
            <div style="font-weight:700;">${esc(sectionLabel(section))}</div>
            <div style="color:#64748b;">فایلی ثبت نشده است.</div>
          </div>
        `;
      }
      const rowHtml = rows
        .map(
          (row) => `
          <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e2e8f0;padding:8px 0;gap:8px;">
            <div>
              <div style="font-weight:600;">${esc(row.file_name || "-")}</div>
              <div style="font-size:0.82rem;color:#64748b;">${esc(row.file_kind || "-")} • ${esc(
            row.uploaded_by_name || row.uploaded_by_id || "-"
          )} • ${esc(formatShamsiDateTime(row.uploaded_at))}</div>
            </div>
            <div style="display:flex;gap:6px;">
              <a class="btn-archive-icon" href="/api/v1/site-logs/attachments/${Number(row.id || 0)}/download" target="_blank" rel="noopener">دانلود</a>
              <button type="button" class="btn-archive-icon" data-sl-action="delete-attachment" data-sl-attachment-id="${Number(
                row.id || 0
              )}">حذف</button>
            </div>
          </div>
        `
        )
        .join("");
      return `
        <div class="archive-card" style="padding:10px;margin-bottom:8px;">
          <div style="font-weight:700;">${esc(sectionLabel(section))}</div>
          ${rowHtml}
        </div>
      `;
    })
    .join("");
  host.innerHTML = html;
  return true;
}

export function createSiteLogsStateBridge(): SiteLogsStateBridge {
  return {
    esc,
    statusClass,
    renderRows,
    renderStats,
    renderComments,
    renderAttachments,
  };
}
