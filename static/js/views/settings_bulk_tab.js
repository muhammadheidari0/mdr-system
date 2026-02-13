(function () {
    if (window.__bulkFrameResizeBound) return;
    window.__bulkFrameResizeBound = true;

    const frame = document.getElementById('bulkRegisterFrame');
    if (!frame) return;

    window.addEventListener('message', (event) => {
      const data = event.data || {};
      if (data.type !== 'mdr-bulk-height') return;

      const h = Number(data.height || 0);
      if (!Number.isFinite(h) || h <= 0) return;

      const minHeight = 460;
      const maxHeight = 1400;
      const nextHeight = Math.max(minHeight, Math.min(maxHeight, h + 10));
      frame.style.height = `${nextHeight}px`;
    });
  })();
