(() => {
    if (typeof window.registerViewBoot !== 'function') return;
    window.registerViewBoot('view-dashboard', {
        init() {
            if (typeof window.initDashboard === 'function') {
                window.initDashboard();
            }
        },
    });
})();
