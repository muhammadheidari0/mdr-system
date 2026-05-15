// @ts-nocheck
const MAX_FILE_SIZE_MB = 15;
    const MAX_CLIENT_ROWS = 10000;
    const BULK_SUBMIT_CHUNK_SIZE = 400;
    const RENDER_BATCH_SIZE = 120;
    const REQUEST_TIMEOUT_MS = 180000;
    const DRAFT_KEY = 'mdr_bulk_draft_v1';
    const DRAFT_DEBOUNCE_MS = 700;
    const FILTER_DEBOUNCE_MS = 180;
    const SUBJECT_SUGGEST_LIMIT = 12;
    const REVISION_OPTIONS = ['00', '01', '02', '03', 'A', 'B', 'C'];
    const DOC_STATUS_OPTIONS = ['Registered', 'Draft', 'IFA', 'IFC', 'IFR', 'Approved', 'Rejected'];
    const DUPLICATE_KEY_ROW_MSG = 'Duplicate key fields in table.';

    // --- Global Data ---
    let dictData = { projects: [], phases: [], disciplines: [], packages: [], blocks: [], levels: [], mdr_categories: [] };
    let draftTimer = null;
    const subjectSuggestCache = new Map();
    const isEmbedded = window.self !== window.top;
    if (isEmbedded) {
        document.body.classList.add('embedded');
    }
    window.addEventListener('load', () => setTimeout(postFrameHeight, 50));
    window.addEventListener('resize', () => requestAnimationFrame(postFrameHeight));

    // --- Auth Helper ---
    function getAuthHeaders() {
        const token = localStorage.getItem('access_token');
        if (!token) {
            window.location.href = '/login';
            throw new Error('No access token');
        }
        return { Authorization: `Bearer ${token}` };
    }

    function extractErrorMessage(response, fallback = 'Request failed') {
        if (!response) return fallback;
        if (response.status === 413) return 'Payload is too large. Split file into smaller batches.';
        if (response.status === 401 || response.status === 403) return 'Session expired or unauthorized.';
        if (response.status === 408) return 'Request timeout. Please retry.';
        return fallback;
    }

    async function fetchWithAuth(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), timeoutMs);
        const headers = { ...options.headers, ...getAuthHeaders() };
        try {
            const response = await fetch(url, { ...options, headers, signal: controller.signal });
            if (response.status === 401 || response.status === 403) {
                showBanner('Session expired. Redirecting to login...', 'error');
                window.location.href = '/login';
                throw new Error('Access denied');
            }
            return response;
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('Request timeout. Try a smaller file or retry.');
            }
            throw error;
        } finally {
            clearTimeout(timeout);
        }
    }

    function showBanner(message, type = 'info') {
        const el = document.getElementById('statusBanner');
        if (!el) return;
        el.className = `status-banner ${type}`;
        el.textContent = message;
        el.style.display = 'block';
        requestAnimationFrame(postFrameHeight);
    }

    function hideBanner() {
        const el = document.getElementById('statusBanner');
        if (!el) return;
        el.style.display = 'none';
        el.textContent = '';
        requestAnimationFrame(postFrameHeight);
    }

    function setProgress(percent, text = '') {
        const wrap = document.getElementById('progressWrap');
        const bar = document.getElementById('progressBar');
        const label = document.getElementById('progressText');
        if (!wrap || !bar || !label) return;
        wrap.style.display = 'block';
        bar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
        label.textContent = text;
    }

    function hideProgress() {
        const wrap = document.getElementById('progressWrap');
        const bar = document.getElementById('progressBar');
        const label = document.getElementById('progressText');
        if (!wrap || !bar || !label) return;
        wrap.style.display = 'none';
        bar.style.width = '0%';
        label.textContent = '';
    }

    function postFrameHeight() {
        if (!isEmbedded) return;
        const body = document.body;
        const doc = document.documentElement;
        const height = Math.max(
            body ? body.scrollHeight : 0,
            body ? body.offsetHeight : 0,
            doc ? doc.scrollHeight : 0,
            doc ? doc.offsetHeight : 0
        );
        window.parent.postMessage({ type: 'mdr-bulk-height', height }, '*');
    }

    // --- Init: Load Dictionaries (Secured) ---
    (async function init() {
        try {
            const res = await fetchWithAuth('/api/v1/lookup/dictionary');
            const data = await res.json();
            if (data.ok) {
                dictData = data.data;
                tryRestoreDraft();
            } else {
                showBanner('Failed to load dictionary data.', 'error');
            }
        } catch (e) {
            console.error('Dictionary load error', e);
            showBanner('Cannot load dictionary data. Check network or login.', 'error');
        } finally {
            bindPageUiEvents();
            bindTableEvents();
        }
    })();

    // --- Tab Switching ---
    function switchTab(event, tabName) {
        document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));
        const activeTabBtn = event?.currentTarget || document.querySelector(`.tab[data-bulk-tab="${tabName}"]`);
        if (activeTabBtn) activeTabBtn.classList.add('active');
        const target = document.getElementById(`tab-${tabName}`);
        if (target) target.classList.add('active');
        scheduleDraftSave();
    }

    function bindPageUiEvents() {
        const root = document.body;
        if (!root || root.dataset.bulkUiBound === '1') return;

        const tabs = document.getElementById('bulkTabs');
        if (tabs) {
            tabs.addEventListener('click', (event) => {
                const tabBtn = event.target.closest('.tab[data-bulk-tab]');
                if (!tabBtn || !tabs.contains(tabBtn)) return;
                event.preventDefault();
                const tabName = String(tabBtn.getAttribute('data-bulk-tab') || '').trim().toLowerCase();
                if (!tabName) return;
                switchTab({ currentTarget: tabBtn }, tabName);
            });
        }

        const fileInput = document.getElementById('fileInput');
        const uploadZone = document.getElementById('bulkFileUploadZone');
        if (uploadZone) {
            uploadZone.addEventListener('click', (event) => {
                if (event.target === fileInput) return;
                if (fileInput) fileInput.click();
            });
            uploadZone.addEventListener('dragover', handleDragOver);
            uploadZone.addEventListener('dragleave', handleDragLeave);
            uploadZone.addEventListener('drop', handleDrop);
        }
        if (fileInput) {
            fileInput.addEventListener('change', handleFileSelect);
        }

        const quickFilterInput = document.getElementById('quickFilterInput');
        if (quickFilterInput) {
            quickFilterInput.addEventListener('input', handleQuickFilterInput);
        }

        root.addEventListener('click', async (event) => {
            const actionEl = event.target.closest('[data-bulk-action]');
            if (!actionEl) return;
            event.preventDefault();
            const action = String(actionEl.getAttribute('data-bulk-action') || '').trim().toLowerCase();
            switch (action) {
                case 'upload-link':
                    await handleLinkUpload();
                    break;
                case 'add-manual-row':
                    addManualRow();
                    break;
                case 'clear-filter':
                    clearQuickFilter();
                    break;
                case 'jump-row':
                    jumpToRow();
                    break;
                case 'save-draft':
                    saveDraftNow(true);
                    break;
                case 'clear-draft':
                    clearDraft(true, true);
                    break;
                case 'submit-final':
                    await submitFinal();
                    break;
                default:
                    break;
            }
        });

        root.dataset.bulkUiBound = '1';
    }

    // --- Helper Functions ---
    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function buildOptions(items, valueKey, labelKey, selectedValue = '') {
        const selectedStr = String(selectedValue ?? '');
        return (items || []).map((item) => {
            const rawValue = String(item?.[valueKey] ?? '');
            const rawLabel = String(item?.[labelKey] ?? item?.name ?? item?.project_name ?? item?.name_e ?? rawValue);
            const selected = rawValue === selectedStr ? 'selected' : '';
            return `<option value="${escapeHtml(rawValue)}" ${selected}>${escapeHtml(rawLabel)}</option>`;
        }).join('');
    }

    function buildSimpleOptions(values, selectedValue = '') {
        const selectedStr = String(selectedValue ?? '');
        return (values || []).map((value) => {
            const rawValue = String(value ?? '');
            const selected = rawValue === selectedStr ? 'selected' : '';
            return `<option value="${escapeHtml(rawValue)}" ${selected}>${escapeHtml(rawValue)}</option>`;
        }).join('');
    }

    function parseCodeToData(docNumber) {
        if (!docNumber || typeof docNumber !== 'string') return {};
        const parts = docNumber.trim().split('-');
        if (parts.length < 3) return {};

        const proj = parts[0] || '';
        const middle = parts[1] || '';
        const suffix = parts[2] || '';

        const mdr = middle.substring(0, 1) || 'E';
        const phase = middle.substring(1, 2) || 'X';

        let pkg = '00';
        let disc = '';
        const packageAndSerial = middle.substring(2);
        if (packageAndSerial) {
            const serialMatch = packageAndSerial.match(/(\d{2})$/);
            const corePkg = serialMatch ? (packageAndSerial.slice(0, -2) || '00') : packageAndSerial;
            const discMatch = String(corePkg || '').match(/^([A-Z]+?)(\d.*)$/);
            if (discMatch) {
                disc = String(discMatch[1] || '').trim().toUpperCase();
                pkg = String(discMatch[2] || '').trim().toUpperCase() || '00';
            } else {
                pkg = String(corePkg || '').trim().toUpperCase() || '00';
                disc = pkg.length >= 2 ? pkg.substring(0, 2) : '';
            }
        }

        const block = suffix.substring(0, 1) || 'G';
        const level = suffix.substring(1) || 'GEN';

        return { proj, mdr, phase, disc, pkg, block, level };
    }

    function normalizeSubjectForSerial(value) {
        return String(value || '')
            .toLowerCase()
            .replace(/[^a-z0-9\u0600-\u06ff]/g, '');
    }

    function parseSerialFromDocCode(code) {
        const doc = String(code || '').trim();
        if (!doc) return null;
        const parts = doc.split('-');
        if (parts.length < 2) return null;
        const middle = parts[1] || '';
        const serialMatch = middle.match(/(\d{2})$/);
        if (!serialMatch) return null;

        const parsed = parseCodeToData(doc);
        if (!parsed.proj || !parsed.mdr || !parsed.phase || !parsed.disc || !parsed.pkg || !parsed.block || !parsed.level) return null;

        const serialInt = Number(serialMatch[1]);
        if (!Number.isFinite(serialInt)) return null;

        const prefix = `${parsed.proj}-${parsed.mdr}${parsed.phase}${parsed.disc}${parsed.pkg}`;
        const suffix = `${parsed.block}${parsed.level}`;
        const scope = `${prefix}-${suffix}`;
        return { prefix, suffix, scope, serialInt, serialStr: serialMatch[1] };
    }

    function formatSerialInt(value) {
        const num = Number(value);
        const safe = Number.isFinite(num) && num > 0 ? Math.floor(num) : 1;
        return safe < 100 ? String(safe).padStart(2, '0') : String(safe);
    }

    function canBuildCode(row) {
        return [row.project, row.mdr, row.phase, row.pkg, row.block, row.level]
            .every((v) => !!String(v || '').trim());
    }

    function buildDocCode(row, serialStr) {
        const prefix = `${row.project}-${row.mdr}${row.phase}${row.disc}${row.pkg}`;
        return `${prefix}${serialStr}-${row.block}${row.level}`;
    }

    function rebuildAutoCodes() {
        const maxSerialByScope = new Map();
        const serialBySubjectKey = new Map();

        rowStore.forEach((row) => {
            if (!row || !row.providedCode) return;
            const parsed = parseSerialFromDocCode(row.code);
            if (!parsed) return;

            const currentMax = maxSerialByScope.get(parsed.scope) || 0;
            if (parsed.serialInt > currentMax) maxSerialByScope.set(parsed.scope, parsed.serialInt);

            const subjectNorm = normalizeSubjectForSerial(row.subject);
            if (subjectNorm) {
                const key = `${parsed.scope}__${subjectNorm}`;
                if (!serialBySubjectKey.has(key)) serialBySubjectKey.set(key, parsed.serialStr);
            }
        });

        rowStore.forEach((row) => {
            if (!row) return;
            if (row.providedCode) {
                row.__search = null;
                return;
            }

            if (!canBuildCode(row)) {
                if (row.code) row.__search = null;
                row.code = '';
                return;
            }

            const prefix = `${row.project}-${row.mdr}${row.phase}${row.disc}${row.pkg}`;
            const scope = `${prefix}-${row.block}${row.level}`;
            const subjectNorm = normalizeSubjectForSerial(row.subject);
            let serialStr = '';

            if (subjectNorm) {
                const subjectKey = `${scope}__${subjectNorm}`;
                serialStr = serialBySubjectKey.get(subjectKey) || '';
                if (!serialStr) {
                    const next = (maxSerialByScope.get(scope) || 0) + 1;
                    maxSerialByScope.set(scope, next);
                    serialStr = formatSerialInt(next);
                    serialBySubjectKey.set(subjectKey, serialStr);
                }
            } else {
                // Subjectless policy: only serial 01 for each exact coding scope.
                serialStr = '01';
            }

            const nextCode = buildDocCode(row, serialStr);
            if (row.code !== nextCode) {
                row.code = nextCode;
                row.__search = null;
            }
        });
    }

    function syncVisibleCodeInputs() {
        const rows = document.querySelectorAll('#tableBody tr[data-row-index]');
        rows.forEach((tr) => {
            const idx = Number(tr.dataset.rowIndex);
            if (!Number.isInteger(idx) || !rowStore[idx]) return;
            const codeInput = tr.querySelector('.data-code');
            if (codeInput) codeInput.value = rowStore[idx].code || '';
        });
    }

    function refreshArchiveControlsForRow(tr, row) {
        if (!tr || !row) return;
        const hasFiles = hasAttachedFiles(row);
        const revisionEl = tr.querySelector('.data-revision');
        if (revisionEl) revisionEl.value = hasFiles ? 'AUTO' : '-';

        const statusEl = tr.querySelector('.data-doc-status');
        if (!statusEl) return;
        statusEl.disabled = !hasFiles;
        if (hasFiles) {
            if (!row.status) row.status = 'Registered';
            statusEl.value = row.status;
        }
    }

    function syncComputedInputsForRow(tr, row) {
        if (!tr || !row) return;
        const codeEl = tr.querySelector('.data-code');
        if (codeEl) codeEl.value = row.code || '';
        const titlePEl = tr.querySelector('.data-title-p');
        if (titlePEl) titlePEl.value = row.titleP || '';
        const titleEEl = tr.querySelector('.data-title-e');
        if (titleEEl) titleEEl.value = row.titleE || '';
        refreshArchiveControlsForRow(tr, row);
    }

    function buildPrefixForRow(row) {
        if (!row) return '';
        const project = String(row.project || '').trim().toUpperCase();
        const mdr = String(row.mdr || '').trim().toUpperCase();
        const phase = String(row.phase || '').trim().toUpperCase();
        const disc = String(row.disc || '').trim().toUpperCase();
        const pkg = String(row.pkg || '').trim().toUpperCase();
        if (!project || !mdr || !phase || !disc || !pkg) return '';
        return `${project}-${mdr}${phase}${disc}${pkg}`;
    }

    function collectLocalSubjectSuggestions(prefix, query = '') {
        const qNorm = normalizeSubjectForSerial(query);
        const seen = new Set();
        const out = [];
        rowStore.forEach((row) => {
            if (buildPrefixForRow(row) !== prefix) return;
            const value = String(row.subject || '').trim();
            if (!value) return;
            const k = normalizeSubjectForSerial(value);
            if (qNorm && !k.includes(qNorm)) return;
            if (seen.has(k)) return;
            seen.add(k);
            out.push(value);
        });
        return out;
    }

    function setSubjectSuggestionList(items) {
        const list = document.getElementById('subjectSuggestionsList');
        if (!list) return;
        list.innerHTML = (items || [])
            .map((item) => `<option value="${escapeHtml(item)}"></option>`)
            .join('');
    }

    async function fetchSubjectSuggestionsFromServer(row, query = '') {
        const prefix = buildPrefixForRow(row);
        if (!prefix) return [];
        const cacheKey = `${prefix}__${normalizeSubjectForSerial(query)}`;
        if (subjectSuggestCache.has(cacheKey)) {
            return subjectSuggestCache.get(cacheKey) || [];
        }

        const params = new URLSearchParams({
            project_code: row.project || '',
            mdr_code: row.mdr || '',
            phase: row.phase || '',
            pkg: row.pkg || '',
            discipline_code: row.disc || '',
            limit: String(SUBJECT_SUGGEST_LIMIT),
        });
        if (String(query || '').trim()) params.set('q', query.trim());

        try {
            const res = await fetchWithAuth(`/api/v1/mdr/subject-suggestions?${params.toString()}`);
            const payload = await res.json().catch(() => ({}));
            if (!res.ok || !payload?.ok || !Array.isArray(payload?.items)) {
                return [];
            }
            const items = payload.items.map((x) => String(x || '').trim()).filter(Boolean);
            subjectSuggestCache.set(cacheKey, items);
            return items;
        } catch (_) {
            return [];
        }
    }

    async function updateSubjectSuggestions(tr, query = '') {
        const idx = Number(tr?.dataset?.rowIndex);
        if (!Number.isInteger(idx) || !rowStore[idx]) return;
        const row = rowStore[idx];
        const prefix = buildPrefixForRow(row);
        if (!prefix) {
            setSubjectSuggestionList([]);
            return;
        }
        const local = collectLocalSubjectSuggestions(prefix, query);
        const remote = await fetchSubjectSuggestionsFromServer(row, query);
        const seen = new Set();
        const merged = [];
        [...local, ...remote].forEach((item) => {
            const value = String(item || '').trim();
            if (!value) return;
            const key = normalizeSubjectForSerial(value);
            if (seen.has(key)) return;
            seen.add(key);
            merged.push(value);
        });
        setSubjectSuggestionList(merged.slice(0, SUBJECT_SUGGEST_LIMIT));
    }

    // --- File Handling ---
    function handleDragOver(e) {
        e.preventDefault();
        e.currentTarget.classList.add('dragover');
    }

    function handleDragLeave(e) {
        e.currentTarget.classList.remove('dragover');
    }

    function handleDrop(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    }

    function handleFileSelect(e) {
        const files = e.target.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    }

    async function handleFile(file) {
        if (!file.name.match(/\.(xlsx|xls)$/i)) {
            showBanner('Only Excel files (.xlsx/.xls) are supported.', 'error');
            return;
        }
        if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
            showBanner(`File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Max allowed is ${MAX_FILE_SIZE_MB} MB.`, 'warning');
            return;
        }

        hideBanner();
        setStatus(`Processing file: ${file.name} ...`, 'blue');
        setProgress(15, 'Uploading file...');

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetchWithAuth('/api/v1/mdr/parse-import-source', {
                method: 'POST',
                body: formData
            });
            setProgress(75, 'Parsing rows...');
            const data = await res.json();

            if (res.ok && data.ok) {
                await populateTable(data.rows || []);
                setProgress(100, 'Preview is ready');
                const rowCount = data.count || (data.rows || []).length;
                setStatus(`Loaded ${rowCount} row(s).`, 'green');
                showBanner(`Preview loaded successfully (${rowCount} rows).`, 'success');
            } else {
                const msg = data.detail || data.message || extractErrorMessage(res, 'Failed to parse file.');
                showBanner(msg, 'error');
                setStatus('Parse failed.', 'red');
            }
        } catch (e) {
            console.error(e);
            showBanner(e.message || 'Network/access error while parsing file.', 'error');
            setStatus('Parse failed.', 'red');
        } finally {
            setTimeout(hideProgress, 700);
        }
    }


    async function handleLinkUpload() {
        const url = document.getElementById('sheetUrl').value.trim();
        if (!url) {
            showBanner('Please enter a Google Sheet URL.', 'warning');
            return;
        }
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            showBanner('URL must start with http:// or https://', 'warning');
            return;
        }

        document.getElementById('linkLoader').style.display = 'inline-block';
        hideBanner();
        setProgress(20, 'Fetching URL...');

        try {
            const formData = new FormData();
            formData.append('url', url);

            const res = await fetchWithAuth('/api/v1/mdr/parse-import-source', {
                method: 'POST',
                body: formData
            });
            setProgress(75, 'Parsing rows...');
            const data = await res.json();

            if (res.ok && data.ok) {
                await populateTable(data.rows || []);
                setProgress(100, 'Preview is ready');
                const rowCount = data.count || (data.rows || []).length;
                setStatus(`Loaded ${rowCount} row(s).`, 'green');
                showBanner(`Preview loaded successfully (${rowCount} rows).`, 'success');
            } else {
                const msg = data.detail || data.message || extractErrorMessage(res, 'Invalid URL source.');
                showBanner(msg, 'error');
                setStatus('URL parse failed.', 'red');
            }
        } catch (e) {
            console.error(e);
            showBanner(e.message || 'Network/access error while parsing URL.', 'error');
            setStatus('URL parse failed.', 'red');
        } finally {
            document.getElementById('linkLoader').style.display = 'none';
            setTimeout(hideProgress, 700);
        }
    }


    // --- Table Management / Virtualized Rendering ---
    let rowStore = [];
    let virtualEnabled = false;
    const VIRTUAL_THRESHOLD = 200;
    const VIRTUAL_ROW_HEIGHT = 64;
    const VIRTUAL_OVERSCAN = 8;
    let lastVirtualStart = -1;
    let lastVirtualEnd = -1;
    let filteredIndexes = null;
    let activeFilterQuery = '';
    let filterTimer = null;

    function getFirstValue(items, key, fallback) {
        if (!Array.isArray(items) || !items.length) return fallback;
        const value = String(items[0]?.[key] ?? '').trim();
        return value || fallback;
    }

    function getDefaultProject() {
        return getFirstValue(dictData.projects, 'code', 'T202');
    }

    function getDefaultMdr() {
        return getFirstValue(dictData.mdr_categories, 'code', 'E');
    }

    function getDefaultPhase() {
        return getFirstValue(dictData.phases, 'ph_code', 'X');
    }

    function getDefaultDisc() {
        return getFirstValue(dictData.disciplines, 'code', 'GN');
    }

    function getDefaultBlock() {
        return getFirstValue(dictData.blocks, 'code', 'G');
    }

    function getDefaultLevel() {
        return getFirstValue(dictData.levels, 'code', 'GEN');
    }

    function getDefaultPkgForDisc(disc) {
        const list = Array.isArray(dictData.packages) ? dictData.packages : [];
        const found = list.find((p) => String(p?.discipline_code || '') === String(disc || ''));
        if (found?.package_code) return String(found.package_code);
        return '00';
    }

    function getPackageNames(disc, pkg) {
        const list = Array.isArray(dictData.packages) ? dictData.packages : [];
        const hit = list.find((p) => (
            String(p?.discipline_code || '') === String(disc || '') &&
            String(p?.package_code || '') === String(pkg || '')
        ));
        const pkgCode = String(pkg || '00').trim() || '00';
        const nameE = String(hit?.name_e || pkgCode).trim() || pkgCode;
        const nameP = String(hit?.name_p || hit?.name_e || pkgCode).trim() || nameE;
        return { nameE, nameP };
    }

    function buildAutoTitles(row) {
        const block = String(row?.block || '').trim().toUpperCase();
        const level = String(row?.level || '').trim().toUpperCase();
        const subject = String(row?.subject || '').trim();
        const pkg = String(row?.pkg || '').trim();
        const disc = String(row?.disc || '').trim();
        if (!pkg || !block || !level) {
            return { titleE: '', titleP: '' };
        }
        const pkgNames = getPackageNames(disc, pkg);
        const omitLocation = block === 'T' && level === 'GEN';
        const locationPart = `${block}${level}`;

        let titleE = pkgNames.nameE;
        if (!omitLocation) titleE = `${titleE}-${locationPart}`;
        if (subject) {
            titleE += ` - ${subject}`;
        }

        let titleP = omitLocation ? pkgNames.nameP : `${locationPart}-${pkgNames.nameP}`;
        if (subject) titleP += `-${subject}`;
        return { titleE, titleP };
    }

    function refreshAutoTitlesForRow(row) {
        if (!row) return;
        const { titleE, titleP } = buildAutoTitles(row);
        row.titleE = titleE;
        row.titleP = titleP;
    }

    function normalizeRowInput(data = {}, options = {}) {
        const useDefaults = options?.useDefaults !== false;
        const code = data.doc_number ?? data.code ?? '';
        const parsed = code ? parseCodeToData(code) : {};

        const projectDefault = useDefaults ? getDefaultProject() : '';
        const mdrDefault = useDefaults ? getDefaultMdr() : '';
        const phaseDefault = useDefaults ? getDefaultPhase() : '';
        const discDefault = useDefaults ? getDefaultDisc() : '';
        const blockDefault = useDefaults ? getDefaultBlock() : '';
        const levelDefault = useDefaults ? getDefaultLevel() : '';

        const project = String(data.project ?? parsed.proj ?? projectDefault).trim() || projectDefault;
        const mdr = String(data.mdr ?? parsed.mdr ?? mdrDefault).trim() || mdrDefault;
        const phase = String(data.phase ?? parsed.phase ?? phaseDefault).trim() || phaseDefault;

        const discRaw = String(data.disc ?? parsed.disc ?? discDefault).trim();
        const disc = discRaw || discDefault;

        const pkgRaw = String(data.pkg ?? parsed.pkg ?? '').trim();
        const pkg = pkgRaw || (disc ? getDefaultPkgForDisc(disc) : '');

        const block = String(data.block ?? parsed.block ?? blockDefault).trim() || blockDefault;
        const level = String(data.level ?? parsed.level ?? levelDefault).trim() || levelDefault;
        const revision = String(data.revision ?? data.rev ?? '00').trim() || '00';
        const status = String(data.status ?? 'Registered').trim() || 'Registered';

        const titleP = String(data.title_p ?? data.titleP ?? '').trim();
        const titleE = String(data.title_e ?? data.titleE ?? '').trim();
        const subject = String(
            data.subject ?? data.subject_e ?? data.subject_p ?? data.subjectE ?? data.subjectP ?? ''
        ).trim();
        const rawCode = String(code || '').trim();
        const explicitProvidedCode = data.provided_code ?? data.providedCode;
        const providedCode = typeof explicitProvidedCode === 'boolean' ? explicitProvidedCode : !!rawCode;

        const row = {
            code: rawCode,
            providedCode,
            subject,
            titleP,
            titleE,
            project,
            mdr,
            phase,
            disc,
            pkg,
            block,
            level,
            revision,
            status,
            pdfFile: null,
            nativeFile: null,
            pdfName: '',
            nativeName: '',
            rowResult: '',
            rowResultType: '',
            __search: null,
        };
        refreshAutoTitlesForRow(row);
        return row;
    }

    function buildPackageOptions(disc, selectedValue = '') {
        const list = (dictData.packages || []).filter((p) => {
            if (!disc) return true;
            return String(p?.discipline_code || '') === String(disc);
        });
        if (!list.length) return '<option value="">-</option>';
        return buildOptions(list, 'package_code', 'name_e', selectedValue);
    }

    function rowIsValidData(row) {
        const required = [row.project, row.mdr, row.phase, row.disc, row.pkg, row.block, row.level];
        const coreValid = required.every((v) => !!String(v || '').trim());
        return coreValid;
    }

    function normalizeDupKeyToken(value) {
        return String(value || '').trim().toUpperCase();
    }

    function buildDuplicateValidationKey(row) {
        if (!rowIsValidData(row)) return '';
        const project = normalizeDupKeyToken(row.project);
        const mdr = normalizeDupKeyToken(row.mdr);
        const phase = normalizeDupKeyToken(row.phase);
        const disc = normalizeDupKeyToken(row.disc);
        const pkg = normalizeDupKeyToken(row.pkg);
        const block = normalizeDupKeyToken(row.block);
        const level = normalizeDupKeyToken(row.level);
        const subjectNorm = normalizeSubjectForSerial(row.subject);
        return [project, mdr, phase, disc, pkg, block, level, subjectNorm].join('|');
    }

    function collectDuplicateKeyRowIndexes() {
        const byKey = new Map();
        rowStore.forEach((row, index) => {
            const key = buildDuplicateValidationKey(row);
            if (!key) return;
            if (!byKey.has(key)) byKey.set(key, []);
            byKey.get(key).push(index);
        });

        const duplicateIndexes = [];
        byKey.forEach((indexes) => {
            if (indexes.length > 1) duplicateIndexes.push(...indexes);
        });
        duplicateIndexes.sort((a, b) => a - b);
        return duplicateIndexes;
    }

    function applyDuplicateRowFlags(duplicateIndexes) {
        const dupSet = new Set(duplicateIndexes || []);
        rowStore.forEach((row, index) => {
            if (dupSet.has(index)) {
                row.rowResult = DUPLICATE_KEY_ROW_MSG;
                row.rowResultType = 'warning';
                row.__search = null;
            } else if (row.rowResult === DUPLICATE_KEY_ROW_MSG && row.rowResultType === 'warning') {
                row.rowResult = '';
                row.rowResultType = '';
                row.__search = null;
            }
        });
    }

    function buildRowSearchText(row) {
        if (row.__search) return row.__search;
        const raw = [
            row.code,
            row.subject,
            row.titleP,
            row.titleE,
            row.project,
            row.mdr,
            row.phase,
            row.disc,
            row.pkg,
            row.block,
            row.level,
            row.revision,
            row.status,
            row.pdfName,
            row.nativeName,
            row.rowResult,
        ].join(' ');
        row.__search = raw.toLowerCase();
        return row.__search;
    }

    function normalizeFilterQuery(value) {
        return String(value || '').toLowerCase().trim();
    }

    function refreshFilterIndexes(resetScroll = false) {
        const query = normalizeFilterQuery(activeFilterQuery);
        const tableScroll = document.getElementById('tableScroll');

        if (!query) {
            filteredIndexes = null;
        } else {
            const hits = [];
            for (let i = 0; i < rowStore.length; i++) {
                if (buildRowSearchText(rowStore[i]).includes(query)) hits.push(i);
            }
            filteredIndexes = hits;
        }

        if (resetScroll && tableScroll) tableScroll.scrollTop = 0;
        updateFilterStats();
    }

    function scheduleFilterRefresh(resetScroll = false) {
        clearTimeout(filterTimer);
        filterTimer = setTimeout(() => {
            refreshFilterIndexes(resetScroll);
            renderRows(true);
            updateCount();
        }, FILTER_DEBOUNCE_MS);
    }

    function updateFilterStats() {
        const el = document.getElementById('filterStats');
        if (!el) return;
        const total = rowStore.length;
        const showing = filteredIndexes ? filteredIndexes.length : total;
        if (activeFilterQuery) {
            el.textContent = `Showing ${showing} / ${total}`;
        } else {
            el.textContent = '';
        }
    }

    function getActiveRowIndexes() {
        return filteredIndexes || null;
    }

    function handleQuickFilterInput(event) {
        activeFilterQuery = event?.target?.value || '';
        scheduleFilterRefresh(true);
    }

    function clearQuickFilter() {
        const input = document.getElementById('quickFilterInput');
        if (input) input.value = '';
        activeFilterQuery = '';
        refreshFilterIndexes(true);
        renderRows(true);
        updateCount();
    }

    function jumpToRow() {
        const jumpInput = document.getElementById('jumpRowInput');
        const tableScroll = document.getElementById('tableScroll');
        if (!jumpInput || !tableScroll) return;

        const n = Number(jumpInput.value);
        const active = getActiveRowIndexes();
        const visibleTotal = active ? active.length : rowStore.length;
        if (visibleTotal === 0) {
            showBanner('No visible rows to jump to.', 'warning');
            return;
        }

        if (!Number.isInteger(n) || n < 1 || n > visibleTotal) {
            showBanner(`Row number must be between 1 and ${visibleTotal}.`, 'warning');
            return;
        }

        const visibleIndex = n - 1;
        tableScroll.scrollTop = visibleIndex * VIRTUAL_ROW_HEIGHT;
        renderRows(true);

        const dataIndex = active ? active[visibleIndex] : visibleIndex;
        requestAnimationFrame(() => {
            const tr = document.querySelector(`tr[data-row-index="${dataIndex}"]`);
            if (tr) {
                tr.classList.add('jump-highlight');
                setTimeout(() => tr.classList.remove('jump-highlight'), 1100);
            }
        });
    }

    function applyValidationToRowElement(tr, row) {
        if (!tr) return;
        const requiredMap = [
            ['.data-project', !!row.project],
            ['.data-mdr', !!row.mdr],
            ['.data-phase', !!row.phase],
            ['.data-disc', !!row.disc],
            ['.data-pkg', !!row.pkg],
            ['.data-block', !!row.block],
            ['.data-level', !!row.level],
        ];

        requiredMap.forEach(([selector, valid]) => {
            const el = tr.querySelector(selector);
            if (el) el.classList.toggle('input-invalid', !valid);
        });

        tr.classList.toggle('row-invalid', !rowIsValidData(row));
    }

    function renderDataRow(row, index, activeIndex) {
        const projOpts = buildOptions(dictData.projects, 'code', 'project_name', row.project);
        const mdrOpts = buildOptions(dictData.mdr_categories, 'code', 'name', row.mdr);
        const phaseOpts = buildOptions(dictData.phases, 'ph_code', 'name_e', row.phase);
        const discOpts = buildOptions(dictData.disciplines, 'code', 'name_e', row.disc);
        const pkgOpts = buildPackageOptions(row.disc, row.pkg);
        const blkOpts = dictData.blocks ? buildOptions(dictData.blocks, 'code', 'code', row.block) : '<option value="G">G</option>';
        const lvlOpts = dictData.levels ? buildOptions(dictData.levels, 'code', 'code', row.level) : '<option value="GEN">GEN</option>';
        const statusOpts = buildSimpleOptions(DOC_STATUS_OPTIONS, row.status || 'Registered');
        const hasFiles = hasAttachedFiles(row);
        const revisionLabel = hasFiles ? 'AUTO' : '-';
        const statusDisabled = hasFiles ? '' : 'disabled';

        const resultType = String(row.rowResultType || '').trim().toLowerCase();
        const resultClass = resultType ? ` ${resultType}` : '';
        const resultTitle = String(row.rowResult || '').trim();

        return `
            <tr data-row-index="${index}" data-active-index="${activeIndex}" class="${rowIsValidData(row) ? '' : 'row-invalid'}">
                <td>
                    <div class="doc-code-cell">
                        <input type="text" class="data-input data-code" value="${escapeHtml(row.code)}" readonly>
                    </div>
                </td>
                <td><input type="text" class="data-input data-title-p" value="${escapeHtml(row.titleP)}" readonly></td>
                <td><input type="text" class="data-input data-title-e" value="${escapeHtml(row.titleE)}" readonly></td>
                <td><input type="text" class="data-input data-subject" list="subjectSuggestionsList" value="${escapeHtml(row.subject)}"></td>
                <td>
                    <input type="file" class="data-file-input data-pdf-file" accept=".pdf,application/pdf">
                    <div class="file-attach-name" title="${escapeHtml(row.pdfName || '')}">${escapeHtml(row.pdfName || '')}</div>
                </td>
                <td>
                    <input type="file" class="data-file-input data-native-file">
                    <div class="file-attach-name" title="${escapeHtml(row.nativeName || '')}">${escapeHtml(row.nativeName || '')}</div>
                </td>
                <td><input type="text" class="data-input data-revision" value="${revisionLabel}" readonly></td>
                <td><select class="data-input data-doc-status" ${statusDisabled}>${statusOpts}</select></td>
                <td><select class="data-input data-project${row.project ? '' : ' input-invalid'}">${projOpts}</select></td>
                <td><select class="data-input data-mdr${row.mdr ? '' : ' input-invalid'}">${mdrOpts}</select></td>
                <td><select class="data-input data-phase${row.phase ? '' : ' input-invalid'}">${phaseOpts}</select></td>
                <td><select class="data-input data-disc${row.disc ? '' : ' input-invalid'}">${discOpts}</select></td>
                <td><select class="data-input data-pkg${row.pkg ? '' : ' input-invalid'}">${pkgOpts}</select></td>
                <td><select class="data-input data-block${row.block ? '' : ' input-invalid'}">${blkOpts}</select></td>
                <td><select class="data-input data-level${row.level ? '' : ' input-invalid'}">${lvlOpts}</select></td>
                <td><div class="row-result${resultClass}" title="${escapeHtml(resultTitle)}">${escapeHtml(resultTitle)}</div></td>
                <td>
                    <div class="row-actions">
                        <button class="btn btn-secondary" type="button" data-row-action="clone" data-row-index="${index}" style="padding:2px 6px;" title="Clone row">
                            <span class="material-icons-round" style="font-size:14px;">content_copy</span>
                        </button>
                        <button class="btn btn-danger" type="button" data-row-action="remove" data-row-index="${index}" style="padding:2px 6px;" title="Delete row">
                            <span class="material-icons-round" style="font-size:14px;">delete</span>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }

    function renderRows(force = false) {
        const tbody = document.getElementById('tableBody');
        const tableScroll = document.getElementById('tableScroll');
        if (!tbody) return;

        const activeIndexes = getActiveRowIndexes();
        const total = activeIndexes ? activeIndexes.length : rowStore.length;
        virtualEnabled = total > VIRTUAL_THRESHOLD;

        if (!total) {
            tbody.innerHTML = '';
            lastVirtualStart = -1;
            lastVirtualEnd = -1;
            requestAnimationFrame(postFrameHeight);
            return;
        }

        if (!virtualEnabled) {
            if (!force && lastVirtualStart === 0 && lastVirtualEnd === total) return;
            if (activeIndexes) {
                tbody.innerHTML = activeIndexes
                    .map((rowIndex, activePos) => renderDataRow(rowStore[rowIndex], rowIndex, activePos))
                    .join('');
            } else {
                tbody.innerHTML = rowStore
                    .map((row, idx) => renderDataRow(row, idx, idx))
                    .join('');
            }
            lastVirtualStart = 0;
            lastVirtualEnd = total;
            requestAnimationFrame(postFrameHeight);
            return;
        }

        if (!tableScroll) {
            if (activeIndexes) {
                tbody.innerHTML = activeIndexes
                    .map((rowIndex, activePos) => renderDataRow(rowStore[rowIndex], rowIndex, activePos))
                    .join('');
            } else {
                tbody.innerHTML = rowStore
                    .map((row, idx) => renderDataRow(row, idx, idx))
                    .join('');
            }
            return;
        }

        const viewportRows = Math.ceil((tableScroll.clientHeight || 420) / VIRTUAL_ROW_HEIGHT);
        const scrollTop = tableScroll.scrollTop;
        const start = Math.max(0, Math.floor(scrollTop / VIRTUAL_ROW_HEIGHT) - VIRTUAL_OVERSCAN);
        const end = Math.min(total, start + viewportRows + (VIRTUAL_OVERSCAN * 2));

        if (!force && start === lastVirtualStart && end === lastVirtualEnd) return;
        lastVirtualStart = start;
        lastVirtualEnd = end;

        const topHeight = start * VIRTUAL_ROW_HEIGHT;
        const bottomHeight = (total - end) * VIRTUAL_ROW_HEIGHT;

        let visibleRows = '';
        if (activeIndexes) {
            for (let activePos = start; activePos < end; activePos++) {
                const rowIndex = activeIndexes[activePos];
                visibleRows += renderDataRow(rowStore[rowIndex], rowIndex, activePos);
            }
        } else {
            for (let activePos = start; activePos < end; activePos++) {
                visibleRows += renderDataRow(rowStore[activePos], activePos, activePos);
            }
        }

        tbody.innerHTML = `
            <tr class="virtual-gap"><td colspan="17" style="height:${topHeight}px; border:none; padding:0;"></td></tr>
            ${visibleRows}
            <tr class="virtual-gap"><td colspan="17" style="height:${bottomHeight}px; border:none; padding:0;"></td></tr>
        `;
        requestAnimationFrame(postFrameHeight);
    }

    async function populateTable(rows) {
        const cappedRows = Array.isArray(rows) ? rows.slice(0, MAX_CLIENT_ROWS) : [];
        if (Array.isArray(rows) && rows.length > MAX_CLIENT_ROWS) {
            showBanner(`Preview was limited to ${MAX_CLIENT_ROWS} rows. Please split larger files.`, 'warning');
        }

        rowStore = [];
        const total = cappedRows.length;
        for (let i = 0; i < total; i += RENDER_BATCH_SIZE) {
            const slice = cappedRows.slice(i, i + RENDER_BATCH_SIZE);
            rowStore.push(...slice.map((r) => normalizeRowInput(r)));
            if (total > RENDER_BATCH_SIZE) {
                const rendered = Math.min(i + slice.length, total);
                setProgress(78 + Math.round((rendered / total) * 20), `Rendering preview ${rendered}/${total}`);
            }
            await new Promise((resolve) => requestAnimationFrame(resolve));
        }

        rebuildAutoCodes();
        document.getElementById('tableWrapper').style.display = rowStore.length ? 'block' : 'none';
        refreshFilterIndexes(true);
        renderRows(true);
        updateCount();
        validateTable();
        saveDraftNow();
    }

    function addTableRow(data = {}, options = {}) {
        rowStore.push(normalizeRowInput(data, options));
        rebuildAutoCodes();
        if (activeFilterQuery) refreshFilterIndexes(false);
        document.getElementById('tableWrapper').style.display = 'block';
        renderRows(true);
        updateCount();
    }

    function addManualRow() {
        addTableRow({}, { useDefaults: false });
        const scroller = document.getElementById('tableScroll');
        if (scroller) {
            requestAnimationFrame(() => {
                scroller.scrollTop = scroller.scrollHeight;
                renderRows(true);
            });
        }
        scheduleDraftSave();
    }

    function removeRowByIndex(index) {
        if (!Number.isInteger(index) || index < 0 || index >= rowStore.length) return;
        rowStore.splice(index, 1);
        rebuildAutoCodes();
        if (activeFilterQuery) refreshFilterIndexes(false);
        renderRows(true);
        updateCount();
        scheduleDraftSave();
    }

    function cloneRowByIndex(index) {
        if (!Number.isInteger(index) || index < 0 || index >= rowStore.length) return;
        const source = rowStore[index];
        if (!source) return;

        const cloned = normalizeRowInput({
            project: source.project,
            mdr: source.mdr,
            phase: source.phase,
            disc: source.disc,
            pkg: source.pkg,
            block: source.block,
            level: source.level,
            subject: source.subject,
            status: source.status,
            providedCode: false,
            code: '',
        }, { useDefaults: false });

        rowStore.splice(index + 1, 0, cloned);
        rebuildAutoCodes();
        if (activeFilterQuery) refreshFilterIndexes(false);
        renderRows(true);
        updateCount();
        scheduleDraftSave();
    }

    function removeRow(btn) {
        const tr = btn?.closest?.('tr[data-row-index]');
        if (!tr) return;
        const idx = Number(tr.dataset.rowIndex);
        removeRowByIndex(idx);
    }

    function updatePkgOptions(discSelect) {
        const tr = discSelect?.closest?.('tr[data-row-index]');
        if (!tr) return;
        const idx = Number(tr.dataset.rowIndex);
        if (!Number.isInteger(idx) || !rowStore[idx]) return;

        rowStore[idx].disc = discSelect.value || '';
        if (!rowStore[idx].pkg || !((dictData.packages || []).some((p) => p.discipline_code === rowStore[idx].disc && p.package_code === rowStore[idx].pkg))) {
            rowStore[idx].pkg = getDefaultPkgForDisc(rowStore[idx].disc);
        }

        const pkgSelect = tr.querySelector('.data-pkg');
        if (pkgSelect) {
            pkgSelect.innerHTML = buildPackageOptions(rowStore[idx].disc, rowStore[idx].pkg);
            pkgSelect.value = rowStore[idx].pkg;
        }

        rowStore[idx].__search = null;
        rebuildAutoCodes();
        refreshAutoTitlesForRow(rowStore[idx]);
        syncComputedInputsForRow(tr, rowStore[idx]);
        applyValidationToRowElement(tr, rowStore[idx]);
        if (activeFilterQuery) scheduleFilterRefresh(false);
        scheduleDraftSave();
    }

    function updateRowDefaults() {
        // Deprecated: manual global project/MDR selectors removed by design.
        return;
    }

    function setStatus(msg, color) {
        const el = document.getElementById('fileStatus');
        if (!el) return;
        el.innerText = msg;
        el.style.color = color;
    }

    function syncRowFromElement(tr) {
        const idx = Number(tr.dataset.rowIndex);
        if (!Number.isInteger(idx) || !rowStore[idx]) return;

        rowStore[idx].project = tr.querySelector('.data-project')?.value || '';
        rowStore[idx].mdr = tr.querySelector('.data-mdr')?.value || '';
        rowStore[idx].phase = tr.querySelector('.data-phase')?.value || '';
        rowStore[idx].disc = tr.querySelector('.data-disc')?.value || '';
        rowStore[idx].pkg = tr.querySelector('.data-pkg')?.value || '';
        rowStore[idx].block = tr.querySelector('.data-block')?.value || '';
        rowStore[idx].level = tr.querySelector('.data-level')?.value || '';
        const statusEl = tr.querySelector('.data-doc-status');
        if (statusEl && !statusEl.disabled) {
            rowStore[idx].status = statusEl.value || 'Registered';
        }

        const subjectEl = tr.querySelector('.data-subject');
        rowStore[idx].subject = subjectEl ? String(subjectEl.value || '').trim() : '';
        rowStore[idx].rowResult = '';
        rowStore[idx].rowResultType = '';

        rebuildAutoCodes();
        refreshAutoTitlesForRow(rowStore[idx]);
        syncComputedInputsForRow(tr, rowStore[idx]);
        rowStore[idx].__search = null;
        applyValidationToRowElement(tr, rowStore[idx]);
        if (activeFilterQuery) scheduleFilterRefresh(false);
    }

    function bindTableEvents() {
        const tbody = document.getElementById('tableBody');
        if (tbody && tbody.dataset.bound !== '1') {
            tbody.dataset.bound = '1';
            tbody.addEventListener('input', onTableFieldChange);
            tbody.addEventListener('change', onTableFieldChange);
            tbody.addEventListener('focusin', onTableFocusIn);
            tbody.addEventListener('click', (event) => {
                const rowBtn = event.target.closest('[data-row-action][data-row-index]');
                if (!rowBtn || !tbody.contains(rowBtn)) return;
                event.preventDefault();
                const action = String(rowBtn.getAttribute('data-row-action') || '').trim().toLowerCase();
                const idx = Number(rowBtn.getAttribute('data-row-index'));
                if (!Number.isInteger(idx)) return;
                if (action === 'clone') {
                    cloneRowByIndex(idx);
                    return;
                }
                if (action === 'remove') {
                    removeRowByIndex(idx);
                }
            });
        }

        const tableScroll = document.getElementById('tableScroll');
        if (tableScroll && tableScroll.dataset.bound !== '1') {
            tableScroll.dataset.bound = '1';
            tableScroll.addEventListener('scroll', () => {
                if (virtualEnabled) renderRows();
            }, { passive: true });
        }

        const jumpInput = document.getElementById('jumpRowInput');
        if (jumpInput && jumpInput.dataset.bound !== '1') {
            jumpInput.dataset.bound = '1';
            jumpInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    jumpToRow();
                }
            });
        }
    }

    function onTableFocusIn(event) {
        const tr = event.target.closest('tr[data-row-index]');
        if (!tr) return;
        if (event.target.classList.contains('data-subject')) {
            updateSubjectSuggestions(tr, event.target.value || '');
        }
    }

    function onTableFieldChange(event) {
        const tr = event.target.closest('tr[data-row-index]');
        if (!tr) return;
        const idx = Number(tr.dataset.rowIndex);
        if (!Number.isInteger(idx) || !rowStore[idx]) return;

        if (event.target.classList.contains('data-pdf-file')) {
            const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
            rowStore[idx].pdfFile = file;
            rowStore[idx].pdfName = file ? String(file.name || '') : '';
            rowStore[idx].rowResult = '';
            rowStore[idx].rowResultType = '';
            rowStore[idx].__search = null;
            const nameEl = tr.querySelector('.file-attach-name');
            if (nameEl) {
                nameEl.textContent = rowStore[idx].pdfName || '';
                nameEl.title = rowStore[idx].pdfName || '';
            }
            refreshArchiveControlsForRow(tr, rowStore[idx]);
            if (activeFilterQuery) scheduleFilterRefresh(false);
            scheduleDraftSave();
            return;
        }
        if (event.target.classList.contains('data-native-file')) {
            const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
            rowStore[idx].nativeFile = file;
            rowStore[idx].nativeName = file ? String(file.name || '') : '';
            rowStore[idx].rowResult = '';
            rowStore[idx].rowResultType = '';
            rowStore[idx].__search = null;
            const nameEl = tr.querySelectorAll('.file-attach-name')[1];
            if (nameEl) {
                nameEl.textContent = rowStore[idx].nativeName || '';
                nameEl.title = rowStore[idx].nativeName || '';
            }
            refreshArchiveControlsForRow(tr, rowStore[idx]);
            if (activeFilterQuery) scheduleFilterRefresh(false);
            scheduleDraftSave();
            return;
        }

        if (event.target.classList.contains('data-disc')) {
            updatePkgOptions(event.target);
            syncRowFromElement(tr);
        } else if (event.target.classList.contains('data-subject')) {
            syncRowFromElement(tr);
            updateSubjectSuggestions(tr, event.target.value || '');
        } else {
            syncRowFromElement(tr);
        }

        scheduleDraftSave();
    }

    function validateTable(showErrors = false) {
        const invalidIndexes = [];
        rowStore.forEach((row, index) => {
            if (!rowIsValidData(row)) invalidIndexes.push(index);
        });
        const duplicateIndexes = collectDuplicateKeyRowIndexes();
        applyDuplicateRowFlags(duplicateIndexes);
        if (showErrors && invalidIndexes.length > 0) {
            showBanner(`${invalidIndexes.length} row(s) are invalid. Complete required fields before submit.`, 'warning');
            renderRows(true);
        } else if (showErrors && duplicateIndexes.length > 0) {
            const preview = duplicateIndexes.slice(0, 12).map((i) => i + 1).join(', ');
            const more = duplicateIndexes.length > 12 ? ` ... (+${duplicateIndexes.length - 12})` : '';
            showBanner(`Duplicate rows detected by key fields. Fix rows: ${preview}${more}`, 'warning');
            renderRows(true);
        }
        return {
            invalidCount: invalidIndexes.length,
            duplicateIndexes,
        };
    }

    function collectRows() {
        return rowStore.map(({ __search, ...row }) => ({ ...row }));
    }

    function collectRowsForDraft() {
        return rowStore.map((row) => ({
            code: row.code,
            providedCode: !!row.providedCode,
            subject: row.subject,
            titleP: row.titleP,
            titleE: row.titleE,
            project: row.project,
            mdr: row.mdr,
            phase: row.phase,
            disc: row.disc,
            pkg: row.pkg,
            block: row.block,
            level: row.level,
            revision: row.revision,
            status: row.status,
        }));
    }

    function scheduleDraftSave() {
        clearTimeout(draftTimer);
        draftTimer = setTimeout(() => saveDraftNow(), DRAFT_DEBOUNCE_MS);
    }

    function saveDraftNow(showMessage = false) {
        const rows = collectRowsForDraft();
        const activeTab = document.querySelector('.tab.active')?.dataset?.bulkTab || 'excel';
        const payload = {
            rows,
            activeTab,
            updatedAt: Date.now(),
        };

        if (!rows.length) {
            localStorage.removeItem(DRAFT_KEY);
            return;
        }

        try {
            localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
            if (showMessage) showBanner('Draft saved locally.', 'info');
        } catch (e) {
            console.error('Draft save error', e);
            if (showMessage) showBanner('Could not save draft in local storage.', 'warning');
        }
    }

    function clearDraft(showMessage = true, clearRows = true) {
        localStorage.removeItem(DRAFT_KEY);
        if (clearRows) {
            clearTable(false);
        }
        if (showMessage) showBanner(clearRows ? 'Draft and table cleared.' : 'Draft cleared.', 'info');
    }

    function tryRestoreDraft() {
        const raw = localStorage.getItem(DRAFT_KEY);
        if (!raw) return;

        let draft;
        try {
            draft = JSON.parse(raw);
        } catch (_) {
            localStorage.removeItem(DRAFT_KEY);
            return;
        }

        if (!draft || !Array.isArray(draft.rows) || !draft.rows.length) return;
        const shouldRestore = confirm(`Found local draft (${draft.rows.length} rows). Restore it?`);
        if (!shouldRestore) return;

        rowStore = draft.rows.slice(0, MAX_CLIENT_ROWS).map((row) => normalizeRowInput({
            doc_number: row.code,
            provided_code: row.providedCode,
            title_p: row.titleP,
            title_e: row.titleE,
            subject: row.subject,
            project: row.project,
            mdr: row.mdr,
            phase: row.phase,
            disc: row.disc,
            pkg: row.pkg,
            block: row.block,
            level: row.level,
            revision: row.revision,
            status: row.status,
        }));

        document.getElementById('tableWrapper').style.display = rowStore.length ? 'block' : 'none';
        refreshFilterIndexes(true);
        renderRows(true);
        updateCount();
        const tab = ['excel', 'link', 'manual'].includes(draft.activeTab) ? draft.activeTab : 'excel';
        switchTab(null, tab);
        showBanner('Draft restored successfully.', 'success');
    }

    function clearTable(clearDraftStorage = true) {
        rowStore = [];
        filteredIndexes = null;
        activeFilterQuery = '';
        const quickFilterInput = document.getElementById('quickFilterInput');
        if (quickFilterInput) quickFilterInput.value = '';
        const jumpRowInput = document.getElementById('jumpRowInput');
        if (jumpRowInput) jumpRowInput.value = '';
        renderRows(true);
        updateCount();
        document.getElementById('tableWrapper').style.display = 'none';
        if (clearDraftStorage) clearDraft(false, false);
    }

    function updateCount() {
        const total = rowStore.length;
        const visible = filteredIndexes ? filteredIndexes.length : total;
        const badgeText = activeFilterQuery ? `${visible}/${total} rows` : `${total} rows`;
        document.getElementById('recordCount').innerText = badgeText;
        if (total === 0) document.getElementById('tableWrapper').style.display = 'none';
        updateFilterStats();
        requestAnimationFrame(postFrameHeight);
    }

    function hasAttachedFiles(row) {
        return !!(row && (row.pdfFile instanceof File || row.nativeFile instanceof File));
    }

    function applyChunkResultToRows(chunkRows, result) {
        const statsDetails = Array.isArray(result?.stats?.details) ? result.stats.details : [];
        const uploadDetails = Array.isArray(result?.uploads?.details) ? result.uploads.details : [];
        const uploadByRow = new Map();
        uploadDetails.forEach((item) => {
            const idx = Number(item?.row_index);
            if (Number.isInteger(idx) && idx >= 0) uploadByRow.set(idx, item);
        });

        for (let i = 0; i < chunkRows.length; i++) {
            const row = chunkRows[i];
            if (!row) continue;

            const docItem = statsDetails[i] || {};
            const docStatusRaw = String(docItem?.status || '');
            const docStatus = docStatusRaw || 'Pending';
            const docMsg = String(docItem?.msg || '').trim();
            const uploadItem = uploadByRow.get(i);
            const uploadStatus = String(uploadItem?.status || '').trim();
            const uploadMsg = String(uploadItem?.message || '').trim();

            let text = '';
            let type = 'success';
            if (uploadItem) {
                text = `Doc: ${docStatus} | Upload: ${uploadStatus}`;
                if (uploadMsg) text += ` - ${uploadMsg}`;
            } else if (hasAttachedFiles(row)) {
                text = `Doc: ${docStatus} | Upload: Pending`;
                type = 'warning';
            } else {
                text = `Doc: ${docStatus}`;
                if (docMsg) text += ` - ${docMsg}`;
            }

            const docStatusNorm = docStatus.toLowerCase();
            const uploadStatusNorm = uploadStatus.toLowerCase();
            const hasError = docStatusNorm === 'failed' || uploadStatusNorm === 'failed';
            const hasWarn = !hasError && (
                docStatusNorm === 'skipped' ||
                uploadStatusNorm === 'skipped' ||
                uploadStatusNorm === 'pending'
            );
            if (hasError) type = 'error';
            else if (hasWarn) type = 'warning';
            else type = 'success';

            row.rowResult = text;
            row.rowResultType = type;
            row.__search = null;
        }
    }

    // --- Submit ---
    async function submitFinal() {
        const rows = rowStore;
        if (!rows.length) {
            showBanner('Table is empty. Add or import rows first.', 'warning');
            return;
        }

        const validation = validateTable(true);
        if ((validation?.invalidCount || 0) > 0) return;
        const duplicateIndexes = Array.isArray(validation?.duplicateIndexes) ? validation.duplicateIndexes : [];
        const duplicateSet = new Set(duplicateIndexes);
        const submitRows = rows.filter((_, idx) => !duplicateSet.has(idx));
        if (!submitRows.length) {
            showBanner('No submittable rows found. Resolve warning rows and try again.', 'warning');
            return;
        }

        const btn = document.getElementById('btnSubmit');
        const originalHtml = btn.innerHTML;
        btn.innerHTML = `<span class="loader" style="width:14px; height:14px; border-width:2px;"></span> Sending...`;
        btn.disabled = true;

        setProgress(15, 'Preparing payload...');

        const toSubmitRow = (r) => {
            const willArchive = hasAttachedFiles(r);
            return {
                project: r.project || 'T202',
                mdr: r.mdr || 'E',
                phase: r.phase || 'X',
                disc: r.disc || 'GN',
                pkg: r.pkg || '00',
                block: r.block || 'G',
                level: r.level || 'GEN',
                subject: r.subject || '',
                titleP: r.titleP || '',
                titleE: r.titleE || '',
                code: r.providedCode ? (r.code || '') : '',
                providedCode: !!r.providedCode,
                revision: '',
                status: willArchive ? (String(r.status || 'Registered').trim() || 'Registered') : '',
            };
        };

        const chunks = [];
        for (let i = 0; i < submitRows.length; i += BULK_SUBMIT_CHUNK_SIZE) {
            chunks.push(submitRows.slice(i, i + BULK_SUBMIT_CHUNK_SIZE));
        }
        rows.forEach((row, idx) => {
            if (duplicateSet.has(idx)) {
                row.rowResult = DUPLICATE_KEY_ROW_MSG;
                row.rowResultType = 'warning';
            } else {
                row.rowResult = '';
                row.rowResultType = '';
            }
            row.__search = null;
        });
        renderRows(true);

        try {
            let aggSuccess = 0;
            let aggFailed = 0;
            let aggTotal = 0;
            let aggUploaded = 0;
            let aggUploadFailed = 0;
            let aggUploadSkipped = 0;

            if (duplicateSet.size > 0) {
                showBanner(`${duplicateSet.size} warning row(s) were kept and not submitted.`, 'warning');
            }

            for (let idx = 0; idx < chunks.length; idx++) {
                const chunkRows = chunks[idx];
                const payloadRows = chunkRows.map(toSubmitRow);
                const formData = new FormData();
                formData.append('rows_json', JSON.stringify(payloadRows));
                formData.append('revision', 'AUTO');
                formData.append('status', String(chunkRows[0]?.status || 'Registered').trim() || 'Registered');

                const manifest = [];
                let fileIndex = 0;
                for (let rowIndex = 0; rowIndex < chunkRows.length; rowIndex++) {
                    const row = chunkRows[rowIndex];
                    if (row.pdfFile instanceof File) {
                        formData.append('files', row.pdfFile, row.pdfFile.name);
                        manifest.push({ row_index: rowIndex, file_index: fileIndex, kind: 'pdf' });
                        fileIndex += 1;
                    }
                    if (row.nativeFile instanceof File) {
                        formData.append('files', row.nativeFile, row.nativeFile.name);
                        manifest.push({ row_index: rowIndex, file_index: fileIndex, kind: 'native' });
                        fileIndex += 1;
                    }
                }
                formData.append('files_manifest', JSON.stringify(manifest));

                const progressBase = 20 + Math.round((idx / chunks.length) * 70);
                setProgress(progressBase, `Submitting chunk ${idx + 1}/${chunks.length}...`);

                const res = await fetchWithAuth('/api/v1/mdr/bulk-register-with-files', {
                    method: 'POST',
                    body: formData
                }, 300000);

                const result = await res.json().catch(() => ({}));
                if (!res.ok || !result.ok) {
                    const msg = result.detail || result.message || extractErrorMessage(res, `Chunk ${idx + 1} failed.`);
                    throw new Error(msg);
                }

                aggSuccess += result?.stats?.success ?? 0;
                aggFailed += result?.stats?.failed ?? 0;
                aggTotal += result?.stats?.total ?? chunkRows.length;
                aggUploaded += result?.uploads?.uploaded ?? 0;
                aggUploadFailed += result?.uploads?.failed ?? 0;
                aggUploadSkipped += result?.uploads?.skipped ?? 0;
                applyChunkResultToRows(chunkRows, result);
                renderRows(true);
            }

            setProgress(100, 'Done');
            const hasUploadIssues = aggUploadFailed > 0;
            const msg = `Bulk completed. Docs: ${aggSuccess} success, ${aggFailed} failed, ${aggTotal} total. Files: ${aggUploaded} uploaded, ${aggUploadFailed} failed, ${aggUploadSkipped} skipped.`;
            showBanner(msg, (aggFailed || hasUploadIssues) ? 'warning' : 'success');
            setStatus(msg, (aggFailed || hasUploadIssues) ? 'orange' : 'green');
            const beforeCount = rowStore.length;
            rowStore = rowStore.filter((row) => String(row?.rowResultType || '').toLowerCase() !== 'success');
            const removedCount = beforeCount - rowStore.length;
            if (removedCount > 0) {
                if (activeFilterQuery) refreshFilterIndexes(false);
                renderRows(true);
                updateCount();
            }
            if (rowStore.length === 0) clearTable(true);
            else saveDraftNow();
        } catch (e) {
            console.error(e);
            showBanner(e.message || 'Network error during bulk submit.', 'error');
        } finally {
            setTimeout(hideProgress, 700);
            btn.innerHTML = originalHtml;
            btn.disabled = false;
            renderRows(true);
        }
    }

export {};
