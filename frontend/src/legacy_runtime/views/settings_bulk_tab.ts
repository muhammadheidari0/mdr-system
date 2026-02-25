// @ts-nocheck
(function () {
    const INBOX_API_BASE = '/api/v1/bim/edms/inbox';
    const FRAME_MIN_HEIGHT = 460;
    const STATE = {
        initialized: false,
        activeTab: 'excel',
        loadingRuns: false,
        loadingItems: false,
        runs: [],
        selectedRunId: '',
        selectedRun: null,
        runItems: [],
        frameResizeBound: false,
    };

    function norm(value) {
        return String(value ?? '').trim();
    }

    function esc(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function apiFetchFn() {
        return typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : fetch;
    }

    async function request(url, options = {}) {
        const fetchFn = apiFetchFn();
        const headers = new Headers(options.headers || {});
        if (!headers.has('accept')) {
            headers.set('accept', 'application/json');
        }
        const hasBody = options.body !== undefined && options.body !== null;
        if (hasBody && !headers.has('content-type') && !(options.body instanceof FormData)) {
            headers.set('content-type', 'application/json');
        }
        const response = await fetchFn(url, { ...options, headers });
        if (!response.ok) {
            let message = `Request failed (${response.status})`;
            try {
                const body = await response.clone().json();
                const detail = body?.detail;
                if (typeof detail === 'string' && detail) {
                    message = detail;
                } else if (detail && typeof detail === 'object') {
                    const code = norm(detail.error_code || detail.code);
                    const text = norm(detail.message || detail.detail || '');
                    message = code && text ? `${code}: ${text}` : text || code || message;
                } else if (body?.message) {
                    message = String(body.message);
                }
            } catch (_) {
                try {
                    const text = await response.text();
                    if (norm(text)) message = text;
                } catch (_) {
                    // keep fallback
                }
            }
            throw new Error(message);
        }
        try {
            return await response.json();
        } catch (_) {
            return {};
        }
    }

    function toIsoUtcFromInput(id) {
        const input = document.getElementById(id);
        const raw = norm(input?.value);
        if (!raw) return '';
        const dt = new Date(raw);
        if (Number.isNaN(dt.getTime())) return '';
        return dt.toISOString();
    }

    function setInboxResult(message = '', level = 'info') {
        const box = document.getElementById('bimInboxResult');
        if (!box) return;
        if (!message) {
            box.style.display = 'none';
            box.textContent = '';
            box.classList.remove('storage-sync-result-success', 'storage-sync-result-error', 'storage-sync-result-info');
            return;
        }
        box.style.display = 'block';
        box.textContent = message;
        box.classList.remove('storage-sync-result-success', 'storage-sync-result-error', 'storage-sync-result-info');
        if (level === 'success') box.classList.add('storage-sync-result-success');
        else if (level === 'error') box.classList.add('storage-sync-result-error');
        else box.classList.add('storage-sync-result-info');
    }

    function statusBadge(status) {
        const key = norm(status).toLowerCase();
        if (!key) return '<span class="storage-badge is-disabled">-</span>';
        if (key === 'approved') return `<span class="storage-badge is-valid">${esc(key)}</span>`;
        if (key === 'staged' || key === 'staged_with_errors') return `<span class="storage-badge is-pending">${esc(key)}</span>`;
        if (key === 'rejected') return `<span class="storage-badge is-rejected">${esc(key)}</span>`;
        if (key === 'expired') return `<span class="storage-badge is-disabled">${esc(key)}</span>`;
        return `<span class="storage-badge is-legacy">${esc(key)}</span>`;
    }

    function formatUtc(value) {
        const raw = norm(value);
        if (!raw) return '-';
        const dt = new Date(raw);
        if (Number.isNaN(dt.getTime())) return raw;
        return dt.toISOString().replace('T', ' ').replace('Z', ' UTC');
    }

    function runSummary(run) {
        const summary = run?.validation_summary || {};
        const requested = Number(summary?.requested_count || 0);
        const valid = Number(summary?.valid_count || 0);
        const invalid = Number(summary?.invalid_count || 0);
        const duplicate = Number(summary?.duplicate_count || 0);
        return {
            requested,
            valid,
            invalid,
            duplicate,
        };
    }

    function setApproveButtonsState() {
        const approveBtn = document.querySelector('[data-bulk-action="approve-bim-run"]');
        const rejectBtn = document.querySelector('[data-bulk-action="reject-bim-run"]');
        const run = STATE.selectedRun;
        const isBusy = Boolean(STATE.loadingItems || STATE.loadingRuns);
        const approvable = Boolean(run?.approvable);
        const status = norm(run?.status).toLowerCase();
        const actionLocked = !run || isBusy || status === 'approved' || status === 'rejected' || status === 'expired';
        if (approveBtn) approveBtn.disabled = actionLocked || !approvable;
        if (rejectBtn) rejectBtn.disabled = actionLocked;
    }

    function renderRuns() {
        const body = document.getElementById('bimInboxRunsBody');
        if (!body) return;

        if (STATE.loadingRuns) {
            body.innerHTML = '<tr><td colspan="8" class="text-center muted">در حال بارگذاری ...</td></tr>';
            return;
        }

        if (!Array.isArray(STATE.runs) || !STATE.runs.length) {
            body.innerHTML = '<tr><td colspan="8" class="text-center muted">Run ای یافت نشد.</td></tr>';
            return;
        }

        body.innerHTML = STATE.runs.map((run) => {
            const runId = norm(run?.run_id);
            const selected = runId && runId === STATE.selectedRunId;
            const summary = runSummary(run);
            const validInvalid = `${summary.valid} / ${summary.invalid}`;
            const sender = norm(run?.sender_name) || norm(run?.sender_email) || '-';
            return `
                <tr class="${selected ? 'bulk-bim-row-selected' : ''}">
                  <td><code>${esc(runId || '-')}</code></td>
                  <td>${esc(run?.project_code || '-')}</td>
                  <td>${esc(sender)}</td>
                  <td>${summary.requested}</td>
                  <td>${esc(validInvalid)}</td>
                  <td>${statusBadge(run?.status)}</td>
                  <td>${esc(formatUtc(run?.started_at))}</td>
                  <td>
                    <button
                      class="btn-archive-icon"
                      type="button"
                      data-bulk-action="select-bim-run"
                      data-run-id="${esc(runId)}"
                    >View</button>
                  </td>
                </tr>
            `;
        }).join('');
    }

    function renderRunMeta() {
        const box = document.getElementById('bimInboxRunMeta');
        if (!box) return;
        const run = STATE.selectedRun;
        if (!run) {
            box.classList.add('muted');
            box.innerHTML = 'یک Run را انتخاب کنید تا جزئیات و آیتم‌ها نمایش داده شود.';
            return;
        }
        box.classList.remove('muted');
        const summary = runSummary(run);
        const sender = norm(run?.sender_name) || norm(run?.sender_email) || '-';
        box.innerHTML = `
            <div class="bulk-bim-meta-grid">
              <div><strong>Run:</strong> <code>${esc(run?.run_id || '-')}</code></div>
              <div><strong>Project:</strong> ${esc(run?.project_code || '-')}</div>
              <div><strong>Sender:</strong> ${esc(sender)}</div>
              <div><strong>Status:</strong> ${statusBadge(run?.status)}</div>
              <div><strong>Valid / Invalid:</strong> ${summary.valid} / ${summary.invalid}</div>
              <div><strong>Duplicates:</strong> ${summary.duplicate}</div>
              <div><strong>Approvable:</strong> ${run?.approvable ? 'yes' : 'no'}</div>
              <div><strong>Created:</strong> ${esc(formatUtc(run?.started_at))}</div>
              <div><strong>Expires:</strong> ${esc(formatUtc(run?.expires_at))}</div>
            </div>
        `;
    }

    function renderRunItems() {
        const body = document.getElementById('bimInboxItemsBody');
        if (!body) return;

        if (STATE.loadingItems) {
            body.innerHTML = '<tr><td colspan="5" class="text-center muted">در حال بارگذاری آیتم‌ها ...</td></tr>';
            return;
        }

        if (!Array.isArray(STATE.runItems) || !STATE.runItems.length) {
            body.innerHTML = '<tr><td colspan="5" class="text-center muted">آیتمی وجود ندارد.</td></tr>';
            return;
        }

        body.innerHTML = STATE.runItems.map((item) => {
            const stateKey = norm(item?.state).toLowerCase();
            const stateClass = stateKey === 'completed'
                ? 'status-success'
                : (stateKey === 'failed' ? 'status-danger' : 'status-muted');
            const errorCode = norm(item?.error_code);
            const errorMessage = norm(item?.error_message);
            const errorText = errorCode && errorMessage
                ? `${errorCode}: ${errorMessage}`
                : (errorMessage || errorCode || '-');
            const stagingFile = norm(item?.staging_file_ref);
            return `
                <tr>
                  <td>${Number(item?.item_index ?? 0)}</td>
                  <td>${esc(item?.sheet_number || item?.sheet_unique_id || '-')}</td>
                  <td class="${stateClass}">${esc(item?.state || '-')}</td>
                  <td title="${esc(errorText)}">${esc(errorText)}</td>
                  <td title="${esc(stagingFile || '-')}">${esc(stagingFile || '-')}</td>
                </tr>
            `;
        }).join('');
    }

    function runFiltersQuery() {
        const params = new URLSearchParams();
        const project = norm(document.getElementById('bimInboxProjectFilterInput')?.value).toUpperCase();
        const status = norm(document.getElementById('bimInboxStatusFilterSelect')?.value).toLowerCase();
        const from = toIsoUtcFromInput('bimInboxCreatedFromInput');
        const to = toIsoUtcFromInput('bimInboxCreatedToInput');
        if (project) params.set('project_code', project);
        if (status) params.set('status', status);
        if (from) params.set('created_from', from);
        if (to) params.set('created_to', to);
        params.set('limit', '100');
        params.set('offset', '0');
        return params.toString();
    }

    async function loadInboxRuns(options = {}) {
        if (STATE.loadingRuns) return;
        const silent = Boolean(options?.silent);
        STATE.loadingRuns = true;
        renderRuns();
        try {
            const query = runFiltersQuery();
            const url = `${INBOX_API_BASE}/runs${query ? `?${query}` : ''}`;
            const payload = await request(url);
            STATE.runs = Array.isArray(payload?.items) ? payload.items : [];
            if (STATE.selectedRunId) {
                const stillExists = STATE.runs.some((row) => norm(row?.run_id) === STATE.selectedRunId);
                if (!stillExists) {
                    STATE.selectedRunId = '';
                    STATE.selectedRun = null;
                    STATE.runItems = [];
                }
            }
            renderRuns();
            renderRunMeta();
            renderRunItems();
            setApproveButtonsState();
            if (!silent) {
                setInboxResult(`Loaded ${STATE.runs.length} run(s).`, 'info');
            }
        } catch (err) {
            STATE.runs = [];
            renderRuns();
            renderRunMeta();
            renderRunItems();
            setApproveButtonsState();
            setInboxResult(err?.message || 'Failed to load inbox runs.', 'error');
        } finally {
            STATE.loadingRuns = false;
            renderRuns();
            setApproveButtonsState();
        }
    }

    async function loadRunDetails(runId) {
        const targetRunId = norm(runId);
        if (!targetRunId) return;
        STATE.selectedRunId = targetRunId;
        STATE.loadingItems = true;
        renderRuns();
        renderRunMeta();
        renderRunItems();
        setApproveButtonsState();
        try {
            const [runPayload, itemsPayload] = await Promise.all([
                request(`${INBOX_API_BASE}/runs/${encodeURIComponent(targetRunId)}`),
                request(`${INBOX_API_BASE}/runs/${encodeURIComponent(targetRunId)}/items`),
            ]);
            STATE.selectedRun = runPayload || null;
            STATE.runItems = Array.isArray(itemsPayload?.items) ? itemsPayload.items : [];
            renderRuns();
            renderRunMeta();
            renderRunItems();
            setApproveButtonsState();
            setInboxResult(`Run ${targetRunId} loaded.`, 'info');
        } catch (err) {
            STATE.selectedRun = null;
            STATE.runItems = [];
            renderRunMeta();
            renderRunItems();
            setApproveButtonsState();
            setInboxResult(err?.message || 'Failed to load run details.', 'error');
        } finally {
            STATE.loadingItems = false;
            renderRunItems();
            setApproveButtonsState();
        }
    }

    async function approveSelectedRun() {
        const run = STATE.selectedRun;
        const runId = norm(run?.run_id || STATE.selectedRunId);
        if (!runId) {
            throw new Error('ابتدا یک Run انتخاب کنید.');
        }
        if (!confirm(`Approve & Archive run ${runId}?`)) return;

        setInboxResult(`Approving run ${runId} ...`, 'info');
        await request(`${INBOX_API_BASE}/runs/${encodeURIComponent(runId)}/approve`, { method: 'POST' });
        setInboxResult(`Run ${runId} approved and archived.`, 'success');
        await loadInboxRuns({ silent: true });
        await loadRunDetails(runId);
    }

    async function rejectSelectedRun() {
        const run = STATE.selectedRun;
        const runId = norm(run?.run_id || STATE.selectedRunId);
        if (!runId) {
            throw new Error('ابتدا یک Run انتخاب کنید.');
        }
        const reasonInput = document.getElementById('bimInboxRejectReasonInput');
        const reason = norm(reasonInput?.value);
        if (!reason) {
            throw new Error('برای Reject باید دلیل وارد شود.');
        }
        if (!confirm(`Reject run ${runId}?`)) return;

        setInboxResult(`Rejecting run ${runId} ...`, 'info');
        await request(`${INBOX_API_BASE}/runs/${encodeURIComponent(runId)}/reject`, {
            method: 'POST',
            body: JSON.stringify({ reason }),
        });
        setInboxResult(`Run ${runId} rejected.`, 'success');
        await loadInboxRuns({ silent: true });
        await loadRunDetails(runId);
    }

    function switchBulkTab(tabName) {
        const target = norm(tabName).toLowerCase() === 'bim' ? 'bim' : 'excel';
        STATE.activeTab = target;
        const root = document.getElementById('settingsBulkRoot');
        if (!root) return;

        root.querySelectorAll('[data-bulk-tab]').forEach((el) => {
            const isActive = norm(el?.dataset?.bulkTab).toLowerCase() === target;
            el.classList.toggle('active', isActive);
            el.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        root.querySelectorAll('[data-bulk-panel]').forEach((panel) => {
            const isActive = norm(panel?.dataset?.bulkPanel).toLowerCase() === target;
            panel.classList.toggle('active', isActive);
            panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        });

        if (target === 'bim' && !STATE.runs.length) {
            loadInboxRuns({ silent: false }).catch((err) => {
                setInboxResult(err?.message || 'Failed to load BIM inbox.', 'error');
            });
        }
    }

    function applyFrameHeight(frame, rawHeight) {
        const h = Number(rawHeight || 0);
        if (!Number.isFinite(h) || h <= 0) return;
        const nextHeight = Math.max(FRAME_MIN_HEIGHT, Math.ceil(h + 12));
        frame.style.height = `${nextHeight}px`;
    }

    function bindBulkIframeResize() {
        if (STATE.frameResizeBound) return;
        const frame = document.getElementById('bulkRegisterFrame');
        if (!frame) return;
        STATE.frameResizeBound = true;

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
                    root ? root.offsetHeight : 0,
                );
                applyFrameHeight(frame, contentHeight);
            } catch (_) {
                // ignore cross-window failures and rely on postMessage
            }
        }

        try {
            const current = frame.getAttribute('src') || '/api/v1/mdr/bulk-register-page';
            const url = new URL(current, window.location.origin);
            url.searchParams.set('_cb', String(Date.now()));
            frame.setAttribute('src', `${url.pathname}${url.search}${url.hash}`);
        } catch (_) {
            // keep existing src
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
            const data = event?.data || {};
            if (data.type !== 'mdr-bulk-height') return;
            applyFrameHeight(frame, data.height);
        });
    }

    function bindActions() {
        const root = document.getElementById('settingsBulkRoot');
        if (!root || root.dataset.bulkBound === '1') return;

        root.addEventListener('click', async (event) => {
            const tabEl = event?.target?.closest?.('[data-bulk-tab]');
            if (tabEl && root.contains(tabEl)) {
                event.preventDefault();
                switchBulkTab(tabEl.dataset.bulkTab || 'excel');
                return;
            }

            const actionEl = event?.target?.closest?.('[data-bulk-action]');
            if (!actionEl || !root.contains(actionEl)) return;
            event.preventDefault();
            const action = norm(actionEl.dataset.bulkAction).toLowerCase();
            try {
                if (action === 'refresh-bim-inbox') {
                    await loadInboxRuns({ silent: false });
                    return;
                }
                if (action === 'select-bim-run') {
                    await loadRunDetails(actionEl.dataset.runId || '');
                    return;
                }
                if (action === 'approve-bim-run') {
                    await approveSelectedRun();
                    return;
                }
                if (action === 'reject-bim-run') {
                    await rejectSelectedRun();
                    return;
                }
            } catch (err) {
                setInboxResult(err?.message || 'Operation failed.', 'error');
            }
        });

        root.dataset.bulkBound = '1';
    }

    async function initSettingsBulk() {
        const root = document.getElementById('settingsBulkRoot');
        if (!root) return;
        bindBulkIframeResize();
        bindActions();
        if (!STATE.initialized) {
            switchBulkTab('excel');
            STATE.initialized = true;
        } else {
            switchBulkTab(STATE.activeTab || 'excel');
        }
        setApproveButtonsState();
    }

    window.initSettingsBulk = initSettingsBulk;
    initSettingsBulk().catch(() => {});
})();
