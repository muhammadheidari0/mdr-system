// @ts-nocheck
import { createPermitQcDataBridge } from "./permit_qc_data";
import { createPermitQcFormBridge } from "./permit_qc_form";
import { createPermitQcStateBridge } from "./permit_qc_state";

export interface PermitQcUiDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
  canEdit: () => boolean;
  showToast: (message: string, type?: string) => void;
  cache: Record<string, unknown>;
}

export interface PermitQcUiBridge {
  onTabOpened(moduleKey: string, tabKey: string, deps: PermitQcUiDeps): Promise<boolean>;
  initModule(moduleKey: string, deps: PermitQcUiDeps): Promise<boolean>;
  initConsultantTemplateSettings(): Promise<boolean>;
}

const dataBridge = createPermitQcDataBridge();
const formBridge = createPermitQcFormBridge();
const stateBridge = createPermitQcStateBridge();

const MODULE_STATE: Record<string, Record<string, unknown>> = {};
const TEMPLATE_STATE: {
  rows: Record<string, unknown>[];
  selectedTemplateId: number;
  selectedStationId: number;
} = {
  rows: [],
  selectedTemplateId: 0,
  selectedStationId: 0,
};
let actionsBound = false;
let templateSettingsBound = false;

function normalize(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function upper(value: unknown): string {
  return String(value ?? "").trim().toUpperCase();
}

function keyOf(moduleKey: string): string {
  return normalize(moduleKey);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

function getElement(id: string): HTMLElement | null {
  try {
    return document.getElementById(id);
  } catch {
    return null;
  }
}

function closePermitRowMenus(exceptMenu: HTMLElement | null = null): void {
  document.querySelectorAll<HTMLElement>(".archive-row-menu.is-open[data-pqc-row-menu]").forEach((menu) => {
    if (exceptMenu && menu === exceptMenu) return;
    menu.classList.remove("is-open");
    const trigger = menu.querySelector<HTMLElement>("[data-pqc-action='toggle-row-menu']");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  });
}

function togglePermitRowMenu(triggerEl: HTMLElement): void {
  const menu = triggerEl.closest<HTMLElement>("[data-pqc-row-menu]");
  if (!(menu instanceof HTMLElement)) return;
  const willOpen = !menu.classList.contains("is-open");
  closePermitRowMenus(menu);
  menu.classList.toggle("is-open", willOpen);
  triggerEl.setAttribute("aria-expanded", willOpen ? "true" : "false");
}

function inputValue(id: string): string {
  const el = getElement(id);
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
    return String(el.value || "").trim();
  }
  return "";
}

function setInputValue(id: string, value: unknown): void {
  const el = getElement(id);
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
    el.value = String(value ?? "");
  }
}

function ensureState(moduleKey: string): Record<string, unknown> {
  const key = keyOf(moduleKey);
  if (!MODULE_STATE[key]) {
    MODULE_STATE[key] = {
      initialized: false,
      actions: {},
      selectedPermitId: 0,
      rows: [],
    };
  }
  return MODULE_STATE[key];
}

function setLoading(moduleKey: string, loading: boolean): void {
  const loadingEl = getElement(`pqc-loading-${keyOf(moduleKey)}`);
  if (!(loadingEl instanceof HTMLElement)) return;
  loadingEl.style.display = loading ? "inline-flex" : "none";
}

