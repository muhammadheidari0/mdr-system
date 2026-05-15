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

type SectionKind = "manpower" | "equipment" | "activity" | "material" | "issue" | "report_attachment";
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
const activityOptionsByKey: Record<string, Record<string, unknown>[]> = {};
const attachmentOptionsByKey: Record<string, Record<string, unknown>[]> = {};
const qcSnapshotByKey: Record<string, Record<string, unknown>> = {};
const asyncSyncSeqByKey: Record<string, number> = {};
const collapsedSectionsByKey: Record<string, boolean> = {};

let catalogCache: Record<string, unknown> | null = null;
let actionsBound = false;
let dualFlowBound = false;
let siteLogAttachmentPreviewObjectUrl = "";

type SectionFieldGroup = "base" | "claimed" | "verified" | "note";

type SectionFieldDef = {
  key: string;
  label: string;
  type?: string;
  step?: string;
  group: SectionFieldGroup;
  catalog?: string;
  catalogValueKey?: string;
  catalogLabelKey?: string;
  placeholder?: string;
  activityTitle?: boolean;
  detail?: boolean;
};

type SectionDef = {
  title: string;
  addButtonLabel?: string;
  hiddenKeys?: string[];
  toolbar?: "activity-picker";
  fields: SectionFieldDef[];
};

const SECTION_DEFS: Record<
  SectionKind,
  SectionDef
