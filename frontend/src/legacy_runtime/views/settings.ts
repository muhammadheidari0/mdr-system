// @ts-nocheck
(() => {
    function initSettings() {
        if (typeof window.openSettingsTab !== 'function') return;
        const pending = typeof window.consumePendingSettingsTab === 'function'
            ? window.consumePendingSettingsTab()
            : null;
        window.openSettingsTab(pending || 'general');
    }

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (String(viewId || '').trim() === 'view-settings') {
                initSettings();
            }
        });
    }

    if (document.getElementById('view-settings')?.classList.contains('active')) {
        initSettings();
    }
})();
