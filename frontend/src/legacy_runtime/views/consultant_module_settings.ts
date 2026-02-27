// @ts-nocheck
(() => {
    function normalizeTabKey(value) {
        return String(value || '').trim().toLowerCase();
    }

    function switchConsultantOpenProjectTab(requestedTab = 'project-import') {
        const root = document.getElementById('consultantOpenProjectOpsRoot');
        if (!root) return;
        const buttons = Array.from(root.querySelectorAll('.storage-openproject-subtab[data-op-tab]'));
        const panels = Array.from(root.querySelectorAll('[data-op-tab-content]'));
        if (!buttons.length || !panels.length) return;

        const available = buttons
            .map((btn) => normalizeTabKey(btn?.dataset?.opTab))
            .filter(Boolean);
        const activeTab = available.includes(normalizeTabKey(requestedTab))
            ? normalizeTabKey(requestedTab)
            : available[0];

        buttons.forEach((btn) => {
            const key = normalizeTabKey(btn?.dataset?.opTab);
            const isActive = key === activeTab;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        panels.forEach((panel) => {
            const key = normalizeTabKey(panel?.dataset?.opTabContent);
            const isActive = key === activeTab;
            panel.classList.toggle('active', isActive);
            panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        });
    }

    function bindConsultantOpenProjectTabs() {
        const root = document.getElementById('consultantOpenProjectOpsRoot');
        if (!root || root.dataset.opTabsBound === '1') return;
        root.addEventListener('click', (event) => {
            const button = event?.target?.closest?.('.storage-openproject-subtab[data-op-tab]');
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            switchConsultantOpenProjectTab(button.dataset.opTab || 'project-import');
        });
        root.dataset.opTabsBound = '1';
        switchConsultantOpenProjectTab('project-import');
    }

    function initConsultantModuleSettingsView() {
        bindConsultantOpenProjectTabs();
        if (typeof window.initSettingsIntegrations !== 'function') return;
        const result = window.initSettingsIntegrations();
        if (result && typeof result.then === 'function') {
            result.catch(() => {});
        }
    }

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (String(viewId || '').trim() === 'view-consultant-settings') {
                initConsultantModuleSettingsView();
            }
        });
    }

    if (document.getElementById('view-consultant-settings')?.classList.contains('active')) {
        initConsultantModuleSettingsView();
    }
})();