function renderModuleShell(moduleKey: string): void {
  const roots = Array.from(
    document.querySelectorAll(`.permit-qc-root[data-module="${normalize(moduleKey)}"][data-tab="permit-qc"]`)
  );
  if (!roots.length) return;
  roots.forEach((root) => {
    const key = keyOf(moduleKey);
    if (root.dataset.pqcReady === "1") return;
    root.innerHTML = `
      <div class="archive-card permit-qc-shell" data-pqc-module="${key}">
        <div class="module-panel-header">
          <h3 class="archive-title">
            <span class="material-icons-round">verified</span>
            پرمیت + کنترل کیفیت
          </h3>
          <p class="archive-subtitle">ثبت، ارسال و بررسی پرمیت‌ها به‌همراه ایستگاه‌ها و آیتم‌های کنترلی.</p>
        </div>

        <div class="module-crud-toolbar">
          <div class="module-crud-toolbar-left">
            <button type="button" class="btn btn-primary" data-pqc-action="open-create" data-pqc-module="${key}">
              <span class="material-icons-round">add</span>پرمیت جدید
            </button>
            <button type="button" class="btn-archive-icon" data-pqc-action="refresh" data-pqc-module="${key}" title="به‌روزرسانی">
              <span class="material-icons-round">refresh</span>
            </button>
            <span id="pqc-loading-${key}" class="permit-qc-loading" style="display:none;">در حال بارگذاری...</span>
          </div>
          <div class="module-crud-toolbar-right">
            <select id="pqc-filter-status-${key}" class="module-crud-select"></select>
            <input id="pqc-filter-project-${key}" class="module-crud-input" type="text" placeholder="کد پروژه">
            <input id="pqc-filter-discipline-${key}" class="module-crud-input" type="text" placeholder="کد دیسیپلین">
            <input id="pqc-filter-permit-${key}" class="module-crud-input" type="text" placeholder="شماره پرمیت">
          </div>
        </div>

        <div class="module-crud-table-wrap">
          <table class="module-crud-table">
            <thead>
              <tr>
                <th style="width:58px;">#</th>
                <th style="width:180px;">شماره پرمیت</th>
                <th>عنوان</th>
                <th style="width:120px;">پروژه</th>
                <th style="width:120px;">دیسیپلین</th>
                <th style="width:140px;">وضعیت</th>
                <th style="width:130px;">تاریخ</th>
                <th style="width:120px;">پیشرفت</th>
                <th style="width:160px;">آخرین بروزرسانی</th>
                <th style="width:260px;">عملیات</th>
              </tr>
            </thead>
            <tbody id="pqc-list-body-${key}"></tbody>
          </table>
        </div>

        <div id="pqc-drawer-${key}" class="permit-qc-drawer" hidden>
          <div class="permit-qc-drawer-header">
            <strong id="pqc-drawer-title-${key}">پرمیت</strong>
            <div class="permit-qc-drawer-actions">
              <button type="button" class="btn btn-secondary" data-pqc-action="close-drawer" data-pqc-module="${key}">بستن</button>
              <button type="button" class="btn btn-primary" data-pqc-action="save-form" data-pqc-module="${key}">ذخیره</button>
            </div>
          </div>

          <input id="pqc-form-id-${key}" type="hidden" value="">
          <div class="permit-qc-form-grid">
            <input id="pqc-form-no-${key}" class="module-crud-input" placeholder="شماره پرمیت">
            <input id="pqc-form-title-${key}" class="module-crud-input" placeholder="عنوان">
            <input id="pqc-form-project-${key}" class="module-crud-input" placeholder="کد پروژه">
            <input id="pqc-form-discipline-${key}" class="module-crud-input" placeholder="کد دیسیپلین">
            <input id="pqc-form-date-${key}" class="module-crud-input" type="date">
            <input id="pqc-form-template-id-${key}" class="module-crud-input" type="number" min="1" placeholder="شناسه الگو (اختیاری)">
            <input id="pqc-form-consultant-org-${key}" class="module-crud-input" type="number" min="1" placeholder="شناسه سازمان مشاور (اختیاری)">
            <input id="pqc-form-wall-${key}" class="module-crud-input" placeholder="نام دیوار">
            <input id="pqc-form-floor-${key}" class="module-crud-input" placeholder="طبقه">
            <input id="pqc-form-elev-start-${key}" class="module-crud-input" placeholder="تراز شروع">
            <input id="pqc-form-elev-end-${key}" class="module-crud-input" placeholder="تراز پایان">
            <textarea id="pqc-form-description-${key}" class="module-crud-textarea" placeholder="شرح"></textarea>
          </div>

          <div class="permit-qc-detail-grid">
            <div>
              <h4>ایستگاه‌های کنترل</h4>
              <div id="pqc-stations-${key}" class="permit-qc-stations"></div>
            </div>
            <div>
              <h4>پیوست‌ها</h4>
              <div class="permit-qc-attachment-upload">
                <input id="pqc-attachment-file-${key}" type="file">
                <button type="button" class="btn btn-secondary" data-pqc-action="upload-attachment" data-pqc-module="${key}">بارگذاری</button>
              </div>
              <div id="pqc-attachments-${key}" class="permit-qc-attachments"></div>
              <h4>گردش وضعیت</h4>
              <div id="pqc-timeline-${key}" class="permit-qc-timeline"></div>
            </div>
          </div>
        </div>
      </div>
    `;
    root.dataset.pqcReady = "1";
  });
}

function toggleDrawer(moduleKey: string, show: boolean): void {
  const drawer = getElement(`pqc-drawer-${keyOf(moduleKey)}`);
  if (!(drawer instanceof HTMLElement)) return;
  drawer.hidden = !show;
}

