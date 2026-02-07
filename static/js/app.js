/**
 * MDR System - Main Application Logic
 * Path: static/js/app.js
 * Version: 2.4 Final (Responsive Sidebar & Reports Added)
 */

// ðŸ›‘ Ú¯Ø§Ø±Ø¯ Ø§ÛŒÙ…Ù†ÛŒ: Ø§Ú¯Ø± Ø¯Ø± ØµÙØ­Ù‡ Ù„Ø§Ú¯ÛŒÙ† Ù‡Ø³ØªÛŒÙ…ØŒ Ú©Ø¯Ù‡Ø§ÛŒ Ø§ØµÙ„ÛŒ Ø¨Ø±Ù†Ø§Ù…Ù‡ Ø±Ø§ Ø§Ø¬Ø±Ø§ Ù†Ú©Ù†
if (window.location.pathname.includes('/login')) {
    console.log("Login page detected. Skipping app.js logic.");
    window.__SKIP_APP_BOOT = true;
}

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
    reports: true,
};
let EDMS_STATS_LOADING = false;
let EDMS_STATS_LAST_LOADED_AT = 0;

const EDMS_TAB_TO_VIEW = {
    archive: 'view-archive',
    transmittal: 'view-transmittal',
    correspondence: 'view-correspondence',
    reports: 'view-reports',
};

const EDMS_VIEW_TO_TAB = {
    'view-archive': 'archive',
    'view-transmittal': 'transmittal',
    'view-correspondence': 'correspondence',
    'view-reports': 'reports',
};

