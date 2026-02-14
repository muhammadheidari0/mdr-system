// @ts-nocheck
(() => {
    if (window.AppEvents) return;

    const topics = new Map();

    function on(eventName, handler) {
        const key = String(eventName || '').trim();
        if (!key || typeof handler !== 'function') return () => {};
        if (!topics.has(key)) topics.set(key, new Set());
        topics.get(key).add(handler);
        return () => off(key, handler);
    }

    function once(eventName, handler) {
        if (typeof handler !== 'function') return () => {};
        let unsub = () => {};
        const wrapped = (...args) => {
            unsub();
            handler(...args);
        };
        unsub = on(eventName, wrapped);
        return unsub;
    }

    function off(eventName, handler) {
        const key = String(eventName || '').trim();
        if (!topics.has(key)) return;
        if (!handler) {
            topics.delete(key);
            return;
        }
        topics.get(key).delete(handler);
    }

    function emit(eventName, payload) {
        const key = String(eventName || '').trim();
        if (!topics.has(key)) return;
        for (const handler of topics.get(key)) {
            try {
                handler(payload);
            } catch (error) {
                console.error(`AppEvents handler failed for "${key}"`, error);
            }
        }
    }

    window.AppEvents = { on, once, off, emit };
})();
