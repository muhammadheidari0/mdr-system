(() => {
    function bindContractorTabClicks() {
        const root = document.getElementById('view-contractor');
        if (!root || root.dataset.contractorTabsBound === '1') return;

        root.addEventListener('click', (event) => {
            const button = event.target.closest('.contractor-tab-btn[data-contractor-tab]');
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            const tab = String(button.getAttribute('data-contractor-tab') || '').trim();
            if (!tab) return;
            if (typeof window.openContractorTab === 'function') {
                window.openContractorTab(tab, button);
            }
        });

        root.dataset.contractorTabsBound = '1';
    }

    function initContractor() {
        bindContractorTabClicks();
        if (typeof window.initContractorView === 'function') {
            window.initContractorView();
        }
    }

    bindContractorTabClicks();

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (String(viewId || '').trim() === 'view-contractor') {
                initContractor();
            }
        });
    }

    if (document.getElementById('view-contractor')?.classList.contains('active')) {
        initContractor();
    }
})();