const VIEW_IDS = [
    'view-dashboard',
    'view-edms',
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

// ============================================================
//  0. INITIALIZATION (Ø±Ø§Ù‡â€ŒØ§Ù†Ø¯Ø§Ø²ÛŒ Ø§ÙˆÙ„ÛŒÙ‡)
// ============================================================
window.onload = async () => {
    // â›” Ù„ÛŒØ³Øª ØµÙØ­Ø§Øª Ø¹Ù…ÙˆÙ…ÛŒ Ú©Ù‡ Ù†Ø¨Ø§ÛŒØ¯ Ú†Ú© Ø´ÙˆÙ†Ø¯
    const publicPages = ['/login', '/debug_login'];
    const path = window.location.pathname;
    
    // Ø§Ú¯Ø± Ø¯Ø± ØµÙØ­Ù‡ Ø¹Ù…ÙˆÙ…ÛŒ Ù‡Ø³ØªÛŒÙ…ØŒ Ù‡ÛŒÚ† Ú©Ø§Ø±ÛŒ Ù†Ú©Ù†
    if (publicPages.includes(path)) {
        console.log("Skipping app init on public page:", path);
        return;
    }
    
    toggleLoader(true);
    
    // 1. Ø¯Ø±ÛŒØ§ÙØª Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ù¾Ø§ÛŒÙ‡ (Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§ØŒ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†â€ŒÙ‡Ø§ Ùˆ...)
    await loadDictionary();
    await loadEdmsNavigation();
    
    // 2. Ø§Ø¬Ø¨Ø§Ø± Ø¨Ù‡ Ù†Ù…Ø§ÛŒØ´ Ø¯Ø§Ø´Ø¨ÙˆØ±Ø¯ Ø¯Ø± Ø´Ø±ÙˆØ¹ Ú©Ø§Ø±
    navigateTo('view-dashboard');
    
    toggleLoader(false);
    
    // 3. ÙØ¹Ø§Ù„â€ŒØ³Ø§Ø²ÛŒ Ù„ÛŒØ³Ù†Ø±Ù‡Ø§ (Ú©Ù„ÛŒÚ©â€ŒÙ‡Ø§ÛŒ Ø¹Ù…ÙˆÙ…ÛŒ)
    setupGlobalListeners();

    // 4. Ø¯Ø±ÛŒØ§ÙØª Ù¾ÛŒØ§Ù… Ø§Ø² iframe (Ø¨Ø±Ø§ÛŒ Ø«Ø¨Øª Ú¯Ø±ÙˆÙ‡ÛŒ)
    window.addEventListener('message', (event) => {
        if (event.data === 'refreshDashboard') {
            console.log("ðŸ”„ Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ø±ÙØ±Ø´ Ø§Ø² Ø³Ù…Øª iframe Ø¯Ø±ÛŒØ§ÙØª Ø´Ø¯.");
            if (typeof initDashboard === 'function') initDashboard();
            showToast("âœ… Ø¹Ù…Ù„ÛŒØ§Øª Ø«Ø¨Øª Ú¯Ø±ÙˆÙ‡ÛŒ Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯.", "success");
        }
    });
};

function setupGlobalListeners() {
    document.addEventListener('click', (e) => {
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
    const requested = String(viewId || '').trim();
    const mappedTab = EDMS_VIEW_TO_TAB[requested];
    if (mappedTab) {
        PENDING_EDMS_TAB = mappedTab;
        return 'view-edms';
    }
    return requested;
}

function isEdmsTabVisible(tabName) {
    return EDMS_TAB_VISIBILITY[String(tabName || '').trim().toLowerCase()] !== false;
}

function getFirstVisibleEdmsTab() {
    const order = ['archive', 'transmittal', 'correspondence', 'reports'];
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
    try {
        const normalized = String(tabName || '').trim().toLowerCase();
        if (!EDMS_TAB_TO_VIEW[normalized]) return;
        localStorage.setItem(getEdmsLastTabStorageKey(), normalized);
    } catch (error) {
        console.warn('Failed to persist EDMS last tab.', error);
    }
}

function loadEdmsLastTab() {
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
    const preferred = String(EDMS_DEFAULT_TAB || '').trim().toLowerCase();
    if (preferred && isEdmsTabVisible(preferred)) {
        return preferred;
    }
    return getFirstVisibleEdmsTab();
}

function applyEdmsTabVisibility() {
    const navEdms = document.getElementById('nav-edms');
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

async function loadEdmsHeaderStats(force = false) {
    if (!document.getElementById('edms-stat-total')) return;

    const now = Date.now();
    const cacheMs = 15000;
    if (!force && EDMS_STATS_LOADING) return;
    if (!force && EDMS_STATS_LAST_LOADED_AT && (now - EDMS_STATS_LAST_LOADED_AT) < cacheMs) return;

    EDMS_STATS_LOADING = true;
    try {
        const res = (typeof fetchWithAuth === 'function')
            ? await fetchWithAuth(`${API_BASE}/dashboard/stats`)
            : await fetch(`${API_BASE}/dashboard/stats`);
        if (!res || !res.ok) return;
        const data = await res.json();
        setEdmsHeaderStats(data || {});
        EDMS_STATS_LAST_LOADED_AT = Date.now();
    } catch (error) {
        console.warn('Failed to load EDMS header stats.', error);
    } finally {
        EDMS_STATS_LOADING = false;
    }
}

window.loadEdmsHeaderStats = loadEdmsHeaderStats;

async function loadEdmsNavigation() {
    const role = String(window.authManager?.user?.role || '').toLowerCase();
    let fallback = {
        archive: true,
        transmittal: true,
        correspondence: true,
        reports: true,
    };

    if (role === 'viewer') {
        fallback = {
            archive: true,
            transmittal: true,
            correspondence: true,
            reports: true,
        };
    }

    EDMS_DEFAULT_TAB = role === 'dcc' || role === 'manager' ? 'transmittal' : (role === 'viewer' ? 'reports' : 'archive');
    EDMS_TAB_VISIBILITY = { ...EDMS_TAB_VISIBILITY, ...fallback };

    try {
        const res = (typeof fetchWithAuth === 'function')
            ? await fetchWithAuth(`${API_BASE}/auth/navigation`)
            : await fetch(`${API_BASE}/auth/navigation`);
        if (res && res.ok) {
            const body = await res.json();
            const tabs = body?.edms_tabs || {};
            EDMS_TAB_VISIBILITY = {
                ...EDMS_TAB_VISIBILITY,
                archive: tabs.archive !== false,
                transmittal: tabs.transmittal !== false,
                correspondence: tabs.correspondence !== false,
                reports: tabs.reports !== false,
            };
            const apiDefaultTab = String(body?.default_edms_tab || '').trim().toLowerCase();
            if (apiDefaultTab && EDMS_TAB_TO_VIEW[apiDefaultTab]) {
                EDMS_DEFAULT_TAB = apiDefaultTab;
            }
        }
    } catch (error) {
        console.warn('Failed to load EDMS navigation permissions, using fallback.', error);
    }

    applyEdmsTabVisibility();
}

function openEdmsTab(tabName, btnEl = null) {
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

    document.querySelectorAll('.edms-tab-btn').forEach((button) => {
        button.classList.remove('active');
    });

    const button = btnEl || document.querySelector(`.edms-tab-btn[data-edms-tab="${normalized}"]`);
    if (button) button.classList.add('active');

    PENDING_EDMS_TAB = normalized;

    switch (normalized) {
        case 'archive':
            if (typeof archiveLoadFiles === 'function') archiveLoadFiles();
            break;
        case 'transmittal':
            if (typeof showListMode === 'function') showListMode();
            if (typeof loadTransmittals === 'function') {
                loadTransmittals();
            } else if (typeof toggleTransmittalMode === 'function') {
                toggleTransmittalMode('list');
            }
            break;
        case 'correspondence':
            if (typeof initCorrespondenceView === 'function') initCorrespondenceView();
            break;
        case 'reports':
            if (typeof initReportsView === 'function') initReportsView();
            break;
        default:
            break;
    }
    saveEdmsLastTab(normalized);
}

window.openEdmsTab = openEdmsTab;

// ============================================================
//  1. NAVIGATION LOGIC (Ù…Ø¯ÛŒØ±ÛŒØª Ø¬Ø§Ø¨Ø¬Ø§ÛŒÛŒ ØµÙØ­Ø§Øª)
// ============================================================

function navigateTo(viewId) {
    const routedViewId = mapToRoutedView(viewId);
    console.log("Navigating to:", routedViewId);

    if (routedViewId !== 'view-login' && !window.requireAuth()) {
        return;
    }

    if (routedViewId === 'view-users' || routedViewId === 'view-bulk') {
        if (!window.requireAdmin()) return;
        PENDING_SETTINGS_TAB = routedViewId === 'view-users' ? 'users' : 'bulk';
        navigateTo('view-settings');
        return;
    }
    
    if (ADMIN_ONLY_VIEWS.has(routedViewId) && !window.requireAdmin()) {
        return;
    }
    
    document.querySelectorAll('.view-section').forEach(el => {
        el.style.display = 'none';
        el.classList.remove('active');
    });

    const target = document.getElementById(routedViewId);
    if (!target) return;

    target.style.display = 'block';
    target.classList.add('active');
    
    switch(routedViewId) {
        case 'view-dashboard':
            if (typeof initDashboard === 'function') initDashboard();
            break;

        case 'view-edms': {
            const lastSavedTab = loadEdmsLastTab();
            const requestedTab = PENDING_EDMS_TAB || lastSavedTab || getEffectiveDefaultEdmsTab() || 'archive';
            const safeTab = isEdmsTabVisible(requestedTab) ? requestedTab : getFirstVisibleEdmsTab();
            if (safeTab) {
                openEdmsTab(safeTab);
                loadEdmsHeaderStats();
            } else {
                showToast('هیچ تب فعالی برای EDMS در دسترس نیست.', 'error');
                navigateTo('view-dashboard');
                return;
            }
            break;
        }

        case 'view-contractor':
            if (typeof initContractorView === 'function') initContractorView();
            break;

        case 'view-consultant':
            if (typeof initConsultantView === 'function') initConsultantView();
            break;
            
        case 'view-settings':
            if (typeof openSettingsTab === 'function') {
                const targetTab = PENDING_SETTINGS_TAB || 'general';
                PENDING_SETTINGS_TAB = null;
                openSettingsTab(targetTab);
            }
            break;

        case 'view-profile':
            if (typeof initUserSettingsView === 'function') initUserSettingsView();
            break;
    }
    
    updateSidebarState(routedViewId);
}

function updateSidebarState(activeViewId) {
    // Ø­Ø°Ù Ú©Ù„Ø§Ø³ active Ø§Ø² Ù‡Ù…Ù‡ Ø¢ÛŒØªÙ…â€ŒÙ‡Ø§
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    let navTargetView = activeViewId;
    if (activeViewId === 'view-users' || activeViewId === 'view-bulk') {
        navTargetView = 'view-settings';
    } else if (activeViewId === 'view-archive' || activeViewId === 'view-transmittal' || activeViewId === 'view-correspondence' || activeViewId === 'view-reports') {
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
    const dropdown = document.getElementById('user-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

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
    try {
        const url = `${API_BASE}/lookup/dictionary`;
        const res = (typeof fetchWithAuth === 'function')
            ? await fetchWithAuth(url)
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

