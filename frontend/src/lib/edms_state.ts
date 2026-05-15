type EdmsTabName = "archive" | "transmittal" | "correspondence" | "meeting_minutes" | "forms";
type EdmsViewId = "view-archive" | "view-transmittal" | "view-correspondence" | "view-meeting-minutes" | "view-edms-forms";

interface NavigationPayload {
  edms_tabs?: Partial<Record<EdmsTabName, boolean>>;
  default_edms_tab?: string;
}

interface HeaderStatsPayload {
  [key: string]: unknown;
}

export interface LoadNavigationOptions {
  role: unknown;
  fetchNavigation: () => Promise<unknown | null>;
}

export interface ApplyTabVisibilityOptions {
  setTabButtonVisible: (tabName: string, visible: boolean) => void;
  setPanelVisible: (viewId: string, visible: boolean) => void;
  setNavVisible: (visible: boolean) => void;
}

export interface LoadNavigationAndApplyOptions extends LoadNavigationOptions {
  applyVisibility: () => void;
}

export interface LoadHeaderStatsOptions {
  force: boolean;
  now: number;
  cacheMs: number;
  fetchStats: () => Promise<unknown | null>;
  applyStats: (payload: HeaderStatsPayload) => void;
}

export interface OpenEdmsTabOptions {
  tabName: string;
  button?: HTMLElement | null;
  userId: unknown;
  role: unknown;
  showAccessDenied: () => void;
  setPanelState: (viewId: string, active: boolean) => void;
  clearButtons: () => void;
  activateButton: (tabName: string, button?: HTMLElement | null) => void;
  onTabActivated: (tabName: string) => void;
  setLegacyPendingTab?: (tabName: string) => void;
}

export interface EdmsStateBridge {
  mapToRoutedView(viewId: string): string;
  consumePendingEdmsTab(): string | null;
  getPendingEdmsTab(): string | null;
  setPendingEdmsTab(tabName: string | null): void;
  isTabVisible(tabName: string): boolean;
  getFirstVisibleTab(): string | null;
  getEffectiveDefaultTab(): string | null;
  loadLastTab(userId: unknown, role: unknown): string | null;
  saveLastTab(tabName: string, userId: unknown, role: unknown): void;
  loadNavigation(options: LoadNavigationOptions): Promise<void>;
  applyTabVisibility(options: ApplyTabVisibilityOptions): boolean;
  loadNavigationAndApply(options: LoadNavigationAndApplyOptions): Promise<boolean>;
  beginHeaderStatsLoad(force: boolean, now: number, cacheMs: number): boolean;
  endHeaderStatsLoad(success: boolean, now: number): void;
  loadHeaderStats(options: LoadHeaderStatsOptions): Promise<boolean>;
  openTab(options: OpenEdmsTabOptions): boolean;
}

const TAB_TO_VIEW: Record<EdmsTabName, EdmsViewId> = {
  archive: "view-archive",
  transmittal: "view-transmittal",
  correspondence: "view-correspondence",
  meeting_minutes: "view-meeting-minutes",
  forms: "view-edms-forms",
};

const VIEW_TO_TAB: Record<EdmsViewId, EdmsTabName> = {
  "view-archive": "archive",
  "view-transmittal": "transmittal",
  "view-correspondence": "correspondence",
  "view-meeting-minutes": "meeting_minutes",
  "view-edms-forms": "forms",
};

const TAB_ORDER: EdmsTabName[] = ["archive", "transmittal", "correspondence", "meeting_minutes", "forms"];

function normalizeTabName(input: unknown): EdmsTabName | null {
  const value = String(input || "").trim().toLowerCase();
  if (!value) return null;
  return value in TAB_TO_VIEW ? (value as EdmsTabName) : null;
}

function normalizeViewId(input: unknown): string {
  return String(input || "").trim();
}

function normalizeRole(input: unknown): string {
  return String(input || "").trim().toLowerCase();
}

function toNavigationPayload(input: unknown): NavigationPayload | null {
  if (!input || typeof input !== "object") return null;
  return input as NavigationPayload;
}

function createStorageKey(userId: unknown, role: unknown): string {
  const normalizedUserId = String(userId ?? "").trim();
  if (normalizedUserId) {
    return `edms_last_tab_user_${normalizedUserId}`;
  }
  const normalizedRole = normalizeRole(role) || "unknown";
  return `edms_last_tab_role_${normalizedRole}`;
}

