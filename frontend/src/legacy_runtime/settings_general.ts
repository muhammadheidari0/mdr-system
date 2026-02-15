// @ts-nocheck
(() => {
    const API_BASE = '/api/v1/settings';
    const ENTITIES = ['projects', 'mdr', 'phases', 'disciplines', 'packages', 'blocks', 'levels', 'statuses', 'corr_issuing', 'corr_categories'];

    const STORE = {
        initialized: false,
        loadingPromise: null,
        storagePathsLoaded: false,
        actionsBound: false,
        activePage: 'db',
        activeDomain: 'all',
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
            ? '<span class="status-badge active">ÙØ¹Ø§Ù„</span>'
            : '<span class="status-badge inactive">ØºÛŒØ±ÙØ¹Ø§Ù„</span>';
    }

    function setLoadingRows(entity, message = 'Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ...') {
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
            <div class="general-pager-left">Ù†Ù…Ø§ÛŒØ´ ${info.from}-${info.to} Ø§Ø² ${info.total}</div>
            <div class="general-pager-right">
                <button class="btn-archive-icon" type="button" ${info.page <= 1 ? 'disabled' : ''} data-general-action="goto-page" data-entity="${esc(entity)}" data-page="${info.page - 1}">Ù‚Ø¨Ù„ÛŒ</button>
                <span>ØµÙØ­Ù‡ ${info.page} Ø§Ø² ${info.totalPages}</span>
                <button class="btn-archive-icon" type="button" ${info.page >= info.totalPages ? 'disabled' : ''} data-general-action="goto-page" data-entity="${esc(entity)}" data-page="${info.page + 1}">Ø¨Ø¹Ø¯ÛŒ</button>
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
            tbody.innerHTML = `<tr><td class="text-center muted" colspan="${meta.colspan}">Ù…ÙˆØ±Ø¯ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯</td></tr>`;
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
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-project" data-code="${esc(encoded(p.code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-project" data-code="${esc(encoded(p.code))}">ØºÛŒØ±ÙØ¹Ø§Ù„</button>
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
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-mdr" data-code="${esc(encoded(m.code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-mdr" data-code="${esc(encoded(m.code))}">ØºÛŒØ±ÙØ¹Ø§Ù„</button>
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
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-phase" data-code="${esc(encoded(p.ph_code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-phase" data-code="${esc(encoded(p.ph_code))}">Ø­Ø°Ù</button>
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
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-discipline" data-code="${esc(encoded(d.code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-discipline" data-code="${esc(encoded(d.code))}">Ø­Ø°Ù</button>
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
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-package" data-discipline-code="${esc(encoded(p.discipline_code))}" data-package-code="${esc(encoded(p.package_code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-package" data-discipline-code="${esc(encoded(p.discipline_code))}" data-package-code="${esc(encoded(p.package_code))}">Ø­Ø°Ù</button>
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
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-block" data-project-code="${esc(encoded(b.project_code))}" data-code="${esc(encoded(b.code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-block" data-project-code="${esc(encoded(b.project_code))}" data-code="${esc(encoded(b.code))}">ØºÛŒØ±ÙØ¹Ø§Ù„</button>
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
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-level" data-code="${esc(encoded(l.code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-level" data-code="${esc(encoded(l.code))}">Ø­Ø°Ù</button>
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
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-status" data-code="${esc(encoded(s.code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-status" data-code="${esc(encoded(s.code))}">Ø­Ø°Ù</button>
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
            let message = `Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯ (${res.status})`;
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
            box.innerHTML = '<div class="text-muted">Ù¾Ø±ÙˆÚ˜Ù‡â€ŒØ§ÛŒ Ø«Ø¨Øª Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª.</div>';
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
        validateStoragePathConflict(false);
        STORE.storagePathsLoaded = true;
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
                setStoragePathConflictError('Ù…Ø³ÛŒØ± MDR Ùˆ Ù…Ø³ÛŒØ± Ù…Ú©Ø§ØªØ¨Ø§Øª Ù†Ø¨Ø§ÛŒØ¯ ÛŒÚ©Ø³Ø§Ù† Ø¨Ø§Ø´Ù†Ø¯.');
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
        const el = document.querySelector('.general-settings-page.active');
        if (!el?.id) return STORE.activePage || 'db';
        return el.id.replace('general-page-', '');
    }

    function isGeneralButtonVisibleForDomain(buttonEl, domain) {
        const buttonDomain = norm(buttonEl?.dataset?.generalDomain || 'common').toLowerCase();
        if (domain === 'all') return true;
        return buttonDomain === domain || buttonDomain === 'common';
    }

    function applyGeneralDomainVisibility(domain = 'all') {
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
        if (page === 'db') {
            await loadOverview();
            await loadStoragePaths(force);
            await loadEntity('projects', force);
            refreshProjectCards();
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
                    window.switchGeneralSettingsDomain(actionEl.dataset.generalDomain || 'all', actionEl);
                    break;
                case 'run-seed':
                    window.localRunSeed();
                    break;
                case 'save-storage-paths':
                    window.saveStoragePaths();
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
            if (!actionEl) return;
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
                await window.switchGeneralSettingsDomain(STORE.activeDomain || 'all', null, force);
            } catch (err) {
                tError(`Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ ØªÙ†Ø¸ÛŒÙ…Ø§Øª Ø¹Ù…ÙˆÙ…ÛŒ: ${err.message}`);
            }
        })();

        STORE.loadingPromise = job.finally(() => {
            STORE.loadingPromise = null;
        });
        return STORE.loadingPromise;
    }

    function requireVal(value, label) {
        if (!norm(value)) throw new Error(`${label} Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª`);
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

    window.switchGeneralSettingsPage = async function switchGeneralSettingsPage(page, btnEl = null, force = false) {
        if (!page) return;
        document.querySelectorAll('.general-settings-btn').forEach((b) => b.classList.remove('active'));
        document.querySelectorAll('.general-settings-page').forEach((p) => p.classList.remove('active'));
        const btn = btnEl || document.querySelector(`.general-settings-btn[data-general-tab="${page}"]`);
        if (btn) btn.classList.add('active');
        const tab = document.getElementById(`general-page-${page}`);
        if (!tab) return;
        tab.classList.add('active');
        await loadGeneralPageData(page, force);
    };

    window.switchGeneralSettingsDomain = async function switchGeneralSettingsDomain(domain = 'all', btnEl = null, force = false) {
        const normalizedDomain = norm(domain).toLowerCase() || 'all';
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
        if (!confirm('Seed Ø§Ø¬Ø±Ø§ Ø´ÙˆØ¯ØŸ Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ù¾Ø§ÛŒÙ‡ Ø¨Ø±ÙˆØ²Ø±Ø³Ø§Ù†ÛŒ Ù…ÛŒâ€ŒØ´ÙˆÙ†Ø¯.')) return;
        try {
            await request(`${API_BASE}/seed`, { method: 'POST' });
            tSuccess('Seed Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø§Ø¬Ø±Ø§ Ø´Ø¯.');
            STORE.initialized = false;
            await initGeneralSettings(true);
        } catch (err) {
            tError(`Seed Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯: ${err.message}`);
        }
    };

    window.saveStoragePaths = async function saveStoragePaths() {
        try {
            bindStoragePathValidation();
            const mdr_storage_path = norm(document.getElementById('mdrStoragePathInput')?.value);
            const correspondence_storage_path = norm(document.getElementById('correspondenceStoragePathInput')?.value);
            requireVal(mdr_storage_path, 'MDR storage path');
            requireVal(correspondence_storage_path, 'Correspondence storage path');
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
            setStoragePathConflictError('');
            STORE.storagePathsLoaded = true;
            tSuccess('Storage paths saved.');
        } catch (err) {
            tError(err.message);
        }
    };

    window.saveProjectSetting = async function saveProjectSetting() {
        try {
            const code = norm(document.getElementById('projectCodeInput')?.value).toUpperCase();
            requireVal(code, 'Ú©Ø¯ Ù¾Ø±ÙˆÚ˜Ù‡');
            const payload = {
                code,
                project_name: norm(document.getElementById('projectNameInput')?.value),
                root_path: norm(document.getElementById('projectRootInput')?.value),
                docnum_template: norm(document.getElementById('projectTemplateInput')?.value),
                is_active: Boolean(document.getElementById('projectActiveInput')?.checked),
            };
            await postAndReload('/projects/upsert', payload, ['projects'], 'Ù¾Ø±ÙˆÚ˜Ù‡ Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm(`Ù¾Ø±ÙˆÚ˜Ù‡ ${code} ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´ÙˆØ¯ØŸ`)) return;
        try { await postAndReload('/projects/delete', { code, hard_delete: false }, ['projects'], 'Ù¾Ø±ÙˆÚ˜Ù‡ ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´Ø¯.'); }
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
            requireVal(payload.code, 'Ú©Ø¯ MDR');
            await postAndReload('/mdr-categories/upsert', payload, ['mdr'], 'MDR Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm(`MDR ${code} ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´ÙˆØ¯ØŸ`)) return;
        try { await postAndReload('/mdr-categories/delete', { code, hard_delete: false }, ['mdr'], 'MDR ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´Ø¯.'); }
        catch (err) { tError(err.message); }
    };

    window.savePhaseSetting = async function savePhaseSetting() {
        try {
            const payload = {
                ph_code: norm(document.getElementById('phaseCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('phaseNameEInput')?.value),
                name_p: norm(document.getElementById('phaseNamePInput')?.value),
            };
            requireVal(payload.ph_code, 'Ú©Ø¯ ÙØ§Ø²');
            requireVal(payload.name_e, 'Ù†Ø§Ù… ÙØ§Ø²');
            await postAndReload('/phases/upsert', payload, ['phases'], 'ÙØ§Ø² Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm(`ÙØ§Ø² ${ph_code} Ø­Ø°Ù Ø´ÙˆØ¯ØŸ`)) return;
        try { await postAndReload('/phases/delete', { ph_code }, ['phases'], 'ÙØ§Ø² Ø­Ø°Ù Ø´Ø¯.'); } catch (err) { tError(err.message); }
    };

    window.saveDisciplineSetting = async function saveDisciplineSetting() {
        try {
            const payload = {
                code: norm(document.getElementById('disciplineCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('disciplineNameEInput')?.value),
                name_p: norm(document.getElementById('disciplineNamePInput')?.value),
            };
            requireVal(payload.code, 'Ú©Ø¯ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†');
            requireVal(payload.name_e, 'Ù†Ø§Ù… Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†');
            await postAndReload('/disciplines/upsert', payload, ['disciplines', 'packages'], 'Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ† Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm(`Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ† ${code} Ø­Ø°Ù Ø´ÙˆØ¯ØŸ`)) return;
        try { await postAndReload('/disciplines/delete', { code }, ['disciplines', 'packages'], 'Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ† Ø­Ø°Ù Ø´Ø¯.'); } catch (err) { tError(err.message); }
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
            requireVal(payload.discipline_code, 'Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†');
            requireVal(payload.package_code, 'Ú©Ø¯ Ù¾Ú©ÛŒØ¬ Ø®ÙˆØ¯Ú©Ø§Ø±');
            requireVal(payload.name_e, 'Ù†Ø§Ù… Ø§Ù†Ú¯Ù„ÛŒØ³ÛŒ Ù¾Ú©ÛŒØ¬');
            await postAndReload('/packages/upsert', payload, ['packages'], 'Ù¾Ú©ÛŒØ¬ Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm(`Ù¾Ú©ÛŒØ¬ ${package_code} Ø¯Ø± ${discipline_code} Ø­Ø°Ù Ø´ÙˆØ¯ØŸ`)) return;
        try { await postAndReload('/packages/delete', { discipline_code, package_code }, ['packages'], 'Ù¾Ú©ÛŒØ¬ Ø­Ø°Ù Ø´Ø¯.'); } catch (err) { tError(err.message); }
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
            requireVal(payload.project_code, 'Ù¾Ø±ÙˆÚ˜Ù‡');
            requireVal(payload.code, 'Ú©Ø¯ Ø¨Ù„ÙˆÚ©');
            await postAndReload('/blocks/upsert', payload, ['blocks'], 'Ø¨Ù„ÙˆÚ© Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm(`Ø¨Ù„ÙˆÚ© ${code} Ø¯Ø± Ù¾Ø±ÙˆÚ˜Ù‡ ${project_code} ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´ÙˆØ¯ØŸ`)) return;
        try { await postAndReload('/blocks/delete', { project_code, code, hard_delete: false }, ['blocks'], 'Ø¨Ù„ÙˆÚ© ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´Ø¯.'); } catch (err) { tError(err.message); }
    };

    window.saveLevelSetting = async function saveLevelSetting() {
        try {
            const payload = {
                code: norm(document.getElementById('levelCodeInput')?.value).toUpperCase(),
                name_e: norm(document.getElementById('levelNameEInput')?.value),
                name_p: norm(document.getElementById('levelNamePInput')?.value),
                sort_order: Number(document.getElementById('levelSortInput')?.value || 0),
            };
            requireVal(payload.code, 'Ú©Ø¯ Ø³Ø·Ø­');
            await postAndReload('/levels/upsert', payload, ['levels'], 'Ø³Ø·Ø­ Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm(`Ø³Ø·Ø­ ${code} Ø­Ø°Ù Ø´ÙˆØ¯ØŸ`)) return;
        try { await postAndReload('/levels/delete', { code }, ['levels'], 'Ø³Ø·Ø­ Ø­Ø°Ù Ø´Ø¯.'); } catch (err) { tError(err.message); }
    };

    window.saveStatusSetting = async function saveStatusSetting() {
        try {
            const payload = {
                code: norm(document.getElementById('statusCodeInput')?.value).toUpperCase(),
                name: norm(document.getElementById('statusNameInput')?.value),
                description: norm(document.getElementById('statusDescInput')?.value),
                sort_order: Number(document.getElementById('statusSortInput')?.value || 0),
            };
            requireVal(payload.code, 'Ú©Ø¯ ÙˆØ¶Ø¹ÛŒØª');
            requireVal(payload.name, 'Ù†Ø§Ù… ÙˆØ¶Ø¹ÛŒØª');
            await postAndReload('/statuses/upsert', payload, ['statuses'], 'ÙˆØ¶Ø¹ÛŒØª Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm(`ÙˆØ¶Ø¹ÛŒØª ${code} Ø­Ø°Ù Ø´ÙˆØ¯ØŸ`)) return;
        try { await postAndReload('/statuses/delete', { code }, ['statuses'], 'ÙˆØ¶Ø¹ÛŒØª Ø­Ø°Ù Ø´Ø¯.'); } catch (err) { tError(err.message); }
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
