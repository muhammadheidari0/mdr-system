(() => {
    const API_BASE = '/api/v1/settings';
    const ENTITIES = ['projects', 'mdr', 'phases', 'disciplines', 'packages', 'blocks', 'levels', 'statuses'];

    const STORE = {
        initialized: false,
        loadingPromise: null,
        storagePathsLoaded: false,
        activePage: 'db',
        data: {
            projects: [],
            mdr: [],
            phases: [],
            disciplines: [],
            packages: [],
            blocks: [],
            levels: [],
            statuses: [],
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
                <button class="btn-archive-icon" type="button" ${info.page <= 1 ? 'disabled' : ''} onclick="settingsGotoPage('${entity}', ${info.page - 1})">قبلی</button>
                <span>صفحه ${info.page} از ${info.totalPages}</span>
                <button class="btn-archive-icon" type="button" ${info.page >= info.totalPages ? 'disabled' : ''} onclick="settingsGotoPage('${entity}', ${info.page + 1})">بعدی</button>
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
                        <button class="btn-archive-icon" type="button" onclick="openEditProjectByCode('${encoded(p.code)}')">ویرایش</button>
                        <button class="btn-archive-icon" type="button" onclick="deleteProjectSetting('${encoded(p.code)}')">غیرفعال</button>
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
                        <button class="btn-archive-icon" type="button" onclick="openEditMdrByCode('${encoded(m.code)}')">ویرایش</button>
                        <button class="btn-archive-icon" type="button" onclick="deleteMdrSetting('${encoded(m.code)}')">غیرفعال</button>
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
                        <button class="btn-archive-icon" type="button" onclick="openEditPhaseByCode('${encoded(p.ph_code)}')">ویرایش</button>
                        <button class="btn-archive-icon" type="button" onclick="deletePhaseSetting('${encoded(p.ph_code)}')">حذف</button>
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
                        <button class="btn-archive-icon" type="button" onclick="openEditDisciplineByCode('${encoded(d.code)}')">ویرایش</button>
                        <button class="btn-archive-icon" type="button" onclick="deleteDisciplineSetting('${encoded(d.code)}')">حذف</button>
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
                        <button class="btn-archive-icon" type="button" onclick="openEditPackageByKey('${encoded(p.discipline_code)}','${encoded(p.package_code)}')">ویرایش</button>
                        <button class="btn-archive-icon" type="button" onclick="deletePackageSetting('${encoded(p.discipline_code)}','${encoded(p.package_code)}')">حذف</button>
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
                        <button class="btn-archive-icon" type="button" onclick="openEditBlockByKey('${encoded(b.project_code)}','${encoded(b.code)}')">ویرایش</button>
                        <button class="btn-archive-icon" type="button" onclick="deleteBlockSetting('${encoded(b.project_code)}','${encoded(b.code)}')">غیرفعال</button>
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
                        <button class="btn-archive-icon" type="button" onclick="openEditLevelByCode('${encoded(l.code)}')">ویرایش</button>
                        <button class="btn-archive-icon" type="button" onclick="deleteLevelSetting('${encoded(l.code)}')">حذف</button>
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
                        <button class="btn-archive-icon" type="button" onclick="openEditStatusByCode('${encoded(s.code)}')">ویرایش</button>
                        <button class="btn-archive-icon" type="button" onclick="deleteStatusSetting('${encoded(s.code)}')">حذف</button>
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
            ['projects', 'پروژه'], ['mdr_categories', 'MDR'], ['phases', 'فاز'],
            ['disciplines', 'دیسیپلین'], ['packages', 'پکیج'], ['blocks', 'بلوک'],
            ['levels', 'سطح'], ['statuses', 'وضعیت'],
        ];
        box.innerHTML = cards.map(([k, label]) => `
            <div class="general-overview-card">
                <div class="general-overview-value">${Number(counts[k] || 0)}</div>
                <div class="general-overview-label">${label}</div>
            </div>
        `).join('');
    }

    async function loadStoragePaths(force = false) {
        const mdrInput = document.getElementById('mdrStoragePathInput');
        const corrInput = document.getElementById('correspondenceStoragePathInput');
        if (!mdrInput || !corrInput) return;
        if (STORE.storagePathsLoaded && !force) return;

        const payload = await request(`${API_BASE}/storage-paths`);
        mdrInput.value = norm(payload?.mdr_storage_path);
        corrInput.value = norm(payload?.correspondence_storage_path);
        STORE.storagePathsLoaded = true;
    }

    async function ensureSelects() {
        if (!STORE.data.projects.length) await loadEntity('projects', true);
        if (!STORE.data.disciplines.length) await loadEntity('disciplines', true);
        fillSelect('blockProjectInput', STORE.data.projects, (p) => `${p.code} - ${p.project_name || '-'}`, (p) => p.code);
        fillSelect('packageDisciplineInput', STORE.data.disciplines, (d) => `${d.code} - ${d.name_e || '-'}`, (d) => d.code);

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

    async function loadGeneralPageData(page, force = false) {
        STORE.activePage = page;
        if (page === 'db') {
            await loadOverview();
            await loadStoragePaths(force);
            await loadEntity('projects', force);
            refreshProjectCards();
            return;
        }
        await loadEntity(page, force);
        if (['projects', 'disciplines', 'packages', 'blocks'].includes(page)) await ensureSelects();
    }

    async function initGeneralSettings(force = false) {
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
                await loadGeneralPageData(activeGeneralPage(), force);
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

    window.switchGeneralSettingsPage = async function switchGeneralSettingsPage(page, btnEl = null) {
        document.querySelectorAll('.general-settings-btn').forEach((b) => b.classList.remove('active'));
        document.querySelectorAll('.general-settings-page').forEach((p) => p.classList.remove('active'));
        const btn = btnEl || document.querySelector(`.general-settings-btn[data-general-tab="${page}"]`);
        if (btn) btn.classList.add('active');
        const tab = document.getElementById(`general-page-${page}`);
        if (tab) tab.classList.add('active');
        await loadGeneralPageData(page);
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
            const mdr_storage_path = norm(document.getElementById('mdrStoragePathInput')?.value);
            const correspondence_storage_path = norm(document.getElementById('correspondenceStoragePathInput')?.value);
            requireVal(mdr_storage_path, 'MDR storage path');
            requireVal(correspondence_storage_path, 'Correspondence storage path');

            const payload = await request(`${API_BASE}/storage-paths`, {
                method: 'POST',
                body: JSON.stringify({ mdr_storage_path, correspondence_storage_path }),
            });

            document.getElementById('mdrStoragePathInput').value = norm(payload?.mdr_storage_path || mdr_storage_path);
            document.getElementById('correspondenceStoragePathInput').value = norm(
                payload?.correspondence_storage_path || correspondence_storage_path
            );
            STORE.storagePathsLoaded = true;
            tSuccess('Storage paths saved.');
        } catch (err) {
            tError(err.message);
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

    window.initGeneralSettings = initGeneralSettings;
})();
