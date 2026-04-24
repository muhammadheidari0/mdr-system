// @ts-nocheck
(() => {
    const ENDPOINT = "/api/v1/settings/site-log-catalogs";
    const CATALOG_SPECS = [
        {
            key: "role",
            title: "فهرست نقش‌ها (نفرات)",
            subtitle: "نمونه: جوشکار، لوله‌کش، برقکار",
            icon: "badge",
            empty: "هنوز آیتمی برای نقش‌های نفرات ثبت نشده است.",
        },
        {
            key: "equipment",
            title: "فهرست تجهیزات",
            subtitle: "نمونه: جرثقیل، لودر، بیل‌مکانیکی",
            icon: "construction",
            empty: "هنوز آیتمی برای تجهیزات ثبت نشده است.",
        },
        {
            key: "equipment_status",
            title: "فهرست وضعیت تجهیزات",
            subtitle: "نمونه: فعال، بیکار، در تعمیر",
            icon: "fact_check",
            empty: "هنوز آیتمی برای وضعیت تجهیزات ثبت نشده است.",
        },
    ];

    const state = {
        bound: false,
        loading: false,
        catalogs: {
            role: [],
            equipment: [],
            equipment_status: [],
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

    function getRoot() {
        return document.getElementById("contractorSiteLogCatalogsRoot");
    }

    function specFor(catalogType) {
        return CATALOG_SPECS.find((item) => item.key === String(catalogType || "").trim()) || null;
    }

    function rowsFor(catalogType) {
        return asArray(state.catalogs[String(catalogType || "").trim()]);
    }

    function nextSortOrder(catalogType) {
        const rows = rowsFor(catalogType);
        if (!rows.length) return 10;
        return rows.reduce((max, row) => Math.max(max, Number(row.sort_order || 0)), 0) + 10;
    }

    function renderStatus(isActive) {
        const active = Boolean(isActive);
        return `<span class="contractor-settings-status ${active ? "is-active" : "is-inactive"}">${active ? "فعال" : "غیرفعال"}</span>`;
    }

    function renderTableRows(catalogType, rows, emptyMessage) {
        if (!rows.length) {
            return `<tr><td colspan="5" class="center-text muted" style="padding: 18px;">${esc(emptyMessage)}</td></tr>`;
        }
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
                                >
                                    ویرایش
                                </button>
                                <button
                                    type="button"
                                    class="btn-archive-icon"
                                    data-contractor-catalog-action="delete-item"
                                    data-catalog-type="${esc(catalogType)}"
                                    data-item-id="${id}"
                                    data-item-label="${esc(label || code)}"
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

    function render() {
        const root = getRoot();
        if (!(root instanceof HTMLElement)) return;
        root.innerHTML = `
            <div class="general-settings-grid contractor-settings-grid">
                ${CATALOG_SPECS.map((spec) => renderCatalogCard(spec)).join("")}
            </div>
        `;
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

    async function loadCatalogs(force = false) {
        if (state.loading && !force) return false;
        const root = getRoot();
        if (!(root instanceof HTMLElement)) return false;
        state.loading = true;
        root.classList.add("is-loading");
        try {
            const payload = await request(ENDPOINT);
            state.catalogs = payload.catalogs || {
                role: [],
                equipment: [],
                equipment_status: [],
            };
            render();
            return true;
        } catch (error) {
            notify("error", error.message || "بارگذاری فهرست‌های گزارش کارگاهی ناموفق بود.");
            return false;
        } finally {
            state.loading = false;
            root.classList.remove("is-loading");
        }
    }

    async function saveItem(card) {
        if (!(card instanceof HTMLElement)) return false;
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
            await request(`${ENDPOINT}/upsert`, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify("success", `${spec?.title || "فهرست"} با موفقیت ذخیره شد.`);
            await loadCatalogs(true);
            return true;
        } catch (error) {
            notify("error", error.message || "ذخیره آیتم ناموفق بود.");
            return false;
        }
    }

    async function deleteItem(actionEl) {
        const catalogType = String(actionEl.dataset.catalogType || "").trim();
        const itemId = Number(actionEl.dataset.itemId || 0);
        const itemLabel = norm(actionEl.dataset.itemLabel || "");
        const spec = specFor(catalogType);
        if (!catalogType || itemId <= 0) return false;
        const ok = window.confirm(`آیتم «${itemLabel || itemId}» از ${spec?.title || "فهرست"} غیرفعال شود؟`);
        if (!ok) return false;
        try {
            await request(`${ENDPOINT}/delete`, {
                method: "POST",
                body: JSON.stringify({ catalog_type: catalogType, id: itemId }),
            });
            window.dispatchEvent(new CustomEvent("site-log-catalogs:updated"));
            notify("success", "آیتم غیرفعال شد.");
            await loadCatalogs(true);
            return true;
        } catch (error) {
            notify("error", error.message || "حذف آیتم ناموفق بود.");
            return false;
        }
    }

    function bindActions() {
        if (state.bound) return;

        document.addEventListener("click", (event) => {
            const actionEl = event?.target?.closest?.("[data-contractor-catalog-action]");
            if (!(actionEl instanceof HTMLElement)) return;

            const root = getRoot();
            const insideView = root && (root.contains(actionEl) || actionEl.closest("#view-contractor-settings"));
            if (!insideView) return;

            const action = String(actionEl.dataset.contractorCatalogAction || "").trim();
            const card = actionEl.closest("[data-catalog-type]");

            if (action === "refresh") {
                void loadCatalogs(true);
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
                setFormValues(card, {
                    id: Number(actionEl.dataset.itemId || 0),
                    code: actionEl.dataset.itemCode || "",
                    label: actionEl.dataset.itemLabel || "",
                    sort_order: Number(actionEl.dataset.itemSortOrder || 0),
                    is_active: String(actionEl.dataset.itemIsActive || "") === "1",
                });
                const codeInput = card.querySelector('[data-catalog-form-field="code"]');
                if (codeInput && typeof codeInput.focus === "function") codeInput.focus();
                return;
            }
            if (action === "delete-item") {
                void deleteItem(actionEl);
            }
        });

        state.bound = true;
    }

    async function initContractorSiteLogCatalogs(force = false) {
        bindActions();
        return loadCatalogs(force);
    }

    window.initContractorSiteLogCatalogs = initContractorSiteLogCatalogs;

    if (window.AppEvents?.on) {
        window.AppEvents.on("view:activated", ({ viewId }) => {
            if (String(viewId || "").trim() === "view-contractor-settings") {
                void initContractorSiteLogCatalogs(false);
            }
        });
    }

    if (document.getElementById("view-contractor-settings")?.classList.contains("active")) {
        void initContractorSiteLogCatalogs(false);
    }
})();
