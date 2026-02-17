// @ts-nocheck
(() => {
    const API_BASE = '/api/v1/settings';
    const ENTITIES = ['projects', 'mdr', 'phases', 'disciplines', 'packages', 'blocks', 'levels', 'statuses', 'corr_issuing', 'corr_categories'];

    const STORE = {
        initialized: false,
        loadingPromise: null,
        storagePathsLoaded: false,
        storagePolicyLoaded: false,
        storageIntegrationsLoaded: false,
        siteCacheLoaded: false,
        actionsBound: false,
        activePage: 'db_sync',
        activeDomain: 'common',
        storageWizard: {
            activeStep: 'paths',
            dirty: {
                paths: false,
                policy: false,
                integrations: false,
            },
        },
        data: {
            projects: [],
            mdr: [],
            phases: [],
            disciplines: [],
            packages: [],
            blocks: [],
            levels: [],
            statuses: [],
            corr_issuing: [],
            corr_categories: [],
        },
        siteCache: {
            profiles: [],
            activeProfileId: 0,
        },
        paging: {},
    };

    ENTITIES.forEach((name) => {
        STORE.paging[name] = { search: '', page: 1, pageSize: 10 };
    });

    const LIST_META = {
        projects: { url: '/projects', tbodyId: 'settingsProjectsRows', pagerId: 'projectsPager', colspan: 4 },
        mdr: { url: '/mdr-categories', tbodyId: 'settingsMdrRows', pagerId: 'mdrPager', colspan: 4 },
        phases: { url: '/phases', tbodyId: 'settingsPhasesRows', pagerId: 'phasesPager', colspan: 4 },
        disciplines: { url: '/disciplines', tbodyId: 'settingsDisciplinesRows', pagerId: 'disciplinesPager', colspan: 4 },
        packages: { url: '/packages', tbodyId: 'settingsPackagesRows', pagerId: 'packagesPager', colspan: 5 },
        blocks: { url: '/blocks', tbodyId: 'settingsBlocksRows', pagerId: 'blocksPager', colspan: 5 },
        levels: { url: '/levels', tbodyId: 'settingsLevelsRows', pagerId: 'levelsPager', colspan: 5 },
        statuses: { url: '/statuses', tbodyId: 'settingsStatusesRows', pagerId: 'statusesPager', colspan: 5 },
        corr_issuing: { url: '/correspondence-issuing', tbodyId: 'settingsCorrIssuingRows', pagerId: 'corrIssuingPager', colspan: 5 },
        corr_categories: { url: '/correspondence-categories', tbodyId: 'settingsCorrCategoriesRows', pagerId: 'corrCategoriesPager', colspan: 5 },
    };

    const STORAGE_WIZARD_STEPS = ['paths', 'policy', 'integrations'];
    const STORAGE_POLICY_DEFAULT_ALLOWED_MIMES = [
        'application/pdf',
        'image/png',
        'image/jpeg',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/zip',
    ];
    const STORAGE_POLICY_DEFAULT_BLOCKED = ['exe', 'bat', 'cmd', 'ps1', 'js', 'vbs', 'sh'];
    const STORAGE_POLICY_PRESETS = {
        warning: {
            enforcement_mode: 'warning',
            blocked_extensions: STORAGE_POLICY_DEFAULT_BLOCKED,
            allowed_mimes: STORAGE_POLICY_DEFAULT_ALLOWED_MIMES,
            max_size_mb: { pdf: 100, native: 250, attachment: 100 },
        },
        standard: {
            enforcement_mode: 'enforce',
            blocked_extensions: STORAGE_POLICY_DEFAULT_BLOCKED,
            allowed_mimes: STORAGE_POLICY_DEFAULT_ALLOWED_MIMES,
            max_size_mb: { pdf: 100, native: 250, attachment: 100 },
        },
        strict: {
            enforcement_mode: 'enforce',
            blocked_extensions: STORAGE_POLICY_DEFAULT_BLOCKED.concat(['zip']),
            allowed_mimes: ['application/pdf', 'image/png', 'image/jpeg'],
            max_size_mb: { pdf: 50, native: 150, attachment: 50 },
        },
    };
    const SITE_CACHE_CODE_RE = /^[A-Z0-9_-]{2,64}$/;
    const SITE_CACHE_PROJECT_CODE_RE = /^[A-Z0-9_-]{1,50}$/;
    const SITE_CACHE_DISCIPLINE_CODE_RE = /^[A-Z0-9_-]{1,20}$/;
    const SITE_CACHE_PACKAGE_CODE_RE = /^[A-Z0-9_-]{1,30}$/;
    const SITE_CACHE_STATUS_CODE_RE = /^[A-Z0-9_-]{1,20}$/;
    const SITE_CACHE_ALL_VALUE = '__ALL__';

    function tSuccess(msg) { if (window.UI?.success) window.UI.success(msg); else alert(msg); }
    function tError(msg) { if (window.UI?.error) window.UI.error(msg); else alert(msg); }
    function norm(v) { return String(v ?? '').trim(); }
    function esc(v) {
        return String(v ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function encoded(v) { return encodeURIComponent(String(v ?? '')); }
    function decoded(v) { return decodeURIComponent(String(v ?? '')); }

    function boolBadge(value) {
        return value
            ? '<span class="status-badge active">فعال</span>'
            : '<span class="status-badge inactive">غیرفعال</span>';
    }

    function setLoadingRows(entity, message = 'در حال بارگذاری...') {
        const meta = LIST_META[entity];
        const tbody = document.getElementById(meta.tbodyId);
        if (!tbody) return;
        tbody.innerHTML = `<tr><td class="text-center muted" colspan="${meta.colspan}">${esc(message)}</td></tr>`;
    }

    function entitySearchText(entity, row) {
        switch (entity) {
            case 'projects':
                return `${row.code} ${row.project_name || ''} ${row.root_path || ''}`;
            case 'mdr':
                return `${row.code} ${row.name_e || ''} ${row.name_p || ''}`;
            case 'phases':
                return `${row.ph_code || ''} ${row.name_e || ''} ${row.name_p || ''}`;
            case 'disciplines':
                return `${row.code || ''} ${row.name_e || ''} ${row.name_p || ''}`;
            case 'packages':
                return `${row.discipline_code || ''} ${row.package_code || ''} ${row.name_e || ''} ${row.name_p || ''}`;
            case 'blocks':
                return `${row.project_code || ''} ${row.code || ''} ${row.name_e || ''} ${row.name_p || ''}`;
            case 'levels':
                return `${row.code || ''} ${row.name_e || ''} ${row.name_p || ''}`;
            case 'statuses':
                return `${row.code || ''} ${row.name || ''} ${row.description || ''}`;
            case 'corr_issuing':
                return `${row.code || ''} ${row.name_e || ''} ${row.name_p || ''} ${row.project_code || ''}`;
            case 'corr_categories':
                return `${row.code || ''} ${row.name_e || ''} ${row.name_p || ''}`;
            default:
                return JSON.stringify(row || {});
        }
    }

    function getFilteredAndPaged(entity) {
        const state = STORE.paging[entity];
        const all = STORE.data[entity] || [];
        const q = norm(state.search).toLowerCase();
        const filtered = q
            ? all.filter((item) => entitySearchText(entity, item).toLowerCase().includes(q))
            : all.slice();

        const pageSize = Math.max(1, Number(state.pageSize) || 10);
        const total = filtered.length;
        const totalPages = Math.max(1, Math.ceil(total / pageSize));
        const safePage = Math.min(Math.max(1, Number(state.page) || 1), totalPages);
        state.page = safePage;
        state.pageSize = pageSize;

        const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
        const to = Math.min(total, safePage * pageSize);
        const rows = filtered.slice(from > 0 ? from - 1 : 0, to);
        return { total, totalPages, page: safePage, from, to, rows };
    }

    function renderPager(entity, info) {
        const pager = document.getElementById(LIST_META[entity].pagerId);
        if (!pager) return;
        pager.innerHTML = `
            <div class="general-pager-left">نمایش ${info.from}-${info.to} از ${info.total}</div>
            <div class="general-pager-right">
                <button class="btn-archive-icon" type="button" ${info.page <= 1 ? 'disabled' : ''} data-general-action="goto-page" data-entity="${esc(entity)}" data-page="${info.page - 1}">قبلی</button>
                <span>صفحه ${info.page} از ${info.totalPages}</span>
                <button class="btn-archive-icon" type="button" ${info.page >= info.totalPages ? 'disabled' : ''} data-general-action="goto-page" data-entity="${esc(entity)}" data-page="${info.page + 1}">بعدی</button>
            </div>
        `;
    }

    function rowActions(inner) {
        return `<div class="general-row-actions">${inner}</div>`;
    }

    function renderEntity(entity) {
        const meta = LIST_META[entity];
        const tbody = document.getElementById(meta.tbodyId);
        if (!tbody) return;

        const info = getFilteredAndPaged(entity);
        if (!info.rows.length) {
            tbody.innerHTML = `<tr><td class="text-center muted" colspan="${meta.colspan}">موردی یافت نشد</td></tr>`;
            renderPager(entity, info);
            return;
        }

        let html = '';
        if (entity === 'projects') {
            html = info.rows.map((p) => `
                <tr>
                    <td>${esc(p.code)}</td>
                    <td>${esc(p.project_name || p.name_e || '-')}</td>
                    <td>${boolBadge(Boolean(p.is_active))}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-project" data-code="${esc(encoded(p.code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-project" data-code="${esc(encoded(p.code))}">غیرفعال</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'mdr') {
            html = info.rows.map((m) => `
                <tr>
                    <td>${esc(m.code)}</td>
                    <td>${esc(m.name_e || m.name_p || '-')}</td>
                    <td>${boolBadge(Boolean(m.is_active))}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-mdr" data-code="${esc(encoded(m.code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-mdr" data-code="${esc(encoded(m.code))}">غیرفعال</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'phases') {
            html = info.rows.map((p) => `
                <tr>
                    <td>${esc(p.ph_code)}</td>
                    <td>${esc(p.name_e || '-')}</td>
                    <td>${esc(p.name_p || '-')}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-phase" data-code="${esc(encoded(p.ph_code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-phase" data-code="${esc(encoded(p.ph_code))}">حذف</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'disciplines') {
            html = info.rows.map((d) => `
                <tr>
                    <td>${esc(d.code)}</td>
                    <td>${esc(d.name_e || '-')}</td>
                    <td>${esc(d.name_p || '-')}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-discipline" data-code="${esc(encoded(d.code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-discipline" data-code="${esc(encoded(d.code))}">حذف</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'packages') {
            html = info.rows.map((p) => `
                <tr>
                    <td>${esc(p.discipline_code)}</td>
                    <td>${esc(p.package_code)}</td>
                    <td>${esc(p.name_e || '-')}</td>
                    <td>${esc(p.name_p || '-')}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-package" data-discipline-code="${esc(encoded(p.discipline_code))}" data-package-code="${esc(encoded(p.package_code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-package" data-discipline-code="${esc(encoded(p.discipline_code))}" data-package-code="${esc(encoded(p.package_code))}">حذف</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'blocks') {
            html = info.rows.map((b) => `
                <tr>
                    <td>${esc(b.project_code)}</td>
                    <td>${esc(b.code)}</td>
                    <td>${esc(b.name_e || b.name_p || '-')}</td>
                    <td>${boolBadge(Boolean(b.is_active))}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-block" data-project-code="${esc(encoded(b.project_code))}" data-code="${esc(encoded(b.code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-block" data-project-code="${esc(encoded(b.project_code))}" data-code="${esc(encoded(b.code))}">غیرفعال</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'levels') {
            html = info.rows.map((l) => `
                <tr>
                    <td>${esc(l.code)}</td>
                    <td>${esc(l.name_e || '-')}</td>
                    <td>${esc(l.name_p || '-')}</td>
                    <td>${esc(l.sort_order ?? 0)}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-level" data-code="${esc(encoded(l.code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-level" data-code="${esc(encoded(l.code))}">حذف</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'statuses') {
            html = info.rows.map((s) => `
                <tr>
                    <td>${esc(s.code)}</td>
                    <td>${esc(s.name || '-')}</td>
                    <td>${esc(s.description || '-')}</td>
                    <td>${esc(s.sort_order ?? 0)}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-status" data-code="${esc(encoded(s.code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-status" data-code="${esc(encoded(s.code))}">حذف</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'corr_issuing') {
            html = info.rows.map((s) => `
                <tr>
                    <td>${esc(s.code)}</td>
                    <td>${esc(s.name_e || s.name_p || '-')}</td>
                    <td>${esc(s.project_code || '-')}</td>
                    <td>${boolBadge(Boolean(s.is_active))}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-corr-issuing" data-code="${esc(encoded(s.code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-corr-issuing" data-code="${esc(encoded(s.code))}">غیرفعال</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'corr_categories') {
            html = info.rows.map((s) => `
                <tr>
                    <td>${esc(s.code)}</td>
                    <td>${esc(s.name_e || s.name_p || '-')}</td>
                    <td>${boolBadge(Boolean(s.is_active))}</td>
                    <td>${esc(s.sort_order ?? 0)}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-corr-category" data-code="${esc(encoded(s.code))}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-corr-category" data-code="${esc(encoded(s.code))}">غیرفعال</button>
                    `)}</td>
                </tr>
            `).join('');
        }

        tbody.innerHTML = html;
        renderPager(entity, info);
    }

    async function request(url, options = {}) {
        const fn = typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : fetch;
        const res = await fn(url, options);
        if (!res.ok) {
            let message = `درخواست ناموفق بود (${res.status})`;
            try {
                const j = await res.clone().json();
                message = j.detail || j.message || message;
            } catch (_) {
                try { message = await res.text(); } catch (_) {}
            }
            throw new Error(message);
        }
        return res.json();
    }

    function responseItems(payload) {
        if (Array.isArray(payload)) return payload;
        if (Array.isArray(payload?.items)) return payload.items;
        if (Array.isArray(payload?.data)) return payload.data;
        return [];
    }

    async function loadEntity(entity, force = false) {
        if (!LIST_META[entity]) return;
        if (!force && STORE.data[entity].length) {
            renderEntity(entity);
            return;
        }
        setLoadingRows(entity);
        const payload = await request(`${API_BASE}${LIST_META[entity].url}`);
        STORE.data[entity] = responseItems(payload);
        renderEntity(entity);
    }

    function fillSelect(selectId, rows, labelFn, valueFn) {
        const el = document.getElementById(selectId);
        if (!el) return;
        const prev = el.value;
        const options = rows.map((r) => `<option value="${esc(valueFn(r))}">${esc(labelFn(r))}</option>`).join('');
        el.innerHTML = options;
        if (prev && rows.some((r) => String(valueFn(r)) === prev)) el.value = prev;
    }

    function refreshProjectCards() {
        const box = document.getElementById('tbl-projects');
        if (!box) return;
        const items = STORE.data.projects || [];
        if (!items.length) {
            box.innerHTML = '<div class="text-muted">پروژه‌ای ثبت نشده است.</div>';
            return;
        }
        box.innerHTML = items.map((p) => `
            <div class="general-project-card">
                <div class="general-project-code">${esc(p.code)}</div>
                <div class="general-project-name">${esc(p.project_name || '-')}</div>
            </div>
        `).join('');
    }

    async function loadOverview() {
        const box = document.getElementById('settingsOverviewStats');
        if (!box) return;
        box.innerHTML = '<div class="text-muted">در حال بارگذاری...</div>';
        const data = await request(`${API_BASE}/overview`);
        const counts = data.counts || {};
        const cards = [
            ['projects', 'پروژه'],
            ['mdr_categories', 'MDR'],
            ['phases', 'فاز'],
            ['disciplines', 'دیسیپلین'],
            ['packages', 'پکیج'],
            ['blocks', 'بلوک'],
            ['levels', 'سطح'],
            ['statuses', 'وضعیت'],
            ['issuing_entities', 'مرجع صدور'],
            ['correspondence_categories', 'دسته مکاتبات'],
        ];
        box.innerHTML = cards.map(([k, label]) => `
            <div class="general-overview-card">
                <div class="general-overview-value">${Number(counts[k] || 0)}</div>
                <div class="general-overview-label">${label}</div>
            </div>
        `).join('');
    }

    function refreshTransmittalConfigSummary() {
        const box = document.getElementById('transmittalConfigSummary');
        if (!box) return;
        const cards = [
            ['projects', 'پروژه'],
            ['mdr', 'MDR'],
            ['phases', 'فاز'],
            ['disciplines', 'دیسیپلین'],
            ['statuses', 'وضعیت'],
        ];
        box.innerHTML = cards.map(([entity, label]) => `
            <div class="general-overview-card">
                <div class="general-overview-value">${Number((STORE.data[entity] || []).length || 0)}</div>
                <div class="general-overview-label">${label}</div>
            </div>
        `).join('');
    }

    function formatFaDateTime(now = new Date()) {
        try {
            return now.toLocaleString('fa-IR');
        } catch (err) {
            return now.toLocaleString();
        }
    }

    function markStorageStepDirty(step) {
        if (!STORAGE_WIZARD_STEPS.includes(step)) return;
        STORE.storageWizard.dirty[step] = true;
        updateStorageActionBarState();
    }

    function clearStorageStepDirty(step) {
        if (!STORAGE_WIZARD_STEPS.includes(step)) return;
        STORE.storageWizard.dirty[step] = false;
        updateStorageActionBarState();
    }

    function updateStoragePathPreview() {
        const mdrInput = document.getElementById('mdrStoragePathInput');
        const corrInput = document.getElementById('correspondenceStoragePathInput');
        const mdrPreview = document.getElementById('storagePathMdrPreview');
        const corrPreview = document.getElementById('storagePathCorrespondencePreview');
        if (mdrPreview && mdrInput) {
            mdrPreview.textContent = normalizeStoragePathForCompare(mdrInput.value) || '-';
        }
        if (corrPreview && corrInput) {
            corrPreview.textContent = normalizeStoragePathForCompare(corrInput.value) || '-';
        }
    }

    function showStorageStepSaved(step, message) {
        if (step !== 'paths') return;
        const note = document.getElementById('storagePathsSavedNote');
        const ts = document.getElementById('storagePathsLastSavedAt');
        if (note) {
            note.textContent = message;
            note.style.display = 'block';
        }
        if (ts) {
            ts.textContent = formatFaDateTime();
        }
    }

    function hideStorageStepSaved(step) {
        if (step !== 'paths') return;
        const note = document.getElementById('storagePathsSavedNote');
        if (note) {
            note.textContent = '';
            note.style.display = 'none';
        }
    }

    function updateStorageActionBarState() {
        const step = STORE.storageWizard.activeStep || 'paths';
        const idx = STORAGE_WIZARD_STEPS.indexOf(step);
        const prevBtn = document.querySelector('[data-general-action="storage-step-prev"]');
        const nextBtn = document.querySelector('[data-general-action="storage-step-next"]');
        const saveBtn = document.querySelector('[data-general-action="storage-save-current"]');
        if (prevBtn) prevBtn.disabled = idx <= 0;
        if (nextBtn) nextBtn.disabled = idx < 0 || idx >= STORAGE_WIZARD_STEPS.length - 1;
        if (saveBtn) {
            const dirty = Boolean(STORE.storageWizard.dirty[step]);
            saveBtn.textContent = dirty ? 'ذخیره مرحله جاری *' : 'ذخیره مرحله جاری';
        }
    }

    function setStorageWizardStep(step, opts = {}) {
        const targetStep = STORAGE_WIZARD_STEPS.includes(step) ? step : 'paths';
        const force = Boolean(opts.force);
        const currentStep = STORE.storageWizard.activeStep || 'paths';
        if (!force && currentStep !== targetStep && STORE.storageWizard.dirty[currentStep]) {
            const ok = confirm('تغییرات این مرحله ذخیره نشده است. آیا مایل به تغییر مرحله هستید؟');
            if (!ok) return false;
        }
        STORE.storageWizard.activeStep = targetStep;

        document.querySelectorAll('[data-storage-step-panel]').forEach((panel) => {
            const isActive = String(panel?.dataset?.storageStepPanel || '') === targetStep;
            panel.classList.toggle('active', isActive);
        });

        document.querySelectorAll('.storage-step-btn[data-storage-step]').forEach((btn) => {
            const isActive = String(btn?.dataset?.storageStep || '') === targetStep;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        updateStorageActionBarState();
        return true;
    }

    function moveStorageWizardStep(direction) {
        const currentStep = STORE.storageWizard.activeStep || 'paths';
        const idx = STORAGE_WIZARD_STEPS.indexOf(currentStep);
        if (idx < 0) return;
        const nextIndex = Math.max(0, Math.min(STORAGE_WIZARD_STEPS.length - 1, idx + Number(direction || 0)));
        setStorageWizardStep(STORAGE_WIZARD_STEPS[nextIndex]);
    }

    async function saveCurrentStorageWizardStep() {
        const step = STORE.storageWizard.activeStep || 'paths';
        if (step === 'paths') {
            await window.saveStoragePaths();
            return;
        }
        if (step === 'policy') {
            await window.saveStoragePolicySettings();
            return;
        }
        if (step === 'integrations') {
            await window.saveStorageIntegrationsSettings();
            return;
        }
    }

    function updateStorageIntegrationsFieldState() {
        const gdriveEnabled = document.getElementById('storageGoogleDriveEnabledInput');
        const openprojectEnabled = document.getElementById('storageOpenProjectEnabledInput');
        const openprojectWp = document.getElementById('storageOpenProjectDefaultWpInput');
        const gdriveDriveId = document.getElementById('storageGoogleDriveDriveIdInput');
        const openprojectWrap = document.getElementById('storageOpenProjectDefaultWpWrap');
        const gdriveWrap = document.getElementById('storageGoogleDriveDriveIdWrap');
        const openprojectSyncBtn = document.getElementById('storageOpenProjectSyncRunBtn');
        const gdriveSyncBtn = document.getElementById('storageGoogleDriveSyncRunBtn');

        const gdriveOn = Boolean(gdriveEnabled?.checked);
        const openprojectOn = Boolean(openprojectEnabled?.checked);

        if (gdriveDriveId) gdriveDriveId.disabled = !gdriveOn;
        if (openprojectWp) openprojectWp.disabled = !openprojectOn;
        if (gdriveWrap) gdriveWrap.classList.toggle('is-disabled', !gdriveOn);
        if (openprojectWrap) openprojectWrap.classList.toggle('is-disabled', !openprojectOn);
        if (gdriveSyncBtn) gdriveSyncBtn.disabled = !gdriveOn;
        if (openprojectSyncBtn) openprojectSyncBtn.disabled = !openprojectOn;
    }

    function bindStorageWorkflowInputs() {
        const root = document.getElementById('storageWorkflowRoot');
        if (!root || root.dataset.storageWorkflowBound === '1') return;

        root.addEventListener('input', (event) => {
            const target = event?.target;
            if (!target) return;
            if (target.closest('#storage-step-paths')) {
                markStorageStepDirty('paths');
                hideStorageStepSaved('paths');
                updateStoragePathPreview();
            } else if (target.closest('#storage-step-policy')) {
                markStorageStepDirty('policy');
            } else if (target.closest('#storage-step-integrations')) {
                markStorageStepDirty('integrations');
            }
        });

        root.addEventListener('change', (event) => {
            const target = event?.target;
            if (!target) return;
            if (target.closest('#storage-step-integrations')) {
                markStorageStepDirty('integrations');
                updateStorageIntegrationsFieldState();
            }
        });

        root.dataset.storageWorkflowBound = '1';
    }

    function setStoragePolicyPresetActive(name = '') {
        const key = String(name || '').trim().toLowerCase();
        document.querySelectorAll('.storage-preset-btn[data-storage-preset]').forEach((btn) => {
            const btnKey = String(btn?.dataset?.storagePreset || '').trim().toLowerCase();
            btn.classList.toggle('active', key && key === btnKey);
        });
    }

    function applyStoragePolicyPreset(name) {
        const key = String(name || '').trim().toLowerCase();
        const preset = STORAGE_POLICY_PRESETS[key] || STORAGE_POLICY_PRESETS.standard;
        applyStoragePolicyToForm(preset);
        setStoragePolicyPresetActive(key);
        markStorageStepDirty('policy');
    }

    async function loadStoragePaths(force = false) {
        const mdrInput = document.getElementById('mdrStoragePathInput');
        const corrInput = document.getElementById('correspondenceStoragePathInput');
        if (!mdrInput || !corrInput) return;
        bindStoragePathValidation();
        if (STORE.storagePathsLoaded && !force) return;

        const payload = await request(`${API_BASE}/storage-paths`);
        const mdrLocked = mdrInput.dataset.storagePathDirty === '1' || document.activeElement === mdrInput;
        const corrLocked = corrInput.dataset.storagePathDirty === '1' || document.activeElement === corrInput;
        if (!mdrLocked) {
            mdrInput.value = norm(payload?.mdr_storage_path);
        }
        if (!corrLocked) {
            corrInput.value = norm(payload?.correspondence_storage_path);
        }
        updateStoragePathPreview();
        validateStoragePathConflict(false);
        if (!mdrLocked && !corrLocked) {
            clearStorageStepDirty('paths');
        }
        STORE.storagePathsLoaded = true;
    }

    function parseCommaSeparatedList(value) {
        return String(value || '')
            .split(/[\n,]+/g)
            .map((item) => String(item || '').trim())
            .filter(Boolean);
    }

    function parsePositiveNumber(value, label, fallback = null) {
        const raw = String(value ?? '').trim();
        if (!raw) return fallback;
        const n = Number(raw);
        if (!Number.isFinite(n) || n <= 0) {
            throw new Error(`${label} باید عدد مثبت باشد.`);
        }
        return Math.round(n);
    }

    function toStorageMaxSizeMap(policy = {}) {
        const maxSize = policy?.max_size_mb && typeof policy.max_size_mb === 'object' ? policy.max_size_mb : {};
        const pdf = Number(maxSize.pdf ?? maxSize.PDF ?? 0);
        const native = Number(maxSize.native ?? maxSize.NATIVE ?? 0);
        const attachment = Number(maxSize.attachment ?? maxSize.ATTACHMENT ?? 0);
        return {
            pdf: Number.isFinite(pdf) && pdf > 0 ? Math.round(pdf) : '',
            native: Number.isFinite(native) && native > 0 ? Math.round(native) : '',
            attachment: Number.isFinite(attachment) && attachment > 0 ? Math.round(attachment) : '',
        };
    }

    function setStorageSyncResult(message = '', level = 'info') {
        const box = document.getElementById('storageSyncResult');
        if (!box) return;
        if (!message) {
            box.textContent = '';
            box.style.display = 'none';
            box.classList.remove('storage-sync-result-success', 'storage-sync-result-error', 'storage-sync-result-info');
            return;
        }
        box.textContent = message;
        box.style.display = 'block';
        box.classList.remove('storage-sync-result-success', 'storage-sync-result-error', 'storage-sync-result-info');
        if (level === 'success') box.classList.add('storage-sync-result-success');
        else if (level === 'error') box.classList.add('storage-sync-result-error');
        else box.classList.add('storage-sync-result-info');
    }

    function applyStoragePolicyToForm(policy = {}) {
        const modeInput = document.getElementById('storagePolicyModeInput');
        const blockedInput = document.getElementById('storageBlockedExtensionsInput');
        const allowedInput = document.getElementById('storageAllowedMimesInput');
        const pdfInput = document.getElementById('storageMaxSizePdfInput');
        const nativeInput = document.getElementById('storageMaxSizeNativeInput');
        const attachmentInput = document.getElementById('storageMaxSizeAttachmentInput');
        const maxSize = toStorageMaxSizeMap(policy);
        if (modeInput) modeInput.value = String(policy?.enforcement_mode || 'warning');
        if (blockedInput) blockedInput.value = Array.isArray(policy?.blocked_extensions) ? policy.blocked_extensions.join(',') : '';
        if (allowedInput) allowedInput.value = Array.isArray(policy?.allowed_mimes) ? policy.allowed_mimes.join(',') : '';
        if (pdfInput) pdfInput.value = String(maxSize.pdf);
        if (nativeInput) nativeInput.value = String(maxSize.native);
        if (attachmentInput) attachmentInput.value = String(maxSize.attachment);
    }

    async function loadStoragePolicy(force = false) {
        const modeInput = document.getElementById('storagePolicyModeInput');
        if (!modeInput) return;
        if (STORE.storagePolicyLoaded && !force) return;
        const payload = await request(`${API_BASE}/storage-policy`);
        applyStoragePolicyToForm(payload?.policy || {});
        setStoragePolicyPresetActive('');
        clearStorageStepDirty('policy');
        STORE.storagePolicyLoaded = true;
    }

    async function saveStoragePolicy() {
        const modeInput = document.getElementById('storagePolicyModeInput');
        const blockedInput = document.getElementById('storageBlockedExtensionsInput');
        const allowedInput = document.getElementById('storageAllowedMimesInput');
        const pdfInput = document.getElementById('storageMaxSizePdfInput');
        const nativeInput = document.getElementById('storageMaxSizeNativeInput');
        const attachmentInput = document.getElementById('storageMaxSizeAttachmentInput');
        if (!modeInput || !blockedInput || !allowedInput || !pdfInput || !nativeInput || !attachmentInput) return;

        const enforcement_mode = String(modeInput.value || 'warning').trim().toLowerCase() === 'enforce' ? 'enforce' : 'warning';
        const blocked_extensions = parseCommaSeparatedList(blockedInput.value);
        const allowed_mimes = parseCommaSeparatedList(allowedInput.value).map((v) => v.toLowerCase());
        const max_size_mb = {
            pdf: parsePositiveNumber(pdfInput.value, 'حداکثر حجم PDF', 100),
            native: parsePositiveNumber(nativeInput.value, 'حداکثر حجم Native', 250),
            attachment: parsePositiveNumber(attachmentInput.value, 'حداکثر حجم Attachment', 100),
        };

        const payload = await request(`${API_BASE}/storage-policy`, {
            method: 'POST',
            body: JSON.stringify({
                enforcement_mode,
                blocked_extensions,
                allowed_mimes,
                max_size_mb,
            }),
        });
        applyStoragePolicyToForm(payload?.policy || {});
        STORE.storagePolicyLoaded = true;
        clearStorageStepDirty('policy');
        setStorageSyncResult('');
        tSuccess('سیاست اعتبارسنجی فایل ذخیره شد.');
    }

    function applyStorageIntegrationsToForm(integrations = {}) {
        const gdriveEnabled = document.getElementById('storageGoogleDriveEnabledInput');
        const openprojectEnabled = document.getElementById('storageOpenProjectEnabledInput');
        const localCacheEnabled = document.getElementById('storageLocalCacheEnabledInput');
        const openprojectWp = document.getElementById('storageOpenProjectDefaultWpInput');
        const gdriveDriveId = document.getElementById('storageGoogleDriveDriveIdInput');

        const gdrive = integrations?.google_drive || {};
        const openproject = integrations?.openproject || {};
        const localCache = integrations?.local_cache || {};

        if (gdriveEnabled) gdriveEnabled.checked = Boolean(gdrive.enabled);
        if (openprojectEnabled) openprojectEnabled.checked = Boolean(openproject.enabled);
        if (localCacheEnabled) localCacheEnabled.checked = Boolean(localCache.enabled);
        if (openprojectWp) openprojectWp.value = String(openproject.default_project_id || '');
        if (gdriveDriveId) gdriveDriveId.value = String(gdrive.shared_drive_id || '');
        updateStorageIntegrationsFieldState();
    }

    async function loadStorageIntegrations(force = false) {
        const gdriveEnabled = document.getElementById('storageGoogleDriveEnabledInput');
        if (!gdriveEnabled) return;
        if (STORE.storageIntegrationsLoaded && !force) return;
        const payload = await request(`${API_BASE}/storage-integrations`);
        applyStorageIntegrationsToForm(payload?.integrations || {});
        clearStorageStepDirty('integrations');
        STORE.storageIntegrationsLoaded = true;
    }

    async function saveStorageIntegrations() {
        const gdriveEnabled = document.getElementById('storageGoogleDriveEnabledInput');
        const openprojectEnabled = document.getElementById('storageOpenProjectEnabledInput');
        const localCacheEnabled = document.getElementById('storageLocalCacheEnabledInput');
        const openprojectWp = document.getElementById('storageOpenProjectDefaultWpInput');
        const gdriveDriveId = document.getElementById('storageGoogleDriveDriveIdInput');
        if (!gdriveEnabled || !openprojectEnabled || !localCacheEnabled || !openprojectWp || !gdriveDriveId) return;

        const payload = await request(`${API_BASE}/storage-integrations`, {
            method: 'POST',
            body: JSON.stringify({
                google_drive: {
                    enabled: Boolean(gdriveEnabled.checked),
                    shared_drive_id: norm(gdriveDriveId.value),
                },
                openproject: {
                    enabled: Boolean(openprojectEnabled.checked),
                    default_project_id: norm(openprojectWp.value),
                },
                local_cache: {
                    enabled: Boolean(localCacheEnabled.checked),
                },
            }),
        });
        applyStorageIntegrationsToForm(payload?.integrations || {});
        STORE.storageIntegrationsLoaded = true;
        clearStorageStepDirty('integrations');
        setStorageSyncResult('');
        tSuccess('تنظیمات یکپارچه‌سازی ذخیره شد.');
    }

    async function runStorageSyncJob(kind) {
        const endpoint = kind === 'openproject'
            ? '/api/v1/storage/sync/openproject/run'
            : '/api/v1/storage/sync/google-drive/run';
        const title = kind === 'openproject' ? 'OpenProject' : 'Google Drive';
        setStorageSyncResult(`در حال اجرای Sync ${title} ...`, 'info');
        const payload = await request(endpoint, { method: 'POST' });
        const processed = Number(payload?.processed || 0);
        const succeeded = Number(payload?.success || payload?.succeeded || 0);
        const failed = Number(payload?.failed || 0);
        const dead = Number(payload?.dead || 0);
        const summary = `نتیجه Sync ${title}: پردازش=${processed}، موفق=${succeeded}، خطا=${failed}، صف‌معیوب=${dead}`;
        setStorageSyncResult(summary, failed > 0 || dead > 0 ? 'error' : 'success');
        if (failed > 0 || dead > 0) {
            tError(`${summary}. جزئیات در پنل نتیجه نمایش داده شد.`);
            return;
        }
        tSuccess(summary);
    }

    function setSiteCacheTokenMessage(message = '', level = 'info') {
        const box = document.getElementById('siteCacheTokenPlain');
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

    function getActiveSiteCacheProfileId() {
        const selected = Number(document.getElementById('siteCacheProfileSelect')?.value || STORE.siteCache.activeProfileId || 0);
        if (!selected) {
            throw new Error('ابتدا یک پروفایل سایت انتخاب کنید.');
        }
        return selected;
    }

    function normalizeSiteCacheProfileCode(value) {
        const code = norm(value).toUpperCase();
        requireVal(code, 'کد سایت');
        if (!SITE_CACHE_CODE_RE.test(code)) {
            throw new Error('کد سایت فقط می‌تواند شامل حروف انگلیسی، عدد، `_` و `-` باشد (حداقل ۲ کاراکتر).');
        }
        return code;
    }

    function normalizeOptionalSiteCode(value, label, regex, maxLength) {
        const code = norm(value).toUpperCase();
        if (!code) return null;
        if (code.length > maxLength) {
            throw new Error(`${label} نباید بیشتر از ${maxLength} کاراکتر باشد.`);
        }
        if (!regex.test(code)) {
            throw new Error(`${label} فقط می‌تواند شامل حروف انگلیسی، عدد، '_' و '-' باشد.`);
        }
        return code;
    }

    function normalizeSiteCacheRootPath(value) {
        const path = norm(value);
        if (!path) return null;
        if (path.length > 1024) {
            throw new Error('مسیر ریشه محلی نباید بیشتر از ۱۰۲۴ کاراکتر باشد.');
        }
        return path;
    }

    function normalizeSiteCacheFallbackMode(value) {
        const mode = norm(value).toLowerCase() || 'local_first';
        if (!['local_first', 'hq_first'].includes(mode)) {
            throw new Error('حالت fallback معتبر نیست.');
        }
        return mode;
    }

    function normalizeSiteCacheRuleName(value) {
        const name = norm(value);
        requireVal(name, 'نام قانون');
        if (name.length > 255) {
            throw new Error('نام قانون نباید بیشتر از ۲۵۵ کاراکتر باشد.');
        }
        return name;
    }

    function parseSiteCacheStatusCodes(value) {
        const items = parseCommaSeparatedList(String(value || '').toUpperCase());
        const dedup = [];
        for (const raw of items) {
            const code = norm(raw).toUpperCase();
            if (!code) continue;
            if (!SITE_CACHE_STATUS_CODE_RE.test(code)) {
                throw new Error(`کد وضعیت نامعتبر است: ${code}`);
            }
            if (!dedup.includes(code)) dedup.push(code);
        }
        return dedup.length ? dedup.join(',') : 'IFA,IFC';
    }

    function parseSiteCachePriority(value) {
        const raw = String(value ?? '').trim();
        if (!raw) return 100;
        const n = Number(raw);
        if (!Number.isInteger(n) || n < 0 || n > 10000) {
            throw new Error('اولویت باید یک عدد صحیح بین ۰ تا ۱۰۰۰۰ باشد.');
        }
        return n;
    }

    function validateIPv4Address(value) {
        const parts = String(value || '').split('.');
        if (parts.length !== 4) return false;
        return parts.every((part) => {
            if (!/^\d{1,3}$/.test(part)) return false;
            const num = Number(part);
            return Number.isInteger(num) && num >= 0 && num <= 255;
        });
    }

    function validateIPv6Address(value) {
        const ip = String(value || '').trim();
        if (!ip) return false;
        if (!/^[0-9a-fA-F:]+$/.test(ip)) return false;
        const segments = ip.split(':');
        if (segments.length < 3 || segments.length > 8) return false;
        let emptyCount = 0;
        for (const segment of segments) {
            if (segment === '') {
                emptyCount += 1;
                continue;
            }
            if (!/^[0-9a-fA-F]{1,4}$/.test(segment)) return false;
        }
        return emptyCount <= 2;
    }

    function normalizeSiteCacheCidr(value) {
        const raw = norm(value);
        requireVal(raw, 'CIDR');
        const slash = raw.indexOf('/');
        if (slash <= 0 || slash === raw.length - 1) {
            throw new Error('CIDR نامعتبر است. نمونه صحیح: 10.88.0.0/16');
        }
        const ip = raw.slice(0, slash).trim();
        const prefixRaw = raw.slice(slash + 1).trim();
        if (!/^\d{1,3}$/.test(prefixRaw)) {
            throw new Error('بخش Prefix در CIDR معتبر نیست.');
        }
        const prefix = Number(prefixRaw);
        if (ip.includes(':')) {
            if (!validateIPv6Address(ip) || prefix < 0 || prefix > 128) {
                throw new Error('CIDR IPv6 معتبر نیست.');
            }
            return `${ip}/${prefix}`;
        }
        if (!validateIPv4Address(ip) || prefix < 0 || prefix > 32) {
            throw new Error('CIDR IPv4 معتبر نیست.');
        }
        return `${ip}/${prefix}`;
    }

    function ensureInputValidity(inputEl, fallbackMessage) {
        if (!inputEl || typeof inputEl.checkValidity !== 'function') return;
        if (inputEl.checkValidity()) return;
        if (typeof inputEl.reportValidity === 'function') inputEl.reportValidity();
        throw new Error(fallbackMessage);
    }

    function toSiteCacheFilterCode(value, regex, label, maxLength) {
        const raw = norm(value).toUpperCase();
        if (!raw || raw === SITE_CACHE_ALL_VALUE) return null;
        if (raw.length > maxLength) {
            throw new Error(`${label} نباید بیشتر از ${maxLength} کاراکتر باشد.`);
        }
        if (!regex.test(raw)) {
            throw new Error(`${label} معتبر نیست.`);
        }
        return raw;
    }

    function getMultiSelectValues(selectEl) {
        if (!selectEl) return [];
        const options = Array.from(selectEl.selectedOptions || []);
        return options
            .map((opt) => norm(opt?.value).toUpperCase())
            .filter(Boolean);
    }

    function normalizeMultiSelectValues(values) {
        const normalized = [];
        (Array.isArray(values) ? values : []).forEach((item) => {
            const code = norm(item).toUpperCase();
            if (!code) return;
            if (!normalized.includes(code)) normalized.push(code);
        });
        if (!normalized.length) return [SITE_CACHE_ALL_VALUE];
        if (normalized.includes(SITE_CACHE_ALL_VALUE) && normalized.length > 1) {
            return normalized.filter((item) => item !== SITE_CACHE_ALL_VALUE);
        }
        return normalized;
    }

    function setMultiSelectValues(selectEl, values) {
        if (!selectEl) return;
        const target = normalizeMultiSelectValues(values);
        Array.from(selectEl.options || []).forEach((opt) => {
            const code = norm(opt?.value).toUpperCase();
            opt.selected = target.includes(code);
        });
    }

    function parseSiteCacheFilterCodes(selectEl, regex, label, maxLength) {
        const values = normalizeMultiSelectValues(getMultiSelectValues(selectEl));
        if (values.length === 1 && values[0] === SITE_CACHE_ALL_VALUE) return [null];
        const out = values
            .map((value) => toSiteCacheFilterCode(value, regex, label, maxLength))
            .filter(Boolean);
        return out.length ? out : [null];
    }

    function parseSiteCachePackageSelections(selectEl) {
        const values = normalizeMultiSelectValues(getMultiSelectValues(selectEl));
        if (values.length === 1 && values[0] === SITE_CACHE_ALL_VALUE) {
            return [{ discipline_code: null, package_code: null }];
        }
        const out = [];
        for (const value of values) {
            const raw = norm(value).toUpperCase();
            const sep = raw.indexOf('::');
            if (sep <= 0 || sep >= raw.length - 2) {
                throw new Error(`پکیج انتخاب‌شده معتبر نیست: ${raw || '-'}`);
            }
            const discipline_code = toSiteCacheFilterCode(raw.slice(0, sep), SITE_CACHE_DISCIPLINE_CODE_RE, 'کد دیسیپلین پکیج', 20);
            const package_code = toSiteCacheFilterCode(raw.slice(sep + 2), SITE_CACHE_PACKAGE_CODE_RE, 'کد پکیج', 30);
            if (!discipline_code || !package_code) continue;
            out.push({ discipline_code, package_code });
        }
        return out.length ? out : [{ discipline_code: null, package_code: null }];
    }

    function fillSiteCacheRulePackageOptions(selectedDisciplines = null, selectedPackages = null) {
        const packageSelect = document.getElementById('siteCacheRulePackageInput');
        if (!packageSelect) return;
        const disciplineSelect = document.getElementById('siteCacheRuleDisciplineInput');
        const selectedDisciplineValues = normalizeMultiSelectValues(
            Array.isArray(selectedDisciplines) ? selectedDisciplines : getMultiSelectValues(disciplineSelect)
        );
        const currentPackageValues = normalizeMultiSelectValues(
            Array.isArray(selectedPackages) ? selectedPackages : getMultiSelectValues(packageSelect)
        );
        const isAllDiscipline = selectedDisciplineValues.includes(SITE_CACHE_ALL_VALUE);
        const packageRows = (STORE.data.packages || [])
            .filter((row) => {
                if (isAllDiscipline) return true;
                const disc = norm(row?.discipline_code).toUpperCase();
                return selectedDisciplineValues.includes(disc);
            })
            .sort((a, b) => {
                const ad = String(a?.discipline_code || '');
                const bd = String(b?.discipline_code || '');
                if (ad !== bd) return ad.localeCompare(bd);
                return String(a?.package_code || '').localeCompare(String(b?.package_code || ''));
            });
        const options = [`<option value="${SITE_CACHE_ALL_VALUE}">همه پکیج‌ها</option>`]
            .concat(
                packageRows.map((row) => {
                    const disc = norm(row?.discipline_code).toUpperCase();
                    const code = norm(row?.package_code).toUpperCase();
                    const pair = `${disc}::${code}`;
                    const label = `${disc || '-'} / ${code || '-'} - ${norm(row?.name_e) || norm(row?.name_p) || '-'}`;
                    return `<option value="${esc(pair)}">${esc(label)}</option>`;
                })
            )
            .join('');
        packageSelect.innerHTML = options;
        const allowedValues = new Set(
            [SITE_CACHE_ALL_VALUE].concat(
                packageRows.map((row) => `${norm(row?.discipline_code).toUpperCase()}::${norm(row?.package_code).toUpperCase()}`)
            )
        );
        const nextValues = currentPackageValues.filter((value) => allowedValues.has(value));
        setMultiSelectValues(packageSelect, nextValues.length ? nextValues : [SITE_CACHE_ALL_VALUE]);
    }

    function fillSiteCacheRuleFilterOptions() {
        const projectSelect = document.getElementById('siteCacheRuleProjectInput');
        const disciplineSelect = document.getElementById('siteCacheRuleDisciplineInput');
        const packageSelect = document.getElementById('siteCacheRulePackageInput');
        if (!projectSelect || !disciplineSelect || !packageSelect) return;
        const currentProject = normalizeMultiSelectValues(getMultiSelectValues(projectSelect));
        const currentDiscipline = normalizeMultiSelectValues(getMultiSelectValues(disciplineSelect));
        const currentPackage = normalizeMultiSelectValues(getMultiSelectValues(packageSelect));
        const projectOptions = [`<option value="${SITE_CACHE_ALL_VALUE}">همه پروژه‌ها</option>`]
            .concat(
                (STORE.data.projects || []).map((row) => {
                    const code = norm(row?.code).toUpperCase();
                    const label = `${code || '-'} - ${norm(row?.project_name) || '-'}`;
                    return `<option value="${esc(code)}">${esc(label)}</option>`;
                })
            )
            .join('');
        const disciplineOptions = [`<option value="${SITE_CACHE_ALL_VALUE}">همه دیسیپلین‌ها</option>`]
            .concat(
                (STORE.data.disciplines || []).map((row) => {
                    const code = norm(row?.code).toUpperCase();
                    const label = `${code || '-'} - ${norm(row?.name_e) || norm(row?.name_p) || '-'}`;
                    return `<option value="${esc(code)}">${esc(label)}</option>`;
                })
            )
            .join('');
        projectSelect.innerHTML = projectOptions;
        disciplineSelect.innerHTML = disciplineOptions;
        const validProjects = [SITE_CACHE_ALL_VALUE].concat((STORE.data.projects || []).map((row) => norm(row?.code).toUpperCase()));
        const validDisciplines = [SITE_CACHE_ALL_VALUE].concat((STORE.data.disciplines || []).map((row) => norm(row?.code).toUpperCase()));
        setMultiSelectValues(projectSelect, currentProject.filter((code) => validProjects.includes(code)));
        setMultiSelectValues(disciplineSelect, currentDiscipline.filter((code) => validDisciplines.includes(code)));
        fillSiteCacheRulePackageOptions(getMultiSelectValues(disciplineSelect), currentPackage);
    }

    function currentSiteCacheProfile() {
        const activeId = Number(STORE.siteCache.activeProfileId || 0);
        return (STORE.siteCache.profiles || []).find((item) => Number(item?.id || 0) === activeId) || null;
    }

    function renderSiteCacheProfiles() {
        const tbody = document.getElementById('settingsSiteCacheProfilesRows');
        const profileSelect = document.getElementById('siteCacheProfileSelect');
        if (!tbody || !profileSelect) return;
        const profiles = Array.isArray(STORE.siteCache.profiles) ? STORE.siteCache.profiles : [];
        if (!profiles.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center muted">هیچ پروفایل سایتی ثبت نشده است.</td></tr>';
            profileSelect.innerHTML = '<option value="">انتخاب پروفایل سایت</option>';
            return;
        }

        if (!STORE.siteCache.activeProfileId || !profiles.some((item) => Number(item?.id || 0) === Number(STORE.siteCache.activeProfileId || 0))) {
            STORE.siteCache.activeProfileId = Number(profiles[0]?.id || 0);
        }

        tbody.innerHTML = profiles.map((item) => {
            const pid = Number(item?.id || 0);
            return `
                <tr>
                    <td>${esc(item?.code || '-')}</td>
                    <td>${esc(item?.name || '-')}</td>
                    <td>${esc(item?.project_code || '-')}</td>
                    <td>${boolBadge(Boolean(item?.is_active))}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-site-cache-profile" data-profile-id="${pid}">ویرایش</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-site-cache-profile" data-profile-id="${pid}">غیرفعال</button>
                    `)}</td>
                </tr>
            `;
        }).join('');

        profileSelect.innerHTML = profiles
            .map((item) => `<option value="${Number(item?.id || 0)}">${esc(`${item?.code || '-'} - ${item?.name || '-'}`)}</option>`)
            .join('');
        profileSelect.value = String(STORE.siteCache.activeProfileId || '');
    }

    function renderSiteCacheProfileDetails(profile) {
        const cidrBox = document.getElementById('settingsSiteCacheCidrsRows');
        const ruleBox = document.getElementById('settingsSiteCacheRulesRows');
        const tokenBox = document.getElementById('settingsSiteCacheTokensRows');
        if (!cidrBox || !ruleBox || !tokenBox) return;

        const cidrs = Array.isArray(profile?.cidrs) ? profile.cidrs : [];
        const rules = Array.isArray(profile?.rules) ? profile.rules : [];

        cidrBox.innerHTML = cidrs.length
            ? cidrs.map((item) => `
                <div class="general-inline-chip">
                    <span class="material-icons-round">network_check</span>
                    <span>${esc(item?.cidr || '-')}</span>
                    <button type="button" data-general-action="delete-site-cache-cidr" data-cidr-id="${Number(item?.id || 0)}" title="حذف CIDR">
                        <span class="material-icons-round">close</span>
                    </button>
                </div>
            `).join('')
            : '<div class="text-muted">CIDR ثبت نشده است.</div>';

        ruleBox.innerHTML = rules.length
            ? rules.map((item) => `
                <div class="general-inline-chip">
                    <span class="material-icons-round">rule</span>
                    <span>${esc(item?.name || '-')} [${esc(item?.status_codes || '-')} ] (${esc(item?.project_code || 'همه')}/${esc(item?.discipline_code || 'همه')}/${esc(item?.package_code || 'همه')})</span>
                    <button type="button" data-general-action="delete-site-cache-rule" data-rule-id="${Number(item?.id || 0)}" title="حذف قانون">
                        <span class="material-icons-round">close</span>
                    </button>
                </div>
            `).join('')
            : '<div class="text-muted">قانونی ثبت نشده است.</div>';

        tokenBox.innerHTML = '<div class="text-muted">در حال بارگذاری...</div>';
    }

    async function loadSiteCacheTokens(profileId) {
        const tokenBox = document.getElementById('settingsSiteCacheTokensRows');
        if (!tokenBox || !profileId) return;
        try {
            const payload = await request(`${API_BASE}/site-cache/tokens?profile_id=${Number(profileId)}`);
            const tokens = Array.isArray(payload?.items) ? payload.items : [];
            tokenBox.innerHTML = tokens.length
                ? tokens.map((item) => `
                    <div class="general-inline-chip">
                        <span class="material-icons-round">vpn_key</span>
                        <span>${esc(item?.token_hint || '-')}</span>
                        <button type="button" data-general-action="revoke-site-cache-token" data-token-id="${Number(item?.id || 0)}" title="لغو توکن">
                            <span class="material-icons-round">close</span>
                        </button>
                    </div>
                `).join('')
                : '<div class="text-muted">توکن فعالی وجود ندارد.</div>';
        } catch (err) {
            tokenBox.innerHTML = `<div class="text-danger">${esc(err?.message || 'بارگذاری توکن‌ها ناموفق بود.')}</div>`;
        }
    }

    async function loadSiteCache(force = false) {
        const profileCodeInput = document.getElementById('siteCacheProfileCodeInput');
        if (!profileCodeInput) return;
        await loadEntity('projects', force);
        await loadEntity('disciplines', force);
        await loadEntity('packages', force);
        fillSiteCacheRuleFilterOptions();
        if (STORE.siteCacheLoaded && !force) {
            renderSiteCacheProfiles();
            const profile = currentSiteCacheProfile();
            renderSiteCacheProfileDetails(profile);
            if (profile?.id) await loadSiteCacheTokens(profile.id);
            return;
        }

        const payload = await request(`${API_BASE}/site-cache/profiles?include_inactive=true`);
        STORE.siteCache.profiles = Array.isArray(payload?.items) ? payload.items : [];
        STORE.siteCacheLoaded = true;
        renderSiteCacheProfiles();
        const profile = currentSiteCacheProfile();
        renderSiteCacheProfileDetails(profile);
        if (profile?.id) await loadSiteCacheTokens(profile.id);
    }

    function resetSiteCacheProfileForm() {
        const ids = [
            'siteCacheProfileCodeInput',
            'siteCacheProfileNameInput',
            'siteCacheProfileProjectInput',
            'siteCacheProfileRootInput',
        ];
        ids.forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        const fallback = document.getElementById('siteCacheProfileFallbackInput');
        if (fallback) fallback.value = 'local_first';
        const active = document.getElementById('siteCacheProfileActiveInput');
        if (active) active.checked = true;
        const codeInput = document.getElementById('siteCacheProfileCodeInput');
        if (codeInput) delete codeInput.dataset.editId;
    }

    async function saveSiteCacheProfile() {
        const codeInput = document.getElementById('siteCacheProfileCodeInput');
        const nameInput = document.getElementById('siteCacheProfileNameInput');
        if (!codeInput || !nameInput) return;
        ensureInputValidity(codeInput, 'فرمت کد سایت معتبر نیست.');
        ensureInputValidity(document.getElementById('siteCacheProfileProjectInput'), 'فرمت کد پروژه معتبر نیست.');
        const code = normalizeSiteCacheProfileCode(codeInput.value);
        const name = norm(nameInput.value);
        requireVal(name, 'نام پروفایل');
        if (name.length > 255) {
            throw new Error('نام پروفایل نباید بیشتر از ۲۵۵ کاراکتر باشد.');
        }

        const editId = Number(codeInput.dataset.editId || 0);
        const payload = {
            id: editId > 0 ? editId : null,
            code,
            name,
            project_code: normalizeOptionalSiteCode(
                document.getElementById('siteCacheProfileProjectInput')?.value,
                'کد پروژه',
                SITE_CACHE_PROJECT_CODE_RE,
                50
            ),
            local_root_path: normalizeSiteCacheRootPath(document.getElementById('siteCacheProfileRootInput')?.value),
            fallback_mode: normalizeSiteCacheFallbackMode(document.getElementById('siteCacheProfileFallbackInput')?.value),
            is_active: Boolean(document.getElementById('siteCacheProfileActiveInput')?.checked),
        };
        await request(`${API_BASE}/site-cache/profiles/upsert`, {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        setSiteCacheTokenMessage('');
        await loadSiteCache(true);
        resetSiteCacheProfileForm();
        tSuccess('پروفایل Site Cache ذخیره شد.');
    }

    function openEditSiteCacheProfile(profileId) {
        const item = (STORE.siteCache.profiles || []).find((row) => Number(row?.id || 0) === Number(profileId || 0));
        if (!item) return;
        const codeInput = document.getElementById('siteCacheProfileCodeInput');
        if (!codeInput) return;
        codeInput.value = item.code || '';
        codeInput.dataset.editId = String(Number(item.id || 0));
        document.getElementById('siteCacheProfileNameInput').value = item.name || '';
        document.getElementById('siteCacheProfileProjectInput').value = item.project_code || '';
        document.getElementById('siteCacheProfileRootInput').value = item.local_root_path || '';
        document.getElementById('siteCacheProfileFallbackInput').value = item.fallback_mode || 'local_first';
        document.getElementById('siteCacheProfileActiveInput').checked = Boolean(item.is_active);
        STORE.siteCache.activeProfileId = Number(item.id || 0);
        renderSiteCacheProfiles();
        renderSiteCacheProfileDetails(item);
        loadSiteCacheTokens(item.id);
    }

    async function disableSiteCacheProfile(profileId) {
        if (!confirm('این پروفایل Site Cache غیرفعال شود؟')) return;
        await request(`${API_BASE}/site-cache/profiles/delete`, {
            method: 'POST',
            body: JSON.stringify({ id: Number(profileId || 0), hard_delete: false }),
        });
        await loadSiteCache(true);
        tSuccess('پروفایل غیرفعال شد.');
    }

    async function addSiteCacheCidr() {
        const profileId = getActiveSiteCacheProfileId();
        ensureInputValidity(document.getElementById('siteCacheCidrInput'), 'فرمت CIDR معتبر نیست.');
        const cidr = normalizeSiteCacheCidr(document.getElementById('siteCacheCidrInput')?.value);
        await request(`${API_BASE}/site-cache/cidrs/upsert`, {
            method: 'POST',
            body: JSON.stringify({ profile_id: profileId, cidr, is_active: true }),
        });
        const input = document.getElementById('siteCacheCidrInput');
        if (input) input.value = '';
        await loadSiteCache(true);
        tSuccess('CIDR اضافه شد.');
    }

    async function deleteSiteCacheCidr(cidrId) {
        await request(`${API_BASE}/site-cache/cidrs/delete`, {
            method: 'POST',
            body: JSON.stringify({ id: Number(cidrId || 0) }),
        });
        await loadSiteCache(true);
        tSuccess('CIDR حذف شد.');
    }

    async function addSiteCacheRule() {
        const profileId = getActiveSiteCacheProfileId();
        ensureInputValidity(document.getElementById('siteCacheRulePriorityInput'), 'اولویت باید بین ۰ تا ۱۰۰۰۰ باشد.');
        const name = normalizeSiteCacheRuleName(document.getElementById('siteCacheRuleNameInput')?.value);
        const projectSelect = document.getElementById('siteCacheRuleProjectInput');
        const disciplineSelect = document.getElementById('siteCacheRuleDisciplineInput');
        const packageSelect = document.getElementById('siteCacheRulePackageInput');
        const projectCodes = parseSiteCacheFilterCodes(projectSelect, SITE_CACHE_PROJECT_CODE_RE, 'کد پروژه قانون', 50);
        const disciplineCodes = parseSiteCacheFilterCodes(disciplineSelect, SITE_CACHE_DISCIPLINE_CODE_RE, 'کد دیسیپلین قانون', 20);
        const packageSelections = parseSiteCachePackageSelections(packageSelect);
        const hasPackageScope = packageSelections.some((item) => item.package_code);
        const statusCodes = parseSiteCacheStatusCodes(document.getElementById('siteCacheRuleStatusInput')?.value);
        const includeNative = Boolean(document.getElementById('siteCacheRuleIncludeNativeInput')?.checked);
        const primaryOnly = Boolean(document.getElementById('siteCacheRulePrimaryOnlyInput')?.checked);
        const priority = parseSiteCachePriority(document.getElementById('siteCacheRulePriorityInput')?.value);

        const targets = [];
        if (hasPackageScope) {
            for (const projectCode of projectCodes) {
                for (const pkg of packageSelections) {
                    if (!pkg.package_code) continue;
                    if (disciplineCodes.every((code) => code !== null) && !disciplineCodes.includes(pkg.discipline_code)) {
                        continue;
                    }
                    targets.push({
                        project_code: projectCode,
                        discipline_code: pkg.discipline_code,
                        package_code: pkg.package_code,
                    });
                }
            }
        } else {
            for (const projectCode of projectCodes) {
                for (const disciplineCode of disciplineCodes) {
                    targets.push({
                        project_code: projectCode,
                        discipline_code: disciplineCode,
                        package_code: null,
                    });
                }
            }
        }

        const dedup = [];
        const seen = new Set();
        for (const target of targets) {
            const key = `${target.project_code || 'ALL'}|${target.discipline_code || 'ALL'}|${target.package_code || 'ALL'}`;
            if (seen.has(key)) continue;
            seen.add(key);
            dedup.push(target);
        }
        if (!dedup.length) {
            throw new Error('ترکیب انتخابی پروژه/دیسیپلین/پکیج معتبر نیست.');
        }
        if (dedup.length > 100) {
            throw new Error('تعداد ترکیب‌های انتخابی زیاد است (بیش از ۱۰۰). لطفاً فیلترها را محدودتر کنید.');
        }

        for (const target of dedup) {
            const scopeLabel = `${target.project_code || 'همه'}/${target.discipline_code || 'همه'}/${target.package_code || 'همه'}`;
            const scopedName = dedup.length > 1 ? `${name} [${scopeLabel}]` : name;
            await request(`${API_BASE}/site-cache/rules/upsert`, {
                method: 'POST',
                body: JSON.stringify({
                    profile_id: profileId,
                    name: scopedName.slice(0, 255),
                    status_codes: statusCodes,
                    project_code: target.project_code,
                    discipline_code: target.discipline_code,
                    package_code: target.package_code,
                    include_native: includeNative,
                    primary_only: primaryOnly,
                    latest_revision_only: true,
                    priority,
                    is_active: true,
                }),
            });
        }
        ['siteCacheRuleNameInput', 'siteCacheRuleStatusInput'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        setMultiSelectValues(projectSelect, [SITE_CACHE_ALL_VALUE]);
        setMultiSelectValues(disciplineSelect, [SITE_CACHE_ALL_VALUE]);
        fillSiteCacheRulePackageOptions([SITE_CACHE_ALL_VALUE], [SITE_CACHE_ALL_VALUE]);
        const priorityInput = document.getElementById('siteCacheRulePriorityInput');
        if (priorityInput) priorityInput.value = '100';
        await loadSiteCache(true);
        tSuccess(`${dedup.length} قانون Pin اضافه شد.`);
    }

    async function deleteSiteCacheRule(ruleId) {
        await request(`${API_BASE}/site-cache/rules/delete`, {
            method: 'POST',
            body: JSON.stringify({ id: Number(ruleId || 0) }),
        });
        await loadSiteCache(true);
        tSuccess('قانون حذف شد.');
    }

    async function mintSiteCacheToken() {
        const profileId = getActiveSiteCacheProfileId();
        const payload = await request(`${API_BASE}/site-cache/tokens/mint`, {
            method: 'POST',
            body: JSON.stringify({ profile_id: profileId }),
        });
        const token = String(payload?.token || '').trim();
        if (token) {
            setSiteCacheTokenMessage(`توکن Agent (فقط یک‌بار نمایش): ${token}`, 'success');
        }
        await loadSiteCacheTokens(profileId);
        tSuccess('توکن Agent جدید ایجاد شد.');
    }

    async function revokeSiteCacheToken(tokenId) {
        await request(`${API_BASE}/site-cache/tokens/revoke`, {
            method: 'POST',
            body: JSON.stringify({ token_id: Number(tokenId || 0) }),
        });
        await loadSiteCache(true);
        setSiteCacheTokenMessage('');
        tSuccess('توکن لغو شد.');
    }

    async function rebuildSiteCachePins() {
        const profileId = getActiveSiteCacheProfileId();
        const payload = await request(`${API_BASE}/site-cache/rebuild-pins`, {
            method: 'POST',
            body: JSON.stringify({ profile_id: profileId, dry_run: false }),
        });
        const result = payload?.result || {};
        const summary = `بازسازی انجام شد: انتخاب=${Number(result.selected_count || 0)}، فعال=${Number(result.to_enable_count || 0)}، غیرفعال=${Number(result.to_disable_count || 0)}`;
        setSiteCacheTokenMessage(summary, 'info');
        tSuccess(summary);
    }

    function normalizeStoragePathForCompare(value) {
        return norm(value).replace(/[\\/]+$/g, '');
    }

    function setStoragePathConflictError(message = '') {
        const box = document.getElementById('storagePathsConflictError');
        const mdrInput = document.getElementById('mdrStoragePathInput');
        const corrInput = document.getElementById('correspondenceStoragePathInput');
        if (!mdrInput || !corrInput) return;
        if (message) {
            if (box) {
                box.textContent = message;
                box.style.display = 'block';
            }
            mdrInput.classList.add('form-input-error');
            corrInput.classList.add('form-input-error');
            return;
        }
        if (box) {
            box.textContent = '';
            box.style.display = 'none';
        }
        mdrInput.classList.remove('form-input-error');
        corrInput.classList.remove('form-input-error');
    }

    function validateStoragePathConflict(showError = true) {
        const mdrInput = document.getElementById('mdrStoragePathInput');
        const corrInput = document.getElementById('correspondenceStoragePathInput');
        if (!mdrInput || !corrInput) return true;

        const mdrPath = normalizeStoragePathForCompare(mdrInput.value);
        const corrPath = normalizeStoragePathForCompare(corrInput.value);
        const hasConflict = Boolean(mdrPath) && Boolean(corrPath) && mdrPath === corrPath;

        if (hasConflict) {
            if (showError) {
                setStoragePathConflictError('مسیر MDR و مسیر مکاتبات نباید یکسان باشند.');
            }
            return false;
        }

        setStoragePathConflictError('');
        return true;
    }

    function bindStoragePathValidation() {
        const mdrInput = document.getElementById('mdrStoragePathInput');
        const corrInput = document.getElementById('correspondenceStoragePathInput');
        if (!mdrInput || !corrInput) return;
        if (mdrInput.dataset.storagePathBound === '1') return;

        const onInput = (event) => {
            const inputEl = event?.target;
            if (inputEl && inputEl.dataset) {
                inputEl.dataset.storagePathDirty = '1';
            }
            hideStorageStepSaved('paths');
            markStorageStepDirty('paths');
            updateStoragePathPreview();
            validateStoragePathConflict(true);
        };
        mdrInput.addEventListener('input', onInput);
        corrInput.addEventListener('input', onInput);
        mdrInput.dataset.storagePathBound = '1';
        corrInput.dataset.storagePathBound = '1';
    }

    async function ensureSelects() {
        if (!STORE.data.projects.length) await loadEntity('projects', true);
        if (!STORE.data.disciplines.length) await loadEntity('disciplines', true);
        fillSelect('blockProjectInput', STORE.data.projects, (p) => `${p.code} - ${p.project_name || '-'}`, (p) => p.code);
        fillSelect('packageDisciplineInput', STORE.data.disciplines, (d) => `${d.code} - ${d.name_e || '-'}`, (d) => d.code);
        const issuingProjectInput = document.getElementById('issuingProjectCodeInput');
        if (issuingProjectInput) {
            const prev = issuingProjectInput.value;
            const options = ['<option value="">Auto / No Project</option>']
                .concat(
                    (STORE.data.projects || []).map(
                        (p) => `<option value="${esc(p.code)}">${esc(`${p.code} - ${p.project_name || '-'}`)}</option>`
                    )
                )
                .join('');
            issuingProjectInput.innerHTML = options;
            if (prev && (STORE.data.projects || []).some((p) => String(p.code || '') === prev)) {
                issuingProjectInput.value = prev;
            } else {
                issuingProjectInput.value = '';
            }
        }

        const packageDiscInput = document.getElementById('packageDisciplineInput');
        const packageCodeInput = document.getElementById('packageCodeInput');
        if (packageDiscInput && packageCodeInput && !packageDiscInput.dataset.autoCodeBound) {
            packageDiscInput.dataset.autoCodeBound = '1';
            packageDiscInput.addEventListener('change', () => {
                if (isPackageEditMode()) return;
                packageCodeInput.value = nextPackageCodeForDiscipline(packageDiscInput.value);
            });
        }
        if (packageDiscInput && packageCodeInput) {
            packageCodeInput.readOnly = true;
        }
        if (packageDiscInput && packageCodeInput && !packageCodeInput.dataset.mode) {
            setPackageFormMode('new');
        } else if (packageDiscInput && packageCodeInput && !isPackageEditMode()) {
            packageCodeInput.value = nextPackageCodeForDiscipline(packageDiscInput.value);
        }
    }

    function activeGeneralPage() {
        const activeBtn = document.querySelector('.general-settings-btn.active[data-general-tab]');
        if (activeBtn?.dataset?.generalTab) return activeBtn.dataset.generalTab;
        const el = document.querySelector('.general-settings-page.active');
        if (!el?.id) return STORE.activePage || 'db_sync';
        return el.id.replace('general-page-', '');
    }

    function toggleGeneralStorageSections(page) {
        const dbPage = document.getElementById('general-page-db');
        if (!dbPage) return;
        const showStorage = page === 'storage';
        const dbOnlySections = Array.from(dbPage.querySelectorAll('.general-db-only'));
        const storageOnlySections = Array.from(dbPage.querySelectorAll('.general-storage-only'));
        dbOnlySections.forEach((el) => {
            el.style.display = showStorage ? 'none' : '';
        });
        storageOnlySections.forEach((el) => {
            el.style.display = showStorage ? '' : 'none';
        });
    }

    function isGeneralButtonVisibleForDomain(buttonEl, domain) {
        const buttonDomain = norm(buttonEl?.dataset?.generalDomain || 'common').toLowerCase();
        if (domain === 'all') return true;
        return buttonDomain === domain || buttonDomain === 'common';
    }

    function applyGeneralDomainVisibility(domain = 'common') {
        const buttons = Array.from(document.querySelectorAll('.general-settings-btn[data-general-tab]'));
        let firstVisible = null;
        let firstDomainVisible = null;
        buttons.forEach((button) => {
            const visible = isGeneralButtonVisibleForDomain(button, domain);
            const buttonDomain = norm(button?.dataset?.generalDomain || 'common').toLowerCase();
            button.classList.toggle('is-hidden', !visible);
            button.setAttribute('aria-hidden', visible ? 'false' : 'true');
            if (visible && !firstVisible) firstVisible = button;
            if (visible && domain !== 'all' && buttonDomain === domain && !firstDomainVisible) firstDomainVisible = button;
        });
        return firstDomainVisible || firstVisible;
    }

    async function loadGeneralPageData(page, force = false) {
        STORE.activePage = page;
        if (page === 'db_sync') {
            toggleGeneralStorageSections(page);
            await loadOverview();
            await loadEntity('projects', force);
            refreshProjectCards();
            return;
        }
        if (page === 'storage') {
            toggleGeneralStorageSections(page);
            bindStorageWorkflowInputs();
            setStorageWizardStep('paths', { force: true });
            await loadStoragePaths(force);
            await loadStoragePolicy(force);
            await loadStorageIntegrations(force);
            try {
                await loadSiteCache(force);
            } catch (err) {
                setSiteCacheTokenMessage(`خطا در بارگذاری Site Cache: ${err.message}`, 'error');
            }
            updateStoragePathPreview();
            updateStorageIntegrationsFieldState();
            updateStorageActionBarState();
            return;
        }
        if (page === 'transmittal_config') {
            await loadEntity('projects', force);
            await loadEntity('mdr', force);
            await loadEntity('phases', force);
            await loadEntity('disciplines', force);
            await loadEntity('statuses', force);
            refreshTransmittalConfigSummary();
            return;
        }
        await loadEntity(page, force);
        if (['projects', 'disciplines', 'packages', 'blocks', 'corr_issuing'].includes(page)) await ensureSelects();
    }

    function bindGeneralActions() {
        if (STORE.actionsBound) return;

        document.addEventListener('click', (event) => {
            const actionEl = event && event.target && event.target.closest
                ? event.target.closest('[data-general-action]')
                : null;
            if (!actionEl) return;

            const action = String(actionEl.dataset.generalAction || '').trim();
            if (!action) return;

            switch (action) {
                case 'switch-page':
                    window.switchGeneralSettingsPage(actionEl.dataset.generalTab || '', actionEl);
                    break;
                case 'switch-domain':
                    window.switchGeneralSettingsDomain(actionEl.dataset.generalDomain || 'common', actionEl);
                    break;
                case 'run-seed':
                    window.localRunSeed();
                    break;
                case 'save-storage-paths':
                    window.saveStoragePaths();
                    break;
                case 'save-storage-policy':
                    window.saveStoragePolicySettings();
                    break;
                case 'save-storage-integrations':
                    window.saveStorageIntegrationsSettings();
                    break;
                case 'run-storage-google-drive-sync':
                    window.runStorageGoogleDriveSync();
                    break;
                case 'run-storage-openproject-sync':
                    window.runStorageOpenProjectSync();
                    break;
                case 'storage-switch-step':
                    setStorageWizardStep(actionEl.dataset.storageStep || 'paths');
                    break;
                case 'storage-step-prev':
                    moveStorageWizardStep(-1);
                    break;
                case 'storage-step-next':
                    moveStorageWizardStep(1);
                    break;
                case 'storage-save-current':
                    saveCurrentStorageWizardStep();
                    break;
                case 'storage-policy-preset':
                    applyStoragePolicyPreset(actionEl.dataset.storagePreset || 'standard');
                    break;
                case 'save-site-cache-profile':
                    window.saveSiteCacheProfileSetting();
                    break;
                case 'reset-site-cache-profile':
                    window.resetSiteCacheProfileSetting();
                    break;
                case 'open-edit-site-cache-profile':
                    window.openEditSiteCacheProfileById(actionEl.dataset.profileId || '');
                    break;
                case 'delete-site-cache-profile':
                    window.deleteSiteCacheProfileById(actionEl.dataset.profileId || '');
                    break;
                case 'refresh-site-cache':
                    window.refreshSiteCacheSettings();
                    break;
                case 'save-site-cache-cidr':
                    window.saveSiteCacheCidrSetting();
                    break;
                case 'delete-site-cache-cidr':
                    window.deleteSiteCacheCidrSetting(actionEl.dataset.cidrId || '');
                    break;
                case 'save-site-cache-rule':
                    window.saveSiteCacheRuleSetting();
                    break;
                case 'delete-site-cache-rule':
                    window.deleteSiteCacheRuleSetting(actionEl.dataset.ruleId || '');
                    break;
                case 'mint-site-cache-token':
                    window.mintSiteCacheTokenSetting();
                    break;
                case 'revoke-site-cache-token':
                    window.revokeSiteCacheTokenSetting(actionEl.dataset.tokenId || '');
                    break;
                case 'rebuild-site-cache-pins':
                    window.rebuildSiteCachePinsSetting();
                    break;
                case 'save-project':
                    window.saveProjectSetting();
                    break;
                case 'reset-project':
                    window.resetProjectForm();
                    break;
                case 'save-mdr':
                    window.saveMdrSetting();
                    break;
                case 'reset-mdr':
                    window.resetMdrForm();
                    break;
                case 'save-phase':
                    window.savePhaseSetting();
                    break;
                case 'reset-phase':
                    window.resetPhaseForm();
                    break;
                case 'save-discipline':
                    window.saveDisciplineSetting();
                    break;
                case 'reset-discipline':
                    window.resetDisciplineForm();
                    break;
                case 'save-package':
                    window.savePackageSetting();
                    break;
                case 'reset-package':
                    window.resetPackageForm();
                    break;
                case 'save-block':
                    window.saveBlockSetting();
                    break;
                case 'reset-block':
                    window.resetBlockForm();
                    break;
                case 'save-level':
                    window.saveLevelSetting();
                    break;
                case 'reset-level':
                    window.resetLevelForm();
                    break;
                case 'save-status':
                    window.saveStatusSetting();
                    break;
                case 'reset-status':
                    window.resetStatusForm();
                    break;
                case 'goto-page':
                    window.settingsGotoPage(actionEl.dataset.entity || '', Number(actionEl.dataset.page || 1));
                    break;
                case 'open-edit-project':
                    window.openEditProjectByCode(actionEl.dataset.code || '');
                    break;
                case 'delete-project':
                    window.deleteProjectSetting(actionEl.dataset.code || '');
                    break;
                case 'open-edit-mdr':
                    window.openEditMdrByCode(actionEl.dataset.code || '');
                    break;
                case 'delete-mdr':
                    window.deleteMdrSetting(actionEl.dataset.code || '');
                    break;
                case 'open-edit-phase':
                    window.openEditPhaseByCode(actionEl.dataset.code || '');
                    break;
                case 'delete-phase':
                    window.deletePhaseSetting(actionEl.dataset.code || '');
                    break;
                case 'open-edit-discipline':
                    window.openEditDisciplineByCode(actionEl.dataset.code || '');
                    break;
                case 'delete-discipline':
                    window.deleteDisciplineSetting(actionEl.dataset.code || '');
                    break;
                case 'open-edit-package':
                    window.openEditPackageByKey(actionEl.dataset.disciplineCode || '', actionEl.dataset.packageCode || '');
                    break;
                case 'delete-package':
                    window.deletePackageSetting(actionEl.dataset.disciplineCode || '', actionEl.dataset.packageCode || '');
                    break;
                case 'open-edit-block':
                    window.openEditBlockByKey(actionEl.dataset.projectCode || '', actionEl.dataset.code || '');
                    break;
                case 'delete-block':
                    window.deleteBlockSetting(actionEl.dataset.projectCode || '', actionEl.dataset.code || '');
                    break;
                case 'open-edit-level':
                    window.openEditLevelByCode(actionEl.dataset.code || '');
                    break;
                case 'delete-level':
                    window.deleteLevelSetting(actionEl.dataset.code || '');
                    break;
                case 'open-edit-status':
                    window.openEditStatusByCode(actionEl.dataset.code || '');
                    break;
                case 'delete-status':
                    window.deleteStatusSetting(actionEl.dataset.code || '');
                    break;
                case 'save-corr-issuing':
                    window.saveCorrespondenceIssuingSetting();
                    break;
                case 'reset-corr-issuing':
                    window.resetCorrespondenceIssuingForm();
                    break;
                case 'open-edit-corr-issuing':
                    window.openEditCorrespondenceIssuingByCode(actionEl.dataset.code || '');
                    break;
                case 'delete-corr-issuing':
                    window.deleteCorrespondenceIssuingSetting(actionEl.dataset.code || '');
                    break;
                case 'save-corr-category':
                    window.saveCorrespondenceCategorySetting();
                    break;
                case 'reset-corr-category':
                    window.resetCorrespondenceCategoryForm();
                    break;
                case 'open-edit-corr-category':
                    window.openEditCorrespondenceCategoryByCode(actionEl.dataset.code || '');
                    break;
                case 'delete-corr-category':
                    window.deleteCorrespondenceCategorySetting(actionEl.dataset.code || '');
                    break;
                default:
                    break;
            }
        });

        document.addEventListener('input', (event) => {
            const actionEl = event && event.target && event.target.closest
                ? event.target.closest('[data-general-action]')
                : null;
            if (!actionEl) return;
            const action = String(actionEl.dataset.generalAction || '').trim();
            if (action !== 'search-entity') return;
            window.updateSettingsSearch(actionEl.dataset.entity || '', actionEl.value || '');
        });

        document.addEventListener('change', (event) => {
            const actionEl = event && event.target && event.target.closest
                ? event.target.closest('[data-general-action]')
                : null;
            if (!actionEl) {
                const target = event?.target;
                if (target?.id === 'siteCacheProfileSelect') {
                    const profileId = Number(target.value || 0);
                    STORE.siteCache.activeProfileId = profileId;
                    const profile = currentSiteCacheProfile();
                    renderSiteCacheProfileDetails(profile);
                    loadSiteCacheTokens(profileId);
                } else if (target?.id === 'siteCacheRuleDisciplineInput') {
                    fillSiteCacheRulePackageOptions(getMultiSelectValues(target));
                }
                return;
            }
            const action = String(actionEl.dataset.generalAction || '').trim();
            if (action !== 'page-size-entity') return;
            window.updateSettingsPageSize(actionEl.dataset.entity || '', actionEl.value || 10);
        });

        STORE.actionsBound = true;
    }

    async function initGeneralSettings(force = false) {
        bindGeneralActions();
        bindStoragePathValidation();
        if (STORE.loadingPromise) return STORE.loadingPromise;

        const job = (async () => {
            try {
                if (!STORE.initialized || force) {
                    await loadEntity('projects', true);
                    await loadEntity('disciplines', true);
                    refreshProjectCards();
                    await ensureSelects();
                    STORE.initialized = true;
                }
                await window.switchGeneralSettingsDomain(STORE.activeDomain || 'common', null, force);
            } catch (err) {
                tError(`خطا در بارگذاری تنظیمات عمومی: ${err.message}`);
            }
        })();

        STORE.loadingPromise = job.finally(() => {
            STORE.loadingPromise = null;
        });
        return STORE.loadingPromise;
    }

    function requireVal(value, label) {
        if (!norm(value)) throw new Error(`${label} الزامی است`);
    }

    function extractPackageSequence(code, disciplineCode = '') {
        const raw = norm(code).toUpperCase();
        if (!raw) return null;
        const disc = norm(disciplineCode).toUpperCase();
        let candidate = raw;
        if (disc && candidate.startsWith(disc)) {
            candidate = candidate.slice(disc.length);
        }
        if (/^\d+$/.test(candidate)) {
            const n = Number(candidate);
            if (Number.isInteger(n) && n >= 1 && n <= 99) return n;
            return null;
        }
        const match = candidate.match(/(\d{1,3})$/);
        if (!match) return null;
        const n = Number(match[1]);
        if (!Number.isInteger(n) || n < 1 || n > 99) return null;
        return n;
    }

    function nextPackageCodeForDiscipline(disciplineCode) {
        const disc = norm(disciplineCode).toUpperCase();
        const used = new Set();
        (STORE.data.packages || []).forEach((pkg) => {
            if (norm(pkg?.discipline_code).toUpperCase() !== disc) return;
            const seq = extractPackageSequence(pkg?.package_code, disc);
            if (seq !== null) used.add(seq);
        });
        for (let i = 1; i <= 99; i += 1) {
            if (!used.has(i)) return String(i).padStart(2, '0');
        }
        return '';
    }

    function isPackageEditMode() {
        const codeInput = document.getElementById('packageCodeInput');
        return (codeInput?.dataset?.mode || 'new') === 'edit';
    }

    function setPackageFormMode(mode = 'new') {
        const codeInput = document.getElementById('packageCodeInput');
        const discInput = document.getElementById('packageDisciplineInput');
        if (!codeInput || !discInput) return;
        const finalMode = mode === 'edit' ? 'edit' : 'new';
        codeInput.dataset.mode = finalMode;
        codeInput.readOnly = true;
        discInput.disabled = finalMode === 'edit';
        if (finalMode === 'new') {
            codeInput.value = nextPackageCodeForDiscipline(discInput.value);
        }
    }

    function findBy(listName, predicate) {
        return (STORE.data[listName] || []).find(predicate);
    }

    async function postAndReload(url, payload, reloadEntities, successMessage) {
        await request(`${API_BASE}${url}`, {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        tSuccess(successMessage);
        for (const entity of reloadEntities) await loadEntity(entity, true);
        if (reloadEntities.includes('projects')) refreshProjectCards();
        if (reloadEntities.includes('projects') || reloadEntities.includes('disciplines')) await ensureSelects();
        await loadOverview();
    }

    window.saveSiteCacheProfileSetting = async function saveSiteCacheProfileSetting() {
        try {
            await saveSiteCacheProfile();
        } catch (err) {
            tError(err.message);
        }
    };

    window.resetSiteCacheProfileSetting = function resetSiteCacheProfileSetting() {
        resetSiteCacheProfileForm();
        setSiteCacheTokenMessage('');
    };

    window.openEditSiteCacheProfileById = function openEditSiteCacheProfileById(profileId) {
        openEditSiteCacheProfile(profileId);
    };

    window.deleteSiteCacheProfileById = async function deleteSiteCacheProfileById(profileId) {
        try {
            await disableSiteCacheProfile(profileId);
        } catch (err) {
            tError(err.message);
        }
    };

    window.refreshSiteCacheSettings = async function refreshSiteCacheSettings() {
        try {
            await loadSiteCache(true);
            setSiteCacheTokenMessage('اطلاعات Site Cache با موفقیت بازخوانی شد.', 'info');
        } catch (err) {
            tError(err.message);
        }
    };

    window.saveSiteCacheCidrSetting = async function saveSiteCacheCidrSetting() {
        try {
            await addSiteCacheCidr();
        } catch (err) {
            tError(err.message);
        }
    };

    window.deleteSiteCacheCidrSetting = async function deleteSiteCacheCidrSetting(cidrId) {
        try {
            await deleteSiteCacheCidr(cidrId);
        } catch (err) {
            tError(err.message);
        }
    };

    window.saveSiteCacheRuleSetting = async function saveSiteCacheRuleSetting() {
        try {
            await addSiteCacheRule();
        } catch (err) {
            tError(err.message);
        }
    };

    window.deleteSiteCacheRuleSetting = async function deleteSiteCacheRuleSetting(ruleId) {
        try {
            await deleteSiteCacheRule(ruleId);
        } catch (err) {
            tError(err.message);
        }
    };

    window.mintSiteCacheTokenSetting = async function mintSiteCacheTokenSetting() {
        try {
            await mintSiteCacheToken();
        } catch (err) {
            tError(err.message);
        }
    };

    window.revokeSiteCacheTokenSetting = async function revokeSiteCacheTokenSetting(tokenId) {
        try {
            await revokeSiteCacheToken(tokenId);
        } catch (err) {
            tError(err.message);
        }
    };

    window.rebuildSiteCachePinsSetting = async function rebuildSiteCachePinsSetting() {
        try {
            await rebuildSiteCachePins();
        } catch (err) {
            tError(err.message);
        }
    };

    window.switchGeneralSettingsPage = async function switchGeneralSettingsPage(page, btnEl = null, force = false) {
        if (!page) return;
        document.querySelectorAll('.general-settings-btn').forEach((b) => b.classList.remove('active'));
        document.querySelectorAll('.general-settings-page').forEach((p) => p.classList.remove('active'));
        const btn = btnEl || document.querySelector(`.general-settings-btn[data-general-tab="${page}"]`);
        if (btn) btn.classList.add('active');
        const physicalPage = page === 'storage' || page === 'db_sync' ? 'db' : page;
        const tab = document.getElementById(`general-page-${physicalPage}`);
        if (!tab) return;
        tab.classList.add('active');
        await loadGeneralPageData(page, force);
    };

    window.switchGeneralSettingsDomain = async function switchGeneralSettingsDomain(domain = 'common', btnEl = null, force = false) {
        const normalizedDomain = norm(domain).toLowerCase() || 'common';
        STORE.activeDomain = normalizedDomain;

        document.querySelectorAll('.general-module-btn').forEach((b) => b.classList.remove('active'));
        const moduleBtn = btnEl || document.querySelector(`.general-module-btn[data-general-domain="${normalizedDomain}"]`);
        if (moduleBtn) moduleBtn.classList.add('active');

        const preferredVisible = applyGeneralDomainVisibility(normalizedDomain);
        const activeBtn = document.querySelector('.general-settings-btn.active');
        const activeBtnDomain = norm(activeBtn?.dataset?.generalDomain || 'common').toLowerCase();
        const keepCurrentActive = Boolean(
            activeBtn &&
            !activeBtn.classList.contains('is-hidden') &&
            (normalizedDomain === 'all' || activeBtnDomain === normalizedDomain)
        );
        if (keepCurrentActive) {
            await loadGeneralPageData(activeGeneralPage(), force);
            return;
        }
        if (preferredVisible?.dataset?.generalTab) {
            await window.switchGeneralSettingsPage(preferredVisible.dataset.generalTab, preferredVisible, force);
        }
    };

    window.updateSettingsSearch = function updateSettingsSearch(entity, value) {
        if (!STORE.paging[entity]) return;
        STORE.paging[entity].search = value || '';
        STORE.paging[entity].page = 1;
        renderEntity(entity);
    };

    window.updateSettingsPageSize = function updateSettingsPageSize(entity, size) {
        if (!STORE.paging[entity]) return;
        STORE.paging[entity].pageSize = Number(size) || 10;
        STORE.paging[entity].page = 1;
        renderEntity(entity);
    };

    window.settingsGotoPage = function settingsGotoPage(entity, page) {
        if (!STORE.paging[entity]) return;
        STORE.paging[entity].page = Number(page) || 1;
        renderEntity(entity);
    };

    window.localRunSeed = async function localRunSeed() {
        if (!confirm('Seed اجرا شود؟ داده‌های پایه بروزرسانی می‌شوند.')) return;
        try {
            await request(`${API_BASE}/seed`, { method: 'POST' });
            tSuccess('Seed با موفقیت اجرا شد.');
            STORE.initialized = false;
            await initGeneralSettings(true);
        } catch (err) {
            tError(`Seed ناموفق بود: ${err.message}`);
        }
    };

    window.saveStoragePaths = async function saveStoragePaths() {
        try {
            bindStoragePathValidation();
            const mdr_storage_path = norm(document.getElementById('mdrStoragePathInput')?.value);
            const correspondence_storage_path = norm(document.getElementById('correspondenceStoragePathInput')?.value);
            requireVal(mdr_storage_path, 'مسیر ذخیره مدارک مهندسی');
            requireVal(correspondence_storage_path, 'مسیر ذخیره مکاتبات');
            if (!validateStoragePathConflict(true)) return;

            const payload = await request(`${API_BASE}/storage-paths`, {
                method: 'POST',
                body: JSON.stringify({ mdr_storage_path, correspondence_storage_path }),
            });

            document.getElementById('mdrStoragePathInput').value = norm(payload?.mdr_storage_path || mdr_storage_path);
            document.getElementById('correspondenceStoragePathInput').value = norm(
                payload?.correspondence_storage_path || correspondence_storage_path
            );
            document.getElementById('mdrStoragePathInput').dataset.storagePathDirty = '0';
            document.getElementById('correspondenceStoragePathInput').dataset.storagePathDirty = '0';
            updateStoragePathPreview();
            setStoragePathConflictError('');
            STORE.storagePathsLoaded = true;
            clearStorageStepDirty('paths');
            showStorageStepSaved('paths', 'مسیرهای ذخیره‌سازی با موفقیت ذخیره شدند.');
            tSuccess('مسیرهای ذخیره‌سازی ذخیره شد.');
        } catch (err) {
            tError(err.message);
        }
    };

    window.saveStoragePolicySettings = async function saveStoragePolicySettings() {
        try {
            await saveStoragePolicy();
        } catch (err) {
            tError(err.message);
        }
    };

    window.saveStorageIntegrationsSettings = async function saveStorageIntegrationsSettings() {
        try {
            await saveStorageIntegrations();
        } catch (err) {
            tError(err.message);
        }
    };

    window.runStorageGoogleDriveSync = async function runStorageGoogleDriveSync() {
        try {
            await runStorageSyncJob('google_drive');
        } catch (err) {
            const detail = String(err?.message || 'Google Drive sync failed.');
            setStorageSyncResult(`اجرای Sync گوگل‌درایو ناموفق بود: ${detail}`, 'error');
            tError(`Sync گوگل‌درایو انجام نشد. ${detail}`);
        }
    };

    window.runStorageOpenProjectSync = async function runStorageOpenProjectSync() {
        try {
            await runStorageSyncJob('openproject');
        } catch (err) {
            const detail = String(err?.message || 'OpenProject sync failed.');
            setStorageSyncResult(`اجرای Sync اوپن‌پراجکت ناموفق بود: ${detail}`, 'error');
            tError(`Sync اوپن‌پراجکت انجام نشد. ${detail}`);
        }
    };

    window.saveProjectSetting = async function saveProjectSetting() {
        try {
            const code = norm(document.getElementById('projectCodeInput')?.value).toUpperCase();
            requireVal(code, 'کد پروژه');
            const payload = {
                code,
                project_name: norm(document.getElementById('projectNameInput')?.value),
                root_path: norm(document.getElementById('projectRootInput')?.value),
                docnum_template: norm(document.getElementById('projectTemplateInput')?.value),
                is_active: Boolean(document.getElementById('projectActiveInput')?.checked),
            };
            await postAndReload('/projects/upsert', payload, ['projects'], 'پروژه ذخیره شد.');
            window.resetProjectForm();
        } catch (err) { tError(err.message); }
    };
    window.resetProjectForm = function resetProjectForm() {
        ['projectCodeInput', 'projectNameInput', 'projectRootInput', 'projectTemplateInput'].forEach((id) => {
            const el = document.getElementById(id); if (el) el.value = '';
        });
        const chk = document.getElementById('projectActiveInput'); if (chk) chk.checked = true;
    };
    window.openEditProjectByCode = function openEditProjectByCode(encodedCode) {
        const item = findBy('projects', (p) => p.code === decoded(encodedCode));
        if (!item) return;
        document.getElementById('projectCodeInput').value = item.code || '';
        document.getElementById('projectNameInput').value = item.project_name || '';
        document.getElementById('projectRootInput').value = item.root_path || '';
        document.getElementById('projectTemplateInput').value = item.docnum_template || '';
        document.getElementById('projectActiveInput').checked = Boolean(item.is_active);
    };
    window.deleteProjectSetting = async function deleteProjectSetting(encodedCode) {
        const code = decoded(encodedCode);
        if (!confirm(`پروژه ${code} غیرفعال شود؟`)) return;
        try { await postAndReload('/projects/delete', { code, hard_delete: false }, ['projects'], 'پروژه غیرفعال شد.'); }
        catch (err) { tError(err.message); }
    };

    window.saveMdrSetting = async function saveMdrSetting() {
        try {
            const payload = {
                code: norm(document.getElementById('mdrCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('mdrNameEInput')?.value),
                name_p: norm(document.getElementById('mdrNamePInput')?.value),
                folder_name: norm(document.getElementById('mdrFolderInput')?.value),
                sort_order: Number(document.getElementById('mdrSortInput')?.value || 0),
                is_active: Boolean(document.getElementById('mdrActiveInput')?.checked),
            };
            requireVal(payload.code, 'کد MDR');
            await postAndReload('/mdr-categories/upsert', payload, ['mdr'], 'MDR ذخیره شد.');
            window.resetMdrForm();
        } catch (err) { tError(err.message); }
    };
    window.resetMdrForm = function resetMdrForm() {
        ['mdrCodeInput', 'mdrNameEInput', 'mdrNamePInput', 'mdrFolderInput'].forEach((id) => (document.getElementById(id).value = ''));
        document.getElementById('mdrSortInput').value = '0';
        document.getElementById('mdrActiveInput').checked = true;
    };
    window.openEditMdrByCode = function openEditMdrByCode(c) {
        const item = findBy('mdr', (x) => x.code === decoded(c)); if (!item) return;
        document.getElementById('mdrCodeInput').value = item.code || '';
        document.getElementById('mdrNameEInput').value = item.name_e || '';
        document.getElementById('mdrNamePInput').value = item.name_p || '';
        document.getElementById('mdrFolderInput').value = item.folder_name || '';
        document.getElementById('mdrSortInput').value = item.sort_order ?? 0;
        document.getElementById('mdrActiveInput').checked = Boolean(item.is_active);
    };
    window.deleteMdrSetting = async function deleteMdrSetting(c) {
        const code = decoded(c);
        if (!confirm(`MDR ${code} غیرفعال شود؟`)) return;
        try { await postAndReload('/mdr-categories/delete', { code, hard_delete: false }, ['mdr'], 'MDR غیرفعال شد.'); }
        catch (err) { tError(err.message); }
    };

    window.savePhaseSetting = async function savePhaseSetting() {
        try {
            const payload = {
                ph_code: norm(document.getElementById('phaseCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('phaseNameEInput')?.value),
                name_p: norm(document.getElementById('phaseNamePInput')?.value),
            };
            requireVal(payload.ph_code, 'کد فاز');
            requireVal(payload.name_e, 'نام فاز');
            await postAndReload('/phases/upsert', payload, ['phases'], 'فاز ذخیره شد.');
            window.resetPhaseForm();
        } catch (err) { tError(err.message); }
    };
    window.resetPhaseForm = function resetPhaseForm() {
        ['phaseCodeInput', 'phaseNameEInput', 'phaseNamePInput'].forEach((id) => (document.getElementById(id).value = ''));
    };
    window.openEditPhaseByCode = function openEditPhaseByCode(c) {
        const item = findBy('phases', (x) => x.ph_code === decoded(c)); if (!item) return;
        document.getElementById('phaseCodeInput').value = item.ph_code || '';
        document.getElementById('phaseNameEInput').value = item.name_e || '';
        document.getElementById('phaseNamePInput').value = item.name_p || '';
    };
    window.deletePhaseSetting = async function deletePhaseSetting(c) {
        const ph_code = decoded(c);
        if (!confirm(`فاز ${ph_code} حذف شود؟`)) return;
        try { await postAndReload('/phases/delete', { ph_code }, ['phases'], 'فاز حذف شد.'); } catch (err) { tError(err.message); }
    };

    window.saveDisciplineSetting = async function saveDisciplineSetting() {
        try {
            const payload = {
                code: norm(document.getElementById('disciplineCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('disciplineNameEInput')?.value),
                name_p: norm(document.getElementById('disciplineNamePInput')?.value),
            };
            requireVal(payload.code, 'کد دیسیپلین');
            requireVal(payload.name_e, 'نام دیسیپلین');
            await postAndReload('/disciplines/upsert', payload, ['disciplines', 'packages'], 'دیسیپلین ذخیره شد.');
            window.resetDisciplineForm();
        } catch (err) { tError(err.message); }
    };
    window.resetDisciplineForm = function resetDisciplineForm() {
        ['disciplineCodeInput', 'disciplineNameEInput', 'disciplineNamePInput'].forEach((id) => (document.getElementById(id).value = ''));
    };
    window.openEditDisciplineByCode = function openEditDisciplineByCode(c) {
        const item = findBy('disciplines', (x) => x.code === decoded(c)); if (!item) return;
        document.getElementById('disciplineCodeInput').value = item.code || '';
        document.getElementById('disciplineNameEInput').value = item.name_e || '';
        document.getElementById('disciplineNamePInput').value = item.name_p || '';
    };
    window.deleteDisciplineSetting = async function deleteDisciplineSetting(c) {
        const code = decoded(c);
        if (!confirm(`دیسیپلین ${code} حذف شود؟`)) return;
        try { await postAndReload('/disciplines/delete', { code }, ['disciplines', 'packages'], 'دیسیپلین حذف شد.'); } catch (err) { tError(err.message); }
    };

    window.savePackageSetting = async function savePackageSetting() {
        try {
            const disciplineCode = norm(document.getElementById('packageDisciplineInput')?.value).toUpperCase();
            const codeInput = document.getElementById('packageCodeInput');
            let normalizedCode = '';
            if (isPackageEditMode()) {
                normalizedCode = norm(codeInput?.value).toUpperCase();
            } else {
                normalizedCode = nextPackageCodeForDiscipline(disciplineCode);
                if (codeInput) codeInput.value = normalizedCode;
            }
            const payload = {
                discipline_code: disciplineCode,
                package_code: normalizedCode,
                name_e: norm(document.getElementById('packageNameEInput')?.value),
                name_p: norm(document.getElementById('packageNamePInput')?.value),
            };
            requireVal(payload.discipline_code, 'دیسیپلین');
            requireVal(payload.package_code, 'کد پکیج خودکار');
            requireVal(payload.name_e, 'نام انگلیسی پکیج');
            await postAndReload('/packages/upsert', payload, ['packages'], 'پکیج ذخیره شد.');
            window.resetPackageForm();
        } catch (err) { tError(err.message); }
    };
    window.resetPackageForm = function resetPackageForm() {
        ['packageCodeInput', 'packageNameEInput', 'packageNamePInput'].forEach((id) => (document.getElementById(id).value = ''));
        setPackageFormMode('new');
        const discInput = document.getElementById('packageDisciplineInput');
        const codeInput = document.getElementById('packageCodeInput');
        if (discInput && codeInput) {
            codeInput.value = nextPackageCodeForDiscipline(discInput.value);
        }
    };
    window.openEditPackageByKey = function openEditPackageByKey(d, p) {
        const item = findBy('packages', (x) => x.discipline_code === decoded(d) && x.package_code === decoded(p)); if (!item) return;
        document.getElementById('packageDisciplineInput').value = item.discipline_code || '';
        document.getElementById('packageCodeInput').value = item.package_code || '';
        document.getElementById('packageNameEInput').value = item.name_e || '';
        document.getElementById('packageNamePInput').value = item.name_p || '';
        setPackageFormMode('edit');
    };
    window.deletePackageSetting = async function deletePackageSetting(d, p) {
        const discipline_code = decoded(d); const package_code = decoded(p);
        if (!confirm(`پکیج ${package_code} در ${discipline_code} حذف شود؟`)) return;
        try { await postAndReload('/packages/delete', { discipline_code, package_code }, ['packages'], 'پکیج حذف شد.'); } catch (err) { tError(err.message); }
    };

    window.saveBlockSetting = async function saveBlockSetting() {
        try {
            const payload = {
                project_code: norm(document.getElementById('blockProjectInput')?.value).toUpperCase(),
                code: norm(document.getElementById('blockCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('blockNameEInput')?.value),
                name_p: norm(document.getElementById('blockNamePInput')?.value),
                sort_order: Number(document.getElementById('blockSortInput')?.value || 0),
                is_active: Boolean(document.getElementById('blockActiveInput')?.checked),
            };
            requireVal(payload.project_code, 'پروژه');
            requireVal(payload.code, 'کد بلوک');
            await postAndReload('/blocks/upsert', payload, ['blocks'], 'بلوک ذخیره شد.');
            window.resetBlockForm();
        } catch (err) { tError(err.message); }
    };
    window.resetBlockForm = function resetBlockForm() {
        ['blockCodeInput', 'blockNameEInput', 'blockNamePInput'].forEach((id) => (document.getElementById(id).value = ''));
        document.getElementById('blockSortInput').value = '0';
        document.getElementById('blockActiveInput').checked = true;
    };
    window.openEditBlockByKey = function openEditBlockByKey(p, c) {
        const item = findBy('blocks', (x) => x.project_code === decoded(p) && x.code === decoded(c)); if (!item) return;
        document.getElementById('blockProjectInput').value = item.project_code || '';
        document.getElementById('blockCodeInput').value = item.code || '';
        document.getElementById('blockNameEInput').value = item.name_e || '';
        document.getElementById('blockNamePInput').value = item.name_p || '';
        document.getElementById('blockSortInput').value = item.sort_order ?? 0;
        document.getElementById('blockActiveInput').checked = Boolean(item.is_active);
    };
    window.deleteBlockSetting = async function deleteBlockSetting(p, c) {
        const project_code = decoded(p); const code = decoded(c);
        if (!confirm(`بلوک ${code} در پروژه ${project_code} غیرفعال شود؟`)) return;
        try { await postAndReload('/blocks/delete', { project_code, code, hard_delete: false }, ['blocks'], 'بلوک غیرفعال شد.'); } catch (err) { tError(err.message); }
    };

    window.saveLevelSetting = async function saveLevelSetting() {
        try {
            const payload = {
                code: norm(document.getElementById('levelCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('levelNameEInput')?.value),
                name_p: norm(document.getElementById('levelNamePInput')?.value),
                sort_order: Number(document.getElementById('levelSortInput')?.value || 0),
            };
            requireVal(payload.code, 'کد سطح');
            await postAndReload('/levels/upsert', payload, ['levels'], 'سطح ذخیره شد.');
            window.resetLevelForm();
        } catch (err) { tError(err.message); }
    };
    window.resetLevelForm = function resetLevelForm() {
        ['levelCodeInput', 'levelNameEInput', 'levelNamePInput'].forEach((id) => (document.getElementById(id).value = ''));
        document.getElementById('levelSortInput').value = '0';
    };
    window.openEditLevelByCode = function openEditLevelByCode(c) {
        const item = findBy('levels', (x) => x.code === decoded(c)); if (!item) return;
        document.getElementById('levelCodeInput').value = item.code || '';
        document.getElementById('levelNameEInput').value = item.name_e || '';
        document.getElementById('levelNamePInput').value = item.name_p || '';
        document.getElementById('levelSortInput').value = item.sort_order ?? 0;
    };
    window.deleteLevelSetting = async function deleteLevelSetting(c) {
        const code = decoded(c);
        if (!confirm(`سطح ${code} حذف شود؟`)) return;
        try { await postAndReload('/levels/delete', { code }, ['levels'], 'سطح حذف شد.'); } catch (err) { tError(err.message); }
    };

    window.saveStatusSetting = async function saveStatusSetting() {
        try {
            const payload = {
                code: norm(document.getElementById('statusCodeInput')?.value).toUpperCase(),
                name: norm(document.getElementById('statusNameInput')?.value),
                description: norm(document.getElementById('statusDescInput')?.value),
                sort_order: Number(document.getElementById('statusSortInput')?.value || 0),
            };
            requireVal(payload.code, 'کد وضعیت');
            requireVal(payload.name, 'نام وضعیت');
            await postAndReload('/statuses/upsert', payload, ['statuses'], 'وضعیت ذخیره شد.');
            window.resetStatusForm();
        } catch (err) { tError(err.message); }
    };
    window.resetStatusForm = function resetStatusForm() {
        ['statusCodeInput', 'statusNameInput', 'statusDescInput'].forEach((id) => (document.getElementById(id).value = ''));
        document.getElementById('statusSortInput').value = '0';
    };
    window.openEditStatusByCode = function openEditStatusByCode(c) {
        const item = findBy('statuses', (x) => x.code === decoded(c)); if (!item) return;
        document.getElementById('statusCodeInput').value = item.code || '';
        document.getElementById('statusNameInput').value = item.name || '';
        document.getElementById('statusDescInput').value = item.description || '';
        document.getElementById('statusSortInput').value = item.sort_order ?? 0;
    };
    window.deleteStatusSetting = async function deleteStatusSetting(c) {
        const code = decoded(c);
        if (!confirm(`وضعیت ${code} حذف شود؟`)) return;
        try { await postAndReload('/statuses/delete', { code }, ['statuses'], 'وضعیت حذف شد.'); } catch (err) { tError(err.message); }
    };

    window.saveCorrespondenceIssuingSetting = async function saveCorrespondenceIssuingSetting() {
        try {
            const payload = {
                code: norm(document.getElementById('issuingCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('issuingNameEInput')?.value) || norm(document.getElementById('issuingNamePInput')?.value),
                name_p: norm(document.getElementById('issuingNamePInput')?.value),
                project_code: norm(document.getElementById('issuingProjectCodeInput')?.value).toUpperCase() || null,
                sort_order: Number(document.getElementById('issuingSortInput')?.value || 0),
                is_active: Boolean(document.getElementById('issuingActiveInput')?.checked),
            };
            requireVal(payload.code, 'Issuing code');
            requireVal(payload.name_e, 'Issuing name');
            await postAndReload('/correspondence-issuing/upsert', payload, ['corr_issuing'], 'Issuing entity saved.');
            window.resetCorrespondenceIssuingForm();
        } catch (err) {
            tError(err.message);
        }
    };
    window.resetCorrespondenceIssuingForm = function resetCorrespondenceIssuingForm() {
        ['issuingCodeInput', 'issuingNameEInput', 'issuingNamePInput'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        const projectInput = document.getElementById('issuingProjectCodeInput');
        if (projectInput) projectInput.value = '';
        const sortInput = document.getElementById('issuingSortInput');
        if (sortInput) sortInput.value = '0';
        const activeInput = document.getElementById('issuingActiveInput');
        if (activeInput) activeInput.checked = true;
    };
    window.openEditCorrespondenceIssuingByCode = function openEditCorrespondenceIssuingByCode(c) {
        const code = decoded(c);
        const item = findBy('corr_issuing', (x) => x.code === code);
        if (!item) return;
        document.getElementById('issuingCodeInput').value = item.code || '';
        document.getElementById('issuingNameEInput').value = item.name_e || '';
        document.getElementById('issuingNamePInput').value = item.name_p || '';
        document.getElementById('issuingProjectCodeInput').value = item.project_code || '';
        document.getElementById('issuingSortInput').value = item.sort_order ?? 0;
        document.getElementById('issuingActiveInput').checked = Boolean(item.is_active);
    };
    window.deleteCorrespondenceIssuingSetting = async function deleteCorrespondenceIssuingSetting(c) {
        const code = decoded(c);
        if (!confirm(`Disable issuing entity ${code}?`)) return;
        try {
            await postAndReload('/correspondence-issuing/delete', { code, hard_delete: false }, ['corr_issuing'], 'Issuing entity disabled.');
        } catch (err) {
            tError(err.message);
        }
    };

    window.saveCorrespondenceCategorySetting = async function saveCorrespondenceCategorySetting() {
        try {
            const payload = {
                code: norm(document.getElementById('corrCategoryCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('corrCategoryNameEInput')?.value) || norm(document.getElementById('corrCategoryNamePInput')?.value),
                name_p: norm(document.getElementById('corrCategoryNamePInput')?.value),
                sort_order: Number(document.getElementById('corrCategorySortInput')?.value || 0),
                is_active: Boolean(document.getElementById('corrCategoryActiveInput')?.checked),
            };
            requireVal(payload.code, 'Category code');
            requireVal(payload.name_e, 'Category name');
            await postAndReload('/correspondence-categories/upsert', payload, ['corr_categories'], 'Correspondence category saved.');
            window.resetCorrespondenceCategoryForm();
        } catch (err) {
            tError(err.message);
        }
    };
    window.resetCorrespondenceCategoryForm = function resetCorrespondenceCategoryForm() {
        ['corrCategoryCodeInput', 'corrCategoryNameEInput', 'corrCategoryNamePInput'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        const sortInput = document.getElementById('corrCategorySortInput');
        if (sortInput) sortInput.value = '0';
        const activeInput = document.getElementById('corrCategoryActiveInput');
        if (activeInput) activeInput.checked = true;
    };
    window.openEditCorrespondenceCategoryByCode = function openEditCorrespondenceCategoryByCode(c) {
        const code = decoded(c);
        const item = findBy('corr_categories', (x) => x.code === code);
        if (!item) return;
        document.getElementById('corrCategoryCodeInput').value = item.code || '';
        document.getElementById('corrCategoryNameEInput').value = item.name_e || '';
        document.getElementById('corrCategoryNamePInput').value = item.name_p || '';
        document.getElementById('corrCategorySortInput').value = item.sort_order ?? 0;
        document.getElementById('corrCategoryActiveInput').checked = Boolean(item.is_active);
    };
    window.deleteCorrespondenceCategorySetting = async function deleteCorrespondenceCategorySetting(c) {
        const code = decoded(c);
        if (!confirm(`Disable correspondence category ${code}?`)) return;
        try {
            await postAndReload('/correspondence-categories/delete', { code, hard_delete: false }, ['corr_categories'], 'Correspondence category disabled.');
        } catch (err) {
            tError(err.message);
        }
    };

    window.initGeneralSettings = initGeneralSettings;
})();