> = {
  manpower: {
    title: "نفرات",
    fields: [
      { key: "role_code", label: "کد نقش", group: "base" },
      { key: "role_label", label: "عنوان نقش", group: "base", catalog: "role_catalog", catalogValueKey: "label" },
      { key: "work_section_label", label: "واحد / بخش کاری", group: "base", catalog: "work_section_catalog", catalogValueKey: "label" },
      { key: "claimed_count", label: "تعداد اعلامی", type: "number", step: "1", group: "claimed" },
      { key: "claimed_hours", label: "ساعت اعلامی", type: "number", step: "0.1", group: "claimed" },
      { key: "verified_count", label: "تعداد تاییدی", type: "number", step: "1", group: "verified" },
      { key: "verified_hours", label: "ساعت تاییدی", type: "number", step: "0.1", group: "verified" },
      { key: "__files", label: "فایل‌ها", group: "base" },
      { key: "note", label: "توضیحات", group: "note", detail: true },
    ],
  },
  equipment: {
    title: "تجهیزات",
    fields: [
      { key: "equipment_code", label: "کد تجهیز", group: "base" },
      { key: "equipment_label", label: "عنوان تجهیز", group: "base", catalog: "equipment_catalog", catalogValueKey: "label" },
      { key: "work_location", label: "محل کارکرد", group: "base" },
      { key: "claimed_count", label: "تعداد اعلامی", type: "number", step: "1", group: "claimed" },
      { key: "claimed_status", label: "وضعیت اعلامی", group: "claimed", catalog: "equipment_status_catalog", catalogValueKey: "code" },
      { key: "claimed_hours", label: "ساعت اعلامی", type: "number", step: "0.1", group: "claimed" },
      { key: "verified_count", label: "تعداد تاییدی", type: "number", step: "1", group: "verified" },
      { key: "verified_status", label: "وضعیت تاییدی", group: "verified", catalog: "equipment_status_catalog", catalogValueKey: "code" },
      { key: "verified_hours", label: "ساعت تاییدی", type: "number", step: "0.1", group: "verified" },
      { key: "__files", label: "فایل‌ها", group: "base" },
      { key: "note", label: "توضیحات", group: "note", detail: true },
    ],
  },
  activity: {
    title: "فعالیت‌های اجرایی",
    addButtonLabel: "افزودن ردیف",
    hiddenKeys: ["source_system", "external_ref", "claimed_progress_pct", "verified_progress_pct", "pms_mapping_id", "pms_template_code", "pms_template_title", "pms_template_version", "pms_step_title", "pms_step_weight_pct"],
    toolbar: "activity-picker",
    fields: [
      { key: "activity_code", label: "کد", group: "base" },
      { key: "activity_title", label: "عنوان فعالیت", group: "base", activityTitle: true },
      { key: "pms_step_code", label: "مرحله PMS", group: "base" },
      { key: "location", label: "محل", group: "base" },
      { key: "unit", label: "واحد", group: "base" },
      { key: "personnel_count", label: "نفرات", type: "number", step: "1", group: "base" },
      { key: "today_quantity", label: "امروز", type: "number", step: "0.01", group: "base" },
      { key: "cumulative_quantity", label: "تجمیعی", type: "number", step: "0.01", group: "base" },
      { key: "activity_status", label: "وضعیت", group: "base" },
      { key: "stop_reason", label: "علت توقف", group: "base", detail: true },
      { key: "__files", label: "فایل‌ها", group: "base" },
      { key: "note", label: "توضیح", group: "note", detail: true },
    ],
  },
  material: {
    title: "مصالح",
    fields: [
      { key: "material_code", label: "کد", group: "base" },
      { key: "title", label: "عنوان", group: "base", catalog: "material_catalog", catalogValueKey: "label" },
      { key: "consumption_location", label: "محل مصرف", group: "base" },
      { key: "unit", label: "واحد", group: "base" },
      { key: "incoming_quantity", label: "ورودی", type: "number", step: "0.01", group: "base" },
      { key: "consumed_quantity", label: "مصرف", type: "number", step: "0.01", group: "base" },
      { key: "cumulative_quantity", label: "تجمیعی", type: "number", step: "0.01", group: "base" },
      { key: "__files", label: "فایل‌ها", group: "base" },
      { key: "note", label: "توضیح", group: "note", detail: true },
    ],
  },
  issue: {
    title: "موانع / ریسک‌ها",
    fields: [
      { key: "issue_type", label: "نوع", group: "base", catalog: "issue_type_catalog", catalogValueKey: "code", catalogLabelKey: "label" },
      { key: "description", label: "شرح", group: "base" },
      { key: "responsible_party", label: "مسئول", group: "base" },
      { key: "due_date", label: "موعد", type: "date", group: "base" },
      { key: "status", label: "وضعیت", group: "base" },
      { key: "__files", label: "فایل‌ها", group: "base" },
      { key: "note", label: "توضیح", group: "note", detail: true },
    ],
  },
  report_attachment: {
    title: "پیوست‌ها",
    hiddenKeys: ["linked_attachment_id", "linked_attachment_file_name", "linked_attachment_file_kind", "linked_attachment_download_url"],
    fields: [
      { key: "attachment_type", label: "نوع", group: "base", catalog: "attachment_type_catalog", catalogValueKey: "code", catalogLabelKey: "label" },
      { key: "title", label: "عنوان", group: "base" },
      { key: "reference_no", label: "مرجع", group: "base" },
      { key: "__files", label: "فایل‌ها", group: "base" },
      { key: "note", label: "توضیح", group: "note", detail: true },
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

function closeSiteLogRowMenus(exceptMenu: HTMLElement | null = null): void {
  document.querySelectorAll<HTMLElement>(".archive-row-menu.is-open[data-sl-row-menu]").forEach((menu) => {
    if (exceptMenu && menu === exceptMenu) return;
    menu.classList.remove("is-open");
    const trigger = menu.querySelector<HTMLElement>("[data-sl-action='toggle-row-menu']");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  });
}

function toggleSiteLogRowMenu(triggerEl: HTMLElement): void {
  const menu = triggerEl.closest<HTMLElement>("[data-sl-row-menu]");
  if (!(menu instanceof HTMLElement)) return;
  const willOpen = !menu.classList.contains("is-open");
  closeSiteLogRowMenus(menu);
  menu.classList.toggle("is-open", willOpen);
  triggerEl.setAttribute("aria-expanded", willOpen ? "true" : "false");
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

function currentFormMode(moduleKey: string, tabKey: string): FormMode {
  const value = getValue(`sl-form-mode-${keyOf(moduleKey, tabKey)}`) || "create";
  return (value as FormMode) || "create";
}

function sectionRowsKey(section: SectionKind): string {
  if (section === "report_attachment") return "attachment_rows";
  return `${section}_rows`;
}

function sectionBodyId(section: SectionKind, key: string): string {
  return `sl-form-${section}-body-${key}`;
}

function sectionStateKey(key: string, section: SectionKind): string {
  return `${key}:${section}`;
}

function isSectionCollapsed(key: string, section: SectionKind): boolean {
  const stateKey = sectionStateKey(key, section);
  if (collapsedSectionsByKey[stateKey] === undefined) {
    collapsedSectionsByKey[stateKey] = section === "report_attachment";
  }
  return Boolean(collapsedSectionsByKey[stateKey]);
}

function setSectionCollapsed(key: string, section: SectionKind, collapsed: boolean): void {
  collapsedSectionsByKey[sectionStateKey(key, section)] = collapsed;
}

function detailFieldsForSection(section: SectionKind): SectionFieldDef[] {
  return SECTION_DEFS[section].fields.filter((field) => Boolean(field.detail));
}

function mainFieldsForSection(section: SectionKind): SectionFieldDef[] {
  return SECTION_DEFS[section].fields.filter((field) => !field.detail);
}

function meaningfulKeysForSection(section: SectionKind): string[] {
  const map: Record<SectionKind, string[]> = {
    manpower: ["role_code", "role_label", "work_section_label", "claimed_count", "claimed_hours", "verified_count", "verified_hours"],
    equipment: ["equipment_code", "equipment_label", "work_location", "claimed_count", "claimed_status", "claimed_hours", "verified_count", "verified_status", "verified_hours"],
    activity: [
      "activity_code",
      "activity_title",
      "location",
      "unit",
      "personnel_count",
      "today_quantity",
      "cumulative_quantity",
      "activity_status",
      "stop_reason",
    ],
    material: ["material_code", "title", "consumption_location", "unit", "incoming_quantity", "consumed_quantity", "cumulative_quantity"],
    issue: ["issue_type", "description", "responsible_party", "due_date", "status"],
    report_attachment: ["attachment_type", "title", "reference_no", "linked_attachment_id"],
  };
  return map[section] || [];
}

function isMeaningfulSectionRow(section: SectionKind, row: Record<string, unknown>): boolean {
  return meaningfulKeysForSection(section).some((key) => {
    const value = row[key];
    if (value === null || value === undefined) return false;
    return String(value).trim() !== "";
  });
}

function formatFaCount(value: number): string {
  return Number(value || 0).toLocaleString("fa-IR");
}

function rowActionsHtml(
  key: string,
  section: SectionKind,
  row: Record<string, unknown>,
  index: number,
  removable: boolean,
  attachmentEditable: boolean,
  hasDetail = false
): string {
  const files = rowAttachmentFilesForRow(key, section, row, index);
  const fileItems = files.length
    ? files
        .map((item) => {
          const id = Number(item.id || 0);
          const name = String(item.file_name || "").trim() || "file";
          const previewUrl = String(item.preview_url || "").trim() || attachmentPreviewUrl(item);
          const downloadUrl = String(item.download_url || "").trim() || attachmentDownloadUrl(item);
          const previewAction = previewUrl
            ? `<a class="sl-row-file-action" href="${stateBridge.esc(previewUrl)}" data-sl-action="preview-attachment" data-sl-attachment-id="${id}" data-sl-file-name="${stateBridge.esc(name)}">مشاهده</a>`
            : "";
          const downloadAction = downloadUrl
            ? `<a class="sl-row-file-action" href="${stateBridge.esc(downloadUrl)}" download>دانلود</a>`
            : "";
          const deleteAction =
            attachmentEditable && id > 0
              ? `<button type="button" class="sl-row-file-action is-danger" data-sl-action="delete-attachment" data-sl-attachment-id="${id}">حذف</button>`
              : "";
          return `
            <div class="sl-row-file-item" data-sl-attachment-id="${id}">
              <span class="sl-row-file-name">${stateBridge.esc(name)}</span>
              <span class="sl-row-file-actions">${previewAction}${downloadAction}${deleteAction}</span>
            </div>
          `;
        })
        .join("")
    : `<div class="sl-row-menu-empty">پیوستی ثبت نشده است.</div>`;
  const uploadAction = section === "report_attachment" ? "upload-report-attachment-row" : "upload-row-attachment";
  const uploadHtml = attachmentEditable
    ? `
      <div class="sl-row-menu-upload">
        <input class="sl-row-file-input" type="file" multiple data-sl-row-attachment-file="${section}:${index}"${
          section === "report_attachment" ? ` data-sl-report-attachment-file="${index}"` : ""
        }>
        <button type="button" class="archive-row-menu-item" data-sl-action="${uploadAction}" data-sl-section="${section}" data-sl-index="${index}">
          <span class="material-icons-round">upload_file</span><span>بارگذاری پیوست</span>
        </button>
      </div>
    `
    : "";
  const removeHtml = removable
    ? `
      <button type="button" class="archive-row-menu-item text-danger" data-sl-action="remove-row" data-sl-section="${section}" data-sl-index="${index}">
        <span class="material-icons-round">delete</span><span>حذف ردیف</span>
      </button>
    `
    : "";
  const detailHtml = hasDetail
    ? `
      <button type="button" class="archive-row-menu-item" data-sl-action="toggle-row-detail" data-sl-section="${section}" data-sl-index="${index}">
        <span class="material-icons-round">unfold_more</span><span>جزئیات ردیف</span>
      </button>
    `
    : "";
  if (!files.length && !uploadHtml && !removeHtml && !detailHtml) return "-";
  return `
    <div class="archive-row-menu sl-form-row-menu" data-sl-row-menu>
      <button class="btn-archive-icon archive-row-menu-trigger" type="button" title="عملیات" data-sl-action="toggle-row-menu" aria-expanded="false">
        <span class="material-icons-round" style="font-size:18px;">more_vert</span>
      </button>
      <div class="archive-row-menu-dropdown">
        <div class="sl-row-menu-title"><span class="material-icons-round">attach_file</span><span>پیوست‌های ردیف</span></div>
        <div class="sl-row-menu-files">${fileItems}</div>
        ${uploadHtml}
        ${detailHtml}
        ${removeHtml}
      </div>
    </div>
  `;
}

function optionRowsFromCatalog(key: string): Record<string, unknown>[] {
  return asArray(asRecord(catalogCache)[key]);
}

function organizationsFromCatalog(): Record<string, unknown>[] {
  return optionRowsFromCatalog("organizations");
}

function contractsForOrganization(organizationId: unknown): Record<string, unknown>[] {
  const id = Number(organizationId || 0);
  if (id <= 0) return [];
  const match = organizationsFromCatalog().find((row) => Number(row.id || 0) === id);
  return asArray(match?.contracts);
}

function activityOptionsForKey(key: string): Record<string, unknown>[] {
  return asArray(activityOptionsByKey[key]);
}

function attachmentOptionsForKey(key: string): Record<string, unknown>[] {
  return asArray(attachmentOptionsByKey[key]);
}

function attachmentDownloadUrl(row: Record<string, unknown>): string {
  const id = Number(row.id || 0);
  return id > 0 ? `/api/v1/site-logs/attachments/${id}/download` : "";
}

function attachmentPreviewUrl(row: Record<string, unknown>): string {
  const id = Number(row.id || 0);
  return id > 0 ? `/api/v1/site-logs/attachments/${id}/preview` : "";
}

function attachmentSectionCodeForRowSection(section: SectionKind): string {
  const map: Record<string, string> = {
    manpower: "MANPOWER",
    equipment: "EQUIPMENT",
    activity: "ACTIVITY",
    material: "MATERIAL",
    issue: "ISSUE",
    report_attachment: "REPORT_ATTACHMENT",
  };
  return map[section] || "GENERAL";
}

function rowAttachmentFilesForRow(key: string, section: SectionKind, row: Record<string, unknown>, index: number): Record<string, unknown>[] {
  const sectionCode = attachmentSectionCodeForRowSection(section);
  const rowId = index + 1;
  const uploaded = attachmentOptionsForKey(key).filter(
    (item) => upper(item.section_code) === sectionCode && Number(item.row_id || 0) === rowId
  );
  const embedded = asArray(row.attachment_files);
  const legacyId = Number(row.linked_attachment_id || 0);
  const legacyName = String(row.linked_attachment_file_name || "").trim();
  const legacyUrl = String(row.linked_attachment_download_url || "").trim();
  const merged = [...embedded, ...uploaded];
  if (section === "report_attachment" && legacyId > 0 && legacyName && !merged.some((item) => Number(item.id || 0) === legacyId)) {
    merged.unshift({
      id: legacyId,
      file_name: legacyName,
      file_kind: row.linked_attachment_file_kind,
      download_url: legacyUrl,
      preview_url: legacyId > 0 ? `/api/v1/site-logs/attachments/${legacyId}/preview` : "",
    });
  }
  const seen = new Set<number>();
  return merged.filter((item) => {
    const id = Number(item.id || 0);
    if (id <= 0) return true;
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function reportAttachmentFilesForRow(key: string, row: Record<string, unknown>, index: number): Record<string, unknown>[] {
  return rowAttachmentFilesForRow(key, "report_attachment", row, index);
}

function reportAttachmentFilesText(row: Record<string, unknown>): string {
  const files = asArray(row.attachment_files);
  if (files.length) return files.map((item) => String(item.file_name || "").trim()).filter(Boolean).join("، ");
  return String(row.linked_attachment_file_name || "").trim();
}

function rowAttachmentFilesText(row: Record<string, unknown>): string {
  const files = asArray(row.attachment_files);
  if (!files.length) return "";
  return files.map((item) => String(item.file_name || "").trim()).filter(Boolean).join("، ");
}

function attachmentFilesFromPayload(row: Record<string, unknown>, includeLegacyReportFile = false): Record<string, unknown>[] {
  const files = [...asArray(row.attachment_files)];
  if (includeLegacyReportFile) {
    const legacyId = Number(row.linked_attachment_id || 0);
    const legacyName = String(row.linked_attachment_file_name || "").trim();
    if (legacyId > 0 && legacyName && !files.some((item) => Number(item.id || 0) === legacyId)) {
      files.unshift({
        id: legacyId,
        file_name: legacyName,
        file_kind: row.linked_attachment_file_kind,
        download_url: row.linked_attachment_download_url,
        preview_url: `/api/v1/site-logs/attachments/${legacyId}/preview`,
      });
    }
  }
  const seen = new Set<number>();
  return files.filter((item) => {
    const id = Number(item.id || 0);
    if (id <= 0) return true;
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function attachmentFileLinksHtml(files: Record<string, unknown>[]): string {
  if (!files.length) return `<span class="sl-report-file-empty">-</span>`;
  return `
    <div class="sl-report-file-list">
      ${files
        .map((item) => {
          const name = String(item.file_name || "").trim() || "file";
          const previewUrl = String(item.preview_url || "").trim() || attachmentPreviewUrl(item);
          const downloadUrl = String(item.download_url || "").trim() || attachmentDownloadUrl(item);
          const id = Number(item.id || 0);
          const preview = previewUrl
            ? `<a class="sl-report-file-link" href="${stateBridge.esc(previewUrl)}" data-sl-action="preview-attachment" data-sl-attachment-id="${id}" data-sl-file-name="${stateBridge.esc(name)}">${stateBridge.esc(name)}</a>`
            : `<span class="sl-report-file-name">${stateBridge.esc(name)}</span>`;
          const download = downloadUrl
            ? `<a class="sl-report-file-action" href="${stateBridge.esc(downloadUrl)}" download>دانلود</a>`
            : "";
          return `<span class="sl-report-file-item">${preview}${download}</span>`;
        })
        .join("")}
    </div>
  `;
}

function rowAttachmentFilesDetailHtml(row: Record<string, unknown>): string {
  return attachmentFileLinksHtml(attachmentFilesFromPayload(row));
}

function reportAttachmentFilesDetailHtml(row: Record<string, unknown>): string {
  return attachmentFileLinksHtml(attachmentFilesFromPayload(row, true));
}

function rowAttachmentFileCellHtml(
  key: string,
  section: SectionKind,
  row: Record<string, unknown>,
  index: number,
  editable: boolean
): string {
  const files = rowAttachmentFilesForRow(key, section, row, index);
  const count = files.length;
  const statusClass = count > 0 ? "has-files" : "is-empty";
  const label = count > 0 ? `${formatFaCount(count)} فایل` : "بدون پیوست";
  return `
    <td class="sl-row-file-status-cell" data-sl-col-label="فایل‌ها">
      <span class="sl-row-file-status ${statusClass}" data-sl-file-status="${section}:${index}" title="${stateBridge.esc(label)}">
        <span class="material-icons-round">attach_file</span>
        <span>${stateBridge.esc(label)}</span>
      </span>
    </td>
  `;
}

function reportAttachmentFileCellHtml(
  key: string,
  row: Record<string, unknown>,
  index: number,
  editable: boolean
): string {
  return rowAttachmentFileCellHtml(key, "report_attachment", row, index, editable);
}

function sectionAttachmentCount(key: string, section: SectionKind, rows: Record<string, unknown>[]): number {
  return rows.reduce((sum, row, index) => sum + rowAttachmentFilesForRow(key, section, row, index).length, 0);
}

function sectionFileStateLabel(sectionEl: HTMLElement | null, fileCount: number): { label: string; className: string } {
  const hasError = Boolean(sectionEl?.querySelector?.(".sl-row-file-status.is-error"));
  const hasPending = Boolean(sectionEl?.querySelector?.(".sl-row-file-status.is-pending"));
  if (hasError) return { label: "خطای آپلود", className: "is-error" };
  if (hasPending) return { label: "در انتظار آپلود", className: "is-pending" };
  if (fileCount > 0) return { label: `${formatFaCount(fileCount)} فایل`, className: "has-files" };
  return { label: "بدون پیوست", className: "is-empty" };
}

function setRowFileStatus(moduleKey: string, tabKey: string, section: SectionKind, index: number, state: "pending" | "error" | "clear"): void {
  const key = keyOf(moduleKey, tabKey);
  const badge = document.querySelector<HTMLElement>(`[data-sl-file-status="${section}:${index}"]`);
  if (!(badge instanceof HTMLElement)) return;
  badge.classList.remove("is-pending", "is-error", "has-files", "is-empty");
  if (state === "pending") {
    badge.classList.add("is-pending");
    badge.title = "در انتظار آپلود";
    const label = badge.querySelector<HTMLElement>("span:last-child");
    if (label) label.textContent = "در انتظار آپلود";
  } else if (state === "error") {
    badge.classList.add("is-error");
    badge.title = "خطای آپلود";
    const label = badge.querySelector<HTMLElement>("span:last-child");
    if (label) label.textContent = "خطای آپلود";
  } else {
    const rows = collectSectionRows(moduleKey, tabKey, section);
    const files = rowAttachmentFilesForRow(key, section, rows[index] || {}, index);
    const fileLabel = files.length ? `${formatFaCount(files.length)} فایل` : "بدون پیوست";
    badge.classList.add(files.length ? "has-files" : "is-empty");
    badge.title = fileLabel;
    const label = badge.querySelector<HTMLElement>("span:last-child");
    if (label) label.textContent = fileLabel;
  }
  updateSectionChrome(moduleKey, tabKey, section);
}

function qcSnapshotForKey(key: string): Record<string, unknown> {
  return asRecord(qcSnapshotByKey[key]);
}

function contractLabel(row: Record<string, unknown>): string {
  const number = String(row.contract_number ?? "").trim();
  const subject = String(row.subject ?? "").trim();
  const blockName = String(row.block_name ?? "").trim();
  const parts = [number, subject, blockName ? `بلوک ${blockName}` : ""].filter(Boolean);
  return parts.join(" | ");
}

function contractSubjectLabel(row: Record<string, unknown>): string {
  return String(row.subject ?? "").trim() || String(row.contract_number ?? "").trim() || "قرارداد بدون موضوع";
}

function selectedContractFromValue(
  organizationId: unknown,
  organizationContractId: unknown,
  contractNumber?: unknown
): Record<string, unknown> | null {
  const currentId = Number(organizationContractId || 0);
  const currentNumber = String(contractNumber ?? "").trim();
  const contracts = contractsForOrganization(organizationId);
  if (currentId > 0) {
    const direct = contracts.find((row) => Number(row.id || 0) === currentId);
    if (direct) return direct;
  }
  if (!currentNumber) return null;
  return contracts.find((row) => String(row.contract_number ?? "").trim() === currentNumber) || null;
}

function syncSelectedContractSnapshot(moduleKey: string, tabKey: string): Record<string, unknown> | null {
  const key = keyOf(moduleKey, tabKey);
  const organizationId = getValue(`sl-form-organization-${key}`);
  const contractId = getValue(`sl-form-contract-subject-${key}`);
  const fallbackNumber = getValue(`sl-form-contract-number-${key}`);
  const fallbackSubject =
    String((getElement(`sl-form-contract-subject-${key}`) as HTMLSelectElement | null)?.dataset.contractSubject || "").trim();
  const fallbackBlock = getValue(`sl-form-contract-block-${key}`);
  const contract = selectedContractFromValue(organizationId, contractId, fallbackNumber);
  const contractNumber = contract ? String(contract.contract_number ?? "").trim() : fallbackNumber;
  const contractSubject = contract ? String(contract.subject ?? "").trim() : fallbackSubject;
  const contractBlock = contract ? String(contract.block_name ?? "").trim() : fallbackBlock;
  setValue(`sl-form-contract-number-${key}`, contractNumber);
  setValue(`sl-form-contract-block-${key}`, contractBlock);
  const select = getElement(`sl-form-contract-subject-${key}`);
  if (select instanceof HTMLSelectElement) {
    select.dataset.contractSubject = contractSubject;
    select.dataset.contractBlock = contractBlock;
  }
  return contract;
}

function syncOrganizationContractSubjectOptions(
  moduleKey: string,
  tabKey: string,
  values?: {
    organizationContractId?: unknown;
    contractNumber?: unknown;
    contractSubject?: unknown;
    contractBlock?: unknown;
  }
): void {
  const key = keyOf(moduleKey, tabKey);
  const select = getElement(`sl-form-contract-subject-${key}`);
  if (!(select instanceof HTMLSelectElement)) return;
  const currentContractId = Number((values?.organizationContractId ?? getValue(`sl-form-contract-subject-${key}`)) || 0);
  const currentNumber = String(values?.contractNumber ?? getValue(`sl-form-contract-number-${key}`) ?? "").trim();
  const currentSubject =
    String(
      values?.contractSubject ??
        select.dataset.contractSubject ??
        ""
    ).trim();
  const currentBlock = String(values?.contractBlock ?? getValue(`sl-form-contract-block-${key}`) ?? "").trim();
  const organizationId = getValue(`sl-form-organization-${key}`);
  const contracts = contractsForOrganization(organizationId);
  let hasCurrent = false;
  const options = [`<option value="">موضوع قرارداد</option>`]
    .concat(
      contracts.map((row) => {
        const value = Number(row.id || 0);
        if (value <= 0) return "";
        if (value === currentContractId) hasCurrent = true;
        const selected = value === currentContractId ? " selected" : "";
        return `<option value="${value}"${selected}>${stateBridge.esc(contractLabel(row) || contractSubjectLabel(row))}</option>`;
      })
    )
    .filter(Boolean);
  if ((currentContractId > 0 || currentNumber) && !hasCurrent) {
    const legacyValue = currentContractId > 0 ? String(currentContractId) : "";
    const legacyLabel = currentSubject || currentNumber || "قرارداد قبلی";
    options.push(`<option value="${stateBridge.esc(legacyValue)}" selected>${stateBridge.esc(legacyLabel)} (مقدار قبلی)</option>`);
  }
  select.innerHTML = options.join("");
  if (currentContractId > 0) {
    select.value = String(currentContractId);
  } else if (!currentNumber) {
    select.value = "";
  }

  const contract = selectedContractFromValue(organizationId, select.value, currentNumber);
  setValue(`sl-form-contract-number-${key}`, contract ? contract.contract_number : currentNumber || "");
  setValue(`sl-form-contract-block-${key}`, contract ? contract.block_name : currentBlock || "");
  select.dataset.contractSubject = contract ? String(contract.subject ?? "").trim() : currentSubject || "";
  select.dataset.contractBlock = contract ? String(contract.block_name ?? "").trim() : currentBlock || "";
}

function boardFilterContractRows(organizationId: unknown): Record<string, unknown>[] {
  const orgId = Number(organizationId || 0);
  if (orgId > 0) return contractsForOrganization(orgId);
  return organizationsFromCatalog().flatMap((org) => {
    const orgName = String(org.name ?? "").trim();
    return asArray(org.contracts).map((contract) => ({ ...asRecord(contract), organization_name: orgName }));
  });
}

function boardFilterContractLabel(row: Record<string, unknown>, includeOrganization = false): string {
  const label = contractLabel(row) || contractSubjectLabel(row);
  const orgName = includeOrganization ? String(row.organization_name ?? "").trim() : "";
  return [label, orgName].filter(Boolean).join(" - ");
}

function boardFilterContractOptions(organizationId: unknown, current = ""): string {
  const normalizedCurrent = String(current ?? "").trim();
  const includeOrganization = Number(organizationId || 0) <= 0;
  const options = boardFilterContractRows(organizationId)
    .map((row) => {
      const value = String(row.id ?? "").trim();
      if (!value) return "";
      const selected = value === normalizedCurrent ? " selected" : "";
      return `<option value="${stateBridge.esc(value)}"${selected}>${stateBridge.esc(
        boardFilterContractLabel(row, includeOrganization)
      )}</option>`;
    })
    .filter(Boolean)
    .join("");
  return `<option value="">همه قراردادها</option>${options}`;
}

function syncBoardContractFilterOptions(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const select = getElement(`sl-filter-contract-${key}`);
  if (!(select instanceof HTMLSelectElement)) return;
  const organizationId = getValue(`sl-filter-organization-${key}`);
  const current = select.value;
  select.innerHTML = boardFilterContractOptions(organizationId, current);
  if (current && !Array.from(select.options).some((option) => option.value === current)) {
    select.value = "";
  }
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
  if (code === "RETURNED") return "برگشت‌شده";
  if (code === "VERIFIED") return "تاییدشده";
  return code || "-";
}

function workStatusLabelFa(value: unknown): string {
  const code = upper(value) || "ACTIVE";
  if (code === "ACTIVE") return "فعال";
  if (code === "HOLIDAY") return "تعطیل";
  if (code === "INACTIVE") return "غیرفعال";
  return code || "-";
}

function workStatusOptions(current = "ACTIVE"): string {
  const rows = optionRowsFromCatalog("work_statuses");
  if (!rows.length) {
    const fallback = ["ACTIVE", "HOLIDAY", "INACTIVE"];
    return fallback
      .map((code) => `<option value="${code}"${upper(current) === code ? " selected" : ""}>${stateBridge.esc(workStatusLabelFa(code))}</option>`)
      .join("");
  }
  const normalizedCurrent = upper(current) || "ACTIVE";
  const hasCurrent = rows.some((row) => upper(row.code || "") === normalizedCurrent);
  const rendered = rows
    .map((row) => {
      const code = upper(row.code || "");
      if (!code) return "";
      const selected = code === normalizedCurrent ? " selected" : "";
      return `<option value="${stateBridge.esc(code)}"${selected}>${stateBridge.esc(String(row.label || workStatusLabelFa(code)))}</option>`;
    })
    .join("");
  if (normalizedCurrent && !hasCurrent) {
    return `${rendered}<option value="${stateBridge.esc(normalizedCurrent)}" selected>${stateBridge.esc(workStatusLabelFa(normalizedCurrent))}</option>`;
  }
  return rendered;
}

function workStatusFilterOptions(current = ""): string {
  const rows = optionRowsFromCatalog("work_statuses");
  const fallbackRows = [
    { code: "ACTIVE", label: workStatusLabelFa("ACTIVE") },
    { code: "HOLIDAY", label: workStatusLabelFa("HOLIDAY") },
    { code: "INACTIVE", label: workStatusLabelFa("INACTIVE") },
  ];
  const options = rows.length ? rows : fallbackRows;
  const normalizedCurrent = upper(current);
  return options
    .map((row) => {
      const code = upper(row.code || "");
      if (!code) return "";
      const selected = normalizedCurrent === code ? " selected" : "";
      return `<option value="${stateBridge.esc(code)}"${selected}>${stateBridge.esc(String(row.label || workStatusLabelFa(code)))}</option>`;
    })
    .join("");
}

function workflowStatusOptions(current = "DRAFT"): string {
  const rows = optionRowsFromCatalog("workflow_statuses");
  if (!rows.length) {
    const fallback = ["DRAFT", "RETURNED", "SUBMITTED", "VERIFIED"];
    return fallback
      .map((code) => `<option value="${code}"${upper(current) === code ? " selected" : ""}>${stateBridge.esc(statusLabelFa(code))}</option>`)
      .join("");
  }
  const normalizedCurrent = upper(current);
  const hasCurrent = rows.some((row) => upper(row.code || "") === normalizedCurrent);
  const rendered = rows
    .map((row) => {
      const code = upper(row.code || "");
      if (!code) return "";
      const selected = code === upper(current) ? " selected" : "";
      return `<option value="${stateBridge.esc(code)}"${selected}>${stateBridge.esc(statusLabelFa(code))}</option>`;
    })
    .join("");
  if (normalizedCurrent && !hasCurrent) {
    return `${rendered}<option value="${stateBridge.esc(normalizedCurrent)}" selected>${stateBridge.esc(statusLabelFa(normalizedCurrent))}</option>`;
  }
  return rendered;
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

function catalogCodeOptions(catalogKey: string, current = "", placeholder = "انتخاب..."): string {
  return optionHtml(optionRowsFromCatalog(catalogKey), "code", "label", placeholder, upper(current), current);
}

function optionRowsForField(key: string, field: SectionFieldDef): Record<string, unknown>[] {
  if (field.catalog === "__report_attachment_links__") {
    return attachmentOptionsForKey(key);
  }
  return field.catalog ? optionRowsFromCatalog(field.catalog) : [];
}

function searchNeedle(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/ي/g, "ی")
    .replace(/ك/g, "ک")
    .replace(/\s+/g, " ");
}

function catalogFieldLabel(row: Record<string, unknown>, valueKey: string, labelKey: string): string {
  const value = String(row[valueKey] ?? "").trim();
  return String(row[labelKey] ?? value).trim() || value;
}

function catalogDatalistOptions(rows: Record<string, unknown>[], valueKey: string, labelKey: string): string {
  return rows
    .map((row) => {
      const value = String(row[valueKey] ?? "").trim();
      if (!value) return "";
      const label = catalogFieldLabel(row, valueKey, labelKey);
      const hint = label && label !== value ? ` label="${stateBridge.esc(value)}"` : "";
      return `<option value="${stateBridge.esc(label || value)}"${hint}></option>`;
    })
    .filter(Boolean)
    .join("");
}

function matchCatalogTypeaheadRow(
  rows: Record<string, unknown>[],
  query: unknown,
  valueKey: string,
  labelKey: string,
  exactOnly = false
): Record<string, unknown> | null {
  const q = searchNeedle(query);
  if (!q) return null;
  const ranked = rows
    .map((row) => {
      const value = String(row[valueKey] ?? "").trim();
      const label = catalogFieldLabel(row, valueKey, labelKey);
      const values = [value, label, `${value} ${label}`, `${label} ${value}`].filter(Boolean);
      let rank = 999;
      values.forEach((item) => {
        const candidate = searchNeedle(item);
        if (!candidate) return;
        if (candidate === q) rank = Math.min(rank, 0);
        else if (!exactOnly && candidate.startsWith(q)) rank = Math.min(rank, 1);
        else if (!exactOnly && candidate.includes(q)) rank = Math.min(rank, 2);
      });
      return { row, rank };
    })
    .filter((item) => item.rank < 999)
    .sort((a, b) => a.rank - b.rank);
  return ranked[0]?.row || null;
}

function catalogDisplayValue(
  rawValue: unknown,
  rows: Record<string, unknown>[],
  valueKey: string,
  labelKey: string,
  useDisplayLabel: boolean
): string {
  const current = String(rawValue ?? "").trim();
  if (!current) return "";
  const row = rows.find((item) => String(item[valueKey] ?? "").trim() === current);
  return useDisplayLabel && row ? catalogFieldLabel(row, valueKey, labelKey) : current;
}

function activityOptionLabel(row: Record<string, unknown>): string {
  const code = String(row.activity_code ?? "").trim();
  const title = String(row.activity_title ?? "").trim();
  const location = String(row.default_location ?? "").trim();
  const unit = String(row.default_unit ?? "").trim();
  const scopeLabel = String(row.scope_label ?? "").trim();
  return [code, title, location, unit, scopeLabel].filter(Boolean).join(" | ");
}

function activityOptionDatalistOptions(key: string): string {
  return activityOptionsForKey(key)
    .map((row) => {
      const id = Number(row.id || 0);
      if (id <= 0) return "";
      return `<option value="${stateBridge.esc(activityOptionLabel(row))}"></option>`;
    })
    .filter(Boolean)
    .join("");
}

function activityTitleDatalistOptions(key: string): string {
  return activityOptionsForKey(key)
    .map((row) => {
      const label = activityOptionLabel(row);
      if (!label) return "";
      return `<option value="${stateBridge.esc(label)}"></option>`;
    })
    .filter(Boolean)
    .join("");
}

function matchActivityOption(key: string, query: unknown, exactOnly = false): Record<string, unknown> | null {
  const q = searchNeedle(query);
  if (!q) return null;
  const ranked = activityOptionsForKey(key)
    .map((row) => {
      const values = [
        activityOptionLabel(row),
        row.activity_code,
        row.activity_title,
        row.default_location,
        row.default_unit,
        row.scope_label,
      ];
      let rank = 999;
      values.forEach((item) => {
        const candidate = searchNeedle(item);
        if (!candidate) return;
        if (candidate === q) rank = Math.min(rank, 0);
        else if (!exactOnly && candidate.startsWith(q)) rank = Math.min(rank, 1);
        else if (!exactOnly && candidate.includes(q)) rank = Math.min(rank, 2);
      });
      return { row, rank };
    })
    .filter((item) => item.rank < 999)
    .sort((a, b) => a.rank - b.rank);
  return ranked[0]?.row || null;
}

function pmsStepsForActivityRow(key: string, row: Record<string, unknown>): Record<string, unknown>[] {
  const direct = asArray(row.pms_steps);
  if (direct.length) return direct;
  const mappingId = Number(row.pms_mapping_id || 0);
  const externalRef = String(row.external_ref || "");
  const catalogId = Number((externalRef.match(/site_log_activity_catalog:(\d+)/) || [])[1] || 0);
  const option = activityOptionsForKey(key).find((item) => {
    if (mappingId > 0 && Number(item.pms_mapping_id || 0) === mappingId) return true;
    if (catalogId > 0 && Number(item.id || 0) === catalogId) return true;
    return false;
  });
  return asArray(option?.pms_steps);
}

function pmsStepDisplayValue(step: Record<string, unknown>): string {
  const code = String(step.step_code ?? "").trim();
  const title = String(step.step_title ?? code).trim();
  const weight = Number(step.weight_pct || 0);
  return [code, title, weight ? formatNumber(weight, 0, "%") : ""].filter(Boolean).join(" | ");
}

function pmsStepTypeaheadHtml(key: string, row: Record<string, unknown>, disabled: string, listScope: string): string {
  const steps = pmsStepsForActivityRow(key, row);
  const current = String(row.pms_step_code ?? "").trim();
  if (!steps.length && !current) {
    return `<input class="module-crud-input sl-typeahead-input" type="text" value="بدون PMS" disabled>`;
  }
  const optionRows = steps.slice();
  if (current && !optionRows.some((step) => String(step.step_code ?? "").trim() === current)) {
    optionRows.push({
      step_code: current,
      step_title: row.pms_step_title || current,
      weight_pct: row.pms_step_weight_pct || 0,
    });
  }
  const currentStep = optionRows.find((step) => String(step.step_code ?? "").trim() === current);
  const display = currentStep
    ? pmsStepDisplayValue(currentStep)
    : [current, row.pms_step_title, row.pms_step_weight_pct ? formatNumber(Number(row.pms_step_weight_pct || 0), 0, "%") : ""]
        .filter(Boolean)
        .join(" | ");
  const listId = `sl-pms-step-list-${key}-${listScope}`;
  const options = optionRows
    .map((step) => `<option value="${stateBridge.esc(pmsStepDisplayValue(step))}"></option>`)
    .join("");
  return `
    <div class="sl-typeahead-control">
      <input type="hidden" class="sl-row-input" data-sl-field="pms_step_code" value="${stateBridge.esc(current)}">
      <input class="module-crud-input sl-typeahead-input" type="text" list="${stateBridge.esc(listId)}" value="${stateBridge.esc(display)}" data-sl-typeahead="pms-step" data-sl-target-field="pms_step_code"${disabled} placeholder="کد یا عنوان PMS...">
      <datalist id="${stateBridge.esc(listId)}">${options}</datalist>
    </div>
  `;
}

function activityTitleTypeaheadHtml(key: string, row: Record<string, unknown>, disabled: string, listScope: string): string {
  const current = String(row.activity_title ?? "").trim();
  const listId = `sl-activity-title-list-${key}-${listScope}`;
  const placeholder = activityOptionsForKey(key).length ? "کد، عنوان، محل یا واحد را بنویسید..." : "عنوان فعالیت را بنویسید...";
  return `
    <div class="sl-typeahead-control">
      <input class="module-crud-input sl-row-input sl-typeahead-input" data-sl-field="activity_title" type="text" list="${stateBridge.esc(listId)}" value="${stateBridge.esc(current)}" data-sl-typeahead="activity-title"${disabled} placeholder="${stateBridge.esc(placeholder)}">
      <datalist id="${stateBridge.esc(listId)}" data-sl-activity-title-list="${stateBridge.esc(key)}">${activityTitleDatalistOptions(key)}</datalist>
    </div>
  `;
}

function activityPickerHtml(key: string): string {
  const options = activityOptionsForKey(key);
  const placeholder = options.length ? "کد، عنوان، محل یا واحد فعالیت را بنویسید..." : "برای این قرارداد کاتالوگ فعالیتی تعریف نشده است";
  return `
    <div class="sl-section-toolbar">
      <div class="sl-typeahead-control">
        <input id="sl-activity-picker-${key}" class="module-crud-input sl-typeahead-input" type="text" list="sl-activity-picker-list-${key}" data-sl-typeahead="activity-picker" placeholder="${stateBridge.esc(placeholder)}">
        <datalist id="sl-activity-picker-list-${key}">${activityOptionDatalistOptions(key)}</datalist>
      </div>
      <button type="button" class="btn-archive-icon" data-sl-action="add-activity-option">افزودن از فهرست</button>
    </div>
  `;
}

function sectionTableHtml(section: SectionKind, key: string): string {
  const def = SECTION_DEFS[section];
  const mainFields = mainFieldsForSection(section);
  const header = mainFields
    .map((field) => `<th>${stateBridge.esc(field.label)}</th>`)
    .join("");
  const addButtonLabel = def.addButtonLabel || "افزودن ردیف";
  const collapsed = isSectionCollapsed(key, section);
  const sectionLabel = stateBridge.esc(def.title);
  return `
    <section id="sl-section-${section}-${key}" class="ci-form-section sl-form-section${collapsed ? " is-collapsed" : ""}" data-sl-section-wrap="${section}">
      <div class="sl-section-header">
        <div class="sl-section-heading">
          <button type="button" class="btn-archive-icon sl-section-toggle" data-sl-action="toggle-section" data-sl-section="${section}" aria-expanded="${collapsed ? "false" : "true"}" title="${collapsed ? "باز کردن بخش" : "بستن بخش"}">
            <span class="material-icons-round">${collapsed ? "keyboard_arrow_down" : "keyboard_arrow_up"}</span>
          </button>
          <h4 class="module-crud-form-title">${sectionLabel}</h4>
          <span id="sl-section-count-${section}-${key}" class="sl-section-badge">۰ ردیف</span>
          <span id="sl-section-files-${section}-${key}" class="sl-section-file-badge is-empty">بدون پیوست</span>
        </div>
        <div class="sl-section-actions">
          <button type="button" class="btn-archive-icon" data-sl-action="copy-last-row" data-sl-section="${section}" title="کپی ردیف قبلی">
            <span class="material-icons-round">content_copy</span>
          </button>
          <button type="button" class="btn-archive-icon" data-sl-action="add-row" data-sl-section="${section}">${stateBridge.esc(addButtonLabel)}</button>
        </div>
      </div>
      <div id="sl-section-content-${section}-${key}" class="sl-section-content"${collapsed ? " hidden" : ""}>
        ${def.toolbar === "activity-picker" ? activityPickerHtml(key) : ""}
        <div class="module-crud-table-wrap">
          <table class="module-crud-table sl-row-table">
            <thead>
              <tr>${header}<th>عملیات</th></tr>
            </thead>
            <tbody id="${sectionBodyId(section, key)}"></tbody>
          </table>
        </div>
      </div>
    </section>
  `;
}

function formAnchorBarHtml(key: string): string {
  const items = [
    ["base", "اطلاعات اصلی"],
    ["summary", "خلاصه مدیریت"],
    ["manpower", "منابع"],
    ["activity", "فعالیت‌ها"],
    ["material", "مصالح"],
    ["issue", "موانع"],
    ["qc", "QC"],
    ["report_attachment", "پیوست‌ها"],
  ];
  return `
    <nav class="sl-form-anchor-bar" aria-label="دسترسی سریع فرم">
      ${items
        .map(
          ([target, label]) => `
            <button type="button" class="sl-form-anchor" data-sl-action="jump-section" data-sl-target="${target}">
              ${stateBridge.esc(label)}
            </button>
          `
        )
        .join("")}
    </nav>
  `;
}

function catalogTypeaheadHtml(
  key: string,
  field: SectionFieldDef,
  row: Record<string, unknown>,
  disabled: string,
  listScope: string
): string {
  const valueKey = field.catalogValueKey || "code";
  const labelKey = field.catalogLabelKey || "label";
  const rows = optionRowsForField(key, field);
  const rawValue = String(row[field.key] ?? "");
  const useHiddenStoredValue = valueKey !== "label";
  const display = catalogDisplayValue(rawValue, rows, valueKey, labelKey, useHiddenStoredValue);
  const listId = `sl-catalog-list-${key}-${listScope}-${field.key}`;
  const commonAttrs = `data-sl-catalog="${stateBridge.esc(
    field.catalog || ""
  )}" data-sl-value-key="${stateBridge.esc(valueKey)}" data-sl-label-key="${stateBridge.esc(
    labelKey
  )}" data-sl-target-field="${stateBridge.esc(field.key)}"`;
  const options = catalogDatalistOptions(rows, valueKey, labelKey);
  const placeholder = rows.length ? `جستجو و انتخاب ${field.label}` : `برای ${field.label} کاتالوگی تعریف نشده است`;
  if (useHiddenStoredValue) {
    return `
      <div class="sl-typeahead-control">
        <input type="hidden" class="sl-row-input" data-sl-field="${stateBridge.esc(field.key)}" value="${stateBridge.esc(rawValue)}">
        <input class="module-crud-input sl-typeahead-input" type="text" list="${stateBridge.esc(listId)}" value="${stateBridge.esc(
          display || rawValue
        )}" data-sl-typeahead="catalog" ${commonAttrs}${disabled} placeholder="${stateBridge.esc(placeholder)}">
        <datalist id="${stateBridge.esc(listId)}">${options}</datalist>
      </div>
    `;
  }
  return `
    <div class="sl-typeahead-control">
      <input class="module-crud-input sl-row-input sl-typeahead-input" data-sl-field="${stateBridge.esc(
        field.key
      )}" type="text" list="${stateBridge.esc(listId)}" value="${stateBridge.esc(display || rawValue)}" data-sl-typeahead="catalog" ${commonAttrs}${disabled} placeholder="${stateBridge.esc(
        placeholder
      )}">
      <datalist id="${stateBridge.esc(listId)}">${options}</datalist>
    </div>
  `;
}

function rowFieldControlHtml(
  key: string,
  field: SectionFieldDef,
  row: Record<string, unknown>,
  disabled: string,
  listScope = "main"
): string {
  const rawValue = String(row[field.key] ?? "");
  if (field.key === "pms_step_code") {
    return pmsStepTypeaheadHtml(key, row, disabled, listScope);
  }
  if (field.activityTitle) {
    return activityTitleTypeaheadHtml(key, row, disabled, listScope);
  }
  if (field.catalog) {
    return catalogTypeaheadHtml(key, field, row, disabled, listScope);
  }
  const type = field.type || (field.detail ? "textarea" : "text");
  const step = field.step ? ` step="${field.step}"` : "";
  const placeholder = field.placeholder ? ` placeholder="${stateBridge.esc(field.placeholder)}"` : "";
  const value = stateBridge.esc(rawValue);
  if (type === "textarea") {
    return `<textarea class="module-crud-textarea sl-row-input" data-sl-field="${field.key}"${disabled}${placeholder}>${value}</textarea>`;
  }
  return `<input class="module-crud-input sl-row-input" data-sl-field="${field.key}" type="${type}" value="${value}"${step}${disabled}${placeholder}>`;
}

function rowFieldCellHtml(
  key: string,
  section: SectionKind,
  row: Record<string, unknown>,
  index: number,
  field: SectionFieldDef,
  mode: FormMode,
  capabilities: { canCreate: boolean; canVerify: boolean }
): string {
  const editable = canEditField(field.group, mode, capabilities);
  const disabled = editable ? "" : " disabled";
  if (field.key === "__files") {
    return rowAttachmentFileCellHtml(key, section, row, index, editable);
  }
  return `<td data-sl-col-label="${stateBridge.esc(field.label)}">${rowFieldControlHtml(
    key,
    field,
    row,
    disabled,
    `${section}-${index}`
  )}</td>`;
}

function rowDetailHtml(
  key: string,
  section: SectionKind,
  row: Record<string, unknown>,
  index: number,
  mode: FormMode,
  capabilities: { canCreate: boolean; canVerify: boolean },
  colSpan: number
): string {
  const fields = detailFieldsForSection(section);
  const files = rowAttachmentFilesForRow(key, section, row, index);
  const fileSummary = files.length
    ? files.map((item) => String(item.file_name || "").trim()).filter(Boolean).join("، ")
    : "پیوستی ثبت نشده است.";
  const fieldHtml = fields
    .map((field) => {
      const editable = canEditField(field.group, mode, capabilities);
      const disabled = editable ? "" : " disabled";
      return `
        <label class="sl-row-detail-field">
          <span>${stateBridge.esc(field.label)}</span>
          ${rowFieldControlHtml(key, field, row, disabled, `${section}-${index}-detail`)}
        </label>
      `;
    })
    .join("");
  return `
    <tr class="sl-row-detail" data-sl-row-detail-for="${index}" hidden>
      <td colspan="${colSpan}">
        <div class="sl-row-detail-panel">
          ${fieldHtml}
          <div class="sl-row-detail-field sl-row-detail-files">
            <span>پیوست‌ها</span>
            <strong>${stateBridge.esc(fileSummary)}</strong>
          </div>
        </div>
      </td>
    </tr>
  `;
}

function buildBoardCard(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): string {
  const key = keyOf(moduleKey, tabKey);
  const title = boardTitle(moduleKey, tabKey);
  const capabilities = boardCapabilities(moduleKey, tabKey, deps);
  const projects = optionRowsFromCatalog("projects");
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
        <div class="module-crud-toolbar-right" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;flex:1 1 100%;min-width:0;width:100%;">
          <select id="sl-filter-project-${key}" class="module-crud-select" data-sl-action="filter-project">${optionHtml(projects, "code", "name", "پروژه")}</select>
          <select id="sl-filter-organization-${key}" class="module-crud-select" data-sl-action="filter-organization">${optionHtml(organizations, "id", "name", "سازمان")}</select>
          <select id="sl-filter-contract-${key}" class="module-crud-select" data-sl-action="filter-contract">${boardFilterContractOptions("", "")}</select>
          <select id="sl-filter-log-type-${key}" class="module-crud-select" data-sl-action="filter-log-type"><option value="">نوع گزارش</option>${logTypeOptions("")}</select>
          <select id="sl-filter-status-${key}" class="module-crud-select" data-sl-action="filter-status"><option value="">وضعیت</option>${workflowStatusOptions("")}</select>
          <select id="sl-filter-work-status-${key}" class="module-crud-select" data-sl-action="filter-work-status"><option value="">وضعیت کارگاه</option>${workStatusFilterOptions("")}</select>
          <input id="sl-filter-date-from-${key}" class="module-crud-input" type="date" title="از تاریخ" aria-label="از تاریخ" data-sl-action="filter-date-from">
          <input id="sl-filter-date-to-${key}" class="module-crud-input" type="date" title="تا تاریخ" aria-label="تا تاریخ" data-sl-action="filter-date-to">
          <input id="sl-filter-search-${key}" class="module-crud-input" type="text" placeholder="جستجو شماره گزارش، قرارداد یا خلاصه" data-sl-action="filter-search">
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
              ${formAnchorBarHtml(key)}
              <div id="sl-section-base-${key}" class="module-crud-form-grid">
                <div class="module-crud-form-field">
                  <label for="sl-form-project-${key}">پروژه</label>
                  <select id="sl-form-project-${key}" class="module-crud-select">${optionHtml(projects, "code", "name", "پروژه")}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-organization-${key}">سازمان</label>
                  <select id="sl-form-organization-${key}" class="module-crud-select">${optionHtml(organizations, "id", "name", "سازمان")}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-contract-subject-${key}">موضوع قرارداد</label>
                  <select id="sl-form-contract-subject-${key}" class="module-crud-select"><option value="">موضوع قرارداد</option></select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-contract-number-${key}">شماره قرارداد</label>
                  <input id="sl-form-contract-number-${key}" class="module-crud-input" type="text" placeholder="خودکار از موضوع قرارداد" readonly>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-contract-block-${key}">بلوک قرارداد</label>
                  <input id="sl-form-contract-block-${key}" class="module-crud-input" type="text" placeholder="خودکار از موضوع قرارداد" readonly>
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
                  <label for="sl-form-work-status-${key}">وضعیت کارگاه</label>
                  <select id="sl-form-work-status-${key}" class="module-crud-select">${workStatusOptions("ACTIVE")}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-shift-${key}">شیفت</label>
                  <select id="sl-form-shift-${key}" class="module-crud-select">${catalogCodeOptions("shift_catalog", "", "شیفت")}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-weather-${key}">وضعیت جوی</label>
                  <select id="sl-form-weather-${key}" class="module-crud-select">${catalogCodeOptions("weather_catalog", "", "وضعیت جوی")}</select>
                </div>
                <div class="module-crud-form-field">
                  <label for="sl-form-status-${key}">وضعیت</label>
                  <select id="sl-form-status-${key}" class="module-crud-select" disabled>${workflowStatusOptions("DRAFT")}</select>
                </div>
              </div>

              <section id="sl-section-summary-${key}" class="ci-form-section">
                <div class="sl-section-header">
                  <h4 class="module-crud-form-title">خلاصه مدیریت</h4>
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;">
                  <div class="module-crud-form-field">
                    <label for="sl-form-current-work-${key}">کارهای در حال انجام</label>
                    <textarea id="sl-form-current-work-${key}" class="module-crud-textarea" placeholder="خلاصه عملیات و وضعیت جاری"></textarea>
                  </div>
                  <div class="module-crud-form-field">
                    <label for="sl-form-next-plan-${key}">برنامه بعدی</label>
                    <textarea id="sl-form-next-plan-${key}" class="module-crud-textarea" placeholder="برنامه فردا یا مرحله بعد"></textarea>
                  </div>
                </div>
              </section>

              ${sectionTableHtml("manpower", key)}
              ${sectionTableHtml("equipment", key)}
              ${sectionTableHtml("activity", key)}
              ${sectionTableHtml("material", key)}
              ${sectionTableHtml("issue", key)}
              ${sectionTableHtml("report_attachment", key)}

              <section id="sl-section-qc-${key}" class="ci-form-section">
                <div class="sl-section-header">
                  <h4 class="module-crud-form-title">QC</h4>
                </div>
                <div id="sl-qc-cards-${key}" class="sl-qc-grid">
                  <article class="sl-qc-card"><span>تست</span><strong>0</strong></article>
                  <article class="sl-qc-card"><span>بازرسی</span><strong>0</strong></article>
                  <article class="sl-qc-card"><span>Punch باز</span><strong>0</strong></article>
                  <article class="sl-qc-card"><span>NCR باز</span><strong>0</strong></article>
                </div>
                <div class="module-crud-form-grid">
                  <div class="module-crud-form-field">
                    <label for="sl-form-qc-open-punch-${key}">Punch باز</label>
                    <input id="sl-form-qc-open-punch-${key}" class="module-crud-input" type="number" min="0" step="1" placeholder="ورودی دستی">
                  </div>
                  <div class="module-crud-form-field module-crud-form-field-span-2">
                    <label for="sl-form-qc-note-${key}">شرح کیفیت / اقدام اصلاحی</label>
                    <textarea id="sl-form-qc-note-${key}" class="module-crud-textarea" placeholder="توضیح تست‌ها، بازرسی‌ها، NCR یا اقدام اصلاحی"></textarea>
                  </div>
                </div>
                <div id="sl-qc-meta-${key}" class="sl-qc-meta"></div>
              </section>

              <section id="sl-comments-wrap-${key}" class="ci-form-section" hidden>
                <h4 class="module-crud-form-title">یادداشت‌ها</h4>
                <div id="sl-comments-${key}" style="margin-bottom:8px;"></div>
                <div class="sl-comment-box">
                  <input id="sl-comment-input-${key}" class="module-crud-input" type="text" placeholder="متن یادداشت">
                  <button id="sl-return-action-${key}" type="button" class="btn btn-danger" data-sl-action="return-form" hidden>
                    <span class="material-icons-round">keyboard_return</span><span>برگشت برای اصلاح</span>
                  </button>
                </div>
              </section>

              <div class="module-crud-form-actions is-sticky sl-form-sticky-actions">
                <button type="button" class="btn btn-secondary" data-sl-action="close-form"><span class="material-icons-round">close</span><span>انصراف</span></button>
                ${capabilities.canCreate ? `<button type="button" class="btn btn-primary" data-sl-action="save-form"><span class="material-icons-round">save</span><span>ذخیره</span></button>` : ""}
                ${capabilities.canCreate ? `<button type="button" class="btn btn-primary" data-sl-action="submit-form"><span class="material-icons-round">send</span><span>ارسال</span></button>` : ""}
                ${capabilities.canVerify ? `<button type="button" class="btn btn-primary" data-sl-action="verify-form"><span class="material-icons-round">verified</span><span>تایید</span></button>` : ""}
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
  const mainFields = mainFieldsForSection(section);
  const colSpan = mainFields.length + 1;
  const allowRemove = mode !== "detail" && (capabilities.canCreate || capabilities.canVerify);
  body.innerHTML = normalizedRows
    .map((row, index) => {
      const fieldsHtml = mainFields
        .map((field) => rowFieldCellHtml(key, section, row, index, field, mode, capabilities))
        .join("");
      const hiddenHtml = (def.hiddenKeys || [])
        .map((hiddenKey) => {
          const hiddenValue = stateBridge.esc(String(row[hiddenKey] ?? ""));
          return `<input type="hidden" data-sl-field="${hiddenKey}" value="${hiddenValue}">`;
        })
        .join("");
      const rowDbId = Number(row.id || 0);
      const rowDbIdAttr = Number.isFinite(rowDbId) && rowDbId > 0 ? String(rowDbId) : "";
      const attachmentEditable = canEditField("base", mode, capabilities);
      return `
        <tr data-sl-row-index="${index}" data-sl-row-db-id="${rowDbIdAttr}">
          ${fieldsHtml}
          <td data-sl-col-label="عملیات">${rowActionsHtml(key, section, row, index, allowRemove, attachmentEditable, detailFieldsForSection(section).length > 0)}${hiddenHtml}</td>
        </tr>
        ${rowDetailHtml(key, section, row, index, mode, capabilities, colSpan)}
      `;
    })
    .join("");
  updateSectionChrome(moduleKey, tabKey, section, normalizedRows);
}

function collectSectionRows(moduleKey: string, tabKey: string, section: SectionKind): Record<string, unknown>[] {
  const key = keyOf(moduleKey, tabKey);
  const body = getElement(sectionBodyId(section, key));
  if (!(body instanceof HTMLElement)) return [];
  const rows: Record<string, unknown>[] = [];
  body.querySelectorAll<HTMLTableRowElement>("tr[data-sl-row-index]").forEach((rowEl, idx) => {
    const row: Record<string, unknown> = { sort_order: idx };
    const dbRowId = Number(rowEl.dataset.slRowDbId || 0);
    if (Number.isFinite(dbRowId) && dbRowId > 0) {
      row.id = dbRowId;
    }
    rowEl.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("[data-sl-field]").forEach((fieldEl) => {
      const field = String(fieldEl.dataset.slField || "").trim();
      if (!field || field.startsWith("__")) return;
      row[field] = fieldEl.value;
    });
    const detailEl = body.querySelector<HTMLTableRowElement>(`tr[data-sl-row-detail-for="${idx}"]`);
    detailEl?.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("[data-sl-field]").forEach((fieldEl) => {
      const field = String(fieldEl.dataset.slField || "").trim();
      if (!field || field.startsWith("__")) return;
      row[field] = fieldEl.value;
    });
    rows.push(row);
  });
  return rows;
}

function updateSectionChrome(moduleKey: string, tabKey: string, section: SectionKind, suppliedRows?: Record<string, unknown>[]): void {
  const key = keyOf(moduleKey, tabKey);
  const rows = suppliedRows || collectSectionRows(moduleKey, tabKey, section);
  const filledCount = rows.filter((row) => isMeaningfulSectionRow(section, row)).length;
  const countEl = getElement(`sl-section-count-${section}-${key}`);
  if (countEl) {
    countEl.textContent = `${formatFaCount(filledCount)} ردیف`;
  }
  const sectionEl = getElement(`sl-section-${section}-${key}`);
  const fileCount = sectionAttachmentCount(key, section, rows);
  const fileState = sectionFileStateLabel(sectionEl, fileCount);
  const fileEl = getElement(`sl-section-files-${section}-${key}`);
  if (fileEl) {
    fileEl.textContent = fileState.label;
    fileEl.className = `sl-section-file-badge ${fileState.className}`;
  }
}

function readForm(moduleKey: string, tabKey: string): Record<string, unknown> {
  const key = keyOf(moduleKey, tabKey);
  const contractSelect = getElement(`sl-form-contract-subject-${key}`) as HTMLSelectElement | null;
  return {
    id: Number(getValue(`sl-form-id-${key}`) || 0),
    log_type: getValue(`sl-form-log-type-${key}`),
    project_code: getValue(`sl-form-project-${key}`),
    discipline_code: "",
    organization_id: getValue(`sl-form-organization-${key}`),
    organization_contract_id: getValue(`sl-form-contract-subject-${key}`),
    log_date: getValue(`sl-form-log-date-${key}`),
    work_status: getValue(`sl-form-work-status-${key}`) || "ACTIVE",
    shift: getValue(`sl-form-shift-${key}`),
    contract_number: getValue(`sl-form-contract-number-${key}`),
    contract_subject: String(contractSelect?.dataset.contractSubject || "").trim(),
    contract_block: getValue(`sl-form-contract-block-${key}`),
    qc_open_punch_count: getValue(`sl-form-qc-open-punch-${key}`),
    qc_summary_note: getValue(`sl-form-qc-note-${key}`),
    weather: getValue(`sl-form-weather-${key}`),
    summary: "",
    current_work_summary: getValue(`sl-form-current-work-${key}`),
    next_plan_summary: getValue(`sl-form-next-plan-${key}`),
    status_code: getValue(`sl-form-status-${key}`) || "DRAFT",
    manpower_rows: collectSectionRows(moduleKey, tabKey, "manpower"),
    equipment_rows: collectSectionRows(moduleKey, tabKey, "equipment"),
    activity_rows: collectSectionRows(moduleKey, tabKey, "activity"),
    material_rows: collectSectionRows(moduleKey, tabKey, "material"),
    issue_rows: collectSectionRows(moduleKey, tabKey, "issue"),
    attachment_rows: collectSectionRows(moduleKey, tabKey, "report_attachment"),
    note: getValue(`sl-comment-input-${key}`),
  };
}

function setFormMode(moduleKey: string, tabKey: string, mode: FormMode): void {
  const key = keyOf(moduleKey, tabKey);
  modeByKey[key] = mode;
  setValue(`sl-form-mode-${key}`, mode);
  const returnAction = getElement(`sl-return-action-${key}`);
  if (returnAction instanceof HTMLElement) returnAction.hidden = mode !== "verify";
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
  const comments = getElement(`sl-comments-wrap-${key}`);
  if (comments instanceof HTMLElement) comments.hidden = !visible;
}

function renderQcSnapshot(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const host = getElement(`sl-qc-cards-${key}`);
  if (!(host instanceof HTMLElement)) return;
  const snapshot = qcSnapshotForKey(key);
  const manualPunch = formBridge.toInt(getValue(`sl-form-qc-open-punch-${key}`)) ?? formBridge.toInt(snapshot.qc_open_punch_count) ?? 0;
  const cards = [
    { label: "تست", value: Number(snapshot.qc_test_count || 0) },
    { label: "بازرسی", value: Number(snapshot.qc_inspection_count || 0) },
    { label: "Punch باز", value: Number(manualPunch || 0) },
    { label: "NCR باز", value: Number(snapshot.qc_open_ncr_count || 0) },
  ];
  host.innerHTML = cards
    .map(
      (card) => `
        <article class="sl-qc-card">
          <span>${stateBridge.esc(card.label)}</span>
          <strong>${stateBridge.esc(String(card.value))}</strong>
        </article>
      `
    )
    .join("");
  const meta = getElement(`sl-qc-meta-${key}`);
  if (meta instanceof HTMLElement) {
    const snapshotAt = String(snapshot.qc_snapshot_at || "").trim();
    meta.textContent = snapshotAt ? `آخرین بروزرسانی QC: ${formatShamsiDateTime(snapshotAt)}` : "";
  }
}

function rerenderSection(moduleKey: string, tabKey: string, section: SectionKind, deps: SiteLogsUiDeps): void {
  const rows = collectSectionRows(moduleKey, tabKey, section);
  renderSectionRows(
    moduleKey,
    tabKey,
    section,
    rows.length ? rows : [{}],
    currentFormMode(moduleKey, tabKey),
    boardCapabilities(moduleKey, tabKey, deps)
  );
}

function rerenderAttachmentAwareSections(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): void {
  (["manpower", "equipment", "activity", "material", "issue", "report_attachment"] as SectionKind[]).forEach((section) => {
    rerenderSection(moduleKey, tabKey, section, deps);
  });
}

function updateActivityPickerUi(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const picker = getElement(`sl-activity-picker-${key}`);
  const list = getElement(`sl-activity-picker-list-${key}`);
  if (list instanceof HTMLDataListElement) {
    list.innerHTML = activityOptionDatalistOptions(key);
  }
  if (picker instanceof HTMLInputElement) {
    picker.placeholder = activityOptionsForKey(key).length
      ? "کد، عنوان، محل یا واحد فعالیت را بنویسید..."
      : "برای این قرارداد کاتالوگ فعالیتی تعریف نشده است";
  }
  document.querySelectorAll<HTMLDataListElement>("datalist[data-sl-activity-title-list]").forEach((item) => {
    if (String(item.dataset.slActivityTitleList || "") === key) {
      item.innerHTML = activityTitleDatalistOptions(key);
    }
  });
}

function rowFieldSnapshot(rowEl: HTMLElement): Record<string, unknown> {
  const row: Record<string, unknown> = {};
  rowEl.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("[data-sl-field]").forEach((fieldEl) => {
    const field = String(fieldEl.dataset.slField || "").trim();
    if (!field) return;
    row[field] = fieldEl.value;
  });
  return row;
}

function setRowFieldValue(rowEl: HTMLElement | null, field: string, value: unknown): void {
  if (!rowEl) return;
  const textValue = String(value ?? "");
  const fieldEl = rowEl.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(`[data-sl-field="${field}"]`);
  if (fieldEl) fieldEl.value = textValue;
  const visibleEl = rowEl.querySelector<HTMLInputElement>(`[data-sl-target-field="${field}"]`);
  if (visibleEl && visibleEl !== fieldEl) visibleEl.value = textValue;
}

function applyCatalogMatchSideEffects(
  rowEl: HTMLElement | null,
  catalogKey: string,
  targetField: string,
  match: Record<string, unknown>
): void {
  if (!rowEl) return;
  if (catalogKey === "role_catalog" && targetField === "role_label") {
    setRowFieldValue(rowEl, "role_code", match.code || "");
  }
  if (catalogKey === "equipment_catalog" && targetField === "equipment_label") {
    setRowFieldValue(rowEl, "equipment_code", match.code || "");
  }
  if (catalogKey === "material_catalog" && targetField === "title") {
    setRowFieldValue(rowEl, "material_code", match.code || "");
    if (String(match.unit || "").trim()) {
      setRowFieldValue(rowEl, "unit", match.unit || "");
    }
  }
}

function applyCatalogSelectValue(select: HTMLSelectElement): void {
  const catalogKey = String(select.dataset.slCatalog || "").trim();
  if (!catalogKey) return;
  const valueKey = String(select.dataset.slValueKey || "code").trim();
  const labelKey = String(select.dataset.slLabelKey || "label").trim();
  const targetField = String(select.dataset.slTargetField || select.dataset.slField || "").trim();
  const rowEl = select.closest("tr[data-sl-row-index], tr[data-sl-row-detail-for]") as HTMLElement | null;
  if (!String(select.value || "").trim()) {
    applyCatalogMatchSideEffects(rowEl, catalogKey, targetField, {});
    return;
  }
  const rows = optionRowsFromCatalog(catalogKey);
  const match = rows.find((row) => String(row[valueKey] ?? "").trim() === String(select.value || "").trim()) || null;
  if (match) {
    applyCatalogMatchSideEffects(rowEl, catalogKey, targetField, match);
  }
}

function applyCatalogTypeaheadValue(input: HTMLInputElement, commit = false): void {
  const catalogKey = String(input.dataset.slCatalog || "").trim();
  if (!catalogKey) return;
  const valueKey = String(input.dataset.slValueKey || "code").trim();
  const labelKey = String(input.dataset.slLabelKey || "label").trim();
  const targetField = String(input.dataset.slTargetField || input.dataset.slField || "").trim();
  const rows = optionRowsFromCatalog(catalogKey);
  const match = matchCatalogTypeaheadRow(rows, input.value, valueKey, labelKey, !commit);
  const rowEl = input.closest("tr[data-sl-row-index], tr[data-sl-row-detail-for]") as HTMLElement | null;
  const hiddenField = input.parentElement?.querySelector<HTMLInputElement>(`input[type="hidden"][data-sl-field="${targetField}"]`);

  if (!String(input.value || "").trim()) {
    if (hiddenField) hiddenField.value = "";
    return;
  }

  if (match) {
    const storedValue = String(match[valueKey] ?? "").trim();
    const label = catalogFieldLabel(match, valueKey, labelKey);
    if (hiddenField) {
      hiddenField.value = storedValue;
      input.value = label || storedValue;
    } else {
      input.value = storedValue;
    }
    input.title = label && label !== storedValue ? `${storedValue} - ${label}` : storedValue;
    applyCatalogMatchSideEffects(rowEl, catalogKey, targetField, match);
    return;
  }

  if (!commit) {
    if (hiddenField) hiddenField.value = "";
    applyCatalogMatchSideEffects(rowEl, catalogKey, targetField, {});
    return;
  }

  if (commit) {
    if (hiddenField) hiddenField.value = "";
    input.value = "";
    input.title = "مقدار باید از کاتالوگ انتخاب شود.";
    applyCatalogMatchSideEffects(rowEl, catalogKey, targetField, {});
  }
}

function applyActivityTitleTypeaheadValue(moduleKey: string, tabKey: string, input: HTMLInputElement, commit = false): boolean {
  const key = keyOf(moduleKey, tabKey);
  const rowEl = input.closest("tr[data-sl-row-index]") as HTMLElement | null;
  if (!rowEl) return false;
  const query = String(input.value || "").trim();
  if (!query) {
    setRowFieldValue(rowEl, "activity_code", "");
    setRowFieldValue(rowEl, "activity_title", "");
    setRowFieldValue(rowEl, "source_system", "MANUAL");
    setRowFieldValue(rowEl, "external_ref", "");
    setRowFieldValue(rowEl, "pms_mapping_id", "");
    setRowFieldValue(rowEl, "pms_template_code", "");
    setRowFieldValue(rowEl, "pms_template_title", "");
    setRowFieldValue(rowEl, "pms_template_version", "");
    setRowFieldValue(rowEl, "pms_step_code", "");
    setRowFieldValue(rowEl, "pms_step_title", "");
    setRowFieldValue(rowEl, "pms_step_weight_pct", "");
    return true;
  }

  const match = matchActivityOption(key, query, !commit);
  if (match) {
    const title = String(match.activity_title ?? match.activity_code ?? query).trim();
    const id = Number(match.id || 0);
    setRowFieldValue(rowEl, "activity_code", match.activity_code || "");
    setRowFieldValue(rowEl, "activity_title", title);
    setRowFieldValue(rowEl, "source_system", "CATALOG");
    setRowFieldValue(rowEl, "external_ref", id > 0 ? `site_log_activity_catalog:${id}` : "");
    setRowFieldValue(rowEl, "location", match.default_location || "");
    setRowFieldValue(rowEl, "unit", match.default_unit || "");
    setRowFieldValue(rowEl, "pms_mapping_id", Number(match.pms_mapping_id || 0) || "");
    setRowFieldValue(rowEl, "pms_template_code", match.pms_template_code || "");
    setRowFieldValue(rowEl, "pms_template_title", match.pms_template_title || "");
    setRowFieldValue(rowEl, "pms_template_version", Number(match.pms_snapshot_version || match.pms_template_version || 0) || "");
    setRowFieldValue(rowEl, "pms_step_code", "");
    setRowFieldValue(rowEl, "pms_step_title", "");
    setRowFieldValue(rowEl, "pms_step_weight_pct", "");
    input.value = title;
    return true;
  }

  if (!commit) {
    setRowFieldValue(rowEl, "activity_code", "");
    setRowFieldValue(rowEl, "source_system", "");
    setRowFieldValue(rowEl, "external_ref", "");
    setRowFieldValue(rowEl, "pms_mapping_id", "");
    setRowFieldValue(rowEl, "pms_template_code", "");
    setRowFieldValue(rowEl, "pms_template_title", "");
    setRowFieldValue(rowEl, "pms_template_version", "");
    setRowFieldValue(rowEl, "pms_step_code", "");
    setRowFieldValue(rowEl, "pms_step_title", "");
    setRowFieldValue(rowEl, "pms_step_weight_pct", "");
    return false;
  }

  if (commit) {
    setRowFieldValue(rowEl, "activity_code", "");
    setRowFieldValue(rowEl, "activity_title", "");
    setRowFieldValue(rowEl, "source_system", "");
    setRowFieldValue(rowEl, "external_ref", "");
    setRowFieldValue(rowEl, "pms_mapping_id", "");
    setRowFieldValue(rowEl, "pms_template_code", "");
    setRowFieldValue(rowEl, "pms_template_title", "");
    setRowFieldValue(rowEl, "pms_template_version", "");
    setRowFieldValue(rowEl, "pms_step_code", "");
    setRowFieldValue(rowEl, "pms_step_title", "");
    setRowFieldValue(rowEl, "pms_step_weight_pct", "");
    input.value = "";
    input.title = "فعالیت باید از کاتالوگ انتخاب شود.";
    return true;
  }

  return false;
}

function matchPmsStep(key: string, row: Record<string, unknown>, query: unknown, exactOnly = false): Record<string, unknown> | null {
  const q = searchNeedle(query);
  if (!q) return null;
  const ranked = pmsStepsForActivityRow(key, row)
    .map((step) => {
      const values = [pmsStepDisplayValue(step), step.step_code, step.step_title, step.weight_pct];
      let rank = 999;
      values.forEach((item) => {
        const candidate = searchNeedle(item);
        if (!candidate) return;
        if (candidate === q) rank = Math.min(rank, 0);
        else if (!exactOnly && candidate.startsWith(q)) rank = Math.min(rank, 1);
        else if (!exactOnly && candidate.includes(q)) rank = Math.min(rank, 2);
      });
      return { step, rank };
    })
    .filter((item) => item.rank < 999)
    .sort((a, b) => a.rank - b.rank);
  return ranked[0]?.step || null;
}

function applyPmsStepTypeaheadValue(moduleKey: string, tabKey: string, input: HTMLInputElement, commit = false): void {
  const key = keyOf(moduleKey, tabKey);
  const rowEl = input.closest("tr[data-sl-row-index]") as HTMLElement | null;
  if (!rowEl) return;
  const hiddenField = input.parentElement?.querySelector<HTMLInputElement>('input[type="hidden"][data-sl-field="pms_step_code"]');
  const query = String(input.value || "").trim();
  if (!query) {
    if (hiddenField) hiddenField.value = "";
    setRowFieldValue(rowEl, "pms_step_title", "");
    setRowFieldValue(rowEl, "pms_step_weight_pct", "");
    return;
  }
  const match = matchPmsStep(key, rowFieldSnapshot(rowEl), query, !commit);
  if (match) {
    const code = String(match.step_code ?? "").trim();
    if (hiddenField) hiddenField.value = code;
    input.value = pmsStepDisplayValue(match);
    setRowFieldValue(rowEl, "pms_step_title", match.step_title || "");
    setRowFieldValue(rowEl, "pms_step_weight_pct", match.weight_pct || "");
  } else if (commit && hiddenField) {
    hiddenField.value = upper(query);
    setRowFieldValue(rowEl, "pms_step_title", "");
    setRowFieldValue(rowEl, "pms_step_weight_pct", "");
  }
}

function syncCatalogSelectValue(id: string, catalogKey: string, value: unknown, label: unknown, placeholder: string): void {
  const el = getElement(id);
  if (!(el instanceof HTMLSelectElement)) return;
  const current = upper(value);
  el.innerHTML = catalogCodeOptions(catalogKey, current, placeholder);
  if (current && !Array.from(el.options).some((option) => option.value === current)) {
    const option = document.createElement("option");
    option.value = current;
    option.textContent = `${String(label || current)} (مقدار قبلی)`;
    option.selected = true;
    option.dataset.legacyOption = "1";
    el.insertBefore(option, el.options[1] || null);
  }
  el.value = current;
}

function resetForm(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): void {
  const key = keyOf(moduleKey, tabKey);
  const capabilities = boardCapabilities(moduleKey, tabKey, deps);
  setFormMode(moduleKey, tabKey, "create");
  setDrawerTitle(moduleKey, tabKey, "گزارش کارگاهی جدید");
  setValue(`sl-form-id-${key}`, "");
  setValue(`sl-form-log-type-${key}`, formBridge.defaultLogType(moduleKey, tabKey));
  setValue(`sl-form-project-${key}`, "");
  setValue(`sl-form-organization-${key}`, "");
  setValue(`sl-form-contract-number-${key}`, "");
  setValue(`sl-form-contract-block-${key}`, "");
  syncOrganizationContractSubjectOptions(moduleKey, tabKey, {});
  setValue(`sl-form-log-date-${key}`, new Date().toISOString().slice(0, 10));
  setValue(`sl-form-work-status-${key}`, "ACTIVE");
  syncCatalogSelectValue(`sl-form-shift-${key}`, "shift_catalog", "", "", "شیفت");
  syncCatalogSelectValue(`sl-form-weather-${key}`, "weather_catalog", "CLEAR", "صاف", "وضعیت جوی");
  setValue(`sl-form-current-work-${key}`, "");
  setValue(`sl-form-next-plan-${key}`, "");
  setValue(`sl-form-qc-open-punch-${key}`, "");
  setValue(`sl-form-qc-note-${key}`, "");
  setValue(`sl-form-status-${key}`, "DRAFT");
  setValue(`sl-comment-input-${key}`, "");
  attachmentOptionsByKey[key] = [];
  activityOptionsByKey[key] = [];
  qcSnapshotByKey[key] = {};
  renderSectionRows(moduleKey, tabKey, "manpower", [{}], "create", capabilities);
  renderSectionRows(moduleKey, tabKey, "equipment", [{}], "create", capabilities);
  renderSectionRows(moduleKey, tabKey, "activity", [{}], "create", capabilities);
  renderSectionRows(moduleKey, tabKey, "material", [{}], "create", capabilities);
  renderSectionRows(moduleKey, tabKey, "issue", [{}], "create", capabilities);
  renderSectionRows(moduleKey, tabKey, "report_attachment", [{}], "create", capabilities);
  updateActivityPickerUi(moduleKey, tabKey);
  renderQcSnapshot(moduleKey, tabKey);
  setExistingSectionsVisible(moduleKey, tabKey, false);
  showFormMode(moduleKey, tabKey);
  ensureShamsiInputs(moduleKey, tabKey);
  setDrawerDirty(moduleKey, tabKey, false);
}

function fillFormFromLog(moduleKey: string, tabKey: string, row: Record<string, unknown>, mode: FormMode, deps: SiteLogsUiDeps): void {
  const key = keyOf(moduleKey, tabKey);
  const capabilities = boardCapabilities(moduleKey, tabKey, deps);
  const statusCode = upper(row.status_code);
  const forceMode: FormMode = mode === "edit" && !["DRAFT", "RETURNED"].includes(statusCode) ? "detail" : mode;
  attachmentOptionsByKey[key] = [];
  setFormMode(moduleKey, tabKey, forceMode);
  setValue(`sl-form-id-${key}`, Number(row.id || 0));
  setValue(`sl-form-log-type-${key}`, row.log_type || "DAILY");
  setValue(`sl-form-project-${key}`, row.project_code || "");
  setValue(`sl-form-organization-${key}`, row.organization_id || "");
  syncOrganizationContractSubjectOptions(
    moduleKey,
    tabKey,
    {
      organizationContractId: row.organization_contract_id || "",
      contractNumber: row.contract_number || "",
      contractSubject: row.contract_subject || "",
      contractBlock: row.contract_block || "",
    }
  );
  syncSelectedContractSnapshot(moduleKey, tabKey);
  setValue(`sl-form-log-date-${key}`, String(row.log_date || "").slice(0, 10));
  setValue(`sl-form-work-status-${key}`, row.work_status || "ACTIVE");
  syncCatalogSelectValue(`sl-form-shift-${key}`, "shift_catalog", row.shift || "", row.shift_label || row.shift || "", "شیفت");
  syncCatalogSelectValue(`sl-form-weather-${key}`, "weather_catalog", row.weather || "", row.weather_label || row.weather || "", "وضعیت جوی");
  setValue(`sl-form-current-work-${key}`, row.current_work_summary || row.summary || "");
  setValue(`sl-form-next-plan-${key}`, row.next_plan_summary || "");
  setValue(`sl-form-qc-open-punch-${key}`, row.qc_open_punch_count ?? "");
  setValue(`sl-form-qc-note-${key}`, row.qc_summary_note || "");
  setValue(`sl-form-status-${key}`, row.status_code || "DRAFT");
  renderSectionRows(moduleKey, tabKey, "manpower", asArray(row.manpower_rows), forceMode, capabilities);
  renderSectionRows(moduleKey, tabKey, "equipment", asArray(row.equipment_rows), forceMode, capabilities);
  renderSectionRows(moduleKey, tabKey, "activity", asArray(row.activity_rows), forceMode, capabilities);
  renderSectionRows(moduleKey, tabKey, "material", asArray(row.material_rows), forceMode, capabilities);
  renderSectionRows(moduleKey, tabKey, "issue", asArray(row.issue_rows), forceMode, capabilities);
  renderSectionRows(moduleKey, tabKey, "report_attachment", asArray(row.attachment_rows), forceMode, capabilities);
  qcSnapshotByKey[key] = {
    qc_test_count: row.qc_test_count,
    qc_inspection_count: row.qc_inspection_count,
    qc_open_ncr_count: row.qc_open_ncr_count,
    qc_open_punch_count: row.qc_open_punch_count,
    qc_snapshot_at: row.qc_snapshot_at,
  };
  renderQcSnapshot(moduleKey, tabKey);
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
  note: string,
  claimedLabel = "اعلامی پیمانکار",
  verifiedLabel = "تایید مشاور"
): string {
  return `
    <article class="sl-report-metric">
      <div class="sl-report-metric-head">
        <span class="material-icons-round">${stateBridge.esc(icon)}</span>
        <strong>${stateBridge.esc(title)}</strong>
      </div>
      <div class="sl-report-metric-values">
        <div class="sl-report-metric-side is-claimed">
          <span>${stateBridge.esc(claimedLabel)}</span>
          <strong>${stateBridge.esc(claimedValue)}</strong>
        </div>
        <div class="sl-report-metric-side is-verified">
          <span>${stateBridge.esc(verifiedLabel)}</span>
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

function summaryBlockText(row: Record<string, unknown>, key: "current_work_summary" | "next_plan_summary"): string {
  const direct = String(row[key] ?? "").trim();
  if (direct) return direct;
  if (key === "current_work_summary") return String(row.summary ?? "").trim();
  return "";
}

function renderNarrativeSummaryBoxes(row: Record<string, unknown>, printable = false): string {
  const currentText = summaryBlockText(row, "current_work_summary");
  const nextPlanText = summaryBlockText(row, "next_plan_summary");
  const emptyText = printable ? "—" : "ثبت نشده";
  return `
    <div class="sl-report-summary-grid">
      <article class="sl-report-summary-box">
        <div class="sl-report-summary-box-title">کارهای در حال انجام</div>
        <div class="sl-report-summary-box-text">${stateBridge.esc(currentText || emptyText)}</div>
      </article>
      <article class="sl-report-summary-box">
        <div class="sl-report-summary-box-title">برنامه بعدی</div>
        <div class="sl-report-summary-box-text">${stateBridge.esc(nextPlanText || emptyText)}</div>
      </article>
    </div>
  `;
}

function buildPrintMetricsHtml(row: Record<string, unknown>): string {
  const manpowerRows = asArray(row.manpower_rows);
  const equipmentRows = asArray(row.equipment_rows);
  const activityRows = asArray(row.activity_rows);
  const blockedActivities = activityRows.filter((item) => String(item.stop_reason ?? "").trim()).length;
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
        <span>تعداد تجهیزات</span>
        <strong>${escHtml(formatNumber(sumRows(equipmentRows, "claimed_count"), 0, " دستگاه"))}</strong>
        <em>تاییدی: ${escHtml(formatNumber(sumRows(equipmentRows, "verified_count"), 0, " دستگاه"))}</em>
      </div>
      <div class="summary-card">
        <span>ساعات تجهیزات</span>
        <strong>${escHtml(formatNumber(sumRows(equipmentRows, "claimed_hours"), 1, " ساعت"))}</strong>
        <em>تاییدی: ${escHtml(formatNumber(sumRows(equipmentRows, "verified_hours"), 1, " ساعت"))}</em>
      </div>
      <div class="summary-card">
        <span>فعالیت‌های اجرایی</span>
        <strong>${escHtml(formatNumber(activityRows.length || 0, 0, " ردیف"))}</strong>
        <em>متوقف: ${escHtml(formatNumber(blockedActivities, 0, " ردیف"))}</em>
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

function printRows(rows: Record<string, unknown>[], maxRows: number): Record<string, unknown>[] {
  return rows.slice(0, Math.max(0, maxRows));
}

function printOmittedRow(totalRows: number, maxRows: number, colSpan: number): string {
  const omitted = totalRows - maxRows;
  if (omitted <= 0) return "";
  return `<tr class="omitted-row"><td colspan="${colSpan}">ادامه ${escHtml(formatNumber(omitted, 0))} ردیف دیگر در سامانه ثبت شده است.</td></tr>`;
}

function buildSiteLogPrintInfoTableHtml(row: Record<string, unknown>): string {
  return `
    <table class="info-table">
      <tbody>
        <tr>
          <td><span>شماره گزارش</span><strong>${escHtml(textValue(row.log_no))}</strong></td>
          <td><span>تاریخ گزارش</span><strong>${escHtml(formatShamsiDate(row.log_date))}</strong></td>
          <td><span>نوع گزارش</span><strong>${escHtml(logTypeLabelFa(row.log_type))}</strong></td>
          <td><span>وضعیت</span><strong>${escHtml(statusLabelFa(row.status_code))}</strong></td>
          <td><span>وضعیت کارگاه</span><strong>${escHtml(workStatusLabelFa(row.work_status))}</strong></td>
          <td><span>شیفت</span><strong>${escHtml(textValue(row.shift_label || row.shift))}</strong></td>
        </tr>
        <tr>
          <td><span>پروژه</span><strong>${escHtml(projectName(row.project_code))}</strong></td>
          <td><span>سازمان</span><strong>${escHtml(textValue(row.organization_name))}</strong></td>
          <td><span>موضوع قرارداد</span><strong>${escHtml(textValue(row.contract_subject))}</strong></td>
          <td><span>شماره قرارداد</span><strong>${escHtml(textValue(row.contract_number))}</strong></td>
          <td><span>بلوک قرارداد</span><strong>${escHtml(textValue(row.contract_block))}</strong></td>
          <td><span>وضعیت جوی</span><strong>${escHtml(textValue(row.weather_label || row.weather))}</strong></td>
        </tr>
      </tbody>
    </table>
  `;
}

function buildSiteLogPrintHtml(row: Record<string, unknown>, mode: "summary" | "full" = "full"): string {
  const projectTitle = projectName(row.project_code);
  const organizationTitle = textValue(row.organization_name);
  const manpowerRows = asArray(row.manpower_rows);
  const equipmentRows = asArray(row.equipment_rows);
  const activityRows = asArray(row.activity_rows);
  const materialRows = asArray(row.material_rows);
  const issueRows = asArray(row.issue_rows);
  const printTime = formatShamsiDateTime(new Date().toISOString());
  const compactActivityRows = printRows(activityRows, 4);
  const compactManpowerRows = printRows(manpowerRows, 3);
  const compactEquipmentRows = printRows(equipmentRows, 3);
  const compactMaterialRows = printRows(materialRows, 2);
  const compactIssueRows = printRows(issueRows, 3);

  const manpowerTable = buildPrintTableHtml(
    "نفرات",
    "اعلام پیمانکار و تایید مشاور",
    ["#", "کد", "عنوان", "واحد کاری", "تعداد اعلامی", "ساعت اعلامی", "تعداد تاییدی", "ساعت تاییدی", "توضیحات"],
    compactManpowerRows
      .map(
        (item, index) => `
          <tr>
            <td>${index + 1}</td>
            <td>${escHtml(textValue(item.role_code))}</td>
            <td>${escHtml(textValue(item.role_label))}</td>
            <td>${escHtml(textValue(item.work_section_label))}</td>
            <td>${escHtml(formatNumber(toNumber(item.claimed_count), 0))}</td>
            <td>${escHtml(formatNumber(toNumber(item.claimed_hours), 1))}</td>
            <td>${escHtml(formatNumber(toNumber(item.verified_count), 0))}</td>
            <td>${escHtml(formatNumber(toNumber(item.verified_hours), 1))}</td>
            <td>${escHtml(textValue(item.note))}</td>
          </tr>
        `
      )
      .join("") + printOmittedRow(manpowerRows.length, compactManpowerRows.length, 9),
    "ردیف نفرات برای این گزارش ثبت نشده است."
  );

  const equipmentTable = buildPrintTableHtml(
    "تجهیزات",
    "تعداد، وضعیت و ساعات تجهیز",
    ["#", "کد", "عنوان", "محل کارکرد", "تعداد اعلامی", "وضعیت اعلامی", "ساعت اعلامی", "تعداد تاییدی", "وضعیت تاییدی", "ساعت تاییدی", "توضیحات"],
    compactEquipmentRows
      .map(
        (item, index) => `
          <tr>
            <td>${index + 1}</td>
            <td>${escHtml(textValue(item.equipment_code))}</td>
            <td>${escHtml(textValue(item.equipment_label))}</td>
            <td>${escHtml(textValue(item.work_location))}</td>
            <td>${escHtml(formatNumber(toNumber(item.claimed_count), 0))}</td>
            <td>${escHtml(textValue(item.claimed_status))}</td>
            <td>${escHtml(formatNumber(toNumber(item.claimed_hours), 1))}</td>
            <td>${escHtml(formatNumber(toNumber(item.verified_count), 0))}</td>
            <td>${escHtml(textValue(item.verified_status))}</td>
            <td>${escHtml(formatNumber(toNumber(item.verified_hours), 1))}</td>
            <td>${escHtml(textValue(item.note))}</td>
          </tr>
        `
      )
      .join("") + printOmittedRow(equipmentRows.length, compactEquipmentRows.length, 11),
    "ردیف تجهیز برای این گزارش ثبت نشده است."
  );

  const activityTable = buildPrintTableHtml(
    "فعالیت‌های اجرایی",
    "فعالیت‌های روز و مقدار تجمیعی",
    ["#", "کد", "عنوان فعالیت", "مرحله PMS", "محل", "واحد", "نفرات", "امروز", "تجمیعی", "وضعیت", "علت توقف", "توضیح"],
    compactActivityRows
      .map(
        (item, index) => `
          <tr>
            <td>${index + 1}</td>
            <td>${escHtml(textValue(item.activity_code))}</td>
            <td>${escHtml(textValue(item.activity_title))}</td>
            <td>${escHtml([textValue(item.pms_step_title), item.pms_step_weight_pct ? formatNumber(toNumber(item.pms_step_weight_pct), 0, "%") : ""].filter(Boolean).join(" - ") || "-")}</td>
            <td>${escHtml(textValue(item.location))}</td>
            <td>${escHtml(textValue(item.unit))}</td>
            <td>${escHtml(formatNumber(toNumber(item.personnel_count), 0))}</td>
            <td>${escHtml(formatNumber(toNumber(item.today_quantity), 2))}</td>
            <td>${escHtml(formatNumber(toNumber(item.cumulative_quantity), 2))}</td>
            <td>${escHtml(textValue(item.activity_status))}</td>
            <td>${escHtml(textValue(item.stop_reason))}</td>
            <td>${escHtml(textValue(item.note))}</td>
          </tr>
        `
      )
      .join("") + printOmittedRow(activityRows.length, compactActivityRows.length, 12),
    "ردیف فعالیت برای این گزارش ثبت نشده است."
  );

  const materialTable = buildPrintTableHtml(
    "مصالح",
    "ورودی، مصرف و مقدار تجمیعی",
    ["#", "کد", "عنوان", "محل مصرف", "واحد", "ورودی", "مصرف", "تجمیعی", "توضیح"],
    compactMaterialRows
      .map(
        (item, index) => `
          <tr>
            <td>${index + 1}</td>
            <td>${escHtml(textValue(item.material_code))}</td>
            <td>${escHtml(textValue(item.title))}</td>
            <td>${escHtml(textValue(item.consumption_location))}</td>
            <td>${escHtml(textValue(item.unit))}</td>
            <td>${escHtml(formatNumber(toNumber(item.incoming_quantity), 2))}</td>
            <td>${escHtml(formatNumber(toNumber(item.consumed_quantity), 2))}</td>
            <td>${escHtml(formatNumber(toNumber(item.cumulative_quantity), 2))}</td>
            <td>${escHtml(textValue(item.note))}</td>
          </tr>
        `
      )
      .join("") + printOmittedRow(materialRows.length, compactMaterialRows.length, 9),
    "ردیف مصالح برای این گزارش ثبت نشده است."
  );

  const issueTable = buildPrintTableHtml(
    "موانع / ریسک‌ها",
    "مشکلات، کمبودها و پیگیری‌ها",
    ["#", "نوع", "شرح", "مسئول", "موعد", "وضعیت", "توضیح"],
    compactIssueRows
      .map(
        (item, index) => `
          <tr>
            <td>${index + 1}</td>
            <td>${escHtml(textValue(item.issue_type_label || item.issue_type))}</td>
            <td>${escHtml(textValue(item.description))}</td>
            <td>${escHtml(textValue(item.responsible_party))}</td>
            <td>${escHtml(formatShamsiDate(item.due_date))}</td>
            <td>${escHtml(textValue(item.status))}</td>
            <td>${escHtml(textValue(item.note))}</td>
          </tr>
        `
      )
      .join("") + printOmittedRow(issueRows.length, compactIssueRows.length, 7),
    "موردی برای موانع / ریسک‌ها ثبت نشده است."
  );

  const summarySection = `
    <section class="print-section print-summary-section">
      <div class="print-section-head">
        <h3>خلاصه مدیریت</h3>
        <p>کارهای روز و برنامه بعدی</p>
      </div>
      ${renderNarrativeSummaryBoxes(row, true)}
    </section>
  `;

  const qcSection = `
    <section class="print-section qc-print-section">
      <div class="print-section-head">
        <h3>کنترل کیفیت</h3>
        <p>خلاصه تست‌ها، بازرسی‌ها و موارد اصلاحی</p>
      </div>
      <section class="summary-grid">
        <div class="summary-card"><span>تست</span><strong>${escHtml(String(Number(row.qc_test_count || 0)))}</strong></div>
        <div class="summary-card"><span>بازرسی</span><strong>${escHtml(String(Number(row.qc_inspection_count || 0)))}</strong></div>
        <div class="summary-card"><span>موارد پانچ باز</span><strong>${escHtml(String(Number(row.qc_open_punch_count || 0)))}</strong></div>
        <div class="summary-card"><span>عدم انطباق باز</span><strong>${escHtml(String(Number(row.qc_open_ncr_count || 0)))}</strong></div>
      </section>
      <section class="section-box">
        <div class="section-title">شرح کیفیت / اقدام اصلاحی</div>
        <div class="section-content">${escHtml(textValue(row.qc_summary_note))}</div>
      </section>
    </section>
  `;

  return `
<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>چاپ گزارش کارگاهی - ${escHtml(textValue(row.log_no))}</title>
  <style>
    @page { size: A4; margin: 6mm; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Tahoma, "Segoe UI", Arial, sans-serif; font-size: 8.4px; color: #0f172a; background: #ffffff; }
    .sheet {
      position: relative;
      max-height: 282mm;
      overflow: hidden;
      border-top: 3px solid #1d4ed8;
      padding: 3px 0 7mm;
    }
    .letterhead {
      display: grid;
      grid-template-columns: 34px 1fr 120px;
      gap: 5px;
      align-items: center;
      border: 1px solid #c7d2fe;
      border-radius: 9px;
      background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
      padding: 4px 6px;
      margin-bottom: 4px;
    }
    .brand-mark {
      width: 28px;
      height: 28px;
      border-radius: 8px;
      border: 1px solid #1d4ed8;
      color: #1d4ed8;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 7.4px;
      font-weight: 900;
      background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
    }
    .letterhead-title { text-align: center; }
    .letterhead-title h1 {
      display: inline-block;
      margin: 0;
      padding: 2px 18px;
      border-radius: 999px;
      background: #dbeafe;
      color: #0b3a7a;
      font-size: 14px;
      font-weight: 900;
      line-height: 1.08;
      box-shadow: inset 0 0 0 1px #bfdbfe;
    }
    .letterhead-title p { margin: 1px 0 0; font-size: 7.3px; color: #475569; }
    .letterhead-meta {
      border-right: 1px solid #cbd5e1;
      padding-right: 5px;
      font-size: 7.2px;
      line-height: 1.28;
    }
    .info-table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 4px;
    }
    .info-table td {
      border: 1px solid #c7d2fe;
      border-radius: 8px;
      padding: 2px 4px;
      vertical-align: top;
      text-align: right;
    }
    .info-table span, .summary-card span { display: block; font-size: 6.9px; color: #475569; margin-bottom: 1px; }
    .info-table strong, .summary-card strong { display: block; font-size: 7.8px; line-height: 1.18; }
    .summary-card {
      border: 1px solid #d2dcf5;
      border-radius: 8px;
      background: #f8fbff;
      padding: 3px 4px;
      min-height: 0;
    }
    .summary-card em { display: block; margin-top: 1px; font-size: 7.2px; color: #166534; font-style: normal; }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 3px;
      margin-bottom: 4px;
    }
    .sl-report-summary-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 3px;
    }
    .sl-report-summary-box {
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      background: #f8fbff;
      padding: 2px 5px;
      min-height: 0;
      max-height: 38px;
      overflow: hidden;
    }
    .sl-report-summary-box-title {
      font-size: 7.3px;
      font-weight: 800;
      color: #1d4ed8;
      margin-bottom: 2px;
    }
    .sl-report-summary-box-text {
      font-size: 7.7px;
      line-height: 1.24;
      white-space: normal;
      word-break: break-word;
    }
    .print-summary-section .sl-report-summary-grid {
      border: 1px solid #c8d7f1;
      border-top: 0;
      border-radius: 0 0 8px 8px;
      padding: 3px;
      margin-bottom: 0;
    }
    .section-box {
      border: 1px solid #c8d7f1;
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 4px;
    }
    .section-title {
      background: #edf4ff;
      padding: 2px 7px;
      font-weight: 800;
      font-size: 9.2px;
      color: #0b3a7a;
      border-bottom: 1px solid #c8d7f1;
    }
    .section-content {
      padding: 3px 5px;
      line-height: 1.3;
      font-size: 7.7px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .print-section { margin-bottom: 4px; break-inside: avoid; }
    .print-section-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      background: #edf4ff;
      border: 1px solid #c8d7f1;
      border-bottom: 0;
      border-radius: 8px 8px 0 0;
      padding: 2px 5px;
    }
    .print-section-head h3 { margin: 0; font-size: 9.6px; font-weight: 900; color: #0b3a7a; }
    .print-section-head p { margin: 0; font-size: 6.9px; color: #475569; }
    table { width: 100%; border-collapse: collapse; font-size: 7.25px; }
    thead { display: table-header-group; }
    tr { page-break-inside: avoid; }
    th, td { border: 1px solid #cfd9ea; padding: 1.4px 2.4px; vertical-align: top; text-align: right; line-height: 1.13; }
    thead th { background: #f0f6ff; font-weight: 900; color: #0b3a7a; }
    .empty-row, .omitted-row td { text-align: center; color: #64748b; padding: 3px; }
    .two-column-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 5px;
      align-items: start;
      margin-bottom: 4px;
    }
    .two-column-grid .qc-print-section .summary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 3px;
    }
    .qc-print-section .section-box { margin-bottom: 0; }
    .qc-print-section .section-content {
      max-height: 24px;
      overflow: hidden;
    }
    .signature-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 4px;
      margin-top: 3px;
    }
    .signature-card {
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      min-height: 42px;
      padding: 3px 5px;
      break-inside: avoid;
    }
    .signature-card h4 { margin: 0 0 1px; font-size: 7.8px; }
    .signature-card .name { font-weight: 700; min-height: 9px; line-height: 1.15; font-size: 7.4px; }
    .signature-card .date { color: #475569; margin-top: 1px; font-size: 6.5px; }
    .signature-card .line { margin-top: 5px; border-top: 1px dashed #64748b; padding-top: 1px; font-size: 6.4px; color: #64748b; }
    .print-footer {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 6.9px;
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
      <div class="brand-mark">لوگو</div>
      <div class="letterhead-title">
        <h1>گزارش کارگاهی</h1>
        <p>فرم فشرده روزانه برای بایگانی، بررسی و امضا</p>
      </div>
      <div class="letterhead-meta">
        <div><strong>شماره گزارش:</strong> ${escHtml(textValue(row.log_no))}</div>
        <div><strong>تاریخ گزارش:</strong> ${escHtml(formatShamsiDate(row.log_date))}</div>
        <div><strong>پروژه:</strong> ${escHtml(projectTitle)}</div>
        <div><strong>سازمان:</strong> ${escHtml(organizationTitle)}</div>
        <div><strong>وضعیت:</strong> ${escHtml(statusLabelFa(row.status_code))}</div>
        <div><strong>وضعیت کارگاه:</strong> ${escHtml(workStatusLabelFa(row.work_status))}</div>
      </div>
    </header>

    ${buildSiteLogPrintInfoTableHtml(row)}

    ${buildPrintMetricsHtml(row)}

    ${summarySection}

    ${activityTable}
    ${mode === "full" ? `<div class="two-column-grid">${manpowerTable}${equipmentTable}</div>` : ""}
    <div class="two-column-grid">${materialTable}${qcSection}</div>
    ${issueTable}

    <section class="print-section">
      <div class="print-section-head">
        <h3>نظرات و تاییدات</h3>
        <p>جای امضا برای نسخه بایگانی</p>
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
    <span>گزارش کارگاهی</span>
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

function triggerBlobDownload(blob: Blob, fileName: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName || "site-log.pdf";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
}

async function downloadDetailPdf(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps, actionEl?: HTMLElement): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const row = detailRowByKey[key];
  const id = Number(row?.id || 0);
  if (id <= 0) {
    deps.showToast("اطلاعات گزارش برای دانلود PDF در دسترس نیست.", "error");
    return;
  }
  const button = actionEl instanceof HTMLButtonElement ? actionEl : null;
  if (button) button.disabled = true;
  try {
    const result = await dataBridge.downloadPdf(id, { fetch: deps.fetch });
    triggerBlobDownload(result.blob, result.fileName || `${textValue(row?.log_no, `site-log-${id}`)}.pdf`);
    deps.showToast("فایل PDF گزارش آماده دانلود شد.", "success");
  } catch (error) {
    deps.showToast(error instanceof Error && error.message ? error.message : "دانلود PDF گزارش ناموفق بود.", "error");
  } finally {
    if (button) button.disabled = false;
  }
}

function siteLogPreviewUnsupportedMessage(): string {
  return "پیش‌نمایش فقط برای فایل‌های PDF و تصویری پشتیبانی می‌شود. برای این فایل از دانلود استفاده کنید.";
}

function siteLogPreviewType(contentType: string, fileName: string): "pdf" | "image" | "" {
  const type = String(contentType || "").split(";", 1)[0].trim().toLowerCase();
  if (type === "application/pdf" || type === "application/x-pdf") return "pdf";
  if (type.startsWith("image/")) return "image";
  const name = String(fileName || "").toLowerCase();
  if (name.endsWith(".pdf")) return "pdf";
  if (/\.(png|jpe?g|gif|webp|bmp)$/.test(name)) return "image";
  return "";
}

function closeSiteLogAttachmentPreview(): void {
  const modal = document.getElementById("slPreviewModal");
  const body = document.getElementById("slPreviewBody");
  const download = document.getElementById("slPreviewDownload") as HTMLAnchorElement | null;
  if (modal) {
    modal.style.display = "none";
    modal.setAttribute("aria-hidden", "true");
  }
  if (body) body.innerHTML = "";
  if (download) {
    download.removeAttribute("href");
    download.removeAttribute("download");
  }
  if (siteLogAttachmentPreviewObjectUrl) {
    window.URL.revokeObjectURL(siteLogAttachmentPreviewObjectUrl);
    siteLogAttachmentPreviewObjectUrl = "";
  }
}

function ensureSiteLogAttachmentPreviewModal(): HTMLElement {
  const existing = document.getElementById("slPreviewModal");
  if (existing instanceof HTMLElement) return existing;
  const modal = document.createElement("div");
  modal.id = "slPreviewModal";
  modal.className = "am-modal-overlay sl-preview-modal";
  modal.setAttribute("aria-hidden", "true");
  modal.innerHTML = `
    <div class="am-modal-box sl-preview-box" role="dialog" aria-modal="true" aria-labelledby="slPreviewTitle">
      <div class="sl-preview-header">
        <h3 id="slPreviewTitle">پیش‌نمایش فایل</h3>
        <button type="button" class="btn-archive-icon" data-sl-preview-close aria-label="بستن پیش‌نمایش">
          <span class="material-icons-round">close</span>
        </button>
      </div>
      <div id="slPreviewBody" class="sl-preview-body"></div>
      <div class="sl-preview-footer">
        <a id="slPreviewDownload" class="btn-archive-icon" href="#" download>
          <span class="material-icons-round">download</span>
          دانلود
        </a>
        <button type="button" class="btn-archive-primary" data-sl-preview-close>بستن</button>
      </div>
    </div>
  `;
  modal.addEventListener("click", (event) => {
    if (event.target === modal || (event.target as HTMLElement | null)?.closest?.("[data-sl-preview-close]")) {
      closeSiteLogAttachmentPreview();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal.getAttribute("aria-hidden") === "false") {
      closeSiteLogAttachmentPreview();
    }
  });
  document.body.appendChild(modal);
  return modal;
}

async function previewSiteLogAttachment(attachmentId: number, fallbackName: string, deps: SiteLogsUiDeps): Promise<void> {
  const id = Math.max(0, Number(attachmentId) || 0);
  if (id <= 0) {
    deps.showToast("فایل برای پیش‌نمایش در دسترس نیست.", "error");
    return;
  }
  try {
    const result = await dataBridge.previewAttachment(id, { fetch: deps.fetch });
    const fileName = String(result.fileName || fallbackName || `attachment-${id}`).trim() || `attachment-${id}`;
    const previewType = siteLogPreviewType(result.contentType, fileName);
    if (!previewType) {
      deps.showToast(siteLogPreviewUnsupportedMessage(), "warning");
      return;
    }
    closeSiteLogAttachmentPreview();
    const typedBlob = result.blob.type
      ? result.blob
      : new Blob([result.blob], { type: previewType === "pdf" ? "application/pdf" : result.contentType || "image/*" });
    const url = window.URL.createObjectURL(typedBlob);
    siteLogAttachmentPreviewObjectUrl = url;

    const modal = ensureSiteLogAttachmentPreviewModal();
    const title = document.getElementById("slPreviewTitle");
    const body = document.getElementById("slPreviewBody");
    const download = document.getElementById("slPreviewDownload") as HTMLAnchorElement | null;
    if (title) title.textContent = `پیش‌نمایش: ${fileName}`;
    if (download) {
      download.href = url;
      download.download = fileName;
    }
    if (body) {
      body.innerHTML =
        previewType === "pdf"
          ? `<iframe class="sl-preview-frame" src="${url}" title="${stateBridge.esc(fileName)}"></iframe>`
          : `<img class="sl-preview-image" src="${url}" alt="${stateBridge.esc(fileName)}">`;
    }
    modal.style.display = "flex";
    modal.setAttribute("aria-hidden", "false");
  } catch (error) {
    deps.showToast(error instanceof Error && error.message ? error.message : siteLogPreviewUnsupportedMessage(), "warning");
  }
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
            <th rowspan="2">واحد / بخش کاری</th>
            <th colspan="2">اعلامی پیمانکار</th>
            <th colspan="2">تایید مشاور</th>
            <th rowspan="2">فایل‌ها</th>
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
                  <td>${stateBridge.esc(textValue(row.work_section_label))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.claimed_count), 0))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.claimed_hours), 1))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.verified_count), 0))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.verified_hours), 1))}</td>
                  <td>${rowAttachmentFilesDetailHtml(row)}</td>
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
    return renderSectionCard("تجهیزات", "تعداد، وضعیت و ساعات تجهیز در دو ستون اعلامی و تاییدی.", renderEmptySection("برای این گزارش ردیف تجهیز ثبت نشده است."), 0);
  }
  const body = `
    <div class="sl-report-table-wrap">
      <table class="module-crud-table sl-report-table">
        <thead>
          <tr>
            <th rowspan="2">#</th>
            <th rowspan="2">کد تجهیز</th>
            <th rowspan="2">عنوان تجهیز</th>
            <th rowspan="2">محل کارکرد</th>
            <th colspan="3">اعلامی پیمانکار</th>
            <th colspan="3">تایید مشاور</th>
            <th rowspan="2">فایل‌ها</th>
            <th rowspan="2">توضیحات</th>
          </tr>
          <tr>
            <th>تعداد</th>
            <th>وضعیت</th>
            <th>ساعت</th>
            <th>تعداد</th>
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
                  <td>${stateBridge.esc(textValue(row.work_location))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.claimed_count), 0))}</td>
                  <td>${stateBridge.esc(textValue(row.claimed_status))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.claimed_hours), 1))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.verified_count), 0))}</td>
                  <td>${stateBridge.esc(textValue(row.verified_status))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.verified_hours), 1))}</td>
                  <td>${rowAttachmentFilesDetailHtml(row)}</td>
                  <td class="sl-report-note-cell">${stateBridge.esc(textValue(row.note))}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return renderSectionCard("تجهیزات", "تعداد، وضعیت و ساعات تجهیز در دو ستون اعلامی و تاییدی.", body, rows.length);
}

function renderActivityDetail(rows: Record<string, unknown>[]): string {
  if (!rows.length) {
    return renderSectionCard("فعالیت‌های اجرایی", "نمایش جزئیات روزانه و تجمیعی فعالیت‌های ثبت‌شده.", renderEmptySection("برای این گزارش فعالیتی ثبت نشده است."), 0);
  }
  const body = `
    <div class="sl-report-table-wrap">
      <table class="module-crud-table sl-report-table">
        <thead>
          <tr>
            <th>ردیف</th>
            <th>کد</th>
            <th>عنوان فعالیت</th>
            <th>مرحله PMS</th>
            <th>محل</th>
            <th>واحد</th>
            <th>نفرات</th>
            <th>امروز</th>
            <th>تجمیعی</th>
            <th>وضعیت</th>
            <th>علت توقف</th>
            <th>فایل‌ها</th>
            <th>توضیح</th>
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
                  <td>${stateBridge.esc([textValue(row.pms_step_title), row.pms_step_weight_pct ? formatNumber(toNumber(row.pms_step_weight_pct), 0, "%") : ""].filter(Boolean).join(" - ") || "-")}</td>
                  <td>${stateBridge.esc(textValue(row.location))}</td>
                  <td>${stateBridge.esc(textValue(row.unit))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.personnel_count), 0))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.today_quantity), 2))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.cumulative_quantity), 2))}</td>
                  <td>${stateBridge.esc(textValue(row.activity_status))}</td>
                  <td>${stateBridge.esc(textValue(row.stop_reason))}</td>
                  <td>${rowAttachmentFilesDetailHtml(row)}</td>
                  <td class="sl-report-note-cell">${stateBridge.esc(textValue(row.note))}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return renderSectionCard("فعالیت‌های اجرایی", "نمایش جزئیات روزانه و تجمیعی فعالیت‌های ثبت‌شده.", body, rows.length);
}

