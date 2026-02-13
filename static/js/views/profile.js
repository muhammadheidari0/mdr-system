(() => {
    function initProfile() {
        if (typeof window.initUserSettingsView === 'function') {
            window.initUserSettingsView();
        }
    }

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (String(viewId || '').trim() === 'view-profile') {
                initProfile();
            }
        });
    }

    if (document.getElementById('view-profile')?.classList.contains('active')) {
        initProfile();
    }
})();
