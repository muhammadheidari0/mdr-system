export interface AppShellListenerOptions {
  navigateTo?: (viewId: string) => void | Promise<void>;
  logout?: () => void;
}

export interface AppShellBridge {
  isPublicPage(pathname: string): boolean;
  setupGlobalListeners(options?: AppShellListenerOptions): void;
  updateSidebarState(activeViewId: string): void;
  toggleSidebar(): void;
  toggleUserMenu(): void;
}

const PUBLIC_PAGES = new Set(["/login", "/debug_login"]);
let listenersBound = false;

function normalizeViewId(input: string): string {
  const value = String(input || "").trim();
  if (!value) return "";
  return value.startsWith("view-") ? value : `view-${value}`;
}

function mapSidebarTarget(activeViewId: string): string {
  const normalized = normalizeViewId(activeViewId);
  if (normalized === "view-users" || normalized === "view-bulk") {
    return "view-settings";
  }
  if (normalized === "view-edms-settings") {
    return "view-edms";
  }
  if (normalized === "view-contractor-settings") {
    return "view-contractor";
  }
  if (normalized === "view-consultant-settings") {
    return "view-consultant";
  }
  if (
    normalized === "view-archive" ||
    normalized === "view-transmittal" ||
    normalized === "view-correspondence" ||
    normalized === "view-document-detail"
  ) {
    return "view-edms";
  }
  return normalized;
}

function isPublicPage(pathname: string): boolean {
  const normalized = String(pathname || "").trim() || "/";
  return PUBLIC_PAGES.has(normalized);
}

function toggleSidebar(): void {
  const sidebar = document.getElementById("app-sidebar");
  if (!sidebar) return;
  const overlay = document.getElementById("sidebar-overlay");

  if (window.innerWidth <= 992) {
    sidebar.classList.toggle("open");
    if (overlay) overlay.classList.toggle("show");
    return;
  }

  document.body.classList.toggle("sidebar-closed");
  const isClosed = document.body.classList.contains("sidebar-closed");
  document.cookie = `sidebar_status=${isClosed ? "closed" : "open"}; path=/; max-age=31536000`;
}

function toggleUserMenu(): void {
  const dropdown = document.getElementById("user-dropdown");
  if (dropdown) {
    dropdown.classList.toggle("show");
  }
}

function updateSidebarState(activeViewId: string): void {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.remove("active");
  });

  const navTargetView = mapSidebarTarget(activeViewId);
  if (!navTargetView) return;

  const id = `nav-${navTargetView.replace("view-", "")}`;
  const activeNavItem = document.getElementById(id);
  if (activeNavItem) {
    activeNavItem.classList.add("active");
  }
}

function setupGlobalListeners(options?: AppShellListenerOptions): void {
  if (listenersBound) return;
  listenersBound = true;

  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    if (!target) return;

    const navTrigger = target.closest("[data-nav-target]") as HTMLElement | null;
    if (navTrigger) {
      event.preventDefault();
      const viewId = String(navTrigger.getAttribute("data-nav-target") || "").trim();
      if (viewId) {
        void options?.navigateTo?.(viewId);
      }
      return;
    }

    const uiAction = target.closest("[data-ui-action]") as HTMLElement | null;
    if (uiAction) {
      event.preventDefault();
      const action = String(uiAction.getAttribute("data-ui-action") || "")
        .trim()
        .toLowerCase();
      if (action === "toggle-sidebar") {
        toggleSidebar();
        return;
      }
      if (action === "toggle-user-menu") {
        toggleUserMenu();
        return;
      }
      if (action === "logout") {
        options?.logout?.();
        return;
      }
    }

    if (!target.closest(".user-menu-container")) {
      const dropdown = document.getElementById("user-dropdown");
      if (dropdown) dropdown.classList.remove("show");
    }

    if (!target.closest(".context-menu") && !target.closest(".action-btn")) {
      const ctxMenu = document.getElementById("context-menu");
      if (ctxMenu) ctxMenu.classList.remove("show");
    }

    if (window.innerWidth <= 992) {
      if (!target.closest(".sidebar") && !target.closest(".menu-toggle")) {
        const sidebar = document.getElementById("app-sidebar");
        if (sidebar && sidebar.classList.contains("open")) {
          toggleSidebar();
        }
      }
    }
  });
}

export function createAppShellBridge(): AppShellBridge {
  return {
    isPublicPage,
    setupGlobalListeners,
    updateSidebarState,
    toggleSidebar,
    toggleUserMenu,
  };
}
