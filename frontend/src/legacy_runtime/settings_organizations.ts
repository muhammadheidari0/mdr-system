// @ts-nocheck
(() => {
    const API_BASE = '/api/v1/settings/organizations';
    const BLOCKS_API = '/api/v1/settings/blocks';
    const TABLE_COLSPAN = 10;
    const SEARCH_DEBOUNCE_MS = 180;
    const DEFAULT_PAGE_SIZE = 20;

    const state = {
        initialized: false,
        loading: false,
        bound: false,
        bulkRegistered: false,
        blocksLoaded: false,
        blocksLoadingPromise: null,
        items: [],
        blockItems: [],
        filtered: [],
        page: 1,
        pageSize: DEFAULT_PAGE_SIZE,
        search: '',
        orgType: '',
        status: '',
        searchTimer: null,
    };

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function norm(value) {
        return String(value == null ? '' : value).trim();
    }

    function normUpper(value) {
        return norm(value).toUpperCase();
    }

    function normId(value) {
        const n = Number(value || 0);
        if (!Number.isFinite(n) || n <= 0) return '';
        return String(Math.trunc(n));
    }

    function typeLabel(value) {
        const map = {
            system: 'Ø³ÛŒØ³ØªÙ…',
            employer: 'Ú©Ø§Ø±ÙØ±Ù…Ø§',
            consultant: 'Ù…Ø´Ø§ÙˆØ±',
            contractor: 'Ù¾ÛŒÙ…Ø§Ù†Ú©Ø§Ø±',
            dcc: 'DCC',
        };
        const key = norm(value).toLowerCase();
        return map[key] || value || '-';
    }

    function notify(type, message) {
        if (window.UI && typeof window.UI[type] === 'function') {
            window.UI[type](message);
            return;
        }
        if (typeof showToast === 'function') {
            showToast(message, type === 'error' ? 'error' : type === 'warning' ? 'warning' : 'success');
            return;
        }
        alert(message);
    }

    function bulkBridge() {
        if (!window.TableBulk || typeof window.TableBulk !== 'object') return null;
        if (typeof window.TableBulk.register !== 'function') return null;
        return window.TableBulk;
    }

    function parseSelectedOrgIds(selectedKeys = []) {
        return (selectedKeys || [])
            .map((key) => Number(key))
            .filter((id) => Number.isFinite(id) && id > 0)
            .map((id) => Math.trunc(id));
    }

    function summarizeErrors(items) {
        if (!items || !items.length) return '';
        const head = items.slice(0, 3).join(' | ');
        return items.length > 3 ? `${head} | +${items.length - 3} more` : head;
    }

    async function runOrganizationsBulk(actionId, selectedKeys) {
        const ids = parseSelectedOrgIds(selectedKeys);
        if (!ids.length) {
            notify('warning', 'No organization selected.');
            return;
        }

        const rows = ids
            .map((id) => getOrganizationById(id))
            .filter(Boolean);
        if (!rows.length) {
            notify('warning', 'Selected organizations are no longer available.');
            return;
        }

        const protectedRows = rows.filter((item) => isProtectedOrganization(item));
        const allowedRows = rows.filter((item) => !isProtectedOrganization(item));
        if (!allowedRows.length) {
            notify('warning', 'SYSTEM_ROOT cannot be modified.');
            return;
        }

        let task = null;
        let confirmMessage = '';
        let operation = '';
        let targetRows = allowedRows;

        if (actionId === 'org-bulk-deactivate') {
            operation = 'deactivated';
            targetRows = allowedRows.filter((item) => Boolean(item.is_active));
            confirmMessage = `Deactivate ${targetRows.length} selected organization(s)?`;
            task = (row) => request(`${API_BASE}/delete`, {
                method: 'POST',
                body: JSON.stringify({ id: Number(row.id), hard_delete: false }),
            });
        } else if (actionId === 'org-bulk-restore') {
            operation = 'restored';
            targetRows = allowedRows.filter((item) => !Boolean(item.is_active));
            confirmMessage = `Restore ${targetRows.length} selected organization(s)?`;
            task = (row) => request(`${API_BASE}/upsert`, {
                method: 'POST',
                body: JSON.stringify({
                    id: Number(row.id),
                    code: normUpper(row.code),
                    name: row.name,
                    org_type: norm(row.org_type).toLowerCase(),
                    parent_id: row.parent_id == null ? null : Number(row.parent_id),
                    is_active: true,
                    contracts: cloneContractsForRequest(row.contracts),
                }),
            });
        } else if (actionId === 'org-bulk-hard-delete') {
            operation = 'deleted';
            targetRows = allowedRows;
            confirmMessage = `Hard-delete ${targetRows.length} selected organization(s)? This cannot be undone.`;
            task = (row) => request(`${API_BASE}/delete`, {
                method: 'POST',
                body: JSON.stringify({ id: Number(row.id), hard_delete: true }),
            });
        }

        if (!task) {
            notify('warning', 'Unknown bulk action.');
            return;
        }
        if (!targetRows.length) {
            notify('warning', 'No eligible rows for this operation.');
            return;
        }
        if (!window.confirm(confirmMessage)) return;

        const failures = [];
        let success = 0;
        for (const row of targetRows) {
            try {
                await task(row);
                success += 1;
            } catch (error) {
                failures.push(`${row.code || row.id}: ${error && error.message ? error.message : 'Request failed'}`);
            }
        }

        if (success > 0) {
            notify('success', `${success} organization(s) ${operation}.`);
        }
        if (protectedRows.length > 0) {
            notify('warning', `${protectedRows.length} protected organization(s) skipped.`);
        }
        if (failures.length > 0) {
            notify('warning', `${failures.length} operation(s) failed. ${summarizeErrors(failures)}`);
        }

        const bulk = bulkBridge();
        if (bulk && typeof bulk.clearSelection === 'function') {
            bulk.clearSelection('organizationsTable');
        }
        await loadOrganizations(true);
    }

    function registerOrganizationsBulkActions() {
        if (state.bulkRegistered) return;
        const bulk = bulkBridge();
        if (!bulk) return;

        bulk.register({
            tableId: 'organizationsTable',
            actions: [
                { id: 'org-bulk-deactivate', label: 'Deactivate selected organizations' },
                { id: 'org-bulk-restore', label: 'Restore selected organizations' },
                { id: 'org-bulk-hard-delete', label: 'Hard-delete selected organizations' },
            ],
            getRowKey(row) {
                return row && row.dataset ? row.dataset.bulkKey : '';
            },
            onAction({ actionId, selectedKeys }) {
                return runOrganizationsBulk(actionId, selectedKeys);
            },
        });
        state.bulkRegistered = true;
    }

    async function request(url, options = {}) {
        const requester = typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : fetch;
        const hasBody = Object.prototype.hasOwnProperty.call(options || {}, 'body');
        const headers = { ...(options.headers || {}) };
        if (hasBody && !(options.body instanceof FormData) && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }
        const response = await requester(url, { ...options, headers });
        if (!response.ok) {
            let message = `Request failed (${response.status})`;
            try {
                const payload = await response.clone().json();
                message = payload.detail || payload.message || message;
            } catch (_) {
                try {
                    const text = await response.text();
                    if (text) message = text;
                } catch (_) {}
            }
            throw new Error(message);
        }
        return response.json();
    }

    function getOrganizationById(id) {
        const key = normId(id);
        if (!key) return null;
        return state.items.find((item) => normId(item && item.id) === key) || null;
    }

    function isProtectedOrganization(item) {
        return normUpper(item && item.code) === 'SYSTEM_ROOT';
    }

    function cloneContractsForRequest(contracts = []) {
        return (Array.isArray(contracts) ? contracts : []).map((item) => {
            const id = normId(item && item.id);
            const blockId = normId(item && item.block_id);
            return {
                id: id ? Number(id) : null,
                contract_number: norm(item && item.contract_number),
                subject: norm(item && item.subject),
                block_id: blockId ? Number(blockId) : null,
            };
        });
    }

    function blockLabel(item) {
        if (!item) return '';
        const primary = [norm(item.project_code), norm(item.code)].filter(Boolean).join(' / ');
        const title = norm(item.name_p || item.name_e);
        if (!primary) return title;
        return title ? `${primary} - ${title}` : primary;
    }

    async function ensureBlocksLoaded(force = false) {
        if (state.blocksLoaded && !force) return;
        if (state.blocksLoadingPromise && !force) {
            await state.blocksLoadingPromise;
            return;
        }

        state.blocksLoadingPromise = (async () => {
            const payload = await request(BLOCKS_API);
            const items = Array.isArray(payload && payload.items) ? payload.items : [];
            state.blockItems = items
                .map((item) => ({
                    id: Number(item && item.id ? item.id : 0),
                    project_code: norm(item && item.project_code),
                    code: norm(item && item.code),
                    name_e: norm(item && item.name_e),
                    name_p: norm(item && item.name_p),
                    is_active: Boolean(item && item.is_active),
                }))
                .filter((item) => item.id > 0)
                .sort((left, right) => {
                    const leftKey = `${norm(left.project_code).toLowerCase()}|${norm(left.code).toLowerCase()}`;
                    const rightKey = `${norm(right.project_code).toLowerCase()}|${norm(right.code).toLowerCase()}`;
                    return leftKey.localeCompare(rightKey);
                });
            state.blocksLoaded = true;
        })();

        try {
            await state.blocksLoadingPromise;
        } finally {
            state.blocksLoadingPromise = null;
        }
    }

    function contractRowHtml(contract = {}) {
        const contractId = normId(contract && contract.id);
        const selectedBlockId = normId(contract && contract.block_id);
        const selectedBlock = state.blockItems.find((item) => normId(item && item.id) === selectedBlockId) || null;
        const fallbackBlockLabel = norm(contract && (contract.block_label || contract.block_code));
        const blockOptions = state.blockItems.map((item) => {
            const itemId = normId(item.id);
            const label = blockLabel(item);
            return `<option value="${esc(itemId)}" ${itemId === selectedBlockId ? 'selected' : ''}>${esc(label)}</option>`;
        }).join('');
        const fallbackOption = selectedBlockId && !selectedBlock
            ? `<option value="${esc(selectedBlockId)}" selected>${esc(fallbackBlockLabel || `Block ${selectedBlockId}`)}</option>`
            : '';

        return `
            <div class="organization-contract-card" data-org-contract-row>
                <input type="hidden" data-contract-field="id" value="${esc(contractId)}">
                <div class="organization-contract-grid">
                    <div class="form-group">
                        <label class="form-label-sm">شماره قرارداد</label>
                        <input type="text" class="form-input" data-contract-field="contract_number" value="${esc(contract && contract.contract_number)}" placeholder="مثال: CNT-1403-01">
                    </div>
                    <div class="form-group">
                        <label class="form-label-sm">موضوع قرارداد</label>
                        <input type="text" class="form-input" data-contract-field="subject" value="${esc(contract && contract.subject)}" placeholder="موضوع قرارداد">
                    </div>
                    <div class="form-group">
                        <label class="form-label-sm">بلوک</label>
                        <select class="form-input" data-contract-field="block_id">
                            <option value="">- بدون بلوک -</option>
                            ${fallbackOption}
                            ${blockOptions}
                        </select>
                    </div>
                </div>
                <div class="organization-contract-actions">
                    <button type="button" class="btn-archive-icon" data-org-action="remove-contract-row">
                        <span class="material-icons-round">delete</span>
                        حذف قرارداد
                    </button>
                </div>
            </div>
        `;
    }

    function renderContractRows(contracts = []) {
        const list = document.getElementById('organizationContractsList');
        if (!list) return;
        const rows = Array.isArray(contracts) && contracts.length ? contracts : [{}];
        list.innerHTML = rows.map((item) => contractRowHtml(item)).join('');
    }

    function addContractRow(contract = {}) {
        const list = document.getElementById('organizationContractsList');
        if (!list) return;
        if (list.querySelector('.organization-contract-empty')) {
            list.innerHTML = '';
        }
        list.insertAdjacentHTML('beforeend', contractRowHtml(contract));
    }

    function removeContractRow(buttonEl) {
        const row = buttonEl && buttonEl.closest ? buttonEl.closest('[data-org-contract-row]') : null;
        if (row && row.parentNode) {
            row.parentNode.removeChild(row);
        }
        const list = document.getElementById('organizationContractsList');
        if (list && !list.querySelector('[data-org-contract-row]')) {
            renderContractRows([]);
        }
    }

    function collectOrganizationContracts() {
        const rows = Array.from(document.querySelectorAll('#organizationContractsList [data-org-contract-row]'));
        return rows.map((row) => {
            const id = normId(row.querySelector('[data-contract-field="id"]')?.value || '');
            const contractNumber = norm(row.querySelector('[data-contract-field="contract_number"]')?.value || '');
            const subject = norm(row.querySelector('[data-contract-field="subject"]')?.value || '');
            const blockId = normId(row.querySelector('[data-contract-field="block_id"]')?.value || '');

            if (!contractNumber && !subject && !blockId) return null;
            if (!contractNumber) {
                throw new Error('Contract number is required for each contract row.');
            }
            if (!subject) {
                throw new Error('Contract subject is required for each contract row.');
            }

            return {
                id: id ? Number(id) : null,
                contract_number: contractNumber,
                subject,
                block_id: blockId ? Number(blockId) : null,
            };
        }).filter(Boolean);
    }

    function closeAllOrganizationActionMenus() {
        const root = document.getElementById('settingsOrganizationsTabRoot');
        if (!root || !root.querySelectorAll) return;
        root.querySelectorAll('.users-kebab-menu.show').forEach((menu) => menu.classList.remove('show'));
        root.querySelectorAll('.users-kebab-btn[aria-expanded="true"]').forEach((btn) => btn.setAttribute('aria-expanded', 'false'));
    }

    function toggleOrganizationActionMenu(event, organizationId) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }

        const id = normId(organizationId);
        if (!id) return;
        const menu = document.getElementById(`organizationsActionMenu-${id}`);
        if (!menu) return;

        const shouldOpen = !menu.classList.contains('show');
        closeAllOrganizationActionMenus();
        if (!shouldOpen) return;

        menu.classList.add('show');
        if (event && event.currentTarget) {
            event.currentTarget.setAttribute('aria-expanded', 'true');
        }
    }

    function renderParentOptions(selectedId = '', excludeId = '') {
        const parentSelect = document.getElementById('organizationParentId');
        if (!parentSelect) return;

        const selected = normId(selectedId);
        const excludedRoot = normId(excludeId);
        const excluded = new Set();
        if (excludedRoot) {
            excluded.add(excludedRoot);
            let changed = true;
            while (changed) {
                changed = false;
                for (const item of state.items) {
                    const itemId = normId(item && item.id);
                    const parentId = normId(item && item.parent_id);
                    if (!itemId || !parentId) continue;
                    if (excluded.has(parentId) && !excluded.has(itemId)) {
                        excluded.add(itemId);
                        changed = true;
                    }
                }
            }
        }

        const options = state.items
            .filter((item) => {
                const itemId = normId(item && item.id);
                return itemId && !excluded.has(itemId);
            })
            .map((item) => {
                const itemId = normId(item.id);
                const depth = Math.max(0, Number(item.depth || 0));
                const indent = depth > 0 ? `${'â€” '.repeat(depth)}` : '';
                const label = `${indent}${norm(item.name) || norm(item.code)}`;
                const selectedAttr = itemId === selected ? 'selected' : '';
                return `<option value="${esc(itemId)}" ${selectedAttr}>${esc(label)}</option>`;
            })
            .join('');

        parentSelect.innerHTML = `
            <option value="">- Ø¨Ø¯ÙˆÙ† ÙˆØ§Ù„Ø¯ -</option>
            ${options}
        `;
    }

    function filterItems() {
        const q = norm(state.search).toLowerCase();
        const orgType = norm(state.orgType).toLowerCase();
        const status = norm(state.status).toLowerCase();

        state.filtered = state.items.filter((item) => {
            const itemType = norm(item && item.org_type).toLowerCase();
            const active = Boolean(item && item.is_active);
            const contractText = Array.isArray(item && item.contracts)
                ? item.contracts.map((contract) => [contract && contract.contract_number, contract && contract.subject].join(' ')).join(' ')
                : '';
            const haystack = [
                item && item.code,
                item && item.name,
                item && item.parent_code,
                item && item.parent_name,
                itemType,
                contractText,
            ].join(' ').toLowerCase();

            if (q && !haystack.includes(q)) return false;
            if (orgType && itemType !== orgType) return false;
            if (status === 'active' && !active) return false;
            if (status === 'inactive' && active) return false;
            return true;
        });
    }

    function getPagination() {
        filterItems();
        const total = state.filtered.length;
        const pageSize = Math.max(1, Number(state.pageSize) || DEFAULT_PAGE_SIZE);
        const totalPages = Math.max(1, Math.ceil(total / pageSize));
        const page = Math.min(Math.max(1, Number(state.page) || 1), totalPages);
        state.page = page;
        state.pageSize = pageSize;

        const startIndex = total === 0 ? 0 : (page - 1) * pageSize;
        const endIndex = Math.min(total, startIndex + pageSize);
        const rows = state.filtered.slice(startIndex, endIndex);

        return {
            total,
            pageSize,
            totalPages,
            page,
            startIndex,
            endIndex,
            from: total === 0 ? 0 : startIndex + 1,
            to: endIndex,
            rows,
        };
    }

    function statusBadge(active) {
        return active
            ? '<span class="status-badge active">ÙØ¹Ø§Ù„</span>'
            : '<span class="status-badge inactive">ØºÛŒØ±ÙØ¹Ø§Ù„</span>';
    }

    function buildOrganizationContractsSummary(item) {
        const contracts = Array.isArray(item && item.contracts) ? item.contracts.filter(Boolean) : [];
        const organizationId = Number(item && item.id ? item.id : 0);
        if (!contracts.length) {
            return `
                <button type="button" class="org-contract-trigger is-empty" data-org-action="open-organization-contracts" data-org-id="${organizationId}">
                    <div class="org-contract-cell is-empty">بدون قرارداد</div>
                </button>
            `;
        }

        const previewRows = contracts.slice(0, 2).map((contract) => {
            const parts = [norm(contract && contract.contract_number), norm(contract && contract.subject)].filter(Boolean);
            const blockText = norm(contract && (contract.block_label || contract.block_code));
            const title = parts.join(' - ') || 'قرارداد';
            return `
                <div class="org-contract-preview-row">
                    <span class="org-contract-preview-title">${esc(title)}</span>
                    ${blockText ? `<span class="org-contract-preview-meta">${esc(blockText)}</span>` : ''}
                </div>
            `;
        }).join('');

        const moreCount = Math.max(0, contracts.length - 2);
        const moreText = moreCount > 0
            ? `<span class="org-contract-preview-more">+${moreCount} قرارداد دیگر</span>`
            : '';

        return `
            <button type="button" class="org-contract-trigger" data-org-action="open-organization-contracts" data-org-id="${organizationId}">
                <div class="org-contract-cell">
                    <span class="org-contract-count">${contracts.length} قرارداد</span>
                    <div class="org-contract-preview-list">
                        ${previewRows}
                    </div>
                    ${moreText}
                </div>
            </button>
        `;
    }

    function renderOrganizationsTable() {
        const body = document.getElementById('organizationsTableBody');
        const meta = document.getElementById('organizationsTableMeta');
        const prevBtn = document.getElementById('organizationsPrevPageBtn');
        const nextBtn = document.getElementById('organizationsNextPageBtn');
        const pageButtons = document.getElementById('organizationsPageButtons');
        if (!body) return;
        closeAllOrganizationActionMenus();

        const info = getPagination();

        if (!info.rows.length) {
            body.innerHTML = `<tr><td colspan="${TABLE_COLSPAN}" class="center-text muted" style="padding: 26px;">Ù…ÙˆØ±Ø¯ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯</td></tr>`;
        } else {
            body.innerHTML = info.rows.map((item) => {
                const id = Number(item.id || 0);
                const depth = Math.max(0, Number(item.depth || 0));
                const padding = depth * 18;
                const protectedOrg = isProtectedOrganization(item);
                const toggleLabel = item.is_active ? 'ØºÛŒØ±ÙØ¹Ø§Ù„' : 'ÙØ¹Ø§Ù„â€ŒØ³Ø§Ø²ÛŒ';
                const toggleAction = item.is_active ? 'deactivate-organization' : 'restore-organization';
                const toggleDisabled = protectedOrg ? 'disabled' : '';
                const deleteDisabled = protectedOrg ? 'disabled' : '';
                const actionMenuId = `organizationsActionMenu-${id}`;

                return `
                    <tr data-bulk-key="${id}" data-org-id="${id}">
                        <td>${id}</td>
                        <td><code>${esc(item.code || '-')}</code></td>
                        <td>
                            <div class="org-row-name" style="padding-right:${padding}px;">
                                <span>${esc(item.name || '-')}</span>
                            </div>
                        </td>
                        <td>${buildOrganizationContractsSummary(item)}</td>
                        <td>${esc(typeLabel(item.org_type))}</td>
                        <td>${esc(item.parent_name || item.parent_code || '-')}</td>
                        <td>${Number(item.users_count || 0)}</td>
                        <td>${Number(item.children_count || 0)}</td>
                        <td>${statusBadge(Boolean(item.is_active))}</td>
                        <td>
                            <div class="users-kebab">
                                <button
                                    type="button"
                                    class="users-kebab-btn"
                                    data-org-action="toggle-organization-action-menu"
                                    data-org-id="${id}"
                                    aria-label="عملیات"
                                    aria-haspopup="true"
                                    aria-expanded="false"
                                    aria-controls="${actionMenuId}"
                                >
                                    <span class="material-icons-round">more_vert</span>
                                </button>
                                <div class="users-kebab-menu" id="${actionMenuId}" role="menu">
                                    <button type="button" class="users-kebab-item" data-org-action="open-edit-organization-modal" data-org-id="${id}">
                                        <span class="material-icons-round">edit</span>
                                        ویرایش
                                    </button>
                                    <button type="button" class="users-kebab-item" data-org-action="${toggleAction}" data-org-id="${id}" ${toggleDisabled}>
                                        <span class="material-icons-round">${item.is_active ? 'block' : 'check_circle'}</span>
                                        ${toggleLabel}
                                    </button>
                                    <button type="button" class="users-kebab-item danger" data-org-action="hard-delete-organization" data-org-id="${id}" ${deleteDisabled}>
                                        <span class="material-icons-round">delete</span>
                                        حذف دائم
                                    </button>
                                </div>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        if (meta) {
            meta.textContent = `Ù†Ù…Ø§ÛŒØ´ ${info.from}-${info.to} Ø§Ø² ${info.total} Ø³Ø§Ø²Ù…Ø§Ù†`;
        }
        if (prevBtn) prevBtn.disabled = info.page <= 1;
        if (nextBtn) nextBtn.disabled = info.page >= info.totalPages;

        if (pageButtons) {
            const pages = [];
            const maxButtons = 7;
            let start = Math.max(1, info.page - 3);
            let end = Math.min(info.totalPages, start + maxButtons - 1);
            start = Math.max(1, end - maxButtons + 1);

            for (let p = start; p <= end; p += 1) {
                const activeClass = p === info.page ? ' active' : '';
                pages.push(
                    `<button type="button" class="users-page-btn${activeClass}" data-org-action="goto-organizations-page" data-page="${p}">${p}</button>`
                );
            }
            pageButtons.innerHTML = pages.join('');
        }
    }

    function setLoadingRow(message = 'Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ...') {
        const body = document.getElementById('organizationsTableBody');
        if (!body) return;
        closeAllOrganizationActionMenus();
        body.innerHTML = `<tr><td colspan="${TABLE_COLSPAN}" class="center-text muted" style="padding: 26px;">${esc(message)}</td></tr>`;
    }

    async function loadOrganizations(force = false) {
        if (state.loading) return;
        if (state.initialized && !force) {
            renderOrganizationsTable();
            return;
        }
        state.loading = true;
        setLoadingRow('Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ø³Ø§Ø²Ù…Ø§Ù†â€ŒÙ‡Ø§...');
        try {
            const payload = await request(`${API_BASE}?include_inactive=true&tree=true`);
            state.items = Array.isArray(payload && payload.items) ? payload.items : [];
            state.initialized = true;
            renderParentOptions();
            renderOrganizationsTable();
        } catch (error) {
            setLoadingRow(`Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ: ${error.message}`);
            notify('error', error.message || 'Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ø³Ø§Ø²Ù…Ø§Ù†â€ŒÙ‡Ø§ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
        } finally {
            state.loading = false;
        }
    }

    function resetOrganizationForm() {
        const idInput = document.getElementById('organizationId');
        const codeInput = document.getElementById('organizationCode');
        const nameInput = document.getElementById('organizationName');
        const typeInput = document.getElementById('organizationType');
        const parentInput = document.getElementById('organizationParentId');
        const activeInput = document.getElementById('organizationIsActive');
        const titleEl = document.getElementById('organizationModalTitle');

        if (idInput) idInput.value = '';
        if (codeInput) codeInput.value = '';
        if (nameInput) nameInput.value = '';
        if (typeInput) typeInput.value = 'contractor';
        if (parentInput) parentInput.value = '';
        if (activeInput) activeInput.checked = true;
        if (titleEl) titleEl.textContent = 'Ø§ÛŒØ¬Ø§Ø¯ Ø³Ø§Ø²Ù…Ø§Ù† Ø¬Ø¯ÛŒØ¯';
        renderParentOptions('', '');
        renderContractRows([]);
    }

    function openOrganizationModal() {
        const modal = document.getElementById('organizationModal');
        if (modal) modal.style.display = 'flex';
    }

    function focusOrganizationContractsSection() {
        window.setTimeout(() => {
            const section = document.querySelector('#organizationForm .organization-contracts-section');
            const firstInput = document.querySelector('#organizationContractsList [data-contract-field="contract_number"]');
            if (section && typeof section.scrollIntoView === 'function') {
                section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            if (firstInput && typeof firstInput.focus === 'function') {
                firstInput.focus();
            }
        }, 60);
    }

    function closeOrganizationModal() {
        const modal = document.getElementById('organizationModal');
        if (modal) modal.style.display = 'none';
        closeAllOrganizationActionMenus();
    }

    function collectOrganizationPayload() {
        const id = normId(document.getElementById('organizationId')?.value || '');
        const code = normUpper(document.getElementById('organizationCode')?.value || '');
        const name = norm(document.getElementById('organizationName')?.value || '');
        const orgType = norm(document.getElementById('organizationType')?.value || '').toLowerCase();
        const parentId = normId(document.getElementById('organizationParentId')?.value || '');
        const isActive = Boolean(document.getElementById('organizationIsActive')?.checked);
        const contracts = collectOrganizationContracts();

        if (!code) throw new Error('Ú©Ø¯ Ø³Ø§Ø²Ù…Ø§Ù† Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª');
        if (!name) throw new Error('Ù†Ø§Ù… Ø³Ø§Ø²Ù…Ø§Ù† Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª');
        if (!orgType) throw new Error('Ù†ÙˆØ¹ Ø³Ø§Ø²Ù…Ø§Ù† Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª');

        return {
            id: id ? Number(id) : null,
            code,
            name,
            org_type: orgType,
            parent_id: parentId ? Number(parentId) : null,
            is_active: isActive,
            contracts,
        };
    }

    async function saveOrganization() {
        try {
            const payload = collectOrganizationPayload();
            await request(`${API_BASE}/upsert`, {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            notify('success', 'Ø³Ø§Ø²Ù…Ø§Ù† Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯');
            closeOrganizationModal();
            state.page = 1;
            await loadOrganizations(true);
        } catch (error) {
            notify('error', error.message || 'Ø°Ø®ÛŒØ±Ù‡ Ø³Ø§Ø²Ù…Ø§Ù† Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
        }
    }

    async function deactivateOrganization(id) {
        const row = getOrganizationById(id);
        if (!row) return;
        if (!confirm(`Ø³Ø§Ø²Ù…Ø§Ù† "${row.name || row.code}" ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´ÙˆØ¯ØŸ`)) return;
        try {
            await request(`${API_BASE}/delete`, {
                method: 'POST',
                body: JSON.stringify({ id: Number(row.id), hard_delete: false }),
            });
            notify('success', 'Ø³Ø§Ø²Ù…Ø§Ù† ØºÛŒØ±ÙØ¹Ø§Ù„ Ø´Ø¯');
            await loadOrganizations(true);
        } catch (error) {
            notify('error', error.message || 'ØºÛŒØ±ÙØ¹Ø§Ù„â€ŒØ³Ø§Ø²ÛŒ Ø³Ø§Ø²Ù…Ø§Ù† Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
        }
    }

    async function restoreOrganization(id) {
        const row = getOrganizationById(id);
        if (!row) return;
        try {
            await request(`${API_BASE}/upsert`, {
                method: 'POST',
                body: JSON.stringify({
                    id: Number(row.id),
                    code: normUpper(row.code),
                    name: row.name,
                    org_type: norm(row.org_type).toLowerCase(),
                    parent_id: row.parent_id == null ? null : Number(row.parent_id),
                    is_active: true,
                    contracts: cloneContractsForRequest(row.contracts),
                }),
            });
            notify('success', 'Ø³Ø§Ø²Ù…Ø§Ù† ÙØ¹Ø§Ù„ Ø´Ø¯');
            await loadOrganizations(true);
        } catch (error) {
            notify('error', error.message || 'ÙØ¹Ø§Ù„â€ŒØ³Ø§Ø²ÛŒ Ø³Ø§Ø²Ù…Ø§Ù† Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
        }
    }

    async function hardDeleteOrganization(id) {
        const row = getOrganizationById(id);
        if (!row) return;
        if (!confirm(`Ø­Ø°Ù Ø¯Ø§Ø¦Ù… Ø³Ø§Ø²Ù…Ø§Ù† "${row.name || row.code}" Ø§Ù†Ø¬Ø§Ù… Ø´ÙˆØ¯ØŸ Ø§ÛŒÙ† Ø¹Ù…Ù„ÛŒØ§Øª ØºÛŒØ±Ù‚Ø§Ø¨Ù„ Ø¨Ø§Ø²Ú¯Ø´Øª Ø§Ø³Øª.`)) return;
        try {
            await request(`${API_BASE}/delete`, {
                method: 'POST',
                body: JSON.stringify({ id: Number(row.id), hard_delete: true }),
            });
            notify('success', 'Ø³Ø§Ø²Ù…Ø§Ù† Ø­Ø°Ù Ø´Ø¯');
            await loadOrganizations(true);
        } catch (error) {
            notify('error', error.message || 'Ø­Ø°Ù Ø¯Ø§Ø¦Ù… Ø³Ø§Ø²Ù…Ø§Ù† Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
        }
    }

    async function openCreateOrganizationModal() {
        try {
            await ensureBlocksLoaded(false);
        } catch (error) {
            console.warn('Organization blocks unavailable in create modal:', error);
        }
        resetOrganizationForm();
        openOrganizationModal();
    }

    async function openEditOrganizationModal(id, options = {}) {
        const row = getOrganizationById(id);
        if (!row) {
            notify('error', 'Ø³Ø§Ø²Ù…Ø§Ù† Ø§Ù†ØªØ®Ø§Ø¨ Ø´Ø¯Ù‡ ÛŒØ§ÙØª Ù†Ø´Ø¯');
            return;
        }
        try {
            await ensureBlocksLoaded(false);
        } catch (error) {
            console.warn('Organization blocks unavailable in edit modal:', error);
        }
        const idInput = document.getElementById('organizationId');
        const codeInput = document.getElementById('organizationCode');
        const nameInput = document.getElementById('organizationName');
        const typeInput = document.getElementById('organizationType');
        const activeInput = document.getElementById('organizationIsActive');
        const titleEl = document.getElementById('organizationModalTitle');

        if (idInput) idInput.value = String(row.id || '');
        if (codeInput) codeInput.value = row.code || '';
        if (nameInput) nameInput.value = row.name || '';
        if (typeInput) typeInput.value = norm(row.org_type).toLowerCase() || 'contractor';
        if (activeInput) activeInput.checked = Boolean(row.is_active);
        if (titleEl) titleEl.textContent = `ÙˆÛŒØ±Ø§ÛŒØ´ Ø³Ø§Ø²Ù…Ø§Ù† ${row.code || ''}`;
        renderParentOptions(normId(row.parent_id), normId(row.id));
        renderContractRows(Array.isArray(row.contracts) ? row.contracts : []);
        openOrganizationModal();
        if (options && options.focusContracts) {
            focusOrganizationContractsSection();
        }
    }

    function bindEvents() {
        if (state.bound) return;
        state.bound = true;
        registerOrganizationsBulkActions();

        const root = document.getElementById('settingsOrganizationsTabRoot');
        const searchInput = document.getElementById('organizationsSearchInput');
        const typeFilter = document.getElementById('organizationsTypeFilter');
        const statusFilter = document.getElementById('organizationsStatusFilter');
        const pageSize = document.getElementById('organizationsPageSize');
        const modal = document.getElementById('organizationModal');

        if (searchInput) {
            searchInput.addEventListener('input', (event) => {
                if (state.searchTimer) window.clearTimeout(state.searchTimer);
                const value = event && event.target ? event.target.value : '';
                state.searchTimer = window.setTimeout(() => {
                    state.search = value || '';
                    state.page = 1;
                    renderOrganizationsTable();
                    state.searchTimer = null;
                }, SEARCH_DEBOUNCE_MS);
            });
        }

        if (typeFilter) {
            typeFilter.addEventListener('change', (event) => {
                state.orgType = event && event.target ? event.target.value : '';
                state.page = 1;
                renderOrganizationsTable();
            });
        }

        if (statusFilter) {
            statusFilter.addEventListener('change', (event) => {
                state.status = event && event.target ? event.target.value : '';
                state.page = 1;
                renderOrganizationsTable();
            });
        }

        if (pageSize) {
            pageSize.addEventListener('change', (event) => {
                const value = Number(event && event.target ? event.target.value : DEFAULT_PAGE_SIZE);
                state.pageSize = Number.isFinite(value) && value > 0 ? value : DEFAULT_PAGE_SIZE;
                state.page = 1;
                renderOrganizationsTable();
            });
        }

        if (modal) {
            modal.addEventListener('click', (event) => {
                if (event.target === modal) {
                    closeOrganizationModal();
                }
            });
        }

        document.addEventListener('click', (event) => {
            const target = event && event.target;
            const insideKebab = Boolean(target && target.closest && target.closest('.users-kebab') && root && root.contains(target.closest('.users-kebab')));
            if (!insideKebab) {
                closeAllOrganizationActionMenus();
            }

            const actionEl = event && event.target && event.target.closest
                ? event.target.closest('[data-org-action]')
                : null;
            if (!actionEl) return;

            if (root && !root.contains(actionEl) && !(modal && modal.contains(actionEl))) return;

            const action = String(actionEl.dataset.orgAction || '').trim();
            if (!action) return;

            switch (action) {
                case 'refresh-organizations':
                    loadOrganizations(true);
                    break;
                case 'open-create-organization-modal':
                    void openCreateOrganizationModal();
                    break;
                case 'change-organizations-page':
                    changeOrganizationsPage(Number(actionEl.dataset.step || 0));
                    break;
                case 'goto-organizations-page':
                    gotoOrganizationsPage(Number(actionEl.dataset.page || 0));
                    break;
                case 'close-organization-modal':
                    closeOrganizationModal();
                    break;
                case 'save-organization':
                    saveOrganization();
                    break;
                case 'add-contract-row':
                    addContractRow();
                    break;
                case 'remove-contract-row':
                    removeContractRow(actionEl);
                    break;
                case 'toggle-organization-action-menu':
                    toggleOrganizationActionMenu(event, actionEl.dataset.orgId || 0);
                    break;
                case 'open-edit-organization-modal':
                    closeAllOrganizationActionMenus();
                    void openEditOrganizationModal(Number(actionEl.dataset.orgId || 0));
                    break;
                case 'open-organization-contracts':
                    closeAllOrganizationActionMenus();
                    void openEditOrganizationModal(Number(actionEl.dataset.orgId || 0), { focusContracts: true });
                    break;
                case 'deactivate-organization':
                    closeAllOrganizationActionMenus();
                    deactivateOrganization(Number(actionEl.dataset.orgId || 0));
                    break;
                case 'restore-organization':
                    closeAllOrganizationActionMenus();
                    restoreOrganization(Number(actionEl.dataset.orgId || 0));
                    break;
                case 'hard-delete-organization':
                    closeAllOrganizationActionMenus();
                    hardDeleteOrganization(Number(actionEl.dataset.orgId || 0));
                    break;
                default:
                    break;
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event && event.key === 'Escape') {
                closeAllOrganizationActionMenus();
            }
        });
    }

    function gotoOrganizationsPage(page) {
        state.page = Math.max(1, Number(page) || 1);
        renderOrganizationsTable();
    }

    function changeOrganizationsPage(delta) {
        state.page = Math.max(1, Number(state.page) + Number(delta || 0));
        renderOrganizationsTable();
    }

    async function initOrganizationsSettings(force = false) {
        bindEvents();
        await Promise.all([
            loadOrganizations(force),
            ensureBlocksLoaded(false).catch((error) => {
                console.warn('Organization blocks unavailable during init:', error);
            }),
        ]);
    }

    window.initOrganizationsSettings = initOrganizationsSettings;
    window.openCreateOrganizationModal = openCreateOrganizationModal;
    window.openEditOrganizationModal = openEditOrganizationModal;
    window.closeOrganizationModal = closeOrganizationModal;
    window.saveOrganization = saveOrganization;
    window.deactivateOrganization = deactivateOrganization;
    window.restoreOrganization = restoreOrganization;
    window.hardDeleteOrganization = hardDeleteOrganization;
    window.changeOrganizationsPage = changeOrganizationsPage;
    window.gotoOrganizationsPage = gotoOrganizationsPage;
})();
