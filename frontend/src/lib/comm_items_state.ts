import { formatShamsiDate, formatShamsiDateTime } from "./persian_datetime";

export interface CommItemsStateBridge {
  esc(value: unknown): string;
  itemTypeLabel(value: unknown): string;
  statusClass(value: unknown): string;
  renderRows(body: HTMLElement | null, rows: Record<string, unknown>[], canEdit: boolean): boolean;
  renderStats(moduleKey: string, rows: Record<string, unknown>[], total: number): boolean;
  renderTimeline(host: HTMLElement | null, payload: Record<string, unknown>): boolean;
  renderComments(host: HTMLElement | null, rows: Record<string, unknown>[]): boolean;
  renderAttachments(host: HTMLElement | null, payload: Record<string, unknown>): boolean;
  renderRelations(host: HTMLElement | null, outgoing: Record<string, unknown>[], incoming: Record<string, unknown>[]): boolean;
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

function itemTypeLabel(value: unknown): string {
  const v = normalize(value);
  if (v === "RFI") return "RFI";
  if (v === "NCR") return "NCR";
  if (v === "TECH") return "TECH";
  return v || "-";
}

function statusClass(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/_/g, "-");
}

function isOpen(itemType: unknown, statusCode: unknown): boolean {
  const type = normalize(itemType);
  const status = normalize(statusCode);
  if (type === "RFI") return !["CLOSED", "SUPERSEDED"].includes(status);
  if (type === "NCR") return status !== "CLOSED";
  if (type === "TECH") return status !== "CLOSED";
  return status !== "CLOSED";
}