function updateQuickStats(moduleKey: string, rows: Record<string, unknown>[]): void {
  const isConsultant = normalize(moduleKey) === "consultant";
  const ids = isConsultant
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
  const statusOpen = new Set(["DRAFT", "SUBMITTED", "UNDER_REVIEW", "RETURNED"]);
  const waiting = new Set(["SUBMITTED", "UNDER_REVIEW", "RETURNED"]);
  const values = {
    total: rows.length,
    open: rows.filter((row) => statusOpen.has(upper(row.status_code))).length,
    waiting: rows.filter((row) => waiting.has(upper(row.status_code))).length,
    overdue: 0,
  };
  Object.entries(ids).forEach(([key, id]) => {
    const el = getElement(id);
    if (el) el.textContent = String(values[key] ?? 0);
  });
}

function renderAttachments(moduleKey: string, rows: Record<string, unknown>[]): void {
  const host = getElement(`pqc-attachments-${keyOf(moduleKey)}`);
  if (!(host instanceof HTMLElement)) return;
  if (!rows.length) {
    host.innerHTML = `<div class="permit-qc-empty">پیوستی ثبت نشده است.</div>`;
    return;
  }
  host.innerHTML = rows
    .map((row) => {
      const id = Number(row.id || 0);
      const module = keyOf(moduleKey);
      return `
        <div class="permit-qc-attachment-row">
          <a href="/api/v1/permit-qc/attachments/${id}/download?module_key=${module}" target="_blank" rel="noopener">${stateBridge.esc(row.file_name || "-")}</a>
          <button type="button" class="btn-archive-icon" data-pqc-action="delete-attachment" data-pqc-module="${module}" data-pqc-attachment-id="${id}">حذف</button>
        </div>
      `;
    })
    .join("");
}

async function loadCatalog(moduleKey: string, deps: PermitQcUiDeps): Promise<void> {
  const key = keyOf(moduleKey);
  const state = ensureState(moduleKey);
  const catalog = asRecord(await dataBridge.catalog(moduleKey, deps));
  state.actions = asRecord(catalog.actions);
  const statuses = Array.isArray(catalog.statuses) ? catalog.statuses : [];
  const select = getElement(`pqc-filter-status-${key}`);
  if (select instanceof HTMLSelectElement) {
    const options = [`<option value="">All Statuses</option>`];
    statuses.forEach((status) => {
      options.push(`<option value="${stateBridge.esc(status)}">${stateBridge.esc(status)}</option>`);
    });
    select.innerHTML = options.join("");
  }
}

async function loadList(moduleKey: string, deps: PermitQcUiDeps): Promise<void> {
  const key = keyOf(moduleKey);
  const state = ensureState(moduleKey);
  setLoading(moduleKey, true);
  try {
    const body = asRecord(
      await dataBridge.list(
        {
          module_key: key,
          status_code: inputValue(`pqc-filter-status-${key}`),
          project_code: inputValue(`pqc-filter-project-${key}`),
          discipline_code: inputValue(`pqc-filter-discipline-${key}`),
          permit_no: inputValue(`pqc-filter-permit-${key}`),
          skip: 0,
          limit: 200,
        },
        deps
      )
    );
    const rows = asRows(body.data);
    state.rows = rows;
    stateBridge.renderRows(getElement(`pqc-list-body-${key}`), rows, deps.canEdit());
    updateQuickStats(moduleKey, rows);
  } finally {
    setLoading(moduleKey, false);
  }
}

function clearForm(moduleKey: string): void {
  const key = keyOf(moduleKey);
  [
    `pqc-form-id-${key}`,
    `pqc-form-no-${key}`,
    `pqc-form-title-${key}`,
    `pqc-form-project-${key}`,
    `pqc-form-discipline-${key}`,
    `pqc-form-date-${key}`,
    `pqc-form-template-id-${key}`,
    `pqc-form-consultant-org-${key}`,
    `pqc-form-wall-${key}`,
    `pqc-form-floor-${key}`,
    `pqc-form-elev-start-${key}`,
    `pqc-form-elev-end-${key}`,
    `pqc-form-description-${key}`,
  ].forEach((id) => setInputValue(id, ""));
}

