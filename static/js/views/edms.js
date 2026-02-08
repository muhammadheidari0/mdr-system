(() => {
    if (typeof window.registerViewBoot !== 'function') return;

    window.registerViewBoot('view-edms', {
        init() {
            const pending = typeof window.consumePendingEdmsTab === 'function'
                ? window.consumePendingEdmsTab()
                : null;
            const lastSaved = typeof window.loadEdmsLastTab === 'function'
                ? window.loadEdmsLastTab()
                : null;
            const fallback = typeof window.getEffectiveDefaultEdmsTab === 'function'
                ? window.getEffectiveDefaultEdmsTab()
                : 'archive';
            const requestedTab = pending || lastSaved || fallback || 'archive';

            const safeTab = (typeof window.isEdmsTabVisible === 'function' && window.isEdmsTabVisible(requestedTab))
                ? requestedTab
                : (typeof window.getFirstVisibleEdmsTab === 'function' ? window.getFirstVisibleEdmsTab() : null);

            if (safeTab) {
                if (typeof window.openEdmsTab === 'function') window.openEdmsTab(safeTab);
                if (typeof window.loadEdmsHeaderStats === 'function') window.loadEdmsHeaderStats();
                return;
            }

            if (typeof window.showToast === 'function') {
                window.showToast('هیچ تب فعالی برای EDMS در دسترس نیست.', 'error');
            }
            if (typeof window.navigateTo === 'function') {
                window.navigateTo('view-dashboard');
            }
        },
    });
})();
