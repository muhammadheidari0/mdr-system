import { formatShamsiDate, formatShamsiDateTime } from "./persian_datetime";

type ModuleKey = "contractor" | "consultant" | string;

interface SummaryResponsePayload {
  ok?: boolean;
  stats?: Record<string, unknown>;
}

interface ListResponsePayload {
  ok?: boolean;
  detail?: string;
  data?: unknown;
}

interface MutationResponsePayload {
  ok?: boolean;
  detail?: string;
}

export interface ModuleBoardSummaryFetchResult {
  ok: boolean;
  body: SummaryResponsePayload | null;
}

export interface ModuleBoardListFetchResult {
  ok: boolean;
  body: ListResponsePayload | null;
}

export interface ModuleBoardMutationFetchResult {
  ok: boolean;
  body: MutationResponsePayload | null;
}

export interface ModuleBoardRefreshDeps {
  fetchSummary: (moduleKey: string) => Promise<ModuleBoardSummaryFetchResult>;
}

export interface ModuleBoardOnTabOpenedDeps extends ModuleBoardRefreshDeps {
  initBoards: () => void;
  loadItems: (moduleKey: string, tabKey: string, force: boolean) => Promise<void>;
}

export interface ModuleBoardLoadDeps {
  initBoards: () => void;
  elementByName: (moduleKey: string, tabKey: string, name: string) => HTMLElement | null;
  fetchList: (query: string) => Promise<ModuleBoardListFetchResult>;
  setRowsCache: (moduleKey: string, tabKey: string, rows: Record<string, unknown>[]) => void;
  renderRows: (moduleKey: string, tabKey: string, rows: Record<string, unknown>[]) => void;
}

export interface ModuleBoardSaveDeps {
  canEdit: () => boolean;
  elementByName: (moduleKey: string, tabKey: string, name: string) => HTMLElement | null;
  fetchJson: (endpoint: string, init?: RequestInit) => Promise<ModuleBoardMutationFetchResult>;
  showToast: (message: string, type: string) => void;
  closeForm: (moduleKey: string, tabKey: string) => void;
  loadItems: (moduleKey: string, tabKey: string, force: boolean) => Promise<void>;
  refreshSummary: (moduleKey: string) => Promise<void>;
}

export interface ModuleBoardDeleteDeps {
  canEdit: () => boolean;
  getRow: (moduleKey: string, tabKey: string, itemId: number) => Record<string, unknown> | null;
  confirmAction: (message: string) => boolean;
  fetchJson: (endpoint: string, init?: RequestInit) => Promise<ModuleBoardMutationFetchResult>;
  showToast: (message: string, type: string) => void;
  loadItems: (moduleKey: string, tabKey: string, force: boolean) => Promise<void>;
  refreshSummary: (moduleKey: string) => Promise<void>;
}

export interface ModuleBoardFormDeps {
  canEdit: () => boolean;
  elementByName: (moduleKey: string, tabKey: string, name: string) => HTMLElement | null;
}

export interface ModuleBoardEditDeps extends ModuleBoardFormDeps {
  getRow: (moduleKey: string, tabKey: string, itemId: number) => Record<string, unknown> | null;
  showToast: (message: string, type: string) => void;
}

export interface ModuleBoardBridge {
  key(moduleKey: string, tabKey: string): string;
  canEdit(role: unknown): boolean;
  statusClass(value: unknown): string;
  priorityClass(value: unknown): string;
  formatDate(value: unknown, includeTime?: boolean): string;
  resetForm(moduleKey: string, tabKey: string, deps: ModuleBoardFormDeps): boolean;
  openForm(
    moduleKey: string,
    tabKey: string,
    item: Record<string, unknown> | null | undefined,
    deps: ModuleBoardFormDeps
  ): boolean;
  closeForm(moduleKey: string, tabKey: string, deps: ModuleBoardFormDeps): boolean;
  edit(moduleKey: string, tabKey: string, itemId: number, deps: ModuleBoardEditDeps): boolean;
  load(moduleKey: string, tabKey: string, force: boolean, deps: ModuleBoardLoadDeps): Promise<boolean>;
  save(moduleKey: string, tabKey: string, deps: ModuleBoardSaveDeps): Promise<boolean>;
  delete(moduleKey: string, tabKey: string, itemId: number, deps: ModuleBoardDeleteDeps): Promise<boolean>;
  refreshSummary(moduleKey: string, deps: ModuleBoardRefreshDeps): Promise<boolean>;
  onTabOpened(moduleKey: string, tabKey: string, deps: ModuleBoardOnTabOpenedDeps): Promise<boolean>;
  bindActions(deps: ModuleBoardBindActionsDeps): boolean;
  debouncedLoad(moduleKey: string, tabKey: string, deps: ModuleBoardDebouncedLoadDeps): void;
}

