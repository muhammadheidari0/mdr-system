export interface AppBootDeps {
  isPublicPage: (pathname: string) => boolean;
  toggleLoader: (show: boolean) => void;
  primeLoadedScriptCache: () => void;
  loadDictionary: () => Promise<void>;
  loadEdmsNavigation: () => Promise<void>;
  resolveInitialView?: () => string;
  navigateTo: (viewId: string) => Promise<void>;
  markPerf: (name: string) => void;
  measurePerf: (metricName: string, startMark: string, endMark: string) => void;
  renderDevPerformancePanel: () => void;
  setupGlobalListeners: () => void;
  onDashboardRefresh: () => void;
}

export interface AppBootBridge {
  runOnLoad: (pathname: string, deps: AppBootDeps) => Promise<boolean>;
}

let dashboardRefreshBound = false;

function bindDashboardRefreshListener(onRefresh: () => void): void {
  if (dashboardRefreshBound) return;
  dashboardRefreshBound = true;

  window.addEventListener("message", (event) => {
    if (event?.data !== "refreshDashboard") return;
    onRefresh();
  });
}

async function runOnLoad(pathname: string, deps: AppBootDeps): Promise<boolean> {
  const path = String(pathname || "").trim() || "/";
  if (deps.isPublicPage(path)) {
    console.log("Skipping app init on public page:", path);
    return true;
  }

  deps.toggleLoader(true);
  try {
    deps.primeLoadedScriptCache();
    await deps.loadDictionary();
    await deps.loadEdmsNavigation();
    const initialView = String(deps.resolveInitialView?.() || "").trim() || "view-dashboard";
    await deps.navigateTo(initialView);

    deps.markPerf("first_view_ready");
    deps.measurePerf("app_boot", "app_boot_start", "first_view_ready");
    deps.renderDevPerformancePanel();

    deps.setupGlobalListeners();
    bindDashboardRefreshListener(deps.onDashboardRefresh);
    return true;
  } finally {
    deps.toggleLoader(false);
  }
}

export function createAppBootBridge(): AppBootBridge {
  return {
    runOnLoad,
  };
}