function renderMaterialDetail(rows: Record<string, unknown>[]): string {
  if (!rows.length) {
    return renderSectionCard("مصالح", "ورودی، مصرف و مقدار تجمیعی مصالح در این گزارش.", renderEmptySection("برای این گزارش ردیف مصالح ثبت نشده است."), 0);
  }
  const body = `
    <div class="sl-report-table-wrap">
      <table class="module-crud-table sl-report-table">
        <thead>
          <tr>
            <th>ردیف</th>
            <th>کد</th>
            <th>عنوان</th>
            <th>محل مصرف</th>
            <th>واحد</th>
            <th>ورودی</th>
            <th>مصرف</th>
            <th>تجمیعی</th>
            <th>فایل‌ها</th>
            <th>توضیح</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row, index) => `
                <tr>
                  <td>${index + 1}</td>
                  <td class="sl-report-code-cell">${stateBridge.esc(textValue(row.material_code))}</td>
                  <td>${stateBridge.esc(textValue(row.title))}</td>
                  <td>${stateBridge.esc(textValue(row.consumption_location))}</td>
                  <td>${stateBridge.esc(textValue(row.unit))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.incoming_quantity), 2))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.consumed_quantity), 2))}</td>
                  <td>${stateBridge.esc(formatNumber(toNumber(row.cumulative_quantity), 2))}</td>
                  <td>${rowAttachmentFilesDetailHtml(row)}</td>
                  <td class="sl-report-note-cell">${stateBridge.esc(textValue(row.note))}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return renderSectionCard("مصالح", "ورودی، مصرف و مقدار تجمیعی مصالح در این گزارش.", body, rows.length);
}

