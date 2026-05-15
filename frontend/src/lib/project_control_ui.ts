// @ts-nocheck

import { csvUrl, getSourceReport, listMeasurements, patchMeasurement, transitionMeasurement } from "./project_control_data";

export interface ProjectControlUiDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
  canEdit: () => boolean;
  showToast: (message: string, type?: string) => void;
  cache: Record<string, unknown>;
}

export interface ProjectControlUiBridge {
  onTabOpened(moduleKey: string, tabKey: string, deps: ProjectControlUiDeps): Promise<boolean>;
  initModule(moduleKey: string, deps: ProjectControlUiDeps): Promise<boolean>;
}

const sections = [
  { key: "activity", label: "فعالیت / اندازه‌گیری" },
  { key: "material", label: "مصالح / بالانس" },
];
const DEFAULT_SECTION = "activity";
const state: Record<string, any> = {};
const saveTimers: Record<string, number> = {};

function normalize(v: unknown): string { return String(v ?? "").trim().toLowerCase(); }
function upper(v: unknown): string { return String(v ?? "").trim().toUpperCase(); }
function keyOf(m: unknown, t: unknown): string { return `${normalize(m)}-${normalize(t)}`; }
function esc(v: unknown): string {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
function asArray(v: unknown): any[] { return Array.isArray(v) ? v : []; }
function q(root: HTMLElement, selector: string): HTMLElement | null { return root.querySelector(selector); }
function value(root: HTMLElement, selector: string): string {
  const el = q(root, selector);
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement) return String(el.value || "").trim();
  return "";
}
function rootFor(moduleKey: string, tabKey: string): HTMLElement | null {
  return document.querySelector(`.project-control-root[data-module="${normalize(moduleKey)}"][data-tab="${normalize(tabKey)}"]`);
}
function currentSection(key: string): string {
  return state[key]?.section === "material" ? "material" : DEFAULT_SECTION;
}
function setSection(key: string, raw: unknown): string {
  const section = String(raw || "").trim() === "material" ? "material" : DEFAULT_SECTION;
  state[key] ||= {};
  state[key].section = section;
  return section;
}
async function fetchJson(deps: ProjectControlUiDeps, url: string): Promise<any> {
  const resp = await deps.fetch(url);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data?.ok === false) throw new Error(data?.detail || "گزارش کنترل پروژه دریافت نشد.");
  return data;
}
function reportParams(root: HTMLElement, key: string): URLSearchParams {
  const params = new URLSearchParams();
  params.set("report_section", "material");
  params.set("page_size", value(root, "[data-pc-filter='page_size']") || "50");
  params.set("page", "1");
  const filters = [
    ["project_code", "project"],
    ["discipline_code", "discipline"],
    ["status_code", "status"],
    ["log_date_from", "date_from"],
    ["log_date_to", "date_to"],
    ["search", "search"],
  ];
  for (const [apiKey, uiKey] of filters) {
    const raw = value(root, `[data-pc-filter='${uiKey}']`);
    if (raw) params.set(apiKey, raw);
  }
  return params;
}
function measurementParams(root: HTMLElement): Record<string, unknown> {
  const params: Record<string, unknown> = {
    page_size: value(root, "[data-pc-filter='page_size']") || "50",
    page: 1,
  };
  const filters = [
    ["project_code", "project"],
    ["discipline_code", "discipline"],
    ["date_from", "date_from"],
    ["date_to", "date_to"],
    ["search", "search"],
    ["activity_code", "activity_code"],
    ["qc_status", "qc_status"],
    ["measurement_status", "measurement_status"],
    ["pms_template_code", "pms_template_code"],
  ];
  for (const [apiKey, uiKey] of filters) {
    const raw = value(root, `[data-pc-filter='${uiKey}']`);
    if (raw) params[apiKey] = raw;
  }
  return params;
}
function renderKpis(root: HTMLElement, summary: any, section: string): void {
  const items = section === "activity"
    ? [
        ["کل ردیف‌ها", summary?.total ?? 0],
        ["در انتظار", summary?.draft ?? 0],
        ["اندازه‌گیری‌شده", summary?.measured ?? 0],
        ["نهایی‌شده", summary?.verified ?? 0],
        ["QC مانده", summary?.qc_pending ?? 0],
        ["QC تایید", summary?.qc_passed ?? 0],
        ["پیشرفت تاییدی", summary?.verified_avg_progress_pct ?? "-"],
        ["اختلاف", summary?.progress_delta_pct ?? "-"],
      ]
    : [
        ["کل ردیف‌های مصالح", summary?.total ?? 0],
        ["ورودی", summary?.incoming_quantity ?? 0],
        ["مصرف", summary?.consumed_quantity ?? 0],
        ["تجمعی", summary?.cumulative_quantity ?? 0],
        ["پیوست‌ها", summary?.row_attachment_count ?? 0],
        ["گزارش‌های پیش‌نویس", summary?.draft ?? 0],
        ["گزارش‌های ارسال‌شده", summary?.submitted ?? 0],
        ["گزارش‌های تاییدشده", summary?.verified ?? 0],
      ];
  q(root, "[data-pc-kpis]")!.innerHTML = items.map(([label, val]) => `
    <div class="edms-info-card">
      <div class="edms-info-card-value">${esc(val)}</div>
      <div class="edms-info-card-label">${esc(label)}</div>
    </div>
  `).join("");
}
function statusClass(value: unknown): string {
  const v = upper(value);
  if (["PASSED", "VERIFIED", "CLOSED"].includes(v)) return "success";
  if (["FAILED", "REJECTED"].includes(v)) return "danger";
  if (["MEASURED", "SUBMITTED", "PENDING"].includes(v)) return "warning";
  return "neutral";
}
function qcLabel(value: unknown): string {
  const map: Record<string, string> = {
    PENDING: "در انتظار QC",
    PASSED: "تایید QC",
    FAILED: "رد QC",
    NA: "نیاز ندارد",
  };
  return map[upper(value)] || String(value || "-");
}
function measurementLabel(value: unknown): string {
  const map: Record<string, string> = {
    DRAFT: "در انتظار",
    MEASURED: "اندازه‌گیری‌شده",
    VERIFIED: "نهایی‌شده",
  };
  return map[upper(value)] || String(value || "-");
}
function inputValue(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}
function pmsBadges(row: any): string {
  const steps = asArray(row?.pms_steps);
  if (!steps.length) return `<span class="muted">-</span>`;
  return steps.map((step) => `
    <span class="module-crud-status is-${step?.is_current_step ? "success" : "neutral"}" title="${esc(step?.step_weight_pct ?? "")}">
      ${esc(step?.step_title || step?.step_code || "-")}
    </span>
  `).join(" ");
}
function renderReadOnlyTable(root: HTMLElement, data: any): void {
  const columns = asArray(data.columns);
  const rows = asArray(data.data);
  q(root, "[data-pc-table]")!.innerHTML = `
    <table class="edms-table compact">
      <thead><tr>${columns.map((col) => `<th>${esc(col.label || col.key)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${columns.map((col) => `<td>${esc(row[col.key] ?? "-")}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${Math.max(columns.length, 1)}" class="muted">داده‌ای برای گزارش وجود ندارد.</td></tr>`}</tbody>
    </table>
  `;
  q(root, "[data-pc-count]")!.textContent = `${esc(data.pagination?.total ?? rows.length)} ردیف`;
}
function renderActivityTable(root: HTMLElement, data: any): void {
  const rows = asArray(data.data);
  q(root, "[data-pc-table]")!.innerHTML = `
    <table class="edms-table compact pc-measurement-table">
      <thead>
        <tr>
          <th>گزارش</th><th>فعالیت</th><th>محل</th><th>واحد پیمانکار</th>
          <th>امروز پیمانکار</th><th>تجمعی پیمانکار</th><th>واحد مشاور</th>
          <th>امروز مشاور</th><th>تجمعی مشاور</th><th>پیشرفت اعلامی</th>
          <th>پیشرفت تاییدی</th><th>PMS</th><th>QC</th><th>وضعیت</th><th>اقدامات</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => {
          const locked = upper(row.measurement_status) === "VERIFIED";
          const lockedAttr = locked ? " disabled" : "";
          return `
          <tr data-pcm-row="${esc(row.row_id)}" class="${locked ? "pc-locked-row" : ""}">
            <td><button type="button" class="btn btn-link" data-pc-action="source" data-row-id="${esc(row.row_id)}">${esc(row.log_no || "-")}</button></td>
            <td><b>${esc(row.activity_code || "-")}</b><div class="muted">${esc(row.activity_title || "-")}</div></td>
            <td>${esc(row.location || "-")}</td>
            <td>${esc(row.contractor_unit || "-")}</td>
            <td>${esc(row.contractor_today_quantity ?? "-")}</td>
            <td>${esc(row.contractor_cumulative_quantity ?? "-")}</td>
            <td><input class="form-control compact-input" data-pcm-field="supervisor_unit" data-row-id="${esc(row.row_id)}" value="${esc(inputValue(row.supervisor_unit || row.contractor_unit))}"${lockedAttr}></td>
            <td><input class="form-control compact-input" type="number" min="0" step="0.01" data-pcm-field="supervisor_today_quantity" data-row-id="${esc(row.row_id)}" value="${esc(inputValue(row.supervisor_today_quantity))}"${lockedAttr}></td>
            <td><input class="form-control compact-input" type="number" min="0" step="0.01" data-pcm-field="supervisor_cumulative_quantity" data-row-id="${esc(row.row_id)}" value="${esc(inputValue(row.supervisor_cumulative_quantity))}"${lockedAttr}></td>
            <td>${esc(row.claimed_progress_pct ?? "-")}</td>
            <td><input class="form-control compact-input" type="number" min="0" max="100" step="0.01" data-pcm-field="verified_progress_pct" data-row-id="${esc(row.row_id)}" value="${esc(inputValue(row.verified_progress_pct))}"${lockedAttr}></td>
            <td>${pmsBadges(row)}</td>
            <td>
              <select class="form-control compact-input" data-pcm-field="qc_status" data-row-id="${esc(row.row_id)}"${lockedAttr}>
                ${["PENDING", "PASSED", "FAILED", "NA"].map((v) => `<option value="${v}" ${upper(row.qc_status) === v ? "selected" : ""}>${esc(qcLabel(v))}</option>`).join("")}
              </select>
            </td>
            <td><span class="module-crud-status is-${statusClass(row.measurement_status)}" data-pcm-status-for="${esc(row.row_id)}">${esc(measurementLabel(row.measurement_status || "DRAFT"))}</span></td>
            <td>
              <button type="button" class="btn btn-sm" data-pc-action="finalize" data-row-id="${esc(row.row_id)}"${locked ? " disabled title=\"این ردیف نهایی شده است.\"" : ""}>نهایی‌سازی</button>
            </td>
          </tr>
        `;
        }).join("") || `<tr><td colspan="15" class="muted">ردیف فعالیتی برای اندازه‌گیری وجود ندارد.</td></tr>`}
      </tbody>
    </table>
  `;
  q(root, "[data-pc-count]")!.textContent = `${esc(data.pagination?.total ?? rows.length)} ردیف`;
}
function bindActivityTableActions(root: HTMLElement, key: string, deps: ProjectControlUiDeps): void {
  root.querySelectorAll("[data-pc-action='source']").forEach((button) => {
    if ((button as HTMLElement).dataset.pcBound === "1") return;
    (button as HTMLElement).dataset.pcBound = "1";
    button.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      try {
        renderSourceDrawer(root, await getSourceReport(Number((button as HTMLElement).dataset.rowId || 0), deps));
      } catch (err) {
        deps.showToast(err instanceof Error ? err.message : "گزارش مبدا دریافت نشد.", "error");
      }
    });
  });
  root.querySelectorAll("[data-pc-action='finalize']").forEach((button) => {
    if ((button as HTMLElement).dataset.pcBound === "1") return;
    (button as HTMLElement).dataset.pcBound = "1";
    button.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if ((button as HTMLButtonElement).disabled) return;
      try {
        await transitionMeasurement(Number((button as HTMLElement).dataset.rowId || 0), "VERIFIED", deps);
        deps.showToast("ردیف فعالیت نهایی شد.", "success");
        void load(root, key, deps);
      } catch (err) {
        deps.showToast(err instanceof Error ? err.message : "نهایی‌سازی انجام نشد.", "error");
      }
    });
  });
}
async function load(root: HTMLElement, key: string, deps: ProjectControlUiDeps): Promise<void> {
  const section = currentSection(key);
  syncSectionChrome(root, key);
  if (section === "activity") {
    const data = await listMeasurements(measurementParams(root), deps);
    state[key].data = data;
    renderKpis(root, data.summary || {}, section);
    renderActivityTable(root, data);
    bindActivityTableActions(root, key, deps);
    return;
  }
  const data = await fetchJson(deps, `/api/v1/site-logs/reports/table?${reportParams(root, key)}`);
  state[key].data = data;
  renderKpis(root, data.summary || {}, section);
  renderReadOnlyTable(root, data);
}
function fieldPayload(field: string, raw: string): Record<string, unknown> {
  if (["supervisor_today_quantity", "supervisor_cumulative_quantity", "verified_progress_pct"].includes(field)) {
    return { [field]: raw.trim() ? Number(raw) : null };
  }
  return { [field]: raw.trim() || null };
}
async function saveField(root: HTMLElement, key: string, deps: ProjectControlUiDeps, fieldEl: HTMLInputElement | HTMLSelectElement): Promise<void> {
  const rowId = Number(fieldEl.dataset.rowId || 0);
  const field = String(fieldEl.dataset.pcmField || "");
  if (!rowId || !field) return;
  try {
    const result = await patchMeasurement(rowId, fieldPayload(field, String(fieldEl.value || "")), deps);
    const row = result?.data || {};
    const statusEl = root.querySelector(`[data-pcm-status-for="${rowId}"]`);
    if (statusEl) {
      statusEl.textContent = measurementLabel(row?.measurement_status || "DRAFT");
      statusEl.className = `module-crud-status is-${statusClass(row?.measurement_status)}`;
    }
  } catch (err) {
    deps.showToast(err instanceof Error ? err.message : "ذخیره اندازه‌گیری انجام نشد.", "error");
  }
}
function renderSourceDrawer(root: HTMLElement, payload: any): void {
  const data = payload?.data || {};
  const log = data?.site_log || {};
  const row = data?.row || {};
  q(root, "[data-pc-drawer]")!.innerHTML = `
    <div class="module-drawer open">
      <div class="module-drawer-header">
        <div>
          <h3>گزارش مبدا</h3>
          <p>${esc(log.log_no || "-")} | ${esc(log.status_code || "-")}</p>
        </div>
        <button type="button" class="btn" data-pc-action="close-drawer">بستن</button>
      </div>
      <div class="module-drawer-body">
        <div class="edms-info-grid">
          <div class="edms-info-card"><div class="edms-info-card-label">پروژه</div><div class="edms-info-card-value">${esc(log.project_code || "-")}</div></div>
          <div class="edms-info-card"><div class="edms-info-card-label">سازمان</div><div class="edms-info-card-value">${esc(log.organization_name || "-")}</div></div>
          <div class="edms-info-card"><div class="edms-info-card-label">تاریخ</div><div class="edms-info-card-value">${esc(log.log_date || "-")}</div></div>
          <div class="edms-info-card"><div class="edms-info-card-label">فعالیت</div><div class="edms-info-card-value">${esc(row.activity_code || "-")}</div></div>
        </div>
        <div class="module-card module-card-flat">
          <h4>${esc(row.activity_title || "-")}</h4>
          <p>${esc(log.current_work_summary || log.summary || "-")}</p>
        </div>
      </div>
    </div>
  `;
}
function syncSectionChrome(root: HTMLElement, key: string): void {
  const section = currentSection(key);
  root.dataset.pcSection = section;
  root.querySelectorAll("[data-pc-section]").forEach((btn) => {
    btn.classList.toggle("active", (btn as HTMLElement).dataset.pcSection === section);
  });
  root.querySelectorAll("[data-pc-activity-only]").forEach((el) => {
    (el as HTMLElement).hidden = section !== "activity";
  });
  root.querySelectorAll("[data-pc-material-only]").forEach((el) => {
    (el as HTMLElement).hidden = section !== "material";
  });
  root.querySelectorAll("[data-pc-activity-filter]").forEach((el) => {
    (el as HTMLElement).hidden = section !== "activity";
  });
  root.querySelectorAll("[data-pc-material-filter]").forEach((el) => {
    (el as HTMLElement).hidden = section !== "material";
  });
  const title = q(root, "[data-pc-section-title]");
  if (title) title.textContent = section === "activity" ? "جدول اندازه‌گیری فعالیت‌ها" : "جدول بالانس مصالح";
  const hint = q(root, "[data-pc-section-hint]");
  if (hint) {
    hint.textContent = section === "activity"
      ? "ردیف‌های فعالیت گزارش‌های کارگاهی برای ثبت مقدار مشاور، QC و نهایی‌سازی اندازه‌گیری."
      : "ردیف‌های مصالح گزارش‌های کارگاهی برای کنترل ورودی، مصرف و مانده/تجمعی متریال.";
  }
}
function renderShell(root: HTMLElement, key: string, deps: ProjectControlUiDeps): void {
  if (root.dataset.pcReady === "1") return;
  root.dataset.pcReady = "1";
  setSection(key, state[key]?.section || DEFAULT_SECTION);
  root.innerHTML = `
    <div class="module-card module-card-flat">
      <div class="module-toolbar">
        <div>
          <h3 class="module-title"><span class="material-icons-round">monitoring</span> کنترل پروژه</h3>
          <p class="module-subtitle">دو میز عملیاتی: فعالیت برای اندازه‌گیری و QC، مصالح برای بالانس متریال.</p>
        </div>
        <div class="module-actions">
          <button class="btn btn-primary" data-pc-action="run"><span class="material-icons-round">manage_search</span> اجرای گزارش</button>
          <button class="btn" data-pc-action="csv" data-pc-material-only><span class="material-icons-round">download</span> CSV مصالح</button>
          <button class="btn" data-pc-action="csv-wide" data-pc-activity-only><span class="material-icons-round">download</span> CSV wide</button>
          <button class="btn" data-pc-action="csv-long" data-pc-activity-only><span class="material-icons-round">download</span> CSV long</button>
          <button class="btn" data-pc-action="copy"><span class="material-icons-round">content_copy</span> لینک PowerBI</button>
        </div>
      </div>
      <div class="segmented-control pc-sections">
        ${sections.map((s) => `<button type="button" class="${s.key === currentSection(key) ? "active" : ""}" data-pc-section="${esc(s.key)}">${esc(s.label)}</button>`).join("")}
      </div>
      <div class="module-filter-bar compact pc-filter-grid">
        <input class="form-control pc-filter-wide" data-pc-filter="search" placeholder="جستجو در شماره، سازمان، قرارداد، فعالیت یا مصالح...">
        <input class="form-control" data-pc-filter="project" placeholder="کد پروژه">
        <input class="form-control" data-pc-filter="discipline" placeholder="دیسیپلین">
        <select class="form-control" data-pc-filter="status" data-pc-material-filter>
          <option value="">همه وضعیت‌های گزارش</option>
          <option value="DRAFT">پیش‌نویس</option>
          <option value="SUBMITTED">ارسال‌شده</option>
          <option value="VERIFIED">تاییدشده</option>
          <option value="CLOSED">بسته‌شده</option>
        </select>
        <input class="form-control" type="date" data-pc-filter="date_from">
        <input class="form-control" type="date" data-pc-filter="date_to">
        <input class="form-control" data-pc-filter="activity_code" data-pc-activity-filter placeholder="کد فعالیت">
        <input class="form-control" data-pc-filter="pms_template_code" data-pc-activity-filter placeholder="PMS">
        <select class="form-control" data-pc-filter="qc_status" data-pc-activity-filter><option value="">همه QC</option><option>PENDING</option><option>PASSED</option><option>FAILED</option><option>NA</option></select>
        <select class="form-control" data-pc-filter="measurement_status" data-pc-activity-filter><option value="">همه اندازه‌گیری‌ها</option><option>DRAFT</option><option>MEASURED</option><option>VERIFIED</option></select>
        <select class="form-control" data-pc-filter="page_size"><option>50</option><option>100</option><option>200</option></select>
      </div>
      <div class="edms-info-grid" data-pc-kpis></div>
      <div class="module-table-title pc-table-title">
        <div>
          <b data-pc-section-title>جدول اندازه‌گیری فعالیت‌ها</b>
          <p data-pc-section-hint class="module-subtitle">ردیف‌های فعالیت گزارش‌های کارگاهی برای ثبت مقدار مشاور، QC و نهایی‌سازی اندازه‌گیری.</p>
        </div>
        <b data-pc-count>0 ردیف</b>
      </div>
      <div class="table-responsive" data-pc-table></div>
      <div data-pc-drawer></div>
    </div>
  `;
  syncSectionChrome(root, key);
  root.addEventListener("click", async (ev) => {
    const target = ev.target as HTMLElement;
    const sectionEl = target.closest("[data-pc-section]") as HTMLElement | null;
    if (sectionEl) {
      setSection(key, sectionEl.dataset.pcSection);
      syncSectionChrome(root, key);
      void load(root, key, deps);
      return;
    }
    const actionEl = target.closest("[data-pc-action]") as HTMLElement | null;
    if (!actionEl) return;
    const action = actionEl.dataset.pcAction || "";
    if (action === "run") void load(root, key, deps);
    if (action === "csv") {
      if (currentSection(key) === "activity") window.open(csvUrl("wide", measurementParams(root)), "_blank");
      else window.open(`/api/v1/site-logs/reports/table.csv?${reportParams(root, key)}`, "_blank");
    }
    if (action === "csv-wide") window.open(csvUrl("wide", measurementParams(root)), "_blank");
    if (action === "csv-long") window.open(csvUrl("long", measurementParams(root)), "_blank");
    if (action === "copy") {
      const url = currentSection(key) === "activity"
        ? `${window.location.origin}${csvUrl("long", measurementParams(root))}`
        : `${window.location.origin}/api/v1/site-logs/reports/table.csv?${reportParams(root, key)}`;
      navigator.clipboard?.writeText(url);
      deps.showToast("لینک فیلترشده برای PowerBI کپی شد.", "success");
    }
    if (action === "finalize") {
      try {
        await transitionMeasurement(Number(actionEl.dataset.rowId || 0), "VERIFIED", deps);
        deps.showToast("ردیف فعالیت نهایی شد.", "success");
        void load(root, key, deps);
      } catch (err) {
        deps.showToast(err instanceof Error ? err.message : "نهایی‌سازی انجام نشد.", "error");
      }
    }
    if (action === "source") {
      try {
        renderSourceDrawer(root, await getSourceReport(Number(actionEl.dataset.rowId || 0), deps));
      } catch (err) {
        deps.showToast(err instanceof Error ? err.message : "گزارش مبدا دریافت نشد.", "error");
      }
    }
    if (action === "close-drawer") q(root, "[data-pc-drawer]")!.innerHTML = "";
  });
  root.addEventListener("change", (ev) => {
    const target = ev.target as HTMLElement;
    if (target.matches("[data-pc-filter]")) void load(root, key, deps);
    if (target.matches("[data-pcm-field]")) void saveField(root, key, deps, target as HTMLInputElement | HTMLSelectElement);
  });
  root.addEventListener("input", (ev) => {
    const target = ev.target as HTMLInputElement;
    if (!target.matches("[data-pcm-field]")) return;
    const timerKey = `${target.dataset.rowId}:${target.dataset.pcmField}`;
    window.clearTimeout(saveTimers[timerKey]);
    saveTimers[timerKey] = window.setTimeout(() => void saveField(root, key, deps, target), 320);
  });
}
async function open(moduleKey: string, tabKey: string, deps: ProjectControlUiDeps): Promise<boolean> {
  const root = rootFor(moduleKey, tabKey);
  if (!root) return false;
  const key = keyOf(moduleKey, tabKey);
  setSection(key, state[key]?.section || DEFAULT_SECTION);
  renderShell(root, key, deps);
  await load(root, key, deps);
  return true;
}
export function createProjectControlUiBridge(): ProjectControlUiBridge {
  return {
    async onTabOpened(moduleKey, tabKey, deps) {
      return open(moduleKey, tabKey, deps);
    },
    async initModule(moduleKey, deps) {
      const roots = document.querySelectorAll(`.project-control-root[data-module="${normalize(moduleKey)}"][data-tab]`);
      for (const root of Array.from(roots)) {
        await open(moduleKey, (root as HTMLElement).dataset.tab || "control", deps);
      }
      return roots.length > 0;
    },
  };
}
