(() => {
    function bindConsultantTabClicks() {
        const root = document.getElementById('view-consultant');
        if (!root || root.dataset.consultantTabsBound === '1') return;

        root.addEventListener('click', (event) => {
            const button = event.target.closest('.consultant-tab-btn[data-consultant-tab]');
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            const tab = String(button.getAttribute('data-consultant-tab') || '').trim();
            if (!tab) return;
            if (typeof window.openConsultantTab === 'function') {
                window.openConsultantTab(tab, button);
            }
        });

        root.dataset.consultantTabsBound = '1';
    }

    function initConsultant() {
        bindConsultantTabClicks();
        if (typeof window.initConsultantView === 'function') {
            window.initConsultantView();
        }
    }

    bindConsultantTabClicks();

    if (window.AppEvents?.on) {
        window.AppEvents.on('view:activated', ({ viewId }) => {
            if (String(viewId || '').trim() === 'view-consultant') {
                initConsultant();
            }
        });
    }

    if (document.getElementById('view-consultant')?.classList.contains('active')) {
        initConsultant();
    }
})();
