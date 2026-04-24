// @ts-nocheck
import { createSiteLogsDataBridge } from "./site_logs_data";
import { createSiteLogsFormBridge } from "./site_logs_form";
import { createSiteLogsStateBridge } from "./site_logs_state";
import { formatShamsiDate, formatShamsiDateTime } from "./persian_datetime";
import { initShamsiDateInputs } from "./shamsi_date_input";

export interface SiteLogsUiDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
  canEdit: () => boolean;
  showToast: (message: string, type?: string) => void;
  cache: Record<string, unknown>;
}

export interface SiteLogsUiBridge {
  onTabOpened(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<boolean>;
  initModule(moduleKey: string, deps: SiteLogsUiDeps): Promise<boolean>;
}

type SectionKind = "manpower" | "equipment" | "activity";
type FormMode = "create" | "edit" | "verify" | "detail";

const dataBridge = createSiteLogsDataBridge();
const formBridge = createSiteLogsFormBridge();
const stateBridge = createSiteLogsStateBridge();

const rowsByKey: Record<string, Record<string, unknown>[]> = {};
const selectedByKey: Record<string, number> = {};
const loadingByKey: Record<string, boolean> = {};
const debounceTimers: Record<string, number | undefined> = {};
const drawerDirtyByKey: Record<string, boolean> = {};
const modeByKey: Record<string, FormMode> = {};
const shamsiRegistryByKey: Record<string, { syncAll: () => void }> = {};
const detailRowByKey: Record<string, Record<string, unknown>> = {};

let catalogCache: Record<string, unknown> | null = null;
let actionsBound = false;
let dualFlowBound = false;

const SECTION_DEFS: Record<
  SectionKind,
  {
    title: string;
    fields: Array<{
      key: string;
      label: string;
      type?: string;
      step?: string;
      group: "base" | "claimed" | "verified" | "note";
      catalog?: string;
      catalogValueKey?: string;
      catalogLabelKey?: string;
    }>;
  }
> = {
  manpower: {
    title: "Ù†ÙØ±Ø§Øª",
    fields: [
      { key: "role_code", label: "Ú©Ø¯ Ù†Ù‚Ø´", group: "base" },
      { key: "role_label", label: "Ø¹Ù†ÙˆØ§Ù† Ù†Ù‚Ø´", group: "base", catalog: "role_catalog", catalogValueKey: "label" },
      { key: "claimed_count", label: "ØªØ¹Ø¯Ø§Ø¯ Ø§Ø¹Ù„Ø§Ù…ÛŒ", type: "number", step: "1", group: "claimed" },
      { key: "claimed_hours", label: "Ø³Ø§Ø¹Ø§Øª Ø§Ø¹Ù„Ø§Ù…ÛŒ", type: "number", step: "0.1", group: "claimed" },
      { key: "verified_count", label: "ØªØ¹Ø¯Ø§Ø¯ ØªØ§ÛŒÛŒØ¯ÛŒ", type: "number", step: "1", group: "verified" },
      { key: "verified_hours", label: "Ø³Ø§Ø¹Ø§Øª ØªØ§ÛŒÛŒØ¯ÛŒ", type: "number", step: "0.1", group: "verified" },
      { key: "note", label: "ØªÙˆØ¶ÛŒØ­Ø§Øª", group: "note" },
    ],
  },
  equipment: {
    title: "ØªØ¬Ù‡ÛŒØ²Ø§Øª",
    fields: [
      { key: "equipment_code", label: "Ú©Ø¯ ØªØ¬Ù‡ÛŒØ²", group: "base" },
      { key: "equipment_label", label: "Ø¹Ù†ÙˆØ§Ù† ØªØ¬Ù‡ÛŒØ²", group: "base", catalog: "equipment_catalog", catalogValueKey: "label" },
      { key: "claimed_status", label: "ÙˆØ¶Ø¹ÛŒØª Ø§Ø¹Ù„Ø§Ù…ÛŒ", group: "claimed", catalog: "equipment_status_catalog", catalogValueKey: "code" },
      { key: "claimed_hours", label: "Ø³Ø§Ø¹Ø§Øª Ø§Ø¹Ù„Ø§Ù…ÛŒ", type: "number", step: "0.1", group: "claimed" },
      { key: "verified_status", label: "ÙˆØ¶Ø¹ÛŒØª ØªØ§ÛŒÛŒØ¯ÛŒ", group: "verified" },
      { key: "verified_hours", label: "Ø³Ø§Ø¹Ø§Øª ØªØ§ÛŒÛŒØ¯ÛŒ", type: "number", step: "0.1", group: "verified" },
      { key: "note", label: "ØªÙˆØ¶ÛŒØ­Ø§Øª", group: "note" },
    ],
  },
  activity: {
    title: "ÙØ¹Ø§Ù„ÛŒØªâ€ŒÙ‡Ø§",
    fields: [
      { key: "activity_code", label: "Ú©Ø¯ ÙØ¹Ø§Ù„ÛŒØª", group: "base" },
      { key: "activity_title", label: "Ø¹Ù†ÙˆØ§Ù† ÙØ¹Ø§Ù„ÛŒØª", group: "base" },
      { key: "claimed_progress_pct", label: "Ù¾ÛŒØ´Ø±ÙØª Ø§Ø¹Ù„Ø§Ù…ÛŒ (%)", type: "number", step: "0.1", group: "claimed" },
      { key: "verified_progress_pct", label: "Ù¾ÛŒØ´Ø±ÙØª ØªØ§ÛŒÛŒØ¯ÛŒ (%)", type: "number", step: "0.1", group: "verified" },
      { key: "note", label: "ØªÙˆØ¶ÛŒØ­Ø§Øª", group: "note" },
    ],
  },
};

function normalize(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function upper(value: unknown): string {
  return String(value ?? "").trim().toUpperCase();
}

function keyOf(moduleKey: unknown, tabKey: unknown): string {
  return `${normalize(moduleKey)}-${normalize(tabKey)}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
}

function getElement(id: string): HTMLElement | null {
  try {
    return document.getElementById(id);
  } catch {
    return null;
  }
}

function getValue(id: string): string {
  const el = getElement(id);
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
    return String(el.value || "").trim();
  }
  return "";
}

function setValue(id: string, value: unknown): void {
  const el = getElement(id);
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
    el.value = String(value ?? "");
  }
}

function boardTitle(moduleKey: string, tabKey: string): string {
  const map: Record<string, string> = {
    "contractor:execution": "گزارش کارگاهی",
    "consultant:inspection": "تایید گزارش کارگاهی",
  };
  return map[`${moduleKey}:${tabKey}`] || "گزارش کارگاهی";
}

function boardCapabilities(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): { canCreate: boolean; canVerify: boolean; canEdit: boolean } {
  const isContractorExecution = normalize(moduleKey) === "contractor" && normalize(tabKey) === "execution";
  const isConsultantInspection = normalize(moduleKey) === "consultant" && normalize(tabKey) === "inspection";
  return {
    canCreate: deps.canEdit() && isContractorExecution,
    canVerify: deps.canEdit() && isConsultantInspection,
    canEdit: deps.canEdit(),
  };
}

function drawerFor(moduleKey: string, tabKey: string): HTMLElement | null {
  return getElement(`sl-drawer-${keyOf(moduleKey, tabKey)}`);
}

function setDrawerDirty(moduleKey: string, tabKey: string, dirty = true): void {
  drawerDirtyByKey[keyOf(moduleKey, tabKey)] = dirty;
}

function openDrawer(moduleKey: string, tabKey: string): void {
  const drawer = drawerFor(moduleKey, tabKey);
  if (!(drawer instanceof HTMLElement)) return;
  drawer.hidden = false;
  drawer.classList.add("is-open");
  document.body.classList.add("ci-drawer-open");
}

function closeDrawer(moduleKey: string, tabKey: string, force = false): boolean {
  const key = keyOf(moduleKey, tabKey);
  if (!force && drawerDirtyByKey[key]) {
    const ok = window.confirm("ØªØºÛŒÛŒØ±Ø§Øª Ø°Ø®ÛŒØ±Ù‡ Ù†Ø´Ø¯Ù‡â€ŒØ§Ù†Ø¯. ÙØ±Ù… Ø¨Ø³ØªÙ‡ Ø´ÙˆØ¯ØŸ");
    if (!ok) return false;
  }
  const drawer = drawerFor(moduleKey, tabKey);
  if (drawer instanceof HTMLElement) {
    drawer.hidden = true;
    drawer.classList.remove("is-open");
  }
  drawerDirtyByKey[key] = false;
  const openCount = document.querySelectorAll(".ci-drawer.is-open").length;
  if (openCount <= 0) document.body.classList.remove("ci-drawer-open");
  return true;
}

function setDrawerTitle(moduleKey: string, tabKey: string, value: string): void {
  const el = getElement(`sl-drawer-title-${keyOf(moduleKey, tabKey)}`);
  if (el) el.textContent = value;
}

function ensureShamsiInputs(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  if (shamsiRegistryByKey[key]) {
    shamsiRegistryByKey[key].syncAll();
    return;
  }
  shamsiRegistryByKey[key] = initShamsiDateInputs([`sl-form-log-date-${key}`]);
  shamsiRegistryByKey[key].syncAll();
}

function canEditField(group: "base" | "claimed" | "verified" | "note", mode: FormMode, capabilities: { canCreate: boolean; canVerify: boolean }): boolean {
  if (mode === "detail") return false;
  if (mode === "verify") return capabilities.canVerify && (group === "verified" || group === "note");
  if (group === "verified" && !capabilities.canVerify) return false;
  return capabilities.canCreate || capabilities.canVerify;
}

function sectionBodyId(section: SectionKind, key: string): string {
  return `sl-form-${section}-body-${key}`;
}

function rowActionsHtml(key: string, section: SectionKind, index: number, removable: boolean): string {
  if (!removable) return "-";
  return `<button type="button" class="btn-archive-icon" data-sl-action="remove-row" data-sl-section="${section}" data-sl-index="${index}">Ø­Ø°Ù</button>`;
}

function optionRowsFromCatalog(key: string): Record<string, unknown>[] {
  return asArray(asRecord(catalogCache)[key]);
}

function optionHtml(
  rows: Record<string, unknown>[],
  valueKey: string,
  labelKey: string,
  placeholder: string,
  current = "",
  fallbackLabel = ""
): string {
  const normalizedCurrent = String(current ?? "").trim();
  let hasCurrent = false;
  const first = `<option value="">${stateBridge.esc(placeholder)}</option>`;
  const extraRows = rows
    .map((row) => {
      const value = String(row[valueKey] ?? "").trim();
      if (!value) return "";
      if (normalizedCurrent && value === normalizedCurrent) hasCurrent = true;
      const selected = value === normalizedCurrent ? " selected" : "";
      const label = String(row[labelKey] ?? value);
      return `<option value="${stateBridge.esc(value)}"${selected}>${stateBridge.esc(label)}</option>`;
    })
    .filter(Boolean)
    .join("");
  const legacyCurrent =
    normalizedCurrent && !hasCurrent
      ? `<option value="${stateBridge.esc(normalizedCurrent)}" selected data-legacy-option="1">${stateBridge.esc(
          fallbackLabel || normalizedCurrent
        )} (مقدار قبلی)</option>`
      : "";
  return first + legacyCurrent + extraRows;
}

function logTypeLabelFa(value: unknown): string {
  const code = upper(value);
  if (code === "DAILY") return "روزانه";
  if (code === "WEEKLY") return "هفتگی";
  if (code === "SAFETY_INCIDENT") return "ایمنی";
  return code || "-";
}

function statusLabelFa(value: unknown): string {
  const code = upper(value);
  if (code === "DRAFT") return "پیش‌نویس";
  if (code === "SUBMITTED") return "ارسال‌شده";
  if (code === "VERIFIED") return "تاییدشده";
  return code || "-";
}

function workflowStatusOptions(current = "DRAFT"): string {
  const rows = optionRowsFromCatalog("workflow_statuses");
  if (!rows.length) {
    return `<option value="DRAFT"${String(current) === "DRAFT" ? " selected" : ""}>پیش‌نویس</option>`;
  }
  return rows
    .map((row) => {
      const code = upper(row.code || "");
      if (!code) return "";
      const selected = code === upper(current) ? " selected" : "";
      return `<option value="${stateBridge.esc(code)}"${selected}>${stateBridge.esc(statusLabelFa(code))}</option>`;
    })
    .join("");
}

function logTypeOptions(current = "DAILY"): string {
  const rows = optionRowsFromCatalog("log_types");
  if (!rows.length) {
    return `<option value="DAILY"${upper(current) === "DAILY" ? " selected" : ""}>روزانه</option>`;
  }
  return rows
    .map((row) => {
      const code = upper(row.code || "");
      if (!code) return "";
      const selected = code === upper(current) ? " selected" : "";
      return `<option value="${stateBridge.esc(code)}"${selected}>${stateBridge.esc(logTypeLabelFa(code))}</option>`;
    })
    .join("");
}

function sectionTableHtml(section: SectionKind, key: string): string {
  const def = SECTION_DEFS[section];
  const header = def.fields
    .map((field) => `<th>${stateBridge.esc(field.label)}</th>`)
    .join("");
  return `
    <section class="ci-form-section">
      <div class="sl-section-header">
        <h4 class="module-crud-form-title">${stateBridge.esc(def.title)}</h4>
        <button type="button" class="btn-archive-icon" data-sl-action="add-row" data-sl-section="${section}">افزودن ردیف</button>
      </div>
      <div class="module-crud-table-wrap">
        <table class="module-crud-table sl-row-table">
          <thead>
            <tr>${header}<th>عملیات</th></tr>
          </thead>
          <tbody id="${sectionBodyId(section, key)}"></tbody>
        </table>
      </div>
    </section>
  `;
}

function buildBoardCard(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): string {
  const key = keyOf(moduleKey, tabKey);
  const title = boardTitle(moduleKey, tabKey);
  const capabilities = boardCapabilities(moduleKey, tabKey, deps);
  const projects = optionRowsFromCatalog("projects");
  const disciplines = optionRowsFromCatalog("disciplines");
  const organizations = optionRowsFromCatalog("organizations");
  const defaultLogType = formBridge.defaultLogType(moduleKey, tabKey);

  return `
    <div class="archive-card site-logs-card" data-module="${moduleKey}" data-tab="${tabKey}">
      <div class="module-panel-header">
        <h3 class="archive-title"><span class="material-icons-round">assignment</span>${stateBridge.esc(title)}</h3>
        <p class="archive-subtitle">ثبت روزانه/هفتگی کارگاه با مدل «اعلام پیمانکار» در برابر «تایید مشاور».</p>
      </div>

      <div class="module-crud-toolbar">
        <div class="module-crud-toolbar-left">
          ${capabilities.canCreate ? `<button type="button" class="btn btn-primary" data-sl-action="open-form">Ú¯Ø²Ø§Ø±Ø´ Ú©Ø§Ø±Ú¯Ø§Ù‡</button>` : ""}
          <button type="button" class="btn-archive-icon" data-sl-action="refresh"><span class="material-icons-round">refresh</span></button>
        </div>
        <div class="module-crud-toolbar-right" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;flex:1 1 100%;min-width:0;width:100%;">
          <select id="sl-filter-project-${key}" class="module-crud-select" data-sl-action="filter-project">${optionHtml(projects, "code", "name", "پروژه")}</select>
          <select id="sl-filter-discipline-${key}" class="module-crud-select" data-sl-action="filter-discipline">${optionHtml(disciplines, "code", "name", "دیسیپلین")}</select>
          <select id="sl-filter-log-type-${key}" class="module-crud-select" data-sl-action="filter-log-type"><option value="">نوع گزارش</option>${logTypeOptions("")}</select>
          <select id="sl-filter-status-${key}" class="module-crud-select" data-sl-action="filter-status"><option value="">وضعیت</option>${workflowStatusOptions("")}</select>
          <input id="sl-filter-search-${key}" class="module-crud-input" type="text" placeholder="جستجو" data-sl-action="filter-search">
        </div>
      </div>

      <div class="module-crud-table-wrap">
        <table class="module-crud-table">
          <thead>
            <tr><th>#</th><th>شماره گزارش</th><th>نوع</th><th>تاریخ</th><th>وضعیت</th><th>نفرات</th><th>تجهیزات</th><th>فعالیت</th><th>سازمان</th><th>عملیات</th></tr>
          </thead>
          <tbody id="sl-tbody-${key}"></tbody>
        </table>
      </div>

      <div id="sl-drawer-${key}" class="ci-drawer sl-drawer" hidden>
        <div class="ci-drawer-backdrop" data-sl-action="drawer-close"></div>
        <aside class="ci-drawer-panel sl-drawer-panel" role="dialog" aria-modal="true" aria-label="فرم گزارش کارگاهی">
          <header class="ci-drawer-header">
            <div id="sl-drawer-title-${key}" class="ci-drawer-title">گزارش کارگاهی</div>
            <button type="button" class="btn-archive-icon" data-sl-action="drawer-close"><span class="material-icons-round">close</span></button>
          </header>
          <div class="ci-drawer-body">
            <div id="sl-form-wrap-${key}" class="module-crud-form-wrap" hidden>
              <input id="sl-form-id-${key}" type="hidden" value="">
              <input id="sl-form-mode-${key}" type="hidden" value="create">
              <div class="module-crud-form-grid">
                <div class="module-crud-form-field">
                  <label for="sl-form-project-${key}">پروژه</label>
                  <select id="sl-form-project-${key}" class="module-crud-select">${optionHtml(projects, "code", "name", "پروژه")}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-discipline-${key}">دیسیپلین</label>
                  <select id="sl-form-discipline-${key}" class="module-crud-select">${optionHtml(disciplines, "code", "name", "دیسیپلین")}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-organization-${key}">سازمان</label>
                  <select id="sl-form-organization-${key}" class="module-crud-select">${optionHtml(organizations, "id", "name", "سازمان")}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-log-type-${key}">نوع گزارش</label>
                  <select id="sl-form-log-type-${key}" class="module-crud-select">${logTypeOptions(defaultLogType)}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-log-date-${key}">تاریخ گزارش</label>
                  <input id="sl-form-log-date-${key}" class="module-crud-input" type="date">
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-weather-${key}">وضعیت جوی</label>
                  <input id="sl-form-weather-${key}" class="module-crud-input" type="text" placeholder="مثلا صاف">
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-status-${key}">وضعیت</label>
                  <select id="sl-form-status-${key}" class="module-crud-select" disabled>${workflowStatusOptions("DRAFT")}</select>
                </div>
                <div class="module-crud-form-field" style="grid-column:1 / -1;">
                  <label for="sl-form-summary-${key}">خلاصه</label>
                  <textarea id="sl-form-summary-${key}" class="module-crud-textarea" placeholder="خلاصه کار انجام‌شده"></textarea>
                </div>
              </div>

              ${sectionTableHtml("manpower", key)}
              ${sectionTableHtml("equipment", key)}
              ${sectionTableHtml("activity", key)}

              <section id="sl-existing-only-${key}" class="ci-form-section" hidden>
                <h4 class="module-crud-form-title">پیوست‌ها</h4>
                <div class="sl-attachment-toolbar">
                  <select id="sl-attachment-section-${key}" class="module-crud-select">
                    <option value="GENERAL">عمومی</option>
                    <option value="MANPOWER">نفرات</option>
                    <option value="EQUIPMENT">تجهیزات</option>
                    <option value="ACTIVITY">فعالیت</option>
                  </select>
                  <select id="sl-attachment-kind-${key}" class="module-crud-select">
                    <option value="attachment">ضمیمه</option>
                    <option value="pdf">PDF</option>
                    <option value="native">فایل اصلی</option>
                  </select>
                  <input id="sl-attachment-file-${key}" type="file">
                  <button type="button" class="btn btn-secondary" data-sl-action="upload-attachment">بارگذاری</button>
                </div>
                <div id="sl-attachments-${key}" style="margin-top:10px;"></div>
              </section>

              <section id="sl-comments-wrap-${key}" class="ci-form-section" hidden>
                <h4 class="module-crud-form-title">یادداشت‌ها</h4>
                <div id="sl-comments-${key}" style="margin-bottom:8px;"></div>
                <div class="sl-comment-box">
                  <input id="sl-comment-input-${key}" class="module-crud-input" type="text" placeholder="متن یادداشت">
                  <button type="button" class="btn btn-secondary" data-sl-action="send-comment">ارسال</button>
                </div>
              </section>

              <div class="module-crud-form-actions">
                <button type="button" class="btn btn-secondary" data-sl-action="close-form">Ø§Ù†ØµØ±Ø§Ù</button>
                ${capabilities.canCreate ? `<button type="button" class="btn btn-primary" data-sl-action="save-form">Ø°Ø®ÛŒØ±Ù‡</button>` : ""}
                ${capabilities.canCreate ? `<button type="button" class="btn btn-primary" data-sl-action="submit-form">Ø§Ø±Ø³Ø§Ù„</button>` : ""}
                ${capabilities.canVerify ? `<button type="button" class="btn btn-primary" data-sl-action="verify-form">ØªØ§ÛŒÛŒØ¯</button>` : ""}
              </div>
            </div>
            <div id="sl-detail-wrap-${key}" class="archive-card sl-detail-wrap" style="display:none;"></div>
          </div>
        </aside>
      </div>
    </div>
  `;
}

function renderSectionRows(moduleKey: string, tabKey: string, section: SectionKind, rows: Record<string, unknown>[], mode: FormMode, capabilities: { canCreate: boolean; canVerify: boolean }): void {
  const key = keyOf(moduleKey, tabKey);
  const body = getElement(sectionBodyId(section, key));
  if (!(body instanceof HTMLElement)) return;
  const normalizedRows = rows.length ? rows : [{}];
  const def = SECTION_DEFS[section];
  const allowRemove = mode !== "detail" && (capabilities.canCreate || capabilities.canVerify);
  body.innerHTML = normalizedRows
    .map((row, index) => {
      const fieldsHtml = def.fields
        .map((field) => {
          const editable = canEditField(field.group, mode, capabilities);
          const disabled = editable ? "" : " disabled";
          const rawValue = String(row[field.key] ?? "");
          if (field.catalog) {
            const valueKey = field.catalogValueKey || "code";
            const labelKey = field.catalogLabelKey || "label";
            const opts = optionHtml(optionRowsFromCatalog(field.catalog), valueKey, labelKey, "انتخاب...", rawValue);
            return `<td><select class="module-crud-select sl-row-input" data-sl-field="${field.key}"${disabled}>${opts}</select></td>`;
          }
          const type = field.type || "text";
          const step = field.step ? ` step="${field.step}"` : "";
          const value = stateBridge.esc(rawValue);
          return `<td><input class="module-crud-input sl-row-input" data-sl-field="${field.key}" type="${type}" value="${value}"${step}${disabled}></td>`;
        })
        .join("");
      return `<tr data-sl-row-index="${index}">${fieldsHtml}<td>${rowActionsHtml(key, section, index, allowRemove)}</td></tr>`;
    })
    .join("");
}

function collectSectionRows(moduleKey: string, tabKey: string, section: SectionKind): Record<string, unknown>[] {
  const key = keyOf(moduleKey, tabKey);
  const body = getElement(sectionBodyId(section, key));
  if (!(body instanceof HTMLElement)) return [];
  const rows: Record<string, unknown>[] = [];
  body.querySelectorAll<HTMLTableRowElement>("tr[data-sl-row-index]").forEach((rowEl, idx) => {
    const row: Record<string, unknown> = { sort_order: idx };
    rowEl.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("[data-sl-field]").forEach((fieldEl) => {
      const field = String(fieldEl.dataset.slField || "").trim();
      if (!field) return;
      row[field] = fieldEl.value;
    });
    rows.push(row);
  });
  return rows;
}

function readForm(moduleKey: string, tabKey: string): Record<string, unknown> {
  const key = keyOf(moduleKey, tabKey);
  return {
    id: Number(getValue(`sl-form-id-${key}`) || 0),
    log_type: getValue(`sl-form-log-type-${key}`),
    project_code: getValue(`sl-form-project-${key}`),
    discipline_code: getValue(`sl-form-discipline-${key}`),
    organization_id: getValue(`sl-form-organization-${key}`),
    log_date: getValue(`sl-form-log-date-${key}`),
    weather: getValue(`sl-form-weather-${key}`),
    summary: getValue(`sl-form-summary-${key}`),
    status_code: getValue(`sl-form-status-${key}`) || "DRAFT",
    manpower_rows: collectSectionRows(moduleKey, tabKey, "manpower"),
    equipment_rows: collectSectionRows(moduleKey, tabKey, "equipment"),
    activity_rows: collectSectionRows(moduleKey, tabKey, "activity"),
    note: getValue(`sl-comment-input-${key}`),
  };
}

function setFormMode(moduleKey: string, tabKey: string, mode: FormMode): void {
  const key = keyOf(moduleKey, tabKey);
  modeByKey[key] = mode;
  setValue(`sl-form-mode-${key}`, mode);
}

function showFormMode(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const form = getElement(`sl-form-wrap-${key}`);
  const detail = getElement(`sl-detail-wrap-${key}`);
  if (form instanceof HTMLElement) form.hidden = false;
  if (detail instanceof HTMLElement) detail.style.display = "none";
}

function showDetailMode(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const form = getElement(`sl-form-wrap-${key}`);
  const detail = getElement(`sl-detail-wrap-${key}`);
  if (form instanceof HTMLElement) form.hidden = true;
  if (detail instanceof HTMLElement) detail.style.display = "block";
}

function setExistingSectionsVisible(moduleKey: string, tabKey: string, visible: boolean): void {
  const key = keyOf(moduleKey, tabKey);
  const existing = getElement(`sl-existing-only-${key}`);
  const comments = getElement(`sl-comments-wrap-${key}`);
  if (existing instanceof HTMLElement) existing.hidden = !visible;
  if (comments instanceof HTMLElement) comments.hidden = !visible;
}

function resetForm(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): void {
  const key = keyOf(moduleKey, tabKey);
  const capabilities = boardCapabilities(moduleKey, tabKey, deps);
  setFormMode(moduleKey, tabKey, "create");
  setDrawerTitle(moduleKey, tabKey, "گزارش کارگاهی جدید");
  setValue(`sl-form-id-${key}`, "");
  setValue(`sl-form-log-type-${key}`, formBridge.defaultLogType(moduleKey, tabKey));
  setValue(`sl-form-project-${key}`, "");
  setValue(`sl-form-discipline-${key}`, "");
  setValue(`sl-form-organization-${key}`, "");
  setValue(`sl-form-log-date-${key}`, new Date().toISOString().slice(0, 10));
  setValue(`sl-form-weather-${key}`, "CLEAR");
  setValue(`sl-form-summary-${key}`, "");
  setValue(`sl-form-status-${key}`, "DRAFT");
  setValue(`sl-comment-input-${key}`, "");
  renderSectionRows(moduleKey, tabKey, "manpower", [{}], "create", capabilities);
  renderSectionRows(moduleKey, tabKey, "equipment", [{}], "create", capabilities);
  renderSectionRows(moduleKey, tabKey, "activity", [{}], "create", capabilities);
  setExistingSectionsVisible(moduleKey, tabKey, false);
  showFormMode(moduleKey, tabKey);
  ensureShamsiInputs(moduleKey, tabKey);
  setDrawerDirty(moduleKey, tabKey, false);
}

function fillFormFromLog(moduleKey: string, tabKey: string, row: Record<string, unknown>, mode: FormMode, deps: SiteLogsUiDeps): void {
  const key = keyOf(moduleKey, tabKey);
  const capabilities = boardCapabilities(moduleKey, tabKey, deps);
  const forceMode: FormMode = mode === "edit" && upper(row.status_code) !== "DRAFT" ? "detail" : mode;
  setFormMode(moduleKey, tabKey, forceMode);
  setValue(`sl-form-id-${key}`, Number(row.id || 0));
  setValue(`sl-form-log-type-${key}`, row.log_type || "DAILY");
  setValue(`sl-form-project-${key}`, row.project_code || "");
  setValue(`sl-form-discipline-${key}`, row.discipline_code || "");
  setValue(`sl-form-organization-${key}`, row.organization_id || "");
  setValue(`sl-form-log-date-${key}`, String(row.log_date || "").slice(0, 10));
  setValue(`sl-form-weather-${key}`, row.weather || "");
  setValue(`sl-form-summary-${key}`, row.summary || "");
  setValue(`sl-form-status-${key}`, row.status_code || "DRAFT");
  renderSectionRows(moduleKey, tabKey, "manpower", asArray(row.manpower_rows), forceMode, capabilities);
  renderSectionRows(moduleKey, tabKey, "equipment", asArray(row.equipment_rows), forceMode, capabilities);
  renderSectionRows(moduleKey, tabKey, "activity", asArray(row.activity_rows), forceMode, capabilities);
  setExistingSectionsVisible(moduleKey, tabKey, Number(row.id || 0) > 0);
  setDrawerTitle(moduleKey, tabKey, forceMode === "verify" ? "تایید گزارش کارگاهی" : forceMode === "detail" ? "جزئیات گزارش" : "ویرایش گزارش");
  showFormMode(moduleKey, tabKey);
  ensureShamsiInputs(moduleKey, tabKey);
  setDrawerDirty(moduleKey, tabKey, false);
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatNumber(value: number | null, digits = 1, suffix = ""): string {
  if (value === null) return "—";
  const normalized = Math.abs(value % 1) < 0.001 ? value.toFixed(0) : value.toFixed(digits);
  return `${normalized.replace(/\.0+$/, "")}${suffix}`;
}

function textValue(value: unknown, fallback = "—"): string {
  const raw = String(value ?? "").trim();
  return raw || fallback;
}

function escHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sumRows(rows: Record<string, unknown>[], key: string): number | null {
  let hasValue = false;
  const total = rows.reduce((sum, row) => {
    const value = toNumber(row[key]);
    if (value === null) return sum;
    hasValue = true;
    return sum + value;
  }, 0);
  return hasValue ? total : null;
}

function avgRows(rows: Record<string, unknown>[], key: string): number | null {
  const values = rows
    .map((row) => toNumber(row[key]))
    .filter((value): value is number => value !== null);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function renderDetailPill(label: string, value: string, tone = "muted"): string {
  return `
    <div class="sl-report-pill ${tone ? `is-${tone}` : ""}">
      <span class="sl-report-pill-label">${stateBridge.esc(label)}</span>
      <strong class="sl-report-pill-value">${stateBridge.esc(value)}</strong>
    </div>
  `;
}

function renderMetaItem(label: string, value: unknown, extraClass = ""): string {
  return `
    <div class="sl-report-meta-item ${extraClass}">
      <span class="sl-report-meta-label">${stateBridge.esc(label)}</span>
      <strong class="sl-report-meta-value">${stateBridge.esc(textValue(value))}</strong>
    </div>
  `;
}

function renderCompareMetric(
  title: string,
  icon: string,
  claimedValue: string,
  verifiedValue: string,
  note: string
): string {
  return `
    <article class="sl-report-metric">
      <div class="sl-report-metric-head">
        <span class="material-icons-round">${stateBridge.esc(icon)}</span>
        <strong>${stateBridge.esc(title)}</strong>
      </div>
      <div class="sl-report-metric-values">
        <div class="sl-report-metric-side is-claimed">
          <span>اعلامی پیمانکار</span>
          <strong>${stateBridge.esc(claimedValue)}</strong>
        </div>
        <div class="sl-report-metric-side is-verified">
          <span>تایید مشاور</span>
          <strong>${stateBridge.esc(verifiedValue)}</strong>
        </div>
      </div>
      <div class="sl-report-metric-note">${stateBridge.esc(note)}</div>
    </article>
  `;
}

function renderSectionCard(title: string, subtitle: string, body: string, count = 0): string {
  return `
    <section class="sl-report-section">
      <div class="sl-report-section-head">
        <div>
          <h4 class="sl-report-section-title">${stateBridge.esc(title)}</h4>
          <p class="sl-report-section-subtitle">${stateBridge.esc(subtitle)}</p>
        </div>
        <span class="doc-muted-pill">${count} ردیف</span>
      </div>
      ${body}
    </section>
  `;
}

function renderEmptySection(message: string): string {
  return `<div class="sl-report-empty">${stateBridge.esc(message)}</div>`;
}

function catalogLabel(listKey: string, matchKey: string, value: unknown, labelKey: string): string {
  const target = String(value ?? "").trim();
  if (!target) return "—";
  const row = optionRowsFromCatalog(listKey).find((item) => String(item[matchKey] ?? "").trim() === target);
  return String(row?.[labelKey] ?? target).trim() || target;
}

function projectName(value: unknown): string {
  return catalogLabel("projects", "code", value, "name");
}

function disciplineName(value: unknown): string {
  return catalogLabel("disciplines", "code", value, "name");
}

function renderSignatureStage(title: string, person: unknown, dateValue: unknown, tone = "default"): string {
  const personText = textValue(person, "ثبت نشده");
  const dateText = personText === "ثبت نشده" ? "—" : formatShamsiDateTime(dateValue);
  return `
    <article class="sl-report-signature-card is-${tone}">
      <div class="sl-report-signature-title">${stateBridge.esc(title)}</div>
      <div class="sl-report-signature-name">${stateBridge.esc(personText)}</div>
      <div class="sl-report-signature-date">${stateBridge.esc(dateText)}</div>
      <div class="sl-report-signature-line">مهر / امضا</div>
    </article>
  `;
}

function renderApprovalFlow(row: Record<string, unknown>): string {
  const body = `
    <div class="sl-report-signature-grid">
      ${renderSignatureStage("ثبت اولیه", row.created_by_name, row.created_at, "created")}
      ${renderSignatureStage("ارسال پیمانکار", row.submitted_by_name, row.submitted_at, "submitted")}
      ${renderSignatureStage("تایید مشاور", row.verified_by_name, row.verified_at, "verified")}
    </div>
  `;
  return renderSectionCard("گردش ثبت و تایید", "این بخش برای نسخه‌ی چاپی و بایگانی گزارش قابل استفاده است.", body, 3);
}

function buildPrintMetricsHtml(row: Record<string, unknown>): string {
  const manpowerRows = asArray(row.manpower_rows);
  const equipmentRows = asArray(row.equipment_rows);
  const activityRows = asArray(row.activity_rows);
  return `
    <section class="summary-grid">
      <div class="summary-card">
        <span>تعداد نفرات</span>
        <strong>${escHtml(formatNumber(sumRows(manpowerRows, "claimed_count"), 0, " نفر"))}</strong>
        <em>تاییدی: ${escHtml(formatNumber(sumRows(manpowerRows, "verified_count"), 0, " نفر"))}</em>
      </div>
      <div class="summary-card">
        <span>ساعات نفرات</span>
        <strong>${escHtml(formatNumber(sumRows(manpowerRows, "claimed_hours"), 1, " ساعت"))}</strong>
        <em>تاییدی: ${escHtml(formatNumber(sumRows(manpowerRows, "verified_hours"), 1, " ساعت"))}</em>
      </div>
      <div class="summary-card">
        <span>ساعات تجهیزات</span>
        <strong>${escHtml(formatNumber(sumRows(equipmentRows, "claimed_hours"), 1, " ساعت"))}</strong>
        <em>تاییدی: ${escHtml(formatNumber(sumRows(equipmentRows, "verified_hours"), 1, " ساعت"))}</em>
      </div>
      <div class="summary-card">
        <span>پیشرفت فعالیت</span>
        <strong>${escHtml(formatNumber(avgRows(activityRows, "claimed_progress_pct"), 1, "%"))}</strong>
        <em>تاییدی: ${escHtml(formatNumber(avgRows(activityRows, "verified_progress_pct"), 1, "%"))}</em>
      </div>
    </section>
  `;
}

function buildPrintTableHtml(
  title: string,
  subtitle: string,
  headers: string[],
  rowsHtml: string,
  emptyMessage: string
): string {
  const body = rowsHtml || `<tr><td colspan="${headers.length}" class="empty-row">${escHtml(emptyMessage)}</td></tr>`;
  return `
    <section class="print-section">
      <div class="print-section-head">
        <div>
          <h3>${escHtml(title)}</h3>
          <p>${escHtml(subtitle)}</p>
        </div>
      </div>
      <table>
        <thead>
          <tr>${headers.map((header) => `<th>${escHtml(header)}</th>`).join("")}</tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </section>
  `;
}

function buildSiteLogPrintInfoTableHtml(row: Record<string, unknown>): string {
  return `
    <table class="info-table">
      <tbody>
        <tr>
          <td><span>پروژه</span><strong>${escHtml(projectName(row.project_code))}</strong></td>
          <td><span>رشته</span><strong>${escHtml(disciplineName(row.discipline_code))}</strong></td>
          <td><span>تاریخ گزارش</span><strong>${escHtml(formatShamsiDate(row.log_date))}</strong></td>
          <td><span>نوع</span><strong>${escHtml(logTypeLabelFa(row.log_type))}</strong></td>
          <td><span>وضعیت</span><strong>${escHtml(statusLabelFa(row.status_code))}</strong></td>
        </tr>
        <tr>
          <td><span>شماره گزارش</span><strong>${escHtml(textValue(row.log_no))}</strong></td>
          <td><span>وضعیت جوی</span><strong>${escHtml(textValue(row.weather))}</strong></td>
          <td><span>ثبت</span><strong>${escHtml(textValue(row.created_by_name))}</strong></td>
          <td><span>ارسال</span><strong>${escHtml(textValue(row.submitted_by_name))}</strong></td>
          <td><span>تایید</span><strong>${escHtml(textValue(row.verified_by_name))}</strong></td>
        </tr>
      </tbody>
    </table>
  `;
}

function buildSiteLogPrintHtml(row: Record<string, unknown>, mode: "summary" | "full" = "full"): string {
  const projectCode = textValue(row.project_code);
  const projectTitle = projectName(row.project_code);
  const disciplineTitle = disciplineName(row.discipline_code);
  const organizationTitle = textValue(row.organization_name);
  const manpowerRows = asArray(row.manpower_rows);
  const equipmentRows = asArray(row.equipment_rows);
  const activityRows = asArray(row.activity_rows);
  const printTime = formatShamsiDateTime(new Date().toISOString());
  const summaryRaw = String(row.summary ?? "").trim();

  const manpowerTable = buildPrintTableHtml(
    "نفرات",
    "مقایسه تعداد و ساعات اعلامی پیمانکار با تاییدی مشاور",
    ["#", "کد نقش", "عنوان نقش", "تعداد اعلامی", "ساعت اعلامی", "تعداد تاییدی", "ساعت تاییدی", "توضیحات"],
    manpowerRows
      .map(
        (item, index) => `
          <tr>
            <td>${index + 1}</td>
            <td>${escHtml(textValue(item.role_code))}</td>
            <td>${escHtml(textValue(item.role_label))}</td>
            <td>${escHtml(formatNumber(toNumber(item.claimed_count), 0))}</td>
            <td>${escHtml(formatNumber(toNumber(item.claimed_hours), 1))}</td>
            <td>${escHtml(formatNumber(toNumber(item.verified_count), 0))}</td>
            <td>${escHtml(formatNumber(toNumber(item.verified_hours), 1))}</td>
            <td>${escHtml(textValue(item.note))}</td>
          </tr>
        `
      )
      .join(""),
    "ردیف نفرات برای این گزارش ثبت نشده است."
  );

  const equipmentTable = buildPrintTableHtml(
    "تجهیزات",
    "نمایش وضعیت و ساعات تجهیز در دو ستون اعلامی و تاییدی",
    ["#", "کد تجهیز", "عنوان تجهیز", "وضعیت اعلامی", "ساعت اعلامی", "وضعیت تاییدی", "ساعت تاییدی", "توضیحات"],
    equipmentRows
      .map(
        (item, index) => `
          <tr>
            <td>${index + 1}</td>
            <td>${escHtml(textValue(item.equipment_code))}</td>
            <td>${escHtml(textValue(item.equipment_label))}</td>
            <td>${escHtml(textValue(item.claimed_status))}</td>
            <td>${escHtml(formatNumber(toNumber(item.claimed_hours), 1))}</td>
            <td>${escHtml(textValue(item.verified_status))}</td>
            <td>${escHtml(formatNumber(toNumber(item.verified_hours), 1))}</td>
            <td>${escHtml(textValue(item.note))}</td>
          </tr>
        `
      )
      .join(""),
    "ردیف تجهیز برای این گزارش ثبت نشده است."
  );

  const activityTable = buildPrintTableHtml(
    "فعالیت‌ها",
    "مقایسه درصد پیشرفت اعلامی پیمانکار و تاییدی مشاور",
    ["#", "کد فعالیت", "عنوان فعالیت", "پیشرفت اعلامی", "پیشرفت تاییدی", "توضیحات"],
    activityRows
      .map(
        (item, index) => `
          <tr>
            <td>${index + 1}</td>
            <td>${escHtml(textValue(item.activity_code))}</td>
            <td>${escHtml(textValue(item.activity_title))}</td>
            <td>${escHtml(formatNumber(toNumber(item.claimed_progress_pct), 1, "%"))}</td>
            <td>${escHtml(formatNumber(toNumber(item.verified_progress_pct), 1, "%"))}</td>
            <td>${escHtml(textValue(item.note))}</td>
          </tr>
        `
      )
      .join(""),
    "ردیف فعالیت برای این گزارش ثبت نشده است."
  );

  const summarySection = summaryRaw
    ? `
    <section class="section-box">
      <div class="section-title">خلاصه عملیات</div>
      <div class="section-content">${escHtml(summaryRaw)}</div>
    </section>
  `
    : "";

  return `
<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>چاپ گزارش کارگاهی - ${escHtml(textValue(row.log_no))}</title>
  <style>
    @page { size: A4; margin: 8mm 8mm 11mm; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Tahoma, "Segoe UI", Arial, sans-serif; font-size: 10px; color: #0f172a; background: #ffffff; }
    .sheet { position: relative; padding-bottom: 8px; }
    .letterhead {
      display: grid;
      grid-template-columns: 38px 1fr 135px;
      gap: 6px;
      align-items: center;
      border: 1px solid #0f172a;
      padding: 5px 7px;
      margin-bottom: 5px;
    }
    .brand-mark {
      width: 30px;
      height: 30px;
      border-radius: 8px;
      border: 1px solid #1d4ed8;
      color: #1d4ed8;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 8.8px;
      font-weight: 900;
      letter-spacing: 0.04em;
      background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
    }
    .letterhead-title { text-align: center; }
    .letterhead-title h1 { margin: 0; font-size: 13.5px; font-weight: 800; line-height: 1.1; }
    .letterhead-title p { margin: 1px 0 0; font-size: 8px; color: #475569; }
    .letterhead-meta {
      border-right: 1px solid #cbd5e1;
      padding-right: 6px;
      font-size: 8px;
      line-height: 1.35;
    }
    .info-table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 5px;
    }
    .info-table td {
      width: 20%;
      border: 1px solid #334155;
      padding: 4px 5px;
      vertical-align: top;
      text-align: right;
    }
    .info-table span, .summary-card span { display: block; font-size: 7.8px; color: #475569; margin-bottom: 1px; }
    .info-table strong, .summary-card strong { display: block; font-size: 9.4px; line-height: 1.25; }
    .summary-card {
      border: 1px solid #334155;
      padding: 4px 5px;
      min-height: 0;
    }
    .summary-card em { display: block; margin-top: 2px; font-size: 8.5px; color: #166534; font-style: normal; }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 4px;
      margin-bottom: 5px;
    }
    .section-box {
      border: 1px solid #334155;
      margin-bottom: 5px;
    }
    .section-title {
      background: #e2e8f0;
      padding: 3px 5px;
      font-weight: 800;
      font-size: 9.8px;
      border-bottom: 1px solid #334155;
    }
    .section-content {
      padding: 4px 6px;
      line-height: 1.45;
      font-size: 9.2px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .print-section { margin-bottom: 6px; break-inside: auto; }
    .print-section-head h3 { margin: 0; font-size: 10px; font-weight: 800; }
    .print-section-head p { margin: 1px 0 3px; font-size: 8px; color: #475569; }
    table { width: 100%; border-collapse: collapse; font-size: 8.7px; }
    thead { display: table-header-group; }
    tr { page-break-inside: avoid; }
    th, td { border: 1px solid #334155; padding: 2px 3px; vertical-align: top; text-align: right; line-height: 1.2; }
    thead th { background: #f1f5f9; font-weight: 800; }
    .empty-row { text-align: center; color: #64748b; padding: 6px; }
    .signature-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 5px;
      margin-top: 4px;
    }
    .signature-card {
      border: 1px solid #334155;
      min-height: 54px;
      padding: 4px 5px;
      break-inside: avoid;
    }
    .signature-card h4 { margin: 0 0 2px; font-size: 8.8px; }
    .signature-card .name { font-weight: 700; min-height: 11px; line-height: 1.2; font-size: 8.7px; }
    .signature-card .date { color: #475569; margin-top: 1px; font-size: 7.5px; }
    .signature-card .line { margin-top: 6px; border-top: 1px dashed #64748b; padding-top: 1px; font-size: 7.3px; color: #64748b; }
    .print-footer {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 7.8px;
      color: #475569;
      border-top: 1px solid #cbd5e1;
      padding-top: 2px;
      background: #ffffff;
    }
    .print-page-number::after { content: counter(page); }
  </style>
</head>
<body>
  <div class="sheet">
    <header class="letterhead">
      <div class="brand-mark">EDMS</div>
      <div class="letterhead-title">
        <h1>گزارش کارگاهی</h1>
        <p>نسخه رسمی چاپ برای بایگانی، بررسی و امضا</p>
      </div>
      <div class="letterhead-meta">
        <div><strong>پروژه:</strong> ${escHtml(projectTitle)}</div>
        <div><strong>شرکت:</strong> ${escHtml(organizationTitle)}</div>
        <div><strong>شماره گزارش:</strong> ${escHtml(textValue(row.log_no))}</div>
        <div><strong>وضعیت:</strong> ${escHtml(statusLabelFa(row.status_code))}</div>
      </div>
    </header>

    ${buildSiteLogPrintInfoTableHtml(row)}

    ${buildPrintMetricsHtml(row)}

    ${summarySection}

    ${mode === "full" ? manpowerTable : ""}
    ${mode === "full" ? equipmentTable : ""}
    ${mode === "full" ? activityTable : ""}

    <section class="print-section">
      <div class="print-section-head">
        <h3>${mode === "summary" ? "ثبت / ارسال / تایید" : "ثبت / ارسال / تایید نهایی"}</h3>
        <p>${mode === "summary" ? "نسخه فشرده برای چاپ سریع" : "جای امضا برای نسخه بایگانی"}</p>
      </div>
      <div class="signature-grid">
        <div class="signature-card">
          <h4>ثبت</h4>
          <div class="name">${escHtml(textValue(row.created_by_name, "ثبت نشده"))}</div>
          <div class="date">تاریخ: ${escHtml(formatShamsiDateTime(row.created_at))}</div>
          <div class="line">مهر / امضا</div>
        </div>
        <div class="signature-card">
          <h4>ارسال</h4>
          <div class="name">${escHtml(textValue(row.submitted_by_name, "ثبت نشده"))}</div>
          <div class="date">تاریخ: ${escHtml(formatShamsiDateTime(row.submitted_at))}</div>
          <div class="line">مهر / امضا</div>
        </div>
        <div class="signature-card">
          <h4>تایید</h4>
          <div class="name">${escHtml(textValue(row.verified_by_name, "ثبت نشده"))}</div>
          <div class="date">تاریخ: ${escHtml(formatShamsiDateTime(row.verified_at))}</div>
          <div class="line">مهر / امضا</div>
        </div>
      </div>
    </section>
  </div>

  <div class="print-footer">
    <span>EDMS Site Log Report</span>
    <span>تاریخ چاپ: ${escHtml(printTime)}</span>
    <span>صفحه <span class="print-page-number"></span></span>
  </div>

  <script>
    window.addEventListener('load', function () {
      setTimeout(function () { window.print(); }, 250);
    });
  </script>
</body>
</html>
`;
}

function openPrintHtml(html: string, title: string): boolean {
  const popup = window.open("", "_blank", "width=1100,height=900");
  if (!popup) return false;
  popup.document.open();
  popup.document.write(html);
  popup.document.title = title;
  popup.document.close();
  popup.focus();
  return true;
}

function renderManpowerDetail(rows: Record<string, unknown>[]): string {
  if (!rows.length) {
    return renderSectionCard("نفرات", "نمایش مقایسه تعداد و ساعات اعلامی با تاییدی.", renderEmptySection("برای این گزارش ردیف نفرات ثبت نشده است."), 0);
  }
  const body = `
    <div class="sl-report-table-wrap">
      <table class="module-crud-table sl-report-table">
        <thead>
          <tr>
            <th rowspan="2">#</th>
            <th rowspan="2">کد نقش</th>
            <th rowspan="2">عنوان نقش</th>
            <th colspan="2">اعلامی پیمانکار</th>
            <th colspan="2">تایید مشاور</th>
            <th rowspan="2">توضیحات</th>
          </tr>
          <tr>
            <th>تعداد</th>
            <th>ساعت</th>
            <th>تعداد</th>
            <th>ساعت</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((row, index) => {
              return `
                <tr>
                  <td>${index + 1}</td>
                  <td class="sl-report-code-cell">${stateBridge.esc(textValue(row.role_code))}</td>
                  <td>${stateBridge.esc(textValue(row.role_label))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.claimed_count), 0))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.claimed_hours), 1))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.verified_count), 0))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.verified_hours), 1))}</td>
                  <td class="sl-report-note-cell">${stateBridge.esc(textValue(row.note))}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return renderSectionCard("نفرات", "نمایش مقایسه تعداد و ساعات اعلامی با تاییدی.", body, rows.length);
}

function renderEquipmentDetail(rows: Record<string, unknown>[]): string {
  if (!rows.length) {
    return renderSectionCard("تجهیزات", "وضعیت و ساعات تجهیز در دو ستون اعلامی و تاییدی.", renderEmptySection("برای این گزارش ردیف تجهیز ثبت نشده است."), 0);
  }
  const body = `
    <div class="sl-report-table-wrap">
      <table class="module-crud-table sl-report-table">
        <thead>
          <tr>
            <th rowspan="2">#</th>
            <th rowspan="2">کد تجهیز</th>
            <th rowspan="2">عنوان تجهیز</th>
            <th colspan="2">اعلامی پیمانکار</th>
            <th colspan="2">تایید مشاور</th>
            <th rowspan="2">توضیحات</th>
          </tr>
          <tr>
            <th>وضعیت</th>
            <th>ساعت</th>
            <th>وضعیت</th>
            <th>ساعت</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((row, index) => {
              return `
                <tr>
                  <td>${index + 1}</td>
                  <td class="sl-report-code-cell">${stateBridge.esc(textValue(row.equipment_code))}</td>
                  <td>${stateBridge.esc(textValue(row.equipment_label))}</td>
                  <td>${stateBridge.esc(textValue(row.claimed_status))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.claimed_hours), 1))}</td>
                  <td>${stateBridge.esc(textValue(row.verified_status))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.verified_hours), 1))}</td>
                  <td class="sl-report-note-cell">${stateBridge.esc(textValue(row.note))}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return renderSectionCard("تجهیزات", "وضعیت و ساعات تجهیز در دو ستون اعلامی و تاییدی.", body, rows.length);
}

function renderActivityDetail(rows: Record<string, unknown>[]): string {
  if (!rows.length) {
    return renderSectionCard("فعالیت‌ها", "مقایسه درصد پیشرفت اعلامی پیمانکار و تاییدی مشاور.", renderEmptySection("برای این گزارش فعالیتی ثبت نشده است."), 0);
  }
  const body = `
    <div class="sl-report-table-wrap">
      <table class="module-crud-table sl-report-table">
        <thead>
          <tr>
            <th>#</th>
            <th>کد فعالیت</th>
            <th>عنوان فعالیت</th>
            <th>پیشرفت اعلامی</th>
            <th>پیشرفت تاییدی</th>
            <th>توضیحات</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((row, index) => {
              return `
                <tr>
                  <td>${index + 1}</td>
                  <td class="sl-report-code-cell">${stateBridge.esc(textValue(row.activity_code))}</td>
                  <td>${stateBridge.esc(textValue(row.activity_title))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.claimed_progress_pct), 1, "%"))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.verified_progress_pct), 1, "%"))}</td>
                  <td class="sl-report-note-cell">${stateBridge.esc(textValue(row.note))}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return renderSectionCard("فعالیت‌ها", "مقایسه درصد پیشرفت اعلامی پیمانکار و تاییدی مشاور.", body, rows.length);
}

function renderDetailCard(moduleKey: string, tabKey: string, row: Record<string, unknown>): void {
  const key = keyOf(moduleKey, tabKey);
  const host = getElement(`sl-detail-wrap-${key}`);
  if (!(host instanceof HTMLElement)) return;
  detailRowByKey[key] = row;
  const manpowerRows = asArray(row.manpower_rows);
  const equipmentRows = asArray(row.equipment_rows);
  const activityRows = asArray(row.activity_rows);
  const claimedManpowerCount = formatNumber(sumRows(manpowerRows, "claimed_count"), 0, " نفر");
  const verifiedManpowerCount = formatNumber(sumRows(manpowerRows, "verified_count"), 0, " نفر");
  const claimedManpowerHours = formatNumber(sumRows(manpowerRows, "claimed_hours"), 1, " ساعت");
  const verifiedManpowerHours = formatNumber(sumRows(manpowerRows, "verified_hours"), 1, " ساعت");
  const claimedEquipmentHours = formatNumber(sumRows(equipmentRows, "claimed_hours"), 1, " ساعت");
  const verifiedEquipmentHours = formatNumber(sumRows(equipmentRows, "verified_hours"), 1, " ساعت");
  const claimedProgress = formatNumber(avgRows(activityRows, "claimed_progress_pct"), 1, "%");
  const verifiedProgress = formatNumber(avgRows(activityRows, "verified_progress_pct"), 1, "%");
  host.innerHTML = `
    <article class="sl-report-detail">
      <div class="sl-report-print-actions">
        <button type="button" class="btn btn-secondary" data-sl-action="print-detail-summary">
          <span class="material-icons-round">article</span>
          چاپ خلاصه
        </button>
        <button type="button" class="btn btn-secondary" data-sl-action="print-detail-full">
          <span class="material-icons-round">print</span>
          چاپ کامل
        </button>
      </div>

      <section class="sl-report-hero">
        <div class="sl-report-hero-main">
          <div class="sl-report-kicker">گزارش کارگاهی</div>
          <h3 class="sl-report-no">${stateBridge.esc(textValue(row.log_no))}</h3>
          <div class="sl-report-pills">
            <span class="module-crud-status is-${stateBridge.statusClass(row.status_code)}">${stateBridge.esc(
              statusLabelFa(row.status_code)
            )}</span>
            ${renderDetailPill("نوع", logTypeLabelFa(row.log_type))}
            ${renderDetailPill("تاریخ", formatShamsiDate(row.log_date))}
            ${renderDetailPill("وضعیت جوی", textValue(row.weather))}
            ${renderDetailPill("نام پروژه", projectName(row.project_code))}
          </div>
        </div>
        <div class="sl-report-hero-side">
          ${renderMetaItem("کد پروژه", row.project_code)}
          ${renderMetaItem("پروژه", projectName(row.project_code))}
          ${renderMetaItem("کد دیسیپلین", row.discipline_code)}
          ${renderMetaItem("دیسیپلین", disciplineName(row.discipline_code))}
          ${renderMetaItem("سازمان", row.organization_name)}
          ${renderMetaItem("ثبت‌کننده", row.created_by_name)}
        </div>
      </section>

      <section class="sl-report-section">
        <div class="sl-report-section-head">
          <div>
            <h4 class="sl-report-section-title">اطلاعات پایه گزارش</h4>
            <p class="sl-report-section-subtitle">شناسه‌ها، وضعیت گردش‌کار و اطلاعات ثبت و تایید گزارش.</p>
          </div>
        </div>
        <div class="sl-report-meta-grid">
          ${renderMetaItem("شناسه گزارش", row.id)}
          ${renderMetaItem("تاریخ گزارش", formatShamsiDate(row.log_date))}
          ${renderMetaItem("وضعیت", statusLabelFa(row.status_code))}
          ${renderMetaItem("نوع گزارش", logTypeLabelFa(row.log_type))}
          ${renderMetaItem("تاریخ ایجاد", formatShamsiDateTime(row.created_at))}
          ${renderMetaItem("آخرین بروزرسانی", formatShamsiDateTime(row.updated_at))}
          ${renderMetaItem("ارسال‌شده توسط", row.submitted_by_name)}
          ${renderMetaItem("تاریخ ارسال", formatShamsiDateTime(row.submitted_at))}
          ${renderMetaItem("تاییدشده توسط", row.verified_by_name)}
          ${renderMetaItem("تاریخ تایید", formatShamsiDateTime(row.verified_at))}
        </div>
      </section>

      <section class="sl-report-summary-card">
        <div class="sl-report-summary-head">
          <span class="material-icons-round">notes</span>
          <strong>خلاصه عملیات</strong>
        </div>
        <p class="sl-report-summary-text">${stateBridge.esc(textValue(row.summary))}</p>
      </section>

      <section class="sl-report-section">
        <div class="sl-report-section-head">
          <div>
            <h4 class="sl-report-section-title">خلاصه اعلامی و تاییدی</h4>
            <p class="sl-report-section-subtitle">مرور سریع خروجی پیمانکار در کنار مقدار تاییدشده توسط مشاور.</p>
          </div>
        </div>
        <div class="sl-report-metrics-grid">
          ${renderCompareMetric("تعداد نفرات", "groups", claimedManpowerCount, verifiedManpowerCount, "جمع تعداد نیروهای ثبت‌شده در این گزارش")}
          ${renderCompareMetric("ساعات نفرات", "schedule", claimedManpowerHours, verifiedManpowerHours, "جمع ساعات کارکرد ثبت‌شده برای نفرات")}
          ${renderCompareMetric("ساعات تجهیزات", "precision_manufacturing", claimedEquipmentHours, verifiedEquipmentHours, "جمع ساعات کارکرد تجهیزات")}
          ${renderCompareMetric("میانگین پیشرفت فعالیت", "insights", claimedProgress, verifiedProgress, "میانگین درصد پیشرفت فعالیت‌های درج‌شده")}
        </div>
      </section>

      ${renderManpowerDetail(manpowerRows)}
      ${renderEquipmentDetail(equipmentRows)}
      ${renderActivityDetail(activityRows)}
      ${renderApprovalFlow(row)}
    </article>
  `;
}

async function refreshCommentsAndAttachments(moduleKey: string, tabKey: string, logId: number, deps: SiteLogsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  if (logId <= 0) {
    stateBridge.renderComments(getElement(`sl-comments-${key}`), []);
    stateBridge.renderAttachments(getElement(`sl-attachments-${key}`), {});
    return;
  }
  try {
    const comments = await dataBridge.listComments(logId, { fetch: deps.fetch });
    stateBridge.renderComments(getElement(`sl-comments-${key}`), asArray(comments.data));
  } catch (error) {
    console.warn("siteLogs comments refresh failed:", error);
  }
  try {
    const attachments = await dataBridge.listAttachments(logId, { fetch: deps.fetch });
    stateBridge.renderAttachments(getElement(`sl-attachments-${key}`), attachments);
  } catch (error) {
    console.warn("siteLogs attachments refresh failed:", error);
  }
}

function listQuery(moduleKey: string, tabKey: string): Record<string, unknown> {
  const key = keyOf(moduleKey, tabKey);
  return {
    module_key: moduleKey,
    tab_key: tabKey,
    project_code: getValue(`sl-filter-project-${key}`),
    discipline_code: getValue(`sl-filter-discipline-${key}`),
    log_type: getValue(`sl-filter-log-type-${key}`),
    status_code: getValue(`sl-filter-status-${key}`),
    search: getValue(`sl-filter-search-${key}`),
    skip: 0,
    limit: 100,
  };
}

async function loadBoard(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps, force = false): Promise<boolean> {
  const key = keyOf(moduleKey, tabKey);
  if (!force && loadingByKey[key]) return false;
  loadingByKey[key] = true;
  try {
    const payload = await dataBridge.list(listQuery(moduleKey, tabKey), { fetch: deps.fetch });
    const rows = asArray(payload.data);
    rowsByKey[key] = rows;
    const capabilities = boardCapabilities(moduleKey, tabKey, deps);
    stateBridge.renderRows(getElement(`sl-tbody-${key}`), rows, { canEdit: capabilities.canCreate, canVerify: capabilities.canVerify });
    stateBridge.renderStats(moduleKey, rows, Number(payload.total || rows.length));
    return true;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "بارگذاری لیست گزارش‌ها ناموفق بود."), "error");
    return false;
  } finally {
    loadingByKey[key] = false;
  }
}

function debouncedLoad(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): void {
  const key = keyOf(moduleKey, tabKey);
  if (debounceTimers[key]) window.clearTimeout(debounceTimers[key]);
  debounceTimers[key] = window.setTimeout(() => {
    void loadBoard(moduleKey, tabKey, deps, true);
  }, 320);
}

async function openCreateDrawer(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<void> {
  resetForm(moduleKey, tabKey, deps);
  openDrawer(moduleKey, tabKey);
}

async function openExistingDrawer(moduleKey: string, tabKey: string, logId: number, mode: FormMode, deps: SiteLogsUiDeps): Promise<void> {
  if (!logId) return;
  try {
    const payload = await dataBridge.get(logId, { fetch: deps.fetch });
    const row = asRecord(payload.data);
    selectedByKey[keyOf(moduleKey, tabKey)] = Number(row.id || logId);
    if (mode === "detail") {
      renderDetailCard(moduleKey, tabKey, row);
      showDetailMode(moduleKey, tabKey);
      setDrawerTitle(moduleKey, tabKey, "جزئیات گزارش");
    } else {
      fillFormFromLog(moduleKey, tabKey, row, mode, deps);
      showFormMode(moduleKey, tabKey);
    }
    openDrawer(moduleKey, tabKey);
    await refreshCommentsAndAttachments(moduleKey, tabKey, Number(row.id || logId), deps);
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "باز کردن گزارش ناموفق بود."), "error");
  }
}

function validateAndNotify(errors: string[], deps: SiteLogsUiDeps): boolean {
  if (!errors.length) return true;
  deps.showToast(errors[0], "error");
  return false;
}

async function saveForm(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<number> {
  const raw = readForm(moduleKey, tabKey);
  const errors = formBridge.validateBase(raw);
  if (!validateAndNotify(errors, deps)) return 0;
  const key = keyOf(moduleKey, tabKey);
  const currentId = Number(raw.id || 0);
  try {
    const payload = currentId > 0 ? formBridge.buildUpdatePayload(raw) : formBridge.buildCreatePayload(raw);
    const res = currentId > 0 ? await dataBridge.update(currentId, payload, { fetch: deps.fetch }) : await dataBridge.create(payload, { fetch: deps.fetch });
    const row = asRecord(res.data);
    const id = Number(row.id || 0);
    if (id > 0) {
      selectedByKey[key] = id;
      setValue(`sl-form-id-${key}`, id);
      setValue(`sl-form-status-${key}`, row.status_code || "DRAFT");
      setExistingSectionsVisible(moduleKey, tabKey, true);
      await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
      setDrawerDirty(moduleKey, tabKey, false);
      deps.showToast("ذخیره با موفقیت انجام شد.", "success");
      await loadBoard(moduleKey, tabKey, deps, true);
      return id;
    }
    return 0;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "ذخیره ناموفق بود."), "error");
    return 0;
  }
}

async function submitForm(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<boolean> {
  const raw = readForm(moduleKey, tabKey);
  const errors = formBridge.validateForSubmit(raw);
  if (!validateAndNotify(errors, deps)) return false;
  let id = Number(raw.id || 0);
  if (id <= 0) {
    id = await saveForm(moduleKey, tabKey, deps);
    if (id <= 0) return false;
  } else {
    await saveForm(moduleKey, tabKey, deps);
  }
  try {
    const res = await dataBridge.submit(id, { note: null }, { fetch: deps.fetch });
    const row = asRecord(res.data);
    setValue(`sl-form-status-${keyOf(moduleKey, tabKey)}`, row.status_code || "SUBMITTED");
    setDrawerDirty(moduleKey, tabKey, false);
    deps.showToast("ارسال با موفقیت انجام شد.", "success");
    await loadBoard(moduleKey, tabKey, deps, true);
    return true;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "ارسال ناموفق بود."), "error");
    return false;
  }
}

async function verifyForm(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<boolean> {
  const raw = readForm(moduleKey, tabKey);
  const id = Number(raw.id || 0);
  if (id <= 0) {
    deps.showToast("ابتدا یک گزارش ارسال‌شده را انتخاب کنید.", "error");
    return false;
  }
  try {
    const payload = formBridge.buildVerifyPayload(raw);
    const res = await dataBridge.verify(id, payload, { fetch: deps.fetch });
    const row = asRecord(res.data);
    setValue(`sl-form-status-${keyOf(moduleKey, tabKey)}`, row.status_code || "VERIFIED");
    setDrawerDirty(moduleKey, tabKey, false);
    deps.showToast("تایید با موفقیت انجام شد.", "success");
    await loadBoard(moduleKey, tabKey, deps, true);
    await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
    return true;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "تایید ناموفق بود."), "error");
    return false;
  }
}

async function sendComment(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<boolean> {
  const key = keyOf(moduleKey, tabKey);
  const id = Number(getValue(`sl-form-id-${key}`) || 0);
  if (id <= 0) {
    deps.showToast("ابتدا گزارش را ذخیره کنید.", "error");
    return false;
  }
  const text = getValue(`sl-comment-input-${key}`);
  if (!text) {
    deps.showToast("متن یادداشت الزامی است.", "error");
    return false;
  }
  try {
    await dataBridge.createComment(id, { comment_text: text, comment_type: "comment" }, { fetch: deps.fetch });
    setValue(`sl-comment-input-${key}`, "");
    await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
    deps.showToast("یادداشت ثبت شد.", "success");
    return true;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "ثبت یادداشت ناموفق بود."), "error");
    return false;
  }
}

async function uploadAttachment(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<boolean> {
  const key = keyOf(moduleKey, tabKey);
  const id = Number(getValue(`sl-form-id-${key}`) || 0);
  if (id <= 0) {
    deps.showToast("ابتدا گزارش را ذخیره کنید.", "error");
    return false;
  }
  const input = getElement(`sl-attachment-file-${key}`);
  if (!(input instanceof HTMLInputElement) || !input.files || !input.files.length) {
    deps.showToast("برای بارگذاری، یک فایل انتخاب کنید.", "error");
    return false;
  }
  const file = input.files[0];
  const formData = new FormData();
  formData.append("file", file);
  formData.append("section_code", getValue(`sl-attachment-section-${key}`) || "GENERAL");
  formData.append("file_kind", getValue(`sl-attachment-kind-${key}`) || "attachment");
  try {
    await dataBridge.uploadAttachment(id, formData, { fetch: deps.fetch });
    input.value = "";
    await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
    deps.showToast("پیوست با موفقیت بارگذاری شد.", "success");
    return true;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "بارگذاری ناموفق بود."), "error");
    return false;
  }
}

async function deleteAttachment(moduleKey: string, tabKey: string, attachmentId: number, deps: SiteLogsUiDeps): Promise<boolean> {
  const id = Number(getValue(`sl-form-id-${keyOf(moduleKey, tabKey)}`) || 0);
  if (id <= 0 || attachmentId <= 0) return false;
  try {
    await dataBridge.deleteAttachment(id, attachmentId, { fetch: deps.fetch });
    await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
    deps.showToast("پیوست حذف شد.", "success");
    return true;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "حذف ناموفق بود."), "error");
    return false;
  }
}

function addSectionRow(moduleKey: string, tabKey: string, section: SectionKind, deps: SiteLogsUiDeps): void {
  const key = keyOf(moduleKey, tabKey);
  const rows = collectSectionRows(moduleKey, tabKey, section);
  rows.push({ sort_order: rows.length });
  const mode = (getValue(`sl-form-mode-${key}`) || "create") as FormMode;
  renderSectionRows(moduleKey, tabKey, section, rows, mode, boardCapabilities(moduleKey, tabKey, deps));
  setDrawerDirty(moduleKey, tabKey, true);
}

function removeSectionRow(moduleKey: string, tabKey: string, section: SectionKind, index: number, deps: SiteLogsUiDeps): void {
  const rows = collectSectionRows(moduleKey, tabKey, section);
  const filtered = rows.filter((_row, idx) => idx !== index);
  const key = keyOf(moduleKey, tabKey);
  const mode = (getValue(`sl-form-mode-${key}`) || "create") as FormMode;
  renderSectionRows(moduleKey, tabKey, section, filtered.length ? filtered : [{}], mode, boardCapabilities(moduleKey, tabKey, deps));
  setDrawerDirty(moduleKey, tabKey, true);
}

function bindDualFlowActions(): void {
  if (dualFlowBound) return;
  document.addEventListener("click", (event) => {
    const el = event.target && (event.target as HTMLElement).closest ? (event.target as HTMLElement).closest("[data-dual-flow-action]") : null;
    if (!(el instanceof HTMLElement)) return;
    const action = String(el.dataset.dualFlowAction || "").trim().toLowerCase();
    const shell = el.closest(".dual-flow-shell");
    if (!(shell instanceof HTMLElement)) return;
    const flow = action === "show-site-log" ? "site-log" : "comm";
    shell.querySelectorAll<HTMLElement>("[data-dual-flow-action]").forEach((button) => {
      const btnFlow = String(button.dataset.dualFlowAction || "").trim().toLowerCase() === "show-site-log" ? "site-log" : "comm";
      button.classList.toggle("is-active", btnFlow === flow);
    });
    shell.querySelectorAll<HTMLElement>("[data-dual-flow-panel]").forEach((panel) => {
      panel.classList.toggle("is-active", String(panel.dataset.dualFlowPanel || "") === flow);
    });
  });
  dualFlowBound = true;
}

function contextFromElement(el: HTMLElement | null): { moduleKey: string; tabKey: string } | null {
  if (!el) return null;
  const card = el.closest(".site-logs-card[data-module][data-tab]") as HTMLElement | null;
  if (!card) return null;
  const moduleKey = normalize(card.dataset.module);
  const tabKey = normalize(card.dataset.tab);
  if (!moduleKey || !tabKey) return null;
  return { moduleKey, tabKey };
}

function bindActions(deps: SiteLogsUiDeps): void {
  if (actionsBound) return;

  document.addEventListener("click", (event) => {
    const actionEl = event.target && (event.target as HTMLElement).closest ? (event.target as HTMLElement).closest("[data-sl-action]") : null;
    if (!(actionEl instanceof HTMLElement)) return;
    const action = normalize(actionEl.dataset.slAction);
    const context = contextFromElement(actionEl);
    if (!context) return;

    if (action === "open-form") {
      void openCreateDrawer(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "open-edit") {
      void openExistingDrawer(context.moduleKey, context.tabKey, Number(actionEl.dataset.slId || 0), "edit", deps);
      return;
    }
    if (action === "open-detail") {
      void openExistingDrawer(context.moduleKey, context.tabKey, Number(actionEl.dataset.slId || 0), "detail", deps);
      return;
    }
    if (action === "open-verify") {
      void openExistingDrawer(context.moduleKey, context.tabKey, Number(actionEl.dataset.slId || 0), "verify", deps);
      return;
    }
    if (action === "refresh") {
      void loadBoard(context.moduleKey, context.tabKey, deps, true);
      return;
    }
    if (action === "drawer-close" || action === "close-form") {
      closeDrawer(context.moduleKey, context.tabKey);
      return;
    }
    if (action === "print-detail-summary" || action === "print-detail-full") {
      const key = keyOf(context.moduleKey, context.tabKey);
      const row = detailRowByKey[key];
      if (!row) {
        deps.showToast("اطلاعات گزارش برای چاپ در دسترس نیست.", "error");
        return;
      }
      const mode = action === "print-detail-summary" ? "summary" : "full";
      const ok = openPrintHtml(
        buildSiteLogPrintHtml(row, mode),
        `${mode === "summary" ? "Site Log Summary" : "Site Log"} - ${textValue(row.log_no, "print")}`
      );
      if (!ok) {
        deps.showToast("باز کردن پنجره چاپ توسط مرورگر مسدود شد.", "error");
      }
      return;
    }
    if (action === "save-form") {
      void saveForm(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "submit-form") {
      void submitForm(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "verify-form") {
      void verifyForm(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "send-comment") {
      void sendComment(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "upload-attachment") {
      void uploadAttachment(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "delete-attachment") {
      void deleteAttachment(context.moduleKey, context.tabKey, Number(actionEl.dataset.slAttachmentId || 0), deps);
      return;
    }
    if (action === "add-row") {
      addSectionRow(context.moduleKey, context.tabKey, normalize(actionEl.dataset.slSection) as SectionKind, deps);
      return;
    }
    if (action === "remove-row") {
      removeSectionRow(
        context.moduleKey,
        context.tabKey,
        normalize(actionEl.dataset.slSection) as SectionKind,
        Number(actionEl.dataset.slIndex || -1),
        deps
      );
    }
  });

  document.addEventListener("input", (event) => {
    const actionEl = event.target && (event.target as HTMLElement).closest ? (event.target as HTMLElement).closest("[data-sl-action]") : null;
    const context = contextFromElement((event.target as HTMLElement) || null);
    if (!context) return;
    if (actionEl instanceof HTMLElement && normalize(actionEl.dataset.slAction) === "filter-search") {
      debouncedLoad(context.moduleKey, context.tabKey, deps);
      return;
    }
    if ((event.target as HTMLElement)?.closest?.(".ci-drawer-body")) {
      setDrawerDirty(context.moduleKey, context.tabKey, true);
    }
  });

  document.addEventListener("change", (event) => {
    const actionEl = event.target && (event.target as HTMLElement).closest ? (event.target as HTMLElement).closest("[data-sl-action]") : null;
    const context = contextFromElement((event.target as HTMLElement) || null);
    if (!context) return;
    if (actionEl instanceof HTMLElement) {
      const action = normalize(actionEl.dataset.slAction);
      if (["filter-project", "filter-discipline", "filter-log-type", "filter-status"].includes(action)) {
        void loadBoard(context.moduleKey, context.tabKey, deps, true);
        return;
      }
    }
    if ((event.target as HTMLElement)?.closest?.(".ci-drawer-body")) {
      setDrawerDirty(context.moduleKey, context.tabKey, true);
    }
  });

  actionsBound = true;
}

async function ensureCatalog(deps: SiteLogsUiDeps): Promise<boolean> {
  if (catalogCache) return true;
  const payload = await dataBridge.catalog({ fetch: deps.fetch });
  catalogCache = payload;
  return true;
}

function ensureBoards(moduleKey: string, deps: SiteLogsUiDeps): Array<{ moduleKey: string; tabKey: string }> {
  bindDualFlowActions();
  bindActions(deps);
  const roots = document.querySelectorAll(`.site-logs-root[data-module="${normalize(moduleKey)}"][data-tab]`);
  const contexts: Array<{ moduleKey: string; tabKey: string }> = [];
  roots.forEach((root) => {
    const m = normalize(root.getAttribute("data-module"));
    const t = normalize(root.getAttribute("data-tab"));
    if (!m || !t) return;
    if (!root.innerHTML.trim()) {
      root.innerHTML = buildBoardCard(m, t, deps);
    }
    const key = keyOf(m, t);
    if (!modeByKey[key]) modeByKey[key] = "create";
    ensureShamsiInputs(m, t);
    contexts.push({ moduleKey: m, tabKey: t });
  });
  return contexts;
}

async function onTabOpened(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<boolean> {
  await ensureCatalog(deps);
  const contexts = ensureBoards(moduleKey, deps);
  const target = contexts.find((ctx) => ctx.tabKey === normalize(tabKey));
  if (!target) return false;
  await loadBoard(target.moduleKey, target.tabKey, deps, true);
  return true;
}

async function initModule(moduleKey: string, deps: SiteLogsUiDeps): Promise<boolean> {
  await ensureCatalog(deps);
  const contexts = ensureBoards(moduleKey, deps);
  if (!contexts.length) return false;
  for (const ctx of contexts) {
    await loadBoard(ctx.moduleKey, ctx.tabKey, deps, true);
  }
  return true;
}

export function createSiteLogsUiBridge(): SiteLogsUiBridge {
  return {
    onTabOpened,
    initModule,
  };
}

if (typeof window !== "undefined") {
  window.addEventListener("site-log-catalogs:updated", () => {
    catalogCache = null;
  });
}