function renderIssueDetail(rows: Record<string, unknown>[]): string {
  if (!rows.length) {
    return renderSectionCard("موانع / ریسک‌ها", "ثبت مشکلات، کمبودها و موارد نیازمند پیگیری.", renderEmptySection("برای این گزارش موردی در بخش موانع / ریسک‌ها ثبت نشده است."), 0);
  }
  const body = `
    <div class="sl-report-table-wrap">
      <table class="module-crud-table sl-report-table">
        <thead>
          <tr>
            <th>ردیف</th>
            <th>نوع</th>
            <th>شرح</th>
            <th>مسئول</th>
            <th>موعد</th>
            <th>وضعیت</th>
            <th>فایل‌ها</th>
            <th>توضیح</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row, index) => `
                <tr>
                  <td>${index + 1}</td>
                  <td>${stateBridge.esc(textValue(row.issue_type_label || row.issue_type))}</td>
                  <td>${stateBridge.esc(textValue(row.description))}</td>
                  <td>${stateBridge.esc(textValue(row.responsible_party))}</td>
                  <td>${stateBridge.esc(formatShamsiDate(row.due_date))}</td>
                  <td>${stateBridge.esc(textValue(row.status))}</td>
                  <td>${rowAttachmentFilesDetailHtml(row)}</td>
                  <td class="sl-report-note-cell">${stateBridge.esc(textValue(row.note))}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return renderSectionCard("موانع / ریسک‌ها", "ثبت مشکلات، کمبودها و موارد نیازمند پیگیری.", body, rows.length);
}