export interface ModuleBoardDebouncedLoadDeps {
  delayMs?: number;
  loadItems: (moduleKey: string, tabKey: string, force: boolean) => void | Promise<void>;
}

export interface ModuleBoardBindActionsDeps {
  openForm: (moduleKey: string, tabKey: string) => void;
  closeForm: (moduleKey: string, tabKey: string) => void;
  saveForm: (moduleKey: string, tabKey: string) => void | Promise<void>;
  loadItems: (moduleKey: string, tabKey: string, force: boolean) => void | Promise<void>;
  editItem: (moduleKey: string, tabKey: string, itemId: number) => void;
  deleteItem: (moduleKey: string, tabKey: string, itemId: number) => void | Promise<void>;
  debouncedLoad: (moduleKey: string, tabKey: string) => void;
}

const CONSULTANT_SUMMARY_MAP: Record<string, string> = {
  total: "consultant-stat-total",
  open: "consultant-stat-open",
  waiting: "consultant-stat-waiting",
  overdue: "consultant-stat-overdue",
};

const CONTRACTOR_SUMMARY_MAP: Record<string, string> = {
  total: "contractor-stat-total",
  open: "contractor-stat-open",
  waiting: "contractor-stat-waiting",
  overdue: "contractor-stat-overdue",
};

let actionListenersBound = false;
const debounceTimers: Record<string, number | undefined> = {};

function normalize(input: unknown): string {
  return String(input || "").trim().toLowerCase();
}

function key(moduleKey: string, tabKey: string): string {
  return `${normalize(moduleKey)}-${normalize(tabKey)}`;
}

function canEdit(role: unknown): boolean {
  return normalize(role) !== "viewer";
}

function statusClass(value: unknown): string {
  return normalize(value).replace(/_/g, "-");
}

function priorityClass(value: unknown): string {
  return normalize(value);
}

function formatDate(value: unknown, includeTime = false): string {
  return includeTime ? formatShamsiDateTime(value) : formatShamsiDate(value);
}

function elementValue(el: HTMLElement | null): string {
  if (!el) return "";
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
    return String(el.value || "").trim();
  }
  return "";
}

function focusElement(el: HTMLElement | null): void {
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
    el.focus();
  }
}

function rowTitle(row: Record<string, unknown> | null, fallbackId: number): string {
  const title = row && typeof row.title === "string" ? row.title.trim() : "";
  return title ? `«${title}»` : `#${Number(fallbackId) || 0}`;
}

function setElementValue(el: HTMLElement | null, value: unknown): void {
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
    el.value = String(value ?? "");
  }
}

function normalizeItem(item: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!item || typeof item !== "object") return null;
  return item;
}

function resetFormInternal(moduleKey: string, tabKey: string, deps: ModuleBoardFormDeps): boolean {
  setElementValue(deps.elementByName(moduleKey, tabKey, "form-id"), "");
  setElementValue(deps.elementByName(moduleKey, tabKey, "form-title"), "");
  setElementValue(deps.elementByName(moduleKey, tabKey, "form-description"), "");
  setElementValue(deps.elementByName(moduleKey, tabKey, "form-project"), "");
  setElementValue(deps.elementByName(moduleKey, tabKey, "form-discipline"), "");
  setElementValue(deps.elementByName(moduleKey, tabKey, "form-status"), "open");
  setElementValue(deps.elementByName(moduleKey, tabKey, "form-priority"), "normal");
  setElementValue(deps.elementByName(moduleKey, tabKey, "form-due"), "");
  return true;
}

function openFormInternal(
  moduleKey: string,
  tabKey: string,
  item: Record<string, unknown> | null | undefined,
  deps: ModuleBoardFormDeps
): boolean {
  if (!deps.canEdit()) return true;

  const wrap = deps.elementByName(moduleKey, tabKey, "form-wrap");
  if (!(wrap instanceof HTMLElement)) return true;

  resetFormInternal(moduleKey, tabKey, deps);
  const normalizedItem = normalizeItem(item);
  if (normalizedItem) {
    setElementValue(deps.elementByName(moduleKey, tabKey, "form-id"), normalizedItem.id ?? "");
    setElementValue(deps.elementByName(moduleKey, tabKey, "form-title"), normalizedItem.title ?? "");
    setElementValue(deps.elementByName(moduleKey, tabKey, "form-description"), normalizedItem.description ?? "");
    setElementValue(deps.elementByName(moduleKey, tabKey, "form-project"), normalizedItem.project_code ?? "");
    setElementValue(deps.elementByName(moduleKey, tabKey, "form-discipline"), normalizedItem.discipline_code ?? "");
    setElementValue(deps.elementByName(moduleKey, tabKey, "form-status"), normalizedItem.status ?? "open");
    setElementValue(deps.elementByName(moduleKey, tabKey, "form-priority"), normalizedItem.priority ?? "normal");
    const dueDate = String(normalizedItem.due_date ?? "").slice(0, 10);
    setElementValue(deps.elementByName(moduleKey, tabKey, "form-due"), dueDate);
  }
  wrap.hidden = false;
  return true;
}

