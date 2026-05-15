// @ts-nocheck
(() => {
    const API_BASE = "/api/v1";
    const PAGE_SIZE = 50;
    const state = {
        initialized: false,
        bound: false,
        loading: false,
        skip: 0,
        limit: PAGE_SIZE,
        total: 0,
        rows: [],
        rowsByKey: {},
        debounce: 0,
    };

    function root() {
        return document.getElementById("view-edms-forms");
    }

    function esc(value) {
        return String(value == null ? "" : value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function valueOf(id) {
        const el = document.getElementById(id);
        return String(el?.value || "").trim();
    }

    function checkedOf(id) {
        const el = document.getElementById(id);
        return Boolean(el?.checked);
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = String(value == null ? "-" : value);
    }

    function upper(value) {
        return String(value || "").trim().toUpperCase();
    }

    function lower(value) {
        return String(value || "").trim().toLowerCase();
    }

    function formatNumber(value) {
        const n = Number(value || 0);
        return Number.isFinite(n) ? n.toLocaleString("fa-IR") : "0";
    }

    function formatDate(value) {
        if (!value) return "-";
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return "-";
        try {
            return new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
            }).format(d);
        } catch {
            return String(value).slice(0, 10);
        }
    }

    function dateParam(value, endOfDay = false) {
        const raw = String(value || "").trim();
        if (!raw) return "";
        if (raw.includes("T")) return raw;
        return `${raw}T${endOfDay ? "23:59:59" : "00:00:00"}`;
    }

    function formTypeLabel(value) {
        const key = upper(value);
        const map = {
            SITE_LOG: "گزارش کارگاهی",
            RFI: "RFI",
            NCR: "NCR",
            WORK_INSTRUCTION: "دستورکار",
            PERMIT_QC: "Permit/QC",
        };
        return map[key] || key || "-";
    }

    function ownerLabel(row) {
        const scope = lower(row?.owner_scope);
        if (scope === "contractor") return row.owner_label || "پیمانکار";
        if (scope === "consultant") return row.owner_label || "مشاور / کنترل";
        if (scope === "closed") return "بسته‌شده";
        return row?.owner_label || "-";
    }

    function statusClass(status) {
        const key = lower(status).replaceAll("_", "-").replaceAll(" ", "-");
        return key ? `module-crud-status is-${esc(key)}` : "module-crud-status";
    }

    function sourceKey(row) {
        return `${row?.source_type || ""}:${Number(row?.source_id || 0)}`;
    }

    function showToast(message, type = "info") {
        if (typeof window.showToast === "function") {
            window.showToast(message, type);
            return;
        }
        console[type === "error" ? "error" : "log"](message);
    }

    async function requestJson(url) {
        const fetcher = typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch;
        const res = await fetcher(url);
        if (!res || !res.ok) {
            let message = `Request failed (${res?.status || "?"})`;
            try {
                const body = await res.json();
                message = body?.detail || message;
            } catch {
                // no-op
            }
            throw new Error(message);
        }
        return res.json();
    }

    function buildQuery() {
        const params = new URLSearchParams();
        params.set("skip", String(state.skip));
        params.set("limit", String(state.limit));
        const search = valueOf("edmsFormsSearch");
        const type = valueOf("edmsFormsType");
        const owner = valueOf("edmsFormsOwner") || "all";
        const project = valueOf("edmsFormsProject");
        const discipline = valueOf("edmsFormsDiscipline");
        const status = valueOf("edmsFormsStatus");
        const from = dateParam(valueOf("edmsFormsDateFrom"));
        const to = dateParam(valueOf("edmsFormsDateTo"), true);
        if (search) params.set("search", search);
        if (type) params.set("form_type", type);
        if (owner) params.set("owner_scope", owner);
        if (project) params.set("project_code", project);
        if (discipline) params.set("discipline_code", discipline);
        if (status) params.set("status_code", status);
        if (from) params.set("date_from", from);
        if (to) params.set("date_to", to);
        if (checkedOf("edmsFormsOverdueOnly")) params.set("overdue_only", "true");
        return params.toString();
    }

    function renderSummary(summary) {
        setText("edmsFormsTotal", formatNumber(summary?.total || 0));
        setText("edmsFormsOpen", formatNumber(summary?.open || 0));
        setText("edmsFormsOverdue", formatNumber(summary?.overdue || 0));
        setText("edmsFormsContractor", formatNumber(summary?.contractor || 0));
        setText("edmsFormsConsultant", formatNumber(summary?.consultant || 0));
    }

    function renderPagination() {
        const start = state.total > 0 ? state.skip + 1 : 0;
        const end = Math.min(state.skip + state.rows.length, state.total);
        setText("edmsFormsPaginationInfo", `نمایش ${formatNumber(start)}-${formatNumber(end)} از ${formatNumber(state.total)}`);
        const prev = root()?.querySelector('[data-edms-forms-action="prev"]');
        const next = root()?.querySelector('[data-edms-forms-action="next"]');
        if (prev) prev.disabled = state.skip <= 0;
        if (next) next.disabled = state.skip + state.limit >= state.total;
    }

    function renderRows() {
        const body = document.getElementById("edmsFormsTableBody");
        if (!body) return;
        state.rowsByKey = {};
        if (state.loading) {
            body.innerHTML = `<tr><td colspan="12" class="archive-empty">در حال بارگذاری...</td></tr>`;
            return;
        }
        if (!state.rows.length) {
            body.innerHTML = `<tr><td colspan="12" class="archive-empty">فرمی یافت نشد.</td></tr>`;
            return;
        }
        body.innerHTML = state.rows.map((row) => {
            const key = sourceKey(row);
            state.rowsByKey[key] = row;
            const sourceButton = row.can_open_source
                ? `<button type="button" class="btn-archive-icon" data-edms-forms-action="open-source" data-row-key="${esc(key)}" title="باز کردن منبع"><span class="material-icons-round">open_in_new</span></button>`
                : "";
            const delay = Number(row.delay_days || 0);
            const dueText = row.due_date
                ? `${formatDate(row.due_date)}${delay > 0 ? ` / ${formatNumber(delay)} روز` : ""}`
                : "-";
            return `
                <tr>
                    <td><span class="module-crud-status is-${esc(lower(row.form_type).replaceAll("_", "-"))}">${esc(formTypeLabel(row.form_type))}</span></td>
                    <td class="edms-forms-number">${esc(row.number || "-")}</td>
                    <td class="edms-forms-title">${esc(row.title || "-")}</td>
                    <td>${esc(row.project_code || "-")}</td>
                    <td>${esc(row.discipline_code || "-")}</td>
                    <td><span class="${statusClass(row.status_code)}">${esc(row.status_code || "-")}</span></td>
                    <td>${esc(ownerLabel(row))}</td>
                    <td>${esc(formatDate(row.record_date))}</td>
                    <td>${esc(dueText)}</td>
                    <td>${formatNumber(row.attachment_count)}</td>
                    <td>${formatNumber(row.action_count)}</td>
                    <td>
                        <div class="edms-forms-row-actions">
                            <button type="button" class="btn-archive-icon" data-edms-forms-action="view-detail" data-row-key="${esc(key)}" title="مشاهده">
                                <span class="material-icons-round">visibility</span>
                            </button>
                            ${sourceButton}
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    async function loadForms(reset = false) {
        if (reset) state.skip = 0;
        state.loading = true;
        renderRows();
        try {
            const payload = await requestJson(`${API_BASE}/edms/forms/list?${buildQuery()}`);
            state.total = Number(payload?.total || 0);
            state.rows = Array.isArray(payload?.data) ? payload.data : [];
            renderSummary(payload?.summary || {});
        } catch (error) {
            state.total = 0;
            state.rows = [];
            showToast(error instanceof Error ? error.message : "خطا در بارگذاری فرم‌ها", "error");
        } finally {
            state.loading = false;
            renderRows();
            renderPagination();
        }
    }

    function detailRow(label, value) {
        return `
            <div class="edms-forms-detail-row">
                <span>${esc(label)}</span>
                <strong>${esc(value || "-")}</strong>
            </div>
        `;
    }

    function openDetail(row) {
        const drawer = document.getElementById("edmsFormsDrawer");
        const title = document.getElementById("edmsFormsDrawerTitle");
        const meta = document.getElementById("edmsFormsDrawerMeta");
        const body = document.getElementById("edmsFormsDrawerBody");
        if (!drawer || !body) return;
        if (title) title.textContent = `${formTypeLabel(row.form_type)} ${row.number || ""}`.trim();
        if (meta) meta.textContent = `${row.project_code || "-"} | ${row.discipline_code || "-"} | ${row.status_code || "-"}`;
        const sourceAction = row.can_open_source
            ? `<button type="button" class="btn-archive-icon" data-edms-forms-action="open-source" data-row-key="${esc(sourceKey(row))}">
                    <span class="material-icons-round">open_in_new</span>
                    باز کردن منبع
               </button>`
            : "";
        body.innerHTML = `
            <div class="edms-forms-detail-title">${esc(row.title || "-")}</div>
            <div class="edms-forms-detail-grid">
                ${detailRow("نوع", formTypeLabel(row.form_type))}
                ${detailRow("شماره", row.number)}
                ${detailRow("پروژه", row.project_code)}
                ${detailRow("دیسیپلین", row.discipline_code)}
                ${detailRow("وضعیت", row.status_code)}
                ${detailRow("مسئول فعلی", ownerLabel(row))}
                ${detailRow("سازمان", row.organization_name)}
                ${detailRow("تاریخ", formatDate(row.record_date))}
                ${detailRow("سررسید", formatDate(row.due_date))}
                ${detailRow("تاخیر", row.delay_days ? `${formatNumber(row.delay_days)} روز` : "-")}
                ${detailRow("پیوست", formatNumber(row.attachment_count))}
                ${detailRow("اقدام", formatNumber(row.action_count))}
            </div>
            <div class="edms-forms-detail-actions">${sourceAction}</div>
        `;
        drawer.hidden = false;
        drawer.classList.add("is-open");
    }

    function closeDetail() {
        const drawer = document.getElementById("edmsFormsDrawer");
        if (!drawer) return;
        drawer.classList.remove("is-open");
        drawer.hidden = true;
    }

    async function openSource(row) {
        if (!row?.can_open_source) {
            showToast("دسترسی باز کردن منبع برای این فرم فعال نیست.", "error");
            return;
        }
        const hub = lower(row.target_hub);
        const tab = lower(row.target_tab);
        if (!hub || !tab || typeof window.navigateTo !== "function") return;
        await window.navigateTo(`view-${hub}`);
        window.setTimeout(() => {
            if (hub === "contractor" && typeof window.openContractorTab === "function") {
                window.openContractorTab(tab);
            } else if (hub === "consultant" && typeof window.openConsultantTab === "function") {
                window.openConsultantTab(tab);
            }
            showToast(`منبع باز شد؛ شماره ${row.number || "-"} را در جدول دنبال کنید.`, "info");
        }, 80);
    }

    function resetFilters() {
        ["edmsFormsSearch", "edmsFormsType", "edmsFormsProject", "edmsFormsDiscipline", "edmsFormsStatus", "edmsFormsDateFrom", "edmsFormsDateTo"].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = "";
        });
        const owner = document.getElementById("edmsFormsOwner");
        if (owner) owner.value = "all";
        const overdue = document.getElementById("edmsFormsOverdueOnly");
        if (overdue) overdue.checked = false;
    }

    function bindEvents() {
        const container = root();
        if (!container || state.bound) return;
        container.addEventListener("click", (event) => {
            const actionEl = event.target?.closest?.("[data-edms-forms-action]");
            if (!actionEl || !container.contains(actionEl)) return;
            const action = lower(actionEl.getAttribute("data-edms-forms-action"));
            const key = actionEl.getAttribute("data-row-key") || "";
            const row = state.rowsByKey[key];
            if (action === "refresh") {
                event.preventDefault();
                void loadForms(false);
            } else if (action === "reset") {
                event.preventDefault();
                resetFilters();
                void loadForms(true);
            } else if (action === "prev") {
                event.preventDefault();
                state.skip = Math.max(0, state.skip - state.limit);
                void loadForms(false);
            } else if (action === "next") {
                event.preventDefault();
                if (state.skip + state.limit < state.total) {
                    state.skip += state.limit;
                    void loadForms(false);
                }
            } else if (action === "view-detail" && row) {
                event.preventDefault();
                openDetail(row);
            } else if (action === "open-source" && row) {
                event.preventDefault();
                void openSource(row);
            } else if (action === "close-detail") {
                event.preventDefault();
                closeDetail();
            }
        });

        ["edmsFormsType", "edmsFormsOwner", "edmsFormsProject", "edmsFormsDiscipline", "edmsFormsStatus", "edmsFormsDateFrom", "edmsFormsDateTo", "edmsFormsOverdueOnly"].forEach((id) => {
            document.getElementById(id)?.addEventListener("change", () => loadForms(true));
        });
        document.getElementById("edmsFormsSearch")?.addEventListener("input", () => {
            if (state.debounce) window.clearTimeout(state.debounce);
            state.debounce = window.setTimeout(() => loadForms(true), 350);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeDetail();
        });
        state.bound = true;
    }

    function initEdmsFormsView(forceReload = false) {
        if (!root()) return;
        bindEvents();
        if (!state.initialized || forceReload) {
            state.initialized = true;
            void loadForms(true);
        }
    }

    window.initEdmsFormsView = initEdmsFormsView;

    if (window.AppEvents?.on) {
        window.AppEvents.on("view:activated", ({ viewId }) => {
            if (String(viewId || "").trim() === "view-edms") {
                const activeTab = document.querySelector('.edms-tab-btn.active[data-edms-tab="forms"]');
                if (activeTab) initEdmsFormsView(false);
            }
        });
    }
})();