function renderReportAttachmentDetail(rows: Record<string, unknown>[]): string {
  if (!rows.length) {
    return renderSectionCard("پیوست‌ها", "ثبت ساختاریافته‌ی پیوست‌ها و ارجاع به فایل‌های گزارش.", renderEmptySection("برای این گزارش ردیف پیوست ساختاریافته ثبت نشده است."), 0);
  }
  const body = `
    <div class="sl-report-table-wrap">
      <table class="module-crud-table sl-report-table">
        <thead>
          <tr>
            <th>ردیف</th>
            <th>نوع</th>
            <th>عنوان</th>
            <th>مرجع</th>
            <th>توضیح</th>
            <th>فایل</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row, index) => `
                <tr>
                  <td>${index + 1}</td>
                  <td>${stateBridge.esc(textValue(row.attachment_type))}</td>
                  <td>${stateBridge.esc(textValue(row.title))}</td>
                  <td>${stateBridge.esc(textValue(row.reference_no))}</td>
                  <td class="sl-report-note-cell">${stateBridge.esc(textValue(row.note))}</td>
                  <td>${reportAttachmentFilesDetailHtml(row)}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  return renderSectionCard("پیوست‌ها", "ثبت ساختاریافته‌ی پیوست‌ها و ارجاع به فایل‌های گزارش.", body, rows.length);
}