function fillForm(moduleKey: string, row: Record<string, unknown>): void {
  const key = keyOf(moduleKey);
  setInputValue(`pqc-form-id-${key}`, row.id || "");
  setInputValue(`pqc-form-no-${key}`, row.permit_no || "");
  setInputValue(`pqc-form-title-${key}`, row.title || "");
  setInputValue(`pqc-form-project-${key}`, row.project_code || "");
  setInputValue(`pqc-form-discipline-${key}`, row.discipline_code || "");
  setInputValue(`pqc-form-date-${key}`, String(row.permit_date || "").slice(0, 10));
  setInputValue(`pqc-form-template-id-${key}`, row.template_id || "");
  setInputValue(`pqc-form-consultant-org-${key}`, row.consultant_org_id || "");
  setInputValue(`pqc-form-wall-${key}`, row.wall_name || "");
  setInputValue(`pqc-form-floor-${key}`, row.floor_label || "");
  setInputValue(`pqc-form-elev-start-${key}`, row.elevation_start || "");
  setInputValue(`pqc-form-elev-end-${key}`, row.elevation_end || "");
  setInputValue(`pqc-form-description-${key}`, row.description || "");
}

async function openDetail(moduleKey: string, permitId: number, deps: PermitQcUiDeps): Promise<void> {
  const key = keyOf(moduleKey);
  const state = ensureState(moduleKey);
  const body = asRecord(await dataBridge.get(permitId, key, deps));
  const data = asRecord(body.data);
  state.selectedPermitId = Number(data.id || 0);
  fillForm(moduleKey, data);
  toggleDrawer(moduleKey, true);
  const actions = asRecord(data.allowed_actions);
  const canReview = Boolean(actions.review);
  stateBridge.renderStations(getElement(`pqc-stations-${key}`), asRows(data.stations), canReview);
  stateBridge.renderTimeline(getElement(`pqc-timeline-${key}`), asRows(data.timeline));
  renderAttachments(moduleKey, asRows(data.attachments));
}

function moduleFromActionElement(actionEl: HTMLElement): string | null {
  const explicit = normalize(actionEl.dataset.pqcModule);
  if (explicit) return explicit;
  const card = actionEl.closest("[data-pqc-module]");
  if (!card) return null;
  return normalize(card.getAttribute("data-pqc-module"));
}

function buildFormPayload(moduleKey: string): Record<string, unknown> {
  const key = keyOf(moduleKey);
  return {
    permit_no: inputValue(`pqc-form-no-${key}`),
    permit_date: inputValue(`pqc-form-date-${key}`),
    title: inputValue(`pqc-form-title-${key}`),
    description: inputValue(`pqc-form-description-${key}`),
    wall_name: inputValue(`pqc-form-wall-${key}`),
    floor_label: inputValue(`pqc-form-floor-${key}`),
    elevation_start: inputValue(`pqc-form-elev-start-${key}`),
    elevation_end: inputValue(`pqc-form-elev-end-${key}`),
    project_code: inputValue(`pqc-form-project-${key}`),
    discipline_code: inputValue(`pqc-form-discipline-${key}`),
    template_id: inputValue(`pqc-form-template-id-${key}`),
    consultant_org_id: inputValue(`pqc-form-consultant-org-${key}`),
  };
}

