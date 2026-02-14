// @ts-nocheck
(() => {
    function bindEdmsUiEvents() {
        const root = document.getElementById('view-edms');
        if (!root || root.dataset.edmsUiBound === '1') return;

        root.addEventListener('click', (event) => {
            const refreshBtn = event.target.closest('[data-edms-action="refresh-stats"]');
            if (refreshBtn && root.contains(refreshBtn)) {
                event.preventDefault();
                if (typeof window.loadEdmsHeaderStats === 'function') {
                    window.loadEdmsHeaderStats(true);
                }
                return;
            }

            const tabBtn = event.target.closest('[data-edms-tab]');
            if (!tabBtn || !root.contains(tabBtn)) return;
            event.preventDefault();
            const tab = String(tabBtn.getAttribute('data-edms-tab') || '').trim();
            if (!tab) return;
            if (typeof window.openEdmsTab === 'function') {
                window.openEdmsTab(tab, tabBtn);
            }
        });

        root.dataset.edmsUiBound = '1';
    }

    bindEdmsUiEvents();

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (String(viewId || '').trim() === 'view-edms') {
                bindEdmsUiEvents();
            }
        });
    }
})();
