// @ts-nocheck
function openSettingsTab(tabName) {
    bindSettingsTabClicks();
    const btn = document.querySelector(`#view-settings [data-settings-tab][data-tab="${tabName}"]`);
    switchSettingsTab(tabName, btn);
}

function switchSettingsTab(tabName, btnEl) {
    const requestedTab = String(tabName || '').trim().toLowerCase();
    const panelTab = requestedTab === 'storage' ? 'general' : requestedTab;
    const tabButtons = document.querySelectorAll('#view-settings [data-settings-tab]');
    const tabPanels = document.querySelectorAll('#view-settings .settings-tab-content');

    tabButtons.forEach((button) => {
        button.classList.remove('active');
        button.setAttribute('aria-selected', 'false');
    });

    tabPanels.forEach((panel) => {
        panel.classList.remove('active');
        panel.setAttribute('aria-hidden', 'true');
    });

    const button = btnEl || document.querySelector(`#view-settings [data-settings-tab][data-tab="${requestedTab}"]`);
    if (button) {
        button.classList.add('active');
        button.setAttribute('aria-selected', 'true');
    }

    const target = document.getElementById(`tab-${panelTab}`);
    if (target) {
        target.classList.add('active');
        target.setAttribute('aria-hidden', 'false');
    }

    if (panelTab === 'general' && typeof window.initGeneralSettings === 'function') {
        const applyGeneralTargetPage = () => {
            if (requestedTab === 'storage' && typeof window.switchGeneralSettingsPage === 'function') {
                window.switchGeneralSettingsPage('storage');
            } else if (requestedTab === 'general' && typeof window.switchGeneralSettingsPage === 'function') {
                window.switchGeneralSettingsPage('db_sync');
            }
        };
        const afterInit = () => {
            if (typeof window.switchGeneralSettingsDomain !== 'function') {
                applyGeneralTargetPage();
                return;
            }
            const domainResult = window.switchGeneralSettingsDomain('common');
            if (domainResult && typeof domainResult.then === 'function') {
                domainResult.then(applyGeneralTargetPage).catch(() => {
                    applyGeneralTargetPage();
                });
            } else {
                applyGeneralTargetPage();
            }
        };
        const initResult = window.initGeneralSettings();
        if (initResult && typeof initResult.then === 'function') {
            initResult.then(afterInit).catch(() => {});
        } else {
            afterInit();
        }
    } else if (panelTab === 'users') {
        if (typeof window.initSettingsUsers === 'function') {
            window.initSettingsUsers();
        } else if (typeof window.loadUsers === 'function') {
            window.loadUsers();
        }
    } else if (panelTab === 'integrations' && typeof window.initSettingsIntegrations === 'function') {
        const initResult = window.initSettingsIntegrations();
        if (initResult && typeof initResult.then === 'function') {
            initResult.catch(() => {});
        }
    } else if (panelTab === 'organizations' && typeof window.initOrganizationsSettings === 'function') {
        window.initOrganizationsSettings();
    } else if (panelTab === 'permissions' && typeof window.initPermissionsSettings === 'function') {
        window.initPermissionsSettings();
    } else if (panelTab === 'reports' && typeof window.initSettingsReports === 'function') {
        window.initSettingsReports();
    }
}

function bindSettingsTabClicks() {
    const root = document.getElementById('view-settings');
    if (!root || root.dataset.settingsTabsBound === '1') return;
    root.addEventListener('click', (event) => {
        const btn = event.target.closest('[data-settings-tab][data-tab]');
        if (!btn || !root.contains(btn)) return;
        event.preventDefault();
        switchSettingsTab(btn.getAttribute('data-tab'), btn);
    });
    root.dataset.settingsTabsBound = '1';
}

bindSettingsTabClicks();
window.openSettingsTab = openSettingsTab;
window.switchSettingsTab = switchSettingsTab;
window.initSettingsShell = bindSettingsTabClicks;