function renderRows(body: HTMLElement | null, rows: Record<string, unknown>[], canEdit: boolean): boolean {
  if (!(body instanceof HTMLElement)) return false;
  if (!Array.isArray(rows) || !rows.length) {
    body.innerHTML = `<tr><td colspan="10" class="center-text" style="padding:24px;color:#64748b;">آیتمی یافت نشد.</td></tr>`;
    return true;
  }

  body.innerHTML = rows
    .map((row, index) => {
      const itemId = Number(row.id || 0);
      const isOverdue = Boolean(row.is_overdue);
      const itemType = normalize(row.item_type);
      const isPrintableForm = ["RFI", "NCR"].includes(itemType);
      const isMutableItem = ["RFI", "NCR"].includes(itemType);
      const overdueBadge = isOverdue ? `<span class="module-crud-priority is-urgent">Overdue</span>` : "";
      return `
        <tr>
          <td>${index + 1}</td>
          <td style="font-family:monospace;">${esc(row.item_no || "-")}</td>
          <td><div class="ci-row-title" title="${esc(row.title || "-")}">${esc(row.title || "-")}</div></td>
          <td><span class="module-crud-status is-${statusClass(row.item_type)}">${esc(itemTypeLabel(row.item_type))}</span></td>
          <td><span class="module-crud-status is-${statusClass(row.status_code)}">${esc(row.status_code || "-")}</span></td>
          <td><span class="module-crud-priority is-${String(row.priority || "").toLowerCase()}">${esc(row.priority || "-")}</span></td>
          <td>${esc(formatShamsiDate(row.response_due_date))}</td>
          <td>${Number(row.aging_days || 0) > 0 ? Number(row.aging_days || 0) : "-"}</td>
          <td>${overdueBadge}</td>
          <td>
            <div class="archive-row-menu" data-ci-row-menu>
              <button class="btn-archive-icon archive-row-menu-trigger" type="button" title="عملیات" data-ci-action="toggle-row-menu" aria-expanded="false">
                <span class="material-icons-round" style="font-size:18px;">more_vert</span>
              </button>
              <div class="archive-row-menu-dropdown">
                <button class="archive-row-menu-item" type="button" data-ci-action="open-detail" data-ci-id="${itemId}">
                  <span class="material-icons-round">visibility</span>
                  <span>جزئیات</span>
                </button>
                ${canEdit && isMutableItem ? `
                <button class="archive-row-menu-item" type="button" data-ci-action="open-edit" data-ci-id="${itemId}">
                  <span class="material-icons-round">edit</span>
                  <span>ویرایش</span>
                </button>
                <button class="archive-row-menu-item" type="button" data-ci-action="quick-transition" data-ci-id="${itemId}">
                  <span class="material-icons-round">sync_alt</span>
                  <span>تغییر وضعیت</span>
                </button>` : ""}
                <button class="archive-row-menu-item" type="button" data-ci-action="copy-item-no" data-ci-item-no="${esc(row.item_no || "-")}">
                  <span class="material-icons-round">content_copy</span>
                  <span>کپی شماره آیتم</span>
                </button>
                ${isPrintableForm ? `
                <button class="archive-row-menu-item" type="button" data-ci-action="print-rfi-form" data-ci-id="${itemId}">
                  <span class="material-icons-round">preview</span>
                  <span>پیش‌نمایش فرم ${esc(itemType)}</span>
                </button>` : ""}
              </div>
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

  const open = rows.filter((row) => isOpen(row.item_type, row.status_code)).length;
  const waiting = rows.filter((row) => ["RETURNED", "IN_REVIEW", "CONTRACTOR_REPLY", "REVISE_RESUBMIT"].includes(normalize(row.status_code))).length;
  const overdue = rows.filter((row) => Boolean(row.is_overdue)).length;

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

function renderTimeline(host: HTMLElement | null, payload: Record<string, unknown>): boolean {
  if (!(host instanceof HTMLElement)) return false;
  const statusLogs = Array.isArray(payload.status_logs) ? (payload.status_logs as Record<string, unknown>[]) : [];
  const fieldAudits = Array.isArray(payload.field_audits) ? (payload.field_audits as Record<string, unknown>[]) : [];

  const statusHtml = statusLogs.length
    ? statusLogs
        .map(
          (row) => `<li><strong>${esc(row.from_status_code || "-")} → ${esc(row.to_status_code || "-")}</strong> · ${esc(
            row.changed_by_name || row.changed_by_id || "-"
          )} · ${esc(formatShamsiDateTime(row.changed_at))}<div>${esc(row.note || "")}</div></li>`
        )
        .join("")
    : '<li style="color:#64748b;">رویدادی ثبت نشده است.</li>';

  const auditHtml = fieldAudits.length
    ? fieldAudits
        .map(
          (row) => `<li><strong>${esc(row.field_name || "-")}</strong>: ${esc(row.old_value || "-")} → ${esc(
            row.new_value || "-"
          )} · ${esc(row.changed_by_name || row.changed_by_id || "-")} · ${esc(formatShamsiDateTime(row.changed_at))}</li>`
        )
        .join("")
    : '<li style="color:#64748b;">Field audit موجود نیست.</li>';

  host.innerHTML = `
    <div class="ci-detail-grid">
      <section class="ci-detail-section">
        <div class="ci-detail-section-head"><h4>تاریخچه وضعیت‌ها</h4></div>
        <ul style="padding-inline-start:18px;line-height:1.9;margin:0;">${statusHtml}</ul>
      </section>
      <section class="ci-detail-section">
        <div class="ci-detail-section-head"><h4>تغییرات فیلدها</h4></div>
        <ul style="padding-inline-start:18px;line-height:1.9;margin:0;">${auditHtml}</ul>
      </section>
    </div>
  `;
  return true;
}

function renderComments(host: HTMLElement | null, rows: Record<string, unknown>[]): boolean {
  if (!(host instanceof HTMLElement)) return false;
  if (!rows.length) {
    host.innerHTML = '<div class="ci-detail-section"><div class="module-crud-empty">کامنتی ثبت نشده است.</div></div>';
    return true;
  }
  host.innerHTML = rows
    .map(
      (row) => `
      <div class="ci-detail-section" style="margin-bottom:8px;">
        <div style="font-size:0.82rem;color:#64748b;">${esc(row.created_by_name || row.created_by_id || "-")} · ${esc(
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

function formatBytes(value: unknown): string {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

function scopeLabel(value: unknown): string {
  const normalized = normalize(value);
  if (normalized === "REFERENCE") return "ارجاع";
  if (normalized === "RESPONSE") return "پاسخ";
  if (normalized === "GENERAL") return "عمومی";
  return normalized || "General";
}

function renderAttachmentRows(rows: Record<string, unknown>[]): string {
  return rows
    .map(
      (row) => `
      <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e2e8f0;padding:8px 0;gap:8px;">
        <div>
          <div style="font-weight:600;">${esc(row.file_name || "-")}</div>
          <div style="font-size:0.82rem;color:#64748b;">
            <span>${esc(row.file_kind || "-")}</span>
            · <span>${esc(row.validation_status || "-")}</span>
            · <span>${esc(formatBytes(row.size_bytes))}</span>
            · <span>${esc(row.uploaded_by_name || row.uploaded_by_id || "-")}</span>
            · <span>${esc(formatShamsiDateTime(row.uploaded_at))}</span>
          </div>
        </div>
        <div style="display:flex;gap:6px;">
          <a class="btn-archive-icon" href="/api/v1/comm-items/attachments/${Number(row.id || 0)}/download" target="_blank" rel="noopener">دانلود</a>
          <button type="button" class="btn-archive-icon" data-ci-action="delete-attachment" data-ci-attachment-id="${Number(
            row.id || 0
          )}">حذف</button>
        </div>
      </div>
    `
    )
    .join("");
}

function renderAttachments(host: HTMLElement | null, payload: Record<string, unknown>): boolean {
  if (!(host instanceof HTMLElement)) return false;
  const rows = Array.isArray(payload.data) ? (payload.data as Record<string, unknown>[]) : [];
  if (!rows.length) {
    host.innerHTML = '<div class="ci-detail-section"><div class="module-crud-empty">پیوستی ثبت نشده است.</div></div>';
    return true;
  }
  const grouped = asRecord(payload.grouped);
  const scopes = ["REFERENCE", "RESPONSE", "GENERAL"];
  host.innerHTML = scopes
    .map((scope) => {
      const slotMap = asRecord(grouped[scope]);
      const slots = Object.keys(slotMap);
      if (!slots.length) {
        return `
          <div class="ci-detail-section" style="margin-bottom:10px;">
            <div class="ci-detail-section-head"><h4>${esc(scopeLabel(scope))}</h4></div>
            <div style="color:#64748b;">پیوستی ثبت نشده است.</div>
          </div>
        `;
      }
      const slotsHtml = slots
        .sort()
        .map((slot) => {
          const bucket = Array.isArray(slotMap[slot]) ? (slotMap[slot] as Record<string, unknown>[]) : [];
          return `
            <div style="margin-top:8px;">
              <div style="font-size:0.82rem;color:#334155;font-weight:600;">${esc(slot)}</div>
              ${renderAttachmentRows(bucket)}
            </div>
          `;
        })
        .join("");
      return `
        <div class="ci-detail-section" style="margin-bottom:10px;">
          <div class="ci-detail-section-head"><h4>${esc(scopeLabel(scope))}</h4></div>
          ${slotsHtml}
        </div>
      `;
    })
    .join("");
  return true;
}

function renderRelations(
  host: HTMLElement | null,
  outgoing: Record<string, unknown>[],
  incoming: Record<string, unknown>[]
): boolean {
  if (!(host instanceof HTMLElement)) return false;
  const toRow = (row: Record<string, unknown>): string => `
    <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e2e8f0;padding:8px 0;gap:8px;">
      <div>
        <strong>${esc(row.relation_type || "-")}</strong>
        <div style="font-size:0.82rem;color:#64748b;">${esc(row.from_item_no || row.from_item_id || "-")} → ${esc(
    row.to_item_no || row.to_item_id || "-"
  )}</div>
      </div>
      <button type="button" class="btn-archive-icon" data-ci-action="delete-relation" data-ci-relation-id="${Number(
        row.id || 0
      )}">حذف</button>
    </div>
  `;

  const outgoingHtml = outgoing.length ? outgoing.map(toRow).join("") : '<div style="color:#64748b;">رابطه خروجی ندارد.</div>';
  const incomingHtml = incoming.length ? incoming.map(toRow).join("") : '<div style="color:#64748b;">رابطه ورودی ندارد.</div>';

  host.innerHTML = `
    <div class="ci-detail-grid">
      <section class="ci-detail-section"><div class="ci-detail-section-head"><h4>روابط خروجی</h4></div>${outgoingHtml}</section>
      <section class="ci-detail-section"><div class="ci-detail-section-head"><h4>روابط ورودی</h4></div>${incomingHtml}</section>
    </div>
  `;
  return true;
}

export function createCommItemsStateBridge(): CommItemsStateBridge {
  return {
    esc,
    itemTypeLabel,
    statusClass,
    renderRows,
    renderStats,
    renderTimeline,
    renderComments,
    renderAttachments,
    renderRelations,
  };
}
