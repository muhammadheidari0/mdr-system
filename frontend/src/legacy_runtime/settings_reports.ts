// @ts-nocheck
(() => {
    const API_BASE = '/api/v1/settings';
    const ACCESS_REPORT_ENDPOINT = `${API_BASE}/permissions/access-report`;
    const ACCESS_REPORT_CSV_ENDPOINT = `${API_BASE}/permissions/access-report.csv`;
    const SCOPE_ENDPOINT = `${API_BASE}/permissions/scope`;
    const AUDIT_ENDPOINT = `${API_BASE}/audit-logs`;
    const USERS_ENDPOINT = '/api/v1/users/';

    const state = {
        initialized: false,
        bound: false,
        projects: [],
        disciplines: [],
        users: [],
        accessReport: {
            items: [],
            page: 1,
            pageSize: 20,
        },
        auditLogs: {
            items: [],
            page: 1,
            pageSize: 20,
            total: 0,
            totalPages: 1,
            offset: 0,
        },
    };

    function esc(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function norm(value) {
        return String(value ?? '').trim();
    }

    function toInt(value, fallback) {
        const parsed = Number(value);
        if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
        return Math.floor(parsed);
    }

    function toNonNegativeInt(value, fallback) {
        const parsed = Number(value);
        if (!Number.isFinite(parsed) || parsed < 0) return fallback;
        return Math.floor(parsed);
    }

    function notify(type, message) {
        if (window.UI && typeof window.UI[type] === 'function') {
            window.UI[type](message);
            return;
        }
        if (typeof showToast === 'function') {
            showToast(message, type === 'error' ? 'error' : 'success');
            return;
        }
        alert(message);
    }

    async function request(url, options = {}) {
        const fn = typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : fetch;
        const res = await fn(url, options);
        if (!res.ok) {
            let message = `Request failed (${res.status})`;
            try {
                const body = await res.clone().json();
                message = body.detail || body.message || message;
            } catch (_) {
                try {
                    message = await res.text();
                } catch (_) {}
            }
            throw new Error(message);
        }
        return res.json();
    }

    function setSelectOptions(selectId, rows, allLabel) {
        const selectEl = document.getElementById(selectId);
        if (!selectEl) return;
        const previous = norm(selectEl.value).toUpperCase();

        const options = [
            `<option value="">${esc(allLabel)}</option>`,
            ...rows.map((row) => {
                const code = norm(row.code).toUpperCase();
                const name = norm(row.name) || code;
                return `<option value="${esc(code)}">${esc(`${code} - ${name}`)}</option>`;
            }),
        ];
        selectEl.innerHTML = options.join('');

        if (previous && rows.some((r) => norm(r.code).toUpperCase() === previous)) {
            selectEl.value = previous;
        }
    }

    function setUserOptions(selectId, users) {
        const selectEl = document.getElementById(selectId);
        if (!selectEl) return;
        const previous = norm(selectEl.value);

        const options = users.map((u) => {
            const label = `${u.full_name || u.email} (${u.email})`;
            return `<option value="${esc(u.id)}">${esc(label)}</option>`;
        });
        selectEl.innerHTML = options.join('');

        if (!users.length) {
            selectEl.innerHTML = '<option value="">Ú©Ø§Ø±Ø¨Ø±ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯</option>';
            return;
        }
        if (previous && users.some((u) => String(u.id) === previous)) {
            selectEl.value = previous;
        } else {
            selectEl.value = String(users[0].id);
        }
    }

    function queryString(params) {
        const q = new URLSearchParams();
        Object.entries(params || {}).forEach(([key, value]) => {
            const v = value === undefined || value === null ? '' : String(value).trim();
            if (!v) return;
            q.set(key, v);
        });
        return q.toString();
    }

    function paginate(items, page, pageSize) {
        const safeItems = Array.isArray(items) ? items : [];
        const total = safeItems.length;
        const safePageSize = Math.max(1, toInt(pageSize, 20));
        const totalPages = Math.max(1, Math.ceil(total / safePageSize));
        const safePage = Math.min(Math.max(1, toInt(page, 1)), totalPages);
        const from = total === 0 ? 0 : (safePage - 1) * safePageSize + 1;
        const to = Math.min(total, safePage * safePageSize);
        const rows = safeItems.slice(from > 0 ? from - 1 : 0, to);
        return { total, totalPages, page: safePage, pageSize: safePageSize, from, to, rows };
    }

    function renderPager(containerId, info, onPageFn) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = `
            <div class="general-pager-left">Ù†Ù…Ø§ÛŒØ´ ${info.from}-${info.to} Ø§Ø² ${info.total} (Ø³Ø§ÛŒØ²: ${info.pageSize})</div>
            <div class="general-pager-right">
                <button class="btn-archive-icon" type="button" ${info.page <= 1 ? 'disabled' : ''} data-settings-reports-action="${esc(onPageFn)}" data-page="${info.page - 1}">Ù‚Ø¨Ù„ÛŒ</button>
                <span>ØµÙØ­Ù‡ ${info.page} Ø§Ø² ${info.totalPages}</span>
                <button class="btn-archive-icon" type="button" ${info.page >= info.totalPages ? 'disabled' : ''} data-settings-reports-action="${esc(onPageFn)}" data-page="${info.page + 1}">Ø¨Ø¹Ø¯ÛŒ</button>
            </div>
        `;
    }

    function accessBadge(allowed) {
        return allowed
            ? '<span class="status-badge active">Ù…Ø¬Ø§Ø²</span>'
            : '<span class="status-badge inactive">ØºÛŒØ±Ù…Ø¬Ø§Ø²</span>';
    }

    function activeBadge(isActive) {
        return isActive
            ? '<span class="status-badge active">ÙØ¹Ø§Ù„</span>'
            : '<span class="status-badge inactive">ØºÛŒØ±ÙØ¹Ø§Ù„</span>';
    }

    function scopeText(restricted, values) {
        if (!restricted) return 'Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª';
        if (!Array.isArray(values) || !values.length) return '-';
        return values.join(', ');
    }

    function syncAccessPageSizeFromDom() {
        const accessSize = toInt(document.getElementById('settingsAccessPageSize')?.value, state.accessReport.pageSize);
        state.accessReport.pageSize = accessSize;
    }

    function syncAuditPageSizeFromDom() {
        const auditSize = toInt(document.getElementById('settingsAuditPageSize')?.value, state.auditLogs.pageSize);
        state.auditLogs.pageSize = auditSize;
    }

    function renderAccessReportRows() {
        syncAccessPageSizeFromDom();
        const tbody = document.getElementById('settingsAccessReportRows');
        const meta = document.getElementById('settingsAccessReportMeta');
        if (!tbody || !meta) return;

        const info = paginate(state.accessReport.items, state.accessReport.page, state.accessReport.pageSize);
        state.accessReport.page = info.page;
        state.accessReport.pageSize = info.pageSize;

        if (!info.rows.length) {
            tbody.innerHTML = '<tr><td class="center-text muted" colspan="6" style="padding: 24px;">Ø±Ú©ÙˆØ±Ø¯ÛŒ Ø¨Ø±Ø§ÛŒ Ù†Ù…Ø§ÛŒØ´ ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ø¯.</td></tr>';
            meta.textContent = `ØªØ¹Ø¯Ø§Ø¯ Ù†ØªÛŒØ¬Ù‡: ${info.total}`;
            renderPager('settingsAccessPager', info, 'gotoSettingsAccessPage');
            return;
        }

        tbody.innerHTML = info.rows.map((item) => `
            <tr>
                <td>
                    <div>${esc(item.full_name || '-')}</div>
                    <div class="muted" style="font-size:0.8rem;">${esc(item.email || '-')}</div>
                </td>
                <td>${esc(item.role || '-')}</td>
                <td>${activeBadge(Boolean(item.is_active))}</td>
                <td>${accessBadge(Boolean(item.has_access))}</td>
                <td>${esc(scopeText(Boolean(item.projects_restricted), item.effective_projects))}</td>
                <td>${esc(scopeText(Boolean(item.disciplines_restricted), item.effective_disciplines))}</td>
            </tr>
        `).join('');
        meta.textContent = `ØªØ¹Ø¯Ø§Ø¯ Ù†ØªÛŒØ¬Ù‡: ${info.total}`;
        renderPager('settingsAccessPager', info, 'gotoSettingsAccessPage');
    }

    function renderUserScopeList(containerId, items) {
        const ul = document.getElementById(containerId);
        if (!ul) return;
        if (!Array.isArray(items) || !items.length) {
            ul.innerHTML = '<li class="muted">Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª</li>';
            return;
        }
        ul.innerHTML = items.map((item) => `<li>${esc(item.code || '-')} - ${esc(item.name || item.code || '-')}</li>`).join('');
    }

    function renderUserAccess(payload) {
        const summary = document.getElementById('settingsUserAccessSummary');
        if (!summary) return;

        const user = payload?.user || {};
        const effective = payload?.effective_scope || {};
        const catalog = payload?.effective_scope_catalog || {};
        summary.innerHTML = `
            <div class="settings-user-summary-grid">
                <div><strong>Ú©Ø§Ø±Ø¨Ø±:</strong> ${esc(user.full_name || user.email || '-')}</div>
                <div><strong>Ù†Ù‚Ø´:</strong> ${esc(user.role || '-')}</div>
                <div><strong>ÙˆØ¶Ø¹ÛŒØª:</strong> ${user.is_active ? 'ÙØ¹Ø§Ù„' : 'ØºÛŒØ±ÙØ¹Ø§Ù„'}</div>
                <div><strong>Project Scope:</strong> ${effective.projects_restricted ? 'Ù…Ø­Ø¯ÙˆØ¯' : 'Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª'}</div>
                <div><strong>Discipline Scope:</strong> ${effective.disciplines_restricted ? 'Ù…Ø­Ø¯ÙˆØ¯' : 'Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª'}</div>
            </div>
        `;

        renderUserScopeList('settingsUserAccessProjects', catalog.projects || []);
        renderUserScopeList('settingsUserAccessDisciplines', catalog.disciplines || []);
    }

    function prettyJson(rawText) {
        const raw = norm(rawText);
        if (!raw) return '';
        try {
            return JSON.stringify(JSON.parse(raw), null, 2);
        } catch (_) {
            return raw;
        }
    }

    function openJsonModal(title, rawText, metaText) {
        const modal = document.getElementById('settingsJsonModal');
        const modalTitle = document.getElementById('settingsJsonModalTitle');
        const modalMeta = document.getElementById('settingsJsonModalMeta');
        const modalContent = document.getElementById('settingsJsonModalContent');
        if (!modal || !modalTitle || !modalMeta || !modalContent) return;

        modalTitle.textContent = title;
        modalMeta.textContent = metaText || '';
        modalContent.textContent = prettyJson(rawText) || '{}';
        modal.style.display = 'flex';
    }

    function closeJsonModal() {
        const modal = document.getElementById('settingsJsonModal');
        if (!modal) return;
        modal.style.display = 'none';
    }

    function jsonActionButton(index, field, rawValue) {
        if (!norm(rawValue)) return '-';
        return `<button class="btn-archive-icon" type="button" data-settings-reports-action="open-settings-audit-json-modal" data-index="${index}" data-field="${esc(field)}">Ù†Ù…Ø§ÛŒØ´ JSON</button>`;
    }

    function renderAuditRows() {
        const tbody = document.getElementById('settingsAuditLogRows');
        const meta = document.getElementById('settingsAuditMeta');
        if (!tbody || !meta) return;

        const rows = Array.isArray(state.auditLogs.items) ? state.auditLogs.items : [];
        const total = toNonNegativeInt(state.auditLogs.total, rows.length);
        const pageSize = Math.max(1, toInt(state.auditLogs.pageSize, 20));
        const totalPages = Math.max(1, toInt(state.auditLogs.totalPages, Math.ceil(Math.max(1, total) / pageSize)));
        const page = Math.min(Math.max(1, toInt(state.auditLogs.page, 1)), totalPages);
        const from = total === 0 || rows.length === 0 ? 0 : ((page - 1) * pageSize) + 1;
        const to = total === 0 || rows.length === 0 ? 0 : Math.min(total, from + rows.length - 1);

        const info = { total, totalPages, page, pageSize, from, to };
        state.auditLogs.page = page;
        state.auditLogs.pageSize = pageSize;
        state.auditLogs.total = total;
        state.auditLogs.totalPages = totalPages;

        if (!rows.length) {
            tbody.innerHTML = '<tr><td class="center-text muted" colspan="6" style="padding: 24px;">Ù„Ø§Ú¯ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯.</td></tr>';
            meta.textContent = `ØªØ¹Ø¯Ø§Ø¯ Ù„Ø§Ú¯: ${total}`;
            renderPager('settingsAuditPager', info, 'gotoSettingsAuditPage');
            return;
        }

        tbody.innerHTML = rows.map((row, idx) => `
            <tr>
                <td>${esc(row.created_at || '-')}</td>
                <td>${esc(row.action || '-')}</td>
                <td>
                    <div>${esc(row.target_type || '-')}</div>
                    <div class="muted" style="font-size:0.8rem;">${esc(row.target_key || '-')}</div>
                </td>
                <td>
                    <div>${esc(row.actor_name || '-')}</div>
                    <div class="muted" style="font-size:0.8rem;">${esc(row.actor_email || '-')}</div>
                </td>
                <td>${jsonActionButton(idx, 'before', row.before_json)}</td>
                <td>${jsonActionButton(idx, 'after', row.after_json)}</td>
            </tr>
        `).join('');
        meta.textContent = `ØªØ¹Ø¯Ø§Ø¯ Ù„Ø§Ú¯: ${total}`;
        renderPager('settingsAuditPager', info, 'gotoSettingsAuditPage');
    }

    function selectedFilters() {
        const projectCode = norm(document.getElementById('reportProjectCode')?.value).toUpperCase();
        const disciplineCode = norm(document.getElementById('reportDisciplineCode')?.value).toUpperCase();
        const includeInactive = Boolean(document.getElementById('reportIncludeInactive')?.checked);
        const includeDenied = Boolean(document.getElementById('reportIncludeDenied')?.checked);
        return { projectCode, disciplineCode, includeInactive, includeDenied };
    }

    async function loadMetadata(force = false) {
        if (state.initialized && !force) return;
        const [scopePayload, usersPayload] = await Promise.all([
            request(SCOPE_ENDPOINT),
            request(USERS_ENDPOINT),
        ]);

        state.projects = Array.isArray(scopePayload?.projects) ? scopePayload.projects : [];
        state.disciplines = Array.isArray(scopePayload?.disciplines) ? scopePayload.disciplines : [];
        state.users = Array.isArray(usersPayload)
            ? usersPayload.filter((u) => String(u.role || '').toLowerCase() !== 'admin')
            : [];

        setSelectOptions('reportProjectCode', state.projects, 'Ù‡Ù…Ù‡ Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§');
        setSelectOptions('reportDisciplineCode', state.disciplines, 'Ù‡Ù…Ù‡ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†â€ŒÙ‡Ø§');
        setUserOptions('reportUserSelect', state.users);

        const projectSelect = document.getElementById('reportProjectCode');
        const disciplineSelect = document.getElementById('reportDisciplineCode');
        if (projectSelect && !norm(projectSelect.value) && state.projects.length) {
            projectSelect.value = norm(state.projects[0].code).toUpperCase();
        } else if (disciplineSelect && !norm(disciplineSelect.value) && state.disciplines.length) {
            disciplineSelect.value = norm(state.disciplines[0].code).toUpperCase();
        }

        syncAccessPageSizeFromDom();
        syncAuditPageSizeFromDom();
        state.initialized = true;
    }

    function bindSettingsReportsActions() {
        if (state.bound) return;
        state.bound = true;

        const root = document.getElementById('settingsReportsTabRoot');
        if (!root) return;

        const jsonModal = document.getElementById('settingsJsonModal');
        const jsonModalContent = jsonModal ? jsonModal.querySelector('.settings-json-modal-content') : null;

        if (jsonModal && !jsonModal.__settingsReportsBound) {
            jsonModal.addEventListener('click', (event) => {
                if (event.target === jsonModal) closeJsonModal();
            });
            if (jsonModalContent) {
                jsonModalContent.addEventListener('click', (event) => event.stopPropagation());
            }
            jsonModal.__settingsReportsBound = true;
        }

        root.addEventListener('click', (event) => {
            const actionEl = event && event.target && event.target.closest
                ? event.target.closest('[data-settings-reports-action]')
                : null;
            if (!actionEl || !root.contains(actionEl)) return;

            const action = norm(actionEl.dataset.settingsReportsAction);
            if (!action) return;

            switch (action) {
                case 'init-settings-reports':
                    window.initSettingsReports(String(actionEl.dataset.force || '').toLowerCase() === 'true');
                    break;
                case 'load-settings-access-report':
                    window.loadSettingsAccessReport();
                    break;
                case 'download-settings-access-report-csv':
                    window.downloadSettingsAccessReportCsv();
                    break;
                case 'load-settings-user-access':
                    window.loadSettingsUserAccess();
                    break;
                case 'load-settings-audit-logs':
                    window.loadSettingsAuditLogs();
                    break;
                case 'close-settings-json-modal':
                    closeJsonModal();
                    break;
                case 'copy-settings-json-modal':
                    window.copySettingsJsonModal();
                    break;
                case 'gotoSettingsAccessPage':
                    window.gotoSettingsAccessPage(toInt(actionEl.dataset.page, 1));
                    break;
                case 'gotoSettingsAuditPage':
                    window.gotoSettingsAuditPage(toInt(actionEl.dataset.page, 1));
                    break;
                case 'open-settings-audit-json-modal':
                    window.openSettingsAuditJsonModal(
                        toNonNegativeInt(actionEl.dataset.index, -1),
                        actionEl.dataset.field || 'before',
                    );
                    break;
                default:
                    break;
            }
        });

        root.addEventListener('change', (event) => {
            const actionEl = event && event.target && event.target.closest
                ? event.target.closest('[data-settings-reports-action]')
                : null;
            if (!actionEl || !root.contains(actionEl)) return;

            const action = norm(actionEl.dataset.settingsReportsAction);
            if (!action) return;

            if (action === 'set-settings-access-page-size') {
                window.setSettingsAccessPageSize(actionEl.value);
            } else if (action === 'set-settings-audit-page-size') {
                window.setSettingsAuditPageSize(actionEl.value);
            }
        });
    }

    window.gotoSettingsAccessPage = function gotoSettingsAccessPage(page) {
        state.accessReport.page = toInt(page, 1);
        renderAccessReportRows();
    };

    window.setSettingsAccessPageSize = function setSettingsAccessPageSize(pageSize) {
        state.accessReport.pageSize = toInt(pageSize, 20);
        state.accessReport.page = 1;
        const select = document.getElementById('settingsAccessPageSize');
        if (select) select.value = String(state.accessReport.pageSize);
        renderAccessReportRows();
    };

    window.gotoSettingsAuditPage = function gotoSettingsAuditPage(page) {
        state.auditLogs.page = toInt(page, 1);
        window.loadSettingsAuditLogs({ page: state.auditLogs.page });
    };

    window.setSettingsAuditPageSize = function setSettingsAuditPageSize(pageSize) {
        state.auditLogs.pageSize = toInt(pageSize, 20);
        state.auditLogs.page = 1;
        const select = document.getElementById('settingsAuditPageSize');
        if (select) select.value = String(state.auditLogs.pageSize);
        window.loadSettingsAuditLogs({ page: 1, pageSize: state.auditLogs.pageSize });
    };

    window.closeSettingsJsonModal = function closeSettingsJsonModal(event) {
        if (event && event.target && event.target.id !== 'settingsJsonModal') {
            return;
        }
        closeJsonModal();
    };

    window.openSettingsAuditJsonModal = function openSettingsAuditJsonModal(index, field) {
        const rowIndex = toNonNegativeInt(index, -1);
        if (rowIndex < 0 || rowIndex >= state.auditLogs.items.length) {
            notify('error', 'Ø±Ú©ÙˆØ±Ø¯ Ù„Ø§Ú¯ ÛŒØ§ÙØª Ù†Ø´Ø¯.');
            return;
        }
        const row = state.auditLogs.items[rowIndex];
        const normalizedField = String(field || '').toLowerCase() === 'after' ? 'after' : 'before';
        const rawText = normalizedField === 'after' ? row.after_json : row.before_json;
        if (!norm(rawText)) {
            notify('error', 'Ø¨Ø±Ø§ÛŒ Ø§ÛŒÙ† Ø¨Ø®Ø´ØŒ Ø¯Ø§Ø¯Ù‡ JSON Ø«Ø¨Øª Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª.');
            return;
        }

        const title = normalizedField === 'after' ? 'After JSON' : 'Before JSON';
        const meta = `action=${row.action || '-'} | target=${row.target_type || '-'}:${row.target_key || '-'} | actor=${row.actor_email || '-'} | time=${row.created_at || '-'}`;
        openJsonModal(title, rawText, meta);
    };

    window.copySettingsJsonModal = async function copySettingsJsonModal() {
        const contentEl = document.getElementById('settingsJsonModalContent');
        const text = contentEl ? contentEl.textContent || '' : '';
        if (!norm(text)) {
            notify('error', 'JSON Ø®Ø§Ù„ÛŒ Ø§Ø³Øª.');
            return;
        }

        try {
            if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                await navigator.clipboard.writeText(text);
            } else {
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                document.execCommand('copy');
                textarea.remove();
            }
            notify('success', 'JSON Ú©Ù¾ÛŒ Ø´Ø¯.');
        } catch (_) {
            notify('error', 'Ú©Ù¾ÛŒ JSON Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯.');
        }
    };

    window.loadSettingsAccessReport = async function loadSettingsAccessReport() {
        try {
            await loadMetadata(false);
            const filters = selectedFilters();
            if (!filters.projectCode && !filters.disciplineCode) {
                notify('error', 'Ø­Ø¯Ø§Ù‚Ù„ ÛŒÚ©ÛŒ Ø§Ø² ÙÛŒÙ„ØªØ±Ù‡Ø§ÛŒ Ù¾Ø±ÙˆÚ˜Ù‡ ÛŒØ§ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ† Ø±Ø§ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯.');
                return;
            }

            const qs = queryString({
                project_code: filters.projectCode,
                discipline_code: filters.disciplineCode,
                include_inactive: filters.includeInactive,
                include_denied: filters.includeDenied,
            });
            const payload = await request(`${ACCESS_REPORT_ENDPOINT}?${qs}`);
            state.accessReport.items = Array.isArray(payload.items) ? payload.items : [];
            state.accessReport.page = 1;
            renderAccessReportRows();
        } catch (error) {
            notify('error', error.message || 'Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª Ú¯Ø²Ø§Ø±Ø´ Ø¯Ø³ØªØ±Ø³ÛŒ');
        }
    };

    window.downloadSettingsAccessReportCsv = async function downloadSettingsAccessReportCsv() {
        try {
            await loadMetadata(false);
            const filters = selectedFilters();
            if (!filters.projectCode && !filters.disciplineCode) {
                notify('error', 'Ø¨Ø±Ø§ÛŒ Ø¯Ø§Ù†Ù„ÙˆØ¯ CSV Ø­Ø¯Ø§Ù‚Ù„ ÛŒÚ© ÙÛŒÙ„ØªØ± Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯.');
                return;
            }

            const qs = queryString({
                project_code: filters.projectCode,
                discipline_code: filters.disciplineCode,
                include_inactive: filters.includeInactive,
                include_denied: filters.includeDenied,
            });
            const url = `${ACCESS_REPORT_CSV_ENDPOINT}?${qs}`;
            const fn = typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : fetch;
            const res = await fn(url);
            if (!res.ok) {
                let message = `Request failed (${res.status})`;
                try {
                    const body = await res.clone().json();
                    message = body.detail || body.message || message;
                } catch (_) {}
                throw new Error(message);
            }

            const blob = await res.blob();
            const disposition = norm(res.headers.get('content-disposition'));
            const match = disposition.match(/filename="?([^"]+)"?/i);
            const filename = match?.[1] || 'permissions_access_report.csv';
            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = objectUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(objectUrl);
            notify('success', 'Ø®Ø±ÙˆØ¬ÛŒ CSV Ø¯Ø§Ù†Ù„ÙˆØ¯ Ø´Ø¯.');
        } catch (error) {
            notify('error', error.message || 'Ø¯Ø§Ù†Ù„ÙˆØ¯ CSV Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
        }
    };

    window.loadSettingsUserAccess = async function loadSettingsUserAccess(silentIfEmpty = false) {
        try {
            await loadMetadata(false);
            const userId = norm(document.getElementById('reportUserSelect')?.value);
            if (!userId) {
                const summary = document.getElementById('settingsUserAccessSummary');
                if (summary) {
                    summary.textContent = 'Ú©Ø§Ø±Ø¨Ø± ØºÛŒØ±Ø§Ø¯Ù…ÛŒÙ† Ø¨Ø±Ø§ÛŒ Ù†Ù…Ø§ÛŒØ´ ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ø¯.';
                }
                if (!silentIfEmpty) {
                    notify('error', 'Ú©Ø§Ø±Ø¨Ø±ÛŒ Ø¨Ø±Ø§ÛŒ Ù†Ù…Ø§ÛŒØ´ Ø§Ù†ØªØ®Ø§Ø¨ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª.');
                }
                return;
            }
            const payload = await request(`${API_BASE}/permissions/user-access/${encodeURIComponent(userId)}`);
            renderUserAccess(payload);
        } catch (error) {
            notify('error', error.message || 'Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª Ø¯Ø³ØªØ±Ø³ÛŒ Ú©Ø§Ø±Ø¨Ø±');
        }
    };

    window.loadSettingsAuditLogs = async function loadSettingsAuditLogs(options = {}) {
        try {
            syncAuditPageSizeFromDom();

            const action = norm(document.getElementById('settingsAuditAction')?.value);
            const targetType = norm(document.getElementById('settingsAuditTargetType')?.value);
            const targetKey = norm(document.getElementById('settingsAuditTargetKey')?.value);
            const page = toInt(options.page, state.auditLogs.page);
            const pageSize = toInt(options.pageSize, state.auditLogs.pageSize);
            const offset = options.offset === undefined ? null : toNonNegativeInt(options.offset, 0);

            state.auditLogs.page = page;
            state.auditLogs.pageSize = pageSize;
            const select = document.getElementById('settingsAuditPageSize');
            if (select) select.value = String(pageSize);

            const qs = queryString({
                action,
                target_type: targetType,
                target_key: targetKey,
                page,
                page_size: pageSize,
                offset,
            });
            const payload = await request(`${AUDIT_ENDPOINT}?${qs}`);
            const pagination = payload?.pagination || {};

            state.auditLogs.items = Array.isArray(payload.items) ? payload.items : [];
            state.auditLogs.page = toInt(pagination.page, page);
            state.auditLogs.pageSize = toInt(pagination.page_size, pageSize);
            state.auditLogs.offset = toNonNegativeInt(
                pagination.offset,
                (state.auditLogs.page - 1) * state.auditLogs.pageSize,
            );
            state.auditLogs.total = toNonNegativeInt(pagination.total, state.auditLogs.items.length);
            state.auditLogs.totalPages = Math.max(
                1,
                toInt(
                    pagination.total_pages,
                    Math.ceil(Math.max(1, state.auditLogs.total) / state.auditLogs.pageSize),
                ),
            );
            renderAuditRows();
        } catch (error) {
            notify('error', error.message || 'Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ù„Ø§Ú¯â€ŒÙ‡Ø§');
        }
    };

    window.initSettingsReports = async function initSettingsReports(force = false) {
        try {
            bindSettingsReportsActions();
            await loadMetadata(force);
            renderAccessReportRows();
            renderAuditRows();

            await window.loadSettingsAuditLogs();
            await window.loadSettingsUserAccess(true);

            const filters = selectedFilters();
            if (filters.projectCode || filters.disciplineCode) {
                await window.loadSettingsAccessReport();
            }
        } catch (error) {
            notify('error', error.message || 'Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ ØªØ¨ Ú¯Ø²Ø§Ø±Ø´â€ŒÙ‡Ø§ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
        }
    };

    if (!window.__settingsJsonModalEscBound) {
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') closeJsonModal();
        });
        window.__settingsJsonModalEscBound = true;
    }
})();
