// @ts-nocheck
(() => {
    const LEGACY_ENDPOINT = "/api/v1/settings/site-log-catalogs";
    const ACTIVITY_ENDPOINT = "/api/v1/settings/site-log-activity-catalog";
    const PMS_ENDPOINT = "/api/v1/settings/site-log-pms";

    const CATALOG_SPECS = [
        {
            key: "role",
            title: "فهرست نقش‌ها (نفرات)",
            navTitle: "نقش‌ها و نفرات",
            subtitle: "نمونه: جوشکار، لوله‌کش، برقکار",
            icon: "badge",
            empty: "هنوز آیتمی برای نقش‌های نفرات ثبت نشده است.",
        },
        {
            key: "work_section",
            title: "فهرست واحد / بخش کاری نفرات",
            navTitle: "واحد کاری نفرات",
            subtitle: "نمونه: دفتر فنی، اجرا / عملیات، انبار و لجستیک",
            icon: "groups",
            empty: "هنوز آیتمی برای واحد / بخش کاری نفرات ثبت نشده است.",
        },
        {
            key: "equipment",
            title: "فهرست تجهیزات",
            navTitle: "تجهیزات",
            subtitle: "نمونه: جرثقیل، لودر، بیل‌مکانیکی",
            icon: "construction",
            empty: "هنوز آیتمی برای تجهیزات ثبت نشده است.",
        },
        {
            key: "material",
            title: "فهرست مصالح",
            navTitle: "مصالح",
            subtitle: "نمونه: سیمان، میلگرد، شن و ماسه",
            icon: "inventory_2",
            empty: "هنوز آیتمی برای مصالح ثبت نشده است.",
        },
        {
            key: "equipment_status",
            title: "فهرست وضعیت تجهیزات",
            navTitle: "وضعیت تجهیزات",
            subtitle: "نمونه: فعال، بیکار، در تعمیر",
            icon: "fact_check",
            empty: "هنوز آیتمی برای وضعیت تجهیزات ثبت نشده است.",
        },
        {
            key: "attachment_type",
            title: "فهرست نوع پیوست گزارش",
            navTitle: "نوع پیوست گزارش",
            subtitle: "نمونه: عکس، فرم بازرسی، نتیجه تست",
            icon: "attach_file",
            empty: "هنوز آیتمی برای نوع پیوست گزارش ثبت نشده است.",
        },
        {
            key: "issue_type",
            title: "فهرست نوع موانع",
            navTitle: "نوع موانع",
            subtitle: "نمونه: کمبود مصالح، محدودیت دسترسی، مشکل تجهیزات",
            icon: "report_problem",
            empty: "هنوز آیتمی برای نوع موانع ثبت نشده است.",
        },
        {
            key: "shift",
            title: "شیفت‌های گزارش",
            navTitle: "شیفت‌های کاری",
            subtitle: "نمونه: DAY / روز، NIGHT / شب",
            icon: "schedule",
            empty: "هنوز آیتمی برای شیفت‌های گزارش ثبت نشده است.",
        },
        {
            key: "weather",
            title: "وضعیت‌های جوی",
            navTitle: "وضعیت‌های جوی",
            subtitle: "نمونه: CLEAR / صاف، RAIN / بارانی",
            icon: "wb_sunny",
            empty: "هنوز آیتمی برای وضعیت‌های جوی ثبت نشده است.",
        },
    ];

    const ACTIVITY_SUBTABS = [
        { key: "activities", title: "فعالیت‌ها", icon: "list_alt" },
        { key: "pms-templates", title: "PMS Templateها", icon: "account_tree" },
        { key: "excel-mapping", title: "Excel و Mapping", icon: "ios_share" },
    ];

    const state = {
        bound: false,
        loading: false,
        catalogs: {
            role: [],
            work_section: [],
            equipment: [],
            material: [],
            equipment_status: [],
            attachment_type: [],
            issue_type: [],
            shift: [],
            weather: [],
        },
        activity: {
            items: [],
            projects: [],
            organizations: [],
            pmsTemplates: [],
            pmsSummary: { total: 0, mapped: 0, none: 0, stale: 0 },
            selectedIds: new Set(),
            activeSubTab: "activities",
            searchText: "",
            statusFilter: "all",
            editingActivity: null,
            editingPmsTemplate: null,
            filters: {
                project_code: "",
                organization_id: "",
                organization_contract_id: "",
                pms_status: "",
                pms_template_id: "",
                default_unit: "",
                default_location: "",
                reference_search: "",
            },
        },
        contractor: {
            activeMainTab: "report-settings",
            activeCatalog: "role",
            searchText: "",
            statusFilter: "all",
            editingItem: null,
            bulkCatalog: null,
        },
    };

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function norm(value) {
        return String(value == null ? "" : value).trim();
    }

    function upper(value) {
        return norm(value).toUpperCase();
    }

    function asArray(value) {
        return Array.isArray(value) ? value : [];
    }

    function canUpdateSettings() {
        if (window.authManager?.user?.is_system_admin === true) return true;
        if (typeof window.hasCapability === "function") {
            return Boolean(window.hasCapability("settings:update"));
        }
        return true;
    }

    function reportCatalogKeys() {
        return CATALOG_SPECS.map((item) => item.key);
    }

    function normalizeReportCatalog(value) {
        const key = String(value || "").trim();
        return reportCatalogKeys().includes(key) ? key : CATALOG_SPECS[0].key;
    }

    function activeReportCatalog() {
        state.contractor.activeCatalog = normalizeReportCatalog(state.contractor.activeCatalog);
        return state.contractor.activeCatalog;
    }

    function activeReportSpec() {
        return specFor(activeReportCatalog()) || CATALOG_SPECS[0];
    }

    function canBulkAddCatalog(catalogType) {
        return ["equipment", "material"].includes(String(catalogType || "").trim());
    }

    function statusFilterValue() {
        const value = String(state.contractor.statusFilter || "all").trim().toLowerCase();
        return ["all", "active", "inactive"].includes(value) ? value : "all";
    }

    function toQuery(params = {}) {
        const searchParams = new URLSearchParams();
        Object.entries(params).forEach(([key, rawValue]) => {
            if (rawValue == null) return;
            const value = norm(rawValue);
            if (!value) return;
            searchParams.set(key, value);
        });
        const encoded = searchParams.toString();
        return encoded ? `?${encoded}` : "";
    }

    function notify(type, message) {
        if (window.UI && typeof window.UI[type] === "function") {
            window.UI[type](message);
            return;
        }
        if (typeof window.showToast === "function") {
            const tone = type === "error" ? "error" : type === "warning" ? "warning" : "success";
            window.showToast(message, tone);
            return;
        }
        if (type === "error") {
            console.error(message);
            return;
        }
        console.log(message);
    }

    async function request(url, options = {}) {
        const requester = typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : window.fetch.bind(window);
        const headers = new Headers(options.headers || {});
        if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
            headers.set("Content-Type", "application/json");
        }
        const response = await requester(url, { ...options, headers });
        if (!response.ok) {
            let message = `Request failed (${response.status})`;
            try {
                const payload = await response.clone().json();
                message = payload.detail || payload.message || message;
            } catch (_) {}
            throw new Error(message);
        }
        return response.json();
    }

    function getContractorRoot() {
        return document.getElementById("contractorSiteLogCatalogsRoot");
    }

    function getActivityRoot() {
        return document.getElementById("consultantSiteLogActivityCatalogRoot");
    }

    function specFor(catalogType) {
        return CATALOG_SPECS.find((item) => item.key === String(catalogType || "").trim()) || null;
    }

    function rowsFor(catalogType) {
        return asArray(state.catalogs[String(catalogType || "").trim()]);
    }

    function filteredRowsFor(catalogType) {
        const query = norm(state.contractor.searchText).toLowerCase();
        const status = statusFilterValue();
        return rowsFor(catalogType).filter((row) => {
            const isActive = Boolean(row.is_active);
            if (status === "active" && !isActive) return false;
            if (status === "inactive" && isActive) return false;
            if (!query) return true;
            const haystack = [row.code, row.label, row.title, row.name]
                .map((value) => norm(value).toLowerCase())
                .join(" ");
            return haystack.includes(query);
        });
    }

    function nextSortOrder(catalogType) {
        const rows = rowsFor(catalogType);
        if (!rows.length) return 10;
        return rows.reduce((max, row) => Math.max(max, Number(row.sort_order || 0)), 0) + 10;
    }

    function activityNextSortOrder() {
        const rows = asArray(state.activity.items);
        if (!rows.length) return 10;
        return rows.reduce((max, row) => Math.max(max, Number(row.sort_order || 0)), 0) + 10;
    }

    function renderStatus(isActive) {
        const active = Boolean(isActive);
        return `<span class="contractor-settings-status ${active ? "is-active" : "is-inactive"}">${active ? "فعال" : "غیرفعال"}</span>`;
    }

    function organizations() {
        return asArray(state.activity.organizations);
    }

    function projects() {
        return asArray(state.activity.projects);
    }

    function pmsTemplates() {
        return asArray(state.activity.pmsTemplates);
    }

    function renderPmsTemplateOptions(current = "", placeholder = "همه Templateها") {
        const selected = String(current || "");
        return [`<option value="">${esc(placeholder)}</option>`]
            .concat(
                pmsTemplates().map((row) => {
                    const id = Number(row.id || 0);
                    if (id <= 0) return "";
                    const code = upper(row.code || "");
                    const title = norm(row.title || code);
                    const version = Number(row.version || 1);
                    return `<option value="${id}"${selected === String(id) ? " selected" : ""}>${esc(code)} - ${esc(title)} (v${version})</option>`;
                })
            )
            .join("");
    }

    function pmsTemplateById(templateId) {
        const target = Number(templateId || 0);
        if (target <= 0) return null;
        return pmsTemplates().find((row) => Number(row.id || 0) === target) || null;
    }

    function pmsSummaryFromRows(rows) {
        const fallback = { total: rows.length, mapped: 0, none: 0, stale: 0 };
        rows.forEach((row) => {
            const status = String(row.pms_status || "none");
            if (status === "stale") fallback.stale += 1;
            else if (status === "mapped") fallback.mapped += 1;
            else fallback.none += 1;
        });
        const summary = state.activity.pmsSummary || {};
        return {
            total: Number(summary.total ?? fallback.total),
            mapped: Number(summary.mapped ?? fallback.mapped),
            none: Number(summary.none ?? fallback.none),
            stale: Number(summary.stale ?? fallback.stale),
        };
    }

    function quickPmsButton(status, label, current) {
        const active = String(status || "") === String(current || "");
        return `<button type="button" class="btn ${active ? "btn-primary" : "btn-secondary"}" data-contractor-catalog-action="quick-pms-filter" data-pms-status="${esc(status)}">${esc(label)}</button>`;
    }

    function normalizeActivitySubTab(value) {
        const key = String(value || "").trim();
        return ACTIVITY_SUBTABS.some((item) => item.key === key) ? key : "activities";
    }

    function activeActivitySubTab() {
        state.activity.activeSubTab = normalizeActivitySubTab(state.activity.activeSubTab);
        return state.activity.activeSubTab;
    }

    function activityStatusFilterValue() {
        const value = String(state.activity.statusFilter || "all").trim().toLowerCase();
        return ["all", "active", "inactive"].includes(value) ? value : "all";
    }

    function filteredActivityRows() {
        const query = norm(state.activity.searchText).toLowerCase();
        const status = activityStatusFilterValue();
        return asArray(state.activity.items).filter((row) => {
            const isActive = Boolean(row.is_active);
            if (status === "active" && !isActive) return false;
            if (status === "inactive" && isActive) return false;
            if (!query) return true;
            const haystack = [
                row.activity_code,
                row.activity_title,
                row.organization_name,
                row.contract_subject,
                row.scope_label,
                row.default_unit,
                row.default_location,
                row.pms_template_code,
                row.pms_template_title,
            ]
                .map((value) => norm(value).toLowerCase())
                .join(" ");
            return haystack.includes(query);
        });
    }

    function activityStatusButton(status, label) {
        const active = activityStatusFilterValue() === status;
        return `
            <button
                type="button"
                class="contractor-catalog-filter-btn ${active ? "active" : ""}"
                data-contractor-catalog-action="set-activity-status-filter"
                data-status-filter="${esc(status)}"
            >
                ${esc(label)}
            </button>
        `;
    }

    function pmsStepWeightTotalFromRows(rows) {
        return asArray(rows).reduce((sum, row) => {
            if (row && row.is_active === false) return sum;
            return sum + Number(row?.weight_pct || 0);
        }, 0);
    }

    function parsePmsStepsText(value) {
        if (Array.isArray(value)) {
            return value.map((step, index) => ({
                step_code: upper(step.step_code || step.code || `STEP${index + 1}`),
                step_title: norm(step.step_title || step.title || step.step_code || `Step ${index + 1}`),
                weight_pct: Number(step.weight_pct || step.weight || 0),
                sort_order: Number(step.sort_order || (index + 1) * 10),
                is_active: step.is_active !== false && step.is_active !== "0",
            }));
        }
        return String(value || "")
            .split(/\r?\n/)
            .map((line, index) => {
                const parts = line.split("|").map((part) => norm(part));
                if (!parts[0] && !parts[1]) return null;
                return {
                    step_code: upper(parts[0] || `STEP${index + 1}`),
                    step_title: parts[1] || parts[0] || `Step ${index + 1}`,
                    weight_pct: Number(parts[2] || 0),
                    sort_order: (index + 1) * 10,
                    is_active: true,
                };
            })
            .filter(Boolean);
    }

    function pmsTemplateSteps(row) {
        return parsePmsStepsText(asArray(row?.steps).length ? row.steps : pmsStepsText(row || {}));
    }

    function invalidPmsTemplateCount() {
        return pmsTemplates().filter((row) => Boolean(row.is_active) && Number(row.weight_total || 0) !== 100).length;
    }

    function renderPmsStatus(row) {
        const status = String(row.pms_status || "none");
        const label = status === "stale" ? "قدیمی شده" : status === "mapped" ? "دارای PMS" : "بدون PMS";
        const className = status === "stale" ? "is-inactive" : status === "mapped" ? "is-active" : "";
        return `<span class="contractor-settings-status ${className}">${esc(label)}</span>`;
    }

    function contractsForOrganization(organizationId) {
        const targetId = Number(organizationId || 0);
        if (targetId <= 0) return [];
        const organization = organizations().find((item) => Number(item.id || 0) === targetId);
        return asArray(organization?.contracts);
    }

    function contractLabel(row) {
        const number = norm(row.contract_number || "");
        const subject = norm(row.subject || "");
        const blockName = norm(row.block_name || "");
        return [number, subject, blockName ? `بلوک ${blockName}` : ""].filter(Boolean).join(" | ");
    }

    function renderProjectOptions(current = "", placeholder = "همه پروژه‌ها") {
        const selected = norm(current);
        return [`<option value="">${esc(placeholder)}</option>`]
            .concat(
                projects().map((row) => {
                    const code = upper(row.code || "");
                    if (!code) return "";
                    const label = norm(row.name || code);
                    return `<option value="${esc(code)}"${selected === code ? " selected" : ""}>${esc(label)}</option>`;
                })
            )
            .join("");
    }

    function renderOrganizationOptions(current = "", placeholder = "همه سازمان‌ها") {
        const selected = String(current || "");
        return [`<option value="">${esc(placeholder)}</option>`]
            .concat(
                organizations().map((row) => {
                    const id = Number(row.id || 0);
                    if (id <= 0) return "";
                    return `<option value="${id}"${selected === String(id) ? " selected" : ""}>${esc(row.name || id)}</option>`;
                })
            )
            .join("");
    }

    function renderContractOptions(organizationId, current = "", placeholder = "همه قراردادها") {
        const selected = String(current || "");
        return [`<option value="">${esc(placeholder)}</option>`]
            .concat(
                contractsForOrganization(organizationId).map((row) => {
                    const id = Number(row.id || 0);
                    if (id <= 0) return "";
                    return `<option value="${id}"${selected === String(id) ? " selected" : ""}>${esc(contractLabel(row) || row.subject || row.contract_number || id)}</option>`;
                })
            )
            .join("");
    }

    function renderTableRows(catalogType, rows, emptyMessage) {
        if (!rows.length) {
            return `<tr><td colspan="5" class="center-text muted" style="padding: 18px;">${esc(emptyMessage)}</td></tr>`;
        }
        const canUpdate = canUpdateSettings();
        return rows
            .map((row) => {
                const id = Number(row.id || 0);
                const code = upper(row.code || "");
                const label = norm(row.label || "");
                const sortOrder = Number(row.sort_order || 0);
                const isActive = Boolean(row.is_active);
                return `
                    <tr>
                        <td style="font-family: monospace;">${esc(code)}</td>
                        <td>${esc(label)}</td>
                        <td>${sortOrder}</td>
                        <td>${renderStatus(isActive)}</td>
                        <td>
                            ${canUpdate ? `
                                <div class="module-crud-actions">
                                    <button
                                        type="button"
                                        class="btn-archive-icon"
                                        data-contractor-catalog-action="edit-item"
                                        data-catalog-type="${esc(catalogType)}"
                                        data-item-id="${id}"
                                        data-item-code="${esc(code)}"
                                        data-item-label="${esc(label)}"
                                        data-item-sort-order="${sortOrder}"
                                        data-item-is-active="${isActive ? "1" : "0"}"
                                        title="ویرایش"
                                    >
                                        <span class="material-icons-round">edit</span>
                                    </button>
                                    <button
                                        type="button"
                                        class="btn-archive-icon"
                                        data-contractor-catalog-action="toggle-item-active"
                                        data-catalog-type="${esc(catalogType)}"
                                        data-item-id="${id}"
                                        data-item-code="${esc(code)}"
                                        data-item-label="${esc(label)}"
                                        data-item-sort-order="${sortOrder}"
                                        data-item-is-active="${isActive ? "1" : "0"}"
                                        title="${isActive ? "غیرفعال‌سازی" : "فعال‌سازی"}"
                                    >
                                        <span class="material-icons-round">${isActive ? "visibility_off" : "restart_alt"}</span>
                                    </button>
                                </div>
                            ` : `<span class="muted">فقط مشاهده</span>`}
                        </td>
                    </tr>
                `;
            })
            .join("");
    }

    function renderCatalogCard(spec) {
        const rows = rowsFor(spec.key);
        const activeCount = rows.filter((row) => Boolean(row.is_active)).length;
        return `
            <section class="general-settings-card contractor-settings-card" data-catalog-type="${esc(spec.key)}">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title">
                            <span class="material-icons-round">${esc(spec.icon)}</span>
                            ${esc(spec.title)}
                        </h3>
                        <p class="contractor-settings-card-subtitle">${esc(spec.subtitle)}</p>
                    </div>
                    <div class="contractor-settings-card-meta">
                        <span class="doc-muted-pill">${rows.length} آیتم</span>
                        <span class="doc-muted-pill">${activeCount} فعال</span>
                        <span class="doc-muted-pill">دارای PMS: ${pmsSummary.mapped}</span>
                        <span class="doc-muted-pill">بدون PMS: ${pmsSummary.none}</span>
                        <span class="doc-muted-pill">قدیمی: ${pmsSummary.stale}</span>
                    </div>
                </div>

                    <div class="module-crud-form-field">
                        <label>PMS</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="pms_status">
                            <option value=""${!filterPmsStatus ? " selected" : ""}>همه فعالیت‌ها</option>
                            <option value="mapped"${filterPmsStatus === "mapped" ? " selected" : ""}>دارای PMS</option>
                            <option value="none"${filterPmsStatus === "none" ? " selected" : ""}>فقط بدون PMS</option>
                            <option value="stale"${filterPmsStatus === "stale" ? " selected" : ""}>قدیمی شده</option>
                        </select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>Template خاص</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="pms_template_id">${renderPmsTemplateOptions(filterPmsTemplate)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>واحد</label>
                        <input class="module-crud-input" data-contractor-catalog-filter="default_unit" value="${esc(filterUnit)}" placeholder="m3 / kg">
                    </div>
                    <div class="module-crud-form-field">
                        <label>محل پیش‌فرض</label>
                        <input class="module-crud-input" data-contractor-catalog-filter="default_location" value="${esc(filterLocation)}" placeholder="Block A">
                    </div>
                    <div class="module-crud-form-field">
                        <label>مرجع / سازمان</label>
                        <input class="module-crud-input" data-contractor-catalog-filter="reference_search" value="${esc(filterReference)}" placeholder="سازمان یا قرارداد">
                    </div>
                </div>

                <div class="contractor-settings-activity-import">
                    <div>
                        <strong>فیلتر سریع PMS</strong>
                        <span>برای پیدا کردن Activityهای ناقص، «بدون PMS» را بزنید.</span>
                    </div>
                    <div class="contractor-settings-activity-import-actions">
                        ${quickPmsButton("", "همه", filterPmsStatus)}
                        ${quickPmsButton("mapped", "دارای PMS", filterPmsStatus)}
                        ${quickPmsButton("none", "بدون PMS", filterPmsStatus)}
                        ${quickPmsButton("stale", "قدیمی شده", filterPmsStatus)}
                    </div>
                </div>

                <div class="contractor-settings-activity-import">
                    <div>
                        <strong>عملیات گروهی PMS</strong>
                        <span>${selectedCount} Activity انتخاب شده است.</span>
                    </div>
                    <div class="contractor-settings-activity-import-actions">
                        <select class="module-crud-select" data-pms-bulk-template>${renderPmsTemplateOptions("", "انتخاب PMS Template")}</select>
                        <label class="contractor-settings-checkbox-wrap">
                            <input type="checkbox" data-pms-bulk-overwrite>
                            <span>Overwrite</span>
                        </label>
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="bulk-apply-pms">اعمال PMS Template</button>
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="quick-without-pms">فقط فعالیت‌های بدون PMS</button>
                    </div>
                </div>

                <div class="module-crud-table-wrap">
                    <table class="module-crud-table">
                        <thead>
                            <tr>
                                <th>کد</th>
                                <th>عنوان</th>
                                <th>ترتیب</th>
                                <th>وضعیت</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${renderTableRows(spec.key, rows, spec.empty)}
                        </tbody>
                    </table>
                </div>

                <div class="module-crud-form-wrap contractor-settings-inline-form">
                    <input type="hidden" data-catalog-form-field="id" value="">
                    <div class="contractor-settings-inline-form-head">
                        <div>
                            <strong data-catalog-form-title>افزودن آیتم جدید</strong>
                            <span>تغییرات این بخش مستقیماً در فرم گزارش کارگاهی استفاده می‌شود.</span>
                        </div>
                    </div>
                    <div class="module-crud-form-grid">
                        <div class="module-crud-form-field">
                            <label>کد</label>
                            <input class="module-crud-input" data-catalog-form-field="code" type="text" placeholder="مثلاً WELD">
                        </div>
                        <div class="module-crud-form-field">
                            <label>عنوان</label>
                            <input class="module-crud-input" data-catalog-form-field="label" type="text" placeholder="مثلاً جوشکار">
                        </div>
                        <div class="module-crud-form-field">
                            <label>ترتیب</label>
                            <input class="module-crud-input" data-catalog-form-field="sort_order" type="number" min="0" step="1" value="${nextSortOrder(spec.key)}">
                        </div>
                        <div class="module-crud-form-field contractor-settings-checkbox-field">
                            <label class="contractor-settings-checkbox-wrap">
                                <input data-catalog-form-field="is_active" type="checkbox" checked>
                                <span>فعال باشد</span>
                            </label>
                        </div>
                    </div>
                    <div class="module-crud-form-actions">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="reset-form" data-catalog-type="${esc(spec.key)}">لغو</button>
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="save-item" data-catalog-type="${esc(spec.key)}">ذخیره</button>
                    </div>
                </div>
            </section>
        `;
    }

    function renderCatalogCard(spec) {
        const rows = rowsFor(spec.key);
        const activeCount = rows.filter((row) => Boolean(row.is_active)).length;
        return `
            <section class="general-settings-card contractor-settings-card" data-catalog-type="${esc(spec.key)}">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title">
                            <span class="material-icons-round">${esc(spec.icon)}</span>
                            ${esc(spec.title)}
                        </h3>
                        <p class="contractor-settings-card-subtitle">${esc(spec.subtitle)}</p>
                    </div>
                    <div class="contractor-settings-card-meta">
                        <span class="doc-muted-pill">${rows.length} آیتم</span>
                        <span class="doc-muted-pill">${activeCount} فعال</span>
                    </div>
                </div>

                <div class="module-crud-table-wrap">
                    <table class="module-crud-table">
                        <thead>
                            <tr>
                                <th>کد</th>
                                <th>عنوان</th>
                                <th>ترتیب</th>
                                <th>وضعیت</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>${renderTableRows(spec.key, rows, spec.empty)}</tbody>
                    </table>
                </div>

                <div class="module-crud-form-wrap contractor-settings-inline-form">
                    <input type="hidden" data-catalog-form-field="id" value="">
                    <div class="contractor-settings-inline-form-head">
                        <div>
                            <strong data-catalog-form-title>افزودن آیتم جدید</strong>
                            <span>تغییرات این بخش مستقیم در فرم گزارش کارگاهی استفاده می‌شود.</span>
                        </div>
                    </div>
                    <div class="module-crud-form-grid">
                        <div class="module-crud-form-field">
                            <label>کد</label>
                            <input class="module-crud-input" data-catalog-form-field="code" type="text">
                        </div>
                        <div class="module-crud-form-field">
                            <label>عنوان</label>
                            <input class="module-crud-input" data-catalog-form-field="label" type="text">
                        </div>
                        <div class="module-crud-form-field">
                            <label>ترتیب</label>
                            <input class="module-crud-input" data-catalog-form-field="sort_order" type="number" min="0" step="1" value="${nextSortOrder(spec.key)}">
                        </div>
                        <div class="module-crud-form-field contractor-settings-checkbox-field">
                            <label class="contractor-settings-checkbox-wrap">
                                <input data-catalog-form-field="is_active" type="checkbox" checked>
                                <span>فعال باشد</span>
                            </label>
                        </div>
                    </div>
                    <div class="module-crud-form-actions">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="reset-form" data-catalog-type="${esc(spec.key)}">لغو</button>
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="save-item" data-catalog-type="${esc(spec.key)}">ذخیره</button>
                    </div>
                </div>
            </section>
        `;
    }

    function renderActivityRows(rows) {
        if (!rows.length) {
            return `<tr><td colspan="9" class="center-text muted" style="padding: 18px;">هنوز آیتمی برای فعالیت‌های اجرایی ثبت نشده است.</td></tr>`;
        }
        return rows
            .map((row) => {
                const id = Number(row.id || 0);
                const isActive = Boolean(row.is_active);
                const projectCode = upper(row.project_code || "");
                const organizationId = Number(row.organization_id || 0);
                const contractId = Number(row.organization_contract_id || 0);
                const reference = norm(row.organization_name || row.contract_subject || projectCode || "");
                return `
                    <tr>
                        <td style="font-family: monospace;">${esc(row.activity_code || "-")}</td>
                        <td>${esc(row.activity_title || "-")}</td>
                        <td>${esc(row.default_location || "-")}</td>
                        <td>${esc(row.default_unit || "-")}</td>
                        <td>${esc(row.scope_label || "-")}</td>
                        <td>${esc(reference || "-")}</td>
                        <td>${Number(row.sort_order || 0)}</td>
                        <td>${renderStatus(isActive)}</td>
                        <td>
                            <div class="module-crud-actions">
                                <button
                                    type="button"
                                    class="btn-archive-icon"
                                    data-contractor-catalog-action="edit-activity"
                                    data-item-id="${id}"
                                    data-project-code="${esc(projectCode)}"
                                    data-organization-id="${organizationId > 0 ? organizationId : ""}"
                                    data-organization-contract-id="${contractId > 0 ? contractId : ""}"
                                    data-activity-code="${esc(row.activity_code || "")}"
                                    data-activity-title="${esc(row.activity_title || "")}"
                                    data-default-location="${esc(row.default_location || "")}"
                                    data-default-unit="${esc(row.default_unit || "")}"
                                    data-sort-order="${Number(row.sort_order || 0)}"
                                    data-item-is-active="${isActive ? "1" : "0"}"
                                >
                                    ویرایش
                                </button>
                                <button
                                    type="button"
                                    class="btn-archive-icon"
                                    data-contractor-catalog-action="delete-activity"
                                    data-item-id="${id}"
                                    data-item-label="${esc(row.activity_title || row.activity_code || id)}"
                                >
                                    حذف
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            })
            .join("");
    }

    function renderActivityRows(rows) {
        if (!rows.length) {
            return `<tr><td colspan="14" class="center-text muted" style="padding: 18px;">هنوز آیتمی برای فعالیت‌های اجرایی ثبت نشده است.</td></tr>`;
        }
        return rows
            .map((row) => {
                const id = Number(row.id || 0);
                const isActive = Boolean(row.is_active);
                const projectCode = upper(row.project_code || "");
                const organizationId = Number(row.organization_id || 0);
                const contractId = Number(row.organization_contract_id || 0);
                const reference = norm(row.organization_name || row.contract_subject || projectCode || "");
                const pmsStatus = String(row.pms_status || "none");
                const selected = state.activity.selectedIds.has(id);
                const pmsTemplate = norm(row.pms_template_title || row.pms_template_code || "");
                const pmsVersion = row.pms_snapshot_version ? `v${Number(row.pms_snapshot_version || 0)}` : "-";
                return `
                    <tr>
                        <td><input type="checkbox" data-activity-row-select="${id}"${selected ? " checked" : ""}></td>
                        <td style="font-family: monospace;">${esc(row.activity_code || "-")}</td>
                        <td>${esc(row.activity_title || "-")}</td>
                        <td>${esc(row.default_location || "-")}</td>
                        <td>${esc(row.default_unit || "-")}</td>
                        <td>${esc(row.scope_label || "-")}</td>
                        <td>${esc(reference || "-")}</td>
                        <td>${esc(pmsTemplate || "-")}</td>
                        <td>${renderPmsStatus(row)}</td>
                        <td>${esc(pmsVersion)}</td>
                        <td>
                            <div class="module-crud-actions">
                                <button type="button" class="btn-archive-icon" data-contractor-catalog-action="pms-activity" data-item-id="${id}">PMS</button>
                                ${pmsStatus !== "none" ? `<button type="button" class="btn-archive-icon" data-contractor-catalog-action="delete-pms-activity" data-item-id="${id}">حذف PMS</button>` : ""}
                                ${pmsStatus === "stale" ? `<button type="button" class="btn-archive-icon" data-contractor-catalog-action="reapply-pms-activity" data-item-id="${id}">Reapply</button>` : ""}
                            </div>
                        </td>
                        <td>${Number(row.sort_order || 0)}</td>
                        <td>${renderStatus(isActive)}</td>
                        <td>
                            <div class="module-crud-actions">
                                <button
                                    type="button"
                                    class="btn-archive-icon"
                                    data-contractor-catalog-action="edit-activity"
                                    data-item-id="${id}"
                                    data-project-code="${esc(projectCode)}"
                                    data-organization-id="${organizationId > 0 ? organizationId : ""}"
                                    data-organization-contract-id="${contractId > 0 ? contractId : ""}"
                                    data-activity-code="${esc(row.activity_code || "")}"
                                    data-activity-title="${esc(row.activity_title || "")}"
                                    data-default-location="${esc(row.default_location || "")}"
                                    data-default-unit="${esc(row.default_unit || "")}"
                                    data-sort-order="${Number(row.sort_order || 0)}"
                                    data-item-is-active="${isActive ? "1" : "0"}"
                                >ویرایش</button>
                                <button
                                    type="button"
                                    class="btn-archive-icon"
                                    data-contractor-catalog-action="delete-activity"
                                    data-item-id="${id}"
                                    data-item-label="${esc(row.activity_title || row.activity_code || id)}"
                                >حذف</button>
                            </div>
                        </td>
                    </tr>
                `;
            })
            .join("");
    }

    function renderActivityCard() {
        const rows = asArray(state.activity.items);
        const activeCount = rows.filter((row) => Boolean(row.is_active)).length;
        const filterProject = norm(state.activity.filters.project_code);
        const filterOrganization = String(state.activity.filters.organization_id || "");
        const filterContract = String(state.activity.filters.organization_contract_id || "");
        const filterPmsStatus = String(state.activity.filters.pms_status || "");
        const filterPmsTemplate = String(state.activity.filters.pms_template_id || "");
        const filterUnit = norm(state.activity.filters.default_unit || "");
        const filterLocation = norm(state.activity.filters.default_location || "");
        const filterReference = norm(state.activity.filters.reference_search || "");
        const selectedCount = state.activity.selectedIds.size;
        const selectedOrganization = organizations().find((row) => String(row.id || "") === filterOrganization);
        const selectedContract = contractsForOrganization(filterOrganization).find((row) => String(row.id || "") === filterContract);
        const importScopeHint = filterProject
            ? [
                  `پروژه ${filterProject}`,
                  selectedOrganization ? `سازمان ${selectedOrganization.name || filterOrganization}` : "سطح عمومی پروژه",
                  selectedContract ? `قرارداد ${contractLabel(selectedContract) || filterContract}` : "",
              ]
                  .filter(Boolean)
                  .join(" / ")
            : "برای ایمپورت، ابتدا فیلتر پروژه را انتخاب کنید.";
        return `
            <section class="general-settings-card contractor-settings-card contractor-settings-card-wide" data-catalog-type="activity">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title">
                            <span class="material-icons-round">list_alt</span>
                            فعالیت‌های اجرایی
                        </h3>
                        <p class="contractor-settings-card-subtitle">کاتالوگ مدیریتی برای پیش‌فیلد کردن جدول فعالیت‌های گزارش کارگاهی.</p>
                    </div>
                    <div class="contractor-settings-card-meta">
                        <span class="doc-muted-pill">${rows.length} آیتم</span>
                        <span class="doc-muted-pill">${activeCount} فعال</span>
                    </div>
                </div>

                <div class="contractor-settings-activity-import">
                    <div>
                        <strong>ایمپورت گروهی از Excel</strong>
                        <span>ستون‌های قابل قبول: کد فعالیت، عنوان فعالیت، محل پیش‌فرض، واحد، ترتیب، وضعیت. دامنه ایمپورت از فیلترهای همین بخش گرفته می‌شود.</span>
                        <small>${esc(importScopeHint)}</small>
                    </div>
                    <div class="contractor-settings-activity-import-actions">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="download-activity-template">دانلود تمپلت Excel</button>
                        <input class="module-crud-input" data-activity-import-file type="file" accept=".xlsx">
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="import-activity-excel">ایمپورت فعالیت‌ها</button>
                    </div>
                </div>

                <div class="contractor-settings-activity-import">
                    <div>
                        <strong>PMS Mapping</strong>
                        <span>برای اتصال Activity به PMS Template از Excel یا عملیات گروهی استفاده کنید.</span>
                    </div>
                    <div class="contractor-settings-activity-import-actions">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="download-pms-mapping-template">Template PMS</button>
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="export-pms-mapping">Export PMS</button>
                        <input class="module-crud-input" data-pms-mapping-import-file type="file" accept=".xlsx">
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="import-pms-mapping">Import PMS</button>
                    </div>
                </div>

                <div class="contractor-settings-activity-filters">
                    <div class="module-crud-form-field">
                        <label>فیلتر پروژه</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="project_code">${renderProjectOptions(filterProject)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>فیلتر سازمان</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="organization_id">${renderOrganizationOptions(filterOrganization)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>فیلتر قرارداد</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="organization_contract_id">${renderContractOptions(filterOrganization, filterContract)}</select>
                    </div>
                </div>

                <div class="module-crud-table-wrap">
                    <table class="module-crud-table">
                        <thead>
                            <tr>
                                <th>کد فعالیت</th>
                                <th>عنوان فعالیت</th>
                                <th>محل پیش‌فرض</th>
                                <th>واحد</th>
                                <th>دامنه</th>
                                <th>مرجع</th>
                                <th>ترتیب</th>
                                <th>وضعیت</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>${renderActivityRows(rows)}</tbody>
                    </table>
                </div>

                <div class="module-crud-form-wrap contractor-settings-inline-form contractor-settings-activity-form">
                    <input type="hidden" data-activity-form-field="id" value="">
                    <div class="contractor-settings-inline-form-head">
                        <div>
                            <strong data-activity-form-title>افزودن فعالیت اجرایی</strong>
                            <span>با انتخاب پروژه، سازمان و در صورت نیاز قرارداد، این فعالیت در همان دامنه در فرم گزارش کارگاهی پیشنهاد می‌شود.</span>
                        </div>
                    </div>
                    <div class="module-crud-form-grid">
                        <div class="module-crud-form-field">
                            <label>پروژه</label>
                            <select class="module-crud-select" data-activity-form-field="project_code">${renderProjectOptions("", "انتخاب پروژه")}</select>
                        </div>
                        <div class="module-crud-form-field">
                            <label>سازمان</label>
                            <select class="module-crud-select" data-activity-form-field="organization_id">${renderOrganizationOptions("", "پروژه‌محور / همه سازمان‌ها")}</select>
                        </div>
                        <div class="module-crud-form-field">
                            <label>قرارداد</label>
                            <select class="module-crud-select" data-activity-form-field="organization_contract_id">${renderContractOptions("", "", "همه قراردادهای سازمان")}</select>
                        </div>
                        <div class="module-crud-form-field">
                            <label>کد فعالیت</label>
                            <input class="module-crud-input" data-activity-form-field="activity_code" type="text" placeholder="مثلاً CV-101">
                        </div>
                        <div class="module-crud-form-field">
                            <label>عنوان فعالیت</label>
                            <input class="module-crud-input" data-activity-form-field="activity_title" type="text" placeholder="مثلاً آرماتوربندی فونداسیون">
                        </div>
                        <div class="module-crud-form-field">
                            <label>محل پیش‌فرض</label>
                            <input class="module-crud-input" data-activity-form-field="default_location" type="text" placeholder="مثلاً بلاک B">
                        </div>
                        <div class="module-crud-form-field">
                            <label>واحد پیش‌فرض</label>
                            <input class="module-crud-input" data-activity-form-field="default_unit" type="text" placeholder="مثلاً تن">
                        </div>
                        <div class="module-crud-form-field">
                            <label>ترتیب</label>
                            <input class="module-crud-input" data-activity-form-field="sort_order" type="number" min="0" step="1" value="${activityNextSortOrder()}">
                        </div>
                        <div class="module-crud-form-field contractor-settings-checkbox-field">
                            <label class="contractor-settings-checkbox-wrap">
                                <input data-activity-form-field="is_active" type="checkbox" checked>
                                <span>فعال باشد</span>
                            </label>
                        </div>
                    </div>
                    <div class="module-crud-form-actions">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="reset-activity-form">لغو</button>
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="save-activity">ذخیره</button>
                    </div>
                </div>
            </section>
        `;
    }

    function renderActivityCard() {
        const rows = asArray(state.activity.items);
        const activeCount = rows.filter((row) => Boolean(row.is_active)).length;
        const filterProject = norm(state.activity.filters.project_code);
        const filterOrganization = String(state.activity.filters.organization_id || "");
        const filterContract = String(state.activity.filters.organization_contract_id || "");
        const filterPmsStatus = String(state.activity.filters.pms_status || "");
        const filterPmsTemplate = String(state.activity.filters.pms_template_id || "");
        const filterUnit = norm(state.activity.filters.default_unit || "");
        const filterLocation = norm(state.activity.filters.default_location || "");
        const filterReference = norm(state.activity.filters.reference_search || "");
        const selectedOrganization = organizations().find((row) => String(row.id || "") === filterOrganization);
        const selectedContract = contractsForOrganization(filterOrganization).find((row) => String(row.id || "") === filterContract);
        const selectedCount = state.activity.selectedIds.size;
        const pmsSummary = pmsSummaryFromRows(rows);
        const importScopeHint = filterProject
            ? [
                  `پروژه ${filterProject}`,
                  selectedOrganization ? `سازمان ${selectedOrganization.name || filterOrganization}` : "سطح عمومی پروژه",
                  selectedContract ? `قرارداد ${contractLabel(selectedContract) || filterContract}` : "",
              ]
                  .filter(Boolean)
                  .join(" / ")
            : "برای ایمپورت، ابتدا فیلتر پروژه را انتخاب کنید.";
        return `
            <section class="general-settings-card contractor-settings-card contractor-settings-card-wide" data-catalog-type="activity">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title"><span class="material-icons-round">list_alt</span>فعالیت‌های اجرایی</h3>
                        <p class="contractor-settings-card-subtitle">کاتالوگ مدیریتی فعالیت‌ها و اتصال کنترل‌شده PMS Template.</p>
                    </div>
                    <div class="contractor-settings-card-meta">
                        <span class="doc-muted-pill">${rows.length} آیتم</span>
                        <span class="doc-muted-pill">${activeCount} فعال</span>
                    </div>
                </div>

                <div class="contractor-settings-activity-import">
                    <div>
                        <strong>Excel</strong>
                        <span>فعالیت‌ها و Mapping PMS با دامنه انتخاب‌شده مدیریت می‌شوند.</span>
                        <small>${esc(importScopeHint)}</small>
                    </div>
                    <div class="contractor-settings-activity-import-actions">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="download-activity-template">Template Activity</button>
                        <input class="module-crud-input" data-activity-import-file type="file" accept=".xlsx">
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="import-activity-excel">Import Activity</button>
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="download-pms-mapping-template">Template PMS</button>
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="export-pms-mapping">Export PMS</button>
                        <input class="module-crud-input" data-pms-mapping-import-file type="file" accept=".xlsx">
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="import-pms-mapping">Import PMS</button>
                    </div>
                </div>

                <div class="contractor-settings-activity-filters">
                    <div class="module-crud-form-field">
                        <label>پروژه</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="project_code">${renderProjectOptions(filterProject)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>سازمان</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="organization_id">${renderOrganizationOptions(filterOrganization)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>قرارداد</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="organization_contract_id">${renderContractOptions(filterOrganization, filterContract)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>PMS</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="pms_status">
                            <option value=""${!filterPmsStatus ? " selected" : ""}>همه فعالیت‌ها</option>
                            <option value="mapped"${filterPmsStatus === "mapped" ? " selected" : ""}>دارای PMS</option>
                            <option value="none"${filterPmsStatus === "none" ? " selected" : ""}>فقط بدون PMS</option>
                            <option value="stale"${filterPmsStatus === "stale" ? " selected" : ""}>قدیمی شده</option>
                        </select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>Template خاص</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="pms_template_id">${renderPmsTemplateOptions(filterPmsTemplate)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>واحد</label>
                        <input class="module-crud-input" data-contractor-catalog-filter="default_unit" value="${esc(filterUnit)}">
                    </div>
                    <div class="module-crud-form-field">
                        <label>محل پیش‌فرض</label>
                        <input class="module-crud-input" data-contractor-catalog-filter="default_location" value="${esc(filterLocation)}">
                    </div>
                    <div class="module-crud-form-field">
                        <label>مرجع / سازمان</label>
                        <input class="module-crud-input" data-contractor-catalog-filter="reference_search" value="${esc(filterReference)}">
                    </div>
                </div>

                <div class="contractor-settings-activity-import">
                    <div>
                        <strong>فیلتر سریع PMS</strong>
                        <span>برای پیدا کردن Activityهای ناقص، «بدون PMS» را بزنید.</span>
                    </div>
                    <div class="contractor-settings-activity-import-actions">
                        ${quickPmsButton("", "همه", filterPmsStatus)}
                        ${quickPmsButton("mapped", "دارای PMS", filterPmsStatus)}
                        ${quickPmsButton("none", "بدون PMS", filterPmsStatus)}
                        ${quickPmsButton("stale", "قدیمی شده", filterPmsStatus)}
                    </div>
                </div>

                <div class="contractor-settings-activity-import">
                    <div>
                        <strong>عملیات گروهی PMS</strong>
                        <span>${selectedCount} Activity انتخاب شده است.</span>
                    </div>
                    <div class="contractor-settings-activity-import-actions">
                        <select class="module-crud-select" data-pms-bulk-template>${renderPmsTemplateOptions("", "انتخاب PMS Template")}</select>
                        <label class="contractor-settings-checkbox-wrap"><input type="checkbox" data-pms-bulk-overwrite><span>Overwrite</span></label>
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="bulk-apply-pms">اعمال PMS Template</button>
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="quick-without-pms">فقط فعالیت‌های بدون PMS</button>
                    </div>
                </div>

                <div class="module-crud-table-wrap">
                    <table class="module-crud-table">
                        <thead>
                            <tr>
                                <th></th>
                                <th>کد فعالیت</th>
                                <th>عنوان فعالیت</th>
                                <th>محل پیش‌فرض</th>
                                <th>واحد</th>
                                <th>دامنه</th>
                                <th>مرجع</th>
                                <th>PMS Template</th>
                                <th>وضعیت PMS</th>
                                <th>نسخه PMS</th>
                                <th>عملیات PMS</th>
                                <th>ترتیب</th>
                                <th>وضعیت</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>${renderActivityRows(rows)}</tbody>
                    </table>
                </div>

                <div class="module-crud-form-wrap contractor-settings-inline-form contractor-settings-activity-form">
                    <input type="hidden" data-activity-form-field="id" value="">
                    <div class="contractor-settings-inline-form-head">
                        <div>
                            <strong data-activity-form-title>افزودن فعالیت اجرایی</strong>
                            <span>با انتخاب پروژه، سازمان و قرارداد، این فعالیت در همان دامنه در فرم گزارش پیشنهاد می‌شود.</span>
                        </div>
                    </div>
                    <div class="module-crud-form-grid">
                        <div class="module-crud-form-field"><label>پروژه</label><select class="module-crud-select" data-activity-form-field="project_code">${renderProjectOptions("", "انتخاب پروژه")}</select></div>
                        <div class="module-crud-form-field"><label>سازمان</label><select class="module-crud-select" data-activity-form-field="organization_id">${renderOrganizationOptions("", "پروژه‌محور / همه سازمان‌ها")}</select></div>
                        <div class="module-crud-form-field"><label>قرارداد</label><select class="module-crud-select" data-activity-form-field="organization_contract_id">${renderContractOptions("", "", "همه قراردادهای سازمان")}</select></div>
                        <div class="module-crud-form-field"><label>کد فعالیت</label><input class="module-crud-input" data-activity-form-field="activity_code" type="text"></div>
                        <div class="module-crud-form-field"><label>عنوان فعالیت</label><input class="module-crud-input" data-activity-form-field="activity_title" type="text"></div>
                        <div class="module-crud-form-field"><label>محل پیش‌فرض</label><input class="module-crud-input" data-activity-form-field="default_location" type="text"></div>
                        <div class="module-crud-form-field"><label>واحد پیش‌فرض</label><input class="module-crud-input" data-activity-form-field="default_unit" type="text"></div>
                        <div class="module-crud-form-field"><label>ترتیب</label><input class="module-crud-input" data-activity-form-field="sort_order" type="number" min="0" step="1" value="${activityNextSortOrder()}"></div>
                        <div class="module-crud-form-field contractor-settings-checkbox-field"><label class="contractor-settings-checkbox-wrap"><input data-activity-form-field="is_active" type="checkbox" checked><span>فعال باشد</span></label></div>
                    </div>
                    <div class="module-crud-form-actions">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="reset-activity-form">لغو</button>
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="save-activity">ذخیره</button>
                    </div>
                </div>
            </section>
        `;
    }

    function renderLegacyCatalogs() {
        const root = getContractorRoot();
        if (!(root instanceof HTMLElement)) return;
        state.contractor.activeCatalog = normalizeReportCatalog(state.contractor.activeCatalog);
        root.innerHTML = `
            <div class="contractor-report-settings">
                ${renderContractorSubTabs()}
                ${renderContractorCatalogPanel()}
                ${renderContractorCatalogDrawer()}
                ${renderContractorBulkDrawer()}
            </div>
        `;
    }

    function pmsStepsText(row) {
        return asArray(row.steps)
            .map((step) => `${upper(step.step_code || "")}|${norm(step.step_title || "")}|${Number(step.weight_pct || 0)}`)
            .join("\n");
    }

    function renderPmsTemplateRows() {
        const rows = pmsTemplates();
        if (!rows.length) {
            return `<tr><td colspan="7" class="center-text muted" style="padding: 18px;">هنوز PMS Template ثبت نشده است.</td></tr>`;
        }
        return rows
            .map((row) => {
                const id = Number(row.id || 0);
                const code = upper(row.code || "");
                const title = norm(row.title || "");
                return `
                    <tr>
                        <td style="font-family: monospace;">${esc(code)}</td>
                        <td>${esc(title)}</td>
                        <td>v${Number(row.version || 1)}</td>
                        <td>${Number(row.active_step_count || 0)}</td>
                        <td>${Number(row.weight_total || 0)}</td>
                        <td>${renderStatus(Boolean(row.is_active))}</td>
                        <td>
                            <div class="module-crud-actions">
                                <button type="button" class="btn-archive-icon" data-contractor-catalog-action="edit-pms-template" data-template-id="${id}" data-template-code="${esc(code)}" data-template-title="${esc(title)}" data-template-sort-order="${Number(row.sort_order || 0)}" data-template-is-active="${Boolean(row.is_active) ? "1" : "0"}" data-template-steps="${esc(pmsStepsText(row))}">ویرایش</button>
                                <button type="button" class="btn-archive-icon" data-contractor-catalog-action="delete-pms-template" data-template-id="${id}" data-template-title="${esc(title || code)}">حذف</button>
                            </div>
                        </td>
                    </tr>
                `;
            })
            .join("");
    }

    function renderPmsTemplateCard() {
        return `
            <section class="general-settings-card contractor-settings-card contractor-settings-card-wide" data-catalog-type="pms-template">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title"><span class="material-icons-round">account_tree</span>PMS Template Library</h3>
                        <p class="contractor-settings-card-subtitle">هر خط Step را به شکل CODE|Title|Weight وارد کنید؛ وزن Stepهای فعال برای اعمال باید 100 باشد.</p>
                    </div>
                </div>
                <div class="module-crud-table-wrap">
                    <table class="module-crud-table">
                        <thead><tr><th>کد</th><th>عنوان</th><th>نسخه</th><th>Step</th><th>Weight</th><th>وضعیت</th><th>عملیات</th></tr></thead>
                        <tbody>${renderPmsTemplateRows()}</tbody>
                    </table>
                </div>
                <div class="module-crud-form-wrap contractor-settings-inline-form">
                    <input type="hidden" data-pms-template-field="id" value="">
                    <div class="module-crud-form-grid">
                        <div class="module-crud-form-field"><label>کد Template</label><input class="module-crud-input" data-pms-template-field="code" type="text"></div>
                        <div class="module-crud-form-field"><label>عنوان Template</label><input class="module-crud-input" data-pms-template-field="title" type="text"></div>
                        <div class="module-crud-form-field"><label>ترتیب</label><input class="module-crud-input" data-pms-template-field="sort_order" type="number" min="0" step="1" value="10"></div>
                        <div class="module-crud-form-field contractor-settings-checkbox-field"><label class="contractor-settings-checkbox-wrap"><input data-pms-template-field="is_active" type="checkbox" checked><span>فعال باشد</span></label></div>
                        <div class="module-crud-form-field module-crud-form-field-span-2"><label>Stepها</label><textarea class="module-crud-textarea" data-pms-template-field="steps" rows="4" placeholder="INSTALL|نصب|80&#10;QC|کنترل QC|20"></textarea></div>
                    </div>
                    <div class="module-crud-form-actions">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="reset-pms-template">لغو</button>
                        <button type="button" class="btn btn-primary" data-contractor-catalog-action="save-pms-template">ذخیره PMS Template</button>
                    </div>
                </div>
            </section>
        `;
    }

    function renderActivityCatalog() {
        const root = getActivityRoot();
        if (!(root instanceof HTMLElement)) return;
        root.innerHTML = `
            <div class="general-settings-grid contractor-settings-grid">
                ${renderPmsTemplateCard()}
                ${renderActivityCard()}
            </div>
        `;
    }

    function renderActivitySubTabs() {
        const active = activeActivitySubTab();
        return `
            <div class="consultant-activity-subtabs" role="tablist" aria-label="تنظیمات داخلی فعالیت‌های اجرایی">
                ${ACTIVITY_SUBTABS.map((tab) => {
                    const isActive = tab.key === active;
                    const count =
                        tab.key === "activities"
                            ? asArray(state.activity.items).length
                            : tab.key === "pms-templates"
                              ? pmsTemplates().length
                              : "";
                    return `
                        <button
                            type="button"
                            class="consultant-activity-subtab ${isActive ? "active" : ""}"
                            data-contractor-catalog-action="switch-activity-subtab"
                            data-activity-subtab="${esc(tab.key)}"
                            role="tab"
                            aria-selected="${isActive ? "true" : "false"}"
                        >
                            <span class="material-icons-round">${esc(tab.icon)}</span>
                            <span>${esc(tab.title)}</span>
                            ${count !== "" ? `<small>${count}</small>` : ""}
                        </button>
                    `;
                }).join("")}
            </div>
        `;
    }

    function renderActivityRows(rows) {
        if (!rows.length) {
            return `<tr><td colspan="11" class="center-text muted" style="padding: 18px;">فعالیتی با فیلترهای فعلی پیدا نشد.</td></tr>`;
        }
        const canUpdate = canUpdateSettings();
        return rows
            .map((row) => {
                const id = Number(row.id || 0);
                const isActive = Boolean(row.is_active);
                const projectCode = upper(row.project_code || "");
                const organizationId = Number(row.organization_id || 0);
                const contractId = Number(row.organization_contract_id || 0);
                const reference = norm(row.organization_name || row.contract_subject || projectCode || "");
                const pmsStatus = String(row.pms_status || "none");
                const selected = state.activity.selectedIds.has(id);
                const pmsTemplate = norm(row.pms_template_title || row.pms_template_code || "");
                return `
                    <tr>
                        <td>${canUpdate ? `<input type="checkbox" data-activity-row-select="${id}"${selected ? " checked" : ""} aria-label="انتخاب فعالیت">` : ""}</td>
                        <td style="font-family: monospace;">${esc(row.activity_code || "-")}</td>
                        <td>${esc(row.activity_title || "-")}</td>
                        <td>${esc(row.scope_label || "-")}</td>
                        <td>${esc(reference || "-")}</td>
                        <td>${esc(row.default_unit || "-")}</td>
                        <td>${esc(row.default_location || "-")}</td>
                        <td>${esc(pmsTemplate || "-")}</td>
                        <td>${renderPmsStatus(row)}</td>
                        <td>${renderStatus(isActive)}</td>
                        <td>
                            ${canUpdate ? `
                                <div class="module-crud-actions">
                                    <button type="button" class="btn-archive-icon" data-contractor-catalog-action="pms-activity" data-item-id="${id}" title="انتخاب PMS">
                                        <span class="material-icons-round">account_tree</span>
                                    </button>
                                    ${pmsStatus !== "none" ? `
                                        <button type="button" class="btn-archive-icon" data-contractor-catalog-action="delete-pms-activity" data-item-id="${id}" title="حذف PMS">
                                            <span class="material-icons-round">link_off</span>
                                        </button>
                                    ` : ""}
                                    ${pmsStatus === "stale" ? `
                                        <button type="button" class="btn-archive-icon" data-contractor-catalog-action="reapply-pms-activity" data-item-id="${id}" title="Reapply PMS">
                                            <span class="material-icons-round">sync</span>
                                        </button>
                                    ` : ""}
                                    <button
                                        type="button"
                                        class="btn-archive-icon"
                                        data-contractor-catalog-action="edit-activity"
                                        data-item-id="${id}"
                                        data-project-code="${esc(projectCode)}"
                                        data-organization-id="${organizationId > 0 ? organizationId : ""}"
                                        data-organization-contract-id="${contractId > 0 ? contractId : ""}"
                                        data-activity-code="${esc(row.activity_code || "")}"
                                        data-activity-title="${esc(row.activity_title || "")}"
                                        data-default-location="${esc(row.default_location || "")}"
                                        data-default-unit="${esc(row.default_unit || "")}"
                                        data-sort-order="${Number(row.sort_order || 0)}"
                                        data-item-is-active="${isActive ? "1" : "0"}"
                                        title="ویرایش"
                                    >
                                        <span class="material-icons-round">edit</span>
                                    </button>
                                    <button
                                        type="button"
                                        class="btn-archive-icon"
                                        data-contractor-catalog-action="toggle-activity-active"
                                        data-item-id="${id}"
                                        data-project-code="${esc(projectCode)}"
                                        data-organization-id="${organizationId > 0 ? organizationId : ""}"
                                        data-organization-contract-id="${contractId > 0 ? contractId : ""}"
                                        data-activity-code="${esc(row.activity_code || "")}"
                                        data-activity-title="${esc(row.activity_title || "")}"
                                        data-default-location="${esc(row.default_location || "")}"
                                        data-default-unit="${esc(row.default_unit || "")}"
                                        data-sort-order="${Number(row.sort_order || 0)}"
                                        data-item-is-active="${isActive ? "1" : "0"}"
                                        data-item-label="${esc(row.activity_title || row.activity_code || id)}"
                                        title="${isActive ? "غیرفعال‌سازی" : "فعال‌سازی"}"
                                    >
                                        <span class="material-icons-round">${isActive ? "visibility_off" : "restart_alt"}</span>
                                    </button>
                                </div>
                            ` : `<span class="muted">فقط مشاهده</span>`}
                        </td>
                    </tr>
                `;
            })
            .join("");
    }

    function renderActivityBulkBar(selectedCount) {
        if (!canUpdateSettings() || selectedCount <= 0) return "";
        return `
            <div class="consultant-activity-bulk-bar">
                <strong>${selectedCount} فعالیت انتخاب شده</strong>
                <select class="module-crud-select" data-pms-bulk-template>${renderPmsTemplateOptions("", "انتخاب PMS Template")}</select>
                <label class="contractor-settings-checkbox-wrap"><input type="checkbox" data-pms-bulk-overwrite><span>Overwrite</span></label>
                <button type="button" class="btn btn-primary" data-contractor-catalog-action="bulk-apply-pms">اعمال PMS Template</button>
                <button type="button" class="btn btn-secondary" data-contractor-catalog-action="quick-without-pms">فقط بدون PMS</button>
            </div>
        `;
    }

    function renderActivityCard() {
        const rows = asArray(state.activity.items);
        const filteredRows = filteredActivityRows();
        const activeCount = rows.filter((row) => Boolean(row.is_active)).length;
        const inactiveCount = rows.length - activeCount;
        const filterProject = norm(state.activity.filters.project_code);
        const filterOrganization = String(state.activity.filters.organization_id || "");
        const filterContract = String(state.activity.filters.organization_contract_id || "");
        const filterPmsStatus = String(state.activity.filters.pms_status || "");
        const filterPmsTemplate = String(state.activity.filters.pms_template_id || "");
        const selectedCount = state.activity.selectedIds.size;
        const pmsSummary = pmsSummaryFromRows(rows);
        const canUpdate = canUpdateSettings();
        return `
            <section class="general-settings-card contractor-settings-card contractor-settings-card-wide consultant-activity-panel" data-catalog-type="activity" role="tabpanel">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title"><span class="material-icons-round">list_alt</span>فعالیت‌های اجرایی</h3>
                        <p class="contractor-settings-card-subtitle">مدیریت کاتالوگ فعالیت‌ها و وضعیت اتصال آن‌ها به PMS Template.</p>
                    </div>
                    <div class="contractor-settings-card-meta">
                        <span class="doc-muted-pill">کل: ${rows.length}</span>
                        <span class="doc-muted-pill">فعال: ${activeCount}</span>
                        <span class="doc-muted-pill">غیرفعال: ${inactiveCount}</span>
                        <span class="doc-muted-pill">دارای PMS: ${pmsSummary.mapped}</span>
                        <span class="doc-muted-pill">بدون PMS: ${pmsSummary.none}</span>
                        <span class="doc-muted-pill">قدیمی: ${pmsSummary.stale}</span>
                        ${canUpdate ? "" : `<span class="doc-muted-pill">فقط مشاهده</span>`}
                    </div>
                </div>

                <div class="consultant-activity-toolbar">
                    <div class="module-crud-form-field">
                        <label>پروژه</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="project_code">${renderProjectOptions(filterProject)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>سازمان</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="organization_id">${renderOrganizationOptions(filterOrganization)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>قرارداد</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="organization_contract_id">${renderContractOptions(filterOrganization, filterContract)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>وضعیت PMS</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="pms_status">
                            <option value=""${!filterPmsStatus ? " selected" : ""}>همه</option>
                            <option value="mapped"${filterPmsStatus === "mapped" ? " selected" : ""}>دارای PMS</option>
                            <option value="none"${filterPmsStatus === "none" ? " selected" : ""}>بدون PMS</option>
                            <option value="stale"${filterPmsStatus === "stale" ? " selected" : ""}>قدیمی شده</option>
                        </select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>Template</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="pms_template_id">${renderPmsTemplateOptions(filterPmsTemplate)}</select>
                    </div>
                    <div class="module-crud-form-field consultant-activity-search">
                        <label>جستجو</label>
                        <input class="module-crud-input" data-activity-search type="search" value="${esc(state.activity.searchText)}" placeholder="کد، عنوان، مرجع، واحد یا محل...">
                    </div>
                    <div class="contractor-catalog-filter-group" role="group" aria-label="فیلتر وضعیت فعالیت">
                        ${activityStatusButton("all", "همه")}
                        ${activityStatusButton("active", "فعال")}
                        ${activityStatusButton("inactive", "غیرفعال")}
                    </div>
                    ${canUpdate ? `
                        <button type="button" class="btn btn-primary contractor-catalog-add-btn" data-contractor-catalog-action="open-activity-drawer">
                            <span class="material-icons-round">add</span>
                            افزودن فعالیت
                        </button>
                    ` : ""}
                </div>

                ${renderActivityBulkBar(selectedCount)}

                <div class="module-crud-table-wrap contractor-catalog-table-wrap">
                    <table class="module-crud-table">
                        <thead>
                            <tr>
                                <th>انتخاب</th>
                                <th>کد</th>
                                <th>عنوان</th>
                                <th>دامنه</th>
                                <th>مرجع</th>
                                <th>واحد</th>
                                <th>محل</th>
                                <th>PMS Template</th>
                                <th>وضعیت PMS</th>
                                <th>وضعیت</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>${renderActivityRows(filteredRows)}</tbody>
                    </table>
                </div>
            </section>
        `;
    }

    function renderPmsTemplateRows() {
        const rows = pmsTemplates();
        if (!rows.length) {
            return `<tr><td colspan="7" class="center-text muted" style="padding: 18px;">هنوز PMS Template ثبت نشده است.</td></tr>`;
        }
        const canUpdate = canUpdateSettings();
        return rows
            .map((row) => {
                const id = Number(row.id || 0);
                const code = upper(row.code || "");
                const title = norm(row.title || "");
                const weightTotal = Number(row.weight_total || 0);
                const isActive = Boolean(row.is_active);
                return `
                    <tr>
                        <td style="font-family: monospace;">${esc(code)}</td>
                        <td>${esc(title)}</td>
                        <td>v${Number(row.version || 1)}</td>
                        <td>${Number(row.active_step_count || 0)}</td>
                        <td><span class="consultant-pms-weight-pill ${isActive && weightTotal !== 100 ? "is-invalid" : ""}">${weightTotal}</span></td>
                        <td>${renderStatus(isActive)}</td>
                        <td>
                            ${canUpdate ? `
                                <div class="module-crud-actions">
                                    <button type="button" class="btn-archive-icon" data-contractor-catalog-action="edit-pms-template" data-template-id="${id}" data-template-code="${esc(code)}" data-template-title="${esc(title)}" data-template-sort-order="${Number(row.sort_order || 0)}" data-template-is-active="${isActive ? "1" : "0"}" data-template-steps="${esc(pmsStepsText(row))}" title="ویرایش">
                                        <span class="material-icons-round">edit</span>
                                    </button>
                                    <button type="button" class="btn-archive-icon" data-contractor-catalog-action="toggle-pms-template-active" data-template-id="${id}" data-template-code="${esc(code)}" data-template-title="${esc(title)}" data-template-sort-order="${Number(row.sort_order || 0)}" data-template-is-active="${isActive ? "1" : "0"}" data-template-steps="${esc(pmsStepsText(row))}" title="${isActive ? "غیرفعال‌سازی" : "فعال‌سازی"}">
                                        <span class="material-icons-round">${isActive ? "visibility_off" : "restart_alt"}</span>
                                    </button>
                                </div>
                            ` : `<span class="muted">فقط مشاهده</span>`}
                        </td>
                    </tr>
                `;
            })
            .join("");
    }

    function renderPmsTemplateCard() {
        const rows = pmsTemplates();
        const activeCount = rows.filter((row) => Boolean(row.is_active)).length;
        const inactiveCount = rows.length - activeCount;
        const invalidCount = invalidPmsTemplateCount();
        const canUpdate = canUpdateSettings();
        return `
            <section class="general-settings-card contractor-settings-card contractor-settings-card-wide consultant-activity-panel" data-catalog-type="pms-template" role="tabpanel">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title"><span class="material-icons-round">account_tree</span>PMS Template Library</h3>
                        <p class="contractor-settings-card-subtitle">تعریف Stepهای PMS و کنترل مجموع وزن Stepهای فعال.</p>
                    </div>
                    <div class="contractor-settings-card-meta">
                        <span class="doc-muted-pill">کل: ${rows.length}</span>
                        <span class="doc-muted-pill">فعال: ${activeCount}</span>
                        <span class="doc-muted-pill">غیرفعال: ${inactiveCount}</span>
                        <span class="doc-muted-pill">وزن نامعتبر: ${invalidCount}</span>
                        ${canUpdate ? "" : `<span class="doc-muted-pill">فقط مشاهده</span>`}
                    </div>
                </div>
                <div class="consultant-activity-list-toolbar">
                    ${canUpdate ? `
                        <button type="button" class="btn btn-primary contractor-catalog-add-btn" data-contractor-catalog-action="open-pms-template-drawer">
                            <span class="material-icons-round">add</span>
                            افزودن PMS Template
                        </button>
                    ` : ""}
                </div>
                <div class="module-crud-table-wrap contractor-catalog-table-wrap">
                    <table class="module-crud-table">
                        <thead><tr><th>کد</th><th>عنوان</th><th>نسخه</th><th>Step فعال</th><th>Weight</th><th>وضعیت</th><th>عملیات</th></tr></thead>
                        <tbody>${renderPmsTemplateRows()}</tbody>
                    </table>
                </div>
            </section>
        `;
    }

    function renderExcelMappingCard() {
        const filterProject = norm(state.activity.filters.project_code);
        const filterOrganization = String(state.activity.filters.organization_id || "");
        const filterContract = String(state.activity.filters.organization_contract_id || "");
        const selectedOrganization = organizations().find((row) => String(row.id || "") === filterOrganization);
        const selectedContract = contractsForOrganization(filterOrganization).find((row) => String(row.id || "") === filterContract);
        const canUpdate = canUpdateSettings();
        const hasProject = Boolean(filterProject);
        const disabledByScope = hasProject ? "" : "disabled";
        const scopeHint = filterProject
            ? [
                  `پروژه ${filterProject}`,
                  selectedOrganization ? `سازمان ${selectedOrganization.name || filterOrganization}` : "همه سازمان‌ها",
                  selectedContract ? `قرارداد ${contractLabel(selectedContract) || filterContract}` : "",
              ]
                  .filter(Boolean)
                  .join(" / ")
            : "برای عملیات دامنه‌دار ابتدا پروژه را انتخاب کنید.";
        return `
            <section class="general-settings-card contractor-settings-card contractor-settings-card-wide consultant-activity-panel" data-catalog-type="activity-excel" role="tabpanel">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title"><span class="material-icons-round">ios_share</span>Excel و Mapping</h3>
                        <p class="contractor-settings-card-subtitle">Import/Export فعالیت‌ها و Mapping PMS در دامنه انتخاب‌شده انجام می‌شود.</p>
                    </div>
                    <div class="contractor-settings-card-meta">
                        <span class="doc-muted-pill">${esc(scopeHint)}</span>
                    </div>
                </div>
                <div class="consultant-activity-toolbar consultant-activity-toolbar-compact">
                    <div class="module-crud-form-field">
                        <label>پروژه</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="project_code">${renderProjectOptions(filterProject)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>سازمان</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="organization_id">${renderOrganizationOptions(filterOrganization)}</select>
                    </div>
                    <div class="module-crud-form-field">
                        <label>قرارداد</label>
                        <select class="module-crud-select" data-contractor-catalog-filter="organization_contract_id">${renderContractOptions(filterOrganization, filterContract)}</select>
                    </div>
                </div>
                <div class="consultant-activity-ops-grid">
                    <section class="consultant-activity-op">
                        <div>
                            <strong>Activity Catalog</strong>
                            <span>فایل قالب را بگیرید یا فعالیت‌ها را برای دامنه انتخاب‌شده import کنید.</span>
                        </div>
                        <div class="contractor-settings-activity-import-actions">
                            <button type="button" class="btn btn-secondary" data-contractor-catalog-action="download-activity-template">Template Activity</button>
                            ${canUpdate ? `
                                <input class="module-crud-input" data-activity-import-file type="file" accept=".xlsx" ${disabledByScope}>
                                <button type="button" class="btn btn-primary" data-contractor-catalog-action="import-activity-excel" ${disabledByScope}>Import Activity</button>
                            ` : ""}
                        </div>
                    </section>
                    <section class="consultant-activity-op">
                        <div>
                            <strong>PMS Mapping</strong>
                            <span>Mapping بین Activity و PMS Template را template، export یا import کنید.</span>
                        </div>
                        <div class="contractor-settings-activity-import-actions">
                            <button type="button" class="btn btn-secondary" data-contractor-catalog-action="download-pms-mapping-template">Template PMS</button>
                            <button type="button" class="btn btn-secondary" data-contractor-catalog-action="export-pms-mapping" ${disabledByScope}>Export PMS</button>
                            ${canUpdate ? `
                                <input class="module-crud-input" data-pms-mapping-import-file type="file" accept=".xlsx" ${disabledByScope}>
                                <button type="button" class="btn btn-primary" data-contractor-catalog-action="import-pms-mapping" ${disabledByScope}>Import PMS</button>
                            ` : ""}
                        </div>
                    </section>
                </div>
            </section>
        `;
    }

    function renderActivityDrawer() {
        const editing = state.activity.editingActivity || {};
        const isOpen = state.activity.editingActivity !== null;
        const isEditing = Number(editing.id || 0) > 0;
        const canUpdate = canUpdateSettings();
        const organizationId = String(editing.organization_id || "");
        return `
            <div class="contractor-settings-drawer" data-activity-drawer ${isOpen ? "" : "hidden"}>
                <div class="contractor-settings-drawer-backdrop" data-contractor-catalog-action="close-activity-drawer"></div>
                <section class="contractor-settings-drawer-panel consultant-activity-drawer-panel" data-activity-form-scope role="dialog" aria-modal="true" aria-label="${esc(isEditing ? "ویرایش فعالیت اجرایی" : "افزودن فعالیت اجرایی")}">
                    <div class="contractor-settings-drawer-header">
                        <div>
                            <h3 data-activity-form-title>${isEditing ? "ویرایش فعالیت اجرایی" : "افزودن فعالیت اجرایی"}</h3>
                            <p>دامنه فعالیت مشخص می‌کند این آیتم در کدام گزارش‌ها پیشنهاد شود.</p>
                        </div>
                        <button type="button" class="btn-archive-icon" data-contractor-catalog-action="close-activity-drawer" title="بستن"><span class="material-icons-round">close</span></button>
                    </div>
                    <div class="contractor-settings-drawer-body">
                        <input type="hidden" data-activity-form-field="id" value="${esc(editing.id || "")}">
                        <div class="module-crud-form-grid">
                            <div class="module-crud-form-field"><label>پروژه</label><select class="module-crud-select" data-activity-form-field="project_code" ${canUpdate ? "" : "disabled"}>${renderProjectOptions(editing.project_code || "", "انتخاب پروژه")}</select></div>
                            <div class="module-crud-form-field"><label>سازمان</label><select class="module-crud-select" data-activity-form-field="organization_id" ${canUpdate ? "" : "disabled"}>${renderOrganizationOptions(organizationId, "پروژه‌محور / همه سازمان‌ها")}</select></div>
                            <div class="module-crud-form-field"><label>قرارداد</label><select class="module-crud-select" data-activity-form-field="organization_contract_id" ${canUpdate ? "" : "disabled"}>${renderContractOptions(organizationId, editing.organization_contract_id || "", "همه قراردادهای سازمان")}</select></div>
                            <div class="module-crud-form-field"><label>کد فعالیت</label><input class="module-crud-input" data-activity-form-field="activity_code" type="text" value="${esc(editing.activity_code || "")}" ${canUpdate ? "" : "disabled"}></div>
                            <div class="module-crud-form-field"><label>عنوان فعالیت</label><input class="module-crud-input" data-activity-form-field="activity_title" type="text" value="${esc(editing.activity_title || "")}" ${canUpdate ? "" : "disabled"}></div>
                            <div class="module-crud-form-field"><label>محل پیش‌فرض</label><input class="module-crud-input" data-activity-form-field="default_location" type="text" value="${esc(editing.default_location || "")}" ${canUpdate ? "" : "disabled"}></div>
                            <div class="module-crud-form-field"><label>واحد پیش‌فرض</label><input class="module-crud-input" data-activity-form-field="default_unit" type="text" value="${esc(editing.default_unit || "")}" ${canUpdate ? "" : "disabled"}></div>
                            <div class="module-crud-form-field"><label>ترتیب</label><input class="module-crud-input" data-activity-form-field="sort_order" type="number" min="0" step="1" value="${esc(editing.sort_order ?? activityNextSortOrder())}" ${canUpdate ? "" : "disabled"}></div>
                            <div class="module-crud-form-field contractor-settings-checkbox-field"><label class="contractor-settings-checkbox-wrap"><input data-activity-form-field="is_active" type="checkbox" ${editing.is_active === false ? "" : "checked"} ${canUpdate ? "" : "disabled"}><span>فعال باشد</span></label></div>
                        </div>
                    </div>
                    <div class="contractor-settings-drawer-footer">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="close-activity-drawer">لغو</button>
                        ${canUpdate ? `<button type="button" class="btn btn-primary" data-contractor-catalog-action="save-activity">ذخیره</button>` : ""}
                    </div>
                </section>
            </div>
        `;
    }

    function renderPmsStepRows(steps) {
        const rows = asArray(steps).length ? asArray(steps) : [{ step_code: "", step_title: "", weight_pct: 100, sort_order: 10, is_active: true }];
        const canUpdate = canUpdateSettings();
        return rows
            .map((step, index) => `
                <div class="consultant-pms-step-row" data-pms-step-row="${index}">
                    <input class="module-crud-input" data-pms-step-field="step_code" value="${esc(step.step_code || "")}" placeholder="CODE" ${canUpdate ? "" : "disabled"}>
                    <input class="module-crud-input" data-pms-step-field="step_title" value="${esc(step.step_title || "")}" placeholder="عنوان Step" ${canUpdate ? "" : "disabled"}>
                    <input class="module-crud-input" data-pms-step-field="weight_pct" type="number" min="0" max="100" step="1" value="${esc(step.weight_pct ?? 0)}" placeholder="Weight" ${canUpdate ? "" : "disabled"}>
                    <input class="module-crud-input" data-pms-step-field="sort_order" type="number" min="0" step="1" value="${esc(step.sort_order ?? (index + 1) * 10)}" placeholder="ترتیب" ${canUpdate ? "" : "disabled"}>
                    <label class="contractor-settings-checkbox-wrap"><input data-pms-step-field="is_active" type="checkbox" ${step.is_active === false ? "" : "checked"} ${canUpdate ? "" : "disabled"}><span>فعال</span></label>
                    ${canUpdate ? `<button type="button" class="btn-archive-icon" data-contractor-catalog-action="remove-pms-step" data-pms-step-index="${index}" title="حذف Step"><span class="material-icons-round">delete</span></button>` : `<span></span>`}
                </div>
            `)
            .join("");
    }

    function renderPmsTemplateDrawer() {
        const editing = state.activity.editingPmsTemplate || {};
        const isOpen = state.activity.editingPmsTemplate !== null;
        const isEditing = Number(editing.id || 0) > 0;
        const canUpdate = canUpdateSettings();
        const steps = asArray(editing.steps).length ? editing.steps : [{ step_code: "", step_title: "", weight_pct: 100, sort_order: 10, is_active: true }];
        const weightTotal = pmsStepWeightTotalFromRows(steps);
        return `
            <div class="contractor-settings-drawer" data-pms-template-drawer ${isOpen ? "" : "hidden"}>
                <div class="contractor-settings-drawer-backdrop" data-contractor-catalog-action="close-pms-template-drawer"></div>
                <section class="contractor-settings-drawer-panel consultant-pms-drawer-panel" data-pms-template-form-scope role="dialog" aria-modal="true" aria-label="${esc(isEditing ? "ویرایش PMS Template" : "افزودن PMS Template")}">
                    <div class="contractor-settings-drawer-header">
                        <div>
                            <h3>${isEditing ? "ویرایش PMS Template" : "افزودن PMS Template"}</h3>
                            <p>Stepهای فعال برای اعمال روی Activity باید مجموع وزن 100 داشته باشند.</p>
                        </div>
                        <button type="button" class="btn-archive-icon" data-contractor-catalog-action="close-pms-template-drawer" title="بستن"><span class="material-icons-round">close</span></button>
                    </div>
                    <div class="contractor-settings-drawer-body">
                        <input type="hidden" data-pms-template-field="id" value="${esc(editing.id || "")}">
                        <div class="module-crud-form-grid">
                            <div class="module-crud-form-field"><label>کد Template</label><input class="module-crud-input" data-pms-template-field="code" type="text" value="${esc(editing.code || "")}" ${canUpdate ? "" : "disabled"}></div>
                            <div class="module-crud-form-field"><label>عنوان Template</label><input class="module-crud-input" data-pms-template-field="title" type="text" value="${esc(editing.title || "")}" ${canUpdate ? "" : "disabled"}></div>
                            <div class="module-crud-form-field"><label>ترتیب</label><input class="module-crud-input" data-pms-template-field="sort_order" type="number" min="0" step="1" value="${esc(editing.sort_order ?? 10)}" ${canUpdate ? "" : "disabled"}></div>
                            <div class="module-crud-form-field contractor-settings-checkbox-field"><label class="contractor-settings-checkbox-wrap"><input data-pms-template-field="is_active" type="checkbox" ${editing.is_active === false ? "" : "checked"} ${canUpdate ? "" : "disabled"}><span>فعال باشد</span></label></div>
                        </div>
                        <div class="consultant-pms-step-editor">
                            <div class="consultant-pms-step-editor-head">
                                <strong>Stepها</strong>
                                <span class="consultant-pms-weight-summary ${weightTotal === 100 ? "" : "is-invalid"}" data-pms-step-weight-total>مجموع وزن: ${weightTotal}</span>
                            </div>
                            <div class="consultant-pms-step-header">
                                <span>کد</span><span>عنوان</span><span>Weight</span><span>ترتیب</span><span>وضعیت</span><span></span>
                            </div>
                            <div data-pms-step-list>${renderPmsStepRows(steps)}</div>
                            ${canUpdate ? `<button type="button" class="btn btn-secondary consultant-pms-add-step" data-contractor-catalog-action="add-pms-step"><span class="material-icons-round">add</span>افزودن Step</button>` : ""}
                        </div>
                    </div>
                    <div class="contractor-settings-drawer-footer">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="close-pms-template-drawer">لغو</button>
                        ${canUpdate ? `<button type="button" class="btn btn-primary" data-contractor-catalog-action="save-pms-template">ذخیره PMS Template</button>` : ""}
                    </div>
                </section>
            </div>
        `;
    }

    function renderActivityCatalog() {
        const root = getActivityRoot();
        if (!(root instanceof HTMLElement)) return;
        const activeTab = activeActivitySubTab();
        const activePanel =
            activeTab === "pms-templates"
                ? renderPmsTemplateCard()
                : activeTab === "excel-mapping"
                  ? renderExcelMappingCard()
                  : renderActivityCard();
        root.innerHTML = `
            <div class="consultant-activity-settings">
                ${renderActivitySubTabs()}
                ${activePanel}
                ${renderActivityDrawer()}
                ${renderPmsTemplateDrawer()}
            </div>
        `;
        syncPmsStepWeightSummary(root);
    }

    function setFormValues(card, values = {}) {
        if (!(card instanceof HTMLElement)) return;
        card.querySelectorAll("[data-catalog-form-field]").forEach((fieldEl) => {
            const field = String(fieldEl.dataset.catalogFormField || "").trim();
            if (!field) return;
            if (fieldEl instanceof HTMLInputElement && fieldEl.type === "checkbox") {
                fieldEl.checked = field === "is_active" ? Boolean(values[field] !== false && values[field] !== "0") : Boolean(values[field]);
                return;
            }
            if (fieldEl instanceof HTMLInputElement || fieldEl instanceof HTMLSelectElement || fieldEl instanceof HTMLTextAreaElement) {
                const fallback = field === "sort_order" ? String(nextSortOrder(card.dataset.catalogType || "")) : "";
                fieldEl.value = String(values[field] ?? fallback);
            }
        });
        const titleEl = card.querySelector("[data-catalog-form-title]");
        if (titleEl) {
            titleEl.textContent = values.id ? "ویرایش آیتم" : "افزودن آیتم جدید";
        }
    }

    function readFormValues(card) {
        const catalogType = String(card?.dataset?.catalogType || "").trim();
        const idInput = card.querySelector('[data-catalog-form-field="id"]');
        const codeInput = card.querySelector('[data-catalog-form-field="code"]');
        const labelInput = card.querySelector('[data-catalog-form-field="label"]');
        const sortOrderInput = card.querySelector('[data-catalog-form-field="sort_order"]');
        const activeInput = card.querySelector('[data-catalog-form-field="is_active"]');
        const id = Number(idInput && "value" in idInput ? idInput.value || 0 : 0);
        const sortOrder = Number(sortOrderInput && "value" in sortOrderInput ? sortOrderInput.value || 0 : 0);
        return {
            catalog_type: catalogType,
            id: id > 0 ? id : null,
            code: upper(codeInput && "value" in codeInput ? codeInput.value : ""),
            label: norm(labelInput && "value" in labelInput ? labelInput.value : ""),
            sort_order: Number.isFinite(sortOrder) ? sortOrder : 0,
            is_active: Boolean(activeInput && "checked" in activeInput ? activeInput.checked : true),
        };
    }

    function splitBulkCatalogLine(line) {
        const raw = norm(line);
        if (!raw) return [];
        const delimiter = raw.includes("|")
            ? "|"
            : raw.includes("\t")
              ? "\t"
              : raw.includes(",")
                ? ","
                : raw.includes("،")
                  ? "،"
                  : "";
        if (!delimiter) return ["", raw, ""];
        return raw.split(delimiter).map((part) => norm(part));
    }

    function parseBulkCatalogItems(value) {
        return String(value || "")
            .split(/\r?\n/)
            .map((line, index) => {
                const parts = splitBulkCatalogLine(line);
                if (!parts.length) return null;
                const hasDelimiter = parts.length > 1;
                const code = hasDelimiter ? upper(parts[0] || "") : "";
                const label = hasDelimiter ? norm(parts[1] || parts[0] || "") : norm(parts[1] || "");
                const sortOrderRaw = hasDelimiter ? parts[2] : "";
                const sortOrder = Number(sortOrderRaw || 0);
                if (!label) return null;
                return {
                    code: code || null,
                    label,
                    sort_order: Number.isFinite(sortOrder) && sortOrder > 0 ? sortOrder : (index + 1) * 10,
                    is_active: true,
                };
            })
            .filter(Boolean);
    }

    function resetForm(card) {
        if (!(card instanceof HTMLElement)) return;
        setFormValues(card, {
            id: "",
            code: "",
            label: "",
            sort_order: nextSortOrder(card.dataset.catalogType || ""),
            is_active: true,
        });
    }

    function openContractorCatalogDrawer(values = {}) {
        const spec = activeReportSpec();
        state.contractor.editingItem = {
            id: values.id || "",
            code: values.code || "",
            label: values.label || "",
            sort_order: values.sort_order ?? nextSortOrder(spec.key),
            is_active: values.is_active !== false && values.is_active !== "0",
        };
        renderLegacyCatalogs();
        const root = getContractorRoot();
        const codeInput = root?.querySelector?.('[data-catalog-form-field="code"]');
        if (codeInput && typeof codeInput.focus === "function") {
            codeInput.focus();
            if (typeof codeInput.select === "function") codeInput.select();
        }
    }

    function closeContractorCatalogDrawer() {
        state.contractor.editingItem = null;
        renderLegacyCatalogs();
    }

    function openContractorBulkDrawer(catalogType = activeReportCatalog()) {
        const key = normalizeReportCatalog(catalogType);
        if (!canBulkAddCatalog(key)) return;
        state.contractor.bulkCatalog = key;
        renderLegacyCatalogs();
        const textarea = getContractorRoot()?.querySelector?.("[data-bulk-catalog-field='items']");
        if (textarea && typeof textarea.focus === "function") textarea.focus();
    }

    function closeContractorBulkDrawer() {
        state.contractor.bulkCatalog = null;
        renderLegacyCatalogs();
    }

    function openActivityDrawer(values = {}) {
        state.activity.editingActivity = {
            id: values.id || "",
            project_code: upper(values.project_code || state.activity.filters.project_code || ""),
            organization_id: String(values.organization_id ?? state.activity.filters.organization_id ?? ""),
            organization_contract_id: String(values.organization_contract_id ?? state.activity.filters.organization_contract_id ?? ""),
            activity_code: upper(values.activity_code || ""),
            activity_title: norm(values.activity_title || ""),
            default_location: norm(values.default_location || ""),
            default_unit: norm(values.default_unit || ""),
            sort_order: values.sort_order ?? activityNextSortOrder(),
            is_active: values.is_active !== false && values.is_active !== "0",
        };
        renderActivityCatalog();
        const codeInput = getActivityRoot()?.querySelector?.('[data-activity-form-field="activity_code"]');
        if (codeInput && typeof codeInput.focus === "function") {
            codeInput.focus();
            if (typeof codeInput.select === "function") codeInput.select();
        }
    }

    function closeActivityDrawer() {
        state.activity.editingActivity = null;
        renderActivityCatalog();
    }

    function readCurrentPmsStepRows() {
        const scope = getActivityRoot()?.querySelector?.("[data-pms-template-form-scope]");
        if (!(scope instanceof HTMLElement)) return [];
        return Array.from(scope.querySelectorAll("[data-pms-step-row]"))
            .map((row, index) => {
                const readValue = (field) => {
                    const el = row.querySelector(`[data-pms-step-field="${field}"]`);
                    return el && "value" in el ? el.value : "";
                };
                const activeEl = row.querySelector('[data-pms-step-field="is_active"]');
                const stepCode = upper(readValue("step_code") || `STEP${index + 1}`);
                const stepTitle = norm(readValue("step_title") || stepCode || `Step ${index + 1}`);
                return {
                    step_code: stepCode,
                    step_title: stepTitle,
                    weight_pct: Number(readValue("weight_pct") || 0),
                    sort_order: Number(readValue("sort_order") || (index + 1) * 10),
                    is_active: Boolean(activeEl && "checked" in activeEl ? activeEl.checked : true),
                };
            })
            .filter((step) => step.step_code || step.step_title);
    }

    function syncPmsStepWeightSummary(root = getActivityRoot()) {
        const scope = root?.querySelector?.("[data-pms-template-form-scope]");
        if (!(scope instanceof HTMLElement)) return;
        const summary = scope.querySelector("[data-pms-step-weight-total]");
        if (!(summary instanceof HTMLElement)) return;
        const total = pmsStepWeightTotalFromRows(readCurrentPmsStepRows());
        summary.textContent = `مجموع وزن: ${total}`;
        summary.classList.toggle("is-invalid", total !== 100);
    }

    function openPmsTemplateDrawer(values = {}) {
        const steps = asArray(values.steps).length ? values.steps : parsePmsStepsText(values.steps || "");
        state.activity.editingPmsTemplate = {
            id: values.id || "",
            code: upper(values.code || ""),
            title: norm(values.title || ""),
            sort_order: values.sort_order ?? 10,
            is_active: values.is_active !== false && values.is_active !== "0",
            steps: steps.length ? steps : [{ step_code: "", step_title: "", weight_pct: 100, sort_order: 10, is_active: true }],
        };
        renderActivityCatalog();
        const codeInput = getActivityRoot()?.querySelector?.('[data-pms-template-field="code"]');
        if (codeInput && typeof codeInput.focus === "function") {
            codeInput.focus();
            if (typeof codeInput.select === "function") codeInput.select();
        }
    }

    function closePmsTemplateDrawer() {
        state.activity.editingPmsTemplate = null;
        renderActivityCatalog();
    }

    function getActivityCard() {
        return getActivityRoot()?.querySelector('[data-catalog-type="activity"]') || null;
    }

    function setActivityContractOptions(card, organizationId, current = "") {
        if (!(card instanceof HTMLElement)) return;
        const contractSelect = card.querySelector('[data-activity-form-field="organization_contract_id"]');
        if (!(contractSelect instanceof HTMLSelectElement)) return;
        contractSelect.innerHTML = renderContractOptions(organizationId, current, "همه قراردادهای سازمان");
    }

    function setActivityFormValues(card, values = {}) {
        if (!(card instanceof HTMLElement)) return;
        const organizationId = String(values.organization_id || "");
        setActivityContractOptions(card, organizationId, values.organization_contract_id || "");
        card.querySelectorAll("[data-activity-form-field]").forEach((fieldEl) => {
            const field = String(fieldEl.dataset.activityFormField || "").trim();
            if (!field) return;
            if (fieldEl instanceof HTMLInputElement && fieldEl.type === "checkbox") {
                fieldEl.checked = field === "is_active" ? Boolean(values[field] !== false && values[field] !== "0") : Boolean(values[field]);
                return;
            }
            if (fieldEl instanceof HTMLInputElement || fieldEl instanceof HTMLSelectElement || fieldEl instanceof HTMLTextAreaElement) {
                const fallback = field === "sort_order" ? String(activityNextSortOrder()) : "";
                fieldEl.value = String(values[field] ?? fallback);
            }
        });
        const titleEl = card.querySelector("[data-activity-form-title]");
        if (titleEl) {
            titleEl.textContent = values.id ? "ویرایش فعالیت اجرایی" : "افزودن فعالیت اجرایی";
        }
    }

    function resetActivityForm(card) {
        setActivityFormValues(card, {
            id: "",
            project_code: norm(state.activity.filters.project_code),
            organization_id: String(state.activity.filters.organization_id || ""),
            organization_contract_id: String(state.activity.filters.organization_contract_id || ""),
            activity_code: "",
            activity_title: "",
            default_location: "",
            default_unit: "",
            sort_order: activityNextSortOrder(),
            is_active: true,
        });
    }

    function readActivityFormValues(card) {
        const readValue = (field) => {
            const el = card?.querySelector?.(`[data-activity-form-field="${field}"]`);
            return el && "value" in el ? el.value : "";
        };
        const id = Number(readValue("id") || 0);
        const sortOrder = Number(readValue("sort_order") || 0);
        const activeEl = card?.querySelector?.('[data-activity-form-field="is_active"]');
        return {
            id: id > 0 ? id : null,
            project_code: upper(readValue("project_code")),
            organization_id: Number(readValue("organization_id") || 0) || null,
            organization_contract_id: Number(readValue("organization_contract_id") || 0) || null,
            activity_code: upper(readValue("activity_code")),
            activity_title: norm(readValue("activity_title")),
            default_location: norm(readValue("default_location")),
            default_unit: norm(readValue("default_unit")),
            sort_order: Number.isFinite(sortOrder) ? sortOrder : 0,
            is_active: Boolean(activeEl && "checked" in activeEl ? activeEl.checked : true),
        };
    }

    function renderContractorSubTabs() {
        const active = activeReportCatalog();
        return `
            <div class="contractor-catalog-subtabs" role="tablist" aria-label="کاتالوگ‌های گزارش پیمانکار">
                ${CATALOG_SPECS.map((spec) => {
                    const isActive = spec.key === active;
                    const rows = rowsFor(spec.key);
                    const activeCount = rows.filter((row) => Boolean(row.is_active)).length;
                    return `
                        <button
                            type="button"
                            class="contractor-catalog-subtab ${isActive ? "active" : ""}"
                            data-contractor-catalog-action="switch-catalog"
                            data-catalog-type="${esc(spec.key)}"
                            role="tab"
                            aria-selected="${isActive ? "true" : "false"}"
                        >
                            <span class="material-icons-round">${esc(spec.icon)}</span>
                            <span>${esc(spec.navTitle || spec.title)}</span>
                            <small>${activeCount}/${rows.length}</small>
                        </button>
                    `;
                }).join("")}
            </div>
        `;
    }

    function statusFilterButton(status, label) {
        const active = statusFilterValue() === status;
        return `
            <button
                type="button"
                class="contractor-catalog-filter-btn ${active ? "active" : ""}"
                data-contractor-catalog-action="set-status-filter"
                data-status-filter="${esc(status)}"
            >
                ${esc(label)}
            </button>
        `;
    }

    function renderContractorCatalogDrawer() {
        const spec = activeReportSpec();
        const editing = state.contractor.editingItem || {};
        const isOpen = state.contractor.editingItem !== null;
        const isEditing = Number(editing.id || 0) > 0;
        const canUpdate = canUpdateSettings();
        return `
            <div class="contractor-settings-drawer" data-contractor-catalog-drawer ${isOpen ? "" : "hidden"}>
                <div class="contractor-settings-drawer-backdrop" data-contractor-catalog-action="close-drawer"></div>
                <section class="contractor-settings-drawer-panel" data-catalog-type="${esc(spec.key)}" role="dialog" aria-modal="true" aria-label="${esc(isEditing ? "ویرایش آیتم" : "افزودن آیتم")}">
                    <div class="contractor-settings-drawer-header">
                        <div>
                            <h3 data-catalog-form-title>${isEditing ? "ویرایش آیتم" : "افزودن آیتم جدید"}</h3>
                            <p>${esc(spec.navTitle || spec.title)}</p>
                        </div>
                        <button type="button" class="btn-archive-icon" data-contractor-catalog-action="close-drawer" title="بستن">
                            <span class="material-icons-round">close</span>
                        </button>
                    </div>
                    <div class="contractor-settings-drawer-body">
                        <input type="hidden" data-catalog-form-field="id" value="${esc(editing.id || "")}">
                        <div class="module-crud-form-grid">
                            <div class="module-crud-form-field">
                                <label>کد</label>
                                <input class="module-crud-input" data-catalog-form-field="code" type="text" value="${esc(editing.code || "")}" ${canUpdate ? "" : "disabled"}>
                            </div>
                            <div class="module-crud-form-field">
                                <label>عنوان</label>
                                <input class="module-crud-input" data-catalog-form-field="label" type="text" value="${esc(editing.label || "")}" ${canUpdate ? "" : "disabled"}>
                            </div>
                            <div class="module-crud-form-field">
                                <label>ترتیب</label>
                                <input class="module-crud-input" data-catalog-form-field="sort_order" type="number" min="0" step="1" value="${esc(editing.sort_order ?? nextSortOrder(spec.key))}" ${canUpdate ? "" : "disabled"}>
                            </div>
                            <div class="module-crud-form-field contractor-settings-checkbox-field">
                                <label class="contractor-settings-checkbox-wrap">
                                    <input data-catalog-form-field="is_active" type="checkbox" ${editing.is_active === false ? "" : "checked"} ${canUpdate ? "" : "disabled"}>
                                    <span>فعال باشد</span>
                                </label>
                            </div>
                        </div>
                    </div>
                    <div class="contractor-settings-drawer-footer">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="close-drawer">لغو</button>
                        ${canUpdate ? `<button type="button" class="btn btn-primary" data-contractor-catalog-action="save-item">ذخیره</button>` : ""}
                    </div>
                </section>
            </div>
        `;
    }

    function renderContractorBulkDrawer() {
        const catalogType = state.contractor.bulkCatalog;
        const spec = specFor(catalogType);
        const isOpen = Boolean(catalogType && spec && canBulkAddCatalog(catalogType));
        const canUpdate = canUpdateSettings();
        return `
            <div class="contractor-settings-drawer" data-contractor-bulk-catalog-drawer ${isOpen ? "" : "hidden"}>
                <div class="contractor-settings-drawer-backdrop" data-contractor-catalog-action="close-bulk-drawer"></div>
                <section class="contractor-settings-drawer-panel contractor-settings-bulk-panel" data-bulk-catalog-type="${esc(catalogType || "")}" role="dialog" aria-modal="true" aria-label="${esc("افزودن گروهی")}">
                    <div class="contractor-settings-drawer-header">
                        <div>
                            <h3>افزودن گروهی</h3>
                            <p>${esc(spec?.navTitle || spec?.title || "")}</p>
                        </div>
                        <button type="button" class="btn-archive-icon" data-contractor-catalog-action="close-bulk-drawer" title="بستن">
                            <span class="material-icons-round">close</span>
                        </button>
                    </div>
                    <div class="contractor-settings-drawer-body">
                        <div class="contractor-settings-bulk-hint">
                            <strong>هر آیتم در یک خط</strong>
                            <span>فرمت پیشنهادی: <code>CODE | عنوان | ترتیب</code>. اگر کد ننویسید، سیستم کد خودکار می‌سازد.</span>
                        </div>
                        <textarea
                            class="module-crud-textarea contractor-settings-bulk-textarea"
                            data-bulk-catalog-field="items"
                            rows="12"
                            placeholder="MAT-001 | سیمان تیپ ۲ | 10&#10;MAT-002 | میلگرد A3 | 20&#10;شن و ماسه"
                            ${canUpdate ? "" : "disabled"}
                        ></textarea>
                        <label class="contractor-settings-checkbox-wrap contractor-settings-bulk-overwrite">
                            <input type="checkbox" data-bulk-catalog-field="overwrite_existing" ${canUpdate ? "" : "disabled"}>
                            <span>کدهای تکراری به‌روزرسانی شوند</span>
                        </label>
                    </div>
                    <div class="contractor-settings-drawer-footer">
                        <button type="button" class="btn btn-secondary" data-contractor-catalog-action="close-bulk-drawer">لغو</button>
                        ${canUpdate ? `<button type="button" class="btn btn-primary" data-contractor-catalog-action="save-bulk-items">ثبت گروهی</button>` : ""}
                    </div>
                </section>
            </div>
        `;
    }

    function renderContractorCatalogPanel() {
        const spec = activeReportSpec();
        const rows = rowsFor(spec.key);
        const filteredRows = filteredRowsFor(spec.key);
        const activeCount = rows.filter((row) => Boolean(row.is_active)).length;
        const inactiveCount = rows.length - activeCount;
        const canUpdate = canUpdateSettings();
        return `
            <section class="general-settings-card contractor-settings-card contractor-settings-card-wide contractor-report-catalog-panel" data-catalog-type="${esc(spec.key)}" role="tabpanel">
                <div class="contractor-settings-card-head">
                    <div>
                        <h3 class="general-settings-title">
                            <span class="material-icons-round">${esc(spec.icon)}</span>
                            ${esc(spec.title)}
                        </h3>
                        <p class="contractor-settings-card-subtitle">${esc(spec.subtitle)}</p>
                    </div>
                    <div class="contractor-settings-card-meta">
                        <span class="doc-muted-pill">کل: ${rows.length}</span>
                        <span class="doc-muted-pill">فعال: ${activeCount}</span>
                        <span class="doc-muted-pill">غیرفعال: ${inactiveCount}</span>
                        ${canUpdate ? "" : `<span class="doc-muted-pill">فقط مشاهده</span>`}
                    </div>
                </div>

                <div class="contractor-catalog-toolbar">
                    <div class="module-crud-form-field contractor-catalog-search">
                        <label>جستجو</label>
                        <input
                            class="module-crud-input"
                            data-contractor-catalog-search
                            type="search"
                            value="${esc(state.contractor.searchText)}"
                            placeholder="جستجو در ${esc(spec.navTitle || spec.title)}..."
                        >
                    </div>
                    <div class="contractor-catalog-filter-group" role="group" aria-label="فیلتر وضعیت">
                        ${statusFilterButton("all", "همه")}
                        ${statusFilterButton("active", "فعال")}
                        ${statusFilterButton("inactive", "غیرفعال")}
                    </div>
                    ${canUpdate ? `
                        ${canBulkAddCatalog(spec.key) ? `
                            <button type="button" class="btn btn-secondary contractor-catalog-add-btn" data-contractor-catalog-action="open-bulk-drawer">
                                <span class="material-icons-round">playlist_add</span>
                                افزودن گروهی
                            </button>
                        ` : ""}
                        <button type="button" class="btn btn-primary contractor-catalog-add-btn" data-contractor-catalog-action="open-drawer">
                            <span class="material-icons-round">add</span>
                            افزودن
                        </button>
                    ` : ""}
                </div>

                <div class="module-crud-table-wrap contractor-catalog-table-wrap">
                    <table class="module-crud-table">
                        <thead>
                            <tr>
                                <th>کد</th>
                                <th>عنوان</th>
                                <th>ترتیب</th>
                                <th>وضعیت</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>${renderTableRows(spec.key, filteredRows, spec.empty)}</tbody>
                    </table>
                </div>
            </section>
        `;
    }

    async function loadLegacyCatalogs(force = false) {
        if (state.loading && !force) return false;
        const root = getContractorRoot();
        if (!(root instanceof HTMLElement)) return false;
        state.loading = true;
        root.classList.add("is-loading");
        try {
            const legacyPayload = await request(LEGACY_ENDPOINT);
            state.catalogs = legacyPayload.catalogs || {
                role: [],
                work_section: [],
                equipment: [],
                material: [],
                equipment_status: [],
                attachment_type: [],
                issue_type: [],
                shift: [],
                weather: [],
            };
            renderLegacyCatalogs();
            return true;
        } catch (error) {
            notify("error", error.message || "بارگذاری فهرست‌های گزارش کارگاهی ناموفق بود.");
            return false;
        } finally {
            state.loading = false;
            root.classList.remove("is-loading");
        }
    }

    async function loadActivityCatalog(force = false) {
        if (state.loading && !force) return false;
        const root = getActivityRoot();
        if (!(root instanceof HTMLElement)) return false;
        state.loading = true;
        root.classList.add("is-loading");
        try {
            const activityPayload = await request(`${ACTIVITY_ENDPOINT}${toQuery(state.activity.filters)}`);
            state.activity.items = asArray(activityPayload.items);
            state.activity.projects = asArray(activityPayload.projects);
            state.activity.organizations = asArray(activityPayload.organizations);
            state.activity.pmsTemplates = asArray(activityPayload.pms_templates);
            state.activity.pmsSummary = activityPayload.pms_summary || { total: state.activity.items.length, mapped: 0, none: 0, stale: 0 };
            const visibleIds = new Set(state.activity.items.map((row) => Number(row.id || 0)).filter((id) => id > 0));
            state.activity.selectedIds.forEach((id) => {
                if (!visibleIds.has(id)) state.activity.selectedIds.delete(id);
            });
            renderActivityCatalog();
            const activityCard = getActivityCard();
            if (activityCard instanceof HTMLElement) {
                resetActivityForm(activityCard);
            }
            return true;
        } catch (error) {
            notify("error", error.message || "بارگذاری کاتالوگ فعالیت‌های اجرایی ناموفق بود.");
            return false;
        } finally {
            state.loading = false;
            root.classList.remove("is-loading");
        }
    }

    async function saveItem(card) {
        if (!(card instanceof HTMLElement)) return false;
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const payload = readFormValues(card);
        const spec = specFor(payload.catalog_type);
        if (!payload.code) {
            notify("error", "کد آیتم الزامی است.");
            return false;
        }
        if (!payload.label) {
            notify("error", "عنوان آیتم الزامی است.");
            return false;
        }
        try {
            await request(`${LEGACY_ENDPOINT}/upsert`, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify("success", `${spec?.title || "فهرست"} با موفقیت ذخیره شد.`);
            state.contractor.editingItem = null;
            await loadLegacyCatalogs(true);
            return true;
        } catch (error) {
            notify("error", error.message || "ذخیره آیتم ناموفق بود.");
            return false;
        }
    }

    async function saveBulkItems(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "Ø´Ù…Ø§ Ø¯Ø³ØªØ±Ø³ÛŒ ØªØºÛŒÛŒØ± ØªÙ†Ø¸ÛŒÙ…Ø§Øª Ø±Ø§ Ù†Ø¯Ø§Ø±ÛŒØ¯.");
            return false;
        }
        const catalogType = String(state.contractor.bulkCatalog || activeReportCatalog() || "").trim();
        if (!canBulkAddCatalog(catalogType)) {
            notify("error", "افزودن گروهی فقط برای مصالح و تجهیزات فعال است.");
            return false;
        }
        const drawer = getContractorRoot()?.querySelector?.("[data-contractor-bulk-catalog-drawer]");
        const textarea = drawer?.querySelector?.("[data-bulk-catalog-field='items']");
        const overwriteEl = drawer?.querySelector?.("[data-bulk-catalog-field='overwrite_existing']");
        const items = parseBulkCatalogItems(textarea && "value" in textarea ? textarea.value : "");
        if (!items.length) {
            notify("error", "حداقل یک آیتم معتبر وارد کنید.");
            return false;
        }
        actionEl?.setAttribute?.("disabled", "disabled");
        try {
            const payload = await request(`${LEGACY_ENDPOINT}/bulk-upsert`, {
                method: "POST",
                body: JSON.stringify({
                    catalog_type: catalogType,
                    items,
                    overwrite_existing: Boolean(overwriteEl && "checked" in overwriteEl ? overwriteEl.checked : false),
                }),
            });
            const created = Number(payload.created || 0);
            const updated = Number(payload.updated || 0);
            const skipped = Number(payload.skipped || 0);
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify(skipped > 0 ? "warning" : "success", `ثبت گروهی انجام شد: ${created} جدید، ${updated} به‌روزرسانی، ${skipped} رد شده.`);
            if (skipped > 0 && Array.isArray(payload.errors)) {
                console.warn("site log catalog bulk skipped rows:", payload.errors);
            }
            state.contractor.bulkCatalog = null;
            await loadLegacyCatalogs(true);
            return true;
        } catch (error) {
            notify("error", error.message || "ثبت گروهی ناموفق بود.");
            return false;
        } finally {
            actionEl?.removeAttribute?.("disabled");
        }
    }

    async function deleteItem(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const catalogType = String(actionEl.dataset.catalogType || "").trim();
        const itemId = Number(actionEl.dataset.itemId || 0);
        const itemLabel = norm(actionEl.dataset.itemLabel || "");
        const spec = specFor(catalogType);
        if (!catalogType || itemId <= 0) return false;
        const ok = window.confirm(`آیتم «${itemLabel || itemId}» از ${spec?.title || "فهرست"} غیرفعال شود؟`);
        if (!ok) return false;
        try {
            await request(`${LEGACY_ENDPOINT}/delete`, {
                method: "POST",
                body: JSON.stringify({ catalog_type: catalogType, id: itemId }),
            });
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify("success", "آیتم غیرفعال شد.");
            await loadLegacyCatalogs(true);
            return true;
        } catch (error) {
            notify("error", error.message || "حذف آیتم ناموفق بود.");
            return false;
        }
    }

    async function toggleItemActive(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const catalogType = String(actionEl.dataset.catalogType || "").trim();
        const itemId = Number(actionEl.dataset.itemId || 0);
        const code = upper(actionEl.dataset.itemCode || "");
        const label = norm(actionEl.dataset.itemLabel || "");
        const sortOrder = Number(actionEl.dataset.itemSortOrder || 0);
        const isActive = String(actionEl.dataset.itemIsActive || "") === "1";
        const spec = specFor(catalogType);
        if (!catalogType || itemId <= 0 || !code || !label) return false;

        if (isActive) {
            return deleteItem(actionEl);
        }

        try {
            await request(`${LEGACY_ENDPOINT}/upsert`, {
                method: "POST",
                body: JSON.stringify({
                    catalog_type: catalogType,
                    id: itemId,
                    code,
                    label,
                    sort_order: Number.isFinite(sortOrder) ? sortOrder : 0,
                    is_active: true,
                }),
            });
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify("success", `${spec?.title || "آیتم"} فعال شد.`);
            await loadLegacyCatalogs(true);
            return true;
        } catch (error) {
            notify("error", error.message || "فعال‌سازی آیتم ناموفق بود.");
            return false;
        }
    }

    async function saveActivity(card) {
        if (!(card instanceof HTMLElement)) return false;
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const payload = readActivityFormValues(card);
        if (!payload.project_code) {
            notify("error", "پروژه فعالیت اجرایی الزامی است.");
            return false;
        }
        if (!payload.activity_code) {
            notify("error", "کد فعالیت الزامی است.");
            return false;
        }
        if (!payload.activity_title) {
            notify("error", "عنوان فعالیت الزامی است.");
            return false;
        }
        try {
            await request(`${ACTIVITY_ENDPOINT}/upsert`, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify("success", "فعالیت اجرایی با موفقیت ذخیره شد.");
            state.activity.editingActivity = null;
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "ذخیره فعالیت اجرایی ناموفق بود.");
            return false;
        }
    }

    async function deleteActivity(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const itemId = Number(actionEl.dataset.itemId || 0);
        const itemLabel = norm(actionEl.dataset.itemLabel || "");
        if (itemId <= 0) return false;
        const ok = window.confirm(`فعالیت «${itemLabel || itemId}» غیرفعال شود؟`);
        if (!ok) return false;
        try {
            await request(`${ACTIVITY_ENDPOINT}/delete`, {
                method: "POST",
                body: JSON.stringify({ id: itemId }),
            });
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify("success", "فعالیت اجرایی غیرفعال شد.");
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "حذف فعالیت اجرایی ناموفق بود.");
            return false;
        }
    }

    async function toggleActivityActive(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const isActive = String(actionEl.dataset.itemIsActive || "") === "1";
        if (isActive) {
            return deleteActivity(actionEl);
        }
        const payload = {
            id: Number(actionEl.dataset.itemId || 0) || null,
            project_code: upper(actionEl.dataset.projectCode || ""),
            organization_id: Number(actionEl.dataset.organizationId || 0) || null,
            organization_contract_id: Number(actionEl.dataset.organizationContractId || 0) || null,
            activity_code: upper(actionEl.dataset.activityCode || ""),
            activity_title: norm(actionEl.dataset.activityTitle || ""),
            default_location: norm(actionEl.dataset.defaultLocation || ""),
            default_unit: norm(actionEl.dataset.defaultUnit || ""),
            sort_order: Number(actionEl.dataset.sortOrder || 0) || 0,
            is_active: true,
        };
        if (!payload.id || !payload.project_code || !payload.activity_code || !payload.activity_title) return false;
        try {
            await request(`${ACTIVITY_ENDPOINT}/upsert`, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify("success", "فعالیت اجرایی فعال شد.");
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "فعال‌سازی فعالیت اجرایی ناموفق بود.");
            return false;
        }
    }

    async function importActivityExcel(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const root = getActivityRoot();
        if (!(root instanceof HTMLElement)) return false;
        const input = root.querySelector("[data-activity-import-file]");
        const file = input instanceof HTMLInputElement && input.files && input.files.length ? input.files[0] : null;
        const projectCode = upper(state.activity.filters.project_code);
        const organizationId = Number(state.activity.filters.organization_id || 0) || null;
        const contractId = Number(state.activity.filters.organization_contract_id || 0) || null;
        if (!projectCode) {
            notify("error", "برای ایمپورت فعالیت‌ها ابتدا فیلتر پروژه را انتخاب کنید.");
            return false;
        }
        if (!file) {
            notify("error", "ابتدا فایل Excel فعالیت‌ها را انتخاب کنید.");
            return false;
        }
        if (!String(file.name || "").toLowerCase().endsWith(".xlsx")) {
            notify("error", "فرمت فایل باید .xlsx باشد.");
            return false;
        }
        const formData = new FormData();
        formData.append("project_code", projectCode);
        if (organizationId) formData.append("organization_id", String(organizationId));
        if (contractId) formData.append("organization_contract_id", String(contractId));
        formData.append("file", file);
        actionEl?.setAttribute?.("disabled", "disabled");
        root.classList.add("is-loading");
        try {
            const payload = await request(`${ACTIVITY_ENDPOINT}/import`, {
                method: "POST",
                body: formData,
            });
            const created = Number(payload.created || 0);
            const updated = Number(payload.updated || 0);
            const skipped = Number(payload.skipped || 0);
            if (input instanceof HTMLInputElement) input.value = "";
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            const message = `ایمپورت انجام شد: ${created} ردیف جدید، ${updated} ردیف بروزرسانی، ${skipped} ردیف رد شده.`;
            notify(skipped > 0 ? "warning" : "success", message);
            if (skipped > 0 && Array.isArray(payload.errors)) {
                console.warn("site log activity import skipped rows:", payload.errors);
            }
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "ایمپورت فعالیت‌ها ناموفق بود.");
            return false;
        } finally {
            root.classList.remove("is-loading");
            actionEl?.removeAttribute?.("disabled");
        }
    }

    async function downloadActivityTemplate(actionEl) {
        actionEl?.setAttribute?.("disabled", "disabled");
        const fetcher = typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : window.fetch.bind(window);
        try {
            const response = await fetcher(`${ACTIVITY_ENDPOINT}/template`);
            if (!response.ok) {
                let message = `دانلود تمپلت ناموفق بود (${response.status})`;
                try {
                    const payload = await response.clone().json();
                    message = payload.detail || payload.message || message;
                } catch (_) {}
                throw new Error(message);
            }
            const blob = await response.blob();
            const contentDisposition = String(response.headers.get("content-disposition") || "");
            let filename = "site_log_activity_catalog_template.xlsx";
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
            const anchor = document.createElement("a");
            anchor.href = objectUrl;
            anchor.download = filename;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(objectUrl);
            notify("success", "تمپلت Excel فعالیت‌ها دانلود شد.");
            return true;
        } catch (error) {
            notify("error", error.message || "دانلود تمپلت فعالیت‌ها ناموفق بود.");
            return false;
        } finally {
            actionEl?.removeAttribute?.("disabled");
        }
    }

    function getPmsTemplateCard() {
        return getActivityRoot()?.querySelector('[data-catalog-type="pms-template"]') || null;
    }

    function getPmsTemplateFormScope() {
        return getActivityRoot()?.querySelector("[data-pms-template-form-scope]") || null;
    }

    function setPmsTemplateFormValues(values = {}) {
        openPmsTemplateDrawer(values);
    }

    function readPmsTemplateFormValues() {
        const card = getPmsTemplateFormScope();
        const readValue = (field) => {
            const el = card?.querySelector?.(`[data-pms-template-field="${field}"]`);
            return el && "value" in el ? el.value : "";
        };
        const activeEl = card?.querySelector?.('[data-pms-template-field="is_active"]');
        const steps = readCurrentPmsStepRows();
        const id = Number(readValue("id") || 0);
        return {
            id: id > 0 ? id : null,
            code: upper(readValue("code")),
            title: norm(readValue("title")),
            sort_order: Number(readValue("sort_order") || 0) || 0,
            is_active: Boolean(activeEl && "checked" in activeEl ? activeEl.checked : true),
            steps,
        };
    }

    async function savePmsTemplate() {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const payload = readPmsTemplateFormValues();
        if (!payload.code || !payload.title) {
            notify("error", "کد و عنوان PMS Template الزامی است.");
            return false;
        }
        if (!payload.steps.length) {
            notify("error", "حداقل یک Step برای PMS Template وارد کنید.");
            return false;
        }
        try {
            await request(`${PMS_ENDPOINT}/templates/upsert`, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            notify("success", "PMS Template ذخیره شد.");
            state.activity.editingPmsTemplate = null;
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "ذخیره PMS Template ناموفق بود.");
            return false;
        }
    }

    async function deletePmsTemplate(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const templateId = Number(actionEl.dataset.templateId || 0);
        const title = norm(actionEl.dataset.templateTitle || "");
        if (templateId <= 0) return false;
        if (!window.confirm(`PMS Template «${title || templateId}» غیرفعال شود؟`)) return false;
        try {
            await request(`${PMS_ENDPOINT}/templates/delete`, {
                method: "POST",
                body: JSON.stringify({ id: templateId }),
            });
            notify("success", "PMS Template غیرفعال شد.");
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "حذف PMS Template ناموفق بود.");
            return false;
        }
    }

    async function togglePmsTemplateActive(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const isActive = String(actionEl.dataset.templateIsActive || "") === "1";
        if (isActive) {
            return deletePmsTemplate(actionEl);
        }
        const templateId = Number(actionEl.dataset.templateId || 0);
        const steps = parsePmsStepsText(actionEl.dataset.templateSteps || "");
        if (templateId <= 0 || !steps.length) return false;
        try {
            await request(`${PMS_ENDPOINT}/templates/upsert`, {
                method: "POST",
                body: JSON.stringify({
                    id: templateId,
                    code: upper(actionEl.dataset.templateCode || ""),
                    title: norm(actionEl.dataset.templateTitle || ""),
                    sort_order: Number(actionEl.dataset.templateSortOrder || 0) || 0,
                    is_active: true,
                    steps,
                }),
            });
            notify("success", "PMS Template فعال شد.");
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "فعال‌سازی PMS Template ناموفق بود.");
            return false;
        }
    }

    async function applyPmsToActivities(activityIds, templateId, overwrite = false) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const ids = asArray(activityIds).map((id) => Number(id || 0)).filter((id) => id > 0);
        if (!ids.length) {
            notify("error", "حداقل یک Activity را انتخاب کنید.");
            return false;
        }
        if (Number(templateId || 0) <= 0) {
            notify("error", "PMS Template را انتخاب کنید.");
            return false;
        }
        try {
            await request(`${PMS_ENDPOINT}/mappings/apply`, {
                method: "POST",
                body: JSON.stringify({ activity_ids: ids, template_id: Number(templateId), overwrite: Boolean(overwrite) }),
            });
            notify("success", "PMS روی Activityهای انتخابی اعمال شد.");
            state.activity.selectedIds.clear();
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "اعمال PMS ناموفق بود.");
            return false;
        }
    }

    async function choosePmsForActivity(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const activityId = Number(actionEl.dataset.itemId || 0);
        if (activityId <= 0) return false;
        const choices = pmsTemplates().map((row) => `${row.id}: ${upper(row.code || "")} - ${norm(row.title || "")}`).join("\n");
        const raw = window.prompt(`PMS Template را انتخاب کنید:\n${choices}`, "");
        if (raw == null) return false;
        const templateId = Number(String(raw).split(":")[0].trim() || raw);
        const overwrite = true;
        return applyPmsToActivities([activityId], templateId, overwrite);
    }

    async function deletePmsFromActivity(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const activityId = Number(actionEl.dataset.itemId || 0);
        if (activityId <= 0) return false;
        if (!window.confirm("PMS این Activity حذف شود؟")) return false;
        try {
            await request(`${PMS_ENDPOINT}/mappings/delete`, {
                method: "POST",
                body: JSON.stringify({ activity_id: activityId }),
            });
            notify("success", "PMS حذف شد.");
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "حذف PMS ناموفق بود.");
            return false;
        }
    }

    async function reapplyPmsActivities(activityIds) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const ids = asArray(activityIds).map((id) => Number(id || 0)).filter((id) => id > 0);
        if (!ids.length) return false;
        try {
            await request(`${PMS_ENDPOINT}/mappings/reapply`, {
                method: "POST",
                body: JSON.stringify({ activity_ids: ids }),
            });
            notify("success", "Reapply انجام شد.");
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "Reapply ناموفق بود.");
            return false;
        }
    }

    async function downloadPmsMappingFile(actionEl, templateOnly = false) {
        actionEl?.setAttribute?.("disabled", "disabled");
        const fetcher = typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : window.fetch.bind(window);
        const url = templateOnly ? `${PMS_ENDPOINT}/mappings/template` : `${PMS_ENDPOINT}/mappings/export${toQuery(state.activity.filters)}`;
        try {
            const response = await fetcher(url);
            if (!response.ok) throw new Error(`Download failed (${response.status})`);
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = objectUrl;
            anchor.download = templateOnly ? "site_log_pms_mapping_template.xlsx" : "site_log_pms_mappings.xlsx";
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(objectUrl);
            return true;
        } catch (error) {
            notify("error", error.message || "دانلود فایل PMS ناموفق بود.");
            return false;
        } finally {
            actionEl?.removeAttribute?.("disabled");
        }
    }

    async function importPmsMapping(actionEl) {
        if (!canUpdateSettings()) {
            notify("error", "شما دسترسی تغییر تنظیمات را ندارید.");
            return false;
        }
        const root = getActivityRoot();
        if (!(root instanceof HTMLElement)) return false;
        const input = root.querySelector("[data-pms-mapping-import-file]");
        const file = input instanceof HTMLInputElement && input.files && input.files.length ? input.files[0] : null;
        const projectCode = upper(state.activity.filters.project_code);
        if (!projectCode) {
            notify("error", "برای Import PMS ابتدا پروژه را انتخاب کنید.");
            return false;
        }
        if (!file) {
            notify("error", "ابتدا فایل Excel Mapping را انتخاب کنید.");
            return false;
        }
        const overwrite = window.confirm("اگر Activity قبلاً PMS داشته باشد، Mapping جدید جایگزین شود؟");
        const formData = new FormData();
        formData.append("project_code", projectCode);
        if (state.activity.filters.organization_id) formData.append("organization_id", String(state.activity.filters.organization_id));
        if (state.activity.filters.organization_contract_id) formData.append("organization_contract_id", String(state.activity.filters.organization_contract_id));
        formData.append("overwrite", overwrite ? "true" : "false");
        formData.append("file", file);
        actionEl?.setAttribute?.("disabled", "disabled");
        try {
            const payload = await request(`${PMS_ENDPOINT}/mappings/import`, { method: "POST", body: formData });
            notify(Number(payload.skipped || 0) > 0 ? "warning" : "success", `Import PMS انجام شد: ${Number(payload.imported || 0)} موفق، ${Number(payload.skipped || 0)} رد شده.`);
            if (input instanceof HTMLInputElement) input.value = "";
            await loadActivityCatalog(true);
            return true;
        } catch (error) {
            notify("error", error.message || "Import PMS ناموفق بود.");
            return false;
        } finally {
            actionEl?.removeAttribute?.("disabled");
        }
    }

    function bindActions() {
        if (state.bound) return;

        document.addEventListener("click", (event) => {
            const actionEl = event?.target?.closest?.("[data-contractor-catalog-action]");
            if (!(actionEl instanceof HTMLElement)) return;

            const contractorRoot = getContractorRoot();
            const activityRoot = getActivityRoot();
            const insideContractor = contractorRoot && (contractorRoot.contains(actionEl) || actionEl.closest("#view-contractor-settings"));
            const insideActivity = activityRoot && (activityRoot.contains(actionEl) || actionEl.closest("#consultant-settings-tab-site-log-activity"));
            if (!insideContractor && !insideActivity) return;

            const action = String(actionEl.dataset.contractorCatalogAction || "").trim();
            const card = actionEl.closest("[data-catalog-type]");

            if (action === "refresh") {
                if (insideActivity) {
                    void loadActivityCatalog(true);
                } else {
                    void loadLegacyCatalogs(true);
                }
                return;
            }
            if (insideActivity && action === "switch-activity-subtab") {
                state.activity.activeSubTab = normalizeActivitySubTab(actionEl.dataset.activitySubtab || "");
                state.activity.editingActivity = null;
                state.activity.editingPmsTemplate = null;
                renderActivityCatalog();
                return;
            }
            if (insideActivity && action === "set-activity-status-filter") {
                state.activity.statusFilter = String(actionEl.dataset.statusFilter || "all");
                renderActivityCatalog();
                return;
            }
            if (insideActivity && action === "open-activity-drawer") {
                openActivityDrawer();
                return;
            }
            if (insideActivity && action === "close-activity-drawer") {
                closeActivityDrawer();
                return;
            }
            if (insideActivity && action === "open-pms-template-drawer") {
                openPmsTemplateDrawer();
                return;
            }
            if (insideActivity && action === "close-pms-template-drawer") {
                closePmsTemplateDrawer();
                return;
            }
            if (insideActivity && action === "add-pms-step") {
                const current = readPmsTemplateFormValues();
                state.activity.editingPmsTemplate = {
                    ...current,
                    steps: asArray(current.steps).concat({
                        step_code: "",
                        step_title: "",
                        weight_pct: 0,
                        sort_order: (asArray(current.steps).length + 1) * 10,
                        is_active: true,
                    }),
                };
                renderActivityCatalog();
                return;
            }
            if (insideActivity && action === "remove-pms-step") {
                const current = readPmsTemplateFormValues();
                const removeIndex = Number(actionEl.dataset.pmsStepIndex || -1);
                const steps = asArray(current.steps).filter((_, index) => index !== removeIndex);
                state.activity.editingPmsTemplate = {
                    ...current,
                    steps: steps.length ? steps : [{ step_code: "", step_title: "", weight_pct: 100, sort_order: 10, is_active: true }],
                };
                renderActivityCatalog();
                return;
            }
            if (insideContractor && action === "switch-catalog") {
                state.contractor.activeCatalog = normalizeReportCatalog(actionEl.dataset.catalogType || "");
                state.contractor.searchText = "";
                state.contractor.statusFilter = "all";
                state.contractor.editingItem = null;
                renderLegacyCatalogs();
                return;
            }
            if (insideContractor && action === "set-status-filter") {
                state.contractor.statusFilter = String(actionEl.dataset.statusFilter || "all");
                renderLegacyCatalogs();
                return;
            }
            if (insideContractor && action === "open-drawer") {
                openContractorCatalogDrawer();
                return;
            }
            if (insideContractor && action === "close-drawer") {
                closeContractorCatalogDrawer();
                return;
            }
            if (insideContractor && action === "open-bulk-drawer") {
                openContractorBulkDrawer(actionEl.dataset.catalogType || activeReportCatalog());
                return;
            }
            if (insideContractor && action === "close-bulk-drawer") {
                closeContractorBulkDrawer();
                return;
            }
            if (insideContractor && action === "save-bulk-items") {
                void saveBulkItems(actionEl);
                return;
            }
            if (action === "delete-activity") {
                void deleteActivity(actionEl);
                return;
            }
            if (action === "toggle-activity-active") {
                void toggleActivityActive(actionEl);
                return;
            }
            if (action === "import-activity-excel") {
                void importActivityExcel(actionEl);
                return;
            }
            if (action === "download-activity-template") {
                void downloadActivityTemplate(actionEl);
                return;
            }
            if (action === "download-pms-mapping-template") {
                void downloadPmsMappingFile(actionEl, true);
                return;
            }
            if (action === "export-pms-mapping") {
                void downloadPmsMappingFile(actionEl, false);
                return;
            }
            if (action === "import-pms-mapping") {
                void importPmsMapping(actionEl);
                return;
            }
            if (action === "save-pms-template") {
                void savePmsTemplate();
                return;
            }
            if (action === "reset-pms-template") {
                closePmsTemplateDrawer();
                return;
            }
            if (action === "edit-pms-template") {
                openPmsTemplateDrawer({
                    id: Number(actionEl.dataset.templateId || 0),
                    code: actionEl.dataset.templateCode || "",
                    title: actionEl.dataset.templateTitle || "",
                    sort_order: Number(actionEl.dataset.templateSortOrder || 0),
                    is_active: String(actionEl.dataset.templateIsActive || "") === "1",
                    steps: actionEl.dataset.templateSteps || "",
                });
                return;
            }
            if (action === "delete-pms-template") {
                void deletePmsTemplate(actionEl);
                return;
            }
            if (action === "toggle-pms-template-active") {
                void togglePmsTemplateActive(actionEl);
                return;
            }
            if (action === "pms-activity") {
                void choosePmsForActivity(actionEl);
                return;
            }
            if (action === "delete-pms-activity") {
                void deletePmsFromActivity(actionEl);
                return;
            }
            if (action === "reapply-pms-activity") {
                void reapplyPmsActivities([Number(actionEl.dataset.itemId || 0)]);
                return;
            }
            if (action === "bulk-apply-pms") {
                const root = getActivityRoot();
                const templateSelect = root?.querySelector?.("[data-pms-bulk-template]");
                const overwriteEl = root?.querySelector?.("[data-pms-bulk-overwrite]");
                void applyPmsToActivities(
                    Array.from(state.activity.selectedIds),
                    templateSelect && "value" in templateSelect ? templateSelect.value : "",
                    Boolean(overwriteEl && "checked" in overwriteEl ? overwriteEl.checked : false)
                );
                return;
            }
            if (action === "quick-without-pms") {
                state.activity.filters.pms_status = "none";
                void loadActivityCatalog(true);
                return;
            }
            if (action === "quick-pms-filter") {
                state.activity.filters.pms_status = String(actionEl.dataset.pmsStatus || "");
                void loadActivityCatalog(true);
                return;
            }
            if (action === "save-activity") {
                const formScope = actionEl.closest("[data-activity-form-scope]");
                if (formScope instanceof HTMLElement) void saveActivity(formScope);
                return;
            }
            if (!(card instanceof HTMLElement)) return;

            if (action === "reset-form") {
                resetForm(card);
                return;
            }
            if (action === "save-item") {
                void saveItem(card);
                return;
            }
            if (action === "edit-item") {
                openContractorCatalogDrawer({
                    id: Number(actionEl.dataset.itemId || 0),
                    code: actionEl.dataset.itemCode || "",
                    label: actionEl.dataset.itemLabel || "",
                    sort_order: Number(actionEl.dataset.itemSortOrder || 0),
                    is_active: String(actionEl.dataset.itemIsActive || "") === "1",
                });
                return;
            }
            if (action === "toggle-item-active") {
                void toggleItemActive(actionEl);
                return;
            }
            if (action === "delete-item") {
                void deleteItem(actionEl);
                return;
            }
            if (action === "reset-activity-form") {
                resetActivityForm(card);
                return;
            }
            if (action === "save-activity") {
                const formScope = actionEl.closest("[data-activity-form-scope]");
                if (formScope instanceof HTMLElement) void saveActivity(formScope);
                return;
            }
            if (action === "edit-activity") {
                openActivityDrawer({
                    id: Number(actionEl.dataset.itemId || 0),
                    project_code: actionEl.dataset.projectCode || "",
                    organization_id: actionEl.dataset.organizationId || "",
                    organization_contract_id: actionEl.dataset.organizationContractId || "",
                    activity_code: actionEl.dataset.activityCode || "",
                    activity_title: actionEl.dataset.activityTitle || "",
                    default_location: actionEl.dataset.defaultLocation || "",
                    default_unit: actionEl.dataset.defaultUnit || "",
                    sort_order: Number(actionEl.dataset.sortOrder || 0),
                    is_active: String(actionEl.dataset.itemIsActive || "") === "1",
                });
            }
        });

        document.addEventListener("input", (event) => {
            const target = event?.target;
            if (!(target instanceof HTMLElement)) return;
            const activityRoot = getActivityRoot();
            if (activityRoot instanceof HTMLElement && activityRoot.contains(target)) {
                if (target.matches("[data-activity-search]")) {
                    state.activity.searchText = target instanceof HTMLInputElement ? target.value : "";
                    renderActivityCatalog();
                    const nextInput = getActivityRoot()?.querySelector?.("[data-activity-search]");
                    if (nextInput && typeof nextInput.focus === "function") {
                        nextInput.focus();
                        if (nextInput instanceof HTMLInputElement) {
                            const end = nextInput.value.length;
                            nextInput.setSelectionRange(end, end);
                        }
                    }
                    return;
                }
                if (target.matches("[data-pms-step-field]")) {
                    syncPmsStepWeightSummary(activityRoot);
                    return;
                }
            }
            const contractorRoot = getContractorRoot();
            if (!(contractorRoot instanceof HTMLElement) || !contractorRoot.contains(target)) return;
            if (!target.matches("[data-contractor-catalog-search]")) return;

            const nextValue = target instanceof HTMLInputElement ? target.value : "";
            state.contractor.searchText = nextValue;
            renderLegacyCatalogs();
            const nextInput = getContractorRoot()?.querySelector?.("[data-contractor-catalog-search]");
            if (nextInput && typeof nextInput.focus === "function") {
                nextInput.focus();
                if (nextInput instanceof HTMLInputElement) {
                    const end = nextInput.value.length;
                    nextInput.setSelectionRange(end, end);
                }
            }
        });

        document.addEventListener("change", (event) => {
            const target = event?.target;
            if (!(target instanceof HTMLElement)) return;
            const root = getActivityRoot();
            if (!(root instanceof HTMLElement) || !root.contains(target)) return;

            const rowSelect = target.dataset?.activityRowSelect;
            if (rowSelect) {
                const id = Number(rowSelect || 0);
                if (id > 0) {
                    if (target instanceof HTMLInputElement && target.checked) {
                        state.activity.selectedIds.add(id);
                    } else {
                        state.activity.selectedIds.delete(id);
                    }
                    renderActivityCatalog();
                }
                return;
            }

            const filterField = String(target.dataset?.contractorCatalogFilter || "").trim();
            if (filterField) {
                const value = target instanceof HTMLInputElement || target instanceof HTMLSelectElement ? target.value : "";
                state.activity.filters[filterField] = value;
                if (filterField === "organization_id") {
                    state.activity.filters.organization_contract_id = "";
                    const contractFilter = root.querySelector('[data-contractor-catalog-filter="organization_contract_id"]');
                    if (contractFilter instanceof HTMLSelectElement) {
                        contractFilter.innerHTML = renderContractOptions(value, "", "همه قراردادها");
                    }
                }
                void loadActivityCatalog(true);
                return;
            }

            const activityField = String(target.dataset?.activityFormField || "").trim();
            if (activityField === "organization_id") {
                const card = target.closest("[data-activity-form-scope]");
                if (!(card instanceof HTMLElement)) return;
                setActivityContractOptions(card, target.value || "", "");
            }

            const pmsStepField = String(target.dataset?.pmsStepField || "").trim();
            if (pmsStepField) {
                syncPmsStepWeightSummary(root);
            }
        });

        state.bound = true;
    }

    async function initContractorSiteLogCatalogs(force = false) {
        bindActions();
        return loadLegacyCatalogs(force);
    }

    async function initConsultantSiteLogActivityCatalog(force = false) {
        bindActions();
        return loadActivityCatalog(force);
    }

    window.initContractorSiteLogCatalogs = initContractorSiteLogCatalogs;
    window.initConsultantSiteLogActivityCatalog = initConsultantSiteLogActivityCatalog;

    if (window.AppEvents?.on) {
        window.AppEvents.on("view:activated", ({ viewId }) => {
            if (String(viewId || "").trim() === "view-contractor-settings") {
                void initContractorSiteLogCatalogs(false);
            }
            if (String(viewId || "").trim() === "view-consultant-settings") {
                void initConsultantSiteLogActivityCatalog(false);
            }
        });
    }

    if (document.getElementById("view-contractor-settings")?.classList.contains("active")) {
        void initContractorSiteLogCatalogs(false);
    }
    if (document.getElementById("view-consultant-settings")?.classList.contains("active")) {
        void initConsultantSiteLogActivityCatalog(false);
    }
})();
