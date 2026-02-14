// @ts-nocheck
/**
 * MDR System - Main Application Logic
 * Path: frontend/src/legacy_runtime/app.ts
 * Version: 2.4 Final (Responsive Sidebar & Reports Added)
 */

// ðŸ›‘ Ú¯Ø§Ø±Ø¯ Ø§ÛŒÙ…Ù†ÛŒ: Ø§Ú¯Ø± Ø¯Ø± ØµÙØ­Ù‡ Ù„Ø§Ú¯ÛŒÙ† Ù‡Ø³ØªÛŒÙ…ØŒ Ú©Ø¯Ù‡Ø§ÛŒ Ø§ØµÙ„ÛŒ Ø¨Ø±Ù†Ø§Ù…Ù‡ Ø±Ø§ Ø§Ø¬Ø±Ø§ Ù†Ú©Ù†
const CURRENT_PATH = String(window.location.pathname || "").trim();
const IS_LOGIN_PAGE = CURRENT_PATH === "/login";
const IS_DEBUG_LOGIN_PAGE = CURRENT_PATH === "/debug_login";
const IS_BULK_REGISTER_PAGE = CURRENT_PATH.startsWith("/api/v1/mdr/bulk-register-page");
const HAS_MAIN_SHELL = Boolean(document.getElementById("view-dashboard"));

if (IS_LOGIN_PAGE || IS_DEBUG_LOGIN_PAGE || IS_BULK_REGISTER_PAGE || !HAS_MAIN_SHELL) {
    window.__SKIP_APP_BOOT = true;
}

const STRICT_BRIDGE_MODE = window.__SKIP_APP_BOOT !== true;

function requireBridge(bridge, name) {
    if (!STRICT_BRIDGE_MODE) {
        return bridge || null;
    }
    if (!bridge || typeof bridge !== 'object') {
        throw new Error(`${name} bridge unavailable.`);
    }
    return bridge;
}

const APP_RUNTIME = (window.AppRuntime && typeof window.AppRuntime === 'object')
    ? window.AppRuntime
    : null;

const TS_APP_SHELL = requireBridge(APP_RUNTIME?.appShell, 'App shell');
const TS_APP_BOOT = requireBridge(APP_RUNTIME?.appBoot, 'App boot');
const TS_APP_ROUTER = requireBridge(APP_RUNTIME?.appRouter, 'App router');
const TS_EDMS_STATE = requireBridge(APP_RUNTIME?.edmsState, 'EDMS state');
const TS_MODULE_BOARD = requireBridge(APP_RUNTIME?.moduleBoard, 'Module board');
const TS_MODULE_TABS = requireBridge(APP_RUNTIME?.moduleTabs, 'Module tabs');
const TS_VIEW_LOADER = requireBridge(APP_RUNTIME?.viewLoader, 'View loader');
const TS_APP_DATA = requireBridge(APP_RUNTIME?.appData, 'App data');

const API_BASE = '/api/v1'; 
window.CACHE = {}; // Ú©Ø´ Ø¨Ø±Ø§ÛŒ Ù†Ú¯Ù‡Ø¯Ø§Ø±ÛŒ Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ù¾Ø§ÛŒÙ‡ (Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§ Ùˆ...)
let SELECTED_DOC_ID = null; // Ø¨Ø±Ø§ÛŒ Ù…Ù†ÙˆÛŒ Ø±Ø§Ø³Øª Ú©Ù„ÛŒÚ©

// Ù„ÛŒØ³Øª ØªÙ…Ø§Ù… Ù†Ù…Ø§Ù‡Ø§ÛŒ Ø³ÛŒØ³ØªÙ…
let PENDING_SETTINGS_TAB = null;
let PENDING_EDMS_TAB = null;
let EDMS_DEFAULT_TAB = 'archive';
let EDMS_TAB_VISIBILITY = {
    archive: true,
    transmittal: true,
    correspondence: true,
};
let EDMS_STATS_LOADING = false;
let EDMS_STATS_LAST_LOADED_AT = 0;

const EDMS_TAB_TO_VIEW = {
    archive: 'view-archive',
    transmittal: 'view-transmittal',
    correspondence: 'view-correspondence',
};

const EDMS_VIEW_TO_TAB = {
    'view-archive': 'archive',
    'view-transmittal': 'transmittal',
    'view-correspondence': 'correspondence',
};

const CONTRACTOR_TAB_TO_PANEL = {
    execution: 'contractor-panel-execution',
    requests: 'contractor-panel-requests',
    quality: 'contractor-panel-quality',
};

const CONSULTANT_TAB_TO_PANEL = {
    inspection: 'consultant-panel-inspection',
    defects: 'consultant-panel-defects',
    instructions: 'consultant-panel-instructions',
    control: 'consultant-panel-control',
};

const WORKBOARD_STATUS_LABELS = {
    open: 'باز',
    in_progress: 'در حال انجام',
    waiting: 'در انتظار',
    done: 'انجام‌شده',
    blocked: 'مسدود',
};

const WORKBOARD_PRIORITY_LABELS = {
    low: 'کم',
    normal: 'نرمال',
    high: 'بالا',
    urgent: 'فوری',
};

const WORKBOARD_STATE = {
    initialized: false,
    actionsBound: false,
    timers: {},
    rowsByKey: {},
};

const VIEW_IDS = [
    'view-dashboard',
    'view-edms',
    'view-reports',
    'view-contractor',
    'view-consultant',
    'view-profile',
    'view-settings'
];

const ADMIN_ONLY_VIEWS = new Set([
    'view-users',
    'view-bulk',
    'view-settings'
]);

const VIEW_PARTIALS = {
    'view-dashboard': 'dashboard',
    'view-edms': 'edms',
    'view-reports': 'reports',
    'view-contractor': 'contractor',
    'view-consultant': 'consultant',
    'view-profile': 'profile',
    'view-settings': 'settings',
};

const VIEW_LOAD_CACHE = new Set(['view-dashboard']);
const LOADED_PARTIAL_SCRIPTS = new Set();
const PERF_METRICS = {};
const PERF_PANEL_ID = 'dev-performance-panel';

if (window.performance?.mark) {
    window.performance.mark('app_boot_start');
}

function buildBootDeps() {
    return {
        isPublicPage: (pathname) => TS_APP_SHELL?.isPublicPage?.(pathname) || false,
        toggleLoader: (show) => toggleLoader(show),
        primeLoadedScriptCache: () => primeLoadedScriptCache(),
        loadDictionary: () => loadDictionary(),
        loadEdmsNavigation: () => loadEdmsNavigation(),
        navigateTo: (viewId) => navigateTo(viewId),
        markPerf: (name) => markPerf(name),
        measurePerf: (metricName, startMark, endMark) => measurePerf(metricName, startMark, endMark),
        renderDevPerformancePanel: () => renderDevPerformancePanel(),
        setupGlobalListeners: () => setupGlobalListeners(),
        onDashboardRefresh: () => {
            console.log("Dashboard refresh requested from iframe.");
            if (typeof initDashboard === 'function') initDashboard();
            showToast('عملیات ثبت گروهی با موفقیت انجام شد.', 'success');
        },
    };
}

