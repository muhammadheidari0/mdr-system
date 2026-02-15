// @ts-nocheck
(function () {
    if (window.__bulkFrameResizeBound) return;
    window.__bulkFrameResizeBound = true;

    const frame = document.getElementById('bulkRegisterFrame');
    if (!frame) return;
    const MIN_HEIGHT = 460;

    function applyFrameHeight(rawHeight) {
      const h = Number(rawHeight || 0);
      if (!Number.isFinite(h) || h <= 0) return;
      const nextHeight = Math.max(MIN_HEIGHT, Math.ceil(h + 12));
      frame.style.height = `${nextHeight}px`;
    }

    function resizeFromIframeDoc() {
      try {
        const win = frame.contentWindow;
        const doc = win?.document;
        if (!doc) return;
        const body = doc.body;
        const root = doc.documentElement;
        const contentHeight = Math.max(
          body ? body.scrollHeight : 0,
          body ? body.offsetHeight : 0,
          root ? root.scrollHeight : 0,
          root ? root.offsetHeight : 0
        );
        applyFrameHeight(contentHeight);
      } catch (_) {
        // Ignore same-origin access failures and rely on postMessage fallback.
      }
    }

    try {
      const current = frame.getAttribute('src') || '/api/v1/mdr/bulk-register-page';
      const url = new URL(current, window.location.origin);
      url.searchParams.set('_cb', String(Date.now()));
      frame.setAttribute('src', `${url.pathname}${url.search}${url.hash}`);
    } catch (_) {
      // Keep existing src when URL parsing fails.
    }

    frame.addEventListener('load', () => {
      resizeFromIframeDoc();
      setTimeout(resizeFromIframeDoc, 80);
      setTimeout(resizeFromIframeDoc, 250);
      setTimeout(resizeFromIframeDoc, 800);
    });

    window.addEventListener('resize', () => {
      requestAnimationFrame(resizeFromIframeDoc);
    });

    window.addEventListener('message', (event) => {
      const data = event.data || {};
      if (data.type !== 'mdr-bulk-height') return;
      applyFrameHeight(data.height);
    });
  })();