function renderQcDetail(row: Record<string, unknown>): string {
  const cards = `
    <div class="sl-qc-grid sl-qc-grid-detail">
      <article class="sl-qc-card"><span>تست</span><strong>${stateBridge.esc(String(Number(row.qc_test_count || 0)))}</strong></article>
      <article class="sl-qc-card"><span>بازرسی</span><strong>${stateBridge.esc(String(Number(row.qc_inspection_count || 0)))}</strong></article>
      <article class="sl-qc-card"><span>Punch باز</span><strong>${stateBridge.esc(String(Number(row.qc_open_punch_count || 0)))}</strong></article>
      <article class="sl-qc-card"><span>NCR باز</span><strong>${stateBridge.esc(String(Number(row.qc_open_ncr_count || 0)))}</strong></article>
    </div>
  `;
  const note = `
    <div class="sl-report-summary-box">
      <div class="sl-report-summary-box-title">شرح کیفیت / اقدام اصلاحی</div>
      <div class="sl-report-summary-box-text">${stateBridge.esc(textValue(row.qc_summary_note))}</div>
    </div>
  `;
  return renderSectionCard("QC", "خلاصه تست‌ها، بازرسی‌ها، NCR و موارد اصلاحی این گزارش.", cards + note, 4);
}

function renderDetailCard(moduleKey: string, tabKey: string, row: Record<string, unknown>): void {
  const key = keyOf(moduleKey, tabKey);
  const host = getElement(`sl-detail-wrap-${key}`);
  if (!(host instanceof HTMLElement)) return;
  detailRowByKey[key] = row;
  const manpowerRows = asArray(row.manpower_rows);
  const equipmentRows = asArray(row.equipment_rows);
  const activityRows = asArray(row.activity_rows);
  const materialRows = asArray(row.material_rows);
  const issueRows = asArray(row.issue_rows);
  const attachmentRows = asArray(row.attachment_rows);
  const claimedManpowerCount = formatNumber(sumRows(manpowerRows, "claimed_count"), 0, " نفر");
  const verifiedManpowerCount = formatNumber(sumRows(manpowerRows, "verified_count"), 0, " نفر");
  const claimedManpowerHours = formatNumber(sumRows(manpowerRows, "claimed_hours"), 1, " ساعت");
  const verifiedManpowerHours = formatNumber(sumRows(manpowerRows, "verified_hours"), 1, " ساعت");
  const claimedEquipmentCount = formatNumber(sumRows(equipmentRows, "claimed_count"), 0, " دستگاه");
  const verifiedEquipmentCount = formatNumber(sumRows(equipmentRows, "verified_count"), 0, " دستگاه");
  const claimedEquipmentHours = formatNumber(sumRows(equipmentRows, "claimed_hours"), 1, " ساعت");
  const verifiedEquipmentHours = formatNumber(sumRows(equipmentRows, "verified_hours"), 1, " ساعت");
  const activityCount = formatNumber(activityRows.length || 0, 0, " ردیف");
  const blockedActivities = formatNumber(
    activityRows.filter((row) => String(row.stop_reason ?? "").trim()).length,
    0,
    " ردیف"
  );
  host.innerHTML = `
    <article class="sl-report-detail">
      <div class="sl-report-print-actions">
        <button type="button" class="btn btn-secondary" data-sl-action="download-detail-pdf">
          <span class="material-icons-round">picture_as_pdf</span>
          دانلود PDF
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
            ${renderDetailPill("وضعیت کارگاه", workStatusLabelFa(row.work_status))}
            ${renderDetailPill("تاریخ", formatShamsiDate(row.log_date))}
            ${renderDetailPill("شیفت", textValue(row.shift_label || row.shift))}
            ${renderDetailPill("موضوع قرارداد", textValue(row.contract_subject))}
            ${renderDetailPill("شماره قرارداد", textValue(row.contract_number))}
            ${renderDetailPill("وضعیت جوی", textValue(row.weather_label || row.weather))}
            ${renderDetailPill("نام پروژه", projectName(row.project_code))}
          </div>
        </div>
        <div class="sl-report-hero-side">
          ${renderMetaItem("کد پروژه", row.project_code)}
          ${renderMetaItem("پروژه", projectName(row.project_code))}
          ${renderMetaItem("سازمان", row.organization_name)}
          ${renderMetaItem("موضوع قرارداد", row.contract_subject)}
          ${renderMetaItem("شماره قرارداد", row.contract_number)}
          ${renderMetaItem("بلوک قرارداد", row.contract_block)}
          ${renderMetaItem("شیفت", row.shift_label || row.shift)}
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
          ${renderMetaItem("وضعیت کارگاه", workStatusLabelFa(row.work_status))}
          ${renderMetaItem("نوع گزارش", logTypeLabelFa(row.log_type))}
          ${renderMetaItem("موضوع قرارداد", row.contract_subject)}
          ${renderMetaItem("شماره قرارداد", row.contract_number)}
          ${renderMetaItem("بلوک قرارداد", row.contract_block)}
          ${renderMetaItem("شیفت", row.shift_label || row.shift)}
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
          <strong>خلاصه مدیریت</strong>
        </div>
        ${renderNarrativeSummaryBoxes(row)}
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
          ${renderCompareMetric("تعداد تجهیزات", "construction", claimedEquipmentCount, verifiedEquipmentCount, "جمع تعداد تجهیزات ثبت‌شده در این گزارش")}
          ${renderCompareMetric("ساعات تجهیزات", "precision_manufacturing", claimedEquipmentHours, verifiedEquipmentHours, "جمع ساعات کارکرد تجهیزات")}
          ${renderCompareMetric("فعالیت‌های اجرایی", "insights", activityCount, blockedActivities, "تعداد کل فعالیت‌ها در کنار تعداد ردیف‌های متوقف", "کل ردیف‌ها", "دارای توقف")}
        </div>
      </section>

      ${renderManpowerDetail(manpowerRows)}
      ${renderEquipmentDetail(equipmentRows)}
      ${renderActivityDetail(activityRows)}
      ${renderMaterialDetail(materialRows)}
      ${renderIssueDetail(issueRows)}
      ${renderReportAttachmentDetail(attachmentRows)}
      ${renderQcDetail(row)}
      ${renderApprovalFlow(row)}
    </article>
  `;
}

