(() => {
    if (typeof window.registerViewBoot !== 'function') return;
    window.registerViewBoot('view-profile', {
        init() {
            if (typeof window.initUserSettingsView === 'function') {
                window.initUserSettingsView();
            }
        },
    });
})();
