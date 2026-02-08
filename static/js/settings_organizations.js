(() => {
    const API_BASE = '/api/v1/settings/organizations';
    const TABLE_COLSPAN = 9;
    const SEARCH_DEBOUNCE_MS = 180;
    const DEFAULT_PAGE_SIZE = 20;

    const state = {
        initialized: false,
        loading: false,
        bound: false,
        items: [],
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
            system: 'سیستم',
            employer: 'کارفرما',
            consultant: 'مشاور',
            contractor: 'پیمانکار',
            subcontractor: 'پیمانکار جزء',
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
                const indent = depth > 0 ? `${'— '.repeat(depth)}` : '';
                const label = `${indent}${norm(item.name) || norm(item.code)}`;
                const selectedAttr = itemId === selected ? 'selected' : '';
                return `<option value="${esc(itemId)}" ${selectedAttr}>${esc(label)}</option>`;
            })
            .join('');

        parentSelect.innerHTML = `
            <option value="">- بدون والد -</option>
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
            const haystack = [
                item && item.code,
                item && item.name,
                item && item.parent_code,
                item && item.parent_name,
                itemType,
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
            ? '<span class="status-badge active">فعال</span>'
            : '<span class="status-badge inactive">غیرفعال</span>';
    }

    function renderOrganizationsTable() {
        const body = document.getElementById('organizationsTableBody');
        const meta = document.getElementById('organizationsTableMeta');
        const prevBtn = document.getElementById('organizationsPrevPageBtn');
        const nextBtn = document.getElementById('organizationsNextPageBtn');
        const pageButtons = document.getElementById('organizationsPageButtons');
        if (!body) return;

        const info = getPagination();

        if (!info.rows.length) {
            body.innerHTML = `<tr><td colspan="${TABLE_COLSPAN}" class="center-text muted" style="padding: 26px;">موردی یافت نشد</td></tr>`;
        } else {
            body.innerHTML = info.rows.map((item) => {
                const id = Number(item.id || 0);
                const depth = Math.max(0, Number(item.depth || 0));
                const padding = depth * 18;
                const protectedOrg = isProtectedOrganization(item);
                const toggleLabel = item.is_active ? 'غیرفعال' : 'فعال‌سازی';
                const toggleAction = item.is_active ? 'deactivate-organization' : 'restore-organization';
                const toggleDisabled = protectedOrg ? 'disabled' : '';
                const deleteDisabled = protectedOrg ? 'disabled' : '';

                return `
                    <tr>
                        <td>${id}</td>
                        <td><code>${esc(item.code || '-')}</code></td>
                        <td>
                            <div style="padding-right:${padding}px;">
                                ${esc(item.name || '-')}
                            </div>
                        </td>
                        <td>${esc(typeLabel(item.org_type))}</td>
                        <td>${esc(item.parent_name || item.parent_code || '-')}</td>
                        <td>${Number(item.users_count || 0)}</td>
                        <td>${Number(item.children_count || 0)}</td>
                        <td>${statusBadge(Boolean(item.is_active))}</td>
                        <td>
                            <div class="general-row-actions">
                                <button class="btn-archive-icon" type="button" data-org-action="open-edit-organization-modal" data-org-id="${id}">ویرایش</button>
                                <button class="btn-archive-icon" type="button" data-org-action="${toggleAction}" data-org-id="${id}" ${toggleDisabled}>${toggleLabel}</button>
                                <button class="btn-archive-icon" type="button" data-org-action="hard-delete-organization" data-org-id="${id}" ${deleteDisabled}>حذف دائم</button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        if (meta) {
            meta.textContent = `نمایش ${info.from}-${info.to} از ${info.total} سازمان`;
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

    function setLoadingRow(message = 'در حال بارگذاری...') {
        const body = document.getElementById('organizationsTableBody');
        if (!body) return;
        body.innerHTML = `<tr><td colspan="${TABLE_COLSPAN}" class="center-text muted" style="padding: 26px;">${esc(message)}</td></tr>`;
    }

    async function loadOrganizations(force = false) {
        if (state.loading) return;
        if (state.initialized && !force) {
            renderOrganizationsTable();
            return;
        }
        state.loading = true;
        setLoadingRow('در حال بارگذاری سازمان‌ها...');
        try {
            const payload = await request(`${API_BASE}?include_inactive=true&tree=true`);
            state.items = Array.isArray(payload && payload.items) ? payload.items : [];
            state.initialized = true;
            renderParentOptions();
            renderOrganizationsTable();
        } catch (error) {
            setLoadingRow(`خطا در بارگذاری: ${error.message}`);
            notify('error', error.message || 'بارگذاری سازمان‌ها ناموفق بود');
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
        if (titleEl) titleEl.textContent = 'ایجاد سازمان جدید';
        renderParentOptions('', '');
    }

    function openOrganizationModal() {
        const modal = document.getElementById('organizationModal');
        if (modal) modal.style.display = 'flex';
    }

    function closeOrganizationModal() {
        const modal = document.getElementById('organizationModal');
        if (modal) modal.style.display = 'none';
    }

    function collectOrganizationPayload() {
        const id = normId(document.getElementById('organizationId')?.value || '');
        const code = normUpper(document.getElementById('organizationCode')?.value || '');
        const name = norm(document.getElementById('organizationName')?.value || '');
        const orgType = norm(document.getElementById('organizationType')?.value || '').toLowerCase();
        const parentId = normId(document.getElementById('organizationParentId')?.value || '');
        const isActive = Boolean(document.getElementById('organizationIsActive')?.checked);

        if (!code) throw new Error('کد سازمان الزامی است');
        if (!name) throw new Error('نام سازمان الزامی است');
        if (!orgType) throw new Error('نوع سازمان الزامی است');

        return {
            id: id ? Number(id) : null,
            code,
            name,
            org_type: orgType,
            parent_id: parentId ? Number(parentId) : null,
            is_active: isActive,
        };
    }

    async function saveOrganization() {
        try {
            const payload = collectOrganizationPayload();
            await request(`${API_BASE}/upsert`, {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            notify('success', 'سازمان ذخیره شد');
            closeOrganizationModal();
            state.page = 1;
            await loadOrganizations(true);
        } catch (error) {
            notify('error', error.message || 'ذخیره سازمان ناموفق بود');
        }
    }

    async function deactivateOrganization(id) {
        const row = getOrganizationById(id);
        if (!row) return;
        if (!confirm(`سازمان "${row.name || row.code}" غیرفعال شود؟`)) return;
        try {
            await request(`${API_BASE}/delete`, {
                method: 'POST',
                body: JSON.stringify({ id: Number(row.id), hard_delete: false }),
            });
            notify('success', 'سازمان غیرفعال شد');
            await loadOrganizations(true);
        } catch (error) {
            notify('error', error.message || 'غیرفعال‌سازی سازمان ناموفق بود');
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
                }),
            });
            notify('success', 'سازمان فعال شد');
            await loadOrganizations(true);
        } catch (error) {
            notify('error', error.message || 'فعال‌سازی سازمان ناموفق بود');
        }
    }

    async function hardDeleteOrganization(id) {
        const row = getOrganizationById(id);
        if (!row) return;
        if (!confirm(`حذف دائم سازمان "${row.name || row.code}" انجام شود؟ این عملیات غیرقابل بازگشت است.`)) return;
        try {
            await request(`${API_BASE}/delete`, {
                method: 'POST',
                body: JSON.stringify({ id: Number(row.id), hard_delete: true }),
            });
            notify('success', 'سازمان حذف شد');
            await loadOrganizations(true);
        } catch (error) {
            notify('error', error.message || 'حذف دائم سازمان ناموفق بود');
        }
    }

    function openCreateOrganizationModal() {
        resetOrganizationForm();
        openOrganizationModal();
    }

    function openEditOrganizationModal(id) {
        const row = getOrganizationById(id);
        if (!row) {
            notify('error', 'سازمان انتخاب شده یافت نشد');
            return;
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
        if (titleEl) titleEl.textContent = `ویرایش سازمان ${row.code || ''}`;
        renderParentOptions(normId(row.parent_id), normId(row.id));
        openOrganizationModal();
    }

    function bindEvents() {
        if (state.bound) return;
        state.bound = true;

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
                    openCreateOrganizationModal();
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
                case 'open-edit-organization-modal':
                    openEditOrganizationModal(Number(actionEl.dataset.orgId || 0));
                    break;
                case 'deactivate-organization':
                    deactivateOrganization(Number(actionEl.dataset.orgId || 0));
                    break;
                case 'restore-organization':
                    restoreOrganization(Number(actionEl.dataset.orgId || 0));
                    break;
                case 'hard-delete-organization':
                    hardDeleteOrganization(Number(actionEl.dataset.orgId || 0));
                    break;
                default:
                    break;
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
        await loadOrganizations(force);
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