function activityRowFromCatalogItem(item: Record<string, unknown>, index: number): Record<string, unknown> {
  return {
    activity_code: String(item.activity_code ?? "").trim(),
    activity_title: String(item.activity_title ?? "").trim(),
    source_system: "CATALOG",
    external_ref: `site_log_activity_catalog:${Number(item.id || 0)}`,
    claimed_progress_pct: "",
    verified_progress_pct: "",
    location: String(item.default_location ?? "").trim(),
    unit: String(item.default_unit ?? "").trim(),
    personnel_count: "",
    pms_mapping_id: Number(item.pms_mapping_id || 0) || "",
    pms_template_code: String(item.pms_template_code ?? "").trim(),
    pms_template_title: String(item.pms_template_title ?? "").trim(),
    pms_template_version: Number(item.pms_snapshot_version || item.pms_template_version || 0) || "",
    pms_step_code: "",
    pms_step_title: "",
    pms_step_weight_pct: "",
    pms_steps: asArray(item.pms_steps),
    today_quantity: "",
    cumulative_quantity: "",
    activity_status: "",
    stop_reason: "",
    note: "",
    sort_order: index,
  };
}

async function refreshFormRuntimeData(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const sequence = (asyncSyncSeqByKey[key] || 0) + 1;
  asyncSyncSeqByKey[key] = sequence;
  const projectCode = upper(getValue(`sl-form-project-${key}`));
  const organizationId = formBridge.toInt(getValue(`sl-form-organization-${key}`));
  const organizationContractId = formBridge.toInt(getValue(`sl-form-contract-subject-${key}`));
  const logDate = getValue(`sl-form-log-date-${key}`);

  if (!projectCode) {
    activityOptionsByKey[key] = [];
    qcSnapshotByKey[key] = {};
    updateActivityPickerUi(moduleKey, tabKey);
    rerenderSection(moduleKey, tabKey, "activity", deps);
    renderQcSnapshot(moduleKey, tabKey);
    return;
  }

  try {
    const activityPayload = await dataBridge.activityOptions(
      {
        project_code: projectCode,
        organization_id: organizationId,
        organization_contract_id: organizationContractId,
      },
      { fetch: deps.fetch }
    );
    if (asyncSyncSeqByKey[key] !== sequence) return;
    activityOptionsByKey[key] = asArray(activityPayload.data);
    updateActivityPickerUi(moduleKey, tabKey);
    rerenderSection(moduleKey, tabKey, "activity", deps);
  } catch (error) {
    if (asyncSyncSeqByKey[key] !== sequence) return;
    activityOptionsByKey[key] = [];
    updateActivityPickerUi(moduleKey, tabKey);
    rerenderSection(moduleKey, tabKey, "activity", deps);
    console.warn("siteLogs activity options refresh failed:", error);
  }

  if (!logDate) {
    qcSnapshotByKey[key] = {};
    renderQcSnapshot(moduleKey, tabKey);
    return;
  }

  try {
    const qcPayload = await dataBridge.qcSnapshot(
      {
        project_code: projectCode,
        organization_id: organizationId,
        log_date: logDate,
      },
      { fetch: deps.fetch }
    );
    if (asyncSyncSeqByKey[key] !== sequence) return;
    qcSnapshotByKey[key] = qcPayload;
    renderQcSnapshot(moduleKey, tabKey);
  } catch (error) {
    if (asyncSyncSeqByKey[key] !== sequence) return;
    qcSnapshotByKey[key] = {};
    renderQcSnapshot(moduleKey, tabKey);
    console.warn("siteLogs qc snapshot refresh failed:", error);
  }
}

function addActivityOptionRow(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): void {
  const key = keyOf(moduleKey, tabKey);
  const picker = getElement(`sl-activity-picker-${key}`);
  if (!(picker instanceof HTMLInputElement)) return;
  const query = String(picker.value || "").trim();
  if (!query) {
    deps.showToast("ابتدا یک فعالیت از کاتالوگ انتخاب کنید.", "error");
    return;
  }
  const selected = matchActivityOption(key, query, false);
  if (!selected) {
    deps.showToast("فعالیت نزدیک یا مطابق در کاتالوگ پیدا نشد.", "error");
    return;
  }
  const rows = collectSectionRows(moduleKey, tabKey, "activity");
  rows.push(activityRowFromCatalogItem(selected, rows.length));
  renderSectionRows(moduleKey, tabKey, "activity", rows, currentFormMode(moduleKey, tabKey), boardCapabilities(moduleKey, tabKey, deps));
  focusSectionRow(moduleKey, tabKey, "activity", rows.length - 1);
  picker.value = "";
  setDrawerDirty(moduleKey, tabKey, true);
}

async function refreshCommentsAndAttachments(moduleKey: string, tabKey: string, logId: number, deps: SiteLogsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  if (logId <= 0) {
    stateBridge.renderComments(getElement(`sl-comments-${key}`), []);
    stateBridge.renderAttachments(getElement(`sl-attachments-${key}`), {});
    attachmentOptionsByKey[key] = [];
    rerenderAttachmentAwareSections(moduleKey, tabKey, deps);
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
    attachmentOptionsByKey[key] = asArray(attachments.data);
    rerenderAttachmentAwareSections(moduleKey, tabKey, deps);
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
    organization_id: getValue(`sl-filter-organization-${key}`),
    organization_contract_id: getValue(`sl-filter-contract-${key}`),
    log_type: getValue(`sl-filter-log-type-${key}`),
    status_code: getValue(`sl-filter-status-${key}`),
    work_status: getValue(`sl-filter-work-status-${key}`),
    log_date_from: getValue(`sl-filter-date-from-${key}`),
    log_date_to: getValue(`sl-filter-date-to-${key}`),
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
  await refreshFormRuntimeData(moduleKey, tabKey, deps);
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
    if (mode !== "detail") {
      await refreshFormRuntimeData(moduleKey, tabKey, deps);
    }
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "باز کردن گزارش ناموفق بود."), "error");
  }
}

function validateAndNotify(errors: string[], deps: SiteLogsUiDeps): boolean {
  if (!errors.length) return true;
  deps.showToast(errors[0], "error");
  return false;
}

function catalogPairMatches(catalogKey: string, codeValue: unknown, labelValue: unknown): boolean {
  const rows = optionRowsFromCatalog(catalogKey);
  const code = upper(codeValue);
  const label = searchNeedle(labelValue);
  if (!code && !label) return true;
  if (!rows.length) return false;
  return rows.some((row) => {
    const rowCode = upper(row.code);
    const rowLabel = searchNeedle(catalogFieldLabel(row, "code", "label"));
    const codeMatches = !code || rowCode === code;
    const labelMatches = !label || rowLabel === label;
    return codeMatches && labelMatches;
  });
}

function activityCatalogRowMatches(key: string, row: Record<string, unknown>): boolean {
  const code = upper(row.activity_code);
  const title = searchNeedle(row.activity_title);
  const externalRef = String(row.external_ref || "").trim();
  const catalogId = Number((externalRef.match(/site_log_activity_catalog:(\d+)/) || [])[1] || 0);
  if (!isMeaningfulSectionRow("activity", row)) return true;
  if (!code && !title && catalogId <= 0) return false;
  const rows = activityOptionsForKey(key);
  if (!rows.length) return false;
  return rows.some((item) => {
    const itemId = Number(item.id || 0);
    const itemCode = upper(item.activity_code);
    const itemTitle = searchNeedle(item.activity_title);
    const itemLabel = searchNeedle(activityOptionLabel(item));
    if (catalogId > 0 && itemId === catalogId) return true;
    if (code && itemCode !== code) return false;
    if (title && itemTitle !== title && itemLabel !== title) return false;
    return Boolean(code || title);
  });
}

function validateRestrictedCatalogRows(input: Record<string, unknown>, key: string): string[] {
  const errors: string[] = [];
  const add = (message: string) => {
    if (!errors.length) errors.push(message);
  };
  asArray(input.manpower_rows).forEach((row, index) => {
    const isNewMeaningfulRow = Number(row.id || 0) <= 0 && isMeaningfulSectionRow("manpower", row);
    const hasRole = Boolean(upper(row.role_code) || searchNeedle(row.role_label));
    const hasWorkSection = Boolean(searchNeedle(row.work_section_label));
    if (isNewMeaningfulRow && (!hasRole || !catalogPairMatches("role_catalog", row.role_code, row.role_label))) {
      add(`نفرات، ردیف ${formatFaCount(index + 1)}: نقش باید از کاتالوگ انتخاب شود.`);
    }
    if (isNewMeaningfulRow && (!hasWorkSection || !catalogPairMatches("work_section_catalog", null, row.work_section_label))) {
      add(`نفرات، ردیف ${formatFaCount(index + 1)}: واحد / بخش کاری باید از کاتالوگ انتخاب شود.`);
    }
  });
  asArray(input.equipment_rows).forEach((row, index) => {
    if (Number(row.id || 0) <= 0 && !catalogPairMatches("equipment_catalog", row.equipment_code, row.equipment_label)) {
      add(`تجهیزات، ردیف ${formatFaCount(index + 1)}: عنوان تجهیز باید از کاتالوگ انتخاب شود.`);
    }
    if (!catalogPairMatches("equipment_status_catalog", row.claimed_status, null)) {
      add(`تجهیزات، ردیف ${formatFaCount(index + 1)}: وضعیت اعلامی باید از کاتالوگ انتخاب شود.`);
    }
    if (!catalogPairMatches("equipment_status_catalog", row.verified_status, null)) {
      add(`تجهیزات، ردیف ${formatFaCount(index + 1)}: وضعیت تاییدی باید از کاتالوگ انتخاب شود.`);
    }
  });
  asArray(input.activity_rows).forEach((row, index) => {
    if (Number(row.id || 0) <= 0 && !activityCatalogRowMatches(key, row)) {
      add(`فعالیت‌ها، ردیف ${formatFaCount(index + 1)}: عنوان فعالیت باید از کاتالوگ انتخاب شود.`);
    }
  });
  asArray(input.material_rows).forEach((row, index) => {
    if (Number(row.id || 0) <= 0 && !catalogPairMatches("material_catalog", row.material_code, row.title)) {
      add(`مصالح، ردیف ${formatFaCount(index + 1)}: عنوان مصالح باید از کاتالوگ انتخاب شود.`);
    }
  });
  asArray(input.issue_rows).forEach((row, index) => {
    if (!catalogPairMatches("issue_type_catalog", row.issue_type, null)) {
      add(`موانع / ریسک‌ها، ردیف ${formatFaCount(index + 1)}: نوع باید از کاتالوگ انتخاب شود.`);
    }
  });
  asArray(input.attachment_rows).forEach((row, index) => {
    if (!catalogPairMatches("attachment_type_catalog", row.attachment_type, null)) {
      add(`پیوست‌ها، ردیف ${formatFaCount(index + 1)}: نوع پیوست باید از کاتالوگ انتخاب شود.`);
    }
  });
  return errors;
}

