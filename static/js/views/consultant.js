(() => {
    if (typeof window.registerViewBoot !== 'function') return;
    window.registerViewBoot('view-consultant', {
        init() {
            if (typeof window.initConsultantView === 'function') {
                window.initConsultantView();
            }
        },
    });
})();
