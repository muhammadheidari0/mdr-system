(() => {
    const MATRIX_ENDPOINT = '/api/v1/settings/permissions/matrix';
    const SEARCH_DEBOUNCE_MS = 180;

    const state = {
        initialized: false,
        toolbarBound: false,
        roles: [],
        permissions: [],
        matrix: {},
        filterQuery: '',
        filterGroup: '',
        collapsedGroups: new Set(),
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

    function normalizeRole(role) {
        return String(role || '').trim().toLowerCase();
    }

    function roleLabel(role) {
        const map = {
            admin: 'مدیر سیستم',
            manager: 'سرپرست',
            user: 'کاربر عادی',
            dcc: 'کنترل مدارک (DCC)',
            viewer: 'مشاهده گر',
        };
        const roleKey = normalizeRole(role);
        return map[roleKey] || role;
    }

    function permissionLabel(permission) {
        return String(permission || '')
            .replace(':', ' / ')
            .replace(/_/g, ' ');
    }

    function permissionGroupKey(permission) {
        const raw = String(permission || '').trim();
        if (!raw) return 'other';
        if (raw.indexOf(':') >= 0) return raw.split(':')[0].toLowerCase();
        if (raw.indexOf('.') >= 0) return raw.split('.')[0].toLowerCase();
        if (raw.indexOf('_') >= 0) return raw.split('_')[0].toLowerCase();
        return 'other';
    }

    function permissionGroupLabel(groupKey) {
        const key = String(groupKey || '').toLowerCase();
        if (!key || key === 'other') return 'سایر';
        return key.replace(/[_-]+/g, ' ').toUpperCase();
    }

    function normalizeQuery(value) {
        return String(value || '').trim().toLowerCase();
    }

    function permissionSearchText(permission) {
        const raw = String(permission || '');
        return `${raw} ${permissionLabel(raw)} ${permissionGroupKey(raw)}`.toLowerCase();
    }

    function groupPermissions(perms) {
        const groups = new Map();
        (perms || []).forEach((perm) => {
            const groupKey = permissionGroupKey(perm);
            if (!groups.has(groupKey)) groups.set(groupKey, []);
            groups.get(groupKey).push(perm);
        });

        const entries = Array.from(groups.entries()).map(([key, list]) => {
            const sorted = list.slice().sort((a, b) => String(a).localeCompare(String(b)));
            return [key, sorted];
        });

        entries.sort((a, b) => {
            if (a[0] === 'other') return 1;
            if (b[0] === 'other') return -1;
            return String(a[0]).localeCompare(String(b[0]));
        });

        return entries;
    }

    function getUniqueGroups() {
        const groups = new Set();
        (state.permissions || []).forEach((perm) => groups.add(permissionGroupKey(perm)));
        return Array.from(groups).sort((a, b) => {
            if (a === 'other') return 1;
            if (b === 'other') return -1;
            return String(a).localeCompare(String(b));
        });
    }

    function getFilteredPermissions() {
        const query = normalizeQuery(state.filterQuery);
        const group = String(state.filterGroup || '').trim().toLowerCase();

        return (state.permissions || []).filter((perm) => {
            if (group && permissionGroupKey(perm) !== group) return false;
            if (query && permissionSearchText(perm).indexOf(query) < 0) return false;
            return true;
        });
    }

    async function request(url, options = {}) {
        const requester = typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : fetch;
        const response = await requester(url, options);

        if (!response.ok) {
            let message = `Request failed (${response.status})`;
            try {
                const body = await response.clone().json();
                message = body.detail || body.message || message;
            } catch (_) {}
            throw new Error(message);
        }

        return response.json();
    }

    function ensureMatrixDefaults() {
        state.roles.forEach((role) => {
            const roleKey = normalizeRole(role);
            if (!state.matrix[roleKey]) state.matrix[roleKey] = {};
            state.permissions.forEach((permission) => {
                if (typeof state.matrix[roleKey][permission] !== 'boolean') {
                    state.matrix[roleKey][permission] = false;
                }
            });
        });
    }

    function renderGroupOptions() {
        const groupSelect = document.getElementById('permissionsResourceFilter');
        if (!groupSelect) return;

        const groups = getUniqueGroups();
        const selected = String(state.filterGroup || '');

        groupSelect.innerHTML = `
            <option value="">همه منابع</option>
            ${groups.map((group) => `<option value="${esc(group)}">${esc(permissionGroupLabel(group))}</option>`).join('')}
        `;

        groupSelect.value = groups.indexOf(selected) >= 0 ? selected : '';
        if (groupSelect.value !== selected) {
            state.filterGroup = '';
        }
    }

    function renderMatrix() {
        const head = document.getElementById('permissionsMatrixHead');
        const body = document.getElementById('permissionsMatrixBody');
        if (!head || !body) return;

        const allPermissions = state.permissions || [];
        const filteredPermissions = getFilteredPermissions();
        const columnCount = Math.max(state.roles.length + 1, 2);

        if (!state.roles.length || !allPermissions.length) {
            head.innerHTML = '';
            body.innerHTML = `<tr><td class="center-text muted" colspan="${columnCount}" style="padding: 36px;">داده ای برای نمایش وجود ندارد</td></tr>`;
            return;
        }

        head.innerHTML = `
            <tr>
                <th class="sticky-col matrix-permission-col">مجوز</th>
                ${state.roles.map((role) => `<th class="matrix-role-head">${esc(roleLabel(role))}</th>`).join('')}
            </tr>
        `;

        if (!filteredPermissions.length) {
            body.innerHTML = `<tr><td class="center-text muted" colspan="${columnCount}" style="padding: 34px;">نتیجه ای مطابق فیلتر فعلی پیدا نشد</td></tr>`;
            return;
        }

        const groups = groupPermissions(filteredPermissions);
        body.innerHTML = groups.map(([groupKey, perms]) => {
            const encodedGroupKey = encodeURIComponent(groupKey);
            const groupName = permissionGroupLabel(groupKey);
            const isCollapsed = state.collapsedGroups.has(groupKey);

            const permissionRows = perms.map((permission) => {
                return `
                    <tr class="matrix-permission-row ${isCollapsed ? 'is-collapsed' : ''}" data-group-parent="${esc(groupKey)}">
                        <td class="matrix-permission-name sticky-col">
                            <span>${esc(permissionLabel(permission))}</span>
                            <span class="matrix-permission-code">${esc(permission)}</span>
                        </td>
                        ${state.roles.map((role) => {
                            const roleKey = normalizeRole(role);
                            const isAdmin = roleKey === 'admin';
                            const checked = Boolean(state.matrix[roleKey] && state.matrix[roleKey][permission]);
                            return `
                                <td class="center-text matrix-role-cell">
                                    <label class="toggle-switch ${isAdmin ? 'is-disabled' : ''}" ${isAdmin ? 'title="ادمین همیشه دسترسی کامل دارد"' : ''}>
                                        <input
                                            type="checkbox"
                                            ${checked ? 'checked' : ''}
                                            ${isAdmin ? 'disabled' : ''}
                                            onchange="togglePermissionCell('${esc(role)}', '${esc(permission)}', this.checked)"
                                        >
                                        <span class="toggle-slider"></span>
                                    </label>
                                </td>
                            `;
                        }).join('')}
                    </tr>
                `;
            }).join('');

            return `
                <tr class="matrix-group-row ${isCollapsed ? 'is-collapsed' : ''}" data-group-key="${esc(groupKey)}">
                    <td colspan="${columnCount}">
                        <div class="matrix-group-header">
                            <button type="button" class="matrix-group-toggle" onclick="togglePermissionGroup('${encodedGroupKey}')">
                                <span class="material-icons-round">expand_more</span>
                                <span class="matrix-group-title">${esc(groupName)}</span>
                            </button>
                            <div class="matrix-group-tools">
                                <span class="matrix-group-count">${perms.length}</span>
                            </div>
                        </div>
                    </td>
                </tr>
                ${permissionRows}
            `;
        }).join('');
    }

    function bindToolbar() {
        if (state.toolbarBound) return;

        const searchInput = document.getElementById('permissionsSearchInput');
        const groupSelect = document.getElementById('permissionsResourceFilter');

        if (searchInput) {
            searchInput.addEventListener('input', (event) => {
                const value = event && event.target ? event.target.value : '';
                if (state.searchTimer) {
                    window.clearTimeout(state.searchTimer);
                }
                state.searchTimer = window.setTimeout(() => {
                    state.filterQuery = String(value || '');
                    renderMatrix();
                    state.searchTimer = null;
                }, SEARCH_DEBOUNCE_MS);
            });
        }

        if (groupSelect) {
            groupSelect.addEventListener('change', (event) => {
                state.filterGroup = String(event && event.target ? event.target.value : '');
                renderMatrix();
            });
        }

        state.toolbarBound = true;
    }

    async function load(force = false) {
        bindToolbar();

        if (state.initialized && !force) {
            renderGroupOptions();
            renderMatrix();
            return;
        }

        const body = document.getElementById('permissionsMatrixBody');
        if (body) {
            body.innerHTML = '<tr><td class="center-text muted" colspan="6" style="padding: 36px;">در حال بارگذاری ماتریس دسترسی...</td></tr>';
        }

        const payload = await request(MATRIX_ENDPOINT);
        state.roles = Array.isArray(payload.roles) ? payload.roles : [];
        state.permissions = Array.isArray(payload.permissions) ? payload.permissions : [];
        state.matrix = payload.matrix || {};
        state.collapsedGroups = new Set();

        ensureMatrixDefaults();
        state.initialized = true;
        renderGroupOptions();
        renderMatrix();
    }

    window.togglePermissionCell = function togglePermissionCell(role, permission, checked) {
        const roleKey = normalizeRole(role);
        if (roleKey === 'admin') return;

        if (!state.matrix[roleKey]) {
            state.matrix[roleKey] = {};
        }
        state.matrix[roleKey][permission] = Boolean(checked);
    };

    window.togglePermissionGroup = function togglePermissionGroup(encodedKey) {
        const groupKey = decodeURIComponent(String(encodedKey || ''));
        if (!groupKey) return;

        if (state.collapsedGroups.has(groupKey)) {
            state.collapsedGroups.delete(groupKey);
        } else {
            state.collapsedGroups.add(groupKey);
        }

        renderMatrix();
    };

    window.expandAllPermissionGroups = function expandAllPermissionGroups() {
        state.collapsedGroups.clear();
        renderMatrix();
    };

    window.collapseAllPermissionGroups = function collapseAllPermissionGroups() {
        const groups = new Set(getFilteredPermissions().map((permission) => permissionGroupKey(permission)));
        state.collapsedGroups = groups;
        renderMatrix();
    };

    window.resetPermissionFilters = function resetPermissionFilters() {
        state.filterQuery = '';
        state.filterGroup = '';
        if (state.searchTimer) {
            window.clearTimeout(state.searchTimer);
            state.searchTimer = null;
        }

        const searchInput = document.getElementById('permissionsSearchInput');
        const groupSelect = document.getElementById('permissionsResourceFilter');
        if (searchInput) searchInput.value = '';
        if (groupSelect) groupSelect.value = '';

        renderMatrix();
    };

    window.savePermissionsMatrix = async function savePermissionsMatrix() {
        try {
            ensureMatrixDefaults();
            await request(MATRIX_ENDPOINT, {
                method: 'POST',
                body: JSON.stringify({ matrix: state.matrix }),
            });
            notify('success', 'ماتریس سطح دسترسی ذخیره شد');
            await load(true);
        } catch (error) {
            notify('error', error.message || 'ذخیره ماتریس ناموفق بود');
        }
    };

    window.initPermissionsSettings = async function initPermissionsSettings(force = false) {
        try {
            await load(force);
        } catch (error) {
            notify('error', error.message || 'بارگذاری ماتریس دسترسی ناموفق بود');
        }
    };
})();