async function saveForm(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<number> {
  const raw = readForm(moduleKey, tabKey);
  const key = keyOf(moduleKey, tabKey);
  const errors = [...formBridge.validateBase(raw), ...validateRestrictedCatalogRows(raw, key)];
  if (!validateAndNotify(errors, deps)) return 0;
  const currentId = Number(raw.id || 0);
  try {
    const payload = currentId > 0 ? formBridge.buildUpdatePayload(raw) : formBridge.buildCreatePayload(raw);
    const res = currentId > 0 ? await dataBridge.update(currentId, payload, { fetch: deps.fetch }) : await dataBridge.create(payload, { fetch: deps.fetch });
    const row = asRecord(res.data);
    const id = Number(row.id || 0);
    if (id > 0) {
      selectedByKey[key] = id;
      fillFormFromLog(moduleKey, tabKey, row, currentFormMode(moduleKey, tabKey), deps);
      setValue(`sl-form-id-${key}`, id);
      setValue(`sl-form-status-${key}`, row.status_code || "DRAFT");
      setExistingSectionsVisible(moduleKey, tabKey, true);
      await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
      await refreshFormRuntimeData(moduleKey, tabKey, deps);
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
  const confirmed = window.confirm(
    "آیا از ارسال گزارش کارگاهی مطمئن هستید؟\nبعد از ارسال، پیمانکار دیگر امکان ویرایش گزارش را ندارد و گزارش برای تایید مشاور ارسال می‌شود."
  );
  if (!confirmed) return false;
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
  const confirmed = window.confirm("آیا از تایید نهایی این گزارش کارگاهی مطمئن هستید؟");
  if (!confirmed) return false;
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

async function returnForRevisionForm(moduleKey: string, tabKey: string, deps: SiteLogsUiDeps): Promise<boolean> {
  const key = keyOf(moduleKey, tabKey);
  const id = Number(getValue(`sl-form-id-${key}`) || 0);
  if (id <= 0) {
    deps.showToast("ابتدا یک گزارش ارسال‌شده را انتخاب کنید.", "error");
    return false;
  }
  const note = getValue(`sl-comment-input-${key}`);
  if (!note) {
    deps.showToast("برای برگشت گزارش، یادداشت اصلاحات الزامی است.", "error");
    return false;
  }
  try {
    const res = await dataBridge.returnForRevision(id, { note }, { fetch: deps.fetch });
    const row = asRecord(res.data);
    setValue(`sl-form-status-${key}`, row.status_code || "RETURNED");
    setValue(`sl-comment-input-${key}`, "");
    setDrawerDirty(moduleKey, tabKey, false);
    deps.showToast("گزارش برای اصلاح به پیمانکار برگشت داده شد.", "success");
    await loadBoard(moduleKey, tabKey, deps, true);
    closeDrawer(moduleKey, tabKey);
    return true;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "برگشت گزارش ناموفق بود."), "error");
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
  const files = Array.from(input.files);
  const hadUnsavedChanges = Boolean(drawerDirtyByKey[key]);
  try {
    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("section_code", getValue(`sl-attachment-section-${key}`) || "GENERAL");
      formData.append("file_kind", getValue(`sl-attachment-kind-${key}`) || "attachment");
      await dataBridge.uploadAttachment(id, formData, { fetch: deps.fetch });
    }
    input.value = "";
    await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
    if (!hadUnsavedChanges) setDrawerDirty(moduleKey, tabKey, false);
    deps.showToast(files.length > 1 ? "پیوست‌ها با موفقیت بارگذاری شدند." : "پیوست با موفقیت بارگذاری شد.", "success");
    return true;
  } catch (error) {
    deps.showToast(String((error as Error)?.message || "بارگذاری ناموفق بود."), "error");
    return false;
  }
}

function rowAttachmentNote(section: SectionKind, rowMeta: Record<string, unknown>): string {
  const keysBySection: Record<string, string[]> = {
    manpower: ["role_code", "role_label", "work_section_label", "note"],
    equipment: ["equipment_code", "equipment_label", "work_location", "note"],
    activity: ["activity_code", "activity_title", "location", "note"],
    material: ["material_code", "title", "consumption_location", "unit", "note"],
    issue: ["issue_type", "description", "responsible_party", "note"],
    report_attachment: ["title", "reference_no", "note"],
  };
  return (keysBySection[section] || ["note"])
    .map((key) => String(rowMeta[key] || "").trim())
    .filter(Boolean)
    .join(" | ");
}

function rowAttachmentStableRowId(key: string, section: SectionKind, rowIndex: number): number {
  if (section === "report_attachment") return 0;
  const rowEl = getElement(sectionBodyId(section, key))?.querySelector<HTMLTableRowElement>(
    `tr[data-sl-row-index="${rowIndex}"]`
  );
  const dbRowId = Number(rowEl?.dataset.slRowDbId || 0);
  return Number.isFinite(dbRowId) && dbRowId > 0 ? dbRowId : 0;
}

function rowAttachmentTargetRowId(key: string, section: SectionKind, rowIndex: number): number {
  const stableRowId = rowAttachmentStableRowId(key, section, rowIndex);
  return stableRowId > 0 ? stableRowId : rowIndex + 1;
}

async function uploadRowAttachment(
  moduleKey: string,
  tabKey: string,
  section: SectionKind,
  rowIndex: number,
  deps: SiteLogsUiDeps
): Promise<boolean> {
  const key = keyOf(moduleKey, tabKey);
  if (!SECTION_DEFS[section]) {
    deps.showToast("بخش ردیف پیوست معتبر نیست.", "error");
    return false;
  }
  const input = getElement(sectionBodyId(section, key))?.querySelector<HTMLInputElement>(
    `input[data-sl-row-attachment-file="${section}:${rowIndex}"]`
  );
  if (!(input instanceof HTMLInputElement) || !input.files || !input.files.length) {
    deps.showToast("برای این ردیف حداقل یک فایل انتخاب کنید.", "error");
    return false;
  }
  setRowFileStatus(moduleKey, tabKey, section, rowIndex, "pending");
  const files = Array.from(input.files);
  const rowsBeforeSave = collectSectionRows(moduleKey, tabKey, section);
  const rowMeta = asRecord(rowsBeforeSave[rowIndex]);
  let id = Number(getValue(`sl-form-id-${key}`) || 0);
  const hadUnsavedChanges = id > 0 && Boolean(drawerDirtyByKey[key]);
  const needsStableRowId = section !== "report_attachment" && rowAttachmentStableRowId(key, section, rowIndex) <= 0;
  if (id <= 0 || needsStableRowId) {
    id = await saveForm(moduleKey, tabKey, deps);
    if (id <= 0) {
      setRowFileStatus(moduleKey, tabKey, section, rowIndex, "error");
      return false;
    }
  }
  const targetRowId = rowAttachmentTargetRowId(key, section, rowIndex);
  const note = rowAttachmentNote(section, rowMeta);
  try {
    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("section_code", attachmentSectionCodeForRowSection(section));
      formData.append("file_kind", "attachment");
      formData.append("row_id", String(targetRowId));
      if (note) formData.append("note", note);
      await dataBridge.uploadAttachment(id, formData, { fetch: deps.fetch });
    }
    input.value = "";
    await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
    setRowFileStatus(moduleKey, tabKey, section, rowIndex, "clear");
    if (!hadUnsavedChanges) setDrawerDirty(moduleKey, tabKey, false);
    const sectionTitle = SECTION_DEFS[section]?.title || "ردیف";
    deps.showToast(
      files.length > 1 ? `فایل‌های ردیف ${sectionTitle} بارگذاری شدند.` : `فایل ردیف ${sectionTitle} بارگذاری شد.`,
      "success"
    );
    return true;
  } catch (error) {
    setRowFileStatus(moduleKey, tabKey, section, rowIndex, "error");
    deps.showToast(String((error as Error)?.message || "بارگذاری فایل‌های ردیف ناموفق بود."), "error");
    return false;
  }
}

async function uploadReportAttachmentRow(moduleKey: string, tabKey: string, rowIndex: number, deps: SiteLogsUiDeps): Promise<boolean> {
  return uploadRowAttachment(moduleKey, tabKey, "report_attachment", rowIndex, deps);
}

async function deleteAttachment(moduleKey: string, tabKey: string, attachmentId: number, deps: SiteLogsUiDeps): Promise<boolean> {
  const key = keyOf(moduleKey, tabKey);
  const id = Number(getValue(`sl-form-id-${key}`) || 0);
  if (id <= 0 || attachmentId <= 0) return false;
  const hadUnsavedChanges = Boolean(drawerDirtyByKey[key]);
  try {
    await dataBridge.deleteAttachment(id, attachmentId, { fetch: deps.fetch });
    const body = getElement(`sl-form-report_attachment-body-${key}`);
    body?.querySelectorAll<HTMLInputElement>(`input[data-sl-field="linked_attachment_id"]`).forEach((input) => {
      if (Number(input.value || 0) === attachmentId) {
        const rowEl = input.closest("tr[data-sl-row-index]");
        input.value = "";
        rowEl?.querySelectorAll<HTMLInputElement>(
          `input[data-sl-field="linked_attachment_file_name"], input[data-sl-field="linked_attachment_file_kind"], input[data-sl-field="linked_attachment_download_url"]`
        ).forEach((hidden) => {
          hidden.value = "";
        });
      }
    });
    await refreshCommentsAndAttachments(moduleKey, tabKey, id, deps);
    if (!hadUnsavedChanges) setDrawerDirty(moduleKey, tabKey, false);
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
  const nextRow: Record<string, unknown> = { sort_order: rows.length };
  if (section === "activity") {
    nextRow.source_system = "MANUAL";
  }
  rows.push(nextRow);
  const mode = (getValue(`sl-form-mode-${key}`) || "create") as FormMode;
  renderSectionRows(moduleKey, tabKey, section, rows, mode, boardCapabilities(moduleKey, tabKey, deps));
  focusSectionRow(moduleKey, tabKey, section, rows.length - 1);
  setDrawerDirty(moduleKey, tabKey, true);
}

function copyLastSectionRow(moduleKey: string, tabKey: string, section: SectionKind, deps: SiteLogsUiDeps): void {
  const key = keyOf(moduleKey, tabKey);
  const rows = collectSectionRows(moduleKey, tabKey, section);
  const source = [...rows].reverse().find((row) => isMeaningfulSectionRow(section, row));
  const clone = source ? { ...source } : {};
  delete clone.id;
  clone.sort_order = rows.length;
  if (section === "report_attachment") {
    delete clone.linked_attachment_id;
    delete clone.linked_attachment_file_name;
    delete clone.linked_attachment_file_kind;
    delete clone.linked_attachment_download_url;
  }
  rows.push(clone);
  const mode = (getValue(`sl-form-mode-${key}`) || "create") as FormMode;
  renderSectionRows(moduleKey, tabKey, section, rows, mode, boardCapabilities(moduleKey, tabKey, deps));
  focusSectionRow(moduleKey, tabKey, section, rows.length - 1);
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

function toggleSection(moduleKey: string, tabKey: string, section: SectionKind): void {
  const key = keyOf(moduleKey, tabKey);
  const collapsed = !isSectionCollapsed(key, section);
  setSectionCollapsed(key, section, collapsed);
  const sectionEl = getElement(`sl-section-${section}-${key}`);
  const content = getElement(`sl-section-content-${section}-${key}`);
  const button = sectionEl?.querySelector<HTMLElement>("[data-sl-action='toggle-section']");
  sectionEl?.classList.toggle("is-collapsed", collapsed);
  if (content instanceof HTMLElement) content.hidden = collapsed;
  if (button) {
    button.setAttribute("aria-expanded", collapsed ? "false" : "true");
    const icon = button.querySelector<HTMLElement>(".material-icons-round");
    if (icon) icon.textContent = collapsed ? "keyboard_arrow_down" : "keyboard_arrow_up";
  }
}

function toggleRowDetail(section: SectionKind, index: number, trigger: HTMLElement): void {
  const row = trigger.closest("tr");
  const body = row?.parentElement;
  const detail = body?.querySelector<HTMLTableRowElement>(`tr[data-sl-row-detail-for="${index}"]`);
  if (!(detail instanceof HTMLTableRowElement)) return;
  const willOpen = detail.hidden;
  detail.hidden = !willOpen;
  trigger.closest("[data-sl-row-menu]")?.querySelector("[data-sl-action='toggle-row-menu']")?.setAttribute("aria-expanded", "false");
}

function jumpToFormSection(moduleKey: string, tabKey: string, target: string): void {
  const key = keyOf(moduleKey, tabKey);
  const normalizedTarget = normalize(target);
  const id =
    normalizedTarget === "base" || normalizedTarget === "summary" || normalizedTarget === "qc"
      ? `sl-section-${normalizedTarget}-${key}`
      : `sl-section-${normalizedTarget}-${key}`;
  const el = getElement(id);
  if (el instanceof HTMLElement) {
    if (["manpower", "equipment", "activity", "material", "issue", "report_attachment"].includes(normalizedTarget)) {
      if (isSectionCollapsed(key, normalizedTarget as SectionKind)) {
        toggleSection(moduleKey, tabKey, normalizedTarget as SectionKind);
      }
    }
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function focusSectionRow(moduleKey: string, tabKey: string, section: SectionKind, index: number): void {
  const key = keyOf(moduleKey, tabKey);
  window.setTimeout(() => {
    const body = getElement(sectionBodyId(section, key));
    const row = body?.querySelector<HTMLElement>(`tr[data-sl-row-index="${index}"]`);
    const firstKey = meaningfulKeysForSection(section)[0];
    const firstField =
      (firstKey && row?.querySelector<HTMLElement>(`[data-sl-field="${firstKey}"]`)) ||
      row?.querySelector<HTMLElement>("[data-sl-field]:not([type='hidden'])");
    firstField?.focus();
  }, 0);
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
    if (!(actionEl instanceof HTMLElement)) {
      if ((event.target as HTMLElement | null)?.closest?.(".archive-row-menu-dropdown")) return;
      closeSiteLogRowMenus();
      return;
    }
    const action = normalize(actionEl.dataset.slAction);
    if (action !== "toggle-row-menu") {
      closeSiteLogRowMenus();
    }
    const context = contextFromElement(actionEl);
    if (!context) return;

    if (action === "toggle-row-menu") {
      toggleSiteLogRowMenu(actionEl);
      return;
    }
    if (action === "toggle-section") {
      toggleSection(context.moduleKey, context.tabKey, normalize(actionEl.dataset.slSection) as SectionKind);
      return;
    }
    if (action === "toggle-row-detail") {
      toggleRowDetail(normalize(actionEl.dataset.slSection) as SectionKind, Number(actionEl.dataset.slIndex || 0), actionEl);
      return;
    }
    if (action === "jump-section") {
      jumpToFormSection(context.moduleKey, context.tabKey, String(actionEl.dataset.slTarget || ""));
      return;
    }
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
    if (action === "download-detail-pdf") {
      void downloadDetailPdf(context.moduleKey, context.tabKey, deps, actionEl);
      return;
    }
    if (action === "preview-attachment") {
      event.preventDefault();
      void previewSiteLogAttachment(Number(actionEl.dataset.slAttachmentId || 0), String(actionEl.dataset.slFileName || ""), deps);
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
        `${mode === "summary" ? "خلاصه گزارش کارگاهی" : "گزارش کارگاهی"} - ${textValue(row.log_no, "print")}`
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
    if (action === "return-form") {
      void returnForRevisionForm(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "upload-attachment") {
      void uploadAttachment(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "upload-row-attachment" || action === "upload-report-attachment-row") {
      const section = action === "upload-row-attachment" ? (normalize(actionEl.dataset.slSection) as SectionKind) : "report_attachment";
      void uploadRowAttachment(context.moduleKey, context.tabKey, section, Number(actionEl.dataset.slIndex || 0), deps);
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
    if (action === "copy-last-row") {
      copyLastSectionRow(context.moduleKey, context.tabKey, normalize(actionEl.dataset.slSection) as SectionKind, deps);
      return;
    }
    if (action === "add-activity-option") {
      addActivityOptionRow(context.moduleKey, context.tabKey, deps);
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
    const target = event.target as HTMLElement;
    const context = contextFromElement(target || null);
    if (!context) return;
    if (actionEl instanceof HTMLElement && normalize(actionEl.dataset.slAction) === "filter-search") {
      debouncedLoad(context.moduleKey, context.tabKey, deps);
      return;
    }
    const key = keyOf(context.moduleKey, context.tabKey);
    if ((target?.id || "") === `sl-form-qc-open-punch-${key}`) {
      renderQcSnapshot(context.moduleKey, context.tabKey);
    }
    if (target instanceof HTMLInputElement && target.type === "file") {
      return;
    }
    if (target instanceof HTMLInputElement && target.dataset.slTypeahead === "catalog") {
      applyCatalogTypeaheadValue(target, false);
    }
    if (target instanceof HTMLInputElement && target.dataset.slTypeahead === "activity-title") {
      applyActivityTitleTypeaheadValue(context.moduleKey, context.tabKey, target, false);
    }
    if (target instanceof HTMLInputElement && target.dataset.slTypeahead === "pms-step") {
      applyPmsStepTypeaheadValue(context.moduleKey, context.tabKey, target, false);
    }
    if (target?.closest?.(".ci-drawer-body")) {
      setDrawerDirty(context.moduleKey, context.tabKey, true);
      const rowEl = target.closest?.("tr[data-sl-row-index], tr[data-sl-row-detail-for]") as HTMLElement | null;
      const sectionEl = target.closest?.("[data-sl-section-wrap]") as HTMLElement | null;
      const section = normalize(sectionEl?.dataset.slSectionWrap) as SectionKind;
      if (rowEl && SECTION_DEFS[section]) updateSectionChrome(context.moduleKey, context.tabKey, section);
    }
  });

  document.addEventListener("change", (event) => {
    const actionEl = event.target && (event.target as HTMLElement).closest ? (event.target as HTMLElement).closest("[data-sl-action]") : null;
    const context = contextFromElement((event.target as HTMLElement) || null);
    if (!context) return;
    if (actionEl instanceof HTMLElement) {
      const action = normalize(actionEl.dataset.slAction);
      if (action === "filter-organization") {
        syncBoardContractFilterOptions(context.moduleKey, context.tabKey);
        void loadBoard(context.moduleKey, context.tabKey, deps, true);
        return;
      }
      if (
        [
          "filter-project",
          "filter-contract",
          "filter-log-type",
          "filter-status",
          "filter-work-status",
          "filter-date-from",
          "filter-date-to",
        ].includes(action)
      ) {
        void loadBoard(context.moduleKey, context.tabKey, deps, true);
        return;
      }
    }
    const targetId = (event.target as HTMLElement)?.id || "";
    const key = keyOf(context.moduleKey, context.tabKey);
    if (targetId === `sl-form-organization-${key}`) {
      setValue(`sl-form-contract-number-${key}`, "");
      setValue(`sl-form-contract-block-${key}`, "");
      syncOrganizationContractSubjectOptions(context.moduleKey, context.tabKey, {});
      void refreshFormRuntimeData(context.moduleKey, context.tabKey, deps);
    }
    if (targetId === `sl-form-contract-subject-${key}`) {
      syncSelectedContractSnapshot(context.moduleKey, context.tabKey);
      void refreshFormRuntimeData(context.moduleKey, context.tabKey, deps);
    }
    if (targetId === `sl-form-project-${key}` || targetId === `sl-form-log-date-${key}`) {
      void refreshFormRuntimeData(context.moduleKey, context.tabKey, deps);
    }
    const targetEl = event.target as HTMLElement;
    if (targetEl instanceof HTMLInputElement && targetEl.type === "file") {
      const marker = String(targetEl.dataset.slRowAttachmentFile || "");
      const [sectionRaw, indexRaw] = marker.split(":");
      const section = normalize(sectionRaw) as SectionKind;
      if (SECTION_DEFS[section] && targetEl.files && targetEl.files.length) {
        setRowFileStatus(context.moduleKey, context.tabKey, section, Number(indexRaw || 0), "pending");
      }
      return;
    }
    if (targetEl instanceof HTMLSelectElement && targetEl.dataset.slCatalogSelect === "1") {
      applyCatalogSelectValue(targetEl);
    }
    if (targetEl instanceof HTMLInputElement && targetEl.dataset.slTypeahead === "catalog") {
      applyCatalogTypeaheadValue(targetEl, true);
    }
    if (targetEl instanceof HTMLInputElement && targetEl.dataset.slTypeahead === "activity-title") {
      if (applyActivityTitleTypeaheadValue(context.moduleKey, context.tabKey, targetEl, true)) {
        rerenderSection(context.moduleKey, context.tabKey, "activity", deps);
      }
    }
    if (targetEl instanceof HTMLInputElement && targetEl.dataset.slTypeahead === "pms-step") {
      applyPmsStepTypeaheadValue(context.moduleKey, context.tabKey, targetEl, true);
    }
    if (targetEl?.closest?.(".ci-drawer-body")) {
      setDrawerDirty(context.moduleKey, context.tabKey, true);
    }
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target as HTMLElement | null;
    const context = contextFromElement(target || null);
    if (event.key === "Enter" && context && target instanceof HTMLInputElement) {
      const key = keyOf(context.moduleKey, context.tabKey);
      if ((target.id || "") === `sl-activity-picker-${key}`) {
        event.preventDefault();
        addActivityOptionRow(context.moduleKey, context.tabKey, deps);
        return;
      }
      if (target.dataset.slTypeahead === "activity-title") {
        event.preventDefault();
        if (applyActivityTitleTypeaheadValue(context.moduleKey, context.tabKey, target, true)) {
          rerenderSection(context.moduleKey, context.tabKey, "activity", deps);
        }
        return;
      }
    }
    if (event.key !== "Escape") return;
    closeSiteLogRowMenus();
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