// ============================================================
//  0. INITIALIZATION (Ø±Ø§Ù‡â€ŒØ§Ù†Ø¯Ø§Ø²ÛŒ Ø§ÙˆÙ„ÛŒÙ‡)
// ============================================================
async function runAppBoot() {
    if (TS_APP_BOOT?.runOnLoad) {
        try {
            const handled = await TS_APP_BOOT.runOnLoad(window.location.pathname, buildBootDeps());
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    const path = window.location.pathname;

    if (TS_APP_SHELL?.isPublicPage?.(path)) {
        console.log("Skipping app init on public page:", path);
        return;
    }

    // â›” Ù„ÛŒØ³Øª ØµÙØ­Ø§Øª Ø¹Ù…ÙˆÙ…ÛŒ Ú©Ù‡ Ù†Ø¨Ø§ÛŒØ¯ Ú†Ú© Ø´ÙˆÙ†Ø¯
    const publicPages = ['/login', '/debug_login'];
    if (publicPages.includes(path)) {
        console.log("Skipping app init on public page:", path);
        return;
    }
    
    toggleLoader(true);
    primeLoadedScriptCache();
    
    // 1. Ø¯Ø±ÛŒØ§ÙØª Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ù¾Ø§ÛŒÙ‡ (Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§ØŒ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†â€ŒÙ‡Ø§ Ùˆ...)
    await loadDictionary();
    await loadEdmsNavigation();
    
    // 2. Ø§Ø¬Ø¨Ø§Ø± Ø¨Ù‡ Ù†Ù…Ø§ÛŒØ´ Ø¯Ø§Ø´Ø¨ÙˆØ±Ø¯ Ø¯Ø± Ø´Ø±ÙˆØ¹ Ú©Ø§Ø±
    await navigateTo('view-dashboard');
    
    toggleLoader(false);
    markPerf('first_view_ready');
    measurePerf('app_boot', 'app_boot_start', 'first_view_ready');
    renderDevPerformancePanel();
    
    // 3. ÙØ¹Ø§Ù„â€ŒØ³Ø§Ø²ÛŒ Ù„ÛŒØ³Ù†Ø±Ù‡Ø§ (Ú©Ù„ÛŒÚ©â€ŒÙ‡Ø§ÛŒ Ø¹Ù…ÙˆÙ…ÛŒ)
    setupGlobalListeners();

    // 4. Ø¯Ø±ÛŒØ§ÙØª Ù¾ÛŒØ§Ù… Ø§Ø² iframe
    window.addEventListener('message', (event) => {
        if (event.data === 'refreshDashboard') {
            console.log("ðŸ”„ Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ø±ÙØ±Ø´ Ø§Ø² Ø³Ù…Øª iframe Ø¯Ø±ÛŒØ§ÙØª Ø´Ø¯.");
            if (typeof initDashboard === 'function') initDashboard();
            showToast("âœ… Ø¹Ù…Ù„ÛŒØ§Øª Ø«Ø¨Øª Ú¯Ø±ÙˆÙ‡ÛŒ Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯.", "success");
        }
    });
}

if (document.readyState === 'complete') {
    void runAppBoot();
} else {
    window.addEventListener('load', () => {
        void runAppBoot();
    }, { once: true });
}

function setupGlobalListeners() {
    if (TS_APP_SHELL?.setupGlobalListeners) {
        TS_APP_SHELL.setupGlobalListeners({
            navigateTo: (targetView) => navigateTo(targetView),
            logout: () => window.authManager?.logout?.(),
        });
        return;
    }

    document.addEventListener('click', (e) => {
        const navTrigger = e.target.closest('[data-nav-target]');
        if (navTrigger) {
            e.preventDefault();
            navigateTo(navTrigger.getAttribute('data-nav-target'));
            return;
        }

        const uiAction = e.target.closest('[data-ui-action]');
        if (uiAction) {
            e.preventDefault();
            const action = String(uiAction.getAttribute('data-ui-action') || '').trim().toLowerCase();
            if (action === 'toggle-sidebar') {
                toggleSidebar();
                return;
            }
            if (action === 'toggle-user-menu') {
                toggleUserMenu();
                return;
            }
            if (action === 'logout') {
                window.authManager?.logout?.();
                return;
            }
        }

        // Ø¨Ø³ØªÙ† Ù…Ù†ÙˆÛŒ Ù¾Ø±ÙˆÙØ§ÛŒÙ„ Ú©Ø§Ø±Ø¨Ø±
        if (!e.target.closest('.user-menu-container')) {
            const dropdown = document.getElementById('user-dropdown');
            if (dropdown) dropdown.classList.remove('show');
        }
        // Ø¨Ø³ØªÙ† Ù…Ù†ÙˆÛŒ Ø±Ø§Ø³Øª Ú©Ù„ÛŒÚ© (Context Menu)
        if (!e.target.closest('.context-menu') && !e.target.closest('.action-btn')) {
            const ctxMenu = document.getElementById('context-menu');
            if (ctxMenu) ctxMenu.classList.remove('show');
        }
        // Ø¨Ø³ØªÙ† Ø³Ø§ÛŒØ¯Ø¨Ø§Ø± Ø¯Ø± Ø­Ø§Ù„Øª Ù…ÙˆØ¨Ø§ÛŒÙ„ (Ø§Ú¯Ø± Ø±ÙˆÛŒ Ø®ÙˆØ¯ Ø³Ø§ÛŒØ¯Ø¨Ø§Ø± ÛŒØ§ Ø¯Ú©Ù…Ù‡ ØªØ§Ú¯Ù„ Ú©Ù„ÛŒÚ© Ù†Ø´Ø¯Ù‡ Ø¨Ø§Ø´Ø¯)
        // Ù†Ú©ØªÙ‡: Ø¯Ø± Ø­Ø§Ù„Øª Ø¯Ø³Ú©ØªØ§Ù¾ Ú©Ù‡ Ø³Ø§ÛŒØ¯Ø¨Ø§Ø± collapsible Ø§Ø³ØªØŒ Ù†Ø¨Ø§ÛŒØ¯ Ø¨Ø§ Ú©Ù„ÛŒÚ© Ø¨ÛŒØ±ÙˆÙ† Ø¨Ø³ØªÙ‡ Ø´ÙˆØ¯.
        if (window.innerWidth <= 992) {
            if (!e.target.closest('.sidebar') && !e.target.closest('.menu-toggle')) {
                const sidebar = document.getElementById('app-sidebar');
                if (sidebar && sidebar.classList.contains('open')) toggleSidebar();
            }
        }
    });
}

 function isViewActive(id) {
    const el = document.getElementById(id);
    return el && el.style.display !== 'none';
}

function mapToRoutedView(viewId) {
    if (TS_EDMS_STATE?.mapToRoutedView) {
        const mapped = TS_EDMS_STATE.mapToRoutedView(viewId);
        if (mapped) {
            if (mapped === 'view-edms' && TS_EDMS_STATE?.getPendingEdmsTab) {
                PENDING_EDMS_TAB = TS_EDMS_STATE.getPendingEdmsTab();
            }
            return mapped;
        }
    }

    const requested = String(viewId || '').trim();
    const mappedTab = EDMS_VIEW_TO_TAB[requested];
    if (mappedTab) {
        PENDING_EDMS_TAB = mappedTab;
        return 'view-edms';
    }
    return requested;
}

async function ensureXlsxLoaded() {
    if (TS_APP_DATA?.ensureXlsxLoaded) {
        try {
            const result = await TS_APP_DATA.ensureXlsxLoaded({
                isScriptLoaded: (absoluteSrc) => LOADED_PARTIAL_SCRIPTS.has(absoluteSrc),
                markScriptLoaded: (absoluteSrc) => LOADED_PARTIAL_SCRIPTS.add(absoluteSrc),
                getGlobalXlsx: () => window.XLSX,
            });
            if (result?.handled) {
                return result.xlsx;
            }
        } catch (error) {
            throw error;
        }
    }

    if (window.XLSX) return window.XLSX;
    const src = 'https://cdn.jsdelivr.net/npm/xlsx@0.19.3/dist/xlsx.full.min.js';
    const absoluteSrc = new URL(src, window.location.origin).href;
    if (LOADED_PARTIAL_SCRIPTS.has(absoluteSrc) && window.XLSX) return window.XLSX;

    await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Failed to load XLSX library.'));
        document.head.appendChild(script);
    });
    LOADED_PARTIAL_SCRIPTS.add(absoluteSrc);
    return window.XLSX;
}

window.ensureXlsxLoaded = ensureXlsxLoaded;

