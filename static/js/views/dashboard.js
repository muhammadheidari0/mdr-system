(() => {
    function initDashboardView() {
        if (typeof window.initDashboard === 'function') {
            window.initDashboard();
        }
    }

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (String(viewId || '').trim() === 'view-dashboard') {
                initDashboardView();
            }
        });
    }

    if (document.getElementById('view-dashboard')?.classList.contains('active')) {
        initDashboardView();
    }
})();