function summaryMap(moduleKey: ModuleKey): Record<string, string> {
  return normalize(moduleKey) === "consultant" ? CONSULTANT_SUMMARY_MAP : CONTRACTOR_SUMMARY_MAP;
}

function resolveContextFromAction(actionEl: HTMLElement | null): { moduleKey: string; tabKey: string } | null {
  if (!actionEl) return null;
  const card = actionEl.closest(".module-crud-card[data-module][data-tab]") as HTMLElement | null;
  if (!card) return null;
  const moduleKey = normalize(card.dataset.module);
  const tabKey = normalize(card.dataset.tab);
  if (!moduleKey || !tabKey) return null;
  return { moduleKey, tabKey };
}

async function invokeMaybeAsync(
  fn: () => void | Promise<void>,
  contextLabel: string
): Promise<void> {
  try {
    await fn();
  } catch (error) {
    console.warn(`moduleBoard action '${contextLabel}' failed:`, error);
  }
}

function applySummaryToDom(moduleKey: string, stats: Record<string, unknown>): void {
  const map = summaryMap(moduleKey);
  Object.entries(map).forEach(([field, id]) => {
    const el = document.getElementById(id);
    if (!el) return;
    const value = Number(stats[field] ?? 0);
    el.textContent = Number.isFinite(value) ? String(value) : "0";
  });
}

async function refreshSummary(moduleKey: string, deps: ModuleBoardRefreshDeps): Promise<boolean> {
  const normalizedModule = normalize(moduleKey);
  if (!normalizedModule) return false;
  try {
    const result = await deps.fetchSummary(normalizedModule);
    if (!result.ok || !result.body?.ok) return false;
    const stats = (result.body.stats || {}) as Record<string, unknown>;
    applySummaryToDom(normalizedModule, stats);
    return true;
  } catch (error) {
    console.warn("moduleBoardRefreshSummary (TS bridge) failed:", error);
    return false;
  }
}

async function onTabOpened(
  moduleKey: string,
  tabKey: string,
  deps: ModuleBoardOnTabOpenedDeps
): Promise<boolean> {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return false;
  deps.initBoards();
  await deps.loadItems(normalizedModule, normalizedTab, true);
  await refreshSummary(normalizedModule, deps);
  return true;
}

function resetForm(moduleKey: string, tabKey: string, deps: ModuleBoardFormDeps): boolean {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return false;
  return resetFormInternal(normalizedModule, normalizedTab, deps);
}

function openForm(
  moduleKey: string,
  tabKey: string,
  item: Record<string, unknown> | null | undefined,
  deps: ModuleBoardFormDeps
): boolean {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return false;
  return openFormInternal(normalizedModule, normalizedTab, item, deps);
}

function closeForm(moduleKey: string, tabKey: string, deps: ModuleBoardFormDeps): boolean {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return false;

  const wrap = deps.elementByName(normalizedModule, normalizedTab, "form-wrap");
  if (wrap instanceof HTMLElement) {
    wrap.hidden = true;
  }
  resetFormInternal(normalizedModule, normalizedTab, deps);
  return true;
}

function edit(moduleKey: string, tabKey: string, itemId: number, deps: ModuleBoardEditDeps): boolean {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return false;

  const normalizedItemId = Number(itemId || 0);
  const row = deps.getRow(normalizedModule, normalizedTab, normalizedItemId);
  if (!row) {
    deps.showToast("آیتم موردنظر یافت نشد.", "error");
    return true;
  }
  return openFormInternal(normalizedModule, normalizedTab, row, deps);
}