async function executeScriptsInElement(rootElement) {
    if (TS_VIEW_LOADER?.executeScriptsInElement) {
        try {
            const handled = await TS_VIEW_LOADER.executeScriptsInElement(rootElement, {
                isScriptLoaded: (absoluteSrc) => LOADED_PARTIAL_SCRIPTS.has(absoluteSrc),
                markScriptLoaded: (absoluteSrc) => LOADED_PARTIAL_SCRIPTS.add(absoluteSrc),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    const scripts = Array.from(rootElement.querySelectorAll('script'));
    for (const oldScript of scripts) {
        const newScript = document.createElement('script');
        for (const attr of Array.from(oldScript.attributes || [])) {
            newScript.setAttribute(attr.name, attr.value);
        }

        const srcAttr = oldScript.getAttribute('src');
        if (srcAttr) {
            const absoluteSrc = new URL(srcAttr, window.location.origin).href;
            if (LOADED_PARTIAL_SCRIPTS.has(absoluteSrc)) {
                oldScript.remove();
                continue;
            }
            await new Promise((resolve, reject) => {
                newScript.onload = () => resolve();
                newScript.onerror = () => reject(new Error(`Failed to load script: ${srcAttr}`));
                oldScript.replaceWith(newScript);
            });
            LOADED_PARTIAL_SCRIPTS.add(absoluteSrc);
            continue;
        }

        newScript.textContent = oldScript.textContent || '';
        oldScript.replaceWith(newScript);
    }
}

async function loadViewPartial(viewId) {
    if (TS_VIEW_LOADER?.loadViewPartial) {
        try {
            const handled = await TS_VIEW_LOADER.loadViewPartial(viewId, {
                resolvePartialName: (requestedViewId) => VIEW_PARTIALS[requestedViewId] || null,
                isViewCached: (requestedViewId) => VIEW_LOAD_CACHE.has(requestedViewId),
                markViewCached: (requestedViewId) => {
                    VIEW_LOAD_CACHE.add(requestedViewId);
                },
                getViewHost: (requestedViewId) => document.getElementById(requestedViewId),
                markPerf: (name) => markPerf(name),
                measurePerf: (metricName, startMark, endMark) => measurePerf(metricName, startMark, endMark),
                fetchPartialHtml: async (partialName) => {
                    try {
                        const res = await fetch(`/ui/partial/${encodeURIComponent(partialName)}`, {
                            headers: { 'X-Requested-With': 'fetch' },
                            credentials: 'same-origin',
                        });
                        const html = res.ok ? await res.text() : null;
                        return { ok: !!res.ok, status: Number(res.status || 0), html };
                    } catch (error) {
                        console.warn('loadViewPartial fetch failed:', error);
                        return { ok: false, status: 0, html: null };
                    }
                },
                emitViewLoaded: (loadedViewId, partialName) => {
                    window.AppEvents?.emit?.('view:loaded', { viewId: loadedViewId, partialName });
                },
                showToast: (message, type = 'info') => showToast(message, type),
            });
            if (handled) return true;
        } catch (error) {
            throw error;
        }
    }

    const partialName = VIEW_PARTIALS[viewId];
    if (!partialName) return true;
    if (VIEW_LOAD_CACHE.has(viewId)) return true;

    const host = document.getElementById(viewId);
    if (!host) return false;

    host.innerHTML = '<div class="lazy-view-state">در حال بارگذاری صفحه...</div>';
    const metricKey = `partial_${partialName}`;
    markPerf(`${metricKey}_start`);

    try {
        const res = await fetch(`/ui/partial/${encodeURIComponent(partialName)}`, {
            headers: { 'X-Requested-With': 'fetch' },
            credentials: 'same-origin',
        });
        if (!res.ok) {
            throw new Error(`Failed to load view (${res.status})`);
        }
        const html = await res.text();
        const wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        const incomingView = wrapper.querySelector(`#${viewId}`) || wrapper.querySelector('.view-section');
        if (!incomingView) {
            throw new Error(`Invalid partial payload for ${viewId}`);
        }

        host.replaceWith(incomingView);
        await executeScriptsInElement(incomingView);
        VIEW_LOAD_CACHE.add(viewId);
        markPerf(`${metricKey}_end`);
        measurePerf(metricKey, `${metricKey}_start`, `${metricKey}_end`);
        window.AppEvents?.emit?.('view:loaded', { viewId, partialName });
        return true;
    } catch (error) {
        host.innerHTML = `
            <div class="lazy-view-state">
                خطا در بارگذاری صفحه.
                <button type="button" class="btn-archive-icon" data-nav-target="${viewId}">تلاش مجدد</button>
            </div>
        `;
        showToast('بارگذاری صفحه با خطا مواجه شد.', 'error');
        console.error(error);
        return false;
    }
}

function consumePendingSettingsTab() {
    const val = PENDING_SETTINGS_TAB;
    PENDING_SETTINGS_TAB = null;
    return val;
}

function consumePendingEdmsTab() {
    if (TS_EDMS_STATE?.consumePendingEdmsTab) {
        const val = TS_EDMS_STATE.consumePendingEdmsTab();
        PENDING_EDMS_TAB = null;
        return val;
    }

    const val = PENDING_EDMS_TAB;
    PENDING_EDMS_TAB = null;
    return val;
}

window.consumePendingSettingsTab = consumePendingSettingsTab;
window.consumePendingEdmsTab = consumePendingEdmsTab;

function isEdmsTabVisible(tabName) {
    if (TS_EDMS_STATE?.isTabVisible) {
        return TS_EDMS_STATE.isTabVisible(tabName);
    }

    return EDMS_TAB_VISIBILITY[String(tabName || '').trim().toLowerCase()] !== false;
}

function getFirstVisibleEdmsTab() {
    if (TS_EDMS_STATE?.getFirstVisibleTab) {
        return TS_EDMS_STATE.getFirstVisibleTab();
    }

    const order = ['archive', 'transmittal', 'correspondence'];
    return order.find((tab) => isEdmsTabVisible(tab)) || null;
}

function getEdmsLastTabStorageKey() {
    const userId = window.authManager?.user?.id;
    if (userId !== undefined && userId !== null && String(userId).trim() !== '') {
        return `edms_last_tab_user_${String(userId).trim()}`;
    }
    const role = String(window.authManager?.user?.role || 'unknown').trim().toLowerCase();
    return `edms_last_tab_role_${role || 'unknown'}`;
}

function saveEdmsLastTab(tabName) {
    if (TS_EDMS_STATE?.saveLastTab) {
        TS_EDMS_STATE.saveLastTab(tabName, window.authManager?.user?.id, window.authManager?.user?.role);
        return;
    }

    try {
        const normalized = String(tabName || '').trim().toLowerCase();
        if (!EDMS_TAB_TO_VIEW[normalized]) return;
        localStorage.setItem(getEdmsLastTabStorageKey(), normalized);
    } catch (error) {
        console.warn('Failed to persist EDMS last tab.', error);
    }
}

function loadEdmsLastTab() {
    if (TS_EDMS_STATE?.loadLastTab) {
        return TS_EDMS_STATE.loadLastTab(window.authManager?.user?.id, window.authManager?.user?.role);
    }

    try {
        const value = localStorage.getItem(getEdmsLastTabStorageKey());
        const normalized = String(value || '').trim().toLowerCase();
        return EDMS_TAB_TO_VIEW[normalized] ? normalized : null;
    } catch (error) {
        console.warn('Failed to load EDMS last tab.', error);
        return null;
    }
}

function getEffectiveDefaultEdmsTab() {
    if (TS_EDMS_STATE?.getEffectiveDefaultTab) {
        return TS_EDMS_STATE.getEffectiveDefaultTab();
    }

    const preferred = String(EDMS_DEFAULT_TAB || '').trim().toLowerCase();
    if (preferred && isEdmsTabVisible(preferred)) {
        return preferred;
    }
    return getFirstVisibleEdmsTab();
}

function applyEdmsTabVisibility() {
    const navEdms = document.getElementById('nav-edms');
    if (TS_EDMS_STATE?.applyTabVisibility) {
        try {
            const handled = TS_EDMS_STATE.applyTabVisibility({
                setTabButtonVisible: (tabName, visible) => {
                    const tabBtn = document.querySelector(`.edms-tab-btn[data-edms-tab="${tabName}"]`);
                    if (tabBtn) tabBtn.style.display = visible ? '' : 'none';
                },
                setPanelVisible: (viewId, visible) => {
                    const panel = document.getElementById(viewId);
                    if (panel && !visible) {
                        panel.style.display = 'none';
                        panel.classList.remove('active');
                    }
                },
                setNavVisible: (visible) => {
                    if (navEdms) navEdms.style.display = visible ? '' : 'none';
                },
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    let hasVisibleTab = false;

    Object.entries(EDMS_TAB_TO_VIEW).forEach(([tabName, viewId]) => {
        const visible = isEdmsTabVisible(tabName);
        const tabBtn = document.querySelector(`.edms-tab-btn[data-edms-tab="${tabName}"]`);
        const panel = document.getElementById(viewId);
        if (tabBtn) tabBtn.style.display = visible ? '' : 'none';
        if (panel && !visible) {
            panel.style.display = 'none';
            panel.classList.remove('active');
        }
        hasVisibleTab = hasVisibleTab || visible;
    });

    if (navEdms) {
        navEdms.style.display = hasVisibleTab ? '' : 'none';
    }
}

function setEdmsHeaderStats(data = {}) {
    const mapping = {
        'edms-stat-total': data.total,
        'edms-stat-review': data.review,
        'edms-stat-approved': data.approved,
        'edms-stat-asbuilt': data.transmittal,
    };
    Object.entries(mapping).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = Number.isFinite(Number(value)) ? String(Number(value)) : '0';
    });
}

function primeLoadedScriptCache() {
    document.querySelectorAll('script[src]').forEach((scriptEl) => {
        try {
            const src = new URL(scriptEl.getAttribute('src'), window.location.origin).href;
            LOADED_PARTIAL_SCRIPTS.add(src);
        } catch (error) {
            // Ignore malformed URLs
        }
    });
}

function markPerf(name) {
    if (!window.performance?.mark) return;
    window.performance.mark(name);
}

function measurePerf(metricName, startMark, endMark) {
    if (!window.performance?.measure) return;
    try {
        window.performance.measure(metricName, startMark, endMark);
        const entries = window.performance.getEntriesByName(metricName);
        const latest = entries?.[entries.length - 1];
        if (!latest) return;
        PERF_METRICS[metricName] = Number(latest.duration || 0).toFixed(1);
        if (window.__DEV_PERF__) {
            console.info(`[perf] ${metricName}: ${PERF_METRICS[metricName]}ms`);
        }
    } catch (error) {
        // Ignore missing marks
    }
}

function shouldShowPerfPanel() {
    const qs = new URLSearchParams(window.location.search || '');
    if (qs.get('perf') === '1') return true;
    return localStorage.getItem('dev_perf_panel') === '1';
}

function renderDevPerformancePanel() {
    if (!shouldShowPerfPanel()) return;
    let panel = document.getElementById(PERF_PANEL_ID);
    if (!panel) {
        panel = document.createElement('div');
        panel.id = PERF_PANEL_ID;
        panel.style.cssText = [
            'position:fixed',
            'bottom:16px',
            'left:16px',
            'z-index:9999',
            'min-width:220px',
            'max-width:280px',
            'background:#0f172a',
            'color:#e2e8f0',
            'border:1px solid #334155',
            'border-radius:10px',
            'padding:10px 12px',
            'font:12px/1.6 Vazirmatn, sans-serif',
            'box-shadow:0 10px 24px rgba(2,6,23,0.35)',
        ].join(';');
        document.body.appendChild(panel);
    }
    const rows = Object.entries(PERF_METRICS)
        .map(([k, v]) => `<div><strong>${k}:</strong> ${v}ms</div>`)
        .join('');
    panel.innerHTML = `<div style="font-weight:700; margin-bottom:6px;">Performance</div>${rows || '<div>no metrics</div>'}`;
}

async function loadEdmsHeaderStats(force = false) {
    if (!document.getElementById('edms-stat-total')) return;

    const now = Date.now();
    const cacheMs = 15000;
    if (TS_EDMS_STATE?.loadHeaderStats) {
        try {
            const handled = await TS_EDMS_STATE.loadHeaderStats({
                force,
                now,
                cacheMs,
                fetchStats: async () => {
                    try {
                        const res = (typeof window.fetchWithAuth === 'function')
                            ? await window.fetchWithAuth(`${API_BASE}/dashboard/stats`)
                            : await fetch(`${API_BASE}/dashboard/stats`);
                        if (!res || !res.ok) return null;
                        return await res.json();
                    } catch (error) {
                        console.warn('loadEdmsHeaderStats fetch failed:', error);
                        return null;
                    }
                },
                applyStats: (payload) => setEdmsHeaderStats(payload || {}),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    if (TS_EDMS_STATE?.beginHeaderStatsLoad) {
        const shouldRun = TS_EDMS_STATE.beginHeaderStatsLoad(force, now, cacheMs);
        if (!shouldRun) return;
    } else {
        if (!force && EDMS_STATS_LOADING) return;
        if (!force && EDMS_STATS_LAST_LOADED_AT && (now - EDMS_STATS_LAST_LOADED_AT) < cacheMs) return;
        EDMS_STATS_LOADING = true;
    }

    let loadSucceeded = false;
    try {
        const res = (typeof window.fetchWithAuth === 'function')
            ? await window.fetchWithAuth(`${API_BASE}/dashboard/stats`)
            : await fetch(`${API_BASE}/dashboard/stats`);
        if (!res || !res.ok) return;
        const data = await res.json();
        setEdmsHeaderStats(data || {});
        loadSucceeded = true;
        if (!TS_EDMS_STATE?.endHeaderStatsLoad) {
            EDMS_STATS_LAST_LOADED_AT = Date.now();
        }
    } catch (error) {
        console.warn('Failed to load EDMS header stats.', error);
    } finally {
        if (TS_EDMS_STATE?.endHeaderStatsLoad) {
            TS_EDMS_STATE.endHeaderStatsLoad(loadSucceeded, Date.now());
        } else {
            EDMS_STATS_LOADING = false;
        }
    }
}

window.loadEdmsHeaderStats = loadEdmsHeaderStats;

async function loadEdmsNavigation() {
    if (TS_EDMS_STATE?.loadNavigationAndApply) {
        try {
            const handled = await TS_EDMS_STATE.loadNavigationAndApply({
                role: window.authManager?.user?.role,
                fetchNavigation: async () => {
                    const res = (typeof window.fetchWithAuth === 'function')
                        ? await window.fetchWithAuth(`${API_BASE}/auth/navigation`)
                        : await fetch(`${API_BASE}/auth/navigation`);
                    if (res && res.ok) {
                        return await res.json();
                    }
                    return null;
                },
                applyVisibility: () => applyEdmsTabVisibility(),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    if (!TS_EDMS_STATE?.loadNavigation) {
        throw new Error('EDMS state bridge does not provide navigation loader.');
    }
    await TS_EDMS_STATE.loadNavigation({
        role: window.authManager?.user?.role,
        fetchNavigation: async () => {
            const res = (typeof window.fetchWithAuth === 'function')
                ? await window.fetchWithAuth(`${API_BASE}/auth/navigation`)
                : await fetch(`${API_BASE}/auth/navigation`);
            if (res && res.ok) {
                return await res.json();
            }
            return null;
        },
    });
    applyEdmsTabVisibility();
}

function openEdmsTab(tabName, btnEl = null) {
    if (TS_EDMS_STATE?.openTab) {
        try {
            const handled = TS_EDMS_STATE.openTab({
                tabName,
                button: btnEl || null,
                userId: window.authManager?.user?.id,
                role: window.authManager?.user?.role,
                showAccessDenied: () => {
                    showToast('Access denied for this tab.', 'error');
                },
                setPanelState: (viewId, active) => {
                    const panel = document.getElementById(viewId);
                    if (!panel) return;
                    panel.style.display = active ? 'block' : 'none';
                    panel.classList.toggle('active', active);
                },
                clearButtons: () => {
                    document.querySelectorAll('.edms-tab-btn[data-edms-tab]').forEach((button) => {
                        button.classList.remove('active');
                    });
                },
                activateButton: (normalizedTab, providedButton) => {
                    const button = providedButton || document.querySelector(`.edms-tab-btn[data-edms-tab="${normalizedTab}"]`);
                    if (button) button.classList.add('active');
                },
                onTabActivated: (normalizedTab) => {
                    switch (normalizedTab) {
                        case 'archive':
                            if (typeof initArchiveView === 'function') {
                                initArchiveView();
                            } else if (typeof archiveLoadFiles === 'function') {
                                archiveLoadFiles();
                            }
                            break;
                        case 'transmittal':
                            if (typeof initTransmittalView === 'function') {
                                initTransmittalView();
                            } else {
                                if (typeof showListMode === 'function') showListMode();
                                if (typeof loadTransmittals === 'function') {
                                    loadTransmittals();
                                } else if (typeof toggleTransmittalMode === 'function') {
                                    toggleTransmittalMode('list');
                                }
                            }
                            break;
                        case 'correspondence':
                            if (typeof initCorrespondenceView === 'function') initCorrespondenceView();
                            break;
                        default:
                            break;
                    }
                },
                setLegacyPendingTab: (normalizedTab) => {
                    PENDING_EDMS_TAB = normalizedTab;
                },
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    const normalized = String(tabName || '').trim().toLowerCase();
    if (!EDMS_TAB_TO_VIEW[normalized]) return;
    if (!isEdmsTabVisible(normalized)) {
        showToast('Ø´Ù…Ø§ Ø¯Ø³ØªØ±Ø³ÛŒ Ù„Ø§Ø²Ù… Ø¨Ø±Ø§ÛŒ Ø§ÛŒÙ† ØªØ¨ Ø±Ø§ Ù†Ø¯Ø§Ø±ÛŒØ¯.', 'error');
        return;
    }

    Object.entries(EDMS_TAB_TO_VIEW).forEach(([tab, viewId]) => {
        const panel = document.getElementById(viewId);
        if (!panel) return;
        const active = tab === normalized;
        panel.style.display = active ? 'block' : 'none';
        panel.classList.toggle('active', active);
    });

    document.querySelectorAll('.edms-tab-btn[data-edms-tab]').forEach((button) => {
        button.classList.remove('active');
    });

    const button = btnEl || document.querySelector(`.edms-tab-btn[data-edms-tab="${normalized}"]`);
    if (button) button.classList.add('active');

    if (TS_EDMS_STATE?.setPendingEdmsTab) TS_EDMS_STATE.setPendingEdmsTab(normalized);
    PENDING_EDMS_TAB = normalized;

    switch (normalized) {
        case 'archive':
            if (typeof initArchiveView === 'function') {
                initArchiveView();
            } else if (typeof archiveLoadFiles === 'function') {
                archiveLoadFiles();
            }
            break;
        case 'transmittal':
            if (typeof initTransmittalView === 'function') {
                initTransmittalView();
            } else {
                if (typeof showListMode === 'function') showListMode();
                if (typeof loadTransmittals === 'function') {
                    loadTransmittals();
                } else if (typeof toggleTransmittalMode === 'function') {
                    toggleTransmittalMode('list');
                }
            }
            break;
        case 'correspondence':
            if (typeof initCorrespondenceView === 'function') initCorrespondenceView();
            break;
        default:
            break;
    }
    saveEdmsLastTab(normalized);
}

window.openEdmsTab = openEdmsTab;
window.loadEdmsLastTab = loadEdmsLastTab;
window.getEffectiveDefaultEdmsTab = getEffectiveDefaultEdmsTab;
window.getFirstVisibleEdmsTab = getFirstVisibleEdmsTab;
window.isEdmsTabVisible = isEdmsTabVisible;

function switchModuleTab(tabName, tabToPanelMap, tabButtonSelector, dataAttrName, btnEl = null) {
    const normalized = String(tabName || '').trim().toLowerCase();
    if (!tabToPanelMap[normalized]) return null;

    if (TS_MODULE_TABS?.switchTab) {
        try {
            const handled = TS_MODULE_TABS.switchTab(
                normalized,
                tabToPanelMap,
                tabButtonSelector,
                dataAttrName,
                btnEl || null
            );
            if (handled) return handled;
        } catch (error) {
            throw error;
        }
    }

    Object.entries(tabToPanelMap).forEach(([tab, panelId]) => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const active = tab === normalized;
        panel.style.display = active ? 'block' : 'none';
        panel.classList.toggle('active', active);
    });

    document.querySelectorAll(tabButtonSelector).forEach((button) => {
        button.classList.remove('active');
    });

    const button = btnEl || document.querySelector(`${tabButtonSelector}[${dataAttrName}="${normalized}"]`);
    if (button) button.classList.add('active');
    return normalized;
}

function openContractorTab(tabName, btnEl = null) {
    const normalized = switchModuleTab(tabName, CONTRACTOR_TAB_TO_PANEL, '.contractor-tab-btn', 'data-contractor-tab', btnEl);
    if (!normalized) return;
    moduleBoardOnTabOpened('contractor', normalized);
}

function initContractorView() {
    initModuleCrudBoards();
    if (TS_MODULE_TABS?.resolveInitialTab) {
        try {
            const initial = TS_MODULE_TABS.resolveInitialTab('.contractor-tab-btn', 'data-contractor-tab', 'execution');
            if (initial?.tabName) {
                openContractorTab(initial.tabName, initial.button || null);
                return;
            }
        } catch (error) {
            throw error;
        }
    }

    const currentButton = document.querySelector('.contractor-tab-btn.active');
    const defaultTab = currentButton?.dataset?.contractorTab || 'execution';
    openContractorTab(defaultTab, currentButton || null);
}

function openConsultantTab(tabName, btnEl = null) {
    const normalized = switchModuleTab(tabName, CONSULTANT_TAB_TO_PANEL, '.consultant-tab-btn', 'data-consultant-tab', btnEl);
    if (!normalized) return;
    moduleBoardOnTabOpened('consultant', normalized);
}

function initConsultantView() {
    initModuleCrudBoards();
    if (TS_MODULE_TABS?.resolveInitialTab) {
        try {
            const initial = TS_MODULE_TABS.resolveInitialTab('.consultant-tab-btn', 'data-consultant-tab', 'inspection');
            if (initial?.tabName) {
                openConsultantTab(initial.tabName, initial.button || null);
                return;
            }
        } catch (error) {
            throw error;
        }
    }

    const currentButton = document.querySelector('.consultant-tab-btn.active');
    const defaultTab = currentButton?.dataset?.consultantTab || 'inspection';
    openConsultantTab(defaultTab, currentButton || null);
}

window.openContractorTab = openContractorTab;
window.initContractorView = initContractorView;
window.openConsultantTab = openConsultantTab;
window.initConsultantView = initConsultantView;

function moduleBoardEsc(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function moduleBoardKey(moduleKey, tabKey) {
    if (TS_MODULE_BOARD?.key) {
        const mapped = TS_MODULE_BOARD.key(moduleKey, tabKey);
        if (mapped) return mapped;
    }

    return `${String(moduleKey || '').trim().toLowerCase()}-${String(tabKey || '').trim().toLowerCase()}`;
}

function moduleBoardCanEdit() {
    if (TS_MODULE_BOARD?.canEdit) {
        return !!TS_MODULE_BOARD.canEdit(window.authManager?.user?.role);
    }

    const role = String(window.authManager?.user?.role || '').trim().toLowerCase();
    return role !== 'viewer';
}

function moduleBoardGetProjects() {
    const rows = Array.isArray(window.CACHE?.projects) ? window.CACHE.projects : [];
    return rows
        .map((row) => ({
            code: String(row.code || row.project_code || '').trim().toUpperCase(),
            name: String(row.project_name || row.name_e || row.name_p || row.code || '').trim(),
        }))
        .filter((row) => row.code);
}

function moduleBoardGetDisciplines() {
    const rows = Array.isArray(window.CACHE?.disciplines) ? window.CACHE.disciplines : [];
    return rows
        .map((row) => ({
            code: String(row.code || row.discipline_code || '').trim().toUpperCase(),
            name: String(row.name_e || row.name_p || row.code || '').trim(),
        }))
        .filter((row) => row.code);
}

function moduleBoardStatusOptions() {
    return Object.entries(WORKBOARD_STATUS_LABELS)
        .map(([key, label]) => `<option value="${moduleBoardEsc(key)}">${moduleBoardEsc(label)}</option>`)
        .join('');
}

function moduleBoardPriorityOptions() {
    return Object.entries(WORKBOARD_PRIORITY_LABELS)
        .map(([key, label]) => `<option value="${moduleBoardEsc(key)}">${moduleBoardEsc(label)}</option>`)
        .join('');
}

function moduleBoardProjectOptions(includeAll = true, emptyLabel = 'همه پروژه‌ها') {
    const options = [];
    if (includeAll) {
        options.push(`<option value="">${moduleBoardEsc(emptyLabel)}</option>`);
    }
    moduleBoardGetProjects().forEach((row) => {
        options.push(
            `<option value="${moduleBoardEsc(row.code)}">${moduleBoardEsc(row.code)} - ${moduleBoardEsc(row.name || row.code)}</option>`
        );
    });
    return options.join('');
}

function moduleBoardDisciplineOptions(includeAll = true, emptyLabel = 'همه دیسیپلین‌ها') {
    const options = [];
    if (includeAll) {
        options.push(`<option value="">${moduleBoardEsc(emptyLabel)}</option>`);
    }
    moduleBoardGetDisciplines().forEach((row) => {
        options.push(
            `<option value="${moduleBoardEsc(row.code)}">${moduleBoardEsc(row.code)} - ${moduleBoardEsc(row.name || row.code)}</option>`
        );
    });
    return options.join('');
}

function moduleBoardRenderCard(moduleKey, tabKey, title) {
    const key = moduleBoardKey(moduleKey, tabKey);
    const canEdit = moduleBoardCanEdit();
    return `
<div class="archive-card module-crud-card" data-module="${moduleBoardEsc(moduleKey)}" data-tab="${moduleBoardEsc(tabKey)}">
    <div class="module-panel-header">
        <h3 class="archive-title">
            <span class="material-icons-round">assignment</span>
            ${moduleBoardEsc(title)}
        </h3>
        <p class="archive-subtitle">ثبت، جستجو، ویرایش و پیگیری آیتم‌های عملیاتی این تب</p>
    </div>

    <div class="module-crud-toolbar">
        <div class="module-crud-toolbar-left">
            ${canEdit ? `<button type="button" class="btn btn-primary" data-mb-action="open-form"><span class="material-icons-round">add</span>افزودن آیتم</button>` : ''}
            <button type="button" class="btn-archive-icon" data-mb-action="load" data-force="true" title="به‌روزرسانی">
                <span class="material-icons-round">refresh</span>
            </button>
        </div>
        <div class="module-crud-toolbar-right">
            <select id="mb-filter-project-${moduleBoardEsc(key)}" class="module-crud-select" data-mb-action="filter-project">
                ${moduleBoardProjectOptions()}
            </select>
            <select id="mb-filter-discipline-${moduleBoardEsc(key)}" class="module-crud-select" data-mb-action="filter-discipline">
                ${moduleBoardDisciplineOptions()}
            </select>
            <select id="mb-filter-status-${moduleBoardEsc(key)}" class="module-crud-select" data-mb-action="filter-status">
                <option value="">همه وضعیت‌ها</option>
                ${moduleBoardStatusOptions()}
            </select>
            <input id="mb-filter-search-${moduleBoardEsc(key)}" class="module-crud-input" type="text" placeholder="جستجو در عنوان/شرح..." data-mb-action="filter-search">
        </div>
    </div>

    <div id="mb-form-wrap-${moduleBoardEsc(key)}" class="module-crud-form-wrap" hidden>
        <h4 class="module-crud-form-title">فرم آیتم عملیاتی</h4>
        <input id="mb-form-id-${moduleBoardEsc(key)}" type="hidden" value="">
        <div class="module-crud-form-grid">
            <div class="module-crud-form-field">
                <label for="mb-form-title-${moduleBoardEsc(key)}">عنوان</label>
                <input id="mb-form-title-${moduleBoardEsc(key)}" class="module-crud-input" type="text" maxlength="255" placeholder="عنوان آیتم">
            </div>
            <div class="module-crud-form-field">
                <label for="mb-form-project-${moduleBoardEsc(key)}">پروژه</label>
                <select id="mb-form-project-${moduleBoardEsc(key)}" class="module-crud-select">
                    ${moduleBoardProjectOptions(true, 'بدون پروژه')}
                </select>
            </div>
            <div class="module-crud-form-field">
                <label for="mb-form-discipline-${moduleBoardEsc(key)}">دیسیپلین</label>
                <select id="mb-form-discipline-${moduleBoardEsc(key)}" class="module-crud-select">
                    ${moduleBoardDisciplineOptions(true, 'بدون دیسیپلین')}
                </select>
            </div>
            <div class="module-crud-form-field">
                <label for="mb-form-status-${moduleBoardEsc(key)}">وضعیت</label>
                <select id="mb-form-status-${moduleBoardEsc(key)}" class="module-crud-select">
                    ${moduleBoardStatusOptions()}
                </select>
            </div>
            <div class="module-crud-form-field">
                <label for="mb-form-priority-${moduleBoardEsc(key)}">اولویت</label>
                <select id="mb-form-priority-${moduleBoardEsc(key)}" class="module-crud-select">
                    ${moduleBoardPriorityOptions()}
                </select>
            </div>
            <div class="module-crud-form-field">
                <label for="mb-form-due-${moduleBoardEsc(key)}">تاریخ سررسید</label>
                <input id="mb-form-due-${moduleBoardEsc(key)}" class="module-crud-input" type="date">
            </div>
            <div class="module-crud-form-field" style="grid-column: 1 / -1;">
                <label for="mb-form-description-${moduleBoardEsc(key)}">شرح</label>
                <textarea id="mb-form-description-${moduleBoardEsc(key)}" class="module-crud-textarea" placeholder="توضیحات/اقدامات"></textarea>
            </div>
        </div>
        <div class="module-crud-form-actions">
            <button type="button" class="btn btn-secondary" data-mb-action="close-form">انصراف</button>
            <button type="button" class="btn btn-primary" data-mb-action="save-form">
                <span class="material-icons-round">save</span>
                ذخیره
            </button>
        </div>
    </div>

    <div class="module-crud-table-wrap">
        <table class="module-crud-table">
            <thead>
                <tr>
                    <th style="width:58px;">#</th>
                    <th>عنوان</th>
                    <th style="width:170px;">پروژه</th>
                    <th style="width:150px;">دیسیپلین</th>
                    <th style="width:120px;">وضعیت</th>
                    <th style="width:90px;">اولویت</th>
                    <th style="width:130px;">سررسید</th>
                    <th style="width:140px;">آخرین بروزرسانی</th>
                    <th style="width:130px;">عملیات</th>
                </tr>
            </thead>
            <tbody id="mb-tbody-${moduleBoardEsc(key)}"></tbody>
        </table>
        <div id="mb-empty-${moduleBoardEsc(key)}" class="module-crud-empty">آیتمی ثبت نشده است.</div>
    </div>
</div>
`;
}

function initModuleCrudBoards() {
    moduleBoardBindActions();
    if (WORKBOARD_STATE.initialized) return;
    const roots = document.querySelectorAll('.module-crud-root[data-module][data-tab]');
    if (!roots.length) return;

    roots.forEach((root) => {
        const moduleKey = String(root.dataset.module || '').trim().toLowerCase();
        const tabKey = String(root.dataset.tab || '').trim().toLowerCase();
        const title = String(root.dataset.title || '').trim() || `${moduleKey}/${tabKey}`;
        root.innerHTML = moduleBoardRenderCard(moduleKey, tabKey, title);
    });
    WORKBOARD_STATE.initialized = true;
}

function moduleBoardResolveContext(actionEl) {
    const card = actionEl && actionEl.closest ? actionEl.closest('.module-crud-card[data-module][data-tab]') : null;
    if (!card) return null;
    const moduleKey = String(card.dataset.module || '').trim().toLowerCase();
    const tabKey = String(card.dataset.tab || '').trim().toLowerCase();
    if (!moduleKey || !tabKey) return null;
    return { moduleKey, tabKey };
}

function moduleBoardBindActions() {
    if (WORKBOARD_STATE.actionsBound) return;
    if (TS_MODULE_BOARD?.bindActions) {
        try {
            const handled = TS_MODULE_BOARD.bindActions({
                openForm: (moduleKey, tabKey) => moduleBoardOpenForm(moduleKey, tabKey),
                closeForm: (moduleKey, tabKey) => moduleBoardCloseForm(moduleKey, tabKey),
                saveForm: (moduleKey, tabKey) => moduleBoardSave(moduleKey, tabKey),
                loadItems: (moduleKey, tabKey, force) => moduleBoardLoad(moduleKey, tabKey, force),
                editItem: (moduleKey, tabKey, itemId) => moduleBoardEdit(moduleKey, tabKey, itemId),
                deleteItem: (moduleKey, tabKey, itemId) => moduleBoardDelete(moduleKey, tabKey, itemId),
                debouncedLoad: (moduleKey, tabKey) => moduleBoardDebouncedLoad(moduleKey, tabKey),
            });
            if (handled) {
                WORKBOARD_STATE.actionsBound = true;
                return;
            }
        } catch (error) {
            throw error;
        }
    }

    document.addEventListener('click', (event) => {
        const actionEl = event && event.target && event.target.closest
            ? event.target.closest('[data-mb-action]')
            : null;
        if (!actionEl) return;
        const action = String(actionEl.dataset.mbAction || '').trim().toLowerCase();
        if (!action) return;

        const context = moduleBoardResolveContext(actionEl);
        if (!context) return;

        switch (action) {
            case 'open-form':
                moduleBoardOpenForm(context.moduleKey, context.tabKey);
                break;
            case 'close-form':
                moduleBoardCloseForm(context.moduleKey, context.tabKey);
                break;
            case 'save-form':
                moduleBoardSave(context.moduleKey, context.tabKey);
                break;
            case 'load':
                moduleBoardLoad(
                    context.moduleKey,
                    context.tabKey,
                    String(actionEl.dataset.force || '').toLowerCase() === 'true'
                );
                break;
            case 'edit-item':
                moduleBoardEdit(context.moduleKey, context.tabKey, Number(actionEl.dataset.itemId || 0));
                break;
            case 'delete-item':
                moduleBoardDelete(context.moduleKey, context.tabKey, Number(actionEl.dataset.itemId || 0));
                break;
            default:
                break;
        }
    });

    document.addEventListener('change', (event) => {
        const actionEl = event && event.target && event.target.closest
            ? event.target.closest('[data-mb-action]')
            : null;
        if (!actionEl) return;
        const action = String(actionEl.dataset.mbAction || '').trim().toLowerCase();
        if (!['filter-project', 'filter-discipline', 'filter-status'].includes(action)) return;

        const context = moduleBoardResolveContext(actionEl);
        if (!context) return;
        moduleBoardLoad(context.moduleKey, context.tabKey, true);
    });

    document.addEventListener('input', (event) => {
        const actionEl = event && event.target && event.target.closest
            ? event.target.closest('[data-mb-action]')
            : null;
        if (!actionEl) return;
        const action = String(actionEl.dataset.mbAction || '').trim().toLowerCase();
        if (action !== 'filter-search') return;

        const context = moduleBoardResolveContext(actionEl);
        if (!context) return;
        moduleBoardDebouncedLoad(context.moduleKey, context.tabKey);
    });

    WORKBOARD_STATE.actionsBound = true;
}

function moduleBoardElementId(moduleKey, tabKey, name) {
    return `mb-${name}-${moduleBoardKey(moduleKey, tabKey)}`;
}

function moduleBoardElement(moduleKey, tabKey, name) {
    return document.getElementById(moduleBoardElementId(moduleKey, tabKey, name));
}

function moduleBoardFormatDate(value, includeTime = false) {
    if (TS_MODULE_BOARD?.formatDate) {
        return TS_MODULE_BOARD.formatDate(value, includeTime);
    }

    const raw = String(value || '').trim();
    if (!raw) return '-';
    const dt = new Date(raw);
    if (Number.isNaN(dt.getTime())) return '-';
    if (includeTime) {
        return dt.toLocaleString('fa-IR');
    }
    return dt.toLocaleDateString('fa-IR');
}

function moduleBoardStatusClass(value) {
    if (TS_MODULE_BOARD?.statusClass) {
        return TS_MODULE_BOARD.statusClass(value);
    }

    return String(value || '').trim().toLowerCase().replace(/_/g, '-');
}

function moduleBoardPriorityClass(value) {
    if (TS_MODULE_BOARD?.priorityClass) {
        return TS_MODULE_BOARD.priorityClass(value);
    }

    return String(value || '').trim().toLowerCase();
}

function moduleBoardGetRow(moduleKey, tabKey, itemId) {
    const key = moduleBoardKey(moduleKey, tabKey);
    const rows = Array.isArray(WORKBOARD_STATE.rowsByKey[key]) ? WORKBOARD_STATE.rowsByKey[key] : [];
    return rows.find((row) => Number(row.id) === Number(itemId)) || null;
}

function moduleBoardRenderRows(moduleKey, tabKey, rows) {
    const tbody = moduleBoardElement(moduleKey, tabKey, 'tbody');
    if (!tbody) return;
    const normalizedRows = Array.isArray(rows) ? rows : [];
    const canEdit = moduleBoardCanEdit();
    tbody.innerHTML = normalizedRows.map((row, idx) => {
        const projectLabel = row.project_code
            ? `${moduleBoardEsc(row.project_code)}${row.project_name ? ` - ${moduleBoardEsc(row.project_name)}` : ''}`
            : '-';
        const disciplineLabel = row.discipline_code
            ? `${moduleBoardEsc(row.discipline_code)}${row.discipline_name ? ` - ${moduleBoardEsc(row.discipline_name)}` : ''}`
            : '-';
        return `
<tr>
    <td>${idx + 1}</td>
    <td>
        <div style="font-weight:700; color:#0f172a;">${moduleBoardEsc(row.title || '-')}</div>
        <div style="font-size:0.78rem; color:#64748b; margin-top:4px;">${moduleBoardEsc(row.description || '')}</div>
    </td>
    <td>${projectLabel}</td>
    <td>${disciplineLabel}</td>
    <td><span class="module-crud-status is-${moduleBoardStatusClass(row.status)}">${moduleBoardEsc(WORKBOARD_STATUS_LABELS[row.status] || row.status || '-')}</span></td>
    <td><span class="module-crud-priority is-${moduleBoardPriorityClass(row.priority)}">${moduleBoardEsc(WORKBOARD_PRIORITY_LABELS[row.priority] || row.priority || '-')}</span></td>
    <td>${moduleBoardEsc(moduleBoardFormatDate(row.due_date, false))}</td>
    <td>${moduleBoardEsc(moduleBoardFormatDate(row.updated_at || row.created_at, true))}</td>
    <td>
        <div class="module-crud-actions">
            ${canEdit ? `<button type="button" class="btn-archive-icon" data-mb-action="edit-item" data-item-id="${Number(row.id)}">ویرایش</button>` : ''}
            ${canEdit ? `<button type="button" class="btn-archive-icon" data-mb-action="delete-item" data-item-id="${Number(row.id)}">حذف</button>` : ''}
            ${!canEdit ? '-' : ''}
        </div>
    </td>
</tr>
`;
    }).join('');
}

async function moduleBoardLoad(moduleKey, tabKey, force = false) {
    if (TS_MODULE_BOARD?.load) {
        try {
            const handled = await TS_MODULE_BOARD.load(moduleKey, tabKey, force, {
                initBoards: () => initModuleCrudBoards(),
                elementByName: (mKey, tKey, name) => moduleBoardElement(mKey, tKey, name),
                fetchList: async (query) => {
                    try {
                        const res = await window.fetchWithAuth(`${API_BASE}/workboard/list?${query}`);
                        const body = await res.json();
                        return { ok: !!res.ok, body };
                    } catch (error) {
                        console.warn('moduleBoardLoad fetch failed:', error);
                        return { ok: false, body: null };
                    }
                },
                setRowsCache: (mKey, tKey, rows) => {
                    WORKBOARD_STATE.rowsByKey[moduleBoardKey(mKey, tKey)] = Array.isArray(rows) ? rows : [];
                },
                renderRows: (mKey, tKey, rows) => moduleBoardRenderRows(mKey, tKey, rows),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    initModuleCrudBoards();
    const key = moduleBoardKey(moduleKey, tabKey);
    const tbody = moduleBoardElement(moduleKey, tabKey, 'tbody');
    const emptyEl = moduleBoardElement(moduleKey, tabKey, 'empty');
    if (!tbody || !emptyEl) return;

    const searchInput = moduleBoardElement(moduleKey, tabKey, 'filter-search');
    const statusSelect = moduleBoardElement(moduleKey, tabKey, 'filter-status');
    const projectSelect = moduleBoardElement(moduleKey, tabKey, 'filter-project');
    const disciplineSelect = moduleBoardElement(moduleKey, tabKey, 'filter-discipline');

    const params = new URLSearchParams({
        module_key: String(moduleKey || '').trim().toLowerCase(),
        tab_key: String(tabKey || '').trim().toLowerCase(),
        limit: '250',
        skip: '0',
    });
    const searchValue = String(searchInput?.value || '').trim();
    const statusValue = String(statusSelect?.value || '').trim();
    const projectValue = String(projectSelect?.value || '').trim();
    const disciplineValue = String(disciplineSelect?.value || '').trim();
    if (searchValue) params.set('search', searchValue);
    if (statusValue) params.set('status', statusValue);
    if (projectValue) params.set('project_code', projectValue);
    if (disciplineValue) params.set('discipline_code', disciplineValue);

    if (force) {
        tbody.innerHTML = '';
        emptyEl.textContent = 'در حال بارگذاری...';
        emptyEl.style.display = 'block';
    }

    try {
        const res = await window.fetchWithAuth(`${API_BASE}/workboard/list?${params.toString()}`);
        const body = await res.json();
        if (!res.ok || !body?.ok) {
            throw new Error(body?.detail || 'Failed to load workboard items.');
        }
        const rows = Array.isArray(body.data) ? body.data : [];
        WORKBOARD_STATE.rowsByKey[key] = rows;

        if (!rows.length) {
            tbody.innerHTML = '';
            emptyEl.textContent = 'آیتمی یافت نشد.';
            emptyEl.style.display = 'block';
            return;
        }

        moduleBoardRenderRows(moduleKey, tabKey, rows);
        emptyEl.style.display = 'none';
    } catch (error) {
        console.error('moduleBoardLoad failed:', error);
        tbody.innerHTML = '';
        emptyEl.textContent = error.message || 'خطا در بارگذاری آیتم‌ها.';
        emptyEl.style.display = 'block';
    }
}

function moduleBoardDebouncedLoad(moduleKey, tabKey) {
    if (TS_MODULE_BOARD?.debouncedLoad) {
        try {
            TS_MODULE_BOARD.debouncedLoad(moduleKey, tabKey, {
                delayMs: 420,
                loadItems: (mKey, tKey, force) => moduleBoardLoad(mKey, tKey, force),
            });
            return;
        } catch (error) {
            throw error;
        }
    }

    const key = moduleBoardKey(moduleKey, tabKey);
    clearTimeout(WORKBOARD_STATE.timers[key]);
    WORKBOARD_STATE.timers[key] = setTimeout(() => {
        moduleBoardLoad(moduleKey, tabKey, false);
    }, 420);
}

function moduleBoardResetForm(moduleKey, tabKey) {
    if (TS_MODULE_BOARD?.resetForm) {
        try {
            const handled = TS_MODULE_BOARD.resetForm(moduleKey, tabKey, {
                canEdit: () => moduleBoardCanEdit(),
                elementByName: (mKey, tKey, name) => moduleBoardElement(mKey, tKey, name),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    const idInput = moduleBoardElement(moduleKey, tabKey, 'form-id');
    const titleInput = moduleBoardElement(moduleKey, tabKey, 'form-title');
    const descInput = moduleBoardElement(moduleKey, tabKey, 'form-description');
    const projectSelect = moduleBoardElement(moduleKey, tabKey, 'form-project');
    const disciplineSelect = moduleBoardElement(moduleKey, tabKey, 'form-discipline');
    const statusSelect = moduleBoardElement(moduleKey, tabKey, 'form-status');
    const prioritySelect = moduleBoardElement(moduleKey, tabKey, 'form-priority');
    const dueInput = moduleBoardElement(moduleKey, tabKey, 'form-due');
    if (idInput) idInput.value = '';
    if (titleInput) titleInput.value = '';
    if (descInput) descInput.value = '';
    if (projectSelect) projectSelect.value = '';
    if (disciplineSelect) disciplineSelect.value = '';
    if (statusSelect) statusSelect.value = 'open';
    if (prioritySelect) prioritySelect.value = 'normal';
    if (dueInput) dueInput.value = '';
}

function moduleBoardOpenForm(moduleKey, tabKey, item = null) {
    if (TS_MODULE_BOARD?.openForm) {
        try {
            const handled = TS_MODULE_BOARD.openForm(moduleKey, tabKey, item, {
                canEdit: () => moduleBoardCanEdit(),
                elementByName: (mKey, tKey, name) => moduleBoardElement(mKey, tKey, name),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    if (!moduleBoardCanEdit()) return;
    const wrap = moduleBoardElement(moduleKey, tabKey, 'form-wrap');
    if (!wrap) return;
    moduleBoardResetForm(moduleKey, tabKey);
    if (item) {
        const idInput = moduleBoardElement(moduleKey, tabKey, 'form-id');
        const titleInput = moduleBoardElement(moduleKey, tabKey, 'form-title');
        const descInput = moduleBoardElement(moduleKey, tabKey, 'form-description');
        const projectSelect = moduleBoardElement(moduleKey, tabKey, 'form-project');
        const disciplineSelect = moduleBoardElement(moduleKey, tabKey, 'form-discipline');
        const statusSelect = moduleBoardElement(moduleKey, tabKey, 'form-status');
        const prioritySelect = moduleBoardElement(moduleKey, tabKey, 'form-priority');
        const dueInput = moduleBoardElement(moduleKey, tabKey, 'form-due');

        if (idInput) idInput.value = String(item.id || '');
        if (titleInput) titleInput.value = String(item.title || '');
        if (descInput) descInput.value = String(item.description || '');
        if (projectSelect) projectSelect.value = String(item.project_code || '');
        if (disciplineSelect) disciplineSelect.value = String(item.discipline_code || '');
        if (statusSelect) statusSelect.value = String(item.status || 'open');
        if (prioritySelect) prioritySelect.value = String(item.priority || 'normal');
        if (dueInput) dueInput.value = String(item.due_date || '').slice(0, 10);
    }
    wrap.hidden = false;
}

function moduleBoardCloseForm(moduleKey, tabKey) {
    if (TS_MODULE_BOARD?.closeForm) {
        try {
            const handled = TS_MODULE_BOARD.closeForm(moduleKey, tabKey, {
                canEdit: () => moduleBoardCanEdit(),
                elementByName: (mKey, tKey, name) => moduleBoardElement(mKey, tKey, name),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    const wrap = moduleBoardElement(moduleKey, tabKey, 'form-wrap');
    if (wrap) wrap.hidden = true;
    moduleBoardResetForm(moduleKey, tabKey);
}

async function moduleBoardSave(moduleKey, tabKey) {
    if (TS_MODULE_BOARD?.save) {
        try {
            const handled = await TS_MODULE_BOARD.save(moduleKey, tabKey, {
                canEdit: () => moduleBoardCanEdit(),
                elementByName: (mKey, tKey, name) => moduleBoardElement(mKey, tKey, name),
                fetchJson: async (endpoint, init = {}) => {
                    try {
                        const res = await window.fetchWithAuth(endpoint, init);
                        const body = await res.json();
                        return { ok: !!res.ok, body };
                    } catch (error) {
                        console.warn('moduleBoardSave fetch failed:', error);
                        return { ok: false, body: null };
                    }
                },
                showToast: (message, type) => showToast(message, type),
                closeForm: (mKey, tKey) => moduleBoardCloseForm(mKey, tKey),
                loadItems: (mKey, tKey, force) => moduleBoardLoad(mKey, tKey, force),
                refreshSummary: (mKey) => moduleBoardRefreshSummary(mKey),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    if (!moduleBoardCanEdit()) return;
    const idInput = moduleBoardElement(moduleKey, tabKey, 'form-id');
    const titleInput = moduleBoardElement(moduleKey, tabKey, 'form-title');
    const descInput = moduleBoardElement(moduleKey, tabKey, 'form-description');
    const projectSelect = moduleBoardElement(moduleKey, tabKey, 'form-project');
    const disciplineSelect = moduleBoardElement(moduleKey, tabKey, 'form-discipline');
    const statusSelect = moduleBoardElement(moduleKey, tabKey, 'form-status');
    const prioritySelect = moduleBoardElement(moduleKey, tabKey, 'form-priority');
    const dueInput = moduleBoardElement(moduleKey, tabKey, 'form-due');

    const title = String(titleInput?.value || '').trim();
    if (!title) {
        showToast('عنوان آیتم الزامی است.', 'error');
        titleInput?.focus();
        return;
    }

    const payload = {
        module_key: String(moduleKey || '').trim().toLowerCase(),
        tab_key: String(tabKey || '').trim().toLowerCase(),
        title,
        description: String(descInput?.value || '').trim() || null,
        project_code: String(projectSelect?.value || '').trim() || null,
        discipline_code: String(disciplineSelect?.value || '').trim() || null,
        status: String(statusSelect?.value || 'open').trim() || 'open',
        priority: String(prioritySelect?.value || 'normal').trim() || 'normal',
        due_date: String(dueInput?.value || '').trim() ? String(dueInput.value).trim() : null,
    };

    const itemId = Number(idInput?.value || 0);
    const endpoint = itemId > 0 ? `${API_BASE}/workboard/${itemId}` : `${API_BASE}/workboard/create`;
    const method = itemId > 0 ? 'PUT' : 'POST';

    try {
        const res = await window.fetchWithAuth(endpoint, {
            method,
            body: JSON.stringify(payload),
        });
        const body = await res.json();
        if (!res.ok || !body?.ok) {
            throw new Error(body?.detail || 'خطا در ذخیره آیتم.');
        }
        showToast(itemId > 0 ? 'آیتم بروزرسانی شد.' : 'آیتم جدید ثبت شد.', 'success');
        moduleBoardCloseForm(moduleKey, tabKey);
        await moduleBoardLoad(moduleKey, tabKey, true);
        await moduleBoardRefreshSummary(moduleKey);
    } catch (error) {
        console.error('moduleBoardSave failed:', error);
        showToast(error.message || 'خطا در ذخیره آیتم.', 'error');
    }
}

function moduleBoardEdit(moduleKey, tabKey, itemId) {
    if (TS_MODULE_BOARD?.edit) {
        try {
            const handled = TS_MODULE_BOARD.edit(moduleKey, tabKey, itemId, {
                canEdit: () => moduleBoardCanEdit(),
                elementByName: (mKey, tKey, name) => moduleBoardElement(mKey, tKey, name),
                getRow: (mKey, tKey, id) => moduleBoardGetRow(mKey, tKey, id),
                showToast: (message, type) => showToast(message, type),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    const row = moduleBoardGetRow(moduleKey, tabKey, itemId);
    if (!row) {
        showToast('آیتم موردنظر یافت نشد.', 'error');
        return;
    }
    moduleBoardOpenForm(moduleKey, tabKey, row);
}

async function moduleBoardDelete(moduleKey, tabKey, itemId) {
    if (TS_MODULE_BOARD?.delete) {
        try {
            const handled = await TS_MODULE_BOARD.delete(moduleKey, tabKey, itemId, {
                canEdit: () => moduleBoardCanEdit(),
                getRow: (mKey, tKey, id) => moduleBoardGetRow(mKey, tKey, id),
                confirmAction: (message) => confirm(message),
                fetchJson: async (endpoint, init = {}) => {
                    try {
                        const res = await window.fetchWithAuth(endpoint, init);
                        const body = await res.json();
                        return { ok: !!res.ok, body };
                    } catch (error) {
                        console.warn('moduleBoardDelete fetch failed:', error);
                        return { ok: false, body: null };
                    }
                },
                showToast: (message, type) => showToast(message, type),
                loadItems: (mKey, tKey, force) => moduleBoardLoad(mKey, tKey, force),
                refreshSummary: (mKey) => moduleBoardRefreshSummary(mKey),
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    if (!moduleBoardCanEdit()) return;
    const row = moduleBoardGetRow(moduleKey, tabKey, itemId);
    const title = row?.title ? `«${row.title}»` : `#${itemId}`;
    if (!confirm(`آیا از حذف آیتم ${title} مطمئن هستید؟`)) return;

    try {
        const res = await window.fetchWithAuth(`${API_BASE}/workboard/${Number(itemId)}`, { method: 'DELETE' });
        const body = await res.json();
        if (!res.ok || !body?.ok) {
            throw new Error(body?.detail || 'خطا در حذف آیتم.');
        }
        showToast('آیتم حذف شد.', 'success');
        await moduleBoardLoad(moduleKey, tabKey, true);
        await moduleBoardRefreshSummary(moduleKey);
    } catch (error) {
        console.error('moduleBoardDelete failed:', error);
        showToast(error.message || 'خطا در حذف آیتم.', 'error');
    }
}

async function moduleBoardRefreshSummary(moduleKey) {
    if (TS_MODULE_BOARD?.refreshSummary) {
        const handled = await TS_MODULE_BOARD.refreshSummary(moduleKey, {
            fetchSummary: async (normalizedModuleKey) => {
                try {
                    const res = await window.fetchWithAuth(`${API_BASE}/workboard/summary?module_key=${encodeURIComponent(String(normalizedModuleKey || '').trim().toLowerCase())}`);
                    const body = await res.json();
                    return { ok: !!res.ok, body };
                } catch (error) {
                    console.warn('moduleBoardRefreshSummary fetch failed:', error);
                    return { ok: false, body: null };
                }
            },
        });
        if (handled) return;
    }

    const normalized = String(moduleKey || '').trim().toLowerCase();
    if (!normalized) return;
    try {
        const res = await window.fetchWithAuth(`${API_BASE}/workboard/summary?module_key=${encodeURIComponent(normalized)}`);
        const body = await res.json();
        if (!res.ok || !body?.ok) return;
        const stats = body.stats || {};
        const map = normalized === 'consultant'
            ? {
                total: 'consultant-stat-total',
                open: 'consultant-stat-open',
                waiting: 'consultant-stat-waiting',
                overdue: 'consultant-stat-overdue',
            }
            : {
                total: 'contractor-stat-total',
                open: 'contractor-stat-open',
                waiting: 'contractor-stat-waiting',
                overdue: 'contractor-stat-overdue',
            };
        Object.entries(map).forEach(([field, id]) => {
            const el = document.getElementById(id);
            if (el) {
                const value = Number(stats[field] ?? 0);
                el.textContent = Number.isFinite(value) ? String(value) : '0';
            }
        });
    } catch (error) {
        console.warn('moduleBoardRefreshSummary failed:', error);
    }
}

async function moduleBoardOnTabOpened(moduleKey, tabKey) {
    if (TS_MODULE_BOARD?.onTabOpened) {
        const handled = await TS_MODULE_BOARD.onTabOpened(moduleKey, tabKey, {
            initBoards: () => initModuleCrudBoards(),
            loadItems: (mKey, tKey, force) => moduleBoardLoad(mKey, tKey, force),
            fetchSummary: async (normalizedModuleKey) => {
                try {
                    const res = await window.fetchWithAuth(`${API_BASE}/workboard/summary?module_key=${encodeURIComponent(String(normalizedModuleKey || '').trim().toLowerCase())}`);
                    const body = await res.json();
                    return { ok: !!res.ok, body };
                } catch (error) {
                    console.warn('moduleBoardOnTabOpened summary fetch failed:', error);
                    return { ok: false, body: null };
                }
            },
        });
        if (handled) return;
    }

    initModuleCrudBoards();
    await moduleBoardLoad(moduleKey, tabKey, true);
    await moduleBoardRefreshSummary(moduleKey);
}

window.moduleBoardLoad = moduleBoardLoad;
window.moduleBoardDebouncedLoad = moduleBoardDebouncedLoad;
window.moduleBoardOpenForm = moduleBoardOpenForm;
window.moduleBoardCloseForm = moduleBoardCloseForm;
window.moduleBoardSave = moduleBoardSave;
window.moduleBoardEdit = moduleBoardEdit;
window.moduleBoardDelete = moduleBoardDelete;

// ============================================================
//  1. NAVIGATION LOGIC (Ù…Ø¯ÛŒØ±ÛŒØª Ø¬Ø§Ø¨Ø¬Ø§ÛŒÛŒ ØµÙØ­Ø§Øª)
// ============================================================

async function runViewInitializer(viewId) {
    if (TS_APP_ROUTER?.runViewInitializer) {
        try {
            return await TS_APP_ROUTER.runViewInitializer(viewId);
        } catch (error) {
            throw error;
        }
    }
    return false;
}

function activateViewSection(viewId) {
    if (TS_APP_ROUTER?.activateView) {
        try {
            return TS_APP_ROUTER.activateView(viewId);
        } catch (error) {
            throw error;
        }
    }

    document.querySelectorAll('.view-section').forEach(el => {
        el.style.display = 'none';
        el.classList.remove('active');
    });

    const target = document.getElementById(viewId);
    if (!target) return null;
    target.style.display = 'block';
    target.classList.add('active');
    return target;
}

function buildRouterDeps() {
    return {
        mapToRoutedView: (requestedViewId) => mapToRoutedView(requestedViewId),
        requireAuth: () => (typeof window.requireAuth === 'function' ? !!window.requireAuth() : true),
        requireAdmin: () => (typeof window.requireAdmin === 'function' ? !!window.requireAdmin() : false),
        isAdminOnlyView: (routedViewId) => ADMIN_ONLY_VIEWS.has(String(routedViewId || '').trim()),
        setPendingSettingsTab: (tabName) => {
            PENDING_SETTINGS_TAB = tabName || null;
        },
        getPendingSettingsTab: () => PENDING_SETTINGS_TAB,
        clearPendingSettingsTab: () => {
            PENDING_SETTINGS_TAB = null;
        },
        getPendingEdmsTab: () => (TS_EDMS_STATE?.getPendingEdmsTab ? TS_EDMS_STATE.getPendingEdmsTab() : PENDING_EDMS_TAB),
        markPerf: (name) => markPerf(name),
        measurePerf: (metricName, startMark, endMark) => measurePerf(metricName, startMark, endMark),
        renderDevPerformancePanel: () => renderDevPerformancePanel(),
        loadViewPartial: (routedViewId) => loadViewPartial(routedViewId),
        activateView: (routedViewId) => activateViewSection(routedViewId),
        runViewInitializer: (routedViewId) => runViewInitializer(routedViewId),
        initDashboard: () => {
            if (typeof initDashboard === 'function') initDashboard();
        },
        loadEdmsLastTab: () => loadEdmsLastTab(),
        getEffectiveDefaultEdmsTab: () => getEffectiveDefaultEdmsTab(),
        isEdmsTabVisible: (tabName) => isEdmsTabVisible(tabName),
        getFirstVisibleEdmsTab: () => getFirstVisibleEdmsTab(),
        openEdmsTab: (tabName) => openEdmsTab(tabName),
        loadEdmsHeaderStats: () => loadEdmsHeaderStats(),
        showToast: (message, type = 'info') => showToast(message, type),
        initReportsView: () => {
            if (typeof initReportsView === 'function') initReportsView();
        },
        initContractorView: () => {
            if (typeof initContractorView === 'function') initContractorView();
        },
        initConsultantView: () => {
            if (typeof initConsultantView === 'function') initConsultantView();
        },
        openSettingsTab: (tabName) => {
            if (typeof openSettingsTab === 'function') openSettingsTab(tabName);
        },
        initUserSettingsView: () => {
            if (typeof initUserSettingsView === 'function') initUserSettingsView();
        },
        emitViewActivated: (routedViewId) => {
            window.AppEvents?.emit?.('view:activated', { viewId: routedViewId });
        },
        updateSidebarState: (routedViewId) => updateSidebarState(routedViewId),
    };
}

async function navigateTo(viewId) {
    if (!TS_APP_ROUTER?.navigateTo) {
        throw new Error('App router bridge unavailable.');
    }
    const handled = await TS_APP_ROUTER.navigateTo(viewId, buildRouterDeps());
    if (!handled) {
        throw new Error(`App router failed to handle navigation for view: ${String(viewId || '')}`);
    }
}

window.navigateTo = navigateTo;
window.App = window.App || {};
window.App.navigateTo = navigateTo;
window.App.events = window.AppEvents || null;

function updateSidebarState(activeViewId) {
    if (TS_APP_SHELL?.updateSidebarState) {
        TS_APP_SHELL.updateSidebarState(activeViewId);
        return;
    }

    // Ø­Ø°Ù Ú©Ù„Ø§Ø³ active Ø§Ø² Ù‡Ù…Ù‡ Ø¢ÛŒØªÙ…â€ŒÙ‡Ø§
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    let navTargetView = activeViewId;
    if (activeViewId === 'view-users' || activeViewId === 'view-bulk') {
        navTargetView = 'view-settings';
    } else if (activeViewId === 'view-archive' || activeViewId === 'view-transmittal' || activeViewId === 'view-correspondence') {
        navTargetView = 'view-edms';
    }

    // Ø§Ø¶Ø§ÙÙ‡ Ú©Ø±Ø¯Ù† Ú©Ù„Ø§Ø³ active Ø¨Ù‡ Ø¢ÛŒØªÙ… Ù…ÙˆØ±Ø¯ Ù†Ø¸Ø±
    const activeNavItem = document.getElementById(`nav-${navTargetView.replace('view-', '')}`);
    if (activeNavItem) {
        activeNavItem.classList.add('active');
    }
}

// ============================================================
//  2. GLOBAL HELPERS (Ú©Ù…Ú©â€ŒÚ©Ù†Ù†Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ø¹Ù…ÙˆÙ…ÛŒ)
// ============================================================

function toggleLoader(show) {
    const loader = document.getElementById('global-loader');
    if (loader) {
        loader.style.display = show ? 'flex' : 'none';
    }
}

function showToast(message, type = 'info', duration = 3000) {
    // Ø§ÛŒØ¬Ø§Ø¯ container Ø§Ú¯Ø± ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ø¯
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = `
            position: fixed; top: 20px; right: 20px; z-index: 10000;
            display: flex; flex-direction: column; gap: 10px;
        `;
        document.body.appendChild(container);
    }
    
    // Ø§ÛŒØ¬Ø§Ø¯ toast
    const toast = document.createElement('div');
    toast.style.cssText = `
        background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3b82f6'};
        color: white; padding: 12px 20px; border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-size: 0.9rem;
        animation: slideIn 0.3s ease; max-width: 300px;
    `;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // Ø­Ø°Ù Ø®ÙˆØ¯Ú©Ø§Ø±
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ============================================================
//  3. SIDEBAR & UI HELPERS (Ú©Ù…Ú©â€ŒÚ©Ù†Ù†Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ø±Ø§Ø¨Ø· Ú©Ø§Ø±Ø¨Ø±ÛŒ)
// ============================================================

function toggleSidebar() {
    if (TS_APP_SHELL?.toggleSidebar) {
        TS_APP_SHELL.toggleSidebar();
        return;
    }

    const sidebar = document.getElementById('app-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    
    // ØªØ´Ø®ÛŒØµ Ù…ÙˆØ¨Ø§ÛŒÙ„ ÛŒØ§ Ø¯Ø³Ú©ØªØ§Ù¾
    if (window.innerWidth <= 992) {
        // Ù…Ù†Ø·Ù‚ Ù…ÙˆØ¨Ø§ÛŒÙ„ (Ø§Ø³ØªÙØ§Ø¯Ù‡ Ø§Ø² Ú©Ù„Ø§Ø³ open Ø±ÙˆÛŒ Ø®ÙˆØ¯ Ø³Ø§ÛŒØ¯Ø¨Ø§Ø±)
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('show');
    } else {
        // Ù…Ù†Ø·Ù‚ Ø¯Ø³Ú©ØªØ§Ù¾ (Ø§Ø³ØªÙØ§Ø¯Ù‡ Ø§Ø² Ú©Ù„Ø§Ø³ Ø±ÙˆÛŒ body Ø¨Ø±Ø§ÛŒ Ø¬Ø§Ø¨Ø¬Ø§ÛŒÛŒ Ù…Ø­ØªÙˆØ§)
        document.body.classList.toggle('sidebar-closed');
        
        // Ø°Ø®ÛŒØ±Ù‡ ÙˆØ¶Ø¹ÛŒØª Ø¯Ø± Ú©ÙˆÚ©ÛŒ Ø¨Ø±Ø§ÛŒ Ø±ÙØ±Ø´ Ø¨Ø¹Ø¯ÛŒ
        const isClosed = document.body.classList.contains('sidebar-closed');
        document.cookie = `sidebar_status=${isClosed ? 'closed' : 'open'}; path=/; max-age=31536000`;
    }
}

function toggleUserMenu() {
    if (TS_APP_SHELL?.toggleUserMenu) {
        TS_APP_SHELL.toggleUserMenu();
        return;
    }

    const dropdown = document.getElementById('user-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

window.showToast = showToast;

// ============================================================
//  4. TRANSMITTAL LOGIC
// ============================================================

function toggleTransmittalMode(mode) {
    const listEl = document.getElementById('trans-list-mode');
    const newEl = document.getElementById('trans-new-mode');
    
    // Safety Check: Ø§Ú¯Ø± Ø§Ù„Ù…Ø§Ù†â€ŒÙ‡Ø§ Ø¯Ø± ØµÙØ­Ù‡ Ù†Ø¨ÙˆØ¯Ù†Ø¯ØŒ Ø§Ø¯Ø§Ù…Ù‡ Ù†Ø¯Ù‡
    if (!listEl || !newEl) return;
    
    if(listEl) listEl.style.display = (mode === 'list') ? 'block' : 'none';
    if(newEl) newEl.style.display = (mode === 'new') ? 'block' : 'none';
    
    if(mode === 'new') {
        // ÙÙ‚Ø· Ø¯Ø± ØµÙˆØ±ØªÛŒ ØªØ§Ø¨Ø¹ Ù„ÙˆØ¯ Ø±Ø§ ØµØ¯Ø§ Ø¨Ø²Ù† Ú©Ù‡ ØªØ¹Ø±ÛŒÙ Ø´Ø¯Ù‡ Ø¨Ø§Ø´Ø¯
        if (typeof loadDocsForTransmittal === 'function') loadDocsForTransmittal();
    } else {
        if (typeof loadTransmittals === 'function') loadTransmittals();
    }
}

// ============================================================
//  5. DICTIONARY & DATA LOADING (Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ù¾Ø§ÛŒÙ‡)
// ============================================================

async function loadDictionary() {
    if (TS_APP_DATA?.loadDictionary) {
        try {
            const handled = await TS_APP_DATA.loadDictionary({
                apiBase: API_BASE,
                fetchDictionary: async (url) => {
                    try {
                        const res = (typeof window.fetchWithAuth === 'function')
                            ? await window.fetchWithAuth(url)
                            : await fetch(url);
                        const body = await res.json();
                        return {
                            ok: !!res.ok,
                            status: Number(res.status || 0),
                            body,
                        };
                    } catch (error) {
                        console.warn('loadDictionary fetch failed:', error);
                        return {
                            ok: false,
                            status: 0,
                            body: null,
                        };
                    }
                },
                setCache: (cache) => {
                    window.CACHE = cache || {};
                },
            });
            if (handled) return;
        } catch (error) {
            throw error;
        }
    }

    try {
        const url = `${API_BASE}/lookup/dictionary`;
        const res = (typeof window.fetchWithAuth === 'function')
            ? await window.fetchWithAuth(url)
            : await fetch(url);
        if (!res.ok) {
            throw new Error(`Dictionary request failed: ${res.status}`);
        }
        const data = await res.json();
        if (data.ok) {
            window.CACHE = data.data || {};
            console.log('âœ… Dictionary loaded:', Object.keys(window.CACHE));
        }
    } catch (error) {
        console.error('âŒ Failed to load dictionary:', error);
    }
}

// ============================================================
//  6. CONTEXT MENU (Ù…Ù†ÙˆÛŒ Ø±Ø§Ø³Øª Ú©Ù„ÛŒÚ©)
// ============================================================

function handleAction(action) {
    if (!SELECTED_DOC_ID) {
        showToast('Ù„Ø·ÙØ§Ù‹ Ø§Ø¨ØªØ¯Ø§ ÛŒÚ© Ø³Ù†Ø¯ Ø±Ø§ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯', 'error');
        return;
    }
    
    switch(action) {
        case 'view':
            showToast(`Ù…Ø´Ø§Ù‡Ø¯Ù‡ Ø¬Ø²Ø¦ÛŒØ§Øª Ø³Ù†Ø¯ ${SELECTED_DOC_ID}`, 'info');
            break;
        case 'history':
            showToast(`ØªØ§Ø±ÛŒØ®Ú†Ù‡ Ø³Ù†Ø¯ ${SELECTED_DOC_ID}`, 'info');
            break;
        case 'upload':
            showToast(`Ø¢Ù¾Ù„ÙˆØ¯ ÙØ§ÛŒÙ„ Ø¬Ø¯ÛŒØ¯ Ø¨Ø±Ø§ÛŒ Ø³Ù†Ø¯ ${SELECTED_DOC_ID}`, 'info');
            break;
        case 'delete':
            if (confirm(`Ø¢ÛŒØ§ Ø§Ø² Ø­Ø°Ù Ø³Ù†Ø¯ ${SELECTED_DOC_ID} Ø§Ø·Ù…ÛŒÙ†Ø§Ù† Ø¯Ø§Ø±ÛŒØ¯ØŸ`)) {
                showToast(`Ø³Ù†Ø¯ ${SELECTED_DOC_ID} Ø­Ø°Ù Ø´Ø¯`, 'success');
            }
            break;
    }
    
    // Ø¨Ø³ØªÙ† Ù…Ù†ÙˆÛŒ Ø±Ø§Ø³Øª Ú©Ù„ÛŒÚ©
    const ctxMenu = document.getElementById('context-menu');
    if (ctxMenu) ctxMenu.classList.remove('show');
}

// ============================================================
//  7. UTILITIES (Ø§Ø¨Ø²Ø§Ø±Ù‡Ø§ÛŒ Ú©Ù…Ú©ÛŒ)
// ============================================================

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Ú©Ù¾ÛŒ Ø´Ø¯', 'success', 1500);
    }).catch(() => {
        showToast('Ø®Ø·Ø§ Ø¯Ø± Ú©Ù¾ÛŒ', 'error');
    });
}

// ============================================================
//  8. ANIMATIONS (Ø§Ù†ÛŒÙ…ÛŒØ´Ù†â€ŒÙ‡Ø§)
// ============================================================

// Ø§Ø¶Ø§ÙÙ‡ Ú©Ø±Ø¯Ù† Ø§Ø³ØªØ§ÛŒÙ„ Ø§Ù†ÛŒÙ…ÛŒØ´Ù†â€ŒÙ‡Ø§ Ø§Ú¯Ø± ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ø¯
if (!document.querySelector('#toast-animations')) {
    const style = document.createElement('style');
    style.id = 'toast-animations';
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
}



