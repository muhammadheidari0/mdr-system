// @ts-nocheck
function shouldRedirectToModuleSettings(tabName) {
    const key = String(tabName || '').trim().toLowerCase();
    return key === 'general' || key === 'bulk';
}

function redirectToModuleSettings(tabName) {
    if (typeof window.openEdmsModuleSettingsTab === 'function') {
        window.openEdmsModuleSettingsTab(tabName || 'general');
    } else if (typeof window.openModuleSettingsTab === 'function') {
        window.openModuleSettingsTab(tabName || 'general');
    }
    if (typeof window.navigateTo === 'function') {
        window.navigateTo('view-edms-settings');
    }
}

function openSettingsTab(tabName) {
    bindSettingsTabClicks();
    const requestedTab = String(tabName || '').trim().toLowerCase();
    const btn = document.querySelector(`#view-settings [data-settings-tab][data-tab="${requestedTab}"]`);
    if (!btn && shouldRedirectToModuleSettings(requestedTab)) {
        redirectToModuleSettings(requestedTab);
        return;
    }
    switchSettingsTab(requestedTab, btn);
}

function switchSettingsTab(tabName, btnEl) {
    const root = document.getElementById('view-settings');
    if (!root) return;

    let requestedTab = String(tabName || '').trim().toLowerCase();
    const tabButtons = root.querySelectorAll('[data-settings-tab]');
    const tabPanels = root.querySelectorAll('.settings-tab-content');
    let button = btnEl || root.querySelector(`[data-settings-tab][data-tab="${requestedTab}"]`);

    if (!button && shouldRedirectToModuleSettings(requestedTab)) {
        redirectToModuleSettings(requestedTab);
        return;
    }

    if (!button) {
        button = tabButtons[0];
        requestedTab = String(button?.getAttribute?.('data-tab') || '').trim().toLowerCase();
    }

    const panelTab = requestedTab;

    tabButtons.forEach((button) => {
        button.classList.remove('active');
        button.setAttribute('aria-selected', 'false');
    });

    tabPanels.forEach((panel) => {
        panel.classList.remove('active');
        panel.setAttribute('aria-hidden', 'true');
    });

    if (button) {
        button.classList.add('active');
        button.setAttribute('aria-selected', 'true');
    }

    const target = root.querySelector(`#tab-${panelTab}`);
    if (target) {
        target.classList.add('active');
        target.setAttribute('aria-hidden', 'false');
    }

    if (panelTab === 'general' && typeof window.initGeneralSettings === 'function') {
        const applyGeneralTargetPage = () => {
            if (requestedTab === 'general' && typeof window.switchGeneralSettingsPage === 'function') {
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
    } else if (panelTab === 'bulk' && typeof window.initSettingsBulk === 'function') {
        const initResult = window.initSettingsBulk();
        if (initResult && typeof initResult.then === 'function') {
            initResult.catch(() => {});
        }
    } else if (panelTab === 'storage' && typeof window.initStorageSettingsPanel === 'function') {
        const initResult = window.initStorageSettingsPanel();
        if (initResult && typeof initResult.then === 'function') {
            initResult.catch(() => {});
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
