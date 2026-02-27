// @ts-nocheck
(() => {
    const STATE = {
        bound: false,
        activeTab: 'general',
        pendingRequest: 'general',
    };

    function norm(value) {
        return String(value ?? '').trim().toLowerCase();
    }

    function resolveRequest(requested) {
        const key = norm(requested);
        if (key === 'bulk') {
            return { raw: 'bulk', tab: 'bulk', panel: 'bulk', domain: 'mdr', page: 'mdr' };
        }
        return { raw: 'general', tab: 'general', panel: 'general', domain: 'mdr', page: 'mdr' };
    }

    function applyTabUi(root, tab, panelKey) {
        root.querySelectorAll('[data-module-settings-tab]').forEach((button) => {
            const isActive = norm(button?.dataset?.moduleSettingsTab) === tab;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        root.querySelectorAll('.module-settings-tab-content').forEach((panelEl) => {
            const panelId = norm(panelEl?.id);
            const expectedId = panelKey === 'bulk' ? 'tab-bulk' : 'tab-general';
            const isActive = panelId === expectedId;
            panelEl.classList.toggle('active', isActive);
            panelEl.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        });
    }

    async function ensureGeneralReady(domain, page) {
        if (typeof window.initGeneralSettings === 'function') {
            await window.initGeneralSettings();
        }
        if (typeof window.switchGeneralSettingsDomain === 'function') {
            await window.switchGeneralSettingsDomain(domain || 'mdr');
        }
        if (typeof window.switchGeneralSettingsPage === 'function') {
            await window.switchGeneralSettingsPage(page || 'mdr');
        }
    }

    async function ensureBulkReady() {
        if (typeof window.initSettingsBulk === 'function') {
            await window.initSettingsBulk();
        }
    }

    async function openTab(requested) {
        const root = document.getElementById('view-edms-settings');
        const request = resolveRequest(requested);
        STATE.pendingRequest = request.raw;
        if (!root) return;

        applyTabUi(root, request.tab, request.panel);
        if (request.panel === 'bulk') {
            await ensureBulkReady();
        } else {
            await ensureGeneralReady(request.domain, request.page);
        }
        STATE.activeTab = request.tab;
    }

    function bindActions() {
        const root = document.getElementById('view-edms-settings');
        if (!root || STATE.bound) return;
        root.addEventListener('click', (event) => {
            const button = event?.target?.closest?.('[data-module-settings-tab]');
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            void openTab(button.dataset.moduleSettingsTab || 'general');
        });
        STATE.bound = true;
    }

    window.openEdmsModuleSettingsTab = function openEdmsModuleSettingsTab(requested = 'general') {
        STATE.pendingRequest = norm(requested) || 'general';
        return openTab(requested);
    };

    window.initEdmsModuleSettingsView = function initEdmsModuleSettingsView() {
        bindActions();
        return openTab(STATE.pendingRequest || STATE.activeTab || 'general');
    };

    // Backward compatibility with older callers
    window.openModuleSettingsTab = window.openEdmsModuleSettingsTab;
    window.initModuleSettingsView = window.initEdmsModuleSettingsView;

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (norm(viewId) === 'view-edms-settings') {
                void window.initEdmsModuleSettingsView();
            }
        });
    }

    if (document.getElementById('view-edms-settings')?.classList.contains('active')) {
        void window.initEdmsModuleSettingsView();
    }
})();
