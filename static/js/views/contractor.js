(() => {
    if (typeof window.registerViewBoot !== 'function') return;
    window.registerViewBoot('view-contractor', {
        init() {
            if (typeof window.initContractorView === 'function') {
                window.initContractorView();
            }
        },
    });
})();