function renderTemplateSettingsRoot(): void {
  const root = getElement("consultantPermitQcTemplateRoot");
  if (!(root instanceof HTMLElement) || root.dataset.pqcTemplatesReady === "1") return;
  root.innerHTML = `
    <div class="permit-qc-template-shell">
      <div class="module-crud-toolbar">
        <div class="module-crud-toolbar-left">
          <button type="button" class="btn btn-primary" data-pqc-template-action="save-template">ذخیره الگو</button>
          <button type="button" class="btn btn-secondary" data-pqc-template-action="activate-template">اعمال وضعیت</button>
          <button type="button" class="btn-archive-icon" data-pqc-template-action="refresh" title="به‌روزرسانی">
            <span class="material-icons-round">refresh</span>
          </button>
        </div>
        <div class="module-crud-toolbar-right">
          <input id="pqc-template-id" class="module-crud-input" type="number" min="1" placeholder="شناسه الگو">
          <input id="pqc-template-code" class="module-crud-input" placeholder="کد الگو">
          <input id="pqc-template-name" class="module-crud-input" placeholder="نام الگو">
          <input id="pqc-template-description" class="module-crud-input" placeholder="شرح (اختیاری)">
          <input id="pqc-template-project" class="module-crud-input" placeholder="کد پروژه (اختیاری)">
          <input id="pqc-template-discipline" class="module-crud-input" placeholder="کد دیسیپلین (اختیاری)">
          <label class="permit-qc-inline-check"><input id="pqc-template-active" type="checkbox" checked> فعال</label>
          <label class="permit-qc-inline-check"><input id="pqc-template-default" type="checkbox"> پیش‌فرض</label>
        </div>
      </div>

      <div class="permit-qc-template-editor-grid">
        <div class="permit-qc-template-editor-card">
          <h4>ایستگاه الگو</h4>
          <div class="permit-qc-template-form-grid">
            <input id="pqc-station-id" class="module-crud-input" type="number" min="1" placeholder="شناسه ایستگاه (برای ویرایش)">
            <input id="pqc-station-template-id" class="module-crud-input" type="number" min="1" placeholder="شناسه الگو">
            <input id="pqc-station-key" class="module-crud-input" placeholder="کلید ایستگاه">
            <input id="pqc-station-label" class="module-crud-input" placeholder="عنوان ایستگاه">
            <input id="pqc-station-org-id" class="module-crud-input" type="number" min="1" placeholder="شناسه سازمان (اختیاری)">
            <input id="pqc-station-sort" class="module-crud-input" type="number" value="0" placeholder="ترتیب نمایش">
            <label class="permit-qc-inline-check"><input id="pqc-station-required" type="checkbox" checked> اجباری</label>
            <label class="permit-qc-inline-check"><input id="pqc-station-active" type="checkbox" checked> فعال</label>
          </div>
          <div class="module-crud-form-actions">
            <button type="button" class="btn btn-secondary" data-pqc-template-action="save-station">ذخیره ایستگاه</button>
          </div>
        </div>

        <div class="permit-qc-template-editor-card">
          <h4>آیتم کنترل الگو</h4>
          <div class="permit-qc-template-form-grid">
            <input id="pqc-check-id" class="module-crud-input" type="number" min="1" placeholder="شناسه کنترل (برای ویرایش)">
            <input id="pqc-check-template-id" class="module-crud-input" type="number" min="1" placeholder="شناسه الگو">
            <input id="pqc-check-station-id" class="module-crud-input" type="number" min="1" placeholder="شناسه ایستگاه">
            <input id="pqc-check-code" class="module-crud-input" placeholder="کد کنترل">
            <input id="pqc-check-label" class="module-crud-input" placeholder="عنوان کنترل">
            <select id="pqc-check-type" class="module-crud-select">
              <option value="BOOLEAN">بولی</option>
              <option value="TEXT">متنی</option>
              <option value="NUMBER">عددی</option>
              <option value="DATE">تاریخ</option>
            </select>
            <input id="pqc-check-sort" class="module-crud-input" type="number" value="0" placeholder="ترتیب نمایش">
            <label class="permit-qc-inline-check"><input id="pqc-check-required" type="checkbox" checked> اجباری</label>
            <label class="permit-qc-inline-check"><input id="pqc-check-active" type="checkbox" checked> فعال</label>
          </div>
          <div class="module-crud-form-actions">
            <button type="button" class="btn btn-secondary" data-pqc-template-action="save-check">ذخیره کنترل</button>
          </div>
        </div>
      </div>

      <div id="pqc-template-list" class="permit-qc-template-list"></div>
    </div>
  `;
  root.dataset.pqcTemplatesReady = "1";
}

function boolChecked(id: string): boolean {
  const el = getElement(id);
  return el instanceof HTMLInputElement ? Boolean(el.checked) : false;
}

function setBoolChecked(id: string, value: unknown): void {
  const el = getElement(id);
  if (el instanceof HTMLInputElement) {
    el.checked = Boolean(value);
  }
}

function findTemplateRow(templateId: number): Record<string, unknown> | null {
  if (templateId <= 0) return null;
  const row = TEMPLATE_STATE.rows.find((item) => Number(item.id || 0) === templateId);
  return row || null;
}

function findStationRow(templateId: number, stationId: number): Record<string, unknown> | null {
  if (templateId <= 0 || stationId <= 0) return null;
  const templateRow = findTemplateRow(templateId);
  if (!templateRow) return null;
  const stations = asRows(templateRow.stations);
  const station = stations.find((item) => Number(item.id || 0) === stationId);
  return station || null;
}

function fillTemplateForm(templateId: number): void {
  const row = findTemplateRow(templateId);
  if (!row) return;
  TEMPLATE_STATE.selectedTemplateId = templateId;
  setInputValue("pqc-template-id", row.id || "");
  setInputValue("pqc-template-code", row.code || "");
  setInputValue("pqc-template-name", row.name || "");
  setInputValue("pqc-template-description", row.description || "");
  setInputValue("pqc-template-project", row.project_code || "");
  setInputValue("pqc-template-discipline", row.discipline_code || "");
  setBoolChecked("pqc-template-active", Boolean(row.is_active));
  setBoolChecked("pqc-template-default", Boolean(row.is_default));
  setInputValue("pqc-station-template-id", row.id || "");
  setInputValue("pqc-check-template-id", row.id || "");
}

