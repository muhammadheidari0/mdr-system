// @ts-nocheck
function openSettingsTab(tabName) {
    bindSettingsTabClicks();
    const btn = document.querySelector(`#view-settings [data-settings-tab][data-tab="${tabName}"]`);
    switchSettingsTab(tabName, btn);
}

function switchSettingsTab(tabName, btnEl) {
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

    const button = btnEl || document.querySelector(`#view-settings [data-settings-tab][data-tab="${tabName}"]`);
    if (button) {
        button.classList.add('active');
        button.setAttribute('aria-selected', 'true');
    }

    const target = document.getElementById(`tab-${tabName}`);
    if (target) {
        target.classList.add('active');
        target.setAttribute('aria-hidden', 'false');
    }

    if (tabName === 'general' && typeof window.initGeneralSettings === 'function') {
        window.initGeneralSettings();
    } else if (tabName === 'users') {
        if (typeof window.initSettingsUsers === 'function') {
            window.initSettingsUsers();
        } else if (typeof window.loadUsers === 'function') {
            window.loadUsers();
        }
    } else if (tabName === 'organizations' && typeof window.initOrganizationsSettings === 'function') {
        window.initOrganizationsSettings();
    } else if (tabName === 'permissions' && typeof window.initPermissionsSettings === 'function') {
        window.initPermissionsSettings();
    } else if (tabName === 'reports' && typeof window.initSettingsReports === 'function') {
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
