// @ts-nocheck
import { initShamsiDateInputs } from "../../lib/shamsi_date_input";

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
        rowsById: {},
        catalog: {
            projects: [],
            meeting_types: [],
            minute_statuses: ["Draft", "Open", "Closed", "Cancelled"],
            resolution_statuses: ["Open", "In Progress", "Done", "Cancelled"],
            priorities: ["Low", "Normal", "High", "Critical"],
            users: [],
            organizations: [],
        },
        selectedMinute: null,
        resolutions: [],
        attachments: [],
        relations: { outgoing: [], incoming: [] },
        drawerTab: "info",
        editingResolutionId: null,
        debounce: 0,
    };

    function root() {
        return document.getElementById("view-meeting-minutes");
    }

    function esc(value) {
        return String(value == null ? "" : value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function lower(value) {
        return String(value || "").trim().toLowerCase();
    }

    function valueOf(id) {
        return String(document.getElementById(id)?.value || "").trim();
    }

    function checkedOf(id) {
        return Boolean(document.getElementById(id)?.checked);
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = String(value == null ? "-" : value);
    }

    function can(permission) {
        if (typeof window.hasCapability === "function") return Boolean(window.hasCapability(permission));
        return false;
    }

    function canCreate() {
        return can("meeting_minutes:create");
    }

    function canUpdate() {
        return can("meeting_minutes:update");
    }

    function canDelete() {
        return can("meeting_minutes:delete");
    }

    function canAttach() {
        return can("meeting_minutes:attachment");
    }

    function showToast(message, type = "info") {
        if (typeof window.showToast === "function") {
            window.showToast(message, type);
            return;
        }
        console[type === "error" ? "error" : "log"](message);
    }

    async function requestJson(url, options = {}) {
        const fetcher = typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch;
        const init = { ...options };
        if (init.body && !(init.body instanceof FormData)) {
            init.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
            init.body = JSON.stringify(init.body);
        }
        const res = await fetcher(url, init);
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

    function syncShamsiDates() {
        try {
            initShamsiDateInputs([
                "meetingMinutesDateFrom",
                "meetingMinutesDateTo",
                "meetingMinuteDate",
                "meetingResolutionDue",
            ]).syncAll();
        } catch {
            // Date inputs still work as Gregorian ISO values if the Jalali adapter is unavailable.
        }
    }

    function dateInputValue(value) {
        if (!value) return "";
        const raw = String(value);
        if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw.slice(0, 10);
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return "";
        return d.toISOString().slice(0, 10);
    }

    function apiDate(value) {
        const raw = String(value || "").trim();
        return raw ? `${raw}T00:00:00` : null;
    }

    function statusClass(status) {
        const key = lower(status).replaceAll("_", "-").replaceAll(" ", "-");
        return key ? `module-crud-status is-${esc(key)}` : "module-crud-status";
    }

    function selectOptions(items, selected = "", placeholder = "") {
        const head = placeholder ? `<option value="">${esc(placeholder)}</option>` : "";
        return head + (items || []).map((item) => {
            const value = typeof item === "string" ? item : (item.value ?? item.code ?? item.id ?? "");
            const label = typeof item === "string"
                ? item
                : (item.label ?? item.name ?? item.name_e ?? item.name_p ?? item.full_name ?? item.email ?? item.code ?? item.id ?? "");
            return `<option value="${esc(value)}" ${String(value) === String(selected || "") ? "selected" : ""}>${esc(label)}</option>`;
        }).join("");
    }

    function populateCatalogSelects() {
        const projectSelect = document.getElementById("meetingMinutesProject");
        if (projectSelect) {
            projectSelect.innerHTML = selectOptions(
                (state.catalog.projects || []).map((project) => ({
                    value: project.code,
                    label: `${project.code}${project.name_e || project.name_p ? ` - ${project.name_e || project.name_p}` : ""}`,
                })),
                valueOf("meetingMinutesProject"),
                "همه پروژه‌ها"
            );
        }
        const typeSelect = document.getElementById("meetingMinutesType");
        if (typeSelect) {
            typeSelect.innerHTML = selectOptions(state.catalog.meeting_types || [], valueOf("meetingMinutesType"), "همه نوع جلسه‌ها");
        }
    }

    async function loadCatalog() {
        const payload = await requestJson(`${API_BASE}/meeting-minutes/catalog`);
        state.catalog = { ...state.catalog, ...(payload || {}) };
        populateCatalogSelects();
        const createBtn = document.getElementById("meetingMinutesCreateBtn");
        if (createBtn) createBtn.style.display = canCreate() ? "" : "none";
    }

    function buildQuery() {
        const params = new URLSearchParams();
        params.set("skip", String(state.skip));
        params.set("limit", String(state.limit));
        const search = valueOf("meetingMinutesSearch");
        const project = valueOf("meetingMinutesProject");
        const type = valueOf("meetingMinutesType");
        const status = valueOf("meetingMinutesStatus");
        const responsible = valueOf("meetingMinutesResponsible");
        const from = valueOf("meetingMinutesDateFrom");
        const to = valueOf("meetingMinutesDateTo");
        if (search) params.set("search", search);
        if (project) params.set("project_code", project);
        if (type) params.set("meeting_type", type);
        if (status) params.set("status", status);
        if (responsible) params.set("responsible", responsible);
        if (from) params.set("date_from", from);
        if (to) params.set("date_to", to);
        if (checkedOf("meetingMinutesOpenResolutionsOnly")) params.set("open_resolutions_only", "true");
        if (checkedOf("meetingMinutesOverdueOnly")) params.set("overdue_only", "true");
        const hasAttachments = valueOf("meetingMinutesHasAttachments");
        const relationSearch = valueOf("meetingMinutesRelationSearch");
        const sortBy = valueOf("meetingMinutesSortBy");
        const sortDir = valueOf("meetingMinutesSortDir");
        if (hasAttachments) params.set("has_attachments", hasAttachments);
        if (relationSearch) params.set("relation_search", relationSearch);
        if (sortBy) params.set("sort_by", sortBy);
        if (sortDir) params.set("sort_dir", sortDir);
        return params.toString();
    }

    function renderSummary(summary) {
        setText("meetingMinutesTotal", formatNumber(summary?.total || 0));
        setText("meetingMinutesOpen", formatNumber(summary?.open || 0));
        setText("meetingMinutesClosed", formatNumber(summary?.closed || 0));
        setText("meetingMinutesOpenResolutions", formatNumber(summary?.open_resolution_minutes || 0));
        setText("meetingMinutesOverdueResolutions", formatNumber(summary?.overdue_resolutions || 0));
    }

    function renderPagination() {
        const start = state.total > 0 ? state.skip + 1 : 0;
        const end = Math.min(state.skip + state.rows.length, state.total);
        setText("meetingMinutesPaginationInfo", `نمایش ${formatNumber(start)}-${formatNumber(end)} از ${formatNumber(state.total)}`);
        const prev = root()?.querySelector('[data-meeting-minutes-action="prev"]');
        const next = root()?.querySelector('[data-meeting-minutes-action="next"]');
        if (prev) prev.disabled = state.skip <= 0;
        if (next) next.disabled = state.skip + state.limit >= state.total;
    }

    function renderRows() {
        const body = document.getElementById("meetingMinutesTableBody");
        if (!body) return;
        state.rowsById = {};
        if (state.loading) {
            body.innerHTML = `<tr><td colspan="10" class="archive-empty">در حال بارگذاری...</td></tr>`;
            return;
        }
        if (!state.rows.length) {
            body.innerHTML = `<tr><td colspan="10" class="archive-empty">صورتجلسه‌ای یافت نشد.</td></tr>`;
            return;
        }
        body.innerHTML = state.rows.map((row) => {
            state.rowsById[String(row.id)] = row;
            const editButton = canUpdate()
                ? `<button type="button" class="btn-archive-icon" data-meeting-minutes-action="edit-minute" data-minute-id="${esc(row.id)}" title="ویرایش"><span class="material-icons-round">edit</span></button>`
                : "";
            const deleteButton = canDelete()
                ? `<button type="button" class="btn-archive-icon" data-meeting-minutes-action="delete-minute" data-minute-id="${esc(row.id)}" title="غیرفعال‌سازی"><span class="material-icons-round">delete</span></button>`
                : "";
            const openCount = Number(row.open_resolution_count || 0);
            const overdueCount = Number(row.overdue_resolution_count || 0);
            return `
                <tr>
                    <td class="meeting-minutes-number">${esc(row.meeting_no || "-")}</td>
                    <td class="meeting-minutes-title">${esc(row.title || "-")}</td>
                    <td>${esc(row.project_code || "-")}</td>
                    <td>${esc(row.meeting_type || "-")}</td>
                    <td>${esc(formatDate(row.meeting_date))}</td>
                    <td><span class="${statusClass(row.status)}">${esc(row.status || "-")}</span></td>
                    <td>${formatNumber(row.resolution_count)}</td>
                    <td>
                        <span class="${overdueCount > 0 ? "meeting-minutes-count is-overdue" : "meeting-minutes-count"}">
                            ${formatNumber(openCount)}${overdueCount > 0 ? ` / ${formatNumber(overdueCount)}` : ""}
                        </span>
                    </td>
                    <td>${row.has_main_file ? `<span class="material-icons-round meeting-minutes-file-icon">attach_file</span>` : formatNumber(row.attachment_count)}</td>
                    <td>
                        <div class="meeting-minutes-row-actions">
                            <button type="button" class="btn-archive-icon" data-meeting-minutes-action="view-minute" data-minute-id="${esc(row.id)}" title="مشاهده">
                                <span class="material-icons-round">visibility</span>
                            </button>
                            ${editButton}
                            ${deleteButton}
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    async function loadMinutes(reset = false) {
        if (reset) state.skip = 0;
        state.loading = true;
        renderRows();
        try {
            const payload = await requestJson(`${API_BASE}/meeting-minutes/list?${buildQuery()}`);
            state.total = Number(payload?.total || 0);
            state.rows = Array.isArray(payload?.data) ? payload.data : [];
            renderSummary(payload?.summary || {});
        } catch (error) {
            state.total = 0;
            state.rows = [];
            renderSummary({});
            showToast(error instanceof Error ? error.message : "خطا در بارگذاری صورتجلسات", "error");
        } finally {
            state.loading = false;
            renderRows();
            renderPagination();
        }
    }

    function resetFilters() {
        [
            "meetingMinutesSearch",
            "meetingMinutesProject",
            "meetingMinutesType",
            "meetingMinutesStatus",
            "meetingMinutesResponsible",
            "meetingMinutesRelationSearch",
            "meetingMinutesDateFrom",
            "meetingMinutesDateTo",
            "meetingMinutesHasAttachments",
            "meetingMinutesSortBy",
            "meetingMinutesSortDir",
        ].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = "";
        });
        ["meetingMinutesOpenResolutionsOnly", "meetingMinutesOverdueOnly"].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.checked = false;
        });
    }

    async function loadDetail(minuteId) {
        if (!minuteId) {
            state.resolutions = [];
            state.attachments = [];
            state.relations = { outgoing: [], incoming: [] };
            return;
        }
        const [resolutionsPayload, attachmentsPayload, relationsPayload] = await Promise.all([
            requestJson(`${API_BASE}/meeting-minutes/${minuteId}/resolutions`),
            requestJson(`${API_BASE}/meeting-minutes/${minuteId}/attachments`),
            requestJson(`${API_BASE}/meeting-minutes/${minuteId}/relations`).catch(() => ({ outgoing: [], incoming: [] })),
        ]);
        state.resolutions = Array.isArray(resolutionsPayload?.data) ? resolutionsPayload.data : [];
        state.attachments = Array.isArray(attachmentsPayload?.data) ? attachmentsPayload.data : [];
        state.relations = {
            outgoing: Array.isArray(relationsPayload?.outgoing) ? relationsPayload.outgoing : [],
            incoming: Array.isArray(relationsPayload?.incoming) ? relationsPayload.incoming : [],
        };
    }

    function minutePayload() {
        return {
            meeting_no: valueOf("meetingMinuteNo") || null,
            title: valueOf("meetingMinuteTitle"),
            project_code: valueOf("meetingMinuteProject") || null,
            meeting_type: valueOf("meetingMinuteType") || "General",
            meeting_date: apiDate(valueOf("meetingMinuteDate")),
            location: valueOf("meetingMinuteLocation") || null,
            chairperson: valueOf("meetingMinuteChairperson") || null,
            secretary: valueOf("meetingMinuteSecretary") || null,
            participants: valueOf("meetingMinuteParticipants") || null,
            status: valueOf("meetingMinuteStatus") || "Open",
            summary: valueOf("meetingMinuteSummary") || null,
            notes: valueOf("meetingMinuteNotes") || null,
        };
    }

    function relationPayload() {
        return {
            target_entity_type: valueOf("meetingRelationTargetType") || "document",
            target_code: valueOf("meetingRelationTargetCode"),
            relation_type: valueOf("meetingRelationType") || "related",
            notes: valueOf("meetingRelationNotes") || null,
        };
    }

    async function refreshNextMeetingNumber() {
        if (state.selectedMinute?.id) return;
        const project = valueOf("meetingMinuteProject");
        const meetingDate = valueOf("meetingMinuteDate");
        const params = new URLSearchParams();
        if (project) params.set("project_code", project);
        if (meetingDate) params.set("meeting_date", meetingDate);
        const previewEl = document.getElementById("meetingMinuteNoPreview");
        try {
            const payload = await requestJson(`${API_BASE}/meeting-minutes/next-number?${params.toString()}`);
            const number = String(payload?.meeting_no || "").trim();
            const input = document.getElementById("meetingMinuteNo");
            if (input && number && !String(input.value || "").trim()) input.placeholder = number;
            if (previewEl) previewEl.textContent = number ? `شماره پیشنهادی: ${number}` : "";
        } catch (error) {
            if (previewEl) previewEl.textContent = "پیش‌نمایش شماره در دسترس نیست.";
        }
    }

    function resolutionPayload() {
        return {
            resolution_no: valueOf("meetingResolutionNo") || null,
            description: valueOf("meetingResolutionDescription"),
            responsible_user_id: valueOf("meetingResolutionUser") ? Number(valueOf("meetingResolutionUser")) : null,
            responsible_org_id: valueOf("meetingResolutionOrg") ? Number(valueOf("meetingResolutionOrg")) : null,
            responsible_name: valueOf("meetingResolutionResponsible") || null,
            due_date: apiDate(valueOf("meetingResolutionDue")),
            status: valueOf("meetingResolutionStatus") || "Open",
            priority: valueOf("meetingResolutionPriority") || "Normal",
            sort_order: Number(valueOf("meetingResolutionSort") || 0),
        };
    }

    function renderMinuteForm(row, readonly) {
        return `
            <section class="meeting-minutes-section">
                <div class="meeting-minutes-section-title">
                    <span class="material-icons-round">event_note</span>
                    اطلاعات جلسه
                </div>
                <div class="meeting-minutes-form-grid">
                    <label>شماره
                        <input id="meetingMinuteNo" type="text" value="${esc(row?.meeting_no || "")}" ${readonly ? "disabled" : ""}>
                        ${readonly || row?.id ? "" : `<small id="meetingMinuteNoPreview" class="meeting-minutes-help">در صورت خالی بودن، شماره اتومات ساخته می‌شود.</small>`}
                    </label>
                    <label>عنوان
                        <input id="meetingMinuteTitle" type="text" value="${esc(row?.title || "")}" ${readonly ? "disabled" : ""}>
                    </label>
                    <label>پروژه
                        <select id="meetingMinuteProject" ${readonly ? "disabled" : ""}>
                            ${selectOptions((state.catalog.projects || []).map((project) => ({
                                value: project.code,
                                label: `${project.code}${project.name_e || project.name_p ? ` - ${project.name_e || project.name_p}` : ""}`,
                            })), row?.project_code || "", "بدون پروژه")}
                        </select>
                    </label>
                    <label>نوع جلسه
                        <input id="meetingMinuteType" type="text" list="meetingMinuteTypesList" value="${esc(row?.meeting_type || "General")}" ${readonly ? "disabled" : ""}>
                    </label>
                    <label>تاریخ جلسه
                        <input id="meetingMinuteDate" type="date" value="${esc(dateInputValue(row?.meeting_date) || new Date().toISOString().slice(0, 10))}" ${readonly ? "disabled" : ""}>
                        <small class="meeting-minutes-help">${esc(formatDate(row?.meeting_date || new Date().toISOString()))}</small>
                    </label>
                    <label>وضعیت
                        <select id="meetingMinuteStatus" ${readonly ? "disabled" : ""}>
                            ${selectOptions(state.catalog.minute_statuses || [], row?.status || "Open")}
                        </select>
                    </label>
                    <label>محل جلسه
                        <input id="meetingMinuteLocation" type="text" value="${esc(row?.location || "")}" ${readonly ? "disabled" : ""}>
                    </label>
                    <label>رئیس جلسه
                        <input id="meetingMinuteChairperson" type="text" value="${esc(row?.chairperson || "")}" ${readonly ? "disabled" : ""}>
                    </label>
                    <label>دبیر جلسه
                        <input id="meetingMinuteSecretary" type="text" value="${esc(row?.secretary || "")}" ${readonly ? "disabled" : ""}>
                    </label>
                </div>
                <datalist id="meetingMinuteTypesList">
                    ${(state.catalog.meeting_types || []).map((item) => `<option value="${esc(item)}"></option>`).join("")}
                </datalist>
                <label class="meeting-minutes-wide-label">شرکت‌کنندگان
                    <textarea id="meetingMinuteParticipants" rows="3" ${readonly ? "disabled" : ""}>${esc(row?.participants || "")}</textarea>
                </label>
                <label class="meeting-minutes-wide-label">خلاصه
                    <textarea id="meetingMinuteSummary" rows="3" ${readonly ? "disabled" : ""}>${esc(row?.summary || "")}</textarea>
                </label>
                <label class="meeting-minutes-wide-label">یادداشت
                    <textarea id="meetingMinuteNotes" rows="2" ${readonly ? "disabled" : ""}>${esc(row?.notes || "")}</textarea>
                </label>
                ${readonly ? "" : `
                    <div class="meeting-minutes-form-actions">
                        ${row?.id ? "" : `<button type="button" class="btn-archive-icon" data-meeting-minutes-action="refresh-next-number">
                            <span class="material-icons-round">tag</span>
                            پیش‌نمایش شماره
                        </button>`}
                        <button type="button" class="btn-archive-primary" data-meeting-minutes-action="save-minute">
                            <span class="material-icons-round">save</span>
                            ذخیره صورتجلسه
                        </button>
                    </div>
                `}
            </section>
        `;
    }

    function renderResolutionForm(readonly) {
        if (readonly || !state.selectedMinute?.id) return "";
        const editing = state.resolutions.find((item) => String(item.id) === String(state.editingResolutionId)) || {};
        return `
            <div class="meeting-minutes-resolution-form">
                <input id="meetingResolutionNo" type="text" placeholder="شماره مصوبه" value="${esc(editing.resolution_no || "")}">
                <input id="meetingResolutionResponsible" type="text" placeholder="مسئول آزاد" value="${esc(editing.responsible_name || "")}">
                <select id="meetingResolutionUser">
                    ${selectOptions((state.catalog.users || []).map((user) => ({
                        value: user.id,
                        label: user.full_name || user.email,
                    })), editing.responsible_user_id || "", "کاربر مسئول")}
                </select>
                <select id="meetingResolutionOrg">
                    ${selectOptions((state.catalog.organizations || []).map((org) => ({
                        value: org.id,
                        label: `${org.name}${org.code ? ` (${org.code})` : ""}`,
                    })), editing.responsible_org_id || "", "سازمان مسئول")}
                </select>
                <input id="meetingResolutionDue" type="date" value="${esc(dateInputValue(editing.due_date))}" title="سررسید">
                <select id="meetingResolutionStatus">
                    ${selectOptions(state.catalog.resolution_statuses || [], editing.status || "Open")}
                </select>
                <select id="meetingResolutionPriority">
                    ${selectOptions(state.catalog.priorities || [], editing.priority || "Normal")}
                </select>
                <input id="meetingResolutionSort" type="number" min="0" step="1" placeholder="ترتیب" value="${esc(editing.sort_order || 0)}">
                <textarea id="meetingResolutionDescription" rows="2" placeholder="شرح مصوبه">${esc(editing.description || "")}</textarea>
                <div class="meeting-minutes-resolution-actions">
                    <button type="button" class="btn-archive-primary" data-meeting-minutes-action="save-resolution">
                        <span class="material-icons-round">task_alt</span>
                        ${state.editingResolutionId ? "ذخیره مصوبه" : "افزودن مصوبه"}
                    </button>
                    ${state.editingResolutionId ? `<button type="button" class="btn-archive-icon" data-meeting-minutes-action="cancel-resolution-edit">انصراف</button>` : ""}
                </div>
            </div>
        `;
    }

    function renderResolutions(readonly) {
        const rows = state.resolutions.length
            ? state.resolutions.map((row) => `
                <tr>
                    <td>${esc(row.resolution_no || "-")}</td>
                    <td class="meeting-minutes-resolution-desc">${esc(row.description || "-")}</td>
                    <td>${esc(row.responsible_name || row.responsible_user_name || row.responsible_org_name || "-")}</td>
                    <td>${esc(formatDate(row.due_date))}</td>
                    <td><span class="${statusClass(row.status)}">${esc(row.status || "-")}</span></td>
                    <td>${esc(row.priority || "-")}</td>
                    <td>${formatNumber(row.attachment_count || 0)}</td>
                    <td>
                        <div class="meeting-minutes-row-actions">
                            ${readonly ? "" : `<button type="button" class="btn-archive-icon" data-meeting-minutes-action="edit-resolution" data-resolution-id="${esc(row.id)}" title="ویرایش"><span class="material-icons-round">edit</span></button>`}
                            ${readonly ? "" : `<button type="button" class="btn-archive-icon" data-meeting-minutes-action="delete-resolution" data-resolution-id="${esc(row.id)}" title="غیرفعال‌سازی"><span class="material-icons-round">delete</span></button>`}
                        </div>
                    </td>
                </tr>
            `).join("")
            : `<tr><td colspan="8" class="archive-empty">مصوبه‌ای ثبت نشده است.</td></tr>`;
        return `
            <section class="meeting-minutes-section">
                <div class="meeting-minutes-section-title">
                    <span class="material-icons-round">checklist</span>
                    مصوبات
                </div>
                ${renderResolutionForm(readonly)}
                <div class="meeting-minutes-nested-table-wrap">
                    <table class="archive-table meeting-minutes-nested-table">
                        <thead>
                            <tr>
                                <th>شماره</th>
                                <th>شرح</th>
                                <th>مسئول</th>
                                <th>سررسید</th>
                                <th>وضعیت</th>
                                <th>اولویت</th>
                                <th>پیوست</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </section>
        `;
    }

    function renderAttachments(readonly) {
        const rows = state.attachments.length
            ? state.attachments.map((row) => `
                <tr>
                    <td>${esc(row.file_kind === "main" ? "فایل اصلی" : "پیوست")}</td>
                    <td class="meeting-minutes-number">${esc(row.file_name || "-")}</td>
                    <td>${row.resolution_id ? esc((state.resolutions.find((item) => String(item.id) === String(row.resolution_id)) || {}).resolution_no || row.resolution_id) : "-"}</td>
                    <td>${formatNumber(row.size_bytes || 0)}</td>
                    <td>${esc(formatDate(row.uploaded_at))}</td>
                    <td>
                        <div class="meeting-minutes-row-actions">
                            <button type="button" class="btn-archive-icon" data-meeting-minutes-action="download-attachment" data-attachment-id="${esc(row.id)}" title="دانلود"><span class="material-icons-round">download</span></button>
                            ${readonly ? "" : `<button type="button" class="btn-archive-icon" data-meeting-minutes-action="delete-attachment" data-attachment-id="${esc(row.id)}" title="غیرفعال‌سازی"><span class="material-icons-round">delete</span></button>`}
                        </div>
                    </td>
                </tr>
            `).join("")
            : `<tr><td colspan="6" class="archive-empty">پیوستی ثبت نشده است.</td></tr>`;
        const resolutionOptions = state.resolutions.map((row) => ({
            value: row.id,
            label: row.resolution_no || row.description || row.id,
        }));
        return `
            <section class="meeting-minutes-section">
                <div class="meeting-minutes-section-title">
                    <span class="material-icons-round">attach_file</span>
                    پیوست‌ها
                </div>
                ${readonly || !state.selectedMinute?.id ? "" : `
                    <div class="meeting-minutes-upload-row">
                        <input id="meetingAttachmentFile" type="file">
                        <select id="meetingAttachmentKind">
                            <option value="attachment">پیوست</option>
                            <option value="main">فایل اصلی صورتجلسه</option>
                        </select>
                        <select id="meetingAttachmentResolution">
                            ${selectOptions(resolutionOptions, "", "بدون اتصال به مصوبه")}
                        </select>
                        <button type="button" class="btn-archive-primary" data-meeting-minutes-action="upload-attachment">
                            <span class="material-icons-round">upload</span>
                            بارگذاری
                        </button>
                    </div>
                `}
                <div class="meeting-minutes-nested-table-wrap">
                    <table class="archive-table meeting-minutes-nested-table">
                        <thead>
                            <tr>
                                <th>نوع</th>
                                <th>فایل</th>
                                <th>مصوبه</th>
                                <th>حجم</th>
                                <th>تاریخ</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </section>
        `;
    }

    function renderDrawerTabs() {
        const active = String(state.drawerTab || "info");
        const tabs = [
            ["info", "اطلاعات جلسه", "event_note"],
            ["resolutions", "مصوبات", "checklist"],
            ["relations", "ارتباطات", "hub"],
            ["attachments", "پیوست‌ها", "attach_file"],
            ["print", "چاپ", "print"],
        ];
        return `
            <div class="meeting-minutes-drawer-tabs" role="tablist">
                ${tabs.map(([key, label, icon]) => `
                    <button type="button" class="${active === key ? "is-active" : ""}" data-meeting-minutes-action="drawer-tab" data-tab="${esc(key)}">
                        <span class="material-icons-round">${esc(icon)}</span>
                        ${esc(label)}
                    </button>
                `).join("")}
            </div>
        `;
    }

    function renderRelations(readonly) {
        const outgoing = Array.isArray(state.relations?.outgoing) ? state.relations.outgoing : [];
        const incoming = Array.isArray(state.relations?.incoming) ? state.relations.incoming : [];
        const rowHtml = (row, incomingRow = false) => `
            <tr>
                <td>${esc(row.target_label || row.target_entity_type || "-")}</td>
                <td class="meeting-minutes-number">${esc(row.target_code || "-")}</td>
                <td>${esc(row.target_title || "-")}</td>
                <td>${esc(row.relation_type || "-")}</td>
                <td>${esc(incomingRow ? "ورودی" : "خروجی")}</td>
                <td>
                    ${incomingRow || readonly ? "" : `<button type="button" class="btn-archive-icon" data-meeting-minutes-action="delete-relation" data-relation-id="${esc(row.id)}" title="حذف"><span class="material-icons-round">delete</span></button>`}
                </td>
            </tr>
        `;
        const rows = [...outgoing.map((row) => rowHtml(row, false)), ...incoming.map((row) => rowHtml(row, true))].join("");
        return `
            <section class="meeting-minutes-section">
                <div class="meeting-minutes-section-title">
                    <span class="material-icons-round">hub</span>
                    ارتباطات
                </div>
                ${!state.selectedMinute?.id ? `<div class="archive-empty">ابتدا صورتجلسه را ذخیره کنید.</div>` : readonly ? "" : `
                    <div class="meeting-minutes-relation-form">
                        <select id="meetingRelationTargetType">
                            <option value="document">مدرک</option>
                            <option value="correspondence">مکاتبه</option>
                        </select>
                        <input id="meetingRelationTargetCode" type="text" placeholder="Doc Code / Correspondence No">
                        <select id="meetingRelationType">
                            <option value="related">مرتبط</option>
                            <option value="references">ارجاع</option>
                            <option value="parent">والد</option>
                            <option value="child">فرزند</option>
                        </select>
                        <input id="meetingRelationNotes" type="text" placeholder="یادداشت اختیاری">
                        <button type="button" class="btn-archive-primary" data-meeting-minutes-action="save-relation">
                            <span class="material-icons-round">add_link</span>
                            افزودن ارتباط
                        </button>
                    </div>
                `}
                <div class="meeting-minutes-nested-table-wrap">
                    <table class="archive-table meeting-minutes-nested-table">
                        <thead>
                            <tr>
                                <th>نوع</th>
                                <th>کد / شماره</th>
                                <th>عنوان</th>
                                <th>رابطه</th>
                                <th>جهت</th>
                                <th>عملیات</th>
                            </tr>
                        </thead>
                        <tbody>${rows || `<tr><td colspan="6" class="archive-empty">ارتباطی ثبت نشده است.</td></tr>`}</tbody>
                    </table>
                </div>
            </section>
        `;
    }

    function renderPrintPanel() {
        return `
            <section class="meeting-minutes-section">
                <div class="meeting-minutes-section-title">
                    <span class="material-icons-round">print</span>
                    پیش‌نمایش چاپ
                </div>
                ${!state.selectedMinute?.id ? `<div class="archive-empty">برای چاپ، ابتدا صورتجلسه را ذخیره کنید.</div>` : `
                    <div class="meeting-minutes-print-card">
                        <div>
                            <strong>${esc(state.selectedMinute?.meeting_no || "-")}</strong>
                            <span>قالب رسمی A4 شامل اطلاعات جلسه، حاضرین، مصوبات، پیوست‌ها و محل امضا.</span>
                        </div>
                        <button type="button" class="btn-archive-primary" data-meeting-minutes-action="print-preview">
                            <span class="material-icons-round">print</span>
                            پیش‌نمایش چاپ
                        </button>
                    </div>
                `}
            </section>
        `;
    }

    function openPrintModal(html) {
        document.getElementById("meetingMinutesPrintModal")?.remove();
        const modal = document.createElement("div");
        modal.id = "meetingMinutesPrintModal";
        modal.className = "meeting-minutes-print-modal";
        modal.innerHTML = `
            <div class="meeting-minutes-print-box">
                <div class="meeting-minutes-print-toolbar">
                    <div>
                        <strong>پیش‌نمایش چاپ صورتجلسه</strong>
                        <span>${esc(state.selectedMinute?.meeting_no || "")}</span>
                    </div>
                    <div>
                        <button type="button" class="btn-archive-primary" data-print-action="print">
                            <span class="material-icons-round">print</span>
                            چاپ / ذخیره PDF
                        </button>
                        <button type="button" class="btn-archive-icon" data-print-action="close">
                            <span class="material-icons-round">close</span>
                        </button>
                    </div>
                </div>
                <iframe class="meeting-minutes-print-frame" title="Meeting minute print preview"></iframe>
            </div>
        `;
        document.body.appendChild(modal);
        const frame = modal.querySelector("iframe");
        if (frame) frame.srcdoc = html;
        modal.addEventListener("click", (event) => {
            const action = event.target?.closest?.("[data-print-action]")?.getAttribute("data-print-action");
            if (action === "close") {
                modal.remove();
            } else if (action === "print") {
                frame?.contentWindow?.focus();
                frame?.contentWindow?.print();
            }
        });
    }

    function renderDrawer() {
        const drawer = document.getElementById("meetingMinutesDrawer");
        const body = document.getElementById("meetingMinutesDrawerBody");
        const title = document.getElementById("meetingMinutesDrawerTitle");
        const meta = document.getElementById("meetingMinutesDrawerMeta");
        if (!drawer || !body) return;
        const row = state.selectedMinute || {};
        const isExisting = Boolean(row.id);
        const readonly = isExisting ? !canUpdate() : !canCreate();
        if (!["info", "resolutions", "relations", "attachments", "print"].includes(String(state.drawerTab || ""))) {
            state.drawerTab = "info";
        }
        if (title) title.textContent = isExisting ? `صورتجلسه ${row.meeting_no || ""}`.trim() : "صورتجلسه جدید";
        if (meta) meta.textContent = isExisting ? `${row.project_code || "-"} | ${row.status || "-"}` : "ثبت اولیه اطلاعات جلسه";
        const activeTab = String(state.drawerTab || "info");
        const content = activeTab === "resolutions"
            ? renderResolutions(!canUpdate())
            : activeTab === "relations"
                ? renderRelations(!canUpdate())
                : activeTab === "attachments"
                    ? renderAttachments(!canAttach())
                    : activeTab === "print"
                        ? renderPrintPanel()
                        : renderMinuteForm(row, readonly);
        body.innerHTML = `
            ${renderDrawerTabs()}
            ${content}
        `;
        syncShamsiDates();
    }

    async function openDrawer(row = null, mode = "view") {
        state.selectedMinute = row ? { ...row } : {};
        state.drawerTab = "info";
        state.editingResolutionId = null;
        if (row?.id) {
            await loadDetail(row.id);
        } else {
            state.resolutions = [];
            state.attachments = [];
            state.relations = { outgoing: [], incoming: [] };
        }
        renderDrawer();
        if (!row?.id) window.setTimeout(() => refreshNextMeetingNumber(), 0);
        const drawer = document.getElementById("meetingMinutesDrawer");
        if (drawer) {
            drawer.hidden = false;
            drawer.classList.add("is-open");
        }
    }

    function closeDrawer() {
        const drawer = document.getElementById("meetingMinutesDrawer");
        if (!drawer) return;
        drawer.classList.remove("is-open");
        drawer.hidden = true;
        state.selectedMinute = null;
        state.resolutions = [];
        state.attachments = [];
        state.relations = { outgoing: [], incoming: [] };
        state.editingResolutionId = null;
    }

    async function saveMinute() {
        const payload = minutePayload();
        if (!payload.title) {
            showToast("عنوان صورتجلسه الزامی است.", "error");
            return;
        }
        const existingId = state.selectedMinute?.id;
        const endpoint = existingId
            ? `${API_BASE}/meeting-minutes/${existingId}`
            : `${API_BASE}/meeting-minutes/create`;
        const method = existingId ? "PUT" : "POST";
        const result = await requestJson(endpoint, { method, body: payload });
        state.selectedMinute = result?.data || state.selectedMinute;
        showToast("صورتجلسه ذخیره شد.", "success");
        await loadMinutes(false);
        if (state.selectedMinute?.id) {
            await loadDetail(state.selectedMinute.id);
        }
        renderDrawer();
    }

    async function saveResolution() {
        if (!state.selectedMinute?.id) {
            showToast("ابتدا صورتجلسه را ذخیره کنید.", "error");
            return;
        }
        const payload = resolutionPayload();
        if (!payload.description) {
            showToast("شرح مصوبه الزامی است.", "error");
            return;
        }
        const endpoint = state.editingResolutionId
            ? `${API_BASE}/meeting-minutes/resolutions/${state.editingResolutionId}`
            : `${API_BASE}/meeting-minutes/${state.selectedMinute.id}/resolutions`;
        const method = state.editingResolutionId ? "PUT" : "POST";
        await requestJson(endpoint, { method, body: payload });
        state.editingResolutionId = null;
        await loadDetail(state.selectedMinute.id);
        await loadMinutes(false);
        renderDrawer();
        showToast("مصوبه ذخیره شد.", "success");
    }

    async function deleteResolution(resolutionId) {
        if (!confirm("این مصوبه غیرفعال شود؟")) return;
        await requestJson(`${API_BASE}/meeting-minutes/resolutions/${resolutionId}`, { method: "DELETE" });
        await loadDetail(state.selectedMinute.id);
        await loadMinutes(false);
        renderDrawer();
    }

    async function uploadAttachment() {
        if (!state.selectedMinute?.id) {
            showToast("ابتدا صورتجلسه را ذخیره کنید.", "error");
            return;
        }
        const fileInput = document.getElementById("meetingAttachmentFile");
        const file = fileInput?.files?.[0];
        if (!file) {
            showToast("فایل را انتخاب کنید.", "error");
            return;
        }
        const form = new FormData();
        form.append("file", file);
        form.append("file_kind", valueOf("meetingAttachmentKind") || "attachment");
        const resolutionId = valueOf("meetingAttachmentResolution");
        if (resolutionId) form.append("resolution_id", resolutionId);
        await requestJson(`${API_BASE}/meeting-minutes/${state.selectedMinute.id}/attachments/upload`, {
            method: "POST",
            body: form,
        });
        await loadDetail(state.selectedMinute.id);
        await loadMinutes(false);
        renderDrawer();
        showToast("پیوست بارگذاری شد.", "success");
    }

    async function downloadAttachment(attachmentId) {
        const fetcher = typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch;
        const res = await fetcher(`${API_BASE}/meeting-minutes/attachments/${attachmentId}/download`);
        if (!res.ok) throw new Error("خطا در دانلود پیوست");
        const blob = await res.blob();
        const disposition = res.headers.get("content-disposition") || "";
        const match = disposition.match(/filename="([^"]+)"/i);
        const filename = match?.[1] || `meeting-attachment-${attachmentId}`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    }

    async function deleteAttachment(attachmentId) {
        if (!confirm("این پیوست غیرفعال شود؟")) return;
        await requestJson(`${API_BASE}/meeting-minutes/attachments/${attachmentId}`, { method: "DELETE" });
        await loadDetail(state.selectedMinute.id);
        await loadMinutes(false);
        renderDrawer();
    }

    async function saveRelation() {
        if (!state.selectedMinute?.id) {
            showToast("ابتدا صورتجلسه را ذخیره کنید.", "error");
            return;
        }
        const payload = relationPayload();
        if (!payload.target_code) {
            showToast("کد مقصد ارتباط الزامی است.", "error");
            return;
        }
        await requestJson(`${API_BASE}/meeting-minutes/${state.selectedMinute.id}/relations`, {
            method: "POST",
            body: payload,
        });
        const codeInput = document.getElementById("meetingRelationTargetCode");
        const notesInput = document.getElementById("meetingRelationNotes");
        if (codeInput) codeInput.value = "";
        if (notesInput) notesInput.value = "";
        await loadDetail(state.selectedMinute.id);
        await loadMinutes(false);
        renderDrawer();
        showToast("ارتباط ثبت شد.", "success");
    }

    async function deleteRelation(relationId) {
        if (!state.selectedMinute?.id || !relationId) return;
        if (!confirm("ارتباط حذف شود؟")) return;
        await requestJson(`${API_BASE}/meeting-minutes/${state.selectedMinute.id}/relations/${encodeURIComponent(relationId)}`, {
            method: "DELETE",
        });
        await loadDetail(state.selectedMinute.id);
        await loadMinutes(false);
        renderDrawer();
        showToast("ارتباط حذف شد.", "success");
    }

    async function printPreview() {
        if (!state.selectedMinute?.id) {
            showToast("ابتدا صورتجلسه را ذخیره کنید.", "error");
            return;
        }
        const fetcher = typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch;
        const res = await fetcher(`${API_BASE}/meeting-minutes/${state.selectedMinute.id}/print-preview`);
        if (!res.ok) throw new Error("خطا در دریافت پیش‌نمایش چاپ");
        openPrintModal(await res.text());
    }

    async function deleteMinute(minuteId) {
        if (!confirm("این صورتجلسه غیرفعال شود؟")) return;
        await requestJson(`${API_BASE}/meeting-minutes/${minuteId}`, { method: "DELETE" });
        await loadMinutes(true);
        showToast("صورتجلسه غیرفعال شد.", "success");
    }

    function bindEvents() {
        const container = root();
        if (!container || state.bound) return;
        container.addEventListener("click", (event) => {
            const actionEl = event.target?.closest?.("[data-meeting-minutes-action]");
            if (!actionEl || !container.contains(actionEl)) return;
            const action = lower(actionEl.getAttribute("data-meeting-minutes-action"));
            const minuteId = actionEl.getAttribute("data-minute-id") || "";
            const resolutionId = actionEl.getAttribute("data-resolution-id") || "";
            const attachmentId = actionEl.getAttribute("data-attachment-id") || "";
            const relationId = actionEl.getAttribute("data-relation-id") || "";
            const row = state.rowsById[String(minuteId)];

            try {
                if (action === "refresh") {
                    event.preventDefault();
                    void loadMinutes(false);
                } else if (action === "reset") {
                    event.preventDefault();
                    resetFilters();
                    void loadMinutes(true);
                } else if (action === "new-minute") {
                    event.preventDefault();
                    void openDrawer(null, "edit");
                } else if (action === "drawer-tab") {
                    event.preventDefault();
                    state.drawerTab = actionEl.getAttribute("data-tab") || "info";
                    renderDrawer();
                } else if (action === "refresh-next-number") {
                    event.preventDefault();
                    void refreshNextMeetingNumber();
                } else if ((action === "view-minute" || action === "edit-minute") && row) {
                    event.preventDefault();
                    void openDrawer(row, action === "edit-minute" ? "edit" : "view");
                } else if (action === "delete-minute" && minuteId) {
                    event.preventDefault();
                    void deleteMinute(minuteId);
                } else if (action === "close-drawer") {
                    event.preventDefault();
                    closeDrawer();
                } else if (action === "save-minute") {
                    event.preventDefault();
                    void saveMinute().catch((error) => showToast(error.message || "خطا در ذخیره صورتجلسه", "error"));
                } else if (action === "save-resolution") {
                    event.preventDefault();
                    void saveResolution().catch((error) => showToast(error.message || "خطا در ذخیره مصوبه", "error"));
                } else if (action === "edit-resolution" && resolutionId) {
                    event.preventDefault();
                    state.editingResolutionId = resolutionId;
                    renderDrawer();
                } else if (action === "cancel-resolution-edit") {
                    event.preventDefault();
                    state.editingResolutionId = null;
                    renderDrawer();
                } else if (action === "delete-resolution" && resolutionId) {
                    event.preventDefault();
                    void deleteResolution(resolutionId).catch((error) => showToast(error.message || "خطا در حذف مصوبه", "error"));
                } else if (action === "upload-attachment") {
                    event.preventDefault();
                    void uploadAttachment().catch((error) => showToast(error.message || "خطا در بارگذاری پیوست", "error"));
                } else if (action === "download-attachment" && attachmentId) {
                    event.preventDefault();
                    void downloadAttachment(attachmentId).catch((error) => showToast(error.message || "خطا در دانلود پیوست", "error"));
                } else if (action === "delete-attachment" && attachmentId) {
                    event.preventDefault();
                    void deleteAttachment(attachmentId).catch((error) => showToast(error.message || "خطا در حذف پیوست", "error"));
                } else if (action === "save-relation") {
                    event.preventDefault();
                    void saveRelation().catch((error) => showToast(error.message || "خطا در ثبت ارتباط", "error"));
                } else if (action === "delete-relation" && relationId) {
                    event.preventDefault();
                    void deleteRelation(relationId).catch((error) => showToast(error.message || "خطا در حذف ارتباط", "error"));
                } else if (action === "print-preview") {
                    event.preventDefault();
                    void printPreview().catch((error) => showToast(error.message || "خطا در پیش‌نمایش چاپ", "error"));
                } else if (action === "prev") {
                    event.preventDefault();
                    state.skip = Math.max(0, state.skip - state.limit);
                    void loadMinutes(false);
                } else if (action === "next") {
                    event.preventDefault();
                    if (state.skip + state.limit < state.total) {
                        state.skip += state.limit;
                        void loadMinutes(false);
                    }
                }
            } catch (error) {
                showToast(error instanceof Error ? error.message : "خطای نامشخص", "error");
            }
        });

        [
            "meetingMinutesProject",
            "meetingMinutesType",
            "meetingMinutesStatus",
            "meetingMinutesDateFrom",
            "meetingMinutesDateTo",
            "meetingMinutesOpenResolutionsOnly",
            "meetingMinutesOverdueOnly",
            "meetingMinutesHasAttachments",
            "meetingMinutesSortBy",
            "meetingMinutesSortDir",
        ].forEach((id) => {
            document.getElementById(id)?.addEventListener("change", () => loadMinutes(true));
        });
        ["meetingMinutesSearch", "meetingMinutesResponsible", "meetingMinutesRelationSearch"].forEach((id) => {
            document.getElementById(id)?.addEventListener("input", () => {
                if (state.debounce) window.clearTimeout(state.debounce);
                state.debounce = window.setTimeout(() => loadMinutes(true), 350);
            });
        });
        container.addEventListener("change", (event) => {
            const id = event.target?.id || "";
            if (id === "meetingMinuteProject" || id === "meetingMinuteDate") {
                void refreshNextMeetingNumber();
            }
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeDrawer();
        });
        state.bound = true;
    }

    async function initMeetingMinutesView(forceReload = false) {
        if (!root()) return;
        bindEvents();
        if (!state.initialized || forceReload) {
            state.initialized = true;
            try {
                await loadCatalog();
            } catch (error) {
                showToast(error instanceof Error ? error.message : "خطا در بارگذاری کاتالوگ صورتجلسات", "error");
            }
            await loadMinutes(true);
            syncShamsiDates();
        }
    }

    window.initMeetingMinutesView = initMeetingMinutesView;

    if (window.AppEvents?.on) {
        window.AppEvents.on("view:activated", ({ viewId }) => {
            if (String(viewId || "").trim() === "view-edms") {
                const activeTab = document.querySelector('.edms-tab-btn.active[data-edms-tab="meeting_minutes"]');
                if (activeTab) void initMeetingMinutesView(false);
            }
        });
    }
})();
