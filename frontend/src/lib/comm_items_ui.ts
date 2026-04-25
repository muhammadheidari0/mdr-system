// @ts-nocheck
import { createCommItemsDataBridge } from "./comm_items_data";
import { createCommItemsFormBridge } from "./comm_items_form";
import { createCommItemsStateBridge } from "./comm_items_state";
import { createCommItemsWorkflowBridge } from "./comm_items_workflow";
import { formatShamsiDate, formatShamsiDateForFileName } from "./persian_datetime";
import { initShamsiDateInputs } from "./shamsi_date_input";

export interface CommItemsUiDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
  canEdit: () => boolean;
  showToast: (message: string, type?: string) => void;
  cache: Record<string, unknown>;
}

export interface CommItemsUiBridge {
  onTabOpened(moduleKey: string, tabKey: string, deps: CommItemsUiDeps): Promise<boolean>;
  initModule(moduleKey: string, deps: CommItemsUiDeps): Promise<boolean>;
}

const dataBridge = createCommItemsDataBridge();
const formBridge = createCommItemsFormBridge();
const stateBridge = createCommItemsStateBridge();
const workflowBridge = createCommItemsWorkflowBridge();

const boardRowsByKey: Record<string, Record<string, unknown>[]> = {};
const selectedItemByKey: Record<string, number> = {};
const selectedItemTypeByKey: Record<string, string> = {};
const selectedTypeFilterByKey: Record<string, string> = {};
const loadingByKey: Record<string, boolean> = {};
const debounceTimers: Record<string, number | undefined> = {};
const drawerDirtyByKey: Record<string, boolean> = {};
const sectionExpandedByKey: Record<string, Record<string, boolean>> = {};
const shamsiRegistryByKey: Record<string, { syncAll: () => void }> = {};

let actionsBound = false;
let catalogCache: Record<string, unknown> | null = null;
let transitionMap = new Map<string, Record<string, unknown>[]>();

function normalize(v: unknown): string { return String(v ?? "").trim().toLowerCase(); }
function upper(v: unknown): string { return String(v ?? "").trim().toUpperCase(); }
function keyOf(m: unknown, t: unknown): string { return `${normalize(m)}-${normalize(t)}`; }
function asRecord(v: unknown): Record<string, unknown> { return v && typeof v === "object" ? (v as Record<string, unknown>) : {}; }
function asArray(v: unknown): Record<string, unknown>[] { return Array.isArray(v) ? (v as Record<string, unknown>[]) : []; }
function getElement(id: string): HTMLElement | null { try { return document.getElementById(id); } catch { return null; } }
function asInput(el: HTMLElement | null): HTMLInputElement | null { return el instanceof HTMLInputElement ? el : null; }
function asSelect(el: HTMLElement | null): HTMLSelectElement | null { return el instanceof HTMLSelectElement ? el : null; }

