(() => {
    if (typeof window.registerViewBoot !== 'function') return;
    window.registerViewBoot('view-settings', {
        init() {
            if (typeof window.openSettingsTab !== 'function') return;
            const pending = typeof window.consumePendingSettingsTab === 'function'
                ? window.consumePendingSettingsTab()
                : null;
            window.openSettingsTab(pending || 'general');
        },
    });
})();
