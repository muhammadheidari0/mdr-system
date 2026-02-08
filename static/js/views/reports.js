(() => {
    if (typeof window.registerViewBoot !== 'function') return;
    window.registerViewBoot('view-reports', {
        init() {
            if (typeof window.initReportsView === 'function') {
                window.initReportsView();
            }
        },
    });
})();
