(() => {
    if (!window.ViewBoot) window.ViewBoot = {};

    window.registerViewBoot = function registerViewBoot(viewId, hooks) {
        const key = String(viewId || '').trim();
        if (!key || !hooks || typeof hooks !== 'object') return;
        const prev = window.ViewBoot[key] || {};
        window.ViewBoot[key] = {
            ...prev,
            ...hooks,
        };
    };
})();