function fillStationForm(templateId: number, stationId: number): void {
  const row = findStationRow(templateId, stationId);
  if (!row) return;
  TEMPLATE_STATE.selectedTemplateId = templateId;
  TEMPLATE_STATE.selectedStationId = stationId;
  setInputValue("pqc-station-id", row.id || "");
  setInputValue("pqc-station-template-id", templateId || "");
  setInputValue("pqc-station-key", row.station_key || "");
  setInputValue("pqc-station-label", row.station_label || "");
  setInputValue("pqc-station-org-id", row.organization_id || "");
  setInputValue("pqc-station-sort", row.sort_order || 0);
  setBoolChecked("pqc-station-required", Boolean(row.is_required));
  setBoolChecked("pqc-station-active", Boolean(row.is_active));
  setInputValue("pqc-check-template-id", templateId || "");
  setInputValue("pqc-check-station-id", stationId || "");
}

async function loadTemplates(): Promise<void> {
  const runtimeFetch = (window as any).fetchWithAuth;
  if (typeof runtimeFetch !== "function") return;
  const body = asRecord(await dataBridge.templates({ fetch: runtimeFetch }));
  const rows = asRows(body.data);
  TEMPLATE_STATE.rows = rows;
  stateBridge.renderTemplates(getElement("pqc-template-list"), rows);
  if (!TEMPLATE_STATE.selectedTemplateId && rows.length) {
    fillTemplateForm(Number(rows[0].id || 0));
  } else if (TEMPLATE_STATE.selectedTemplateId) {
    fillTemplateForm(TEMPLATE_STATE.selectedTemplateId);
  }
}

function bindTemplateSettingsActions(): void {
  if (templateSettingsBound) return;
  document.addEventListener("click", async (event) => {
    const selectTemplateEl = event?.target?.closest?.("[data-pqc-template-select]");
    if (selectTemplateEl) {
      event.preventDefault();
      const templateId = Number(selectTemplateEl.getAttribute("data-pqc-template-select") || 0);
      if (templateId > 0) fillTemplateForm(templateId);
      return;
    }

    const selectStationEl = event?.target?.closest?.("[data-pqc-template-station-select]");
    if (selectStationEl) {
      event.preventDefault();
      const stationId = Number(selectStationEl.getAttribute("data-pqc-template-station-select") || 0);
      const templateId = Number(selectStationEl.getAttribute("data-pqc-template-id") || 0);
      if (templateId > 0 && stationId > 0) {
        fillTemplateForm(templateId);
        fillStationForm(templateId, stationId);
      }
      return;
    }

    const actionEl = event?.target?.closest?.("[data-pqc-template-action]");
    if (!actionEl) return;
    event.preventDefault();
    const action = normalize(actionEl.getAttribute("data-pqc-template-action"));
    const runtimeFetch = (window as any).fetchWithAuth;
    if (typeof runtimeFetch !== "function") return;
    if (action === "refresh") {
      await loadTemplates();
      return;
    }

    if (action === "save-template") {
      const idValue = Number(inputValue("pqc-template-id") || 0);
      const payload: Record<string, unknown> = {
        code: inputValue("pqc-template-code") || null,
        name: inputValue("pqc-template-name"),
        description: inputValue("pqc-template-description") || null,
        project_code: inputValue("pqc-template-project") || null,
        discipline_code: inputValue("pqc-template-discipline") || null,
        is_active: boolChecked("pqc-template-active"),
        is_default: boolChecked("pqc-template-default"),
      };
      if (idValue > 0) payload.id = idValue;
      await dataBridge.upsertTemplate(payload, { fetch: runtimeFetch });
      await loadTemplates();
      return;
    }

    if (action === "activate-template") {
      const idValue = Number(inputValue("pqc-template-id") || TEMPLATE_STATE.selectedTemplateId || 0);
      if (idValue <= 0) throw new Error("شناسه الگو الزامی است.");
      await dataBridge.activateTemplate(
        idValue,
        {
          is_active: boolChecked("pqc-template-active"),
          is_default: boolChecked("pqc-template-default"),
        },
        { fetch: runtimeFetch }
      );
      await loadTemplates();
      return;
    }

    if (action === "save-station") {
      const templateId = Number(
        inputValue("pqc-station-template-id") ||
          inputValue("pqc-template-id") ||
          TEMPLATE_STATE.selectedTemplateId ||
          0
      );
      if (templateId <= 0) throw new Error("برای ایستگاه، شناسه الگو الزامی است.");
      const payload: Record<string, unknown> = {
        station_key: inputValue("pqc-station-key"),
        station_label: inputValue("pqc-station-label"),
        organization_id: inputValue("pqc-station-org-id") || null,
        is_required: boolChecked("pqc-station-required"),
        is_active: boolChecked("pqc-station-active"),
        sort_order: Number(inputValue("pqc-station-sort") || 0),
      };
      const stationId = Number(inputValue("pqc-station-id") || 0);
      if (stationId > 0) payload.id = stationId;
      await dataBridge.upsertTemplateStation(templateId, payload, { fetch: runtimeFetch });
      TEMPLATE_STATE.selectedTemplateId = templateId;
      await loadTemplates();
      return;
    }

    if (action === "save-check") {
      const templateId = Number(
        inputValue("pqc-check-template-id") ||
          inputValue("pqc-template-id") ||
          TEMPLATE_STATE.selectedTemplateId ||
          0
      );
      if (templateId <= 0) throw new Error("برای کنترل، شناسه الگو الزامی است.");
      const stationId = Number(inputValue("pqc-check-station-id") || TEMPLATE_STATE.selectedStationId || 0);
      if (stationId <= 0) throw new Error("برای کنترل، شناسه ایستگاه الزامی است.");
      const payload: Record<string, unknown> = {
        station_id: stationId,
        check_code: inputValue("pqc-check-code"),
        check_label: inputValue("pqc-check-label"),
        check_type: inputValue("pqc-check-type") || "BOOLEAN",
        is_required: boolChecked("pqc-check-required"),
        is_active: boolChecked("pqc-check-active"),
        sort_order: Number(inputValue("pqc-check-sort") || 0),
      };
      const checkId = Number(inputValue("pqc-check-id") || 0);
      if (checkId > 0) payload.id = checkId;
      await dataBridge.upsertTemplateCheck(templateId, payload, { fetch: runtimeFetch });
      TEMPLATE_STATE.selectedTemplateId = templateId;
      TEMPLATE_STATE.selectedStationId = stationId;
      await loadTemplates();
      return;
    }
  });
  templateSettingsBound = true;
}