async function load(
  moduleKey: string,
  tabKey: string,
  force: boolean,
  deps: ModuleBoardLoadDeps
): Promise<boolean> {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return false;

  deps.initBoards();
  const tbody = deps.elementByName(normalizedModule, normalizedTab, "tbody");
  const emptyEl = deps.elementByName(normalizedModule, normalizedTab, "empty");
  if (!(tbody instanceof HTMLElement) || !(emptyEl instanceof HTMLElement)) {
    return false;
  }

  const params = new URLSearchParams({
    module_key: normalizedModule,
    tab_key: normalizedTab,
    limit: "250",
    skip: "0",
  });

  const searchValue = elementValue(deps.elementByName(normalizedModule, normalizedTab, "filter-search"));
  const statusValue = elementValue(deps.elementByName(normalizedModule, normalizedTab, "filter-status"));
  const projectValue = elementValue(deps.elementByName(normalizedModule, normalizedTab, "filter-project"));
  const disciplineValue = elementValue(deps.elementByName(normalizedModule, normalizedTab, "filter-discipline"));

  if (searchValue) params.set("search", searchValue);
  if (statusValue) params.set("status", statusValue);
  if (projectValue) params.set("project_code", projectValue);
  if (disciplineValue) params.set("discipline_code", disciplineValue);

  if (force) {
    tbody.innerHTML = "";
    emptyEl.textContent = "در حال بارگذاری...";
    emptyEl.style.display = "block";
  }

  try {
    const result = await deps.fetchList(params.toString());
    if (!result.ok || !result.body?.ok) {
      throw new Error(result.body?.detail || "Failed to load workboard items.");
    }

    const rows = (Array.isArray(result.body.data) ? result.body.data : []) as Record<string, unknown>[];
    deps.setRowsCache(normalizedModule, normalizedTab, rows);

    if (!rows.length) {
      tbody.innerHTML = "";
      emptyEl.textContent = "آیتمی یافت نشد.";
      emptyEl.style.display = "block";
      return true;
    }

    deps.renderRows(normalizedModule, normalizedTab, rows);
    emptyEl.style.display = "none";
    return true;
  } catch (error) {
    console.error("moduleBoardLoad failed:", error);
    tbody.innerHTML = "";
    emptyEl.textContent = error instanceof Error && error.message
      ? error.message
      : "خطا در بارگذاری آیتم‌ها.";
    emptyEl.style.display = "block";
    return true;
  }
}

async function save(
  moduleKey: string,
  tabKey: string,
  deps: ModuleBoardSaveDeps
): Promise<boolean> {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return false;

  if (!deps.canEdit()) return true;

  const idInput = deps.elementByName(normalizedModule, normalizedTab, "form-id");
  const titleInput = deps.elementByName(normalizedModule, normalizedTab, "form-title");
  const descInput = deps.elementByName(normalizedModule, normalizedTab, "form-description");
  const projectSelect = deps.elementByName(normalizedModule, normalizedTab, "form-project");
  const disciplineSelect = deps.elementByName(normalizedModule, normalizedTab, "form-discipline");
  const statusSelect = deps.elementByName(normalizedModule, normalizedTab, "form-status");
  const prioritySelect = deps.elementByName(normalizedModule, normalizedTab, "form-priority");
  const dueInput = deps.elementByName(normalizedModule, normalizedTab, "form-due");

  const title = elementValue(titleInput);
  if (!title) {
    deps.showToast("عنوان آیتم الزامی است.", "error");
    focusElement(titleInput);
    return true;
  }

  const dueDate = elementValue(dueInput);
  const payload = {
    module_key: normalizedModule,
    tab_key: normalizedTab,
    title,
    description: elementValue(descInput) || null,
    project_code: elementValue(projectSelect) || null,
    discipline_code: elementValue(disciplineSelect) || null,
    status: elementValue(statusSelect) || "open",
    priority: elementValue(prioritySelect) || "normal",
    due_date: dueDate || null,
  };

  const itemId = Number(elementValue(idInput) || 0);
  const endpoint = itemId > 0 ? `/api/v1/workboard/${itemId}` : "/api/v1/workboard/create";
  const method = itemId > 0 ? "PUT" : "POST";

  try {
    const result = await deps.fetchJson(endpoint, {
      method,
      body: JSON.stringify(payload),
    });
    if (!result.ok || !result.body?.ok) {
      throw new Error(result.body?.detail || "خطا در ذخیره آیتم.");
    }
    deps.showToast(itemId > 0 ? "آیتم بروزرسانی شد." : "آیتم جدید ثبت شد.", "success");
    deps.closeForm(normalizedModule, normalizedTab);
    await deps.loadItems(normalizedModule, normalizedTab, true);
    await deps.refreshSummary(normalizedModule);
    return true;
  } catch (error) {
    console.error("moduleBoardSave failed:", error);
    deps.showToast(
      error instanceof Error && error.message ? error.message : "خطا در ذخیره آیتم.",
      "error"
    );
    return true;
  }
}

