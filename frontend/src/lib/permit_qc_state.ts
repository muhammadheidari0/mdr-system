import { formatShamsiDate, formatShamsiDateTime } from "./persian_datetime";

export interface PermitQcStateBridge {
  esc(value: unknown): string;
  statusClass(value: unknown): string;
  renderRows(body: HTMLElement | null, rows: Record<string, unknown>[], canEdit: boolean): boolean;
  renderStations(host: HTMLElement | null, stations: Record<string, unknown>[], canReview: boolean): boolean;
  renderTimeline(host: HTMLElement | null, rows: Record<string, unknown>[]): boolean;
  renderTemplates(host: HTMLElement | null, rows: Record<string, unknown>[]): boolean;
}

function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function statusClass(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/_/g, "-");
}

function asRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

function renderRows(body: HTMLElement | null, rows: Record<string, unknown>[], canEdit: boolean): boolean {
  if (!(body instanceof HTMLElement)) return false;
  if (!Array.isArray(rows) || !rows.length) {
    body.innerHTML = `<tr><td colspan="10" class="center-text" style="padding:24px;color:#64748b;">No permits found.</td></tr>`;
    return true;
  }
  body.innerHTML = rows
    .map((row, index) => {
      const permitId = Number(row.id || 0);
      const actions =
        row.allowed_actions && typeof row.allowed_actions === "object"
          ? (row.allowed_actions as Record<string, unknown>)
          : {};
      const allowSubmit = Boolean(actions.submit);
      const allowResubmit = Boolean(actions.resubmit);
      const allowCancel = Boolean(actions.cancel);
      return `
        <tr>
          <td>${index + 1}</td>
          <td style="font-family:monospace;">${esc(row.permit_no || "-")}</td>
          <td><div class="ci-row-title" title="${esc(row.title || "-")}">${esc(row.title || "-")}</div></td>
          <td>${esc(row.project_code || "-")}</td>
          <td>${esc(row.discipline_code || "-")}</td>
          <td><span class="module-crud-status is-${statusClass(row.status_code)}">${esc(row.status_code || "-")}</span></td>
          <td>${esc(formatShamsiDate(row.permit_date))}</td>
          <td>${Number(row.required_station_approved || 0)}/${Number(row.required_station_total || 0)}</td>
          <td>${esc(formatShamsiDateTime(row.updated_at))}</td>
          <td>
            <div class="module-crud-actions">
              ${canEdit ? `<button type="button" class="btn-archive-icon" data-pqc-action="open-edit" data-pqc-id="${permitId}">Edit</button>` : ""}
              <button type="button" class="btn-archive-icon" data-pqc-action="open-detail" data-pqc-id="${permitId}">Details</button>
              ${allowSubmit ? `<button type="button" class="btn-archive-icon" data-pqc-action="submit" data-pqc-id="${permitId}">Submit</button>` : ""}
              ${allowResubmit ? `<button type="button" class="btn-archive-icon" data-pqc-action="resubmit" data-pqc-id="${permitId}">Resubmit</button>` : ""}
              ${allowCancel ? `<button type="button" class="btn-archive-icon" data-pqc-action="cancel" data-pqc-id="${permitId}">Cancel</button>` : ""}
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
  return true;
}

function renderCheckValue(row: Record<string, unknown>): string {
  const checkType = String(row.check_type || "").trim().toUpperCase();
  if (checkType === "BOOLEAN") return String(row.value_bool ?? "-");
  if (checkType === "NUMBER") return String(row.value_number ?? "-");
  if (checkType === "DATE") return String(formatShamsiDate(row.value_date) || "-");
  return String(row.value_text || "-");
}

function renderStations(host: HTMLElement | null, stations: Record<string, unknown>[], canReview: boolean): boolean {
  if (!(host instanceof HTMLElement)) return false;
  if (!stations.length) {
    host.innerHTML = `<div class="permit-qc-empty">No station snapshot.</div>`;
    return true;
  }
  host.innerHTML = stations
    .map((station) => {
      const stationId = Number(station.id || 0);
      const checks = asRows(station.checks);
      const checkRows = checks
        .map(
          (check) => `
            <tr>
              <td>${esc(check.check_code || "-")}</td>
              <td>${esc(check.check_label || "-")}</td>
              <td>${esc(check.check_type || "-")}</td>
              <td>${esc(renderCheckValue(check))}</td>
              <td>${esc(check.note || "-")}</td>
            </tr>
          `
        )
        .join("");
      return `
        <div class="permit-qc-station-card">
          <div class="permit-qc-station-head">
            <strong>${esc(station.station_label || station.station_key || "-")}</strong>
            <span class="module-crud-status is-${statusClass(station.status_code)}">${esc(station.status_code || "-")}</span>
          </div>
          <div class="permit-qc-station-meta">
            <span>Org: ${esc(station.organization_name || station.organization_id || "-")}</span>
            <span>Reviewed: ${esc(formatShamsiDateTime(station.reviewed_at))}</span>
          </div>
          ${
            canReview
              ? `
            <div class="permit-qc-station-actions">
              <button type="button" class="btn-archive-icon" data-pqc-action="review-station" data-pqc-station-id="${stationId}" data-pqc-review-action="approve">Approve</button>
              <button type="button" class="btn-archive-icon" data-pqc-action="review-station" data-pqc-station-id="${stationId}" data-pqc-review-action="return">Return</button>
              <button type="button" class="btn-archive-icon" data-pqc-action="review-station" data-pqc-station-id="${stationId}" data-pqc-review-action="reject">Reject</button>
            </div>
            `
              : ""
          }
          <div class="table-wrap">
            <table class="archive-table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Check</th>
                  <th>Type</th>
                  <th>Value</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>${checkRows || `<tr><td colspan="5" class="text-center muted">No checks.</td></tr>`}</tbody>
            </table>
          </div>
        </div>
      `;
    })
    .join("");
  return true;
}

function renderTimeline(host: HTMLElement | null, rows: Record<string, unknown>[]): boolean {
  if (!(host instanceof HTMLElement)) return false;
  if (!rows.length) {
    host.innerHTML = `<div class="permit-qc-empty">No timeline records.</div>`;
    return true;
  }
  host.innerHTML = rows
    .map(
      (row) => `
      <div class="permit-qc-event">
        <div class="permit-qc-event-head">
          <strong>${esc(row.event_type || "-")}</strong>
          <span>${esc(formatShamsiDateTime(row.created_at))}</span>
        </div>
        <div class="permit-qc-event-meta">${esc(row.created_by_name || row.created_by_id || "-")} | ${esc(row.from_status_code || "-")} -> ${esc(row.to_status_code || "-")}</div>
        <div class="permit-qc-event-note">${esc(row.note || "-")}</div>
      </div>
    `
    )
    .join("");
  return true;
}

function renderTemplates(host: HTMLElement | null, rows: Record<string, unknown>[]): boolean {
  if (!(host instanceof HTMLElement)) return false;
  if (!rows.length) {
    host.innerHTML = `<div class="permit-qc-empty">No templates found.</div>`;
    return true;
  }
  host.innerHTML = rows
    .map((row) => {
      const rowId = Number(row.id || 0);
      const stations = Number(row.station_count || 0);
      const checks = Number(row.check_count || 0);
      const stationRows = asRows(row.stations);
      const stationItems = stationRows
        .map((station) => {
          const stationId = Number(station.id || 0);
          const checkRows = asRows(station.checks);
          const checksText = checkRows
            .map((check) => `${esc(check.check_code || "-")}:${esc(check.check_label || "-")}`)
            .join(", ");
          return `
            <li class="permit-qc-template-station-item">
              <button type="button" class="btn-archive-icon" data-pqc-template-station-select="${stationId}" data-pqc-template-id="${rowId}">
                ${esc(station.station_key || "-")} | ${esc(station.station_label || "-")}
              </button>
              <div class="permit-qc-template-station-checks">${checksText || "-"}</div>
            </li>
          `;
        })
        .join("");
      return `
        <div class="permit-qc-template-card" data-pqc-template-id="${rowId}">
          <div class="permit-qc-template-head">
            <strong>${esc(row.name || "-")}</strong>
            <div class="permit-qc-template-head-actions">
              <button type="button" class="btn-archive-icon" data-pqc-template-select="${rowId}">Select</button>
              <span class="module-crud-status is-${statusClass(row.is_active ? "active" : "inactive")}">${row.is_active ? "Active" : "Inactive"}</span>
            </div>
          </div>
          <div class="permit-qc-template-meta">
            <span>Code: ${esc(row.code || "-")}</span>
            <span>Project: ${esc(row.project_code || "ALL")}</span>
            <span>Discipline: ${esc(row.discipline_code || "ALL")}</span>
            <span>Stations: ${stations}</span>
            <span>Checks: ${checks}</span>
          </div>
          <ul class="permit-qc-template-stations">${stationItems || `<li class="permit-qc-template-station-item">No stations.</li>`}</ul>
        </div>
      `;
    })
    .join("");
  return true;
}

export function createPermitQcStateBridge(): PermitQcStateBridge {
  return {
    esc,
    statusClass,
    renderRows,
    renderStations,
    renderTimeline,
    renderTemplates,
  };
}
