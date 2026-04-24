// @ts-nocheck
(() => {
    const MATRIX_ENDPOINT = '/api/v1/settings/permissions/matrix';
    const SEARCH_DEBOUNCE_MS = 180;
    const DEFAULT_CATEGORY = 'consultant';
    const KNOWN_CATEGORIES = ['consultant', 'contractor', 'employer', 'dcc'];

    const TREE_CATALOG = [
        {
            key: 'edms_core',
            label: 'هسته EDMS',
            pages: [
                { key: 'documents', label: 'مدارک مهندسی', groupKeys: ['documents'] },
                { key: 'archive', label: 'آرشیو مدارک', groupKeys: ['archive'] },
                { key: 'transmittal', label: 'ترنسمیتال', groupKeys: ['transmittal'] },
                { key: 'correspondence', label: 'مکاتبات', groupKeys: ['correspondence'] },
            ],
        },
        {
            key: 'visibility',
            label: 'نمایش هاب‌ها و ماژول‌ها',
            pages: [
                {
                    key: 'hub_visibility',
                    label: 'نمایش هاب‌ها',
                    groupKeys: ['hub_edms', 'hub_reports', 'hub_contractor', 'hub_consultant'],
                },
                {
                    key: 'module_visibility',
                    label: 'نمایش ماژول‌ها',
                    groupKeys: [
                        'module_archive',
                        'module_transmittal',
                        'module_correspondence',
                        'module_reports',
                        'module_site_logs_contractor',
                        'module_comm_items_contractor',
                        'module_permit_qc_contractor',
                        'module_site_logs_consultant',
                        'module_comm_items_consultant',
                        'module_permit_qc_consultant',
                        'module_settings',
                    ],
                },
            ],
        },
        {
            key: 'field_control',
            label: 'فرآیندهای اجرایی',
            pages: [
                { key: 'ops_workboard', label: 'کارتابل', groupKeys: ['workboard'] },
                { key: 'ops_site_logs', label: 'گزارش‌های کارگاهی', groupKeys: ['site_logs'] },
                { key: 'ops_comm_items', label: 'اقلام ارتباطی', groupKeys: ['comm_items'] },
                { key: 'ops_permit_qc', label: 'پرمیت و کنترل کیفیت', groupKeys: ['permit_qc'] },
                { key: 'ops_bim', label: 'مدل‌سازی اطلاعات ساختمان (BIM)', groupKeys: ['bim'] },
            ],
        },
        {
            key: 'analytics',
            label: 'گزارش و پایش',
            pages: [
                { key: 'dashboard', label: 'داشبورد', groupKeys: ['dashboard'] },
                { key: 'reports', label: 'گزارش‌ها', groupKeys: ['reports'] },
            ],
        },
        {
            key: 'admin_control',
            label: 'پیکربندی و مدیریت',
            pages: [
                {
                    key: 'users_access',
                    label: 'کاربران و سطح دسترسی',
                    groupKeys: ['users', 'organizations', 'permissions'],
                },
                {
                    key: 'settings_catalog',
                    label: 'تنظیمات و فهرست‌های پایه',
                    groupKeys: ['settings', 'lookup'],
                },
                {
                    key: 'storage_sync',
                    label: 'ذخیره‌سازی و کش',
                    groupKeys: ['storage', 'site_cache'],
                },
                {
                    key: 'integrations',
                    label: 'یکپارچه‌سازی‌ها',
                    groupKeys: ['integrations'],
                },
            ],
        },
    ];

    const state = {
        initialized: false,
        toolbarBound: false,
        actionsBound: false,
        activeCategory: DEFAULT_CATEGORY,
        categories: KNOWN_CATEGORIES.slice(),
        roles: [],
        permissions: [],
        matrix: {},
        filterQuery: '',
        filterGroup: '',
        collapsedSections: new Set(),
        collapsedGroups: new Set(),
        renderedSections: {},
        renderedPages: {},
        searchTimer: null,
        readOnly: false,
    };

    const catalogIndex = (() => {
        const groupToPage = new Map();
        const pageToSection = new Map();
        const pageLabels = new Map();
        const sectionLabels = new Map();
        for (const section of TREE_CATALOG) {
            sectionLabels.set(section.key, section.label);
            for (const page of section.pages) {
                pageToSection.set(page.key, section.key);
                pageLabels.set(page.key, page.label);
                for (const key of page.groupKeys || []) {
                    groupToPage.set(String(key || '').toLowerCase(), page.key);
                }
            }
        }
        return {
            groupToPage,
            pageToSection,
            pageLabels,
            sectionLabels,
        };
    })();

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

    function normalizeCategory(value) {
        const key = String(value || '').trim().toLowerCase();
        if (KNOWN_CATEGORIES.indexOf(key) >= 0) return key;
        return DEFAULT_CATEGORY;
    }

    function categoryLabel(value) {
        const map = {
            consultant: 'مشاور',
            contractor: 'پیمانکار',
            employer: 'کارفرما',
            dcc: 'DCC',        };
        return map[normalizeCategory(value)] || 'مشاور';
    }

    function roleLabel(role) {
        const map = {
            manager: 'سرپرست',
            user: 'کاربر عادی',
            dcc: 'کنترل مدارک (DCC)',
            viewer: 'مشاهده‌گر',
        };
        const roleKey = normalizeRole(role);
        return map[roleKey] || role;
    }

    function splitPermission(permission) {
        const raw = String(permission || '').trim();
        if (!raw) return [];
        if (raw.indexOf(':') >= 0) {
            return raw.split(':').map((item) => String(item || '').trim()).filter(Boolean);
        }
        if (raw.indexOf('/') >= 0) {
            return raw.split('/').map((item) => String(item || '').trim()).filter(Boolean);
        }
        if (raw.indexOf('.') >= 0) {
            return raw.split('.').map((item) => String(item || '').trim()).filter(Boolean);
        }
        return [raw];
    }

    function readableToken(token) {
        const key = String(token || '').trim().toLowerCase();
        const map = {
            read: 'مشاهده',
            create: 'ایجاد',
            update: 'ویرایش',
            delete: 'حذف',
            issue: 'صدور',
            void: 'ابطال',
            manage: 'مدیریت',
            upload: 'آپلود',
            download: 'دانلود',
            export: 'خروجی',
            import: 'ورودی',
            review: 'بررسی',
            approve: 'تایید',
            reject: 'رد',
            publish: 'انتشار',
            submit: 'ارسال',
            sync: 'همگام‌سازی',
            ingest: 'دریافت',
            audit: 'ممیزی',
            relation: 'ارتباطات',
            tag: 'تگ‌ها',
            comment: 'کامنت',
            template: 'قالب',
            attachment: 'پیوست',
            report: 'گزارش',
        };
        if (map[key]) return map[key];
        return String(token || '')
            .replace(/[_-]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim()
            .toUpperCase();
    }

    function permissionLeafLabel(permission) {
        const parts = splitPermission(permission);
        if (!parts.length) return '-';
        if (parts.length === 1) return readableToken(parts[0]);
        return parts.slice(1).map((item) => readableToken(item)).join(' / ');
    }

    function permissionLabel(permission) {
        const parts = splitPermission(permission);
        if (!parts.length) return '-';
        return parts.map((item) => readableToken(item)).join(' / ');
    }

    function permissionGroupKey(permission) {
        const parts = splitPermission(permission);
        if (parts.length) return String(parts[0] || '').toLowerCase();
        return 'other';
    }

    function permissionGroupLabel(groupKey) {
        const key = String(groupKey || '').toLowerCase();
        const map = {
            archive: 'آرشیو مدارک',
            dashboard: 'داشبورد',
            documents: 'مدارک مهندسی',
            transmittal: 'ترنسمیتال',
            correspondence: 'مکاتبات',
            settings: 'تنظیمات عمومی',
            users: 'کاربران',
            organizations: 'سازمان‌ها',
            permissions: 'سطح دسترسی',
            module_settings: 'نمایش ماژول تنظیمات',
            reports: 'گزارش‌ها',
            hub_edms: 'نمایش هاب EDMS',
            hub_reports: 'نمایش هاب گزارش‌ها',
            hub_contractor: 'نمایش هاب پیمانکار',
            hub_consultant: 'نمایش هاب مشاور',
            module_archive: 'نمایش ماژول آرشیو مدارک',
            module_transmittal: 'نمایش ماژول ترنسمیتال',
            module_correspondence: 'نمایش ماژول مکاتبات',
            module_reports: 'نمایش ماژول گزارش‌ها',
            module_site_logs_contractor: 'نمایش ماژول گزارش کارگاهی پیمانکار',
            module_comm_items_contractor: 'نمایش ماژول اقلام ارتباطی پیمانکار',
            module_permit_qc_contractor: 'نمایش ماژول Permit/QC پیمانکار',
            module_site_logs_consultant: 'نمایش ماژول گزارش کارگاهی مشاور',
            module_comm_items_consultant: 'نمایش ماژول اقلام ارتباطی مشاور',
            module_permit_qc_consultant: 'نمایش ماژول Permit/QC مشاور',
            workboard: 'کارتابل',
            site_logs: 'گزارش‌های کارگاهی',
            comm_items: 'اقلام ارتباطی',
            permit_qc: 'پرمیت و کنترل کیفیت',
            bim: 'مدل‌سازی اطلاعات ساختمان (BIM)',
            lookup: 'فهرست‌های پایه',
            storage: 'ذخیره‌سازی',
            site_cache: 'کش سایت و مسیرها',
            integrations: 'یکپارچه‌سازی‌ها',
        };
        if (map[key]) return map[key];
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

    function matrixUrl() {
        const params = new URLSearchParams();
        params.set('category', normalizeCategory(state.activeCategory));
        return `${MATRIX_ENDPOINT}?${params.toString()}`;
    }

    function applyReadOnlyState() {
        const root = document.getElementById('settingsPermissionsTabRoot');
        const saveBtn = root ? root.querySelector('[data-permissions-action="save-permissions-matrix"]') : null;
        if (saveBtn) {
            saveBtn.disabled = !!state.readOnly;
            saveBtn.setAttribute('aria-disabled', state.readOnly ? 'true' : 'false');
            saveBtn.title = state.readOnly ? 'این دسته فقط خواندنی است.' : '';
            saveBtn.classList.toggle('is-disabled', !!state.readOnly);
        }
    }

    function renderCategoryTabs(selectedBtn = null) {
        const tabsRoot = document.getElementById('permissionsCategoryTabs');
        if (!tabsRoot) return;
        const active = normalizeCategory(state.activeCategory);
        const availableCategories = new Set((state.categories || []).map((item) => normalizeCategory(item)));
        const buttons = tabsRoot.querySelectorAll('[data-permissions-category]');
        buttons.forEach((btn) => {
            const key = normalizeCategory(btn.dataset.permissionsCategory || '');
            const visible = availableCategories.size === 0 || availableCategories.has(key);
            btn.style.display = visible ? '' : 'none';
            if (!visible) return;
            const isActive = key === active;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
        applyReadOnlyState();
        if (selectedBtn && typeof selectedBtn.blur === 'function') {
            selectedBtn.blur();
        }
    }

    function getUniqueGroups() {
        const groups = new Set();
        (state.permissions || []).forEach((perm) => groups.add(permissionGroupKey(perm)));
        return Array.from(groups).sort((a, b) => permissionGroupLabel(a).localeCompare(permissionGroupLabel(b), 'fa'));
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

    function cleanupMatrixBulkUi() {
        const table = document.getElementById('permissionsMatrixTable');
        if (!(table instanceof HTMLTableElement)) return;

        try {
            if (window.TableBulk && typeof window.TableBulk.clearSelection === 'function') {
                window.TableBulk.clearSelection(table.id);
            }
        } catch (_) {}

        const parent = table.parentElement;
        if (parent) {
            Array.from(parent.querySelectorAll('.table-bulk-toolbar'))
                .filter((node) => !node.dataset.bulkFor || node.dataset.bulkFor === table.id)
                .forEach((node) => node.remove());
        }

        table.querySelectorAll('.table-bulk-cell').forEach((cell) => cell.remove());
        table.querySelectorAll('tr.bulk-row-selected').forEach((row) => row.classList.remove('bulk-row-selected'));
        table.querySelectorAll('[data-bulk-resolved-key]').forEach((row) => row.removeAttribute('data-bulk-resolved-key'));
        table.querySelectorAll('[data-bulk-row]').forEach((row) => row.removeAttribute('data-bulk-row'));
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
        if (groupSelect.value !== selected) state.filterGroup = '';
    }

    function resolveSectionForGroup(groupKey) {
        const key = String(groupKey || '').toLowerCase();
        const pageKey = catalogIndex.groupToPage.get(key);
        if (pageKey) return catalogIndex.pageToSection.get(pageKey) || 'admin_control';
        return 'admin_control';
    }

    function resolvePageForGroup(groupKey) {
        const key = String(groupKey || '').toLowerCase();
        const mapped = catalogIndex.groupToPage.get(key);
        if (mapped) {
            return {
                key: mapped,
                label: catalogIndex.pageLabels.get(mapped) || permissionGroupLabel(key),
                sectionKey: catalogIndex.pageToSection.get(mapped) || 'admin_control',
                dynamic: false,
            };
        }
        return {
            key: `dynamic:${key}`,
            label: permissionGroupLabel(key),
            sectionKey: resolveSectionForGroup(key),
            dynamic: true,
        };
    }

    function buildPermissionTree(perms) {
        const tree = TREE_CATALOG.map((section) => ({
            key: section.key,
            label: section.label,
            pages: (section.pages || []).map((page, index) => ({
                key: page.key,
                label: page.label,
                dynamic: false,
                sortIndex: index,
                permissions: [],
            })),
        }));

        const sectionByKey = new Map(tree.map((section) => [section.key, section]));
        const pageByKey = new Map();
        tree.forEach((section) => {
            section.pages.forEach((page) => pageByKey.set(page.key, page));
        });

        (perms || []).forEach((permission) => {
            const groupKey = permissionGroupKey(permission);
            const target = resolvePageForGroup(groupKey);
            let section = sectionByKey.get(target.sectionKey);
            if (!section) {
                section = { key: target.sectionKey, label: target.sectionKey, pages: [] };
                sectionByKey.set(target.sectionKey, section);
                tree.push(section);
            }

            let page = pageByKey.get(target.key);
            if (!page) {
                page = {
                    key: target.key,
                    label: target.label,
                    dynamic: true,
                    sortIndex: section.pages.length + 1000,
                    permissions: [],
                };
                section.pages.push(page);
                pageByKey.set(target.key, page);
            }
            page.permissions.push(permission);
        });

        return tree
            .map((section) => ({
                ...section,
                pages: section.pages
                    .map((page) => ({
                        ...page,
                        permissions: page.permissions
                            .slice()
                            .sort((a, b) => String(a).localeCompare(String(b))),
                    }))
                    .filter((page) => page.permissions.length > 0)
                    .sort((a, b) => {
                        if (a.dynamic && !b.dynamic) return 1;
                        if (!a.dynamic && b.dynamic) return -1;
                        if (a.sortIndex !== b.sortIndex) return Number(a.sortIndex) - Number(b.sortIndex);
                        return String(a.label).localeCompare(String(b.label), 'fa');
                    }),
            }))
            .filter((section) => section.pages.length > 0);
    }

    function getRoleStateForPermissions(role, permissions) {
        const roleKey = normalizeRole(role);
        const perms = Array.isArray(permissions) ? permissions : [];
        if (!perms.length) {
            return { checked: false, indeterminate: false, disabled: true, empty: true };
        }

        const values = perms.map((permission) => Boolean(state.matrix[roleKey] && state.matrix[roleKey][permission]));
        const enabledCount = values.filter(Boolean).length;
        return {
            checked: values.length > 0 && enabledCount === values.length,
            indeterminate: enabledCount > 0 && enabledCount < values.length,
            disabled: !!state.readOnly,
            empty: false,
        };
    }

    function renderAggregateRoleCell(scopeKey, role, permissions, handlerName) {
        const roleKey = normalizeRole(role);
        const roleState = getRoleStateForPermissions(role, permissions);
        if (roleState.empty) {
            return `<td class="center-text matrix-role-cell"><span class="muted">-</span></td>`;
        }
        const checked = roleState.checked ? 'checked' : '';
        const disabled = roleState.disabled ? 'disabled' : '';
        const indeterminate = roleState.indeterminate ? 'data-indeterminate="1"' : '';
        return `
            <td class="center-text matrix-role-cell">
                <label class="toggle-switch ${roleState.disabled ? 'is-disabled' : ''}">
                    <input
                        type="checkbox"
                        ${checked}
                        ${disabled}
                        ${indeterminate}
                        data-permissions-action="${esc(handlerName)}"
                        data-scope-key="${encodeURIComponent(scopeKey)}"
                        data-role-key="${esc(roleKey)}"
                    >
                    <span class="toggle-slider"></span>
                </label>
            </td>
        `;
    }

    function applyIndeterminateStates() {
        const checks = document.querySelectorAll('#permissionsMatrixBody input[data-indeterminate="1"]');
        checks.forEach((input) => {
            try {
                input.indeterminate = true;
            } catch (_) {}
            const wrap = input.closest('.toggle-switch');
            if (wrap) wrap.classList.add('is-indeterminate');
        });
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
            body.innerHTML = `<tr><td class="center-text muted" colspan="${columnCount}" style="padding: 36px;">داده‌ای برای نمایش وجود ندارد.</td></tr>`;
            return;
        }

        head.innerHTML = `
            <tr>
                <th class="sticky-col matrix-permission-col">مجوز (درختی)</th>
                ${state.roles.map((role) => `<th class="matrix-role-head">${esc(roleLabel(role))}</th>`).join('')}
            </tr>
        `;

        if (!filteredPermissions.length) {
            state.renderedSections = {};
            state.renderedPages = {};
            body.innerHTML = `<tr><td class="center-text muted" colspan="${columnCount}" style="padding: 34px;">نتیجه‌ای مطابق فیلتر فعلی پیدا نشد.</td></tr>`;
            return;
        }

        const tree = buildPermissionTree(filteredPermissions);
        state.renderedSections = {};
        state.renderedPages = {};
        tree.forEach((section) => {
            state.renderedSections[section.key] = section.pages.flatMap((page) => page.permissions || []);
            section.pages.forEach((page) => {
                state.renderedPages[page.key] = (page.permissions || []).slice();
            });
        });

        body.innerHTML = tree.map((section) => {
            const sectionCollapsed = state.collapsedSections.has(section.key);
            const sectionPerms = state.renderedSections[section.key] || [];
            const sectionRoleCells = state.roles
                .map((role) => renderAggregateRoleCell(section.key, role, sectionPerms, 'toggle-permission-section-role'))
                .join('');

            const pagesHtml = section.pages.map((page) => {
                const pageCollapsed = state.collapsedGroups.has(page.key);
                const hiddenBySection = sectionCollapsed;
                const pagePerms = state.renderedPages[page.key] || [];
                const pageRoleCells = state.roles
                    .map((role) => renderAggregateRoleCell(page.key, role, pagePerms, 'toggle-permission-group-role'))
                    .join('');

                const pageHiddenClass = hiddenBySection ? 'is-collapsed' : '';
                const pageCollapsedClass = pageCollapsed ? 'is-page-collapsed' : '';

                const childRows = pagePerms.map((permission) => {
                    const childHidden = hiddenBySection || pageCollapsed;
                    const childClass = childHidden ? 'is-collapsed' : '';
                    const leafLabel = permissionLeafLabel(permission);
                    return `
                        <tr class="matrix-tree-child-row ${childClass}" data-group-parent="${esc(page.key)}" data-section-parent="${esc(section.key)}">
                            <td class="matrix-permission-name sticky-col">
                                <span class="matrix-tree-action-label">${esc(leafLabel)}</span>
                                <span class="matrix-tree-code">${esc(permission)}</span>
                            </td>
                            ${state.roles.map((role) => {
                                const roleKey = normalizeRole(role);
                                const isDisabled = !!state.readOnly;
                                const checked = Boolean(state.matrix[roleKey] && state.matrix[roleKey][permission]);
                                return `
                                    <td class="center-text matrix-role-cell">
                                        <label class="toggle-switch ${isDisabled ? 'is-disabled' : ''}">
                                            <input
                                                type="checkbox"
                                                ${checked ? 'checked' : ''}
                                                ${isDisabled ? 'disabled' : ''}
                                                data-permissions-action="toggle-permission-cell"
                                                data-role-key="${esc(roleKey)}"
                                                data-permission="${encodeURIComponent(permission)}"
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
                    <tr class="matrix-tree-group-row ${pageHiddenClass} ${pageCollapsedClass}" data-group-key="${esc(page.key)}" data-section-parent="${esc(section.key)}">
                        <td class="matrix-permission-name sticky-col matrix-tree-group-cell">
                            <button type="button" class="matrix-tree-group-toggle" data-permissions-action="toggle-permission-group" data-page-key="${encodeURIComponent(page.key)}">
                                <span class="material-icons-round">expand_more</span>
                                <span class="matrix-tree-group-name">${esc(page.label)}</span>
                            </button>
                            <span class="matrix-group-count">${pagePerms.length}</span>
                        </td>
                        ${pageRoleCells}
                    </tr>
                    ${childRows}
                `;
            }).join('');

            return `
                <tr class="matrix-tree-section-row ${sectionCollapsed ? 'is-collapsed' : ''}" data-section-key="${esc(section.key)}">
                    <td class="matrix-permission-name sticky-col matrix-tree-section-cell">
                        <button type="button" class="matrix-tree-section-toggle" data-permissions-action="toggle-permission-section" data-section-key="${encodeURIComponent(section.key)}">
                            <span class="material-icons-round">expand_more</span>
                            <span class="matrix-tree-section-name">${esc(section.label)}</span>
                        </button>
                        <span class="matrix-group-count">${sectionPerms.length}</span>
                    </td>
                    ${sectionRoleCells}
                </tr>
                ${pagesHtml}
            `;
        }).join('');

        applyIndeterminateStates();
    }

    function bindToolbar() {
        cleanupMatrixBulkUi();
        if (state.toolbarBound) return;

        const root = document.getElementById('settingsPermissionsTabRoot');
        const searchInput = document.getElementById('permissionsSearchInput');
        const groupSelect = document.getElementById('permissionsResourceFilter');

        if (searchInput) {
            searchInput.addEventListener('input', (event) => {
                const value = event && event.target ? event.target.value : '';
                if (state.searchTimer) window.clearTimeout(state.searchTimer);
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

        if (root && !state.actionsBound) {
            root.addEventListener('click', (event) => {
                const actionEl = event && event.target && event.target.closest
                    ? event.target.closest('[data-permissions-action]')
                    : null;
                if (!actionEl || !root.contains(actionEl)) return;

                const action = String(actionEl.dataset.permissionsAction || '').trim();
                if (!action) return;

                switch (action) {
                    case 'init-permissions-settings':
                        window.initPermissionsSettings(String(actionEl.dataset.force || '').toLowerCase() === 'true');
                        break;
                    case 'switch-permissions-category':
                        window.switchPermissionsCategory(actionEl.dataset.permissionsCategory || '', actionEl);
                        break;
                    case 'expand-all-permission-groups':
                        window.expandAllPermissionGroups();
                        break;
                    case 'collapse-all-permission-groups':
                        window.collapseAllPermissionGroups();
                        break;
                    case 'reset-permission-filters':
                        window.resetPermissionFilters();
                        break;
                    case 'save-permissions-matrix':
                        window.savePermissionsMatrix();
                        break;
                    case 'toggle-permission-group':
                        window.togglePermissionGroup(actionEl.dataset.pageKey || '');
                        break;
                    case 'toggle-permission-section':
                        window.togglePermissionSection(actionEl.dataset.sectionKey || '');
                        break;
                    default:
                        break;
                }
            });

            root.addEventListener('change', (event) => {
                const actionEl = event && event.target && event.target.closest
                    ? event.target.closest('[data-permissions-action]')
                    : null;
                if (!actionEl || !root.contains(actionEl)) return;

                const action = String(actionEl.dataset.permissionsAction || '').trim();
                if (!action) return;

                switch (action) {
                    case 'toggle-permission-cell':
                        window.togglePermissionCell(
                            actionEl.dataset.roleKey || '',
                            decodeURIComponent(String(actionEl.dataset.permission || '')),
                            Boolean(actionEl.checked),
                        );
                        break;
                    case 'toggle-permission-group-role':
                        window.togglePermissionGroupRole(
                            actionEl.dataset.scopeKey || '',
                            actionEl.dataset.roleKey || '',
                            Boolean(actionEl.checked),
                        );
                        break;
                    case 'toggle-permission-section-role':
                        window.togglePermissionSectionRole(
                            actionEl.dataset.scopeKey || '',
                            actionEl.dataset.roleKey || '',
                            Boolean(actionEl.checked),
                        );
                        break;
                    default:
                        break;
                }
            });
            state.actionsBound = true;
        }

        state.toolbarBound = true;
    }

    async function load(force = false) {
        bindToolbar();
        cleanupMatrixBulkUi();
        renderCategoryTabs();

        if (state.initialized && !force) {
            renderGroupOptions();
            renderMatrix();
            return;
        }

        const body = document.getElementById('permissionsMatrixBody');
        if (body) {
            body.innerHTML = '<tr><td class="center-text muted" colspan="6" style="padding: 36px;">در حال بارگذاری ماتریس دسترسی...</td></tr>';
        }

        const payload = await request(matrixUrl());
        state.activeCategory = normalizeCategory(payload && payload.category);
        if (Array.isArray(payload && payload.categories) && payload.categories.length) {
            const normalized = payload.categories
                .map((item) => normalizeCategory(item))
                .filter((item, idx, arr) => arr.indexOf(item) === idx);
            state.categories = normalized.length ? normalized : KNOWN_CATEGORIES.slice();
        }
        state.roles = Array.isArray(payload.roles) ? payload.roles : [];
        state.permissions = Array.isArray(payload.permissions) ? payload.permissions : [];
        state.matrix = payload.matrix || {};
        state.readOnly = Boolean(payload && payload.read_only);
        state.collapsedSections = new Set();
        state.collapsedGroups = new Set();

        ensureMatrixDefaults();
        state.initialized = true;
        renderCategoryTabs();
        renderGroupOptions();
        renderMatrix();
    }

    window.togglePermissionCell = function togglePermissionCell(role, permission, checked) {
        if (state.readOnly) return;
        const roleKey = normalizeRole(role);        if (!state.matrix[roleKey]) state.matrix[roleKey] = {};
        state.matrix[roleKey][permission] = Boolean(checked);
        renderMatrix();
    };

    window.togglePermissionSectionRole = function togglePermissionSectionRole(encodedSectionKey, role, checked) {
        if (state.readOnly) return;
        const sectionKey = decodeURIComponent(String(encodedSectionKey || ''));
        const roleKey = normalizeRole(role);
        if (!sectionKey) return;
        const perms = state.renderedSections[sectionKey] || [];
        if (!perms.length) return;
        if (!state.matrix[roleKey]) state.matrix[roleKey] = {};
        perms.forEach((permission) => {
            state.matrix[roleKey][permission] = Boolean(checked);
        });
        renderMatrix();
    };

    window.togglePermissionGroupRole = function togglePermissionGroupRole(encodedPageKey, role, checked) {
        if (state.readOnly) return;
        const pageKey = decodeURIComponent(String(encodedPageKey || ''));
        const roleKey = normalizeRole(role);
        if (!pageKey) return;
        const perms = state.renderedPages[pageKey] || [];
        if (!perms.length) return;
        if (!state.matrix[roleKey]) state.matrix[roleKey] = {};
        perms.forEach((permission) => {
            state.matrix[roleKey][permission] = Boolean(checked);
        });
        renderMatrix();
    };

    window.togglePermissionSection = function togglePermissionSection(encodedSectionKey) {
        const sectionKey = decodeURIComponent(String(encodedSectionKey || ''));
        if (!sectionKey) return;
        if (state.collapsedSections.has(sectionKey)) state.collapsedSections.delete(sectionKey);
        else state.collapsedSections.add(sectionKey);
        renderMatrix();
    };

    window.togglePermissionGroup = function togglePermissionGroup(encodedPageKey) {
        const pageKey = decodeURIComponent(String(encodedPageKey || ''));
        if (!pageKey) return;
        if (state.collapsedGroups.has(pageKey)) state.collapsedGroups.delete(pageKey);
        else state.collapsedGroups.add(pageKey);
        renderMatrix();
    };

    window.expandAllPermissionGroups = function expandAllPermissionGroups() {
        state.collapsedSections.clear();
        state.collapsedGroups.clear();
        renderMatrix();
    };

    window.collapseAllPermissionGroups = function collapseAllPermissionGroups() {
        const tree = buildPermissionTree(getFilteredPermissions());
        state.collapsedSections = new Set(tree.map((section) => section.key));
        state.collapsedGroups = new Set(tree.flatMap((section) => section.pages.map((page) => page.key)));
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
        if (state.readOnly) {
            notify('warning', 'این دسته فقط خواندنی است.');
            return;
        }
        try {
            ensureMatrixDefaults();
            await request(matrixUrl(), {
                method: 'POST',
                body: JSON.stringify({ matrix: state.matrix }),
            });
            notify('success', `ماتریس سطح دسترسی ${categoryLabel(state.activeCategory)} ذخیره شد.`);
            await load(true);
        } catch (error) {
            notify('error', error.message || 'ذخیره ماتریس ناموفق بود.');
        }
    };

    window.switchPermissionsCategory = async function switchPermissionsCategory(category, btnEl) {
        const target = normalizeCategory(category);
        if (target === state.activeCategory && state.initialized) {
            renderCategoryTabs(btnEl || null);
            return;
        }
        state.activeCategory = target;
        state.initialized = false;
        renderCategoryTabs(btnEl || null);
        await window.initPermissionsSettings(true);
    };

    window.initPermissionsSettings = async function initPermissionsSettings(force = false) {
        try {
            await load(force);
        } catch (error) {
            notify('error', error.message || 'بارگذاری ماتریس دسترسی ناموفق بود.');
        }
    };
})();