export function createEdmsStateBridge(): EdmsStateBridge {
  let pendingEdmsTab: EdmsTabName | null = null;
  let defaultEdmsTab: EdmsTabName = "archive";
  let visibility: Record<EdmsTabName, boolean> = {
    archive: true,
    transmittal: true,
    correspondence: true,
    meeting_minutes: true,
    forms: true,
  };
  let headerStatsLoading = false;
  let headerStatsLastLoadedAt = 0;

  function setFallbackByRole(role: string): void {
    defaultEdmsTab = role === "dcc" || role === "manager" ? "transmittal" : "archive";
    visibility = {
      archive: true,
      transmittal: true,
      correspondence: true,
      meeting_minutes: true,
      forms: true,
    };
  }

  function mapToRoutedView(viewId: string): string {
    const requested = normalizeViewId(viewId);
    if (!requested) return "";
    const mappedTab = VIEW_TO_TAB[requested as EdmsViewId];
    if (mappedTab) {
      pendingEdmsTab = mappedTab;
      return "view-edms";
    }
    return requested;
  }

  function consumePendingEdmsTab(): string | null {
    const value = pendingEdmsTab;
    pendingEdmsTab = null;
    return value;
  }

  function getPendingEdmsTab(): string | null {
    return pendingEdmsTab;
  }

  function setPendingEdmsTab(tabName: string | null): void {
    pendingEdmsTab = normalizeTabName(tabName);
  }

  function isTabVisible(tabName: string): boolean {
    const normalized = normalizeTabName(tabName);
    if (!normalized) return false;
    return visibility[normalized] !== false;
  }

  function getFirstVisibleTab(): string | null {
    return TAB_ORDER.find((tab) => isTabVisible(tab)) || null;
  }

  function getEffectiveDefaultTab(): string | null {
    if (isTabVisible(defaultEdmsTab)) {
      return defaultEdmsTab;
    }
    return getFirstVisibleTab();
  }

  function loadLastTab(userId: unknown, role: unknown): string | null {
    try {
      const key = createStorageKey(userId, role);
      const value = localStorage.getItem(key);
      return normalizeTabName(value);
    } catch (error) {
      console.warn("Failed to load EDMS last tab.", error);
      return null;
    }
  }

  function saveLastTab(tabName: string, userId: unknown, role: unknown): void {
    const normalized = normalizeTabName(tabName);
    if (!normalized) return;
    try {
      const key = createStorageKey(userId, role);
      localStorage.setItem(key, normalized);
    } catch (error) {
      console.warn("Failed to persist EDMS last tab.", error);
    }
  }

  async function loadNavigation(options: LoadNavigationOptions): Promise<void> {
    const role = normalizeRole(options.role);
    setFallbackByRole(role);

    try {
      const payload = toNavigationPayload(await options.fetchNavigation());
      if (!payload) return;

      const tabs = payload.edms_tabs || {};
      visibility = {
        archive: tabs.archive !== false,
        transmittal: tabs.transmittal !== false,
        correspondence: tabs.correspondence !== false,
        meeting_minutes: tabs.meeting_minutes !== false,
        forms: tabs.forms !== false,
      };

      const apiDefault = normalizeTabName(payload.default_edms_tab);
      if (apiDefault) {
        defaultEdmsTab = apiDefault;
      }
    } catch (error) {
      console.warn("Failed to load EDMS navigation permissions, using fallback.", error);
    }
  }

  function applyTabVisibility(options: ApplyTabVisibilityOptions): boolean {
    let hasVisibleTab = false;

    Object.entries(TAB_TO_VIEW).forEach(([tabName, viewId]) => {
      const visible = isTabVisible(tabName);
      options.setTabButtonVisible(tabName, visible);
      options.setPanelVisible(viewId, visible);
      hasVisibleTab = hasVisibleTab || visible;
    });

    options.setNavVisible(hasVisibleTab);
    return true;
  }

  async function loadNavigationAndApply(options: LoadNavigationAndApplyOptions): Promise<boolean> {
    await loadNavigation(options);
    options.applyVisibility();
    return true;
  }

  function beginHeaderStatsLoad(force: boolean, now: number, cacheMs: number): boolean {
    if (!force && headerStatsLoading) return false;
    if (!force && headerStatsLastLoadedAt && now - headerStatsLastLoadedAt < cacheMs) return false;
    headerStatsLoading = true;
    return true;
  }

  function endHeaderStatsLoad(success: boolean, now: number): void {
    headerStatsLoading = false;
    if (success) {
      headerStatsLastLoadedAt = now;
    }
  }

  async function loadHeaderStats(options: LoadHeaderStatsOptions): Promise<boolean> {
    if (!beginHeaderStatsLoad(options.force, options.now, options.cacheMs)) {
      return true;
    }

    let loadSucceeded = false;
    try {
      const payload = await options.fetchStats();
      if (payload && typeof payload === "object") {
        options.applyStats(payload as HeaderStatsPayload);
        loadSucceeded = true;
      }
      return true;
    } catch (error) {
      console.warn("Failed to load EDMS header stats.", error);
      return true;
    } finally {
      endHeaderStatsLoad(loadSucceeded, Date.now());
    }
  }

  function openTab(options: OpenEdmsTabOptions): boolean {
    const normalized = normalizeTabName(options.tabName);
    if (!normalized) return false;
    if (!isTabVisible(normalized)) {
      return false;
    }

    Object.entries(TAB_TO_VIEW).forEach(([tabName, viewId]) => {
      options.setPanelState(viewId, tabName === normalized);
    });

    options.clearButtons();
    options.activateButton(normalized, options.button || null);

    pendingEdmsTab = normalized;
    if (options.setLegacyPendingTab) {
      options.setLegacyPendingTab(normalized);
    }

    options.onTabActivated(normalized);
    saveLastTab(normalized, options.userId, options.role);
    return true;
  }

  return {
    mapToRoutedView,
    consumePendingEdmsTab,
    getPendingEdmsTab,
    setPendingEdmsTab,
    isTabVisible,
    getFirstVisibleTab,
    getEffectiveDefaultTab,
    loadLastTab,
    saveLastTab,
    loadNavigation,
    applyTabVisibility,
    loadNavigationAndApply,
    beginHeaderStatsLoad,
    endHeaderStatsLoad,
    loadHeaderStats,
    openTab,
  };
}