function valueOf(id: string): string {
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
function checkedOf(id: string): boolean { return Boolean(asInput(getElement(id))?.checked); }
function setChecked(id: string, value: boolean): void { const el = asInput(getElement(id)); if (el) el.checked = Boolean(value); }

function parseBoolSelect(value: unknown): boolean | null {
  const raw = normalize(value);
  if (!raw) return null;
  if (["1", "true", "yes"].includes(raw)) return true;
  if (["0", "false", "no"].includes(raw)) return false;
  return null;
}

function errorFieldFromMessage(message: string): string | null {
  const textValue = String(message || "");
  const rules: Array<[RegExp, string]> = [
    [/project/i, "project_code"],
    [/discipline/i, "discipline_code"],
    [/title/i, "title"],
    [/recipient org/i, "recipient_org_id"],
    [/response due date/i, "response_due_date"],
    [/rfi question/i, "rfi_question"],
    [/rfi answer_text/i, "rfi_answer"],
    [/rfi answered_at/i, "rfi_answered_at"],
    [/ncr kind/i, "ncr_kind"],
    [/ncr severity/i, "ncr_severity"],
    [/nonconformance/i, "ncr_nonconf"],
    [/containment/i, "ncr_containment"],
    [/rectification/i, "ncr_rectification"],
    [/verification note/i, "ncr_verification_note"],
    [/ncr verified_at/i, "ncr_verified_at"],
    [/tech subtype/i, "tech_subtype"],
    [/document_no/i, "tech_doc_no"],
    [/revision/i, "tech_revision"],
  ];
  for (const [pattern, field] of rules) {
    if (pattern.test(textValue)) return field;
  }
  return null;
}

function fieldKeyFromInputId(id: string, key: string): string | null {
  const map: Array<[string, string]> = [
    [`ci-form-project-${key}`, "project_code"],
    [`ci-form-discipline-${key}`, "discipline_code"],
    [`ci-form-title-${key}`, "title"],
    [`ci-form-recipient-org-${key}`, "recipient_org_id"],
    [`ci-form-response-due-${key}`, "response_due_date"],
    [`ci-form-rfi-question-${key}`, "rfi_question"],
    [`ci-form-rfi-answer-${key}`, "rfi_answer"],
    [`ci-form-rfi-answered-at-${key}`, "rfi_answered_at"],
    [`ci-form-ncr-kind-${key}`, "ncr_kind"],
    [`ci-form-ncr-severity-${key}`, "ncr_severity"],
    [`ci-form-ncr-nonconf-${key}`, "ncr_nonconf"],
    [`ci-form-ncr-containment-${key}`, "ncr_containment"],
    [`ci-form-ncr-rectification-${key}`, "ncr_rectification"],
    [`ci-form-ncr-verification-note-${key}`, "ncr_verification_note"],
    [`ci-form-ncr-verified-at-${key}`, "ncr_verified_at"],
    [`ci-form-tech-subtype-${key}`, "tech_subtype"],
    [`ci-form-tech-doc-no-${key}`, "tech_doc_no"],
    [`ci-form-tech-revision-${key}`, "tech_revision"],
  ];
  const found = map.find(([prefix]) => id === prefix);
  return found ? found[1] : null;
}

function clearFieldError(moduleKey: string, tabKey: string, fieldKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const form = getElement(`ci-form-wrap-${key}`);
  if (!(form instanceof HTMLElement)) return;
  const field = form.querySelector<HTMLElement>(`[data-ci-field="${fieldKey}"]`);
  if (!(field instanceof HTMLElement)) return;
  field.classList.remove("is-error");
  const errorEl = field.querySelector<HTMLElement>(".ci-field-error");
  if (errorEl) {
    errorEl.textContent = "";
    errorEl.hidden = true;
  }
  const hasErrors = form.querySelector(".module-crud-form-field.is-error");
  if (!hasErrors) {
    const summary = getElement(`ci-form-error-summary-${key}`);
    if (summary instanceof HTMLElement) {
      summary.textContent = "";
      summary.hidden = true;
    }
  }
}

function clearFormErrors(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const form = getElement(`ci-form-wrap-${key}`);
  if (!(form instanceof HTMLElement)) return;
  form.querySelectorAll<HTMLElement>(".module-crud-form-field.is-error").forEach((field) => {
    field.classList.remove("is-error");
  });
  form.querySelectorAll<HTMLElement>(".ci-field-error").forEach((el) => {
    el.textContent = "";
    el.hidden = true;
  });
  const summary = getElement(`ci-form-error-summary-${key}`);
  if (summary instanceof HTMLElement) {
    summary.textContent = "";
    summary.hidden = true;
  }
}

function renderFormErrors(moduleKey: string, tabKey: string, errors: string[]): void {
  const key = keyOf(moduleKey, tabKey);
  clearFormErrors(moduleKey, tabKey);
  const form = getElement(`ci-form-wrap-${key}`);
  if (!(form instanceof HTMLElement) || !errors.length) return;

  const summary = getElement(`ci-form-error-summary-${key}`);
  if (summary instanceof HTMLElement) {
    summary.textContent = errors[0];
    summary.hidden = false;
  }

  let firstInvalidField: HTMLElement | null = null;
  const assigned = new Set<string>();
  errors.forEach((message) => {
    const fieldKey = errorFieldFromMessage(message);
    if (!fieldKey || assigned.has(fieldKey)) return;
    const field = form.querySelector<HTMLElement>(`[data-ci-field="${fieldKey}"]`);
    if (!(field instanceof HTMLElement)) return;
    field.classList.add("is-error");
    const errorEl = field.querySelector<HTMLElement>(".ci-field-error");
    if (errorEl instanceof HTMLElement) {
      errorEl.textContent = message;
      errorEl.hidden = false;
    }
    if (!firstInvalidField) firstInvalidField = field;
    assigned.add(fieldKey);
  });

  if (!(firstInvalidField instanceof HTMLElement)) return;
  firstInvalidField.scrollIntoView({ behavior: "smooth", block: "center" });
  const focusTarget = firstInvalidField.querySelector<HTMLElement>("input,select,textarea");
  if (focusTarget instanceof HTMLElement && typeof focusTarget.focus === "function") {
    focusTarget.focus();
  }
}

function setFormSavingState(moduleKey: string, tabKey: string, saving: boolean): void {
  const key = keyOf(moduleKey, tabKey);
  const saveButton = getElement(`ci-form-save-${key}`) as HTMLButtonElement | null;
  if (!saveButton) return;
  saveButton.disabled = saving;
  saveButton.dataset.loading = saving ? "1" : "0";
  saveButton.textContent = saving ? "در حال ذخیره..." : "ذخیره";
}

function effectiveFormItemType(moduleKey: string, tabKey: string): string {
  const key = keyOf(moduleKey, tabKey);
  const itemId = Number(valueOf(`ci-form-id-${key}`) || 0);
  const currentType = upper(valueOf(`ci-form-item-type-${key}`) || itemTypeForTab(moduleKey, tabKey));
  if (itemId <= 0 && upper(itemTypeForTab(moduleKey, tabKey)) === "RFI" && checkedOf(`ci-form-rfi-as-ncr-${key}`)) {
    return "NCR";
  }
  return currentType;
}

function updateFormHeaderMeta(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const typeBadge = getElement(`ci-form-type-badge-${key}`);
  const statusBadge = getElement(`ci-form-status-badge-${key}`);
  const itemId = Number(valueOf(`ci-form-id-${key}`) || 0);
  const effectiveType = effectiveFormItemType(moduleKey, tabKey) || "RFI";
  const statusCode = upper(valueOf(`ci-form-status-${key}`));

  if (typeBadge instanceof HTMLElement) {
    typeBadge.textContent = effectiveType;
    typeBadge.className = `ci-form-badge ci-form-type-badge is-${normalize(effectiveType)}`;
  }
  if (statusBadge instanceof HTMLElement) {
    if (itemId > 0 && statusCode) {
      statusBadge.hidden = false;
      statusBadge.textContent = statusCode;
    } else {
      statusBadge.hidden = true;
      statusBadge.textContent = "";
    }
  }
}

function setDrawerHeaderMode(moduleKey: string, tabKey: string, mode: "form" | "detail"): void {
  const key = keyOf(moduleKey, tabKey);
  const meta = getElement(`ci-drawer-meta-${key}`);
  if (meta instanceof HTMLElement) {
    meta.style.display = mode === "form" ? "inline-flex" : "none";
  }
}

function ensureSectionState(key: string): Record<string, boolean> {
  if (!sectionExpandedByKey[key]) {
    sectionExpandedByKey[key] = {
      main: true,
      specific: true,
      refs: false,
      attachments: false,
      impact: false,
    };
  }
  return sectionExpandedByKey[key];
}

function setSectionExpanded(moduleKey: string, tabKey: string, section: string, expanded: boolean): void {
  const key = keyOf(moduleKey, tabKey);
  const state = ensureSectionState(key);
  state[section] = expanded;
  const body = getElement(`ci-section-body-${section}-${key}`);
  const toggle = getElement(`ci-section-toggle-${section}-${key}`);
  if (body instanceof HTMLElement) body.hidden = !expanded;
  if (toggle instanceof HTMLElement) {
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    toggle.classList.toggle("is-collapsed", !expanded);
  }
}

function applySectionState(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const state = ensureSectionState(key);
  ["main", "specific", "refs", "attachments", "impact"].forEach((section) => {
    setSectionExpanded(moduleKey, tabKey, section, Boolean(state[section]));
  });
}

function toggleSection(moduleKey: string, tabKey: string, section: string): void {
  const key = keyOf(moduleKey, tabKey);
  const state = ensureSectionState(key);
  const current = Boolean(state[section]);
  setSectionExpanded(moduleKey, tabKey, section, !current);
}

function updateTypeFilterChipState(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const selected = upper(selectedTypeFilterByKey[key] || "");
  const form = getElement(`ci-tfilters-${key}`);
  if (!(form instanceof HTMLElement)) return;
  form.querySelectorAll<HTMLElement>("[data-ci-action='filter-type']").forEach((chip) => {
    const chipType = upper(chip.dataset.ciTypeFilter || "");
    const active = chipType === selected || (!chipType && !selected);
    chip.classList.toggle("active", active);
    chip.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function filteredRowsForBoard(moduleKey: string, tabKey: string, rows: Record<string, unknown>[]): Record<string, unknown>[] {
  const key = keyOf(moduleKey, tabKey);
  const filterType = upper(selectedTypeFilterByKey[key] || "");
  if (!filterType) return rows;
  return rows.filter((row) => upper(row.item_type) === filterType);
}

function renderBoardRows(moduleKey: string, tabKey: string, deps: CommItemsUiDeps, total?: number): void {
  const key = keyOf(moduleKey, tabKey);
  const rows = asArray(boardRowsByKey[key]);
  const filteredRows = filteredRowsForBoard(moduleKey, tabKey, rows);
  const filterType = upper(selectedTypeFilterByKey[key] || "");
  const effectiveTotal = filterType ? filteredRows.length : Number(total || rows.length || 0);
  updateTypeFilterChipState(moduleKey, tabKey);
  stateBridge.renderRows(getElement(`ci-tbody-${key}`), filteredRows, deps.canEdit());
  stateBridge.renderStats(moduleKey, filteredRows, effectiveTotal);
}

function drawerFor(moduleKey: string, tabKey: string): HTMLElement | null {
  return getElement(`ci-drawer-${keyOf(moduleKey, tabKey)}`);
}

function openDrawer(moduleKey: string, tabKey: string): void {
  const drawer = drawerFor(moduleKey, tabKey);
  if (!(drawer instanceof HTMLElement)) return;
  drawer.hidden = false;
  drawer.classList.add("is-open");
  document.body.classList.add("ci-drawer-open");
}

function closeRowMenus(): void {
  document.querySelectorAll("[data-ci-row-menu].is-open").forEach((menuEl) => {
    menuEl.classList.remove("is-open");
    const trigger = menuEl.querySelector("[data-ci-action='toggle-row-menu']");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  });
}

function toggleRowMenu(triggerEl: HTMLElement | null): void {
  const menuEl = triggerEl?.closest?.("[data-ci-row-menu]");
  if (!(menuEl instanceof HTMLElement)) return;
  const shouldOpen = !menuEl.classList.contains("is-open");
  closeRowMenus();
  if (shouldOpen) {
    menuEl.classList.add("is-open");
    triggerEl?.setAttribute("aria-expanded", "true");
  }
}

function closeDrawer(moduleKey: string, tabKey: string, force = false): boolean {
  const key = keyOf(moduleKey, tabKey);
  if (!force && drawerDirtyByKey[key]) {
    const confirmed = window.confirm("Changes are not saved. Close anyway?");
    if (!confirmed) return false;
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
  const el = getElement(`ci-drawer-title-${keyOf(moduleKey, tabKey)}`);
  if (el) el.textContent = value;
}

function showFormMode(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const form = getElement(`ci-form-wrap-${key}`);
  const detail = getElement(`ci-detail-wrap-${key}`);
  if (form instanceof HTMLElement) form.hidden = false;
  if (detail instanceof HTMLElement) detail.style.display = "none";
  setDrawerHeaderMode(moduleKey, tabKey, "form");
}

function showDetailMode(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const form = getElement(`ci-form-wrap-${key}`);
  const detail = getElement(`ci-detail-wrap-${key}`);
  if (form instanceof HTMLElement) form.hidden = true;
  if (detail instanceof HTMLElement) detail.style.display = "block";
  setDrawerHeaderMode(moduleKey, tabKey, "detail");
}

function markDrawerDirty(moduleKey: string, tabKey: string, dirty = true): void {
  drawerDirtyByKey[keyOf(moduleKey, tabKey)] = dirty;
}

function ensureShamsiInputsForBoard(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  if (shamsiRegistryByKey[key]) {
    shamsiRegistryByKey[key].syncAll();
    return;
  }
  shamsiRegistryByKey[key] = initShamsiDateInputs([
    `ci-form-response-due-${key}`,
    `ci-form-rfi-answered-at-${key}`,
    `ci-form-ncr-verified-at-${key}`,
    `ci-form-tech-meeting-date-${key}`,
  ]);
  shamsiRegistryByKey[key].syncAll();
}

function attachmentSlotFor(itemType: unknown, scope: unknown): string {
  const t = upper(itemType);
  const s = upper(scope);
  if (s === "GENERAL") return "GENERAL_ATTACHMENT";
  if (t === "RFI") return s === "REFERENCE" ? "RFI_REFERENCE" : "RFI_RESPONSE";
  if (t === "NCR") return s === "REFERENCE" ? "NCR_REFERENCE" : "NCR_RESPONSE";
  return s === "REFERENCE" ? "TECH_REFERENCE" : "TECH_RESPONSE";
}

function fileKindForName(name: string): string {
  const n = String(name || "").toLowerCase();
  if (n.endsWith(".pdf")) return "pdf";
  if ([".dwg", ".dxf", ".ifc", ".xls", ".xlsx", ".zip", ".doc", ".docx"].some((x) => n.endsWith(x))) return "native";
  return "attachment";
}

function tabTitle(moduleKey: string, tabKey: string): string {
  const map: Record<string, string> = {
    "contractor:execution": "دفتر فنی و اجرا",
    "contractor:requests": "درخواست‌ها (RFI/NCR)",
    "consultant:inspection": "بازدید و IR",
    "consultant:defects": "نواقص (NCR)",
    "consultant:instructions": "دستورکار و صورتجلسه",
    "consultant:control": "کنترل پروژه",
  };
  return map[`${moduleKey}:${tabKey}`] || `${moduleKey}/${tabKey}`;
}

function itemTypeForTab(moduleKey: string, tabKey: string): string {
  return formBridge.resolveItemType({ moduleKey, tabKey });
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((row) => String(row ?? "").trim())
    .filter((row) => !!row);
}

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function textOrDash(value: unknown): string {
  const parsed = text(value);
  return parsed || "-";
}

function tabSupportsRfi(moduleKey: string, tabKey: string): boolean {
  const m = normalize(moduleKey);
  const t = normalize(tabKey);
  if (!m || !t) return false;
  if (upper(itemTypeForTab(m, t)) === "RFI") return true;
  const matchedRule = asArray(catalogCache?.tab_rules).find(
    (row) => normalize(row.module_key) === m && normalize(row.tab_key) === t
  );
  if (!matchedRule) {
    return m === "consultant" && t === "control";
  }
  const rule = asRecord(matchedRule.rule);
  return asStringArray(rule.item_types).map((row) => upper(row)).includes("RFI");
}

function findProjectName(cache: Record<string, unknown>, projectCode: unknown): string {
  const code = upper(projectCode);
  if (!code) return "-";
  const row = asArray(cache.projects).find((project) => upper(project.code || project.project_code) === code);
  return textOrDash(row?.project_name || row?.name || row?.name_p || row?.name_e || code);
}

function findDisciplineLabel(cache: Record<string, unknown>, disciplineCode: unknown): string {
  const code = upper(disciplineCode);
  if (!code) return "-";
  const row = asArray(cache.disciplines).find((discipline) => upper(discipline.code || discipline.discipline_code) === code);
  return textOrDash(row?.name || row?.name_p || row?.name_e || code);
}

function findOrganizationName(cache: Record<string, unknown>, organizationId: unknown): string {
  const id = Number(organizationId || 0);
  if (!id) return "-";
  const row = asArray(cache.organizations).find((organization) => Number(organization.id || 0) === id);
  return textOrDash(row?.name || row?.name_e || row?.name_p || row?.code);
}

function escHtml(value: unknown): string {
  return stateBridge.esc(textOrDash(value));
}

function rfiExcelHeaders(): string[] {
  return [
    "شناسه اختصاصی",
    "نام پروژه",
    "کد پروژه",
    "تاریخ صدور",
    "صادرکننده",
    "شرکت",
    "شماره قرار داد",
    "نام و نام خانوادگی",
    "سمت",
    "اطلاعات تماس",
    "ایمیل",
    "مخاطب",
    "رشته (Discipline)",
    "کد مدرک مرجع",
    "شماره شیت",
    "REV",
    "بلوک",
    "طبقه",
    "موضوع",
    "شرح موضوع",
    "طرح پیشنهاد",
    "پیوست",
    "بارگذاری مدارک",
    "ارسال",
    "پاسخ",
    "پیوست پاسخ",
    "شرح پاسخ",
    "تایید کارفرما",
    "file",
    "ارسال ایمیل",
    "ایمیل ارسال TO",
    "ایمیل ارسال CC",
    "خطای ارسال",
  ];
}

function rfiExcelRow(item: Record<string, unknown>, cache: Record<string, unknown>): string[] {
  const rfi = asRecord(item.rfi);
  const answerText = text(rfi.answer_text);
  const drawingRefs = asStringArray(rfi.drawing_refs);
  return [
    textOrDash(item.item_no),
    findProjectName(cache, item.project_code),
    textOrDash(item.project_code),
    textOrDash(formatShamsiDate(item.created_at)),
    textOrDash(item.created_by_name),
    findOrganizationName(cache, item.organization_id),
    "-",
    textOrDash(item.created_by_name),
    "-",
    "-",
    "-",
    textOrDash(item.recipient_org_name),
    findDisciplineLabel(cache, item.discipline_code),
    textOrDash(drawingRefs[0]),
    "-",
    "-",
    textOrDash(item.zone),
    "-",
    textOrDash(item.title),
    textOrDash(rfi.question_text || item.short_description),
    textOrDash(rfi.proposed_solution),
    "-",
    "-",
    textOrDash(item.status_code),
    answerText ? "ارسال شد" : "انتظار اقدام",
    "-",
    textOrDash(rfi.answer_text),
    "-",
    "-",
    "-",
    "-",
    "-",
    "-",
  ];
}

function csvEscape(value: unknown): string {
  const raw = String(value ?? "");
  if (!/[",\r\n]/.test(raw)) return raw;
  return `"${raw.replace(/"/g, '""')}"`;
}

function triggerDownload(content: Blob, fileName: string): void {
  const url = window.URL.createObjectURL(content);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

async function copyTextToClipboard(value: string): Promise<boolean> {
  const textValue = String(value || "").trim();
  if (!textValue) return false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(textValue);
      return true;
    }
  } catch {
    // fallback below
  }
  try {
    const input = document.createElement("textarea");
    input.value = textValue;
    input.setAttribute("readonly", "true");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    const ok = document.execCommand("copy");
    input.remove();
    return ok;
  } catch {
    return false;
  }
}

function buildRfiPrintHtml(item: Record<string, unknown>, cache: Record<string, unknown>): string {
  const rfi = asRecord(item.rfi);
  const drawingRefs = asStringArray(rfi.drawing_refs).join("، ");
  const specRefs = asStringArray(rfi.spec_refs).join("، ");
  const projectName = findProjectName(cache, item.project_code);
  const disciplineLabel = findDisciplineLabel(cache, item.discipline_code);
  const companyName = findOrganizationName(cache, item.organization_id);
  const issueDate = formatShamsiDate(item.created_at);
  const answeredDate = formatShamsiDate(rfi.answered_at);
  const printTime = formatShamsiDate(new Date());
  const statusLabel = String(item.status_code || "DRAFT");

  return `
<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>چاپ فرم RFI - ${stateBridge.esc(textOrDash(item.item_no))}</title>
  <style>
    @page { size: A4; margin: 7mm 7mm 10mm; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Tahoma, "Segoe UI", Arial, sans-serif; font-size: 10px; color: #111827; background: #ffffff; }
    .sheet {
      position: relative;
      min-height: calc(297mm - 17mm);
      padding: 3px 3px 8px;
      border: 1.8px solid #111827;
      display: flex;
      flex-direction: column;
    }
    .sheet-main { display: flex; flex-direction: column; min-height: 100%; flex: 1; }
    .content-stack {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
    }
    .sheet-bottom { margin-top: 3px; }
    .letterhead {
      display: grid;
      grid-template-columns: 112px 1fr 112px;
      gap: 4px;
      align-items: center;
      border: 1.5px solid #111827;
      padding: 3px 5px;
      margin-bottom: 3px;
    }
    .brand-mark {
      width: 26px;
      height: 26px;
      border-radius: 7px;
      border: 1.5px solid #1d4ed8;
      color: #1d4ed8;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 7.8px;
      font-weight: 900;
      letter-spacing: 0.04em;
      background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
      justify-self: end;
    }
    .letterhead-title { text-align: center; }
    .letterhead-title h1 { margin: 0; font-size: 12px; font-weight: 800; line-height: 1.05; }
    .letterhead-title p { margin: 1px 0 0; font-size: 6.8px; color: #374151; }
    .letterhead-side {
      font-size: 7.2px;
      line-height: 1.35;
      display: grid;
      gap: 1px;
    }
    .letterhead-side div {
      display: flex;
      justify-content: space-between;
      gap: 6px;
      border-bottom: 1px solid #d1d5db;
      padding-bottom: 1px;
    }
    .letterhead-side div:last-child { border-bottom: 0; padding-bottom: 0; }
    .letterhead-side strong { white-space: nowrap; }
    .form-table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 3px;
    }
    .form-table td {
      border: 1.2px solid #111827;
      padding: 2px 4px;
      vertical-align: top;
      text-align: right;
    }
    .form-table.compact td { padding: 2px 3px; }
    .cell-label {
      display: inline-block;
      font-size: 7px;
      font-weight: 700;
      color: #111827;
      margin-left: 4px;
      white-space: nowrap;
    }
    .cell-value {
      font-size: 7.9px;
      line-height: 1.35;
      color: #111827;
      word-break: break-word;
    }
    .cell-value.block { display: block; min-height: 11px; }
    .muted {
      color: #4b5563;
      font-size: 6.9px;
    }
    .ref-strip {
      border: 1.2px solid #111827;
      padding: 2px 5px;
      margin-bottom: 3px;
      font-size: 7px;
      line-height: 1.5;
      display: flex;
      flex-wrap: wrap;
      gap: 4px 12px;
    }
    .ref-strip strong { color: #111827; }
    .section-box {
      border: 1.2px solid #111827;
      margin-bottom: 3px;
    }
    .section-box.question-section,
    .section-box.proposal-section,
    .section-box.answer-section {
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .section-box.question-section { flex: 1.35; }
    .section-box.proposal-section { flex: 1.2; }
    .section-box.answer-section { flex: 0.6; margin-bottom: 0; }
    .section-box.answer-section {
      min-height: 0;
    }
    .section-title {
      background: #ffffff;
      padding: 2px 5px;
      font-weight: 800;
      font-size: 8.6px;
      border-bottom: 1.2px solid #111827;
    }
    .section-content {
      padding: 4px 6px;
      line-height: 1.55;
      font-size: 8.8px;
      white-space: pre-wrap;
      word-break: break-word;
      min-height: 38px;
    }
    .section-content.subject-box { min-height: 26px; }
    .section-content.question-box { min-height: 210px; }
    .section-content.proposal-box { min-height: 195px; }
    .section-content.answer-box { min-height: 54px; }
    .question-section .section-content.question-box { flex: 1; min-height: 210px; }
    .proposal-section .section-content.proposal-box { flex: 1; min-height: 195px; }
    .answer-section .section-content.answer-box { flex: 1; min-height: 54px; }
    .lined-box {
      background-image: linear-gradient(to bottom, transparent 0, transparent 21px, rgba(17,24,39,0.08) 22px);
      background-size: 100% 22px;
    }
    .response-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 4px;
      align-items: center;
      padding: 3px 6px 4px;
    }
    .response-choices {
      display: flex;
      flex-wrap: wrap;
      gap: 4px 10px;
      font-size: 7.8px;
      font-weight: 700;
    }
    .response-choice {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      white-space: nowrap;
    }
    .check-box {
      display: inline-block;
      width: 10px;
      height: 10px;
      border: 1.2px solid #334155;
      vertical-align: middle;
    }
    .disclaimer-note {
      background: #fefce8;
      border: 1.2px solid #ca8a04;
      padding: 3px 5px;
      margin: 3px;
      font-size: 7.3px;
      line-height: 1.45;
      color: #713f12;
    }
    .print-section { margin-bottom: 3px; break-inside: auto; }
    .print-section-head { margin-bottom: 2px; }
    .print-section-head h3 { margin: 0; font-size: 8.4px; font-weight: 800; }
    .print-section-head p { margin: 0; font-size: 6.8px; color: #4b5563; }
    .signature-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 3px;
      margin-top: 2px;
    }
    .signature-card {
      border: 1.2px solid #111827;
      min-height: 56px;
      padding: 3px 5px;
      break-inside: avoid;
      position: relative;
    }
    .signature-card h4 { margin: 0 0 2px; font-size: 7.5px; }
    .signature-card .name { font-weight: 700; min-height: 11px; line-height: 1.2; font-size: 7.5px; }
    .signature-card .date { color: #4b5563; margin-top: 2px; font-size: 6.8px; }
    .signature-card .line { margin-top: 10px; border-top: 1px dashed #64748b; padding-top: 2px; font-size: 6.8px; color: #64748b; }
    .logo-stamp-placeholder {
      position: absolute;
      top: 3px;
      left: 3px;
      width: 24px;
      height: 24px;
      border: 1px dashed #cbd5e1;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 5.5px;
      color: #cbd5e1;
      background: #f8fafc;
    }
    .print-footer {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 7px;
      color: #475569;
      border-top: 1px solid #9ca3af;
      padding-top: 1px;
      background: #ffffff;
    }
    .print-page-number::after { content: counter(page); }
  </style>
</head>
<body>
  <div class="sheet">
    <div class="sheet-main">
    <header class="letterhead">
      <div class="letterhead-side">
        <div><strong>پروژه</strong><span>${escHtml(projectName)}</span></div>
        <div><strong>شرکت</strong><span>${escHtml(companyName)}</span></div>
        <div><strong>رشته</strong><span>${escHtml(disciplineLabel)}</span></div>
      </div>
      <div class="letterhead-title">
        <h1>درخواست اطلاعات فنی (RFI)</h1>
        <p>نسخه رسمی برای ثبت، بررسی، پاسخ و بایگانی</p>
      </div>
      <div class="letterhead-side">
        <div><strong>شماره</strong><span>${escHtml(textOrDash(item.item_no))}</span></div>
        <div><strong>تاریخ</strong><span>${escHtml(issueDate)}</span></div>
        <div><strong>وضعیت</strong><span>${escHtml(statusLabel)}</span></div>
      </div>
    </header>

    <table class="form-table compact">
      <tr>
        <td style="width:16.5%;">
          <span class="cell-label">تاریخ صدور:</span>
          <span class="cell-value">${escHtml(issueDate)}</span>
        </td>
        <td style="width:16.5%;">
          <span class="cell-label">شماره مدرک:</span>
          <span class="cell-value">${escHtml(textOrDash(item.item_no))}</span>
        </td>
        <td style="width:34%;">
          <span class="cell-label">عنوان مدرک:</span>
          <span class="cell-value">${escHtml(textOrDash(item.title))}</span>
        </td>
        <td style="width:16.5%;">
          <span class="cell-label">کارفرما:</span>
          <span class="cell-value">${escHtml(companyName)}</span>
        </td>
        <td style="width:16.5%;">
          <span class="cell-label">کد پروژه:</span>
          <span class="cell-value">${escHtml(textOrDash(item.project_code))}</span>
        </td>
      </tr>
    </table>

    <table class="form-table compact">
      <tr>
        <td style="width:21%;">
          <span class="cell-label">درخواست‌کننده:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.created_by_name))}</span>
        </td>
        <td style="width:21%;">
          <span class="cell-label">شرکت / واحد:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.sender_org_name || companyName))}</span>
        </td>
        <td style="width:18%;">
          <span class="cell-label">سمت:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.created_by_title || "-"))}</span>
        </td>
        <td style="width:20%;">
          <span class="cell-label">مخاطب:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.recipient_org_name))}</span>
        </td>
        <td style="width:20%;">
          <span class="cell-label">پیوست:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.attachment_count))}</span>
        </td>
      </tr>
      <tr>
        <td>
          <span class="cell-label">شماره تماس:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.created_by_phone || "-"))}</span>
        </td>
        <td>
          <span class="cell-label">ایمیل:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.created_by_email || "-"))}</span>
        </td>
        <td>
          <span class="cell-label">رشته:</span>
          <span class="cell-value block">${escHtml(disciplineLabel)}</span>
        </td>
        <td colspan="2">
          <span class="cell-label">وضعیت / اولویت:</span>
          <span class="cell-value block">${escHtml(statusLabel)} / ${escHtml(textOrDash(item.priority_code || item.priority))}</span>
        </td>
      </tr>
    </table>

    <table class="form-table compact">
      <tr>
        <td style="width:28%;">
          <span class="cell-label">شماره نقشه مرجع:</span>
          <span class="cell-value block">${escHtml(drawingRefs || "------------")}</span>
        </td>
        <td style="width:18%;">
          <span class="cell-label">بلوک:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.block || item.zone || "-"))}</span>
        </td>
        <td style="width:18%;">
          <span class="cell-label">طبقه:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.level_code || "-"))}</span>
        </td>
        <td style="width:18%;">
          <span class="cell-label">پکیج:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.package_code || "-"))}</span>
        </td>
        <td style="width:18%;">
          <span class="cell-label">مرجع مرتبط:</span>
          <span class="cell-value block">${escHtml(textOrDash(item.reference_no || item.related_item_no || specRefs || "-"))}</span>
        </td>
      </tr>
    </table>

    <section class="section-box">
      <div class="section-title">موضوع</div>
      <div class="section-content subject-box">${escHtml(textOrDash(item.title))}</div>
    </section>

    <div class="content-stack">
      <section class="section-box question-section">
        <div class="section-title">شرح موضوع و سوال فنی</div>
        <div class="section-content question-box lined-box">${escHtml(textOrDash(rfi.question_text || item.short_description))}</div>
      </section>

      <section class="section-box proposal-section">
        <div class="section-title">طرح پیشنهادی</div>
        <div class="section-content proposal-box lined-box">${escHtml(textOrDash(rfi.proposed_solution))}</div>
      </section>

      <section class="section-box answer-section">
        <div class="section-title">پاسخ و نتیجه بررسی</div>
        <div class="section-content answer-box lined-box">${escHtml(textOrDash(rfi.answer_text))}</div>
        <div class="response-row">
          <div class="response-choices">
            <span class="response-choice"><span class="check-box"></span>تایید</span>
            <span class="response-choice"><span class="check-box"></span>اصلاح</span>
            <span class="response-choice"><span class="check-box"></span>مردود</span>
          </div>
          <div style="font-size: 7.6px;"><strong>تاریخ پاسخ:</strong> ${escHtml(answeredDate)}</div>
        </div>
      </section>
    </div>

    <div class="sheet-bottom">
    <section class="section-box">
      <div class="section-title">توضیح</div>
      <div class="disclaimer-note">
        هدف از این فرم صرفاً رفع ابهامات فنی و پاسخ به سوالات جاری پروژه است.
        در صورت وجود هرگونه اثر مالی، زمانی یا تغییر در محدوده کار، اجرای عملیات منوط به اخذ تایید کتبی کارفرما پیش از اجرا خواهد بود.
      </div>
    </section>

    <section class="print-section">
      <div class="print-section-head">
        <h3>ثبت / ارسال / تایید</h3>
        <p>این بخش برای امضا، مهر و بایگانی نسخه چاپی است</p>
      </div>
      <div class="signature-grid">
        <div class="signature-card">
          <div class="logo-stamp-placeholder">لوگو</div>
          <h4>1. درخواست‌کننده</h4>
          <div class="name">${escHtml(textOrDash(item.created_by_name))}</div>
          <div class="date">تاریخ: ${escHtml(issueDate)}</div>
          <div class="line">مهر / امضا</div>
        </div>
        <div class="signature-card">
          <div class="logo-stamp-placeholder">لوگو</div>
          <h4>2. پاسخ‌دهنده</h4>
          <div class="name">${escHtml(textOrDash(item.recipient_org_name))}</div>
          <div class="date">تاریخ: ${escHtml(answeredDate)}</div>
          <div class="line">مهر / امضا</div>
        </div>
        <div class="signature-card">
          <div class="logo-stamp-placeholder">مهر</div>
          <h4>3. کارفرما</h4>
          <div class="name">-</div>
          <div class="date">تاریخ: -</div>
          <div class="line">مهر / امضا</div>
        </div>
      </div>
    </section>
    </div>
    </div>
  </div>

  <div class="print-footer">
    <span>EDMS RFI Form</span>
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

function typeSectionsHtml(key: string, defaultTechSubtype: string): string {
  const subtypes = asArray(catalogCache?.tech_subtypes)
    .map((row) => {
      const code = upper(row.code);
      const selected = code === upper(defaultTechSubtype) ? " selected" : "";
      return `<option value="${stateBridge.esc(code)}"${selected}>${stateBridge.esc(row.label || code)}</option>`;
    })
    .join("") || `<option value="${stateBridge.esc(defaultTechSubtype)}">${stateBridge.esc(defaultTechSubtype)}</option>`;

  const reviewResults = ['<option value="">(none)</option>']
    .concat(
      asArray(catalogCache?.review_results).map((row) => {
        const code = upper(row.code);
        return `<option value="${stateBridge.esc(code)}">${stateBridge.esc(row.label || code)}</option>`;
      })
    )
    .join("");

  return `
    <div data-ci-type="RFI" class="ci-type-section">
      <div class="ci-type-section-title">RFI</div>
      <div class="module-crud-form-grid">
        <div class="module-crud-form-field span-2" data-ci-field="rfi_question">
          <label>متن سوال</label>
          <textarea id="ci-form-rfi-question-${key}" class="module-crud-textarea" placeholder="متن سوال"></textarea>
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field span-2">
          <label>پیشنهاد فنی</label>
          <textarea id="ci-form-rfi-proposed-${key}" class="module-crud-textarea" placeholder="پیشنهاد فنی"></textarea>
        </div>
        <div class="module-crud-form-field span-2" data-ci-field="rfi_answer">
          <label>متن پاسخ</label>
          <textarea id="ci-form-rfi-answer-${key}" class="module-crud-textarea" placeholder="متن پاسخ"></textarea>
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field" data-ci-field="rfi_answered_at">
          <label>تاریخ پاسخ</label>
          <input id="ci-form-rfi-answered-at-${key}" class="module-crud-input" type="date">
          <div class="ci-field-error" hidden></div>
        </div>
      </div>
    </div>
    <div data-ci-type="NCR" class="ci-type-section" style="display:none;">
      <div class="ci-type-section-title">NCR</div>
      <div class="module-crud-form-grid">
        <div class="module-crud-form-field" data-ci-field="ncr_kind">
          <label>نوع NCR</label>
          <input id="ci-form-ncr-kind-${key}" class="module-crud-input" placeholder="NCR">
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field" data-ci-field="ncr_severity">
          <label>شدت</label>
          <input id="ci-form-ncr-severity-${key}" class="module-crud-input" placeholder="MINOR / MAJOR">
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field span-2" data-ci-field="ncr_nonconf">
          <label>شرح عدم انطباق</label>
          <textarea id="ci-form-ncr-nonconf-${key}" class="module-crud-textarea" placeholder="شرح عدم انطباق"></textarea>
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field span-2" data-ci-field="ncr_containment">
          <label>اقدام فوری</label>
          <textarea id="ci-form-ncr-containment-${key}" class="module-crud-textarea" placeholder="اقدام فوری"></textarea>
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field span-2" data-ci-field="ncr_rectification">
          <label>روش اصلاح</label>
          <textarea id="ci-form-ncr-rectification-${key}" class="module-crud-textarea" placeholder="روش اصلاح"></textarea>
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field span-2" data-ci-field="ncr_verification_note">
          <label>یادداشت تایید</label>
          <textarea id="ci-form-ncr-verification-note-${key}" class="module-crud-textarea" placeholder="یادداشت تایید"></textarea>
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field" data-ci-field="ncr_verified_at">
          <label>تاریخ تایید</label>
          <input id="ci-form-ncr-verified-at-${key}" class="module-crud-input" type="date">
          <div class="ci-field-error" hidden></div>
        </div>
      </div>
    </div>
    <div data-ci-type="TECH" class="ci-type-section" style="display:none;">
      <div class="ci-type-section-title">TECH</div>
      <div class="module-crud-form-grid">
        <div class="module-crud-form-field" data-ci-field="tech_subtype">
          <label>زیرنوع</label>
          <select id="ci-form-tech-subtype-${key}" class="module-crud-select">${subtypes}</select>
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field">
          <label>عنوان سند</label>
          <input id="ci-form-tech-document-title-${key}" class="module-crud-input" placeholder="عنوان سند">
        </div>
        <div class="module-crud-form-field" data-ci-field="tech_doc_no">
          <label>شماره سند</label>
          <input id="ci-form-tech-doc-no-${key}" class="module-crud-input" placeholder="شماره سند">
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field" data-ci-field="tech_revision">
          <label>Revision</label>
          <input id="ci-form-tech-revision-${key}" class="module-crud-input" placeholder="Revision">
          <div class="ci-field-error" hidden></div>
        </div>
        <div class="module-crud-form-field">
          <label>شماره ترنسمیتال</label>
          <input id="ci-form-tech-transmittal-no-${key}" class="module-crud-input" placeholder="شماره ترنسمیتال">
        </div>
        <div class="module-crud-form-field">
          <label>شماره سابمیتال</label>
          <input id="ci-form-tech-submission-no-${key}" class="module-crud-input" placeholder="شماره سابمیتال">
        </div>
        <div class="module-crud-form-field">
          <label>نتیجه بررسی</label>
          <select id="ci-form-tech-review-result-${key}" class="module-crud-select">${reviewResults}</select>
        </div>
        <div class="module-crud-form-field span-2">
          <label>یادداشت بررسی</label>
          <textarea id="ci-form-tech-review-note-${key}" class="module-crud-textarea" placeholder="یادداشت بررسی"></textarea>
        </div>
        <div class="module-crud-form-field">
          <label>تاریخ جلسه</label>
          <input id="ci-form-tech-meeting-date-${key}" class="module-crud-input" type="date">
        </div>
      </div>
    </div>
  `;
}

function buildBoardCard(moduleKey: string, tabKey: string, cache: Record<string, unknown>, canEdit: boolean): string {
  const key = keyOf(moduleKey, tabKey);
  const defaults = formBridge.defaultValues(moduleKey, tabKey, itemTypeForTab(moduleKey, tabKey));
  const title = tabTitle(moduleKey, tabKey);
  const impactLabel = "اثرات احتمالی";
  const projects = asArray(cache.projects);
  const disciplines = asArray(cache.disciplines);
  const projectHtml = [`<option value="">همه پروژه‌ها</option>`]
    .concat(projects.map((row) => `<option value="${stateBridge.esc(row.code || row.project_code || "")}">${stateBridge.esc(row.code || row.project_code || "")}</option>`))
    .join("");
  const disciplineHtml = [`<option value="">همه دیسیپلین‌ها</option>`]
    .concat(disciplines.map((row) => `<option value="${stateBridge.esc(row.code || row.discipline_code || "")}">${stateBridge.esc(row.code || row.discipline_code || "")}</option>`))
    .join("");
  const quickTypeLabels: Record<string, string> = { RFI: "RFI", NCR: "NCR", TECH: "TECH" };
  const quickTypes = Array.from(new Set(itemTypesForTab(moduleKey, tabKey).map((row) => upper(row)))).filter((row) => !!row);
  const quickTypeButtons = [{ value: "", label: "همه" }]
    .concat(quickTypes.map((row) => ({ value: row, label: quickTypeLabels[row] || row })))
    .map((row) => {
      const active = row.value === "" ? " active" : "";
      return `<button type="button" class="ci-type-chip${active}" data-ci-action="filter-type" data-ci-type-filter="${stateBridge.esc(row.value)}" aria-pressed="${row.value === "" ? "true" : "false"}">${stateBridge.esc(row.label)}</button>`;
    })
    .join("");

  return `
    <div class="archive-card comm-items-card" data-module="${moduleKey}" data-tab="${tabKey}">
      <div class="module-panel-header">
        <h3 class="archive-title"><span class="material-icons-round">assignment</span>${stateBridge.esc(title)}</h3>
        <p class="archive-subtitle">ثبت و پیگیری مکاتبات فنی با ساختار یکپارچه.</p>
      </div>
      <div class="module-crud-toolbar ci-toolbar">
        <div class="ci-toolbar-top">
          <div class="module-crud-toolbar-left">
            ${canEdit ? `<button type="button" class="btn btn-primary" data-ci-action="open-form">افزودن آیتم</button>` : ""}
            ${tabSupportsRfi(moduleKey, tabKey) ? `<button type="button" class="btn btn-secondary" data-ci-action="export-rfi-excel">خروجی اکسل RFI</button>` : ""}
            <button type="button" class="btn-archive-icon" data-ci-action="refresh"><span class="material-icons-round">refresh</span></button>
          </div>
          <div id="ci-tfilters-${key}" class="ci-type-filters" aria-label="فیلتر سریع نوع">
            ${quickTypeButtons}
          </div>
        </div>
        <div class="ci-toolbar-bottom">
          <div class="module-crud-toolbar-right ci-toolbar-filters">
            <select id="ci-filter-project-${key}" class="module-crud-select" data-ci-action="filter-project">${projectHtml}</select>
            <select id="ci-filter-discipline-${key}" class="module-crud-select" data-ci-action="filter-discipline">${disciplineHtml}</select>
            <select id="ci-filter-status-${key}" class="module-crud-select" data-ci-action="filter-status"><option value="">همه وضعیت‌ها</option></select>
            <select id="ci-filter-ref-${key}" class="module-crud-select" data-ci-action="filter-ref"><option value="">پیوست ارجاع</option><option value="true">دارد</option><option value="false">ندارد</option></select>
            <select id="ci-filter-resp-${key}" class="module-crud-select" data-ci-action="filter-resp"><option value="">پیوست پاسخ</option><option value="true">دارد</option><option value="false">ندارد</option></select>
            <select id="ci-filter-atype-${key}" class="module-crud-select" data-ci-action="filter-atype"><option value="">نوع فایل</option><option value="pdf">PDF</option><option value="image">Image</option><option value="sheet">Sheet</option><option value="cad">CAD</option><option value="model">Model</option><option value="archive">Archive</option></select>
            <input id="ci-filter-search-${key}" class="module-crud-input" type="text" placeholder="جستجو" data-ci-action="filter-search">
          </div>
        </div>
      </div>

      <div class="module-crud-table-wrap">
        <table class="module-crud-table">
          <thead><tr><th>#</th><th>شماره</th><th>عنوان</th><th>نوع</th><th>وضعیت</th><th>اولویت</th><th>سررسید</th><th>تاخیر</th><th>SLA</th><th>عملیات</th></tr></thead>
          <tbody id="ci-tbody-${key}"></tbody>
        </table>
      </div>

      <div id="ci-drawer-${key}" class="ci-drawer" hidden>
        <div class="ci-drawer-backdrop" data-ci-action="drawer-close"></div>
        <aside class="ci-drawer-panel" role="dialog" aria-modal="true" aria-label="Communication Item Drawer">
          <header class="ci-drawer-header">
            <div class="ci-drawer-header-main">
              <div id="ci-drawer-title-${key}" class="ci-drawer-title">فرم درخواست</div>
              ${formModeSwitchHtml(key)}
              <div id="ci-drawer-meta-${key}" class="ci-drawer-meta">
                <span id="ci-form-type-badge-${key}" class="ci-form-badge ci-form-type-badge is-${normalize(defaults.itemType)}">${stateBridge.esc(defaults.itemType)}</span>
                <span id="ci-form-status-badge-${key}" class="ci-form-badge ci-form-status-badge" hidden></span>
              </div>
            </div>
            <button type="button" class="btn-archive-icon" data-ci-action="drawer-close"><span class="material-icons-round">close</span></button>
          </header>
          <div class="ci-drawer-body">
            <div id="ci-form-wrap-${key}" class="module-crud-form-wrap" hidden>
              <input id="ci-form-id-${key}" type="hidden" value="">
              <input id="ci-form-item-type-${key}" type="hidden" value="${stateBridge.esc(defaults.itemType)}">
              <input id="ci-form-tech-subtype-default-${key}" type="hidden" value="${stateBridge.esc(defaults.techSubtypeCode)}">

              <div id="ci-form-error-summary-${key}" class="ci-form-error-summary" hidden></div>

              <section class="ci-form-section" data-ci-section="main">
                <button type="button" id="ci-section-toggle-main-${key}" class="ci-section-toggle" data-ci-action="toggle-section" data-ci-section="main" aria-expanded="true">
                  <span>اطلاعات اصلی</span>
                  <span class="material-icons-round">expand_more</span>
                </button>
                <div id="ci-section-body-main-${key}" class="ci-form-section-body">
                  <div class="module-crud-form-grid">
                    <div class="module-crud-form-field" data-ci-field="project_code">
                      <label>پروژه</label>
                      <select id="ci-form-project-${key}" class="module-crud-select">${projectHtml.replace("همه پروژه‌ها", "پروژه")}</select>
                      <div class="ci-field-error" hidden></div>
                    </div>
                    <div class="module-crud-form-field" data-ci-field="discipline_code">
                      <label>دیسپلین</label>
                      <select id="ci-form-discipline-${key}" class="module-crud-select">${disciplineHtml.replace("همه دیسیپلین‌ها", "دیسپلین")}</select>
                      <div class="ci-field-error" hidden></div>
                    </div>
                    <div class="module-crud-form-field span-2" data-ci-field="title">
                      <label>عنوان</label>
                      <input id="ci-form-title-${key}" class="module-crud-input" placeholder="عنوان درخواست">
                      <div class="ci-field-error" hidden></div>
                    </div>
                    <div class="module-crud-form-field">
                      <label>اولویت</label>
                      <select id="ci-form-priority-${key}" class="module-crud-select"><option value="LOW">LOW</option><option value="NORMAL" selected>NORMAL</option><option value="HIGH">HIGH</option><option value="URGENT">URGENT</option></select>
                    </div>
                    <div class="module-crud-form-field">
                      <label>وضعیت</label>
                      <select id="ci-form-status-${key}" class="module-crud-select"><option value="${stateBridge.esc(defaults.statusCode)}">${stateBridge.esc(defaults.statusCode)}</option></select>
                    </div>
                    <div class="module-crud-form-field" data-ci-field="recipient_org_id">
                      <label>گیرنده (شناسه سازمان)</label>
                      <input id="ci-form-recipient-org-${key}" class="module-crud-input" type="number" min="1" placeholder="مثال: 12">
                      <div class="ci-field-error" hidden></div>
                    </div>
                    <div class="module-crud-form-field" data-ci-field="response_due_date">
                      <label>سررسید</label>
                      <input id="ci-form-response-due-${key}" class="module-crud-input" type="date">
                      <div class="ci-field-error" hidden></div>
                    </div>
                    <div class="module-crud-form-field span-2">
                      <label>شرح کوتاه</label>
                      <textarea id="ci-form-short-desc-${key}" class="module-crud-textarea" placeholder="شرح کوتاه درخواست"></textarea>
                    </div>
                  </div>
                </div>
              </section>

              <section class="ci-form-section" data-ci-section="specific">
                <button type="button" id="ci-section-toggle-specific-${key}" class="ci-section-toggle" data-ci-action="toggle-section" data-ci-section="specific" aria-expanded="true">
                  <span>فیلدهای اختصاصی فرم</span>
                  <span class="material-icons-round">expand_more</span>
                </button>
                <div id="ci-section-body-specific-${key}" class="ci-form-section-body">
                  ${typeSectionsHtml(key, defaults.techSubtypeCode)}
                </div>
              </section>

              <section class="ci-form-section" data-ci-section="refs">
                <button type="button" id="ci-section-toggle-refs-${key}" class="ci-section-toggle" data-ci-action="toggle-section" data-ci-section="refs" aria-expanded="false">
                  <span>ارجاعات</span>
                  <span class="material-icons-round">expand_more</span>
                </button>
                <div id="ci-section-body-refs-${key}" class="ci-form-section-body" hidden>
                  <div class="module-crud-form-grid">
                    <div class="module-crud-form-field" data-ci-type="RFI" style="display:none;">
                      <label>ارجاع نقشه‌ها</label>
                      <input id="ci-form-rfi-drawing-refs-${key}" class="module-crud-input" placeholder="با کاما جدا کنید">
                    </div>
                    <div class="module-crud-form-field" data-ci-type="RFI" style="display:none;">
                      <label>ارجاع Spec</label>
                      <input id="ci-form-rfi-spec-refs-${key}" class="module-crud-input" placeholder="با کاما جدا کنید">
                    </div>
                    <div class="module-crud-form-field">
                      <label>بند Spec عمومی</label>
                      <input id="ci-form-spec-clause-${key}" class="module-crud-input" placeholder="بند Spec">
                    </div>
                    <div class="module-crud-form-field">
                      <label>WBS</label>
                      <input id="ci-form-wbs-${key}" class="module-crud-input" placeholder="WBS">
                    </div>
                    <div class="module-crud-form-field">
                      <label>Activity</label>
                      <input id="ci-form-activity-${key}" class="module-crud-input" placeholder="Activity">
                    </div>
                  </div>
                </div>
              </section>

              <section class="ci-form-section" data-ci-section="attachments">
                <button type="button" id="ci-section-toggle-attachments-${key}" class="ci-section-toggle" data-ci-action="toggle-section" data-ci-section="attachments" aria-expanded="false">
                  <span>پیوست‌ها</span>
                  <span class="material-icons-round">expand_more</span>
                </button>
                <div id="ci-section-body-attachments-${key}" class="ci-form-section-body" hidden>
                  <div class="ci-attachments-hint">بعد از ذخیره آیتم فعال می‌شود.</div>
                </div>
              </section>

              <section class="ci-form-section" data-ci-section="impact">
                <button type="button" id="ci-section-toggle-impact-${key}" class="ci-section-toggle" data-ci-action="toggle-section" data-ci-section="impact" aria-expanded="false">
                  <span>${stateBridge.esc(impactLabel)}</span>
                  <span class="material-icons-round">expand_more</span>
                </button>
                <div id="ci-section-body-impact-${key}" class="ci-form-section-body" hidden>
                  <div class="ci-impact-lite">
                    <label><input type="checkbox" id="ci-form-impact-time-${key}"> تاثیر زمانی</label>
                    <label><input type="checkbox" id="ci-form-impact-cost-${key}"> تاثیر هزینه‌ای</label>
                  </div>
                </div>
              </section>

              <div class="module-crud-form-actions is-sticky">
                <button type="button" class="btn btn-secondary" data-ci-action="close-form">انصراف</button>
                <button type="button" id="ci-form-save-${key}" class="btn btn-primary" data-ci-action="save-form">ذخیره</button>
              </div>
            </div>

            <div id="ci-detail-wrap-${key}" class="archive-card ci-detail-wrap" style="display:none;"></div>
          </div>
        </aside>
      </div>
    </div>
  `;
}
async function ensureCatalog(deps: CommItemsUiDeps): Promise<boolean> {
  if (catalogCache) return true;
  const payload = await dataBridge.catalog({ fetch: deps.fetch });
  catalogCache = payload;
  transitionMap = workflowBridge.buildMap(asArray(payload.workflow_transitions) as any);
  return true;
}

function statusOptionsForItemType(itemType: string): { value: string; label: string }[] {
  const rows = asArray(asRecord(catalogCache?.workflow_statuses)[upper(itemType)]);
  return rows.map((r) => ({ value: String(r.code || ""), label: String(r.label || r.code || "") }));
}

function itemTypesForTab(moduleKey: string, tabKey: string): string[] {
  const m = normalize(moduleKey);
  const t = normalize(tabKey);
  if (!m || !t) return [upper(itemTypeForTab(moduleKey, tabKey))];
  const matchedRule = asArray(catalogCache?.tab_rules).find(
    (row) => normalize(row.module_key) === m && normalize(row.tab_key) === t
  );
  if (!matchedRule) return [upper(itemTypeForTab(moduleKey, tabKey))];
  const rule = asRecord(matchedRule.rule);
  const mapped = asStringArray(rule.item_types).map((row) => upper(row)).filter((row) => !!row);
  if (!mapped.length) return [upper(itemTypeForTab(moduleKey, tabKey))];
  return Array.from(new Set(mapped));
}

function statusOptionsFor(moduleKey: string, tabKey: string, itemTypeOverride?: string): { value: string; label: string }[] {
  return statusOptionsForItemType(upper(itemTypeOverride || itemTypeForTab(moduleKey, tabKey)));
}

function populateStatusOptions(moduleKey: string, tabKey: string, formItemType?: string): void {
  const key = keyOf(moduleKey, tabKey);
  const filterTypes = itemTypesForTab(moduleKey, tabKey);
  const filterSeen = new Set<string>();
  const filterOptions: { value: string; label: string }[] = [];
  filterTypes.forEach((itemType) => {
    statusOptionsForItemType(itemType).forEach((row) => {
      if (filterSeen.has(row.value)) return;
      filterSeen.add(row.value);
      filterOptions.push(row);
    });
  });
  const filter = asSelect(getElement(`ci-filter-status-${key}`));
  if (filter && filter.options.length <= 1) {
    filterOptions.forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o.value;
      opt.textContent = o.label;
      filter.appendChild(opt);
    });
  }

  const formStatus = asSelect(getElement(`ci-form-status-${key}`));
  const options = statusOptionsFor(moduleKey, tabKey, formItemType || valueOf(`ci-form-item-type-${key}`));
  if (formStatus && options.length) {
    const current = valueOf(`ci-form-status-${key}`);
    formStatus.innerHTML = "";
    options.forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o.value;
      opt.textContent = o.label;
      formStatus.appendChild(opt);
    });
    const keep = options.find((o) => o.value === current)?.value;
    formStatus.value = keep || options[0].value;
  }
}

function applyTypeVisibility(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const defaultTabType = upper(itemTypeForTab(moduleKey, tabKey));
  const itemId = Number(valueOf(`ci-form-id-${key}`) || 0);
  const createMode = itemId <= 0;
  const rfiAsNcr = createMode && defaultTabType === "RFI" && checkedOf(`ci-form-rfi-as-ncr-${key}`);
  const rfiAsNcrInput = asInput(getElement(`ci-form-rfi-as-ncr-${key}`));
  const rfiAsNcrNote = getElement(`ci-form-rfi-as-ncr-note-${key}`);
  const modeSwitch = getElement(`ci-drawer-mode-switch-${key}`);
  const rfiModeBtn = getElement(`ci-form-mode-rfi-${key}`);
  const ncrModeBtn = getElement(`ci-form-mode-ncr-${key}`);
  const canToggleMode = createMode && defaultTabType === "RFI";
  if (rfiAsNcrInput) rfiAsNcrInput.disabled = !(createMode && defaultTabType === "RFI");
  if (rfiAsNcrNote instanceof HTMLElement) {
    rfiAsNcrNote.hidden = !rfiAsNcr;
  }
  if (modeSwitch instanceof HTMLElement) {
    modeSwitch.hidden = !canToggleMode;
  }
  if (rfiModeBtn instanceof HTMLButtonElement) {
    rfiModeBtn.disabled = !canToggleMode;
    rfiModeBtn.classList.toggle("active", !rfiAsNcr);
    rfiModeBtn.setAttribute("aria-pressed", !rfiAsNcr ? "true" : "false");
  }
  if (ncrModeBtn instanceof HTMLButtonElement) {
    ncrModeBtn.disabled = !canToggleMode;
    ncrModeBtn.classList.toggle("active", rfiAsNcr);
    ncrModeBtn.setAttribute("aria-pressed", rfiAsNcr ? "true" : "false");
  }
  if (createMode && defaultTabType === "RFI") {
    setValue(`ci-form-item-type-${key}`, rfiAsNcr ? "NCR" : "RFI");
  }
  const itemType = upper(valueOf(`ci-form-item-type-${key}`) || defaultTabType);
  const effectiveType = rfiAsNcr ? "NCR" : itemType;
  populateStatusOptions(moduleKey, tabKey, effectiveType);
  const card = getElement(`ci-form-wrap-${key}`)?.closest(".comm-items-card") as HTMLElement | null;
  if (!card) return;
  card.querySelectorAll<HTMLElement>("[data-ci-type]").forEach((el) => {
    const sectionType = upper(el.dataset.ciType);
    el.style.display = sectionType === effectiveType ? "block" : "none";
  });
  updateFormHeaderMeta(moduleKey, tabKey);
}

function ensureBoards(moduleKey: string, deps: CommItemsUiDeps): boolean {
  const roots = document.querySelectorAll(`.comm-items-root[data-module="${normalize(moduleKey)}"][data-tab]`);
  if (!roots.length) return false;
  roots.forEach((root) => {
    const moduleValue = normalize(root.getAttribute("data-module"));
    const tabValue = normalize(root.getAttribute("data-tab"));
    const key = keyOf(moduleValue, tabValue);
    if (!root.innerHTML.trim()) {
      root.innerHTML = buildBoardCard(moduleValue, tabValue, deps.cache || {}, deps.canEdit());
    }
    populateStatusOptions(moduleValue, tabValue);
    applyTypeVisibility(moduleValue, tabValue);
    applySectionState(moduleValue, tabValue);
    drawerDirtyByKey[key] = false;
    ensureShamsiInputsForBoard(moduleValue, tabValue);
    if (!selectedItemTypeByKey[key]) selectedItemTypeByKey[key] = itemTypeForTab(moduleValue, tabValue);
    if (typeof selectedTypeFilterByKey[key] === "undefined") selectedTypeFilterByKey[key] = "";
    updateTypeFilterChipState(moduleValue, tabValue);
  });
  return true;
}

function hasBoardRoot(moduleKey: string, tabKey: string): boolean {
  const moduleValue = normalize(moduleKey);
  const tabValue = normalize(tabKey);
  if (!moduleValue || !tabValue) return false;
  try {
    return !!document.querySelector(`.comm-items-root[data-module="${moduleValue}"][data-tab="${tabValue}"]`);
  } catch {
    return false;
  }
}

function contextFromElement(el: HTMLElement | null): { moduleKey: string; tabKey: string; key: string } | null {
  if (!el) return null;
  const card = el.closest(".comm-items-card[data-module][data-tab]") as HTMLElement | null;
  if (!card) return null;
  const moduleKey = normalize(card.dataset.module);
  const tabKey = normalize(card.dataset.tab);
  if (!moduleKey || !tabKey) return null;
  return { moduleKey, tabKey, key: keyOf(moduleKey, tabKey) };
}

function contextFromAction(actionEl: HTMLElement | null): { moduleKey: string; tabKey: string; key: string } | null {
  return contextFromElement(actionEl);
}

function resetForm(moduleKey: string, tabKey: string): void {
  const key = keyOf(moduleKey, tabKey);
  const defaults = formBridge.defaultValues(moduleKey, tabKey, itemTypeForTab(moduleKey, tabKey));
  setValue(`ci-form-id-${key}`, "");
  setValue(`ci-form-item-type-${key}`, defaults.itemType);
  [
    `ci-form-title-${key}`,
    `ci-form-short-desc-${key}`,
    `ci-form-project-${key}`,
    `ci-form-discipline-${key}`,
    `ci-form-response-due-${key}`,
    `ci-form-recipient-org-${key}`,
    `ci-form-contract-clause-${key}`,
    `ci-form-spec-clause-${key}`,
    `ci-form-wbs-${key}`,
    `ci-form-activity-${key}`,
    `ci-form-rfi-question-${key}`,
    `ci-form-rfi-proposed-${key}`,
    `ci-form-rfi-drawing-refs-${key}`,
    `ci-form-rfi-spec-refs-${key}`,
    `ci-form-rfi-answer-${key}`,
    `ci-form-rfi-answered-at-${key}`,
    `ci-form-ncr-kind-${key}`,
    `ci-form-ncr-severity-${key}`,
    `ci-form-ncr-nonconf-${key}`,
    `ci-form-ncr-containment-${key}`,
    `ci-form-ncr-rectification-${key}`,
    `ci-form-ncr-verification-note-${key}`,
    `ci-form-ncr-verified-at-${key}`,
    `ci-form-tech-document-title-${key}`,
    `ci-form-tech-doc-no-${key}`,
    `ci-form-tech-revision-${key}`,
    `ci-form-tech-transmittal-no-${key}`,
    `ci-form-tech-submission-no-${key}`,
    `ci-form-tech-review-result-${key}`,
    `ci-form-tech-review-note-${key}`,
    `ci-form-tech-meeting-date-${key}`,
  ].forEach((id) => setValue(id, ""));
  setValue(`ci-form-priority-${key}`, "NORMAL");
  setValue(`ci-form-status-${key}`, defaults.statusCode);
  setValue(`ci-form-tech-subtype-${key}`, valueOf(`ci-form-tech-subtype-default-${key}`) || defaults.techSubtypeCode);
  setChecked(`ci-form-rfi-as-ncr-${key}`, false);
  setChecked(`ci-form-impact-time-${key}`, false);
  setChecked(`ci-form-impact-cost-${key}`, false);
  setFormSavingState(moduleKey, tabKey, false);
  clearFormErrors(moduleKey, tabKey);
  markDrawerDirty(moduleKey, tabKey, false);
  applyTypeVisibility(moduleKey, tabKey);
  applySectionState(moduleKey, tabKey);
  ensureShamsiInputsForBoard(moduleKey, tabKey);
}

function openForm(moduleKey: string, tabKey: string): void {
  setDrawerTitle(moduleKey, tabKey, "فرم درخواست");
  showFormMode(moduleKey, tabKey);
  openDrawer(moduleKey, tabKey);
  markDrawerDirty(moduleKey, tabKey, false);
  applyTypeVisibility(moduleKey, tabKey);
  applySectionState(moduleKey, tabKey);
  clearFormErrors(moduleKey, tabKey);
  ensureShamsiInputsForBoard(moduleKey, tabKey);
}

function closeForm(moduleKey: string, tabKey: string): void {
  if (!closeDrawer(moduleKey, tabKey)) return;
  resetForm(moduleKey, tabKey);
}

function fillFormWithItem(moduleKey: string, tabKey: string, item: Record<string, unknown>): void {
  const key = keyOf(moduleKey, tabKey);
  const itemType = upper(item.item_type || itemTypeForTab(moduleKey, tabKey));
  selectedItemTypeByKey[key] = itemType;
  setValue(`ci-form-id-${key}`, item.id || "");
  setValue(`ci-form-item-type-${key}`, itemType);
  setChecked(`ci-form-rfi-as-ncr-${key}`, false);
  setValue(`ci-form-project-${key}`, item.project_code || "");
  setValue(`ci-form-discipline-${key}`, item.discipline_code || "");
  setValue(`ci-form-title-${key}`, item.title || "");
  setValue(`ci-form-short-desc-${key}`, item.short_description || "");
  setValue(`ci-form-priority-${key}`, item.priority || "NORMAL");
  setValue(`ci-form-status-${key}`, item.status_code || "");
  setValue(`ci-form-response-due-${key}`, String(item.response_due_date || "").slice(0, 10));
  setValue(`ci-form-recipient-org-${key}`, item.recipient_org_id || "");
  setValue(`ci-form-contract-clause-${key}`, item.contract_clause_ref || "");
  setValue(`ci-form-spec-clause-${key}`, item.spec_clause_ref || "");
  setValue(`ci-form-wbs-${key}`, item.wbs_code || "");
  setValue(`ci-form-activity-${key}`, item.activity_code || "");
  setChecked(`ci-form-impact-time-${key}`, Boolean(item.potential_impact_time));
  setChecked(`ci-form-impact-cost-${key}`, Boolean(item.potential_impact_cost));

  const rfi = asRecord(item.rfi);
  const ncr = asRecord(item.ncr);
  const tech = asRecord(item.tech);
  setValue(`ci-form-rfi-question-${key}`, rfi.question_text || "");
  setValue(`ci-form-rfi-proposed-${key}`, rfi.proposed_solution || "");
  setValue(`ci-form-rfi-drawing-refs-${key}`, Array.isArray(rfi.drawing_refs) ? rfi.drawing_refs.join(", ") : "");
  setValue(`ci-form-rfi-spec-refs-${key}`, Array.isArray(rfi.spec_refs) ? rfi.spec_refs.join(", ") : "");
  setValue(`ci-form-rfi-answer-${key}`, rfi.answer_text || "");
  setValue(`ci-form-rfi-answered-at-${key}`, String(rfi.answered_at || "").slice(0, 10));
  setValue(`ci-form-ncr-kind-${key}`, ncr.kind || "");
  setValue(`ci-form-ncr-severity-${key}`, ncr.severity || "");
  setValue(`ci-form-ncr-nonconf-${key}`, ncr.nonconformance_text || "");
  setValue(`ci-form-ncr-containment-${key}`, ncr.containment_action || "");
  setValue(`ci-form-ncr-rectification-${key}`, ncr.rectification_method || "");
  setValue(`ci-form-ncr-verification-note-${key}`, ncr.verification_note || "");
  setValue(`ci-form-ncr-verified-at-${key}`, String(ncr.verified_at || "").slice(0, 10));
  setValue(`ci-form-tech-subtype-${key}`, tech.tech_subtype_code || formBridge.resolveDefaultTechSubtype(moduleKey, tabKey));
  setValue(`ci-form-tech-document-title-${key}`, tech.document_title || "");
  setValue(`ci-form-tech-doc-no-${key}`, tech.document_no || "");
  setValue(`ci-form-tech-revision-${key}`, tech.revision || "");
  setValue(`ci-form-tech-transmittal-no-${key}`, tech.transmittal_no || "");
  setValue(`ci-form-tech-submission-no-${key}`, tech.submission_no || "");
  setValue(`ci-form-tech-review-result-${key}`, tech.review_result_code || "");
  setValue(`ci-form-tech-review-note-${key}`, tech.review_note || "");
  setValue(`ci-form-tech-meeting-date-${key}`, String(tech.meeting_date || "").slice(0, 10));
  populateStatusOptions(moduleKey, tabKey, itemType);
  setValue(`ci-form-status-${key}`, item.status_code || "");
  openForm(moduleKey, tabKey);
  markDrawerDirty(moduleKey, tabKey, false);
  applySectionState(moduleKey, tabKey);
  ensureShamsiInputsForBoard(moduleKey, tabKey);
}

function buildFormInput(moduleKey: string, tabKey: string): Record<string, unknown> {
  const key = keyOf(moduleKey, tabKey);
  return {
    moduleKey,
    tabKey,
    itemType: valueOf(`ci-form-item-type-${key}`),
    projectCode: valueOf(`ci-form-project-${key}`),
    disciplineCode: valueOf(`ci-form-discipline-${key}`),
    title: valueOf(`ci-form-title-${key}`),
    shortDescription: valueOf(`ci-form-short-desc-${key}`),
    statusCode: valueOf(`ci-form-status-${key}`),
    priority: valueOf(`ci-form-priority-${key}`),
    responseDueDate: valueOf(`ci-form-response-due-${key}`),
    recipientOrgId: valueOf(`ci-form-recipient-org-${key}`),
    contractClauseRef: valueOf(`ci-form-contract-clause-${key}`),
    specClauseRef: valueOf(`ci-form-spec-clause-${key}`),
    wbsCode: valueOf(`ci-form-wbs-${key}`),
    activityCode: valueOf(`ci-form-activity-${key}`),
    impactTime: checkedOf(`ci-form-impact-time-${key}`),
    impactCost: checkedOf(`ci-form-impact-cost-${key}`),
    rfiQuestionText: valueOf(`ci-form-rfi-question-${key}`),
    rfiProposedSolution: valueOf(`ci-form-rfi-proposed-${key}`),
    rfiDrawingRefs: valueOf(`ci-form-rfi-drawing-refs-${key}`),
    rfiSpecRefs: valueOf(`ci-form-rfi-spec-refs-${key}`),
    rfiAnswerText: valueOf(`ci-form-rfi-answer-${key}`),
    rfiAnsweredAt: valueOf(`ci-form-rfi-answered-at-${key}`),
    ncrKind: valueOf(`ci-form-ncr-kind-${key}`),
    ncrSeverity: valueOf(`ci-form-ncr-severity-${key}`),
    ncrNonconformanceText: valueOf(`ci-form-ncr-nonconf-${key}`),
    ncrContainmentAction: valueOf(`ci-form-ncr-containment-${key}`),
    ncrRectificationMethod: valueOf(`ci-form-ncr-rectification-${key}`),
    ncrVerificationNote: valueOf(`ci-form-ncr-verification-note-${key}`),
    ncrVerifiedAt: valueOf(`ci-form-ncr-verified-at-${key}`),
    techSubtypeCode: valueOf(`ci-form-tech-subtype-${key}`),
    techDocumentTitle: valueOf(`ci-form-tech-document-title-${key}`),
    techDocumentNo: valueOf(`ci-form-tech-doc-no-${key}`),
    techRevision: valueOf(`ci-form-tech-revision-${key}`),
    techTransmittalNo: valueOf(`ci-form-tech-transmittal-no-${key}`),
    techSubmissionNo: valueOf(`ci-form-tech-submission-no-${key}`),
    techReviewResultCode: valueOf(`ci-form-tech-review-result-${key}`),
    techReviewNote: valueOf(`ci-form-tech-review-note-${key}`),
    techMeetingDate: valueOf(`ci-form-tech-meeting-date-${key}`),
    rfiAsNcr: checkedOf(`ci-form-rfi-as-ncr-${key}`),
  };
}

async function loadTab(moduleKey: string, tabKey: string, deps: CommItemsUiDeps, force = false): Promise<boolean> {
  const key = keyOf(moduleKey, tabKey);
  if (loadingByKey[key] && !force) return true;
  loadingByKey[key] = true;
  const tbody = getElement(`ci-tbody-${key}`);
  if (tbody instanceof HTMLElement && force) {
    tbody.innerHTML = '<tr><td colspan="10" class="center-text" style="padding:24px;color:#64748b;">Loading...</td></tr>';
  }

  const query = {
    skip: 0,
    limit: 250,
    module_key: moduleKey,
    tab_key: tabKey,
    search: valueOf(`ci-filter-search-${key}`),
    status_code: valueOf(`ci-filter-status-${key}`),
    project_code: valueOf(`ci-filter-project-${key}`),
    discipline_code: valueOf(`ci-filter-discipline-${key}`),
    has_reference_attachments: parseBoolSelect(valueOf(`ci-filter-ref-${key}`)),
    has_response_attachments: parseBoolSelect(valueOf(`ci-filter-resp-${key}`)),
    attachment_type: valueOf(`ci-filter-atype-${key}`),
  };
  try {
    const body = await dataBridge.list(query, { fetch: deps.fetch });
    const rows = asArray(body.data);
    boardRowsByKey[key] = rows;
    renderBoardRows(moduleKey, tabKey, deps, Number(body.total || rows.length || 0));
    return true;
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Load failed", "error");
    if (tbody instanceof HTMLElement) {
      tbody.innerHTML = '<tr><td colspan="10" class="center-text" style="padding:24px;color:#b91c1c;">Failed to load</td></tr>';
    }
    return false;
  } finally {
    loadingByKey[key] = false;
  }
}
function detailTabHtml(key: string): string {
  return `
    <div class="ci-detail-tabs edms-tabs">
      <button type="button" class="edms-tab-btn active" data-ci-action="detail-tab" data-ci-detail-tab="summary" data-ci-key="${key}">خلاصه</button>
      <button type="button" class="edms-tab-btn" data-ci-action="detail-tab" data-ci-detail-tab="timeline" data-ci-key="${key}">گردش</button>
      <button type="button" class="edms-tab-btn" data-ci-action="detail-tab" data-ci-detail-tab="comments" data-ci-key="${key}">کامنت‌ها</button>
      <button type="button" class="edms-tab-btn" data-ci-action="detail-tab" data-ci-detail-tab="attachments" data-ci-key="${key}">پیوست‌ها</button>
      <button type="button" class="edms-tab-btn" data-ci-action="detail-tab" data-ci-detail-tab="relations" data-ci-key="${key}">روابط</button>
    </div>
    <div id="ci-detail-summary-${key}" class="ci-detail-panel"></div>
    <div id="ci-detail-timeline-${key}" class="ci-detail-panel" style="display:none;"></div>
    <div id="ci-detail-comments-${key}" class="ci-detail-panel" style="display:none;"></div>
    <div id="ci-detail-attachments-${key}" class="ci-detail-panel" style="display:none;"></div>
    <div id="ci-detail-relations-${key}" class="ci-detail-panel" style="display:none;"></div>
  `;
}

function formModeSwitchHtml(key: string): string {
  return `
    <div id="ci-drawer-mode-switch-${key}" class="ci-drawer-mode-switch" hidden>
      <input id="ci-form-rfi-as-ncr-${key}" type="checkbox" hidden>
      <button type="button" id="ci-form-mode-rfi-${key}" class="ci-rfi-mode-btn active" data-ci-action="set-rfi-mode" data-ci-key="${key}" aria-pressed="true">
        <span>RFI</span>
      </button>
      <button type="button" id="ci-form-mode-ncr-${key}" class="ci-rfi-mode-btn" data-ci-action="set-ncr-mode" data-ci-key="${key}" aria-pressed="false">
        <span>NCR</span>
      </button>
    </div>
  `;
}

function detailValue(value: unknown): string {
  return escHtml(textOrDash(value));
}

function detailMetaCard(label: string, value: unknown, tone = "neutral"): string {
  return `
    <div class="ci-detail-stat ci-detail-stat-${tone}">
      <span class="ci-detail-stat-label">${stateBridge.esc(label)}</span>
      <strong class="ci-detail-stat-value">${detailValue(value)}</strong>
    </div>
  `;
}

function detailInfoItem(label: string, value: unknown): string {
  return `
    <div class="ci-detail-info-item">
      <span class="ci-detail-info-label">${stateBridge.esc(label)}</span>
      <strong class="ci-detail-info-value">${detailValue(value)}</strong>
    </div>
  `;
}

function detailNarrativeSection(title: string, body: unknown, emphasis = false): string {
  return `
    <section class="ci-detail-section${emphasis ? " is-emphasis" : ""}">
      <div class="ci-detail-section-head">
        <h4>${stateBridge.esc(title)}</h4>
      </div>
      <div class="ci-detail-section-body">${detailValue(body)}</div>
    </section>
  `;
}

function buildSpecificDetailSections(item: Record<string, unknown>, itemType: string): string {
  const rfi = asRecord(item.rfi);
  const ncr = asRecord(item.ncr);
  const tech = asRecord(item.tech);
  if (itemType === "RFI") {
    return [
      detailNarrativeSection("شرح موضوع و سوال فنی", rfi.question_text || item.short_description, true),
      detailNarrativeSection("پیشنهاد / راهکار درخواست‌کننده", rfi.proposed_solution),
      detailNarrativeSection("پاسخ و نتیجه بررسی", rfi.answer_text),
    ].join("");
  }
  if (itemType === "NCR") {
    return [
      detailNarrativeSection("شرح عدم انطباق", ncr.nonconformance_text || item.short_description, true),
      detailNarrativeSection("اقدام فوری", ncr.containment_action),
      detailNarrativeSection("روش اصلاح", ncr.rectification_method),
      detailNarrativeSection("یادداشت تایید", ncr.verification_note),
    ].join("");
  }
  return [
    detailNarrativeSection("شرح / خلاصه", item.short_description || tech.review_note || item.title, true),
    detailNarrativeSection("نتیجه بررسی", tech.review_result_code),
    detailNarrativeSection("یادداشت بررسی", tech.review_note),
  ].join("");
}

function renderSummaryTab(moduleKey: string, tabKey: string, item: Record<string, unknown>, canEdit: boolean): void {
  const key = keyOf(moduleKey, tabKey);
  const host = getElement(`ci-detail-summary-${key}`);
  if (!(host instanceof HTMLElement)) return;
  const transitions = workflowBridge.nextStatuses(item.item_type, item.status_code, transitionMap as any) || [];
  const transitionOptions = transitions.length
    ? transitions.map((r: Record<string, unknown>) => `<option value="${stateBridge.esc(r.to_status_code || "")}">${stateBridge.esc(r.to_status_code || "")}</option>`).join("")
    : '<option value="">انتقالی در دسترس نیست</option>';
  const relationTypeOptions = asArray(catalogCache?.relation_types).length
    ? asArray(catalogCache?.relation_types).map((x) => `<option value="${stateBridge.esc(x)}">${stateBridge.esc(x)}</option>`).join("")
    : '<option value="">رابطه‌ای تعریف نشده</option>';
  const itemType = upper(item.item_type || itemTypeForTab(moduleKey, tabKey));
  selectedItemTypeByKey[key] = itemType;
  const rfi = asRecord(item.rfi);
  const ncr = asRecord(item.ncr);
  const tech = asRecord(item.tech);
  const projectName = findProjectName(catalogCache || {}, item.project_code);
  const disciplineName = findDisciplineLabel(catalogCache || {}, item.discipline_code);
  const ownerOrgName = textOrDash(item.sender_org_name || findOrganizationName(catalogCache || {}, item.organization_id));
  const recipientOrgName = textOrDash(item.recipient_org_name);
  const createdAt = formatShamsiDate(item.created_at);
  const dueDate = formatShamsiDate(item.response_due_date);
  const answeredAt = formatShamsiDate(rfi.answered_at || ncr.verified_at || tech.meeting_date);
  const aging = Number(item.aging_days || 0);
  const title = textOrDash(item.title);
  const subtitle = textOrDash(item.short_description || rfi.question_text || ncr.nonconformance_text || tech.review_note);
  const references = [
    text(rfi.drawing_refs && asArray(rfi.drawing_refs).map((row) => text(row)).filter(Boolean).join("، ")),
    text(rfi.spec_refs && asArray(rfi.spec_refs).map((row) => text(row)).filter(Boolean).join("، ")),
    text(item.contract_clause_ref),
    text(item.spec_clause_ref),
    text(item.reference_no),
  ].filter(Boolean).join(" | ");

  const uploads = ["REFERENCE", "RESPONSE", "GENERAL"]
    .map((scope) => {
      const slot = attachmentSlotFor(itemType, scope);
      return `
        <div class="ci-detail-inline-card">
          <div class="ci-detail-inline-head">
            <strong>${stateBridge.esc(scope === "REFERENCE" ? "پیوست ارجاع" : scope === "RESPONSE" ? "پیوست پاسخ" : "پیوست عمومی")}</strong>
            <span>${stateBridge.esc(slot)}</span>
          </div>
          <input id="ci-detail-file-${scope}-${key}" type="file" class="module-crud-input" ${canEdit ? "" : "disabled"}>
          <input id="ci-detail-file-note-${scope}-${key}" class="module-crud-input" placeholder="یادداشت فایل" ${canEdit ? "" : "disabled"}>
          ${canEdit ? `<button type="button" class="btn btn-secondary" data-ci-action="upload-attachment" data-ci-scope="${scope}">آپلود</button>` : ""}
        </div>
      `;
    })
    .join("");

  host.innerHTML = `
    <div class="ci-detail-shell">
      <section class="ci-detail-hero">
        <div class="ci-detail-hero-main">
          <div class="ci-detail-kicker">${stateBridge.esc(itemType)} / ${stateBridge.esc(moduleKey)} / ${stateBridge.esc(tabKey)}</div>
          <div class="ci-detail-hero-head">
            <div>
              <h3>${stateBridge.esc(textOrDash(item.item_no))}</h3>
              <p>${stateBridge.esc(title)}</p>
            </div>
            <div class="ci-detail-badges">
              <span class="module-crud-status is-${stateBridge.statusClass(item.item_type)}">${stateBridge.esc(itemType)}</span>
              <span class="module-crud-status is-${stateBridge.statusClass(item.status_code)}">${stateBridge.esc(textOrDash(item.status_code))}</span>
              <span class="module-crud-priority is-${normalize(item.priority || "normal")}">${stateBridge.esc(textOrDash(item.priority))}</span>
            </div>
          </div>
          <div class="ci-detail-subtitle">${stateBridge.esc(subtitle)}</div>
          <div class="ci-detail-stats">
            ${detailMetaCard("پروژه", projectName, "info")}
            ${detailMetaCard("رشته", disciplineName)}
            ${detailMetaCard("سررسید", dueDate, item.is_overdue ? "warn" : "neutral")}
            ${detailMetaCard("سن آیتم", aging > 0 ? `${aging} روز` : "-", aging > 0 ? "warn" : "neutral")}
          </div>
        </div>
        <div class="ci-detail-hero-side">
          <div class="ci-detail-side-block">
            <div class="ci-detail-side-label">صادرکننده</div>
            <div class="ci-detail-side-value">${stateBridge.esc(textOrDash(item.created_by_name))}</div>
          </div>
          <div class="ci-detail-side-block">
            <div class="ci-detail-side-label">سازمان / واحد</div>
            <div class="ci-detail-side-value">${stateBridge.esc(ownerOrgName)}</div>
          </div>
          <div class="ci-detail-side-block">
            <div class="ci-detail-side-label">مخاطب</div>
            <div class="ci-detail-side-value">${stateBridge.esc(recipientOrgName)}</div>
          </div>
          <div class="ci-detail-side-block">
            <div class="ci-detail-side-label">تاریخ ثبت</div>
            <div class="ci-detail-side-value">${stateBridge.esc(createdAt)}</div>
          </div>
          ${itemType === "RFI" ? '<button type="button" class="btn btn-secondary ci-detail-print-btn" data-ci-action="print-rfi-form">پرینت فرم RFI</button>' : ""}
        </div>
      </section>

      <div class="ci-detail-grid">
        <div class="ci-detail-main">
          <section class="ci-detail-section">
            <div class="ci-detail-section-head">
              <h4>اطلاعات پایه</h4>
            </div>
            <div class="ci-detail-info-grid">
              ${detailInfoItem("عنوان", title)}
              ${detailInfoItem("شرح کوتاه", item.short_description)}
              ${detailInfoItem("شماره مرجع", item.reference_no || item.related_item_no)}
              ${detailInfoItem("Clause قرارداد", item.contract_clause_ref)}
              ${detailInfoItem("Clause Spec", item.spec_clause_ref)}
              ${detailInfoItem("WBS / Activity", [text(item.wbs_code), text(item.activity_code)].filter(Boolean).join(" / "))}
              ${detailInfoItem("تاریخ پاسخ / تایید", answeredAt)}
              ${detailInfoItem("ارجاعات", references || "-")}
            </div>
          </section>

          <div class="ci-detail-narratives">
            ${buildSpecificDetailSections(item, itemType)}
          </div>
        </div>

        <aside class="ci-detail-sidebar">
          <section class="ci-detail-section ci-detail-action-card">
            <div class="ci-detail-section-head">
              <h4>تغییر وضعیت</h4>
            </div>
            <div class="ci-detail-action-stack">
              <select id="ci-detail-transition-status-${key}" class="module-crud-select">${transitionOptions}</select>
              <input id="ci-detail-transition-note-${key}" class="module-crud-input" placeholder="یادداشت تغییر وضعیت">
              ${canEdit ? '<button type="button" class="btn btn-primary" data-ci-action="transition-item">اعمال وضعیت</button>' : ""}
            </div>
          </section>

          <section class="ci-detail-section ci-detail-action-card">
            <div class="ci-detail-section-head">
              <h4>ثبت کامنت</h4>
            </div>
            <div class="ci-detail-action-stack">
              <textarea id="ci-detail-comment-${key}" class="module-crud-textarea" placeholder="یادداشت یا توضیح جدید"></textarea>
              ${canEdit ? '<button type="button" class="btn btn-secondary" data-ci-action="add-comment">افزودن کامنت</button>' : ""}
            </div>
          </section>

          <section class="ci-detail-section ci-detail-action-card">
            <div class="ci-detail-section-head">
              <h4>پیوست سریع</h4>
            </div>
            <div class="ci-detail-upload-stack">
              ${uploads}
            </div>
          </section>

          <section class="ci-detail-section ci-detail-action-card">
            <div class="ci-detail-section-head">
              <h4>ایجاد رابطه</h4>
            </div>
            <div class="ci-detail-action-stack">
              <input id="ci-detail-rel-to-${key}" class="module-crud-input" type="number" min="1" placeholder="شناسه آیتم مقصد">
              <select id="ci-detail-rel-type-${key}" class="module-crud-select">${relationTypeOptions}</select>
              ${canEdit ? '<button type="button" class="btn btn-secondary" data-ci-action="add-relation">افزودن رابطه</button>' : ""}
            </div>
          </section>
        </div>
      </div>
    </div>
  `;
}

async function loadDetailData(moduleKey: string, tabKey: string, itemId: number, deps: CommItemsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const [timelineBody, commentsBody, attachmentsBody, relationsBody] = await Promise.all([
    dataBridge.timeline(itemId, { fetch: deps.fetch }),
    dataBridge.listComments(itemId, { fetch: deps.fetch }),
    dataBridge.listAttachments(itemId, { fetch: deps.fetch }),
    dataBridge.listRelations(itemId, { fetch: deps.fetch }),
  ]);
  stateBridge.renderTimeline(getElement(`ci-detail-timeline-${key}`), timelineBody);
  stateBridge.renderComments(getElement(`ci-detail-comments-${key}`), asArray(commentsBody.data));
  stateBridge.renderAttachments(getElement(`ci-detail-attachments-${key}`), attachmentsBody);
  stateBridge.renderRelations(getElement(`ci-detail-relations-${key}`), asArray(relationsBody.outgoing), asArray(relationsBody.incoming));
}

async function openDetail(moduleKey: string, tabKey: string, itemId: number, deps: CommItemsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const wrap = getElement(`ci-detail-wrap-${key}`);
  if (!(wrap instanceof HTMLElement)) return;
  const body = await dataBridge.get(itemId, { fetch: deps.fetch });
  const item = asRecord(body.data);
  const id = Number(item.id || itemId || 0);
  const itemType = upper(item.item_type || itemTypeForTab(moduleKey, tabKey));
  selectedItemByKey[key] = id;
  selectedItemTypeByKey[key] = itemType;
  showDetailMode(moduleKey, tabKey);
  setDrawerTitle(moduleKey, tabKey, `جزئیات ${itemType} ${String(item.item_no || id)}`);
  openDrawer(moduleKey, tabKey);
  markDrawerDirty(moduleKey, tabKey, false);
  wrap.innerHTML = detailTabHtml(key);
  renderSummaryTab(moduleKey, tabKey, item, deps.canEdit());
  await loadDetailData(moduleKey, tabKey, id, deps);
}

async function openQuickTransition(moduleKey: string, tabKey: string, itemId: number, deps: CommItemsUiDeps): Promise<void> {
  await openDetail(moduleKey, tabKey, itemId, deps);
  const key = keyOf(moduleKey, tabKey);
  const statusSelect = asSelect(getElement(`ci-detail-transition-status-${key}`));
  if (statusSelect) {
    statusSelect.focus();
    try {
      statusSelect.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch {
      // no-op
    }
  }
}

function switchDetailTab(key: string, tab: string): void {
  ["summary", "timeline", "comments", "attachments", "relations"].forEach((name) => {
    const panel = getElement(`ci-detail-${name}-${key}`);
    if (panel instanceof HTMLElement) panel.style.display = normalize(name) === normalize(tab) ? "block" : "none";
  });
  document.querySelectorAll(`button[data-ci-action="detail-tab"][data-ci-key="${key}"]`).forEach((button) => {
    button.classList.remove("active");
    if (normalize((button as HTMLElement).dataset.ciDetailTab) === normalize(tab)) button.classList.add("active");
  });
}

async function saveForm(moduleKey: string, tabKey: string, deps: CommItemsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const itemId = Number(valueOf(`ci-form-id-${key}`) || 0);
  const formInput = buildFormInput(moduleKey, tabKey);
  const rfiAsNcrMode = itemId <= 0 && upper(itemTypeForTab(moduleKey, tabKey)) === "RFI" && checkedOf(`ci-form-rfi-as-ncr-${key}`);
  if (rfiAsNcrMode) {
    formInput.itemType = "NCR";
    formInput.statusCode = "ISSUED";
    if (!text(formInput.ncrKind)) formInput.ncrKind = "NCR";
    if (!text(formInput.ncrSeverity)) formInput.ncrSeverity = "MINOR";
    if (!text(formInput.ncrNonconformanceText)) {
      formInput.ncrNonconformanceText = text(formInput.rfiQuestionText);
    }
    if (!text(formInput.ncrContainmentAction)) {
      formInput.ncrContainmentAction = text(formInput.rfiProposedSolution);
    }
  }

  if (!itemId) {
    const errors = formBridge.validateForSubmit(formInput as any);
    if (errors.length) {
      renderFormErrors(moduleKey, tabKey, errors);
      deps.showToast(errors[0], "error");
      return;
    }
  }

  const createPayload = formBridge.buildCreatePayload(formInput as any);
  setFormSavingState(moduleKey, tabKey, true);
  clearFormErrors(moduleKey, tabKey);
  try {
    if (itemId > 0) {
      const updatePayload = formBridge.buildUpdatePayload(createPayload as any);
      delete updatePayload.status_code;
      await dataBridge.update(itemId, updatePayload, { fetch: deps.fetch });
      deps.showToast("Item updated", "success");
      markDrawerDirty(moduleKey, tabKey, false);
      closeForm(moduleKey, tabKey);
      await loadTab(moduleKey, tabKey, deps, true);
      await openDetail(moduleKey, tabKey, itemId, deps);
      return;
    }
    const created = await dataBridge.create(createPayload, { fetch: deps.fetch });
    const createdId = Number(asRecord(created.data).id || 0);
    deps.showToast("Item created", "success");
    if (rfiAsNcrMode) {
      deps.showToast("آیتم با نوع NCR ثبت شد و در جدول درخواست‌ها قابل مشاهده است.", "success");
    }
    markDrawerDirty(moduleKey, tabKey, false);
    closeForm(moduleKey, tabKey);
    await loadTab(moduleKey, tabKey, deps, true);
    if (createdId > 0) {
      await openDetail(moduleKey, tabKey, createdId, deps);
      switchDetailTab(key, "summary");
    }
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Save failed", "error");
  } finally {
    setFormSavingState(moduleKey, tabKey, false);
  }
}

async function openEdit(moduleKey: string, tabKey: string, itemId: number, deps: CommItemsUiDeps): Promise<void> {
  const rows = asArray(boardRowsByKey[keyOf(moduleKey, tabKey)]);
  const row = rows.find((r) => Number(r.id || 0) === Number(itemId || 0));
  if (!row) {
    deps.showToast("Item not found", "error");
    return;
  }
  const body = await dataBridge.get(itemId, { fetch: deps.fetch });
  fillFormWithItem(moduleKey, tabKey, asRecord(body.data));
}
async function doTransition(moduleKey: string, tabKey: string, deps: CommItemsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const itemId = Number(selectedItemByKey[key] || 0);
  if (!itemId) {
    deps.showToast("No item selected", "error");
    return;
  }
  const toStatus = valueOf(`ci-detail-transition-status-${key}`);
  if (!toStatus) {
    deps.showToast("Target status is required", "error");
    return;
  }
  const note = valueOf(`ci-detail-transition-note-${key}`);
  try {
    await dataBridge.transition(itemId, { to_status_code: upper(toStatus), note: note || null }, { fetch: deps.fetch });
    deps.showToast("Transition applied", "success");
    await loadTab(moduleKey, tabKey, deps, true);
    await openDetail(moduleKey, tabKey, itemId, deps);
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Transition failed", "error");
  }
}

async function addComment(moduleKey: string, tabKey: string, deps: CommItemsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const itemId = Number(selectedItemByKey[key] || 0);
  const text = valueOf(`ci-detail-comment-${key}`);
  if (!itemId || !text) return;
  try {
    await dataBridge.createComment(itemId, { comment_text: text, comment_type: "comment" }, { fetch: deps.fetch });
    setValue(`ci-detail-comment-${key}`, "");
    await loadDetailData(moduleKey, tabKey, itemId, deps);
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Comment failed", "error");
  }
}

async function uploadAttachment(moduleKey: string, tabKey: string, scopeCode: string, deps: CommItemsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const itemId = Number(selectedItemByKey[key] || 0);
  if (!itemId) {
    deps.showToast("Save item first", "error");
    return;
  }
  const scope = upper(scopeCode || "GENERAL") || "GENERAL";
  const fileInput = asInput(getElement(`ci-detail-file-${scope}-${key}`));
  const file = fileInput?.files?.[0];
  if (!file) {
    deps.showToast("Select a file", "error");
    return;
  }
  const itemType = upper(selectedItemTypeByKey[key] || itemTypeForTab(moduleKey, tabKey));
  const slotCode = attachmentSlotFor(itemType, scope);
  const note = valueOf(`ci-detail-file-note-${scope}-${key}`);
  const formData = new FormData();
  formData.append("file", file);
  formData.append("file_kind", fileKindForName(file.name));
  formData.append("scope_code", scope);
  formData.append("slot_code", slotCode);
  if (note) formData.append("note", note);
  try {
    await dataBridge.uploadAttachment(itemId, formData, { fetch: deps.fetch });
    if (fileInput) fileInput.value = "";
    setValue(`ci-detail-file-note-${scope}-${key}`, "");
    await loadDetailData(moduleKey, tabKey, itemId, deps);
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Upload failed", "error");
  }
}

async function deleteAttachment(moduleKey: string, tabKey: string, attachmentId: number, deps: CommItemsUiDeps): Promise<void> {
  const itemId = Number(selectedItemByKey[keyOf(moduleKey, tabKey)] || 0);
  if (!itemId || !attachmentId) return;
  try {
    await dataBridge.deleteAttachment(itemId, attachmentId, { fetch: deps.fetch });
    await loadDetailData(moduleKey, tabKey, itemId, deps);
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Delete attachment failed", "error");
  }
}

async function addRelation(moduleKey: string, tabKey: string, deps: CommItemsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const itemId = Number(selectedItemByKey[key] || 0);
  const toItemId = Number(valueOf(`ci-detail-rel-to-${key}`) || 0);
  const relationType = upper(valueOf(`ci-detail-rel-type-${key}`));
  if (!itemId || !toItemId || !relationType) {
    deps.showToast("Relation data incomplete", "error");
    return;
  }
  try {
    await dataBridge.createRelation(itemId, { to_item_id: toItemId, relation_type: relationType }, { fetch: deps.fetch });
    setValue(`ci-detail-rel-to-${key}`, "");
    await loadDetailData(moduleKey, tabKey, itemId, deps);
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Add relation failed", "error");
  }
}

async function deleteRelation(moduleKey: string, tabKey: string, relationId: number, deps: CommItemsUiDeps): Promise<void> {
  const itemId = Number(selectedItemByKey[keyOf(moduleKey, tabKey)] || 0);
  if (!itemId || !relationId) return;
  try {
    await dataBridge.deleteRelation(itemId, relationId, { fetch: deps.fetch });
    await loadDetailData(moduleKey, tabKey, itemId, deps);
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Delete relation failed", "error");
  }
}

async function exportRfiExcel(moduleKey: string, tabKey: string, deps: CommItemsUiDeps): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const rows = asArray(boardRowsByKey[key]).filter((row) => upper(row.item_type) === "RFI");
  if (!rows.length) {
    deps.showToast("ردیف RFI برای خروجی وجود ندارد.", "error");
    return;
  }
  const stamp = text(formatShamsiDateForFileName(new Date())) || text(new Date().toISOString().slice(0, 10).replace(/-/g, ""));
  const baseName = `RFI_List_${normalize(moduleKey)}_${normalize(tabKey)}_${stamp}`;
  const sheetRows = [rfiExcelHeaders()].concat(rows.map((row) => rfiExcelRow(row, deps.cache || {})));
  try {
    if (!window.XLSX?.utils) {
      try {
        await window.ensureXlsxLoaded?.();
      } catch {
        // fall back to CSV when XLSX CDN is unavailable
      }
    }
    if (window.XLSX?.utils) {
      const wb = window.XLSX.utils.book_new();
      const ws = window.XLSX.utils.aoa_to_sheet(sheetRows);
      window.XLSX.utils.book_append_sheet(wb, ws, "RFI");
      window.XLSX.writeFile(wb, `${baseName}.xlsx`);
      return;
    }
    const csvText = sheetRows.map((cols) => cols.map(csvEscape).join(",")).join("\r\n");
    const csvBlob = new Blob([`\uFEFF${csvText}`], { type: "text/csv;charset=utf-8;" });
    triggerDownload(csvBlob, `${baseName}.csv`);
    deps.showToast("XLSX در دسترس نبود؛ خروجی CSV تولید شد.", "warning");
  } catch (error) {
    deps.showToast(error instanceof Error ? error.message : "Export failed", "error");
  }
}

async function printRfiForm(moduleKey: string, tabKey: string, deps: CommItemsUiDeps, explicitItemId?: number): Promise<void> {
  const key = keyOf(moduleKey, tabKey);
  const selectedId = Number(explicitItemId || selectedItemByKey[key] || 0);
  if (!selectedId) {
    deps.showToast("ابتدا یک آیتم را در جزئیات انتخاب کنید.", "error");
    return;
  }
  const popup = window.open("", "_blank", "width=980,height=900");
  if (!popup) {
    deps.showToast("پنجره پرینت توسط مرورگر مسدود شده است.", "error");
    return;
  }
  try {
    const body = await dataBridge.get(selectedId, { fetch: deps.fetch });
    const item = asRecord(body.data);
    if (upper(item.item_type) !== "RFI") {
      popup.close();
      deps.showToast("فرم پرینت فقط برای آیتم RFI فعال است.", "error");
      return;
    }
    popup.document.open();
    popup.document.write(buildRfiPrintHtml(item, deps.cache || {}));
    popup.document.close();
    popup.focus();
    window.setTimeout(() => {
      try {
        popup.print();
      } catch {
        // no-op
      }
    }, 180);
  } catch (error) {
    try {
      popup.close();
    } catch {
      // no-op
    }
    deps.showToast(error instanceof Error ? error.message : "Print failed", "error");
  }
}

function bindActions(depsResolver: () => CommItemsUiDeps): void {
  if (actionsBound) return;

  document.addEventListener("click", async (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-ci-action]") as HTMLElement | null;
    if (!actionEl) {
      if (!target?.closest?.("[data-ci-row-menu]")) closeRowMenus();
      return;
    }
    const action = normalize(actionEl.dataset.ciAction);
    const deps = depsResolver();
    if (!deps) return;

    if (action === "detail-tab") {
      const key = String(actionEl.dataset.ciKey || "");
      const tab = String(actionEl.dataset.ciDetailTab || "");
      if (key && tab) switchDetailTab(key, tab);
      return;
    }

    const context = contextFromAction(actionEl);
    if (!context) return;

    if (action === "toggle-row-menu") {
      toggleRowMenu(actionEl);
      return;
    }

    closeRowMenus();

    if (action === "drawer-close") {
      closeDrawer(context.moduleKey, context.tabKey);
      return;
    }
    if (action === "filter-type") {
      selectedTypeFilterByKey[context.key] = upper(actionEl.dataset.ciTypeFilter || "");
      renderBoardRows(context.moduleKey, context.tabKey, deps);
      return;
    }
    if (action === "set-rfi-mode" || action === "set-ncr-mode") {
      const toggle = asInput(getElement(`ci-form-rfi-as-ncr-${context.key}`));
      if (toggle) toggle.checked = action === "set-ncr-mode";
      applyTypeVisibility(context.moduleKey, context.tabKey);
      markDrawerDirty(context.moduleKey, context.tabKey, true);
      return;
    }
    if (action === "revert-rfi-mode") {
      const toggle = asInput(getElement(`ci-form-rfi-as-ncr-${context.key}`));
      if (toggle) toggle.checked = false;
      applyTypeVisibility(context.moduleKey, context.tabKey);
      markDrawerDirty(context.moduleKey, context.tabKey, true);
      deps.showToast("فرم به حالت RFI برگشت.", "success");
      return;
    }
    if (action === "toggle-section") {
      const section = normalize(actionEl.dataset.ciSection || "");
      if (section) toggleSection(context.moduleKey, context.tabKey, section);
      return;
    }
    if (action === "refresh") return void (await loadTab(context.moduleKey, context.tabKey, deps, true));
    if (action === "export-rfi-excel") return void (await exportRfiExcel(context.moduleKey, context.tabKey, deps));
    if (action === "open-form") { resetForm(context.moduleKey, context.tabKey); openForm(context.moduleKey, context.tabKey); return; }
    if (action === "close-form") { closeForm(context.moduleKey, context.tabKey); return; }
    if (action === "save-form") return void (await saveForm(context.moduleKey, context.tabKey, deps));
    if (action === "open-edit") { const id = Number(actionEl.dataset.ciId || 0); if (id > 0) await openEdit(context.moduleKey, context.tabKey, id, deps); return; }
    if (action === "open-detail") { const id = Number(actionEl.dataset.ciId || 0); if (id > 0) await openDetail(context.moduleKey, context.tabKey, id, deps); return; }
    if (action === "quick-transition") { const id = Number(actionEl.dataset.ciId || 0); if (id > 0) await openQuickTransition(context.moduleKey, context.tabKey, id, deps); return; }
    if (action === "copy-item-no") {
      const ok = await copyTextToClipboard(String(actionEl.dataset.ciItemNo || ""));
      deps.showToast(ok ? "شماره آیتم کپی شد." : "کپی شماره آیتم انجام نشد.", ok ? "success" : "error");
      return;
    }
    if (action === "print-rfi-form") return void (await printRfiForm(context.moduleKey, context.tabKey, deps, Number(actionEl.dataset.ciId || 0)));
    if (action === "transition-item") return void (await doTransition(context.moduleKey, context.tabKey, deps));
    if (action === "add-comment") return void (await addComment(context.moduleKey, context.tabKey, deps));
    if (action === "upload-attachment") return void (await uploadAttachment(context.moduleKey, context.tabKey, String(actionEl.dataset.ciScope || "GENERAL"), deps));
    if (action === "delete-attachment") return void (await deleteAttachment(context.moduleKey, context.tabKey, Number(actionEl.dataset.ciAttachmentId || 0), deps));
    if (action === "add-relation") return void (await addRelation(context.moduleKey, context.tabKey, deps));
    if (action === "delete-relation") return void (await deleteRelation(context.moduleKey, context.tabKey, Number(actionEl.dataset.ciRelationId || 0), deps));
  });

  document.addEventListener("change", async (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-ci-action]") as HTMLElement | null;
    if (actionEl) {
      const action = normalize(actionEl.dataset.ciAction);
      if (["filter-project", "filter-discipline", "filter-status", "filter-ref", "filter-resp", "filter-atype"].includes(action)) {
        const context = contextFromAction(actionEl);
        if (!context) return;
        await loadTab(context.moduleKey, context.tabKey, depsResolver(), true);
        return;
      }
    }

    const context = contextFromElement(target);
    if (!context) return;
    const id = String((target as HTMLElement)?.id || "");
    if (id.startsWith(`ci-form-`)) {
      if (id === `ci-form-rfi-as-ncr-${context.key}`) {
        applyTypeVisibility(context.moduleKey, context.tabKey);
      } else if (id === `ci-form-status-${context.key}`) {
        updateFormHeaderMeta(context.moduleKey, context.tabKey);
      }
      const fieldKey = fieldKeyFromInputId(id, context.key);
      if (fieldKey) clearFieldError(context.moduleKey, context.tabKey, fieldKey);
      markDrawerDirty(context.moduleKey, context.tabKey, true);
    }
  });

  document.addEventListener("input", (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-ci-action]") as HTMLElement | null;
    if (actionEl && normalize(actionEl.dataset.ciAction) === "filter-search") {
      const context = contextFromAction(actionEl);
      if (!context) return;
      if (debounceTimers[context.key]) window.clearTimeout(debounceTimers[context.key]);
      debounceTimers[context.key] = window.setTimeout(() => {
        void loadTab(context.moduleKey, context.tabKey, depsResolver(), true);
      }, 350);
      return;
    }

    const context = contextFromElement(target);
    if (!context) return;
    const id = String((target as HTMLElement)?.id || "");
    if (id.startsWith(`ci-form-`)) {
      const fieldKey = fieldKeyFromInputId(id, context.key);
      if (fieldKey) clearFieldError(context.moduleKey, context.tabKey, fieldKey);
      markDrawerDirty(context.moduleKey, context.tabKey, true);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const openDrawers = Array.from(document.querySelectorAll(".ci-drawer.is-open")) as HTMLElement[];
    const last = openDrawers[openDrawers.length - 1];
    if (!last) return;
    const context = contextFromElement(last);
    if (!context) return;
    closeDrawer(context.moduleKey, context.tabKey);
  });

  actionsBound = true;
}

async function initModule(moduleKey: string, deps: CommItemsUiDeps): Promise<boolean> {
  await ensureCatalog(deps);
  ensureBoards(normalize(moduleKey), deps);
  bindActions(() => deps);
  return true;
}

async function onTabOpened(moduleKey: string, tabKey: string, deps: CommItemsUiDeps): Promise<boolean> {
  const m = normalize(moduleKey);
  const t = normalize(tabKey);
  if (!m || !t) return false;
  if (!hasBoardRoot(m, t)) return false;
  await ensureCatalog(deps);
  ensureBoards(m, deps);
  bindActions(() => deps);
  return loadTab(m, t, deps, true);
}

export function createCommItemsUiBridge(): CommItemsUiBridge {
  return { onTabOpened, initModule };
}