async function remove(
  moduleKey: string,
  tabKey: string,
  itemId: number,
  deps: ModuleBoardDeleteDeps
): Promise<boolean> {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return false;

  if (!deps.canEdit()) return true;

  const normalizedItemId = Number(itemId || 0);
  const row = deps.getRow(normalizedModule, normalizedTab, normalizedItemId);
  const title = rowTitle(row, normalizedItemId);
  if (!deps.confirmAction(`آیا از حذف آیتم ${title} مطمئن هستید؟`)) return true;

  try {
    const result = await deps.fetchJson(`/api/v1/workboard/${normalizedItemId}`, { method: "DELETE" });
    if (!result.ok || !result.body?.ok) {
      throw new Error(result.body?.detail || "خطا در حذف آیتم.");
    }
    deps.showToast("آیتم حذف شد.", "success");
    await deps.loadItems(normalizedModule, normalizedTab, true);
    await deps.refreshSummary(normalizedModule);
    return true;
  } catch (error) {
    console.error("moduleBoardDelete failed:", error);
    deps.showToast(
      error instanceof Error && error.message ? error.message : "خطا در حذف آیتم.",
      "error"
    );
    return true;
  }
}

function debouncedLoad(moduleKey: string, tabKey: string, deps: ModuleBoardDebouncedLoadDeps): void {
  const normalizedModule = normalize(moduleKey);
  const normalizedTab = normalize(tabKey);
  if (!normalizedModule || !normalizedTab) return;

  const timerKey = key(normalizedModule, normalizedTab);
  const delay = Number.isFinite(Number(deps.delayMs)) ? Number(deps.delayMs) : 420;
  const existingTimer = debounceTimers[timerKey];
  if (existingTimer) {
    window.clearTimeout(existingTimer);
  }

  debounceTimers[timerKey] = window.setTimeout(() => {
    void invokeMaybeAsync(
      () => deps.loadItems(normalizedModule, normalizedTab, false),
      "debounced-load"
    );
  }, delay);
}

function bindActions(deps: ModuleBoardBindActionsDeps): boolean {
  if (actionListenersBound) return true;
  actionListenersBound = true;

  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-mb-action]") as HTMLElement | null;
    if (!actionEl) return;
    const action = normalize(actionEl.dataset.mbAction);
    if (!action) return;

    const context = resolveContextFromAction(actionEl);
    if (!context) return;

    switch (action) {
      case "open-form":
        deps.openForm(context.moduleKey, context.tabKey);
        break;
      case "close-form":
        deps.closeForm(context.moduleKey, context.tabKey);
        break;
      case "save-form":
        void invokeMaybeAsync(
          () => deps.saveForm(context.moduleKey, context.tabKey),
          "save-form"
        );
        break;
      case "load":
        void invokeMaybeAsync(
          () =>
            deps.loadItems(
              context.moduleKey,
              context.tabKey,
              normalize(actionEl.dataset.force) === "true"
            ),
          "load"
        );
        break;
      case "edit-item":
        deps.editItem(context.moduleKey, context.tabKey, Number(actionEl.dataset.itemId || 0));
        break;
      case "delete-item":
        void invokeMaybeAsync(
          () => deps.deleteItem(context.moduleKey, context.tabKey, Number(actionEl.dataset.itemId || 0)),
          "delete-item"
        );
        break;
      default:
        break;
    }
  });

  document.addEventListener("change", (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-mb-action]") as HTMLElement | null;
    if (!actionEl) return;
    const action = normalize(actionEl.dataset.mbAction);
    if (!["filter-project", "filter-discipline", "filter-status"].includes(action)) return;

    const context = resolveContextFromAction(actionEl);
    if (!context) return;
    void invokeMaybeAsync(
      () => deps.loadItems(context.moduleKey, context.tabKey, true),
      "filter-change"
    );
  });

  document.addEventListener("input", (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-mb-action]") as HTMLElement | null;
    if (!actionEl) return;
    const action = normalize(actionEl.dataset.mbAction);
    if (action !== "filter-search") return;

    const context = resolveContextFromAction(actionEl);
    if (!context) return;
    deps.debouncedLoad(context.moduleKey, context.tabKey);
  });

  return true;
}

export function createModuleBoardBridge(): ModuleBoardBridge {
  return {
    key,
    canEdit,
    statusClass,
    priorityClass,
    formatDate,
    resetForm,
    openForm,
    closeForm,
    edit,
    load,
    save,
    delete: remove,
    refreshSummary,
    onTabOpened,
    bindActions,
    debouncedLoad,
  };
}
