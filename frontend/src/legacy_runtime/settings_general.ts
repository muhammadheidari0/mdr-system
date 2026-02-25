// @ts-nocheck
(() => {
    const API_BASE = '/api/v1/settings';
    const ENTITIES = ['projects', 'mdr', 'phases', 'disciplines', 'packages', 'blocks', 'levels', 'statuses', 'corr_issuing', 'corr_categories'];

    const STORE = {
        initialized: false,
        loadingPromise: null,
        bulkRegistered: false,
        storagePathsLoaded: false,
        storagePolicyLoaded: false,
        storageIntegrationsLoaded: false,
        storageBimRevitLoaded: false,
        siteCacheLoaded: false,
        actionsBound: false,
        activePage: 'db_sync',
        activeDomain: 'common',
        storageWizard: {
            activeStep: 'paths',
            dirty: {
                paths: false,
                policy: false,
                site_cache: false,
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
            activeListTab: 'cidr',
            tokenMulti: {},
        },
        openprojectImport: {
            activeTab: 'connection',
            selectedRunId: 0,
            lastValidatedRunId: 0,
            pollingTimer: null,
        },
        integrationsProviderTab: 'openproject',
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

    const ENTITY_TABLE_IDS = {
        projects: 'settingsProjectsTable',
        mdr: 'settingsMdrTable',
        phases: 'settingsPhasesTable',
        disciplines: 'settingsDisciplinesTable',
        packages: 'settingsPackagesTable',
        blocks: 'settingsBlocksTable',
        levels: 'settingsLevelsTable',
        statuses: 'settingsStatusesTable',
        corr_issuing: 'settingsCorrIssuingTable',
        corr_categories: 'settingsCorrCategoriesTable',
    };

    const SITE_CACHE_BULK_ACTION_ACTIVATE = 'site-cache-profiles-bulk-activate';
    const SITE_CACHE_BULK_ACTION_DEACTIVATE = 'site-cache-profiles-bulk-deactivate';

    const STORAGE_WIZARD_STEPS = ['paths', 'policy', 'site_cache'];
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
    const SITE_CACHE_TOKEN_MULTI_IDS = ['siteCacheRuleProjectInput', 'siteCacheRuleDisciplineInput', 'siteCacheRulePackageInput'];
    const SITE_CACHE_TOKEN_MULTI_PLACEHOLDER = {
        siteCacheRuleProjectInput: 'Ø§Ù†ØªØ®Ø§Ø¨ Ù¾Ø±ÙˆÚ˜Ù‡',
        siteCacheRuleDisciplineInput: 'Ø§Ù†ØªØ®Ø§Ø¨ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†',
        siteCacheRulePackageInput: 'Ø§Ù†ØªØ®Ø§Ø¨ Ù¾Ú©ÛŒØ¬',
    };

    function tSuccess(msg) { if (window.UI?.success) window.UI.success(msg); else alert(msg); }
    function tError(msg) { if (window.UI?.error) window.UI.error(msg); else alert(msg); }
    function tWarning(msg) {
        if (window.UI?.warning) {
            window.UI.warning(msg);
            return;
        }
        tError(msg);
    }
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

    function entityTableId(entity) {
        return ENTITY_TABLE_IDS[entity] || '';
    }

    function entityBulkKey(entity, row) {
        if (!row || typeof row !== 'object') return '';
        if (entity === 'phases') return norm(row.ph_code).toUpperCase();
        if (entity === 'packages') {
            return `${norm(row.discipline_code).toUpperCase()}::${norm(row.package_code).toUpperCase()}`;
        }
        if (entity === 'blocks') {
            return `${norm(row.project_code).toUpperCase()}::${norm(row.code).toUpperCase()}`;
        }
        return norm(row.code).toUpperCase();
    }

    function entityBulkLabel(entity, row) {
        if (!row || typeof row !== 'object') return '-';
        if (entity === 'phases') return norm(row.ph_code) || '-';
        if (entity === 'packages') return `${norm(row.discipline_code)}/${norm(row.package_code)}`;
        if (entity === 'blocks') return `${norm(row.project_code)}/${norm(row.code)}`;
        return norm(row.code) || '-';
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
                <tr data-bulk-key="${esc(entityBulkKey('projects', p))}">
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
                <tr data-bulk-key="${esc(entityBulkKey('mdr', m))}">
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
                <tr data-bulk-key="${esc(entityBulkKey('phases', p))}">
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
                <tr data-bulk-key="${esc(entityBulkKey('disciplines', d))}">
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
                <tr data-bulk-key="${esc(entityBulkKey('packages', p))}">
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
                <tr data-bulk-key="${esc(entityBulkKey('blocks', b))}">
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
                <tr data-bulk-key="${esc(entityBulkKey('levels', l))}">
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
                <tr data-bulk-key="${esc(entityBulkKey('statuses', s))}">
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
                <tr data-bulk-key="${esc(entityBulkKey('corr_issuing', s))}">
                    <td>${esc(s.code)}</td>
                    <td>${esc(s.name_e || s.name_p || '-')}</td>
                    <td>${esc(s.project_code || '-')}</td>
                    <td>${boolBadge(Boolean(s.is_active))}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-corr-issuing" data-code="${esc(encoded(s.code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-corr-issuing" data-code="${esc(encoded(s.code))}">ØºÛŒØ±ÙØ¹Ø§Ù„</button>
                    `)}</td>
                </tr>
            `).join('');
        } else if (entity === 'corr_categories') {
            html = info.rows.map((s) => `
                <tr data-bulk-key="${esc(entityBulkKey('corr_categories', s))}">
                    <td>${esc(s.code)}</td>
                    <td>${esc(s.name_e || s.name_p || '-')}</td>
                    <td>${boolBadge(Boolean(s.is_active))}</td>
                    <td>${esc(s.sort_order ?? 0)}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-corr-category" data-code="${esc(encoded(s.code))}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon" type="button" data-general-action="delete-corr-category" data-code="${esc(encoded(s.code))}">ØºÛŒØ±ÙØ¹Ø§Ù„</button>
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
            let details = null;
            try {
                const j = await res.clone().json();
                details = j?.detail;
                if (Array.isArray(details) && details.length) {
                    const lines = details
                        .map((item) => {
                            if (!item || typeof item !== 'object') return norm(item);
                            const field = norm(item.field || item.loc || '');
                            const text = norm(item.message || item.detail || item.msg || '');
                            if (field && text) return `${field}: ${text}`;
                            return text || JSON.stringify(item);
                        })
                        .filter(Boolean);
                    if (lines.length) message = lines.join(' | ');
                } else {
                    message = j.detail || j.message || message;
                }
            } catch (_) {
                try { message = await res.text(); } catch (_) {}
            }
            const err = new Error(message);
            if (Array.isArray(details)) err.details = details;
            throw err;
        }
        return res.json();
    }

    function generalBulkBridge() {
        if (!window.TableBulk || typeof window.TableBulk !== 'object') return null;
        if (typeof window.TableBulk.register !== 'function') return null;
        return window.TableBulk;
    }

    function summarizeFailures(items = []) {
        if (!Array.isArray(items) || !items.length) return '';
        const head = items.slice(0, 3).join(' | ');
        return items.length > 3 ? `${head} | +${items.length - 3} more` : head;
    }

    function rowsBySelectedBulkKeys(entity, selectedKeys = []) {
        const keySet = new Set((selectedKeys || []).map((value) => norm(value).toUpperCase()).filter(Boolean));
        if (!keySet.size) return [];
        return (STORE.data[entity] || []).filter((row) => keySet.has(entityBulkKey(entity, row).toUpperCase()));
    }

    function bulkActionMetaForEntity(entity) {
        switch (entity) {
            case 'projects':
                return {
                    id: 'general-bulk-projects-deactivate',
                    label: 'Deactivate selected projects',
                    confirm: (count) => `Deactivate ${count} selected project(s)?`,
                    endpoint: '/projects/delete',
                    reloadEntities: ['projects'],
                    successText: 'project(s) deactivated.',
                };
            case 'mdr':
                return {
                    id: 'general-bulk-mdr-deactivate',
                    label: 'Deactivate selected MDR categories',
                    confirm: (count) => `Deactivate ${count} selected MDR category(ies)?`,
                    endpoint: '/mdr-categories/delete',
                    reloadEntities: ['mdr'],
                    successText: 'MDR category(ies) deactivated.',
                };
            case 'phases':
                return {
                    id: 'general-bulk-phases-delete',
                    label: 'Delete selected phases',
                    confirm: (count) => `Delete ${count} selected phase(s)?`,
                    endpoint: '/phases/delete',
                    reloadEntities: ['phases'],
                    successText: 'phase(s) deleted.',
                };
            case 'disciplines':
                return {
                    id: 'general-bulk-disciplines-delete',
                    label: 'Delete selected disciplines',
                    confirm: (count) => `Delete ${count} selected discipline(s)?`,
                    endpoint: '/disciplines/delete',
                    reloadEntities: ['disciplines', 'packages'],
                    successText: 'discipline(s) deleted.',
                };
            case 'packages':
                return {
                    id: 'general-bulk-packages-delete',
                    label: 'Delete selected packages',
                    confirm: (count) => `Delete ${count} selected package(s)?`,
                    endpoint: '/packages/delete',
                    reloadEntities: ['packages'],
                    successText: 'package(s) deleted.',
                };
            case 'blocks':
                return {
                    id: 'general-bulk-blocks-deactivate',
                    label: 'Deactivate selected blocks',
                    confirm: (count) => `Deactivate ${count} selected block(s)?`,
                    endpoint: '/blocks/delete',
                    reloadEntities: ['blocks'],
                    successText: 'block(s) deactivated.',
                };
            case 'levels':
                return {
                    id: 'general-bulk-levels-delete',
                    label: 'Delete selected levels',
                    confirm: (count) => `Delete ${count} selected level(s)?`,
                    endpoint: '/levels/delete',
                    reloadEntities: ['levels'],
                    successText: 'level(s) deleted.',
                };
            case 'statuses':
                return {
                    id: 'general-bulk-statuses-delete',
                    label: 'Delete selected statuses',
                    confirm: (count) => `Delete ${count} selected status(es)?`,
                    endpoint: '/statuses/delete',
                    reloadEntities: ['statuses'],
                    successText: 'status(es) deleted.',
                };
            case 'corr_issuing':
                return {
                    id: 'general-bulk-corr-issuing-deactivate',
                    label: 'Deactivate selected issuing entities',
                    confirm: (count) => `Deactivate ${count} selected issuing entit(ies)?`,
                    endpoint: '/correspondence-issuing/delete',
                    reloadEntities: ['corr_issuing'],
                    successText: 'issuing entit(ies) deactivated.',
                };
            case 'corr_categories':
                return {
                    id: 'general-bulk-corr-categories-deactivate',
                    label: 'Deactivate selected correspondence categories',
                    confirm: (count) => `Deactivate ${count} selected correspondence category(ies)?`,
                    endpoint: '/correspondence-categories/delete',
                    reloadEntities: ['corr_categories'],
                    successText: 'correspondence category(ies) deactivated.',
                };
            default:
                return null;
        }
    }

    function entityBulkPayloadForMutation(entity, row) {
        switch (entity) {
            case 'projects':
                return { code: norm(row?.code).toUpperCase(), hard_delete: false };
            case 'mdr':
                return { code: norm(row?.code).toUpperCase(), hard_delete: false };
            case 'phases':
                return { ph_code: norm(row?.ph_code).toUpperCase() };
            case 'disciplines':
                return { code: norm(row?.code).toUpperCase() };
            case 'packages':
                return {
                    discipline_code: norm(row?.discipline_code).toUpperCase(),
                    package_code: norm(row?.package_code).toUpperCase(),
                };
            case 'blocks':
                return {
                    project_code: norm(row?.project_code).toUpperCase(),
                    code: norm(row?.code).toUpperCase(),
                    hard_delete: false,
                };
            case 'levels':
                return { code: norm(row?.code).toUpperCase() };
            case 'statuses':
                return { code: norm(row?.code).toUpperCase() };
            case 'corr_issuing':
                return { code: norm(row?.code).toUpperCase(), hard_delete: false };
            case 'corr_categories':
                return { code: norm(row?.code).toUpperCase(), hard_delete: false };
            default:
                return null;
        }
    }

    async function reloadEntitiesAfterMutation(reloadEntities = []) {
        for (const entity of reloadEntities) {
            await loadEntity(entity, true);
        }
        if (reloadEntities.includes('projects')) refreshProjectCards();
        if (reloadEntities.includes('projects') || reloadEntities.includes('disciplines')) await ensureSelects();
        if (reloadEntities.some((entity) => ['projects', 'mdr', 'phases', 'disciplines', 'statuses'].includes(entity))) {
            refreshTransmittalConfigSummary();
        }
        if (STORE.siteCacheLoaded && reloadEntities.some((entity) => ['projects', 'disciplines', 'packages'].includes(entity))) {
            fillSiteCacheRuleFilterOptions();
        }
        await loadOverview();
    }

    async function runEntityBulkAction(entity, selectedKeys) {
        const meta = bulkActionMetaForEntity(entity);
        if (!meta) return;

        const rows = rowsBySelectedBulkKeys(entity, selectedKeys);
        if (!rows.length) {
            tWarning('No eligible rows selected.');
            return;
        }
        if (!confirm(meta.confirm(rows.length))) return;

        const failures = [];
        let success = 0;
        for (const row of rows) {
            const payload = entityBulkPayloadForMutation(entity, row);
            if (!payload) {
                failures.push(`${entityBulkLabel(entity, row)}: invalid payload`);
                continue;
            }
            try {
                await request(`${API_BASE}${meta.endpoint}`, {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
                success += 1;
            } catch (err) {
                failures.push(`${entityBulkLabel(entity, row)}: ${err?.message || 'Request failed'}`);
            }
        }

        if (success > 0) {
            const bulk = generalBulkBridge();
            const tableId = entityTableId(entity);
            if (bulk && tableId && typeof bulk.clearSelection === 'function') {
                bulk.clearSelection(tableId);
            }
            await reloadEntitiesAfterMutation(meta.reloadEntities || []);
            tSuccess(`${success} ${meta.successText}`);
        }
        if (failures.length > 0) {
            tWarning(`${failures.length} operation(s) failed. ${summarizeFailures(failures)}`);
        }
    }

    async function runSiteCacheProfilesBulk(actionId, selectedKeys) {
        const ids = (selectedKeys || [])
            .map((value) => Number(value))
            .filter((value) => Number.isFinite(value) && value > 0)
            .map((value) => Math.trunc(value));
        if (!ids.length) {
            tWarning('No Site Cache profile selected.');
            return;
        }

        const idSet = new Set(ids.map((value) => String(value)));
        const selectedProfiles = (STORE.siteCache.profiles || [])
            .filter((item) => idSet.has(String(Number(item?.id || 0))));
        if (!selectedProfiles.length) {
            tWarning('Selected Site Cache profiles are no longer available.');
            return;
        }

        let targetRows = selectedProfiles;
        let confirmMessage = '';
        let requestTask = null;
        let successText = '';

        if (actionId === SITE_CACHE_BULK_ACTION_DEACTIVATE) {
            targetRows = selectedProfiles.filter((item) => Boolean(item?.is_active));
            confirmMessage = `Deactivate ${targetRows.length} selected Site Cache profile(s)?`;
            successText = 'profile(s) deactivated.';
            requestTask = (item) => request(`${API_BASE}/site-cache/profiles/delete`, {
                method: 'POST',
                body: JSON.stringify({ id: Number(item?.id || 0), hard_delete: false }),
            });
        } else if (actionId === SITE_CACHE_BULK_ACTION_ACTIVATE) {
            targetRows = selectedProfiles.filter((item) => !Boolean(item?.is_active));
            confirmMessage = `Activate ${targetRows.length} selected Site Cache profile(s)?`;
            successText = 'profile(s) activated.';
            requestTask = (item) => request(`${API_BASE}/site-cache/profiles/upsert`, {
                method: 'POST',
                body: JSON.stringify({
                    id: Number(item?.id || 0),
                    code: norm(item?.code).toUpperCase(),
                    name: norm(item?.name),
                    project_code: norm(item?.project_code).toUpperCase() || null,
                    local_root_path: norm(item?.local_root_path) || null,
                    fallback_mode: norm(item?.fallback_mode).toLowerCase() || 'local_first',
                    is_active: true,
                }),
            });
        }

        if (!requestTask) {
            tWarning('Unknown Site Cache bulk action.');
            return;
        }
        if (!targetRows.length) {
            tWarning('No eligible Site Cache profile found for this action.');
            return;
        }
        if (!confirm(confirmMessage)) return;

        const failures = [];
        let success = 0;
        for (const item of targetRows) {
            try {
                await requestTask(item);
                success += 1;
            } catch (err) {
                const code = norm(item?.code) || String(item?.id || '-');
                failures.push(`${code}: ${err?.message || 'Request failed'}`);
            }
        }

        if (success > 0) {
            const bulk = generalBulkBridge();
            if (bulk && typeof bulk.clearSelection === 'function') {
                bulk.clearSelection('settingsSiteCacheProfilesTable');
            }
            await loadSiteCache(true);
            tSuccess(`${success} ${successText}`);
        }
        if (failures.length > 0) {
            tWarning(`${failures.length} operation(s) failed. ${summarizeFailures(failures)}`);
        }
    }

    function registerGeneralBulkActions() {
        if (STORE.bulkRegistered) return;
        const bulk = generalBulkBridge();
        if (!bulk) return;

        for (const entity of ENTITIES) {
            const meta = bulkActionMetaForEntity(entity);
            const tableId = entityTableId(entity);
            if (!meta || !tableId) continue;
            bulk.register({
                tableId,
                actions: [{ id: meta.id, label: meta.label }],
                getRowKey(row) {
                    return row && row.dataset ? row.dataset.bulkKey : '';
                },
                onAction({ actionId, selectedKeys }) {
                    if (actionId !== meta.id) return Promise.resolve();
                    return runEntityBulkAction(entity, selectedKeys);
                },
            });
        }

        bulk.register({
            tableId: 'settingsSiteCacheProfilesTable',
            actions: [
                { id: SITE_CACHE_BULK_ACTION_ACTIVATE, label: 'Activate selected site cache profiles' },
                { id: SITE_CACHE_BULK_ACTION_DEACTIVATE, label: 'Deactivate selected site cache profiles' },
            ],
            getRowKey(row) {
                return row && row.dataset ? row.dataset.bulkKey : '';
            },
            onAction({ actionId, selectedKeys }) {
                return runSiteCacheProfilesBulk(actionId, selectedKeys);
            },
        });

        STORE.bulkRegistered = true;
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
        box.innerHTML = '<div class="text-muted">Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ...</div>';
        const data = await request(`${API_BASE}/overview`);
        const counts = data.counts || {};
        const cards = [
            ['projects', 'Ù¾Ø±ÙˆÚ˜Ù‡'],
            ['mdr_categories', 'MDR'],
            ['phases', 'ÙØ§Ø²'],
            ['disciplines', 'Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†'],
            ['packages', 'Ù¾Ú©ÛŒØ¬'],
            ['blocks', 'Ø¨Ù„ÙˆÚ©'],
            ['levels', 'Ø³Ø·Ø­'],
            ['statuses', 'ÙˆØ¶Ø¹ÛŒØª'],
            ['issuing_entities', 'Ù…Ø±Ø¬Ø¹ ØµØ¯ÙˆØ±'],
            ['correspondence_categories', 'Ø¯Ø³ØªÙ‡ Ù…Ú©Ø§ØªØ¨Ø§Øª'],
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
            ['projects', 'Ù¾Ø±ÙˆÚ˜Ù‡'],
            ['mdr', 'MDR'],
            ['phases', 'ÙØ§Ø²'],
            ['disciplines', 'Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†'],
            ['statuses', 'ÙˆØ¶Ø¹ÛŒØª'],
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
            const canSaveStep = step !== 'site_cache';
            saveBtn.disabled = !canSaveStep;
            const dirty = canSaveStep ? Boolean(STORE.storageWizard.dirty[step]) : false;
            saveBtn.textContent = canSaveStep
                ? (dirty ? 'Ø°Ø®ÛŒØ±Ù‡ Ù…Ø±Ø­Ù„Ù‡ Ø¬Ø§Ø±ÛŒ *' : 'Ø°Ø®ÛŒØ±Ù‡ Ù…Ø±Ø­Ù„Ù‡ Ø¬Ø§Ø±ÛŒ')
                : 'Ù…Ø±Ø­Ù„Ù‡ Ø¬Ø§Ø±ÛŒ Ø°Ø®ÛŒØ±Ù‡ Ù…Ø³ØªÙ‚Ù„ Ù†Ø¯Ø§Ø±Ø¯';
        }
    }

    function setStorageWizardStep(step, opts = {}) {
        const targetStep = STORAGE_WIZARD_STEPS.includes(step) ? step : 'paths';
        const force = Boolean(opts.force);
        const currentStep = STORE.storageWizard.activeStep || 'paths';
        if (!force && currentStep !== targetStep && STORE.storageWizard.dirty[currentStep]) {
            const ok = confirm('ØªØºÛŒÛŒØ±Ø§Øª Ø§ÛŒÙ† Ù…Ø±Ø­Ù„Ù‡ Ø°Ø®ÛŒØ±Ù‡ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª. Ø¢ÛŒØ§ Ù…Ø§ÛŒÙ„ Ø¨Ù‡ ØªØºÛŒÛŒØ± Ù…Ø±Ø­Ù„Ù‡ Ù‡Ø³ØªÛŒØ¯ØŸ');
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
        tSuccess('ØªÙ†Ø¸ÛŒÙ…Ø§Øª Site Cache Ø¨Ø§ Ø§Ú©Ø´Ù†â€ŒÙ‡Ø§ÛŒ Ø¯Ø§Ø®Ù„ÛŒ Ù‡Ù…ÛŒÙ† ØµÙØ­Ù‡ Ø°Ø®ÛŒØ±Ù‡ Ù…ÛŒâ€ŒØ´ÙˆØ¯.');
    }

    function stopOpenProjectImportPolling() {
        const timer = STORE.openprojectImport?.pollingTimer;
        if (timer) {
            clearTimeout(timer);
            STORE.openprojectImport.pollingTimer = null;
        }
    }

    function setOpenProjectImportSummary(message = '', level = 'info') {
        const box = document.getElementById('storageOpenProjectImportSummary');
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

    function setOpenProjectImportProgress(total = 0, done = 0, statusCode = '') {
        const wrap = document.getElementById('storageOpenProjectImportProgressWrap');
        const bar = document.getElementById('storageOpenProjectImportProgressBar');
        const text = document.getElementById('storageOpenProjectImportProgressText');
        const safeTotal = Math.max(0, Number(total) || 0);
        const safeDone = Math.max(0, Number(done) || 0);
        if (!wrap || !bar || !text) return;
        if (!safeTotal) {
            wrap.style.display = 'none';
            bar.style.width = '0%';
            text.textContent = '';
            return;
        }
        const pct = Math.max(0, Math.min(100, Math.round((safeDone / safeTotal) * 100)));
        wrap.style.display = 'block';
        bar.style.width = `${pct}%`;
        text.textContent = `پیشرفت: ${safeDone} از ${safeTotal} (${pct}%)${statusCode ? ` | ${statusCode}` : ''}`;
    }

    function setOpenProjectSubTab(nextTab = 'connection') {
        const activeTab = ['connection', 'project-import', 'import', 'logs'].includes(String(nextTab || '').toLowerCase())
            ? String(nextTab || '').toLowerCase()
            : 'connection';
        STORE.openprojectImport.activeTab = activeTab;
        document.querySelectorAll('.storage-openproject-subtab[data-op-tab]').forEach((btn) => {
            const key = String(btn?.dataset?.opTab || '').toLowerCase();
            const isActive = key === activeTab;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        document.querySelectorAll('[data-op-tab-content]').forEach((panel) => {
            const key = String(panel?.dataset?.opTabContent || '').toLowerCase();
            const isActive = key === activeTab;
            panel.classList.toggle('active', isActive);
            panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        });
    }

    function setIntegrationsProviderTab(nextTab = 'openproject') {
        const activeTab = ['openproject', 'google', 'nextcloud', 'bim'].includes(String(nextTab || '').toLowerCase())
            ? String(nextTab || '').toLowerCase()
            : 'openproject';
        STORE.integrationsProviderTab = activeTab;
        document.querySelectorAll('.integrations-provider-tab[data-integrations-provider-tab]').forEach((btn) => {
            const key = String(btn?.dataset?.integrationsProviderTab || '').toLowerCase();
            const isActive = key === activeTab;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        document.querySelectorAll('[data-integrations-provider-panel]').forEach((panel) => {
            const key = String(panel?.dataset?.integrationsProviderPanel || '').toLowerCase();
            const isActive = key === activeTab;
            panel.classList.toggle('active', isActive);
            panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        });
    }

    function updateOpenProjectTokenSavedState(tokenSource = 'none', tokenValue = '') {
        const tokenSavedState = document.getElementById('storageOpenProjectTokenSavedState');
        if (!tokenSavedState) return;
        const source = norm(tokenSource).toLowerCase();
        const hasTypedToken = Boolean(norm(tokenValue));
        let state = 'none';
        let text = 'Token not saved';
        if (source === 'env') {
            state = 'env';
            text = 'Token managed by environment';
        } else if (source === 'settings') {
            state = 'settings';
            text = 'Token saved';
        }
        if (hasTypedToken) {
            state = 'pending';
            text = source === 'settings'
                ? 'New token entered (not saved yet)'
                : 'Token entered (not saved yet)';
        }
        tokenSavedState.dataset.tokenSavedState = state;
        tokenSavedState.textContent = text;
    }

    function updateStorageIntegrationsFieldState() {
        const mirrorProvider = document.getElementById('storageMirrorProviderSelect');
        const googleEnabled = document.getElementById('storageGoogleDriveEnabledInput');
        const googleDriveEnabled = document.getElementById('storageGoogleDriveDriveEnabledInput');
        const googleGmailEnabled = document.getElementById('storageGoogleGmailEnabledInput');
        const googleCalendarEnabled = document.getElementById('storageGoogleCalendarEnabledInput');
        const googleOauthClientId = document.getElementById('storageGoogleOauthClientIdInput');
        const googleOauthClientSecret = document.getElementById('storageGoogleOauthClientSecretInput');
        const googleOauthRefreshToken = document.getElementById('storageGoogleOauthRefreshTokenInput');
        const googleDriveId = document.getElementById('storageGoogleDriveDriveIdInput');
        const googleRootFolderId = document.getElementById('storageGoogleDriveRootFolderInput');
        const googleSenderEmail = document.getElementById('storageGoogleSenderEmailInput');
        const googleCalendarId = document.getElementById('storageGoogleCalendarIdInput');

        const googleOauthClientIdWrap = document.getElementById('storageGoogleOauthClientIdWrap');
        const googleOauthClientSecretWrap = document.getElementById('storageGoogleOauthClientSecretWrap');
        const googleOauthRefreshTokenWrap = document.getElementById('storageGoogleOauthRefreshTokenWrap');
        const googleDriveWrap = document.getElementById('storageGoogleDriveDriveIdWrap');
        const googleRootFolderWrap = document.getElementById('storageGoogleDriveRootFolderWrap');
        const googleSenderEmailWrap = document.getElementById('storageGoogleSenderEmailWrap');
        const googleCalendarWrap = document.getElementById('storageGoogleCalendarIdWrap');

        const openprojectEnabled = document.getElementById('storageOpenProjectEnabledInput');
        const openprojectBaseUrl = document.getElementById('storageOpenProjectBaseUrlInput');
        const openprojectToken = document.getElementById('storageOpenProjectApiTokenInput');
        const openprojectWp = document.getElementById('storageOpenProjectDefaultWpInput');
        const openprojectSkipSsl = document.getElementById('storageOpenProjectSkipSslVerifyInput');
        const openprojectProjectRef = document.getElementById('storageOpenProjectProjectRefInput');
        const openprojectProjectMaxItems = document.getElementById('storageOpenProjectProjectImportMaxItemsInput');
        const openprojectProjectPageSize = document.getElementById('storageOpenProjectProjectImportPageSizeInput');

        const openprojectWrap = document.getElementById('storageOpenProjectDefaultWpWrap');
        const openprojectBaseUrlWrap = document.getElementById('storageOpenProjectBaseUrlWrap');
        const openprojectTokenWrap = document.getElementById('storageOpenProjectTokenWrap');
        const openprojectSslWrap = document.getElementById('storageOpenProjectSslWrap');
        const openprojectSslHint = document.getElementById('storageOpenProjectSslManagedHint');
        const openprojectSslWarning = document.getElementById('storageOpenProjectSkipSslWarning');
        const openprojectSyncBtn = document.getElementById('storageOpenProjectSyncRunBtn');
        const gdriveSyncBtn = document.getElementById('storageGoogleDriveSyncRunBtn');
        const tokenBadge = document.getElementById('storageOpenProjectTokenSourceBadge');
        const tokenHint = document.getElementById('storageOpenProjectTokenManagedHint');
        const nextcloudEnabled = document.getElementById('storageNextcloudEnabledInput');
        const nextcloudBaseUrl = document.getElementById('storageNextcloudBaseUrlInput');
        const nextcloudUsername = document.getElementById('storageNextcloudUsernameInput');
        const nextcloudAppPassword = document.getElementById('storageNextcloudAppPasswordInput');
        const nextcloudRootPath = document.getElementById('storageNextcloudRootPathInput');
        const nextcloudSkipSsl = document.getElementById('storageNextcloudSkipSslVerifyInput');
        const nextcloudBaseUrlWrap = document.getElementById('storageNextcloudBaseUrlWrap');
        const nextcloudUsernameWrap = document.getElementById('storageNextcloudUsernameWrap');
        const nextcloudRootPathWrap = document.getElementById('storageNextcloudRootPathWrap');
        const nextcloudTokenWrap = document.getElementById('storageNextcloudTokenWrap');
        const nextcloudSslWrap = document.getElementById('storageNextcloudSslWrap');
        const nextcloudCredentialBadge = document.getElementById('storageNextcloudCredentialSourceBadge');
        const nextcloudCredentialHint = document.getElementById('storageNextcloudCredentialManagedHint');
        const nextcloudSslHint = document.getElementById('storageNextcloudSslManagedHint');
        const nextcloudSslWarning = document.getElementById('storageNextcloudSkipSslWarning');
        const nextcloudSyncBtn = document.getElementById('storageNextcloudSyncRunBtn');
        const bimEnabled = document.getElementById('storageBimRevitEnabledInput');
        const bimRequireSignature = document.getElementById('storageBimRevitRequireSignatureInput');
        const bimEndpoint = document.getElementById('storageBimRevitApiEndpointInput');
        const bimKeyId = document.getElementById('storageBimRevitPluginKeyIdInput');
        const bimSecret = document.getElementById('storageBimRevitPluginSecretInput');
        const bimDefaultCategory = document.getElementById('storageBimRevitDefaultCategoryIdInput');
        const bimDefaultFolder = document.getElementById('storageBimRevitDefaultFolderIdInput');
        const bimAllowedMime = document.getElementById('storageBimRevitAllowedMimeInput');
        const bimMaxBatch = document.getElementById('storageBimRevitMaxBatchSizeInput');
        const bimSecretBadge = document.getElementById('storageBimRevitSecretStateBadge');
        const executeBtn = document.getElementById('storageOpenProjectImportExecuteBtn');
        const tokenSource = norm(tokenBadge?.dataset?.tokenSource || 'none').toLowerCase();
        const sslSource = norm(openprojectSkipSsl?.dataset?.sslSource || 'env_default').toLowerCase();
        const sslForceActive = String(openprojectSkipSsl?.dataset?.sslForceActive || '').toLowerCase() === 'true';
        const envManagedToken = tokenSource === 'env';
        const envManagedSsl = sslForceActive || sslSource === 'env_force';
        const nextcloudCredentialSource = norm(nextcloudCredentialBadge?.dataset?.tokenSource || 'none').toLowerCase();
        const nextcloudSslSource = norm(nextcloudSkipSsl?.dataset?.sslSource || 'env_default').toLowerCase();
        const nextcloudSslForceActive = String(nextcloudSkipSsl?.dataset?.sslForceActive || '').toLowerCase() === 'true';
        const nextcloudEnvManagedCred = nextcloudCredentialSource === 'env';
        const nextcloudEnvManagedSsl = nextcloudSslForceActive || nextcloudSslSource === 'env_force';

        const googleOn = Boolean(googleEnabled?.checked);
        const googleDriveOn = googleOn && Boolean(googleDriveEnabled?.checked);
        const googleGmailOn = googleOn && Boolean(googleGmailEnabled?.checked);
        const googleCalendarOn = googleOn && Boolean(googleCalendarEnabled?.checked);
        const openprojectOn = Boolean(openprojectEnabled?.checked);
        const nextcloudOn = Boolean(nextcloudEnabled?.checked);
        const bimOn = Boolean(bimEnabled?.checked);
        const bimSignatureOn = bimOn && Boolean(bimRequireSignature?.checked);
        const readyForExecute = openprojectOn && Number(STORE.openprojectImport?.lastValidatedRunId || 0) > 0;

        if (mirrorProvider) mirrorProvider.disabled = false;
        if (googleOauthClientId) googleOauthClientId.disabled = !googleOn;
        if (googleOauthClientSecret) googleOauthClientSecret.disabled = !googleOn;
        if (googleOauthRefreshToken) googleOauthRefreshToken.disabled = !googleOn;
        if (googleDriveId) googleDriveId.disabled = !googleDriveOn;
        if (googleRootFolderId) googleRootFolderId.disabled = !googleDriveOn;
        if (googleSenderEmail) googleSenderEmail.disabled = !googleGmailOn;
        if (googleCalendarId) googleCalendarId.disabled = !googleCalendarOn;

        if (googleOauthClientIdWrap) googleOauthClientIdWrap.classList.toggle('is-disabled', !googleOn);
        if (googleOauthClientSecretWrap) googleOauthClientSecretWrap.classList.toggle('is-disabled', !googleOn);
        if (googleOauthRefreshTokenWrap) googleOauthRefreshTokenWrap.classList.toggle('is-disabled', !googleOn);
        if (googleDriveWrap) googleDriveWrap.classList.toggle('is-disabled', !googleDriveOn);
        if (googleRootFolderWrap) googleRootFolderWrap.classList.toggle('is-disabled', !googleDriveOn);
        if (googleSenderEmailWrap) googleSenderEmailWrap.classList.toggle('is-disabled', !googleGmailOn);
        if (googleCalendarWrap) googleCalendarWrap.classList.toggle('is-disabled', !googleCalendarOn);

        if (openprojectBaseUrl) openprojectBaseUrl.disabled = !openprojectOn;
        if (openprojectToken) openprojectToken.disabled = !openprojectOn || envManagedToken;
        if (openprojectWp) openprojectWp.disabled = !openprojectOn;
        if (openprojectSkipSsl) openprojectSkipSsl.disabled = !openprojectOn || envManagedSsl;
        if (openprojectProjectRef) openprojectProjectRef.disabled = !openprojectOn;
        if (openprojectProjectMaxItems) openprojectProjectMaxItems.disabled = !openprojectOn;
        if (openprojectProjectPageSize) openprojectProjectPageSize.disabled = !openprojectOn;
        if (nextcloudBaseUrl) nextcloudBaseUrl.disabled = !nextcloudOn;
        if (nextcloudUsername) nextcloudUsername.disabled = !nextcloudOn;
        if (nextcloudAppPassword) nextcloudAppPassword.disabled = !nextcloudOn || nextcloudEnvManagedCred;
        if (nextcloudRootPath) nextcloudRootPath.disabled = !nextcloudOn;
        if (nextcloudSkipSsl) nextcloudSkipSsl.disabled = !nextcloudOn || nextcloudEnvManagedSsl;

        if (openprojectBaseUrlWrap) openprojectBaseUrlWrap.classList.toggle('is-disabled', !openprojectOn);
        if (openprojectTokenWrap) openprojectTokenWrap.classList.toggle('is-disabled', !openprojectOn);
        if (openprojectWrap) openprojectWrap.classList.toggle('is-disabled', !openprojectOn);
        if (openprojectSslWrap) openprojectSslWrap.classList.toggle('is-disabled', !openprojectOn || envManagedSsl);
        if (openprojectSslHint) openprojectSslHint.textContent = envManagedSsl ? 'SSL policy is managed by environment' : '';
        if (openprojectSslWarning) {
            const showWarning = openprojectOn && Boolean(openprojectSkipSsl?.checked);
            openprojectSslWarning.style.display = showWarning ? 'flex' : 'none';
        }
        if (nextcloudBaseUrlWrap) nextcloudBaseUrlWrap.classList.toggle('is-disabled', !nextcloudOn);
        if (nextcloudUsernameWrap) nextcloudUsernameWrap.classList.toggle('is-disabled', !nextcloudOn);
        if (nextcloudTokenWrap) nextcloudTokenWrap.classList.toggle('is-disabled', !nextcloudOn);
        if (nextcloudRootPathWrap) nextcloudRootPathWrap.classList.toggle('is-disabled', !nextcloudOn);
        if (nextcloudSslWrap) nextcloudSslWrap.classList.toggle('is-disabled', !nextcloudOn || nextcloudEnvManagedSsl);
        if (nextcloudCredentialHint) {
            nextcloudCredentialHint.textContent = nextcloudEnvManagedCred ? 'Credentials are managed by environment' : '';
        }
        if (nextcloudSslHint) {
            nextcloudSslHint.textContent = nextcloudEnvManagedSsl ? 'SSL policy is managed by environment' : '';
        }
        if (nextcloudSslWarning) {
            const showWarning = nextcloudOn && Boolean(nextcloudSkipSsl?.checked);
            nextcloudSslWarning.style.display = showWarning ? 'flex' : 'none';
        }
        if (gdriveSyncBtn) gdriveSyncBtn.disabled = !googleOn;
        if (openprojectSyncBtn) openprojectSyncBtn.disabled = !openprojectOn;
        if (nextcloudSyncBtn) nextcloudSyncBtn.disabled = !nextcloudOn;
        if (bimRequireSignature) bimRequireSignature.disabled = !bimOn;
        if (bimEndpoint) bimEndpoint.disabled = !bimOn;
        if (bimDefaultCategory) bimDefaultCategory.disabled = !bimOn;
        if (bimDefaultFolder) bimDefaultFolder.disabled = !bimOn;
        if (bimAllowedMime) bimAllowedMime.disabled = !bimOn;
        if (bimMaxBatch) bimMaxBatch.disabled = !bimOn;
        if (bimKeyId) bimKeyId.disabled = !bimSignatureOn;
        if (bimSecret) bimSecret.disabled = !bimSignatureOn;
        if (bimSecretBadge) {
            const hasSecret = String(bimSecretBadge.dataset.hasSecret || '').toLowerCase() === 'true';
            bimSecretBadge.textContent = hasSecret ? 'saved' : 'none';
        }
        if (executeBtn) executeBtn.disabled = !readyForExecute;
        if (tokenHint) tokenHint.textContent = envManagedToken ? 'Token is managed by environment' : '';
        updateOpenProjectTokenSavedState(tokenSource, norm(openprojectToken?.value));
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
            }
        });

        root.addEventListener('change', (event) => {
            const target = event?.target;
            if (!target) return;
            if (target.closest('#storage-step-site-cache')) {
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
            throw new Error(`${label} Ø¨Ø§ÛŒØ¯ Ø¹Ø¯Ø¯ Ù…Ø«Ø¨Øª Ø¨Ø§Ø´Ø¯.`);
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
            pdf: parsePositiveNumber(pdfInput.value, 'Ø­Ø¯Ø§Ú©Ø«Ø± Ø­Ø¬Ù… PDF', 100),
            native: parsePositiveNumber(nativeInput.value, 'Ø­Ø¯Ø§Ú©Ø«Ø± Ø­Ø¬Ù… Native', 250),
            attachment: parsePositiveNumber(attachmentInput.value, 'Ø­Ø¯Ø§Ú©Ø«Ø± Ø­Ø¬Ù… Attachment', 100),
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
        tSuccess('Ø³ÛŒØ§Ø³Øª Ø§Ø¹ØªØ¨Ø§Ø±Ø³Ù†Ø¬ÛŒ ÙØ§ÛŒÙ„ Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
    }

    function applyStorageIntegrationsToForm(integrations = {}) {
        const mirrorProvider = document.getElementById('storageMirrorProviderSelect');
        const gdriveEnabled = document.getElementById('storageGoogleDriveEnabledInput');
        const gdriveDriveEnabled = document.getElementById('storageGoogleDriveDriveEnabledInput');
        const gdriveGmailEnabled = document.getElementById('storageGoogleGmailEnabledInput');
        const gdriveCalendarEnabled = document.getElementById('storageGoogleCalendarEnabledInput');
        const gdriveOauthClientId = document.getElementById('storageGoogleOauthClientIdInput');
        const gdriveOauthClientSecret = document.getElementById('storageGoogleOauthClientSecretInput');
        const gdriveOauthRefreshToken = document.getElementById('storageGoogleOauthRefreshTokenInput');
        const gdriveRootFolder = document.getElementById('storageGoogleDriveRootFolderInput');
        const gdriveSenderEmail = document.getElementById('storageGoogleSenderEmailInput');
        const gdriveCalendarId = document.getElementById('storageGoogleCalendarIdInput');
        const openprojectEnabled = document.getElementById('storageOpenProjectEnabledInput');
        const openprojectBaseUrl = document.getElementById('storageOpenProjectBaseUrlInput');
        const openprojectToken = document.getElementById('storageOpenProjectApiTokenInput');
        const openprojectWp = document.getElementById('storageOpenProjectDefaultWpInput');
        const openprojectSkipSsl = document.getElementById('storageOpenProjectSkipSslVerifyInput');
        const gdriveDriveId = document.getElementById('storageGoogleDriveDriveIdInput');
        const tokenBadge = document.getElementById('storageOpenProjectTokenSourceBadge');
        const tokenHint = document.getElementById('storageOpenProjectTokenManagedHint');
        const openprojectSslHint = document.getElementById('storageOpenProjectSslManagedHint');
        const openprojectSslWarning = document.getElementById('storageOpenProjectSkipSslWarning');
        const nextcloudEnabled = document.getElementById('storageNextcloudEnabledInput');
        const nextcloudBaseUrl = document.getElementById('storageNextcloudBaseUrlInput');
        const nextcloudUsername = document.getElementById('storageNextcloudUsernameInput');
        const nextcloudAppPassword = document.getElementById('storageNextcloudAppPasswordInput');
        const nextcloudRootPath = document.getElementById('storageNextcloudRootPathInput');
        const nextcloudSkipSsl = document.getElementById('storageNextcloudSkipSslVerifyInput');
        const nextcloudCredentialBadge = document.getElementById('storageNextcloudCredentialSourceBadge');
        const nextcloudCredentialHint = document.getElementById('storageNextcloudCredentialManagedHint');
        const nextcloudSslHint = document.getElementById('storageNextcloudSslManagedHint');
        const nextcloudSslWarning = document.getElementById('storageNextcloudSkipSslWarning');

        const mirror = integrations?.mirror || {};
        const gdrive = integrations?.google_drive || {};
        const openproject = integrations?.openproject || {};
        const nextcloud = integrations?.nextcloud || {};
        const mirrorProviderValue = ['none', 'google_drive', 'nextcloud'].includes(norm(mirror.provider).toLowerCase())
            ? norm(mirror.provider).toLowerCase()
            : 'none';
        const tokenSource = norm(openproject.token_source || 'none').toLowerCase();
        const sslSource = norm(openproject.ssl_source || 'env_default').toLowerCase();
        const sslForceActive = Boolean(openproject.ssl_force_active);
        const skipSslVerify = Boolean(openproject.skip_ssl_verify);
        const nextcloudCredentialSource = norm(nextcloud.credential_source || 'none').toLowerCase();
        const nextcloudSslSource = norm(nextcloud.ssl_source || 'env_default').toLowerCase();
        const nextcloudSslForceActive = Boolean(nextcloud.ssl_force_active);
        const nextcloudSkipSslVerify = Boolean(nextcloud.skip_ssl_verify);

        if (mirrorProvider) mirrorProvider.value = mirrorProviderValue;

        if (gdriveEnabled) gdriveEnabled.checked = Boolean(gdrive.enabled);
        if (gdriveDriveEnabled) gdriveDriveEnabled.checked = Boolean(gdrive.drive_enabled);
        if (gdriveGmailEnabled) gdriveGmailEnabled.checked = Boolean(gdrive.gmail_enabled);
        if (gdriveCalendarEnabled) gdriveCalendarEnabled.checked = Boolean(gdrive.calendar_enabled);
        if (gdriveOauthClientId) gdriveOauthClientId.value = String(gdrive.oauth_client_id || '');
        if (gdriveOauthClientSecret) gdriveOauthClientSecret.value = '';
        if (gdriveOauthRefreshToken) gdriveOauthRefreshToken.value = '';
        if (gdriveRootFolder) gdriveRootFolder.value = String(gdrive.root_folder_id || '');
        if (gdriveSenderEmail) gdriveSenderEmail.value = String(gdrive.sender_email || '');
        if (gdriveCalendarId) gdriveCalendarId.value = String(gdrive.calendar_id || '');
        if (openprojectEnabled) openprojectEnabled.checked = Boolean(openproject.enabled);
        if (openprojectBaseUrl) openprojectBaseUrl.value = String(openproject.base_url || '');
        if (openprojectToken) openprojectToken.value = '';
        if (openprojectWp) openprojectWp.value = String(openproject.default_work_package_id || openproject.default_project_id || '');
        if (openprojectSkipSsl) {
            openprojectSkipSsl.checked = skipSslVerify;
            openprojectSkipSsl.dataset.sslSource = sslSource || 'env_default';
            openprojectSkipSsl.dataset.sslForceActive = sslForceActive ? 'true' : 'false';
        }
        if (gdriveDriveId) gdriveDriveId.value = String(gdrive.shared_drive_id || '');
        if (tokenBadge) {
            tokenBadge.textContent = tokenSource || 'none';
            tokenBadge.dataset.tokenSource = tokenSource || 'none';
        }
        if (tokenHint) tokenHint.textContent = tokenSource === 'env' ? 'Token is managed by environment' : '';
        if (openprojectSslHint) {
            openprojectSslHint.textContent = sslForceActive ? 'SSL policy is managed by environment' : '';
        }
        if (openprojectSslWarning) {
            openprojectSslWarning.style.display = skipSslVerify ? 'flex' : 'none';
        }
        if (nextcloudEnabled) nextcloudEnabled.checked = Boolean(nextcloud.enabled);
        if (nextcloudBaseUrl) nextcloudBaseUrl.value = String(nextcloud.base_url || '');
        if (nextcloudUsername) nextcloudUsername.value = String(nextcloud.username || '');
        if (nextcloudAppPassword) nextcloudAppPassword.value = '';
        if (nextcloudRootPath) nextcloudRootPath.value = String(nextcloud.root_path || '');
        if (nextcloudSkipSsl) {
            nextcloudSkipSsl.checked = nextcloudSkipSslVerify;
            nextcloudSkipSsl.dataset.sslSource = nextcloudSslSource || 'env_default';
            nextcloudSkipSsl.dataset.sslForceActive = nextcloudSslForceActive ? 'true' : 'false';
        }
        if (nextcloudCredentialBadge) {
            nextcloudCredentialBadge.textContent = nextcloudCredentialSource || 'none';
            nextcloudCredentialBadge.dataset.tokenSource = nextcloudCredentialSource || 'none';
        }
        if (nextcloudCredentialHint) {
            nextcloudCredentialHint.textContent = nextcloudCredentialSource === 'env'
                ? 'Credentials are managed by environment'
                : '';
        }
        if (nextcloudSslHint) {
            nextcloudSslHint.textContent = nextcloudSslForceActive ? 'SSL policy is managed by environment' : '';
        }
        if (nextcloudSslWarning) {
            nextcloudSslWarning.style.display = nextcloudSkipSslVerify ? 'flex' : 'none';
        }
        updateStorageIntegrationsFieldState();
    }

    function setBimRevitRotateResult(message = '', level = 'info') {
        const box = document.getElementById('storageBimRevitRotateResult');
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

    function applyBimRevitSettingsToForm(payload = {}) {
        const settingsPayload = payload?.settings || payload || {};
        const enabled = document.getElementById('storageBimRevitEnabledInput');
        const requireSig = document.getElementById('storageBimRevitRequireSignatureInput');
        const endpoint = document.getElementById('storageBimRevitApiEndpointInput');
        const keyId = document.getElementById('storageBimRevitPluginKeyIdInput');
        const secret = document.getElementById('storageBimRevitPluginSecretInput');
        const defCategory = document.getElementById('storageBimRevitDefaultCategoryIdInput');
        const defFolder = document.getElementById('storageBimRevitDefaultFolderIdInput');
        const allowedMime = document.getElementById('storageBimRevitAllowedMimeInput');
        const maxBatch = document.getElementById('storageBimRevitMaxBatchSizeInput');
        const badge = document.getElementById('storageBimRevitSecretStateBadge');

        if (enabled) enabled.checked = Boolean(settingsPayload.enabled);
        if (requireSig) requireSig.checked = Boolean(settingsPayload.require_plugin_signature);
        if (endpoint) endpoint.value = String(settingsPayload.api_endpoint_url || '');
        if (keyId) keyId.value = String(settingsPayload.plugin_key_id || '');
        if (secret) secret.value = '';
        if (defCategory) defCategory.value = settingsPayload.default_category_id ? String(settingsPayload.default_category_id) : '';
        if (defFolder) defFolder.value = settingsPayload.default_folder_id ? String(settingsPayload.default_folder_id) : '';
        if (allowedMime) allowedMime.value = Array.isArray(settingsPayload.allowed_mime) ? settingsPayload.allowed_mime.join(',') : '';
        if (maxBatch) maxBatch.value = String(settingsPayload.max_batch_size || 100);
        if (badge) {
            const hasSecret = Boolean(settingsPayload.has_secret);
            badge.dataset.hasSecret = hasSecret ? 'true' : 'false';
            badge.textContent = hasSecret ? 'saved' : 'none';
        }
        updateStorageIntegrationsFieldState();
    }

    async function loadBimRevitSettings(force = false) {
        const endpoint = document.getElementById('storageBimRevitApiEndpointInput');
        if (!endpoint) return;
        if (STORE.storageBimRevitLoaded && !force) return;
        const payload = await request(`${API_BASE}/bim-revit`);
        applyBimRevitSettingsToForm(payload);
        STORE.storageBimRevitLoaded = true;
    }

    function buildBimRevitPayloadFromForm() {
        const enabled = document.getElementById('storageBimRevitEnabledInput');
        const requireSig = document.getElementById('storageBimRevitRequireSignatureInput');
        const endpoint = document.getElementById('storageBimRevitApiEndpointInput');
        const keyId = document.getElementById('storageBimRevitPluginKeyIdInput');
        const secret = document.getElementById('storageBimRevitPluginSecretInput');
        const defCategory = document.getElementById('storageBimRevitDefaultCategoryIdInput');
        const defFolder = document.getElementById('storageBimRevitDefaultFolderIdInput');
        const allowedMime = document.getElementById('storageBimRevitAllowedMimeInput');
        const maxBatch = document.getElementById('storageBimRevitMaxBatchSizeInput');
        if (!enabled || !requireSig || !endpoint || !keyId || !secret || !defCategory || !defFolder || !allowedMime || !maxBatch) {
            return null;
        }

        const payload = {
            enabled: Boolean(enabled.checked),
            require_plugin_signature: Boolean(requireSig.checked),
            api_endpoint_url: norm(endpoint.value),
            plugin_key_id: norm(keyId.value),
            plugin_secret: norm(secret.value),
            default_category_id: norm(defCategory.value) ? Number(defCategory.value) : null,
            default_folder_id: norm(defFolder.value) ? Number(defFolder.value) : null,
            allowed_mime: parseCommaSeparatedList(allowedMime.value).map((x) => String(x || '').trim().toLowerCase()),
            max_batch_size: Number(maxBatch.value || 100),
        };
        return payload;
    }

    async function saveBimRevitSettings(options = {}) {
        const payload = buildBimRevitPayloadFromForm();
        if (!payload) return;

        const silent = Boolean(options?.silent);
        if (payload.enabled) {
            if (!payload.api_endpoint_url) {
                throw new Error('BIM API Endpoint URL is required when BIM integration is enabled.');
            }
            if (payload.require_plugin_signature && !payload.plugin_key_id) {
                throw new Error('Plugin Key ID is required when signature is enabled.');
            }
        }
        if (!Number.isFinite(payload.max_batch_size) || payload.max_batch_size <= 0) {
            throw new Error('Max batch size must be a positive number.');
        }

        const response = await request(`${API_BASE}/bim-revit`, {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        applyBimRevitSettingsToForm(response);
        STORE.storageBimRevitLoaded = true;
        if (!silent) {
            setBimRevitRotateResult('');
            tSuccess('BIM/Revit settings saved.');
        }
    }

    async function rotateBimRevitSecret() {
        const response = await request(`${API_BASE}/bim-revit/rotate-secret`, {
            method: 'POST',
        });
        applyBimRevitSettingsToForm(response);
        const keyId = norm(response?.plugin_key_id);
        const secret = norm(response?.plugin_secret);
        if (secret) {
            setBimRevitRotateResult(`NEW SECRET (copy now): ${secret}`, 'success');
        } else {
            setBimRevitRotateResult('Secret rotated, but server did not return a one-time secret.', 'error');
        }
        if (keyId) {
            tSuccess(`BIM/Revit secret rotated. Key ID: ${keyId}`);
        }
    }

    async function loadStorageIntegrations(force = false) {
        const gdriveEnabled = document.getElementById('storageGoogleDriveEnabledInput');
        if (!gdriveEnabled) return;
        if (STORE.storageIntegrationsLoaded && !force) return;
        const payload = await request(`${API_BASE}/storage-integrations`);
        applyStorageIntegrationsToForm(payload?.integrations || {});
        STORE.storageIntegrationsLoaded = true;
        await loadBimRevitSettings(force);
    }

    async function saveStorageIntegrations() {
        const mirrorProvider = document.getElementById('storageMirrorProviderSelect');
        const gdriveEnabled = document.getElementById('storageGoogleDriveEnabledInput');
        const gdriveDriveEnabled = document.getElementById('storageGoogleDriveDriveEnabledInput');
        const gdriveGmailEnabled = document.getElementById('storageGoogleGmailEnabledInput');
        const gdriveCalendarEnabled = document.getElementById('storageGoogleCalendarEnabledInput');
        const gdriveOauthClientId = document.getElementById('storageGoogleOauthClientIdInput');
        const gdriveOauthClientSecret = document.getElementById('storageGoogleOauthClientSecretInput');
        const gdriveOauthRefreshToken = document.getElementById('storageGoogleOauthRefreshTokenInput');
        const openprojectEnabled = document.getElementById('storageOpenProjectEnabledInput');
        const openprojectBaseUrl = document.getElementById('storageOpenProjectBaseUrlInput');
        const openprojectToken = document.getElementById('storageOpenProjectApiTokenInput');
        const openprojectWp = document.getElementById('storageOpenProjectDefaultWpInput');
        const openprojectSkipSsl = document.getElementById('storageOpenProjectSkipSslVerifyInput');
        const gdriveDriveId = document.getElementById('storageGoogleDriveDriveIdInput');
        const gdriveRootFolder = document.getElementById('storageGoogleDriveRootFolderInput');
        const gdriveSenderEmail = document.getElementById('storageGoogleSenderEmailInput');
        const gdriveCalendarId = document.getElementById('storageGoogleCalendarIdInput');
        const nextcloudEnabled = document.getElementById('storageNextcloudEnabledInput');
        const nextcloudBaseUrl = document.getElementById('storageNextcloudBaseUrlInput');
        const nextcloudUsername = document.getElementById('storageNextcloudUsernameInput');
        const nextcloudAppPassword = document.getElementById('storageNextcloudAppPasswordInput');
        const nextcloudRootPath = document.getElementById('storageNextcloudRootPathInput');
        const nextcloudSkipSsl = document.getElementById('storageNextcloudSkipSslVerifyInput');
        if (
            !mirrorProvider
            || !gdriveEnabled
            || !openprojectEnabled
            || !openprojectWp
            || !gdriveDriveId
            || !openprojectBaseUrl
            || !openprojectToken
            || !openprojectSkipSsl
            || !nextcloudEnabled
            || !nextcloudBaseUrl
            || !nextcloudUsername
            || !nextcloudAppPassword
            || !nextcloudRootPath
            || !nextcloudSkipSsl
        ) return;

        const sslForceActive = String(openprojectSkipSsl.dataset.sslForceActive || '').toLowerCase() === 'true';
        const openprojectPayload = {
            enabled: Boolean(openprojectEnabled.checked),
            base_url: norm(openprojectBaseUrl.value),
            api_token: norm(openprojectToken.value),
            default_work_package_id: norm(openprojectWp.value),
        } as Record<string, unknown>;
        if (!sslForceActive) {
            openprojectPayload.skip_ssl_verify = Boolean(openprojectSkipSsl.checked);
        }
        const nextcloudSslForceActive = String(nextcloudSkipSsl.dataset.sslForceActive || '').toLowerCase() === 'true';
        const nextcloudPayload = {
            enabled: Boolean(nextcloudEnabled.checked),
            base_url: norm(nextcloudBaseUrl.value),
            username: norm(nextcloudUsername.value),
            app_password: norm(nextcloudAppPassword.value),
            root_path: norm(nextcloudRootPath.value),
        } as Record<string, unknown>;
        if (!nextcloudSslForceActive) {
            nextcloudPayload.skip_ssl_verify = Boolean(nextcloudSkipSsl.checked);
        }
        const selectedMirrorProvider = ['none', 'google_drive', 'nextcloud'].includes(norm(mirrorProvider.value).toLowerCase())
            ? norm(mirrorProvider.value).toLowerCase()
            : 'none';

        const payload = await request(`${API_BASE}/storage-integrations`, {
            method: 'POST',
            body: JSON.stringify({
                mirror: {
                    provider: selectedMirrorProvider,
                },
                google_drive: {
                    enabled: Boolean(gdriveEnabled.checked),
                    shared_drive_id: norm(gdriveDriveId.value),
                    root_folder_id: norm(gdriveRootFolder?.value),
                    oauth_client_id: norm(gdriveOauthClientId?.value),
                    oauth_client_secret: norm(gdriveOauthClientSecret?.value),
                    oauth_refresh_token: norm(gdriveOauthRefreshToken?.value),
                    drive_enabled: Boolean(gdriveDriveEnabled?.checked),
                    gmail_enabled: Boolean(gdriveGmailEnabled?.checked),
                    calendar_enabled: Boolean(gdriveCalendarEnabled?.checked),
                    sender_email: norm(gdriveSenderEmail?.value),
                    calendar_id: norm(gdriveCalendarId?.value),
                },
                openproject: openprojectPayload,
                nextcloud: nextcloudPayload,
            }),
        });
        applyStorageIntegrationsToForm(payload?.integrations || {});
        await saveBimRevitSettings({ silent: true });
        STORE.storageIntegrationsLoaded = true;
        setStorageSyncResult('');
        tSuccess('تنظیمات یکپارچه‌سازی و BIM/Revit ذخیره شد.');
    }

    function runSummaryText(run) {
        const total = Number(run?.total_rows || 0);
        const valid = Number(run?.valid_rows || 0);
        const invalid = Number(run?.invalid_rows || 0);
        const created = Number(run?.created_rows || 0);
        const failed = Number(run?.failed_rows || 0);
        const summary = run?.summary || {};
        const pass1Created = Number(summary?.pass1_created_rows || 0);
        const pass1Failed = Number(summary?.pass1_failed_rows || 0);
        const pass2Created = Number(summary?.pass2_relation_created || 0);
        const pass2Failed = Number(summary?.pass2_relation_failed || 0);
        const status = String(run?.status_code || '-');
        return `Run=${status} | Total=${total} | Valid=${valid} | Invalid=${invalid} | Created=${created} | Failed=${failed} | Pass1=${pass1Created}/${pass1Failed} | Pass2=${pass2Created}/${pass2Failed}`;
    }

    function rowExecutionStatusClass(value) {
        const key = norm(value).toUpperCase();
        if (!key) return '';
        if (key === 'CREATED' || key === 'RELATION_CREATED' || key === 'IMPORTED') {
            return 'status-success';
        }
        if (key === 'FAILED' || key === 'RELATION_FAILED') {
            return 'status-danger';
        }
        if (key === 'SKIPPED') {
            return 'status-muted';
        }
        return '';
    }

    function renderOpenProjectImportRowDetails(row) {
        const box = document.getElementById('storageOpenProjectImportRowDetails');
        if (!box) return;
        if (!row || typeof row !== 'object') {
            box.innerHTML = 'Select a row to view mapping and relation details.';
            return;
        }
        const payload = row?.payload || {};
        const mapped = payload?.mapped_fields || {};
        const customFields = payload?.custom_fields || {};
        const executionMeta = payload?.execution_meta || {};
        const relations = Array.isArray(executionMeta?.relations) ? executionMeta.relations : [];
        const relationCreated = relations.filter((it) => String(it?.status || '').toUpperCase() === 'CREATED').length;
        const relationFailed = relations.filter((it) => String(it?.status || '').toUpperCase() === 'FAILED').length;
        const customSummary = Object.keys(customFields || {})
            .slice(0, 8)
            .map((key) => `${key}: ${customFields[key]}`)
            .join(' | ');
        box.innerHTML = `
            <div class="storage-openproject-row-details-grid">
              <div><strong>Row:</strong> ${esc(row?.row_no || '-')}</div>
              <div><strong>WBS:</strong> ${esc(mapped?.wbs_code || '-')}</div>
              <div><strong>Type:</strong> ${esc(mapped?.type_text || '-')}</div>
              <div><strong>Priority:</strong> ${esc(mapped?.priority_text || '-')}</div>
              <div><strong>Done %:</strong> ${esc(mapped?.done_ratio ?? '-')}</div>
              <div><strong>Relations:</strong> ${esc(`${relationCreated} success / ${relationFailed} failed`)}</div>
              <div class="storage-openproject-row-details-full"><strong>Custom Fields:</strong> ${esc(customSummary || '-')}</div>
              <div class="storage-openproject-row-details-full"><strong>Error:</strong> ${esc(row?.error_message || '-')}</div>
            </div>
        `;
    }

    function setOpenProjectProjectImportSummary(message = '', tone = 'info') {
        const box = document.getElementById('storageOpenProjectProjectImportSummary');
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
        if (tone === 'success') box.classList.add('storage-sync-result-success');
        else if (tone === 'error') box.classList.add('storage-sync-result-error');
        else box.classList.add('storage-sync-result-info');
    }

    function renderOpenProjectProjectPreview(rows = []) {
        const tbody = document.getElementById('storageOpenProjectProjectPreviewBody');
        if (!tbody) return;
        if (!Array.isArray(rows) || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center muted">No data.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map((row) => `
            <tr>
              <td>${esc(row?.row_no || '-')}</td>
              <td>${esc(row?.work_package_id || '-')}</td>
              <td>${esc(row?.subject || '-')}</td>
              <td>${esc(row?.status || '-')}</td>
              <td>${esc(row?.type || '-')}</td>
              <td>${esc(row?.assignee || '-')}</td>
              <td>${esc(row?.start_date || '-')}</td>
              <td>${esc(row?.due_date || '-')}</td>
              <td>${esc(row?.done_ratio ?? '-')}</td>
            </tr>
        `).join('');
    }

    function getOpenProjectProjectImportParams() {
        const projectRefInput = document.getElementById('storageOpenProjectProjectRefInput');
        const maxItemsInput = document.getElementById('storageOpenProjectProjectImportMaxItemsInput');
        const pageSizeInput = document.getElementById('storageOpenProjectProjectImportPageSizeInput');
        const projectRef = norm(projectRefInput?.value);
        if (!projectRef) {
            throw new Error('Project ID / Identifier is required.');
        }
        const maxItems = Math.max(1, Number(maxItemsInput?.value || 5000) || 5000);
        const pageSize = Math.max(1, Number(pageSizeInput?.value || 200) || 200);
        return { projectRef, maxItems, pageSize };
    }

    async function previewOpenProjectProjectWorkPackages() {
        const { projectRef, pageSize } = getOpenProjectProjectImportParams();
        setOpenProjectProjectImportSummary('Loading project work packages preview ...', 'info');
        const encodedRef = encodeURIComponent(projectRef);
        const payload = await request(
            `/api/v1/storage/openproject/projects/${encodedRef}/work-packages/preview?skip=0&limit=${Math.min(1000, pageSize)}`
        );
        const rows = Array.isArray(payload?.items) ? payload.items : [];
        renderOpenProjectProjectPreview(rows);
        const projectName = String(payload?.project?.name || payload?.project?.identifier || projectRef);
        setOpenProjectProjectImportSummary(
            `Preview loaded | project=${projectName} | rows=${rows.length} | total=${Number(payload?.total || rows.length)}`,
            rows.length > 0 ? 'success' : 'info'
        );
    }

    async function importOpenProjectProjectWorkPackages() {
        const { projectRef, maxItems, pageSize } = getOpenProjectProjectImportParams();
        setOpenProjectProjectImportSummary('Importing project snapshot ...', 'info');
        const encodedRef = encodeURIComponent(projectRef);
        const payload = await request(`/api/v1/storage/openproject/projects/${encodedRef}/import`, {
            method: 'POST',
            body: JSON.stringify({
                max_items: maxItems,
                page_size: pageSize,
            }),
        });
        const run = payload?.run || {};
        const runId = Number(run?.id || 0);
        if (runId > 0) {
            STORE.openprojectImport.selectedRunId = runId;
            STORE.openprojectImport.lastValidatedRunId = 0;
            const runInput = document.getElementById('storageOpenProjectImportRunIdInput');
            if (runInput) runInput.value = String(runId);
        }
        setOpenProjectProjectImportSummary(runSummaryText(run), Number(run?.failed_rows || 0) > 0 ? 'error' : 'success');
        await refreshOpenProjectImportData();
        setOpenProjectSubTab('logs');
        if (Number(run?.failed_rows || 0) > 0) {
            tError('Project snapshot import completed with some failed rows.');
        } else {
            tSuccess('Project snapshot import completed.');
        }
        return run;
    }

    function renderOpenProjectImportRuns(rows = []) {
        const tbody = document.getElementById('storageOpenProjectImportRunsBody');
        if (!tbody) return;
        if (!Array.isArray(rows) || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center muted">داده ای ثبت نشده است.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map((row) => {
            const runId = Number(row?.id || 0);
            return `
                <tr data-import-run-id="${esc(runId)}">
                  <td>${esc(row?.run_no || '-')}</td>
                  <td>${esc(row?.status_code || '-')}</td>
                  <td>${esc(String(row?.valid_rows || 0))}/${esc(String(row?.total_rows || 0))}</td>
                  <td>${esc(String(row?.created_rows || 0))}/${esc(String(row?.failed_rows || 0))}</td>
                  <td>
                    <div class="general-row-actions">
                      <button class="btn-archive-icon" type="button" data-integrations-action="select-openproject-import-run" data-run-id="${esc(runId)}">Rows</button>
                    </div>
                  </td>
                </tr>
            `;
        }).join('');
    }

    function renderOpenProjectImportRows(rows = []) {
        const tbody = document.getElementById('storageOpenProjectImportRowsBody');
        if (!tbody) return;
        if (!Array.isArray(rows) || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center muted">رکوردی یافت نشد.</td></tr>';
            renderOpenProjectImportRowDetails(null);
            return;
        }
        tbody.innerHTML = rows.map((row, index) => `
            <tr data-row-index="${esc(index)}">
              <td>${esc(row?.row_no || '-')}</td>
              <td>${esc(row?.task_name || '-')}</td>
              <td>${esc(row?.validation_status || '-')}</td>
              <td><span class="${esc(rowExecutionStatusClass(row?.execution_status))}">${esc(row?.execution_status || '-')}</span></td>
              <td>${esc(row?.created_work_package_id || '-')}</td>
              <td class="text-left">${esc(row?.error_message || '-')}</td>
            </tr>
        `).join('');
        const tableRows = Array.from(tbody.querySelectorAll('tr[data-row-index]'));
        tableRows.forEach((tr) => {
            tr.addEventListener('click', () => {
                tableRows.forEach((rowEl) => rowEl.classList.remove('is-selected'));
                tr.classList.add('is-selected');
                const idx = Number(tr.getAttribute('data-row-index') || 0);
                renderOpenProjectImportRowDetails(rows[idx] || null);
            });
        });
        if (tableRows.length > 0) {
            tableRows[0].classList.add('is-selected');
            renderOpenProjectImportRowDetails(rows[0]);
        }
    }

    function renderOpenProjectActivity(rows = []) {
        const tbody = document.getElementById('storageOpenProjectActivityBody');
        if (!tbody) return;
        if (!Array.isArray(rows) || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center muted">فعالیتی ثبت نشده است.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map((row) => {
            const details = row?.source === 'import'
                ? `run=${row?.run_no || '-'} | row=${row?.row_no || '-'} | wp=${row?.created_work_package_id || '-'}`
                : `entity=${row?.entity_type || '-'}:${row?.entity_id || '-'} | wp=${row?.work_package_id || '-'}`;
            return `
                <tr>
                  <td>${esc(row?.event_at || '-')}</td>
                  <td>${esc(row?.source || '-')}</td>
                  <td>${esc(row?.kind || '-')}</td>
                  <td>${esc(details)}</td>
                </tr>
            `;
        }).join('');
    }

    async function loadOpenProjectImportRuns(selectRunId = 0) {
        const payload = await request('/api/v1/storage/openproject/import/runs?limit=50');
        const runs = Array.isArray(payload?.runs) ? payload.runs : [];
        renderOpenProjectImportRuns(runs);
        const selected = Number(selectRunId || STORE.openprojectImport?.selectedRunId || 0);
        if (selected > 0) {
            await loadOpenProjectImportRows(selected);
        }
        return runs;
    }

    async function loadOpenProjectImportRows(runId) {
        const safeRunId = Number(runId || 0);
        STORE.openprojectImport.selectedRunId = safeRunId;
        if (safeRunId <= 0) {
            renderOpenProjectImportRows([]);
            return [];
        }
        const payload = await request(`/api/v1/storage/openproject/import/runs/${safeRunId}/rows?skip=0&limit=500`);
        const rows = Array.isArray(payload?.rows) ? payload.rows : [];
        renderOpenProjectImportRows(rows);
        return rows;
    }

    async function loadOpenProjectActivities() {
        const payload = await request('/api/v1/storage/openproject/activity?limit=50');
        const rows = Array.isArray(payload?.items) ? payload.items : [];
        renderOpenProjectActivity(rows);
        return rows;
    }

    async function refreshOpenProjectImportData() {
        await loadOpenProjectImportRuns();
        await loadOpenProjectActivities();
    }

    async function validateOpenProjectImportFile() {
        const input = document.getElementById('storageOpenProjectImportFileInput');
        const file = input?.files?.[0] || null;
        if (!file) {
            throw new Error('ابتدا فایل اکسل را انتخاب کنید.');
        }
        if (!String(file.name || '').toLowerCase().endsWith('.xlsx')) {
            throw new Error('فرمت فایل باید .xlsx باشد.');
        }
        setOpenProjectImportSummary('در حال اعتبارسنجی فایل اکسل ...', 'info');

        const formData = new FormData();
        formData.append('file', file, file.name);
        const payload = await request('/api/v1/storage/openproject/import/validate', {
            method: 'POST',
            body: formData,
        });
        const run = payload?.run || {};
        const runId = Number(run?.id || 0);
        STORE.openprojectImport.lastValidatedRunId = runId;
        STORE.openprojectImport.selectedRunId = runId;
        const runInput = document.getElementById('storageOpenProjectImportRunIdInput');
        if (runInput) runInput.value = String(runId || '');
        setOpenProjectImportSummary(runSummaryText(run), 'success');
        setOpenProjectImportProgress(Number(run?.total_rows || 0), 0, String(run?.status_code || 'VALIDATED'));
        updateStorageIntegrationsFieldState();
        await refreshOpenProjectImportData();
        setOpenProjectSubTab('logs');
        tSuccess('اعتبارسنجی فایل OpenProject انجام شد.');
        return run;
    }

    async function executeOpenProjectImportRun() {
        const selectedRunId = Number(
            STORE.openprojectImport?.lastValidatedRunId ||
            STORE.openprojectImport?.selectedRunId ||
            document.getElementById('storageOpenProjectImportRunIdInput')?.value ||
            0
        );
        if (selectedRunId <= 0) {
            throw new Error('ابتدا Validate (Dry-run) انجام دهید.');
        }

        setOpenProjectImportSummary('پردازش ردیف های معتبر شروع شد ...', 'info');
        const payload = await request(`/api/v1/storage/openproject/import/runs/${selectedRunId}/execute`, {
            method: 'POST',
            body: JSON.stringify({}),
        });
        const run = payload?.run || {};
        const total = Number(run?.valid_rows || run?.total_rows || 0);
        const done = Number(run?.created_rows || 0) + Number(run?.failed_rows || 0);
        setOpenProjectImportProgress(total, done, String(run?.status_code || 'COMPLETED'));
        setOpenProjectImportSummary(runSummaryText(run), Number(run?.failed_rows || 0) > 0 ? 'error' : 'success');
        await refreshOpenProjectImportData();
        setOpenProjectSubTab('logs');
        if (Number(run?.failed_rows || 0) > 0) {
            tError('پردازش اجرا شد ولی بعضی ردیف ها خطا داشتند.');
        } else {
            tSuccess('پردازش OpenProject با موفقیت انجام شد.');
        }
        return run;
    }

    async function pollOpenProjectRun(runId) {
        stopOpenProjectImportPolling();
        const safeRunId = Number(runId || 0);
        if (safeRunId <= 0) return;
        const loop = async () => {
            try {
                const payload = await request(`/api/v1/storage/openproject/import/runs/${safeRunId}`);
                const run = payload?.run || {};
                const total = Number(run?.valid_rows || run?.total_rows || 0);
                const done = Number(run?.created_rows || 0) + Number(run?.failed_rows || 0);
                setOpenProjectImportProgress(total, done, String(run?.status_code || ''));
                if (String(run?.status_code || '').toUpperCase() === 'RUNNING') {
                    STORE.openprojectImport.pollingTimer = setTimeout(loop, 1200);
                    return;
                }
                await refreshOpenProjectImportData();
            } catch (_err) {
                stopOpenProjectImportPolling();
            }
        };
        STORE.openprojectImport.pollingTimer = setTimeout(loop, 300);
    }

    async function clearOpenProjectStoredToken() {
        const payload = await request(`${API_BASE}/storage-integrations/openproject/clear-token`, {
            method: 'POST',
        });
        applyStorageIntegrationsToForm(payload?.integrations || {});
        setStorageSyncResult('توکن ذخیره‌شده OpenProject پاک شد.', 'success');
    }

    async function pingOpenProject() {
        const openprojectBaseUrl = document.getElementById('storageOpenProjectBaseUrlInput');
        const openprojectToken = document.getElementById('storageOpenProjectApiTokenInput');
        const openprojectSkipSsl = document.getElementById('storageOpenProjectSkipSslVerifyInput');
        const pingBody = {
            base_url: norm(openprojectBaseUrl?.value),
            api_token: norm(openprojectToken?.value),
            skip_ssl_verify: Boolean(openprojectSkipSsl?.checked),
        };
        setStorageSyncResult('در حال بررسی اتصال OpenProject ...', 'info');
        const payload = await request('/api/v1/storage/openproject/ping', {
            method: 'POST',
            body: JSON.stringify(pingBody),
        });
        const reachable = Boolean(payload?.reachable);
        const authOk = Boolean(payload?.auth_ok);
        const statusCode = payload?.status_code ?? '-';
        const tokenSource = String(payload?.token_source || 'none');
        const sslSource = String(payload?.ssl_source || 'env_default');
        const tlsVerifyEffective = Boolean(payload?.tls_verify_effective);
        const message = String(payload?.message || '');
        const summary = `Ping OpenProject: reachable=${reachable} | auth_ok=${authOk} | status=${statusCode} | token_source=${tokenSource} | tls_verify=${tlsVerifyEffective} | ssl_source=${sslSource}`;
        setStorageSyncResult(`${summary}${message ? ` | ${message}` : ''}`, authOk ? 'success' : (reachable ? 'info' : 'error'));
        if (authOk) tSuccess('اتصال OpenProject تایید شد.');
        else tError('Ping OpenProject انجام شد ولی احراز هویت/مسیر نیاز به اصلاح دارد.');
    }

    async function pingGoogle(service) {
        const googleOauthClientId = document.getElementById('storageGoogleOauthClientIdInput');
        const googleOauthClientSecret = document.getElementById('storageGoogleOauthClientSecretInput');
        const googleOauthRefreshToken = document.getElementById('storageGoogleOauthRefreshTokenInput');
        const googleSenderEmail = document.getElementById('storageGoogleSenderEmailInput');
        const googleCalendarId = document.getElementById('storageGoogleCalendarIdInput');
        const safeService = norm(service).toLowerCase();
        setStorageSyncResult(`Testing Google ${safeService} connection ...`, 'info');
        const payload = await request('/api/v1/storage/google/ping', {
            method: 'POST',
            body: JSON.stringify({
                service: safeService,
                oauth_client_id: norm(googleOauthClientId?.value),
                oauth_client_secret: norm(googleOauthClientSecret?.value),
                oauth_refresh_token: norm(googleOauthRefreshToken?.value),
                sender_email: norm(googleSenderEmail?.value),
                calendar_id: norm(googleCalendarId?.value),
            }),
        });
        const reachable = Boolean(payload?.reachable);
        const authOk = Boolean(payload?.auth_ok);
        const statusCode = payload?.status_code ?? '-';
        const message = String(payload?.message || '');
        const summary = `Ping Google ${safeService}: reachable=${reachable} | auth_ok=${authOk} | status=${statusCode}`;
        setStorageSyncResult(`${summary}${message ? ` | ${message}` : ''}`, authOk ? 'success' : (reachable ? 'info' : 'error'));
        if (authOk) tSuccess(`Google ${safeService} connection verified.`);
        else tError(`Google ${safeService} ping completed but needs configuration/auth fix.`);
    }

    async function pingNextcloud() {
        const nextcloudBaseUrl = document.getElementById('storageNextcloudBaseUrlInput');
        const nextcloudUsername = document.getElementById('storageNextcloudUsernameInput');
        const nextcloudAppPassword = document.getElementById('storageNextcloudAppPasswordInput');
        const nextcloudRootPath = document.getElementById('storageNextcloudRootPathInput');
        const nextcloudSkipSsl = document.getElementById('storageNextcloudSkipSslVerifyInput');
        const pingBody = {
            base_url: norm(nextcloudBaseUrl?.value),
            username: norm(nextcloudUsername?.value),
            app_password: norm(nextcloudAppPassword?.value),
            root_path: norm(nextcloudRootPath?.value),
            skip_ssl_verify: Boolean(nextcloudSkipSsl?.checked),
        };
        setStorageSyncResult('Testing Nextcloud connection ...', 'info');
        const payload = await request('/api/v1/storage/nextcloud/ping', {
            method: 'POST',
            body: JSON.stringify(pingBody),
        });
        const reachable = Boolean(payload?.reachable);
        const authOk = Boolean(payload?.auth_ok);
        const statusCode = payload?.status_code ?? '-';
        const credentialSource = String(payload?.credential_source || 'none');
        const sslSource = String(payload?.ssl_source || 'env_default');
        const tlsVerifyEffective = Boolean(payload?.tls_verify_effective);
        const message = String(payload?.message || '');
        const summary = `Ping Nextcloud: reachable=${reachable} | auth_ok=${authOk} | status=${statusCode} | credential_source=${credentialSource} | tls_verify=${tlsVerifyEffective} | ssl_source=${sslSource}`;
        setStorageSyncResult(`${summary}${message ? ` | ${message}` : ''}`, authOk ? 'success' : (reachable ? 'info' : 'error'));
        if (authOk) tSuccess('Nextcloud connection verified.');
        else tError('Nextcloud ping completed but needs configuration/auth fix.');
    }

    async function downloadOpenProjectTemplate() {
        const fetcher = typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : fetch;
        setStorageSyncResult('در حال دانلود تمپلیت OpenProject ...', 'info');
        const response = await fetcher('/api/v1/storage/openproject/import/template');
        if (!response.ok) {
            let message = `دانلود تمپلیت ناموفق بود (${response.status})`;
            try {
                const body = await response.clone().json();
                message = body?.detail || body?.message || message;
            } catch (_) {
                try {
                    const text = await response.text();
                    if (norm(text)) message = text;
                } catch (_) {}
            }
            throw new Error(String(message || 'Not authenticated'));
        }
        const blob = await response.blob();
        const contentDisposition = String(response.headers.get('content-disposition') || '');
        let filename = 'openproject template.xlsx';
        const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
        const asciiMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
        if (utf8Match?.[1]) {
            try {
                filename = decodeURIComponent(String(utf8Match[1]));
            } catch (_) {
                filename = String(utf8Match[1]);
            }
        } else if (asciiMatch?.[1]) {
            filename = String(asciiMatch[1]);
        }
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
        setStorageSyncResult('تمپلیت OpenProject دانلود شد.', 'success');
    }

    async function runStorageSyncJob(kind) {
        const endpoint = kind === 'openproject'
            ? '/api/v1/storage/sync/openproject/run'
            : kind === 'nextcloud'
                ? '/api/v1/storage/sync/nextcloud/run'
                : '/api/v1/storage/sync/google-drive/run';
        const title = kind === 'openproject' ? 'OpenProject' : (kind === 'nextcloud' ? 'Nextcloud' : 'Google Drive');
        setStorageSyncResult(`Ø¯Ø± Ø­Ø§Ù„ Ø§Ø¬Ø±Ø§ÛŒ Sync ${title} ...`, 'info');
        const payload = await request(endpoint, { method: 'POST' });
        const processed = Number(payload?.processed || 0);
        const succeeded = Number(payload?.success || payload?.succeeded || 0);
        const failed = Number(payload?.failed || 0);
        const dead = Number(payload?.dead || 0);
        const summary = `Ù†ØªÛŒØ¬Ù‡ Sync ${title}: Ù¾Ø±Ø¯Ø§Ø²Ø´=${processed}ØŒ Ù…ÙˆÙÙ‚=${succeeded}ØŒ Ø®Ø·Ø§=${failed}ØŒ ØµÙâ€ŒÙ…Ø¹ÛŒÙˆØ¨=${dead}`;
        setStorageSyncResult(summary, failed > 0 || dead > 0 ? 'error' : 'success');
        if (failed > 0 || dead > 0) {
            tError(`${summary}. Ø¬Ø²Ø¦ÛŒØ§Øª Ø¯Ø± Ù¾Ù†Ù„ Ù†ØªÛŒØ¬Ù‡ Ù†Ù…Ø§ÛŒØ´ Ø¯Ø§Ø¯Ù‡ Ø´Ø¯.`);
            return;
        }
        tSuccess(summary);
    }

    function bindIntegrationsActions() {
        const root = document.getElementById('settingsIntegrationsRoot');
        if (!root || root.dataset.integrationsActionsBound === '1') return;
        const findEventTargetEl = (event, selector) => {
            if (!event || !selector) return null;
            const directTarget = event.target;
            if (directTarget instanceof Element) {
                const directMatch = directTarget.closest(selector);
                if (directMatch) return directMatch;
            }
            const path = typeof event.composedPath === 'function' ? event.composedPath() : [];
            for (const node of path) {
                if (!(node instanceof Element)) continue;
                if (node.matches(selector)) return node;
                const match = node.closest(selector);
                if (match) return match;
            }
            return null;
        };
        root.addEventListener('click', async (event) => {
            const providerTabEl = findEventTargetEl(event, '[data-integrations-provider-tab]');
            if (providerTabEl && root.contains(providerTabEl)) {
                event.preventDefault();
                setIntegrationsProviderTab(providerTabEl.dataset.integrationsProviderTab || 'openproject');
                return;
            }
            const tabEl = findEventTargetEl(event, '[data-op-tab]');
            if (tabEl && root.contains(tabEl)) {
                event.preventDefault();
                setOpenProjectSubTab(tabEl.dataset.opTab || 'connection');
                return;
            }
            const actionEl = findEventTargetEl(event, '[data-integrations-action]');
            if (!actionEl || !root.contains(actionEl)) return;
            event.preventDefault();
            const action = norm(actionEl.dataset.integrationsAction || '').toLowerCase();
            try {
                if (action === 'save-integrations') {
                    await saveStorageIntegrations();
                    return;
                }
                if (action === 'rotate-bim-revit-secret') {
                    await rotateBimRevitSecret();
                    return;
                }
                if (action === 'run-google-sync') {
                    await runStorageSyncJob('google_drive');
                    return;
                }
                if (action === 'run-nextcloud-sync') {
                    await runStorageSyncJob('nextcloud');
                    return;
                }
                if (action === 'run-openproject-sync') {
                    await runStorageSyncJob('openproject');
                    return;
                }
                if (action === 'ping-openproject') {
                    await pingOpenProject();
                    return;
                }
                if (action === 'ping-google-drive') {
                    await pingGoogle('drive');
                    return;
                }
                if (action === 'ping-google-gmail') {
                    await pingGoogle('gmail');
                    return;
                }
                if (action === 'ping-google-calendar') {
                    await pingGoogle('calendar');
                    return;
                }
                if (action === 'ping-nextcloud') {
                    await pingNextcloud();
                    return;
                }
                if (action === 'clear-openproject-token') {
                    await clearOpenProjectStoredToken();
                    return;
                }
                if (action === 'preview-openproject-project-work-packages') {
                    await previewOpenProjectProjectWorkPackages();
                    return;
                }
                if (action === 'import-openproject-project-work-packages') {
                    await importOpenProjectProjectWorkPackages();
                    return;
                }
                if (action === 'download-openproject-template') {
                    await downloadOpenProjectTemplate();
                    return;
                }
                if (action === 'validate-openproject-import') {
                    const run = await validateOpenProjectImportFile();
                    await pollOpenProjectRun(run?.id);
                    return;
                }
                if (action === 'execute-openproject-import') {
                    const run = await executeOpenProjectImportRun();
                    await pollOpenProjectRun(run?.id);
                    return;
                }
                if (action === 'refresh-openproject-import-data') {
                    await refreshOpenProjectImportData();
                    return;
                }
                if (action === 'select-openproject-import-run') {
                    const runId = Number(actionEl.dataset.runId || 0);
                    if (runId > 0) {
                        await loadOpenProjectImportRows(runId);
                    }
                    return;
                }
            } catch (err) {
                tError(err.message);
            }
        });
        root.addEventListener('change', () => {
            updateStorageIntegrationsFieldState();
        });
        root.addEventListener('input', (event) => {
            const target = event?.target;
            if (!target) return;
            if (target.id === 'storageOpenProjectApiTokenInput') {
                updateStorageIntegrationsFieldState();
            }
        });
        root.dataset.integrationsActionsBound = '1';
    }

    async function initSettingsIntegrations(force = false) {
        stopOpenProjectImportPolling();
        bindIntegrationsActions();
        await loadStorageIntegrations(force);
        await refreshOpenProjectImportData();
        setIntegrationsProviderTab(STORE.integrationsProviderTab || 'openproject');
        setOpenProjectSubTab(STORE.openprojectImport?.activeTab || 'connection');
        setOpenProjectImportSummary('');
        setOpenProjectProjectImportSummary('');
        renderOpenProjectProjectPreview([]);
        updateStorageIntegrationsFieldState();
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
            throw new Error('Ø§Ø¨ØªØ¯Ø§ ÛŒÚ© Ù¾Ø±ÙˆÙØ§ÛŒÙ„ Ø³Ø§ÛŒØª Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯.');
        }
        return selected;
    }

    function normalizeSiteCacheProfileCode(value) {
        const code = norm(value).toUpperCase();
        requireVal(code, 'Ú©Ø¯ Ø³Ø§ÛŒØª');
        if (!SITE_CACHE_CODE_RE.test(code)) {
            throw new Error('Ú©Ø¯ Ø³Ø§ÛŒØª ÙÙ‚Ø· Ù…ÛŒâ€ŒØªÙˆØ§Ù†Ø¯ Ø´Ø§Ù…Ù„ Ø­Ø±ÙˆÙ Ø§Ù†Ú¯Ù„ÛŒØ³ÛŒØŒ Ø¹Ø¯Ø¯ØŒ `_` Ùˆ `-` Ø¨Ø§Ø´Ø¯ (Ø­Ø¯Ø§Ù‚Ù„ Û² Ú©Ø§Ø±Ø§Ú©ØªØ±).');
        }
        return code;
    }

    function normalizeOptionalSiteCode(value, label, regex, maxLength) {
        const code = norm(value).toUpperCase();
        if (!code) return null;
        if (code.length > maxLength) {
            throw new Error(`${label} Ù†Ø¨Ø§ÛŒØ¯ Ø¨ÛŒØ´ØªØ± Ø§Ø² ${maxLength} Ú©Ø§Ø±Ø§Ú©ØªØ± Ø¨Ø§Ø´Ø¯.`);
        }
        if (!regex.test(code)) {
            throw new Error(`${label} ÙÙ‚Ø· Ù…ÛŒâ€ŒØªÙˆØ§Ù†Ø¯ Ø´Ø§Ù…Ù„ Ø­Ø±ÙˆÙ Ø§Ù†Ú¯Ù„ÛŒØ³ÛŒØŒ Ø¹Ø¯Ø¯ØŒ '_' Ùˆ '-' Ø¨Ø§Ø´Ø¯.`);
        }
        return code;
    }

    function normalizeSiteCacheRootPath(value) {
        const path = norm(value);
        if (!path) return null;
        if (path.length > 1024) {
            throw new Error('Ù…Ø³ÛŒØ± Ø±ÛŒØ´Ù‡ Ù…Ø­Ù„ÛŒ Ù†Ø¨Ø§ÛŒØ¯ Ø¨ÛŒØ´ØªØ± Ø§Ø² Û±Û°Û²Û´ Ú©Ø§Ø±Ø§Ú©ØªØ± Ø¨Ø§Ø´Ø¯.');
        }
        return path;
    }

    function normalizeSiteCacheFallbackMode(value) {
        const mode = norm(value).toLowerCase() || 'local_first';
        if (!['local_first', 'hq_first'].includes(mode)) {
            throw new Error('Ø­Ø§Ù„Øª fallback Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.');
        }
        return mode;
    }

    function normalizeSiteCacheRuleName(value) {
        const name = norm(value);
        requireVal(name, 'Ù†Ø§Ù… Ù‚Ø§Ù†ÙˆÙ†');
        if (name.length > 255) {
            throw new Error('Ù†Ø§Ù… Ù‚Ø§Ù†ÙˆÙ† Ù†Ø¨Ø§ÛŒØ¯ Ø¨ÛŒØ´ØªØ± Ø§Ø² Û²ÛµÛµ Ú©Ø§Ø±Ø§Ú©ØªØ± Ø¨Ø§Ø´Ø¯.');
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
                throw new Error(`Ú©Ø¯ ÙˆØ¶Ø¹ÛŒØª Ù†Ø§Ù…Ø¹ØªØ¨Ø± Ø§Ø³Øª: ${code}`);
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
            throw new Error('Ø§ÙˆÙ„ÙˆÛŒØª Ø¨Ø§ÛŒØ¯ ÛŒÚ© Ø¹Ø¯Ø¯ ØµØ­ÛŒØ­ Ø¨ÛŒÙ† Û° ØªØ§ Û±Û°Û°Û°Û° Ø¨Ø§Ø´Ø¯.');
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
            throw new Error('CIDR Ù†Ø§Ù…Ø¹ØªØ¨Ø± Ø§Ø³Øª. Ù†Ù…ÙˆÙ†Ù‡ ØµØ­ÛŒØ­: 10.88.0.0/16');
        }
        const ip = raw.slice(0, slash).trim();
        const prefixRaw = raw.slice(slash + 1).trim();
        if (!/^\d{1,3}$/.test(prefixRaw)) {
            throw new Error('Ø¨Ø®Ø´ Prefix Ø¯Ø± CIDR Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.');
        }
        const prefix = Number(prefixRaw);
        if (ip.includes(':')) {
            if (!validateIPv6Address(ip) || prefix < 0 || prefix > 128) {
                throw new Error('CIDR IPv6 Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.');
            }
            return `${ip}/${prefix}`;
        }
        if (!validateIPv4Address(ip) || prefix < 0 || prefix > 32) {
            throw new Error('CIDR IPv4 Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.');
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
            throw new Error(`${label} Ù†Ø¨Ø§ÛŒØ¯ Ø¨ÛŒØ´ØªØ± Ø§Ø² ${maxLength} Ú©Ø§Ø±Ø§Ú©ØªØ± Ø¨Ø§Ø´Ø¯.`);
        }
        if (!regex.test(raw)) {
            throw new Error(`${label} Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.`);
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
        refreshSiteCacheTokenMultiControl(selectEl.id);
    }

    function closeSiteCacheTokenMultiDropdown(exceptId = '') {
        Object.entries(STORE.siteCache.tokenMulti || {}).forEach(([selectId, ref]) => {
            if (!ref?.dropdown || selectId === exceptId) return;
            ref.dropdown.classList.remove('is-open');
            ref.trigger?.setAttribute('aria-expanded', 'false');
        });
    }

    function updateSiteCacheTokenMultiOptions(selectId) {
        const ref = STORE.siteCache.tokenMulti?.[selectId];
        if (!ref?.select || !ref.optionsBox) return;
        const q = norm(ref.searchInput?.value).toLowerCase();
        const selected = new Set(normalizeMultiSelectValues(getMultiSelectValues(ref.select)));
        const options = Array.from(ref.select.options || []).map((opt) => ({
            value: norm(opt.value).toUpperCase(),
            label: String(opt.textContent || '').trim(),
        }));
        const filtered = q
            ? options.filter((opt) => opt.label.toLowerCase().includes(q) || opt.value.toLowerCase().includes(q))
            : options;

        ref.optionsBox.innerHTML = filtered.length
            ? filtered.map((opt) => {
                const checked = selected.has(opt.value);
                return `
                    <button type="button" class="token-multi-option ${checked ? 'is-selected' : ''}" data-token-option-value="${esc(opt.value)}">
                        <span class="token-multi-option-check material-icons-round">${checked ? 'check_box' : 'check_box_outline_blank'}</span>
                        <span class="token-multi-option-label">${esc(opt.label)}</span>
                    </button>
                `;
            }).join('')
            : '<div class="token-multi-empty">Ú¯Ø²ÛŒÙ†Ù‡â€ŒØ§ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯.</div>';
    }

    function updateSiteCacheTokenMultiChips(selectId) {
        const ref = STORE.siteCache.tokenMulti?.[selectId];
        if (!ref?.select || !ref.chipsBox || !ref.placeholder) return;
        const values = normalizeMultiSelectValues(getMultiSelectValues(ref.select));
        const selectedValues = new Set(values);
        const options = Array.from(ref.select.options || []);
        const chips = [];

        values.forEach((value) => {
            if (value === SITE_CACHE_ALL_VALUE) {
                chips.push(`
                    <span class="token-chip token-chip-all">
                        <span>Ù‡Ù…Ù‡</span>
                    </span>
                `);
                return;
            }
            const opt = options.find((item) => norm(item?.value).toUpperCase() === value);
            const label = String(opt?.textContent || value).trim();
            chips.push(`
                <button type="button" class="token-chip" data-token-chip-value="${esc(value)}" title="${esc(label)}">
                    <span>${esc(label)}</span>
                    <span class="material-icons-round">close</span>
                </button>
            `);
        });

        ref.chipsBox.innerHTML = chips.join('');
        const showPlaceholder = values.length === 1 && values[0] === SITE_CACHE_ALL_VALUE;
        ref.placeholder.style.display = showPlaceholder ? '' : 'none';
        ref.placeholder.textContent = SITE_CACHE_TOKEN_MULTI_PLACEHOLDER[selectId] || 'Ø§Ù†ØªØ®Ø§Ø¨ Ú¯Ø²ÛŒÙ†Ù‡';
        ref.root.classList.toggle('is-disabled', Boolean(ref.select.disabled));
        ref.root.classList.toggle('has-value', !showPlaceholder);
        ref.trigger?.setAttribute('aria-expanded', ref.dropdown?.classList.contains('is-open') ? 'true' : 'false');
        ref.root.dataset.selected = Array.from(selectedValues).join(',');
    }

    function refreshSiteCacheTokenMultiControl(selectId) {
        const ref = STORE.siteCache.tokenMulti?.[selectId];
        if (!ref) return;
        updateSiteCacheTokenMultiChips(selectId);
        updateSiteCacheTokenMultiOptions(selectId);
    }

    function toggleSiteCacheTokenMultiValue(selectId, value) {
        const ref = STORE.siteCache.tokenMulti?.[selectId];
        if (!ref?.select || ref.select.disabled) return;
        const code = norm(value).toUpperCase();
        if (!code) return;
        let selected = normalizeMultiSelectValues(getMultiSelectValues(ref.select));
        if (code === SITE_CACHE_ALL_VALUE) {
            selected = [SITE_CACHE_ALL_VALUE];
        } else if (selected.includes(code)) {
            selected = selected.filter((item) => item !== code);
        } else {
            selected = selected.filter((item) => item !== SITE_CACHE_ALL_VALUE).concat([code]);
        }
        setMultiSelectValues(ref.select, selected.length ? selected : [SITE_CACHE_ALL_VALUE]);
        ref.select.dispatchEvent(new Event('change', { bubbles: true }));
        refreshSiteCacheTokenMultiControl(selectId);
    }

    function ensureSiteCacheTokenMultiControl(selectId) {
        const selectEl = document.getElementById(selectId);
        if (!selectEl) return;
        if (STORE.siteCache.tokenMulti?.[selectId]) {
            refreshSiteCacheTokenMultiControl(selectId);
            return;
        }

        const root = document.createElement('div');
        root.className = 'token-multi-root';
        root.dataset.selectId = selectId;

        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'token-multi-trigger';
        trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.setAttribute('aria-expanded', 'false');

        const chipsBox = document.createElement('div');
        chipsBox.className = 'token-multi-chips';

        const placeholder = document.createElement('span');
        placeholder.className = 'token-multi-placeholder';
        placeholder.textContent = SITE_CACHE_TOKEN_MULTI_PLACEHOLDER[selectId] || 'Ø§Ù†ØªØ®Ø§Ø¨ Ú¯Ø²ÛŒÙ†Ù‡';

        const icon = document.createElement('span');
        icon.className = 'material-icons-round token-multi-expand';
        icon.textContent = 'expand_more';

        trigger.appendChild(chipsBox);
        trigger.appendChild(placeholder);
        trigger.appendChild(icon);

        const dropdown = document.createElement('div');
        dropdown.className = 'token-multi-dropdown';

        const searchWrap = document.createElement('div');
        searchWrap.className = 'token-multi-search-wrap';

        const searchIcon = document.createElement('span');
        searchIcon.className = 'material-icons-round';
        searchIcon.textContent = 'search';

        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.className = 'token-multi-search-input';
        searchInput.placeholder = 'Ø¬Ø³ØªØ¬Ùˆ...';

        searchWrap.appendChild(searchIcon);
        searchWrap.appendChild(searchInput);

        const optionsBox = document.createElement('div');
        optionsBox.className = 'token-multi-options';

        dropdown.appendChild(searchWrap);
        dropdown.appendChild(optionsBox);
        root.appendChild(trigger);
        root.appendChild(dropdown);

        selectEl.classList.add('token-multi-native');
        selectEl.parentElement?.insertBefore(root, selectEl);

        STORE.siteCache.tokenMulti[selectId] = {
            select: selectEl,
            root,
            trigger,
            dropdown,
            searchInput,
            chipsBox,
            placeholder,
            optionsBox,
        };

        trigger.addEventListener('click', () => {
            if (selectEl.disabled) return;
            const willOpen = !dropdown.classList.contains('is-open');
            closeSiteCacheTokenMultiDropdown(willOpen ? selectId : '');
            dropdown.classList.toggle('is-open', willOpen);
            trigger.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            if (willOpen) {
                searchInput.focus();
                searchInput.select();
            }
            refreshSiteCacheTokenMultiControl(selectId);
        });

        searchInput.addEventListener('input', () => {
            updateSiteCacheTokenMultiOptions(selectId);
        });

        searchInput.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                dropdown.classList.remove('is-open');
                trigger.setAttribute('aria-expanded', 'false');
                trigger.focus();
            }
        });

        optionsBox.addEventListener('click', (event) => {
            const optionBtn = event?.target?.closest?.('[data-token-option-value]');
            if (!optionBtn) return;
            toggleSiteCacheTokenMultiValue(selectId, optionBtn.dataset.tokenOptionValue || '');
        });

        chipsBox.addEventListener('click', (event) => {
            const chipBtn = event?.target?.closest?.('[data-token-chip-value]');
            if (!chipBtn) return;
            const value = norm(chipBtn.dataset.tokenChipValue).toUpperCase();
            if (!value) return;
            const selected = normalizeMultiSelectValues(getMultiSelectValues(selectEl)).filter((item) => item !== value);
            setMultiSelectValues(selectEl, selected.length ? selected : [SITE_CACHE_ALL_VALUE]);
            selectEl.dispatchEvent(new Event('change', { bubbles: true }));
            refreshSiteCacheTokenMultiControl(selectId);
        });

        refreshSiteCacheTokenMultiControl(selectId);
    }

    function ensureSiteCacheTokenMultiControls() {
        SITE_CACHE_TOKEN_MULTI_IDS.forEach((selectId) => ensureSiteCacheTokenMultiControl(selectId));
    }

    function syncDisciplinesBySelectedPackages() {
        const packageSelect = document.getElementById('siteCacheRulePackageInput');
        const disciplineSelect = document.getElementById('siteCacheRuleDisciplineInput');
        if (!packageSelect || !disciplineSelect) return;
        const selectedPackages = normalizeMultiSelectValues(getMultiSelectValues(packageSelect));
        if (selectedPackages.includes(SITE_CACHE_ALL_VALUE)) return;
        const disciplines = [];
        selectedPackages.forEach((value) => {
            const code = norm(value).toUpperCase();
            const sep = code.indexOf('::');
            if (sep <= 0) return;
            const disc = code.slice(0, sep);
            if (disc && !disciplines.includes(disc)) disciplines.push(disc);
        });
        if (!disciplines.length) return;
        setMultiSelectValues(disciplineSelect, disciplines);
        fillSiteCacheRulePackageOptions(disciplines, selectedPackages);
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
                throw new Error(`Ù¾Ú©ÛŒØ¬ Ø§Ù†ØªØ®Ø§Ø¨â€ŒØ´Ø¯Ù‡ Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª: ${raw || '-'}`);
            }
            const discipline_code = toSiteCacheFilterCode(raw.slice(0, sep), SITE_CACHE_DISCIPLINE_CODE_RE, 'Ú©Ø¯ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ† Ù¾Ú©ÛŒØ¬', 20);
            const package_code = toSiteCacheFilterCode(raw.slice(sep + 2), SITE_CACHE_PACKAGE_CODE_RE, 'Ú©Ø¯ Ù¾Ú©ÛŒØ¬', 30);
            if (!discipline_code || !package_code) continue;
            out.push({ discipline_code, package_code });
        }
        return out.length ? out : [{ discipline_code: null, package_code: null }];
    }

    function buildSiteCacheRuleTargets(projectCodes, disciplineCodes, packageSelections) {
        const hasPackageScope = packageSelections.some((item) => item.package_code);
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
        return { targets: dedup, hasPackageScope };
    }

    function countEffectiveMultiSelect(selectEl, totalCount) {
        const values = normalizeMultiSelectValues(getMultiSelectValues(selectEl));
        if (!values.length || values.includes(SITE_CACHE_ALL_VALUE)) {
            return Number(totalCount || 0);
        }
        return values.length;
    }

    function updateSiteCacheRuleLiveSummary() {
        const summaryEl = document.getElementById('siteCacheRuleLiveSummary');
        const projectSelect = document.getElementById('siteCacheRuleProjectInput');
        const disciplineSelect = document.getElementById('siteCacheRuleDisciplineInput');
        const packageSelect = document.getElementById('siteCacheRulePackageInput');
        if (!summaryEl || !projectSelect || !disciplineSelect || !packageSelect) return;

        try {
            const projectCodes = parseSiteCacheFilterCodes(projectSelect, SITE_CACHE_PROJECT_CODE_RE, 'Ú©Ø¯ Ù¾Ø±ÙˆÚ˜Ù‡ Ù‚Ø§Ù†ÙˆÙ†', 50);
            const disciplineCodes = parseSiteCacheFilterCodes(disciplineSelect, SITE_CACHE_DISCIPLINE_CODE_RE, 'Ú©Ø¯ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ† Ù‚Ø§Ù†ÙˆÙ†', 20);
            const packageSelections = parseSiteCachePackageSelections(packageSelect);
            const compiled = buildSiteCacheRuleTargets(projectCodes, disciplineCodes, packageSelections);
            const projectCount = countEffectiveMultiSelect(projectSelect, (STORE.data.projects || []).length);
            const disciplineCount = countEffectiveMultiSelect(disciplineSelect, (STORE.data.disciplines || []).length);
            const packageOptionCount = Array.from(packageSelect.options || []).filter((opt) => norm(opt?.value).toUpperCase() !== SITE_CACHE_ALL_VALUE).length;
            const packageCount = countEffectiveMultiSelect(packageSelect, packageOptionCount);

            summaryEl.classList.remove('is-error');
            summaryEl.innerHTML = `
                <strong>Ø®Ù„Ø§ØµÙ‡ Ø§Ù†ØªØ®Ø§Ø¨:</strong>
                Ù¾Ø±ÙˆÚ˜Ù‡: ${Number(projectCount || 0)} |
                Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†: ${Number(disciplineCount || 0)} |
                Ù¾Ú©ÛŒØ¬: ${Number(packageCount || 0)} |
                ØªØ±Ú©ÛŒØ¨ Ù†Ù‡Ø§ÛŒÛŒ: ${compiled.targets.length}
            `;
        } catch (err) {
            summaryEl.classList.add('is-error');
            summaryEl.textContent = `ØªØ±Ú©ÛŒØ¨ ÙØ¹Ù„ÛŒ Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª: ${err.message || 'Ø®Ø·Ø§ÛŒ Ù†Ø§Ù…Ø´Ø®Øµ'}`;
        }
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
        const options = [`<option value="${SITE_CACHE_ALL_VALUE}">Ù‡Ù…Ù‡ Ù¾Ú©ÛŒØ¬â€ŒÙ‡Ø§</option>`]
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
        if (isAllDiscipline) {
            packageSelect.disabled = true;
            setMultiSelectValues(packageSelect, [SITE_CACHE_ALL_VALUE]);
            updateSiteCacheRuleLiveSummary();
            return;
        }
        packageSelect.disabled = false;
        const allowedValues = new Set(
            [SITE_CACHE_ALL_VALUE].concat(
                packageRows.map((row) => `${norm(row?.discipline_code).toUpperCase()}::${norm(row?.package_code).toUpperCase()}`)
            )
        );
        const nextValues = currentPackageValues.filter((value) => allowedValues.has(value));
        setMultiSelectValues(packageSelect, nextValues.length ? nextValues : [SITE_CACHE_ALL_VALUE]);
        updateSiteCacheRuleLiveSummary();
    }

    function fillSiteCacheRuleFilterOptions() {
        const projectSelect = document.getElementById('siteCacheRuleProjectInput');
        const disciplineSelect = document.getElementById('siteCacheRuleDisciplineInput');
        const packageSelect = document.getElementById('siteCacheRulePackageInput');
        if (!projectSelect || !disciplineSelect || !packageSelect) return;
        const currentProject = normalizeMultiSelectValues(getMultiSelectValues(projectSelect));
        const currentDiscipline = normalizeMultiSelectValues(getMultiSelectValues(disciplineSelect));
        const currentPackage = normalizeMultiSelectValues(getMultiSelectValues(packageSelect));
        const projectOptions = [`<option value="${SITE_CACHE_ALL_VALUE}">Ù‡Ù…Ù‡ Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§</option>`]
            .concat(
                (STORE.data.projects || []).map((row) => {
                    const code = norm(row?.code).toUpperCase();
                    const label = `${code || '-'} - ${norm(row?.project_name) || '-'}`;
                    return `<option value="${esc(code)}">${esc(label)}</option>`;
                })
            )
            .join('');
        const disciplineOptions = [`<option value="${SITE_CACHE_ALL_VALUE}">Ù‡Ù…Ù‡ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†â€ŒÙ‡Ø§</option>`]
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
        ensureSiteCacheTokenMultiControls();
        updateSiteCacheRuleLiveSummary();
    }

    function setSiteCacheListTab(tab) {
        const targetTab = ['cidr', 'rules', 'tokens'].includes(String(tab || '').toLowerCase())
            ? String(tab).toLowerCase()
            : (STORE.siteCache.activeListTab || 'cidr');
        STORE.siteCache.activeListTab = targetTab;
        document.querySelectorAll('.site-cache-list-tab[data-site-cache-list-tab]').forEach((btn) => {
            const isActive = String(btn?.dataset?.siteCacheListTab || '').toLowerCase() === targetTab;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        document.querySelectorAll('[data-site-cache-list-panel]').forEach((panel) => {
            const isActive = String(panel?.dataset?.siteCacheListPanel || '').toLowerCase() === targetTab;
            panel.classList.toggle('active', isActive);
            panel.hidden = !isActive;
        });
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
            tbody.innerHTML = '<tr><td colspan="5" class="text-center muted">Ù‡ÛŒÚ† Ù¾Ø±ÙˆÙØ§ÛŒÙ„ Ø³Ø§ÛŒØªÛŒ Ø«Ø¨Øª Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª.</td></tr>';
            profileSelect.innerHTML = '<option value="">Ø§Ù†ØªØ®Ø§Ø¨ Ù¾Ø±ÙˆÙØ§ÛŒÙ„ Ø³Ø§ÛŒØª</option>';
            setSiteCacheListTab('cidr');
            return;
        }

        if (!STORE.siteCache.activeProfileId || !profiles.some((item) => Number(item?.id || 0) === Number(STORE.siteCache.activeProfileId || 0))) {
            STORE.siteCache.activeProfileId = Number(profiles[0]?.id || 0);
        }

        tbody.innerHTML = profiles.map((item) => {
            const pid = Number(item?.id || 0);
            return `
                <tr data-bulk-key="${pid}" data-profile-id="${pid}">
                    <td>${esc(item?.code || '-')}</td>
                    <td>${esc(item?.name || '-')}</td>
                    <td>${esc(item?.project_code || '-')}</td>
                    <td>${boolBadge(Boolean(item?.is_active))}</td>
                    <td>${rowActions(`
                        <button class="btn-archive-icon" type="button" data-general-action="open-edit-site-cache-profile" data-profile-id="${pid}">ÙˆÛŒØ±Ø§ÛŒØ´</button>
                        <button class="btn-archive-icon btn-archive-danger-soft" type="button" data-general-action="delete-site-cache-profile" data-profile-id="${pid}">ØºÛŒØ±ÙØ¹Ø§Ù„</button>
                    `)}</td>
                </tr>
            `;
        }).join('');

        profileSelect.innerHTML = profiles
            .map((item) => `<option value="${Number(item?.id || 0)}">${esc(`${item?.code || '-'} - ${item?.name || '-'}`)}</option>`)
            .join('');
        profileSelect.value = String(STORE.siteCache.activeProfileId || '');
        setSiteCacheListTab(STORE.siteCache.activeListTab || 'cidr');
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
                    <button type="button" data-general-action="delete-site-cache-cidr" data-cidr-id="${Number(item?.id || 0)}" title="Ø­Ø°Ù CIDR">
                        <span class="material-icons-round">close</span>
                    </button>
                </div>
            `).join('')
            : '<div class="text-muted">CIDR Ø«Ø¨Øª Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª.</div>';

        ruleBox.innerHTML = rules.length
            ? rules.map((item) => `
                <div class="general-inline-chip">
                    <span class="material-icons-round">rule</span>
                    <span>${esc(item?.name || '-')} [${esc(item?.status_codes || '-')} ] (${esc(item?.project_code || 'Ù‡Ù…Ù‡')}/${esc(item?.discipline_code || 'Ù‡Ù…Ù‡')}/${esc(item?.package_code || 'Ù‡Ù…Ù‡')})</span>
                    <button type="button" data-general-action="delete-site-cache-rule" data-rule-id="${Number(item?.id || 0)}" title="Ø­Ø°Ù Ù‚Ø§Ù†ÙˆÙ†">
                        <span class="material-icons-round">close</span>
                    </button>
                </div>
            `).join('')
            : '<div class="text-muted">Ù‚Ø§Ù†ÙˆÙ†ÛŒ Ø«Ø¨Øª Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª.</div>';

        tokenBox.innerHTML = '<div class="text-muted">Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ...</div>';
        setSiteCacheListTab(STORE.siteCache.activeListTab || 'cidr');
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
                        <button class="site-cache-danger-inline" type="button" data-general-action="revoke-site-cache-token" data-token-id="${Number(item?.id || 0)}" title="Ù„ØºÙˆ ØªÙˆÚ©Ù†">
                            <span class="material-icons-round">close</span>
                        </button>
                    </div>
                `).join('')
                : '<div class="text-muted">ØªÙˆÚ©Ù† ÙØ¹Ø§Ù„ÛŒ ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ø¯.</div>';
        } catch (err) {
            tokenBox.innerHTML = `<div class="text-danger">${esc(err?.message || 'Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ ØªÙˆÚ©Ù†â€ŒÙ‡Ø§ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯.')}</div>`;
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
        ensureInputValidity(codeInput, 'ÙØ±Ù…Øª Ú©Ø¯ Ø³Ø§ÛŒØª Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.');
        ensureInputValidity(document.getElementById('siteCacheProfileProjectInput'), 'ÙØ±Ù…Øª Ú©Ø¯ Ù¾Ø±ÙˆÚ˜Ù‡ Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.');
        const code = normalizeSiteCacheProfileCode(codeInput.value);
        const name = norm(nameInput.value);
        requireVal(name, 'Ù†Ø§Ù… Ù¾Ø±ÙˆÙØ§ÛŒÙ„');
        if (name.length > 255) {
            throw new Error('Ù†Ø§Ù… Ù¾Ø±ÙˆÙØ§ÛŒÙ„ Ù†Ø¨Ø§ÛŒØ¯ Ø¨ÛŒØ´ØªØ± Ø§Ø² Û²ÛµÛµ Ú©Ø§Ø±Ø§Ú©ØªØ± Ø¨Ø§Ø´Ø¯.');
        }

        const editId = Number(codeInput.dataset.editId || 0);
        const payload = {
            id: editId > 0 ? editId : null,
            code,
            name,
            project_code: normalizeOptionalSiteCode(
                document.getElementById('siteCacheProfileProjectInput')?.value,
                'Ú©Ø¯ Ù¾Ø±ÙˆÚ˜Ù‡',
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
        tSuccess('Ù¾Ø±ÙˆÙØ§ÛŒÙ„ Site Cache Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
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
        if (!confirm('Ø§ÛŒÙ† Ù¾Ø±ÙˆÙØ§ÛŒÙ„ Site Cache ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´ÙˆØ¯ØŸ')) return;
        await request(`${API_BASE}/site-cache/profiles/delete`, {
            method: 'POST',
            body: JSON.stringify({ id: Number(profileId || 0), hard_delete: false }),
        });
        await loadSiteCache(true);
        tSuccess('Ù¾Ø±ÙˆÙØ§ÛŒÙ„ ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´Ø¯.');
    }

    async function addSiteCacheCidr() {
        const profileId = getActiveSiteCacheProfileId();
        ensureInputValidity(document.getElementById('siteCacheCidrInput'), 'ÙØ±Ù…Øª CIDR Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.');
        const cidr = normalizeSiteCacheCidr(document.getElementById('siteCacheCidrInput')?.value);
        await request(`${API_BASE}/site-cache/cidrs/upsert`, {
            method: 'POST',
            body: JSON.stringify({ profile_id: profileId, cidr, is_active: true }),
        });
        const input = document.getElementById('siteCacheCidrInput');
        if (input) input.value = '';
        await loadSiteCache(true);
        tSuccess('CIDR Ø§Ø¶Ø§ÙÙ‡ Ø´Ø¯.');
    }

    async function deleteSiteCacheCidr(cidrId) {
        await request(`${API_BASE}/site-cache/cidrs/delete`, {
            method: 'POST',
            body: JSON.stringify({ id: Number(cidrId || 0) }),
        });
        await loadSiteCache(true);
        tSuccess('CIDR Ø­Ø°Ù Ø´Ø¯.');
    }

    async function addSiteCacheRule() {
        const profileId = getActiveSiteCacheProfileId();
        ensureInputValidity(document.getElementById('siteCacheRulePriorityInput'), 'Ø§ÙˆÙ„ÙˆÛŒØª Ø¨Ø§ÛŒØ¯ Ø¨ÛŒÙ† Û° ØªØ§ Û±Û°Û°Û°Û° Ø¨Ø§Ø´Ø¯.');
        const name = normalizeSiteCacheRuleName(document.getElementById('siteCacheRuleNameInput')?.value);
        const projectSelect = document.getElementById('siteCacheRuleProjectInput');
        const disciplineSelect = document.getElementById('siteCacheRuleDisciplineInput');
        const packageSelect = document.getElementById('siteCacheRulePackageInput');
        const projectCodes = parseSiteCacheFilterCodes(projectSelect, SITE_CACHE_PROJECT_CODE_RE, 'Ú©Ø¯ Ù¾Ø±ÙˆÚ˜Ù‡ Ù‚Ø§Ù†ÙˆÙ†', 50);
        const disciplineCodes = parseSiteCacheFilterCodes(disciplineSelect, SITE_CACHE_DISCIPLINE_CODE_RE, 'Ú©Ø¯ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ† Ù‚Ø§Ù†ÙˆÙ†', 20);
        const packageSelections = parseSiteCachePackageSelections(packageSelect);
        const statusCodes = parseSiteCacheStatusCodes(document.getElementById('siteCacheRuleStatusInput')?.value);
        const includeNative = Boolean(document.getElementById('siteCacheRuleIncludeNativeInput')?.checked);
        const primaryOnly = Boolean(document.getElementById('siteCacheRulePrimaryOnlyInput')?.checked);
        const priority = parseSiteCachePriority(document.getElementById('siteCacheRulePriorityInput')?.value);
        const compiled = buildSiteCacheRuleTargets(projectCodes, disciplineCodes, packageSelections);
        const dedup = compiled.targets;
        if (!dedup.length) {
            throw new Error('ØªØ±Ú©ÛŒØ¨ Ø§Ù†ØªØ®Ø§Ø¨ÛŒ Ù¾Ø±ÙˆÚ˜Ù‡/Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†/Ù¾Ú©ÛŒØ¬ Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.');
        }
        if (dedup.length > 100) {
            throw new Error('ØªØ¹Ø¯Ø§Ø¯ ØªØ±Ú©ÛŒØ¨â€ŒÙ‡Ø§ÛŒ Ø§Ù†ØªØ®Ø§Ø¨ÛŒ Ø²ÛŒØ§Ø¯ Ø§Ø³Øª (Ø¨ÛŒØ´ Ø§Ø² Û±Û°Û°). Ù„Ø·ÙØ§Ù‹ ÙÛŒÙ„ØªØ±Ù‡Ø§ Ø±Ø§ Ù…Ø­Ø¯ÙˆØ¯ØªØ± Ú©Ù†ÛŒØ¯.');
        }

        const existingRules = Array.isArray(currentSiteCacheProfile()?.rules) ? currentSiteCacheProfile().rules : [];
        const makeRuleKey = (payload) => [
            norm(payload.name),
            norm(payload.project_code || 'ALL'),
            norm(payload.discipline_code || 'ALL'),
            norm(payload.package_code || 'ALL'),
            norm(payload.status_codes),
            payload.include_native ? '1' : '0',
            payload.primary_only ? '1' : '0',
            '1',
            String(Number(payload.priority || 0)),
            payload.is_active ? '1' : '0',
        ].join('|');
        const existingKeys = new Set(existingRules.map((row) => makeRuleKey({
            name: row?.name || '',
            project_code: row?.project_code,
            discipline_code: row?.discipline_code,
            package_code: row?.package_code,
            status_codes: row?.status_codes || 'IFA,IFC',
            include_native: Boolean(row?.include_native),
            primary_only: Boolean(row?.primary_only),
            priority: Number(row?.priority || 0),
            is_active: Boolean(row?.is_active ?? true),
        })));

        let createdCount = 0;
        let existedCount = 0;
        for (const target of dedup) {
            const scopeLabel = `${target.project_code || 'Ù‡Ù…Ù‡'}/${target.discipline_code || 'Ù‡Ù…Ù‡'}/${target.package_code || 'Ù‡Ù…Ù‡'}`;
            const scopedName = dedup.length > 1 ? `${name} [${scopeLabel}]` : name;
            const payload = {
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
            };
            const key = makeRuleKey(payload);
            if (existingKeys.has(key)) {
                existedCount += 1;
                continue;
            }
            await request(`${API_BASE}/site-cache/rules/upsert`, {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            createdCount += 1;
            existingKeys.add(key);
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
        const summary = `${createdCount} Ù‚Ø§Ù†ÙˆÙ† Ø§ÛŒØ¬Ø§Ø¯ Ø´Ø¯ØŒ ${existedCount} Ù‚Ø§Ù†ÙˆÙ† Ø§Ø² Ù‚Ø¨Ù„ ÙˆØ¬ÙˆØ¯ Ø¯Ø§Ø´Øª (Ø§ÛŒØ¬Ø§Ø¯ Ù†Ø´Ø¯).`;
        setSiteCacheTokenMessage(summary, createdCount > 0 ? 'success' : 'info');
        tSuccess(summary);
    }

    async function deleteSiteCacheRule(ruleId) {
        await request(`${API_BASE}/site-cache/rules/delete`, {
            method: 'POST',
            body: JSON.stringify({ id: Number(ruleId || 0) }),
        });
        await loadSiteCache(true);
        tSuccess('Ù‚Ø§Ù†ÙˆÙ† Ø­Ø°Ù Ø´Ø¯.');
    }

    async function mintSiteCacheToken() {
        const profileId = getActiveSiteCacheProfileId();
        const payload = await request(`${API_BASE}/site-cache/tokens/mint`, {
            method: 'POST',
            body: JSON.stringify({ profile_id: profileId }),
        });
        const token = String(payload?.token || '').trim();
        if (token) {
            setSiteCacheTokenMessage(`ØªÙˆÚ©Ù† Agent (ÙÙ‚Ø· ÛŒÚ©â€ŒØ¨Ø§Ø± Ù†Ù…Ø§ÛŒØ´): ${token}`, 'success');
        }
        await loadSiteCacheTokens(profileId);
        tSuccess('ØªÙˆÚ©Ù† Agent Ø¬Ø¯ÛŒØ¯ Ø§ÛŒØ¬Ø§Ø¯ Ø´Ø¯.');
    }

    async function revokeSiteCacheToken(tokenId) {
        if (!confirm('Ø§ÛŒÙ† ØªÙˆÚ©Ù† Agent Ù„ØºÙˆ Ø´ÙˆØ¯ØŸ')) return;
        await request(`${API_BASE}/site-cache/tokens/revoke`, {
            method: 'POST',
            body: JSON.stringify({ token_id: Number(tokenId || 0) }),
        });
        await loadSiteCache(true);
        setSiteCacheTokenMessage('');
        tSuccess('ØªÙˆÚ©Ù† Ù„ØºÙˆ Ø´Ø¯.');
    }

    async function rebuildSiteCachePins() {
        const profileId = getActiveSiteCacheProfileId();
        const payload = await request(`${API_BASE}/site-cache/rebuild-pins`, {
            method: 'POST',
            body: JSON.stringify({ profile_id: profileId, dry_run: false }),
        });
        const result = payload?.result || {};
        const summary = `Ø¨Ø§Ø²Ø³Ø§Ø²ÛŒ Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯: Ø§Ù†ØªØ®Ø§Ø¨=${Number(result.selected_count || 0)}ØŒ ÙØ¹Ø§Ù„=${Number(result.to_enable_count || 0)}ØŒ ØºÛŒØ±ÙØ¹Ø§Ù„=${Number(result.to_disable_count || 0)}`;
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
        const generalPanel = document.getElementById('tab-general');
        const activeBtn = generalPanel?.querySelector('.general-settings-btn.active[data-general-tab]');
        if (activeBtn?.dataset?.generalTab) return activeBtn.dataset.generalTab;
        const el = generalPanel?.querySelector('.general-settings-page.active');
        if (!el?.id) return STORE.activePage || 'db_sync';
        return el.id.replace('general-page-', '');
    }

    function toggleGeneralStorageSections(page) {
        const dbPage = document.getElementById('general-page-db');
        if (!dbPage) return;
        const showStorage = page === 'storage';
        const moduleNav = document.querySelector('.general-module-nav');
        const settingsNav = document.querySelector('.general-settings-nav');
        const dbOnlySections = Array.from(dbPage.querySelectorAll('.general-db-only'));
        const storageOnlySections = Array.from(dbPage.querySelectorAll('.general-storage-only'));
        if (moduleNav) {
            moduleNav.style.display = showStorage ? 'none' : '';
        }
        if (settingsNav) {
            settingsNav.style.display = showStorage ? 'none' : '';
        }
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
        const generalPanel = document.getElementById('tab-general');
        const buttons = Array.from(generalPanel?.querySelectorAll('.general-settings-btn[data-general-tab]') || []);
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
        toggleGeneralStorageSections(page);
        if (page === 'db_sync') {
            await loadOverview();
            await loadEntity('projects', force);
            refreshProjectCards();
            return;
        }
        if (page === 'storage') {
            bindStorageWorkflowInputs();
            setStorageWizardStep('paths', { force: true });
            await loadStoragePaths(force);
            await loadStoragePolicy(force);
            try {
                await loadSiteCache(force);
            } catch (err) {
                setSiteCacheTokenMessage(`Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Site Cache: ${err.message}`, 'error');
            }
            updateStoragePathPreview();
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
            const insideTokenMulti = Boolean(event?.target?.closest?.('.token-multi-root'));
            if (!insideTokenMulti) closeSiteCacheTokenMultiDropdown('');
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
                case 'run-storage-nextcloud-sync':
                    window.runStorageNextcloudSync();
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
                case 'switch-site-cache-list-tab':
                    setSiteCacheListTab(actionEl.dataset.siteCacheListTab || 'cidr');
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
                } else if (target?.id === 'siteCacheRulePackageInput') {
                    syncDisciplinesBySelectedPackages();
                    updateSiteCacheRuleLiveSummary();
                } else if (target?.id === 'siteCacheRuleProjectInput') {
                    updateSiteCacheRuleLiveSummary();
                }
                if (target?.id && SITE_CACHE_TOKEN_MULTI_IDS.includes(target.id)) {
                    refreshSiteCacheTokenMultiControl(target.id);
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
        registerGeneralBulkActions();
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
        await reloadEntitiesAfterMutation(reloadEntities);
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
            setSiteCacheTokenMessage('Ø§Ø·Ù„Ø§Ø¹Ø§Øª Site Cache Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø¨Ø§Ø²Ø®ÙˆØ§Ù†ÛŒ Ø´Ø¯.', 'info');
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
        const generalPanel = document.getElementById('tab-general');
        if (!generalPanel) return;
        generalPanel.querySelectorAll('.general-settings-btn').forEach((b) => b.classList.remove('active'));
        generalPanel.querySelectorAll('.general-settings-page').forEach((p) => p.classList.remove('active'));
        const btn = btnEl || generalPanel.querySelector(`.general-settings-btn[data-general-tab="${page}"]`);
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
        const generalPanel = document.getElementById('tab-general');
        if (!generalPanel) return;

        generalPanel.querySelectorAll('.general-module-btn').forEach((b) => b.classList.remove('active'));
        const moduleBtn = btnEl || generalPanel.querySelector(`.general-module-btn[data-general-domain="${normalizedDomain}"]`);
        if (moduleBtn) moduleBtn.classList.add('active');

        const preferredVisible = applyGeneralDomainVisibility(normalizedDomain);
        const activeBtn = generalPanel.querySelector('.general-settings-btn.active');
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
            const network_username = norm(document.getElementById('storageNetworkUsernameInput')?.value);
            const network_password = String(document.getElementById('storageNetworkPasswordInput')?.value || '').trim();
            requireVal(mdr_storage_path, 'Ù…Ø³ÛŒØ± Ø°Ø®ÛŒØ±Ù‡ Ù…Ø¯Ø§Ø±Ú© Ù…Ù‡Ù†Ø¯Ø³ÛŒ');
            requireVal(correspondence_storage_path, 'Ù…Ø³ÛŒØ± Ø°Ø®ÛŒØ±Ù‡ Ù…Ú©Ø§ØªØ¨Ø§Øª');
            if (!validateStoragePathConflict(true)) return;

            const payload = await request(`${API_BASE}/storage-paths`, {
                method: 'POST',
                body: JSON.stringify({
                    mdr_storage_path,
                    correspondence_storage_path,
                    network_username,
                    network_password,
                }),
            });

            document.getElementById('mdrStoragePathInput').value = norm(payload?.mdr_storage_path || mdr_storage_path);
            document.getElementById('correspondenceStoragePathInput').value = norm(
                payload?.correspondence_storage_path || correspondence_storage_path
            );
            const networkPasswordInput = document.getElementById('storageNetworkPasswordInput');
            if (networkPasswordInput) networkPasswordInput.value = '';
            document.getElementById('mdrStoragePathInput').dataset.storagePathDirty = '0';
            document.getElementById('correspondenceStoragePathInput').dataset.storagePathDirty = '0';
            updateStoragePathPreview();
            setStoragePathConflictError('');
            STORE.storagePathsLoaded = true;
            clearStorageStepDirty('paths');
            showStorageStepSaved('paths', 'Ù…Ø³ÛŒØ±Ù‡Ø§ÛŒ Ø°Ø®ÛŒØ±Ù‡â€ŒØ³Ø§Ø²ÛŒ Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯Ù†Ø¯.');
            tSuccess('Ù…Ø³ÛŒØ±Ù‡Ø§ÛŒ Ø°Ø®ÛŒØ±Ù‡â€ŒØ³Ø§Ø²ÛŒ Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯.');
        } catch (err) {
            const lines = Array.isArray(err?.details)
                ? err.details
                    .map((item) => {
                        if (!item || typeof item !== 'object') return norm(item);
                        const field = norm(item.field || '');
                        const text = norm(item.message || item.detail || '');
                        if (field && text) return `${field}: ${text}`;
                        return text;
                    })
                    .filter(Boolean)
                : [];
            if (lines.length) setStoragePathConflictError(lines.join(' | '));
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
            setStorageSyncResult(`Ø§Ø¬Ø±Ø§ÛŒ Sync Ú¯ÙˆÚ¯Ù„â€ŒØ¯Ø±Ø§ÛŒÙˆ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯: ${detail}`, 'error');
            tError(`Sync Ú¯ÙˆÚ¯Ù„â€ŒØ¯Ø±Ø§ÛŒÙˆ Ø§Ù†Ø¬Ø§Ù… Ù†Ø´Ø¯. ${detail}`);
        }
    };

    window.runStorageOpenProjectSync = async function runStorageOpenProjectSync() {
        try {
            await runStorageSyncJob('openproject');
        } catch (err) {
            const detail = String(err?.message || 'OpenProject sync failed.');
            setStorageSyncResult(`Ø§Ø¬Ø±Ø§ÛŒ Sync Ø§ÙˆÙ¾Ù†â€ŒÙ¾Ø±Ø§Ø¬Ú©Øª Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯: ${detail}`, 'error');
            tError(`Sync Ø§ÙˆÙ¾Ù†â€ŒÙ¾Ø±Ø§Ø¬Ú©Øª Ø§Ù†Ø¬Ø§Ù… Ù†Ø´Ø¯. ${detail}`);
        }
    };

    window.runStorageNextcloudSync = async function runStorageNextcloudSync() {
        try {
            await runStorageSyncJob('nextcloud');
        } catch (err) {
            const detail = String(err?.message || 'Nextcloud sync failed.');
            setStorageSyncResult(`Nextcloud sync failed: ${detail}`, 'error');
            tError(`Nextcloud sync failed. ${detail}`);
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
    window.initSettingsIntegrations = initSettingsIntegrations;
})();

