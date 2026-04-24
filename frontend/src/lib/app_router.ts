export interface AppRouterDeps {
  mapToRoutedView: (viewId: string) => string;
  requireAuth: () => boolean;
  requireAdmin: () => boolean;
  isAdminOnlyView: (viewId: string) => boolean;
  setPendingSettingsTab: (tab: string | null) => void;
  getPendingSettingsTab: () => string | null;
  clearPendingSettingsTab: () => void;
  getPendingEdmsTab: () => string | null;
  markPerf: (name: string) => void;
  measurePerf: (metricName: string, startMark: string, endMark: string) => void;
  renderDevPerformancePanel: () => void;
  loadViewPartial: (viewId: string) => Promise<boolean>;
  activateView: (viewId: string) => HTMLElement | null;
  runViewInitializer: (viewId: string) => Promise<boolean>;
  initDashboard: () => void;
  loadEdmsLastTab: () => string | null;
  getEffectiveDefaultEdmsTab: () => string | null;
  isEdmsTabVisible: (tabName: string) => boolean;
  getFirstVisibleEdmsTab: () => string | null;
  openEdmsTab: (tabName: string) => void;
  loadEdmsHeaderStats: () => void;
  showToast: (message: string, type?: string) => void;
  initReportsView: () => void;
  initContractorView: () => void;
  initConsultantView: () => void;
  initModuleSettingsView: () => void;
  openSettingsTab: (tabName: string) => void;
  initUserSettingsView: () => void;
  initDocumentDetailView: () => void;
  emitViewActivated: (viewId: string) => void;
  updateSidebarState: (viewId: string) => void;
}

export interface AppRouterBridge {
  navigateTo: (viewId: string, deps: AppRouterDeps) => Promise<boolean>;
  runViewInitializer: (viewId: string) => Promise<boolean>;
  activateView: (viewId: string) => HTMLElement | null;
}

function normalizeViewId(viewId: unknown): string {
  return String(viewId || "").trim();
}

function resolveRequestedEdmsTab(deps: AppRouterDeps): string {
  const requested = normalizeViewId(deps.getPendingEdmsTab());
  if (requested) return requested;

  const lastSaved = normalizeViewId(deps.loadEdmsLastTab());
  if (lastSaved) return lastSaved;

  const effectiveDefault = normalizeViewId(deps.getEffectiveDefaultEdmsTab());
  return effectiveDefault || "archive";
}

async function runViewInitializerForRoute(routedViewId: string, deps: AppRouterDeps): Promise<boolean> {
  switch (routedViewId) {
    case "view-dashboard":
      deps.initDashboard();
      return true;
    case "view-edms": {
      const requestedTab = resolveRequestedEdmsTab(deps);
      const safeTab = deps.isEdmsTabVisible(requestedTab)
        ? requestedTab
        : normalizeViewId(deps.getFirstVisibleEdmsTab());
      if (safeTab) {
        deps.openEdmsTab(safeTab);
        deps.loadEdmsHeaderStats();
        return true;
      }
      deps.showToast("هیچ تب فعالی برای EDMS در دسترس نیست.", "error");
      return false;
    }
    case "view-reports":
      deps.initReportsView();
      return true;
    case "view-contractor":
      deps.initContractorView();
      return true;
    case "view-consultant":
      deps.initConsultantView();
      return true;
    case "view-edms-settings":
      deps.initModuleSettingsView();
      return true;
    case "view-contractor-settings":
      return true;
    case "view-consultant-settings":
      return true;
    case "view-settings": {
      const targetTab = normalizeViewId(deps.getPendingSettingsTab()) || "users";
      deps.clearPendingSettingsTab();
      deps.openSettingsTab(targetTab);
      return true;
    }
    case "view-profile":
      deps.initUserSettingsView();
      return true;
    case "view-document-detail":
      deps.initDocumentDetailView();
      return true;
    default:
      return true;
  }
}

async function navigateToInternal(viewId: string, deps: AppRouterDeps): Promise<boolean> {
  const requestedViewId = normalizeViewId(viewId);
  if (!requestedViewId) return false;

  const routedViewId = normalizeViewId(deps.mapToRoutedView(requestedViewId));
  if (!routedViewId) return false;
  console.log("Navigating to:", routedViewId);

  if (routedViewId !== "view-login" && !deps.requireAuth()) {
    return false;
  }

  if (routedViewId === "view-users" || routedViewId === "view-bulk") {
    if (!deps.requireAdmin()) return false;
    deps.setPendingSettingsTab(routedViewId === "view-users" ? "users" : "bulk");
    return navigateToInternal("view-settings", deps);
  }

  if (deps.isAdminOnlyView(routedViewId) && !deps.requireAdmin()) {
    return false;
  }

  deps.markPerf("view_switch_start");
  const loaded = await deps.loadViewPartial(routedViewId);
  if (!loaded) return false;

  const target = deps.activateView(routedViewId);
  if (!target) return false;

  const initializerOk = await runViewInitializerForRoute(routedViewId, deps);
  if (!initializerOk) {
    await navigateToInternal("view-dashboard", deps);
    return false;
  }

  deps.markPerf("view_switch_end");
  deps.measurePerf("view_switch", "view_switch_start", "view_switch_end");
  deps.renderDevPerformancePanel();
  deps.emitViewActivated(routedViewId);
  deps.updateSidebarState(routedViewId);
  return true;
}

export function createAppRouterBridge(): AppRouterBridge {
  return {
    navigateTo: navigateToInternal,
    runViewInitializer: async (viewId: string): Promise<boolean> => {
      const normalized = normalizeViewId(viewId);
      if (!normalized) return false;
      return false;
    },
    activateView: (viewId: string): HTMLElement | null => {
      const normalized = normalizeViewId(viewId);
      if (!normalized) return null;
      document.querySelectorAll(".view-section").forEach((el) => {
        (el as HTMLElement).style.display = "none";
        el.classList.remove("active");
      });

      const target = document.getElementById(normalized);
      if (!target) return null;
      target.style.display = "block";
      target.classList.add("active");
      return target;
    },
  };
}
