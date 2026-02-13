(() => {
    function initReports() {
        if (typeof window.initReportsView === 'function') {
            window.initReportsView();
        }
    }

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (String(viewId || '').trim() === 'view-reports') {
                initReports();
            }
        });
    }

    if (document.getElementById('view-reports')?.classList.contains('active')) {
        initReports();
    }
})();