function bindActions(): void {
  if (actionsBound) return;
  document.addEventListener("change", (event) => {
    const target = event?.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.id.startsWith("pqc-filter-")) return;
    const moduleKey = target.id.endsWith("-contractor") ? "contractor" : target.id.endsWith("-consultant") ? "consultant" : "";
    if (!moduleKey) return;
    const runtimeFetch = (window as any).fetchWithAuth;
    if (typeof runtimeFetch !== "function") return;
    loadList(moduleKey, {
      fetch: runtimeFetch,
      canEdit: () => true,
      showToast: (msg: string, tone = "info") => (window as any).showToast?.(msg, tone),
      cache: (window as any).CACHE || {},
    }).catch(() => {});
  });

  document.addEventListener("click", async (event) => {
    const actionEl = event?.target?.closest?.("[data-pqc-action]");
    if (!actionEl) {
      closePermitRowMenus();
      return;
    }
    event.preventDefault();
    const moduleKey = moduleFromActionElement(actionEl);
    if (!moduleKey) return;
    const runtimeFetch = (window as any).fetchWithAuth;
    if (typeof runtimeFetch !== "function") return;
    const deps: PermitQcUiDeps = {
      fetch: runtimeFetch,
      canEdit: () => true,
      showToast: (msg: string, tone = "info") => (window as any).showToast?.(msg, tone),
      cache: (window as any).CACHE || {},
    };
    const action = normalize(actionEl.getAttribute("data-pqc-action"));
    if (action !== "toggle-row-menu") {
      closePermitRowMenus();
    }
    const state = ensureState(moduleKey);
    const permitId = Number(actionEl.getAttribute("data-pqc-id") || 0);

    try {
      if (action === "toggle-row-menu") {
        togglePermitRowMenu(actionEl as HTMLElement);
        return;
      }
      if (action === "refresh") {
        await loadList(moduleKey, deps);
        return;
      }
      if (action === "open-create") {
        clearForm(moduleKey);
        state.selectedPermitId = 0;
        toggleDrawer(moduleKey, true);
        return;
      }
      if (action === "close-drawer") {
        toggleDrawer(moduleKey, false);
        return;
      }
      if (action === "save-form") {
        const formPayload = buildFormPayload(moduleKey);
        const currentId = Number(inputValue(`pqc-form-id-${keyOf(moduleKey)}`) || 0);
        if (currentId > 0) {
          const payload = formBridge.buildUpdatePayload(formPayload);
          await dataBridge.update(currentId, payload, deps);
          state.selectedPermitId = currentId;
        } else {
          const payload = formBridge.buildCreatePayload(moduleKey, formPayload);
          const result = asRecord(await dataBridge.create(payload, deps));
          const data = asRecord(result.data);
          state.selectedPermitId = Number(data.id || 0);
        }
        await loadList(moduleKey, deps);
        if (Number(state.selectedPermitId || 0) > 0) {
          await openDetail(moduleKey, Number(state.selectedPermitId || 0), deps);
        }
        return;
      }
      if (action === "open-detail" || action === "open-edit") {
        if (permitId <= 0) return;
        await openDetail(moduleKey, permitId, deps);
        return;
      }
      if (action === "submit") {
        if (permitId <= 0) return;
        await dataBridge.submit(permitId, deps);
        await loadList(moduleKey, deps);
        await openDetail(moduleKey, permitId, deps);
        return;
      }
      if (action === "resubmit") {
        if (permitId <= 0) return;
        await dataBridge.resubmit(permitId, deps);
        await loadList(moduleKey, deps);
        await openDetail(moduleKey, permitId, deps);
        return;
      }
      if (action === "cancel") {
        if (permitId <= 0) return;
        const note = window.prompt("یادداشت لغو (اختیاری)", "") || "";
        await dataBridge.cancel(permitId, note, deps);
        await loadList(moduleKey, deps);
        return;
      }
      if (action === "review-station") {
        const stationId = Number(actionEl.getAttribute("data-pqc-station-id") || 0);
        const reviewAction = normalize(actionEl.getAttribute("data-pqc-review-action"));
        const currentPermit = Number(state.selectedPermitId || 0);
        if (currentPermit <= 0 || stationId <= 0) return;
        const note = window.prompt("یادداشت بررسی", reviewAction === "approve" ? "" : "الزامی") || "";
        const payload = formBridge.buildReviewPayload({
          station_id: stationId,
          action: reviewAction,
          note,
          checks: [],
        });
        await dataBridge.review(currentPermit, payload, deps);
        await loadList(moduleKey, deps);
        await openDetail(moduleKey, currentPermit, deps);
        return;
      }
      if (action === "upload-attachment") {
        const currentPermit = Number(state.selectedPermitId || 0);
        if (currentPermit <= 0) return;
        const input = getElement(`pqc-attachment-file-${keyOf(moduleKey)}`) as HTMLInputElement | null;
        const file = input?.files?.[0];
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);
        formData.append("file_kind", "attachment");
        await dataBridge.uploadAttachment(currentPermit, moduleKey, formData, deps);
        await openDetail(moduleKey, currentPermit, deps);
        return;
      }
      if (action === "delete-attachment") {
        const currentPermit = Number(state.selectedPermitId || 0);
        const attachmentId = Number(actionEl.getAttribute("data-pqc-attachment-id") || 0);
        if (currentPermit <= 0 || attachmentId <= 0) return;
        await dataBridge.deleteAttachment(currentPermit, moduleKey, attachmentId, deps);
        await openDetail(moduleKey, currentPermit, deps);
      }
    } catch (error) {
      deps.showToast(String((error as any)?.message || "عملیات پرمیت ناموفق بود."), "error");
    }
  });

  actionsBound = true;
}

async function initModule(moduleKey: string, deps: PermitQcUiDeps): Promise<boolean> {
  const module = normalize(moduleKey);
  if (!module) return false;
  const roots = document.querySelectorAll(`.permit-qc-root[data-module="${module}"][data-tab="permit-qc"]`);
  if (!roots.length) return false;
  renderModuleShell(module);
  bindActions();
  const state = ensureState(module);
  if (!state.initialized) {
    await loadCatalog(module, deps);
    state.initialized = true;
  }
  await loadList(module, deps);
  return true;
}

async function onTabOpened(moduleKey: string, tabKey: string, deps: PermitQcUiDeps): Promise<boolean> {
  if (normalize(tabKey) !== "permit-qc") return false;
  return initModule(moduleKey, deps);
}

async function initConsultantTemplateSettings(): Promise<boolean> {
  const root = getElement("consultantPermitQcTemplateRoot");
  if (!(root instanceof HTMLElement)) return false;
  renderTemplateSettingsRoot();
  bindTemplateSettingsActions();
  await loadTemplates();
  return true;
}

export function createPermitQcUiBridge(): PermitQcUiBridge {
  return {
    onTabOpened,
    initModule,
    initConsultantTemplateSettings,
  };
}
