// @ts-nocheck
import { formatShamsiDate, formatShamsiDateTime } from "../lib/persian_datetime";
(() => {
    const APP_RUNTIME = (window.AppRuntime && typeof window.AppRuntime === "object")
        ? window.AppRuntime
        : null;
    const TS_TRANSMITTAL_UI = (APP_RUNTIME?.transmittalUi && typeof APP_RUNTIME.transmittalUi === "object")
        ? APP_RUNTIME.transmittalUi
        : null;
    const TS_TRANSMITTAL_DATA = (APP_RUNTIME?.transmittalData && typeof APP_RUNTIME.transmittalData === "object")
        ? APP_RUNTIME.transmittalData
        : null;
    const TS_TRANSMITTAL_MUTATIONS = (APP_RUNTIME?.transmittalMutations && typeof APP_RUNTIME.transmittalMutations === "object")
        ? APP_RUNTIME.transmittalMutations
        : null;

    const state = {
        formData: null,
        selectedDocs: [],
        searchDocs: [],
        listItems: [],
        bulkRegistered: false,
        createReady: false,
        editingId: null,
        activeDetailId: null,
        printPreviewId: null,
        printPreviewUrl: "",
        directionOptions: [],
        senderOptions: [],
        recipientOptions: [],
    };

    const TR2_BULK_ACTION_ISSUE = 'tr2-bulk-issue';
    const TR2_BULK_ACTION_VOID = 'tr2-bulk-void';
    const DEFAULT_DIRECTION_OPTIONS = [
        { code: "O", label: "صادره", is_active: true, sort_order: 10 },
        { code: "I", label: "وارده", is_active: true, sort_order: 20 },
    ];
    const DEFAULT_RECIPIENT_OPTIONS = [
        { code: "C", label: "مشاور", is_active: true, sort_order: 10 },
    ];

    function notify(type, message) {
        if (window.UI && typeof window.UI[type] === "function") {
            window.UI[type](message);
            return;
        }
        if (typeof showToast === "function") {
            showToast(message, type === "error" ? "error" : "success");
            return;
        }
        alert(message);
    }

    function transmittalBulkBridge() {
        if (!window.TableBulk || typeof window.TableBulk !== "object") return null;
        if (typeof window.TableBulk.register !== "function") return null;
        return window.TableBulk;
    }

    function summarizeBulkErrors(items = []) {
        if (!Array.isArray(items) || !items.length) return "";
        const head = items.slice(0, 3).join(" | ");
        return items.length > 3 ? `${head} | +${items.length - 3} مورد دیگر` : head;
    }

    function parseBulkTransmittalIds(selectedKeys = []) {
        return (selectedKeys || [])
            .map((key) => String(key || "").trim())
            .filter(Boolean);
    }

    function selectedTransmittalRows(ids = []) {
        if (!ids.length) return [];
        const idSet = new Set(ids);
        return (state.listItems || []).filter((item) => idSet.has(String(item?.id || "").trim()));
    }

    function isDraftTransmittal(item) {
        return String(item?.status || "").trim().toLowerCase() === "draft";
    }

    function canVoidTransmittal(item) {
        const status = String(item?.status || "").trim().toLowerCase();
        return status === "draft" || status === "issued";
    }

    function normalizeTransmittalStatus(value) {
        const raw = String(value || "").trim().toLowerCase();
        if (!raw) return "draft";
        if (raw === "پیش‌نویس") return "draft";
        if (raw === "صادر شده") return "issued";
        if (raw === "باطل") return "void";
        return raw;
    }

    function formatStatusLabel(value) {
        const status = normalizeTransmittalStatus(value);
        if (status === "draft") return "پیش‌نویس";
        if (status === "issued") return "صادر شده";
        if (status === "void") return "باطل";
        return String(value || "-");
    }

    function normalizePartyOption(item, fallbackIndex = 0) {
        const code = String(item?.code || "").trim().toUpperCase();
        if (!code) return null;
        return {
            code,
            label: String(item?.label || code).trim() || code,
            is_active: item?.is_active !== false,
            sort_order: Number(item?.sort_order ?? ((fallbackIndex + 1) * 10)),
        };
    }

    function normalizePartyOptions(items, fallback) {
        const source = Array.isArray(items) && items.length ? items : fallback;
        const seen = new Set();
        return source
            .map((item, index) => normalizePartyOption(item, index))
            .filter((item) => item && !seen.has(item.code) && seen.add(item.code))
            .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0));
    }

    function directionOptions() {
        return normalizePartyOptions(state.directionOptions, DEFAULT_DIRECTION_OPTIONS);
    }

    function recipientOptions() {
        return normalizePartyOptions(state.recipientOptions, DEFAULT_RECIPIENT_OPTIONS);
    }

    function senderOptions() {
        return normalizePartyOptions(state.senderOptions, recipientOptions());
    }

    function partyLabel(group, code, fallbackLabel = "") {
        const normalized = String(code || "").trim().toUpperCase();
        const fallback = String(fallbackLabel || "").trim();
        if (fallback) return fallback;
        const options = group === "recipient"
            ? recipientOptions()
            : (group === "sender" ? senderOptions() : directionOptions());
        const found = options.find((item) => item.code === normalized);
        if (!found && group === "sender" && ["O", "I"].includes(normalized)) {
            return partyLabel("direction", normalized);
        }
        return found?.label || normalized || "-";
    }

    function renderPartySelectOptions(selectEl, options, selectedCode) {
        if (!selectEl) return;
        const selected = String(selectedCode || "").trim().toUpperCase();
        const rows = [...options];
        if (selected && !rows.some((option) => option.code === selected)) {
            const labelGroup = selectEl.id === "tr2-sender"
                ? "sender"
                : (selectEl.id === "tr2-receiver" ? "recipient" : "direction");
            rows.unshift({
                code: selected,
                label: partyLabel(labelGroup, selected),
                is_active: true,
                sort_order: -1,
            });
        }
        selectEl.innerHTML = rows.map((option) => {
            const code = String(option.code || "").trim().toUpperCase();
            const label = String(option.label || code).trim();
            return `<option value="${escapeHtml(code)}" ${code === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
        }).join("");
        if (selected && rows.some((option) => option.code === selected)) {
            selectEl.value = selected;
        } else if (rows[0]) {
            selectEl.value = rows[0].code;
        }
    }

    function renderPartySelects(senderValue = "", receiverValue = "", directionValue = "O") {
        const resolvedSender = String(senderValue || senderOptions()[0]?.code || recipientOptions()[0]?.code || "C").trim().toUpperCase();
        const resolvedReceiver = String(receiverValue || recipientOptions()[0]?.code || "C").trim().toUpperCase();
        renderPartySelectOptions(document.getElementById("tr2-sender"), senderOptions(), resolvedSender);
        renderPartySelectOptions(document.getElementById("tr2-receiver"), recipientOptions(), resolvedReceiver);
        renderPartySelectOptions(document.getElementById("tr2-direction"), directionOptions(), directionValue || "O");
    }

    function currentSenderCode() {
        const fallback = senderOptions()[0]?.code || recipientOptions()[0]?.code || "C";
        return String(document.getElementById("tr2-sender")?.value || fallback).trim().toUpperCase() || fallback;
    }

    function currentReceiverCode() {
        const fallback = recipientOptions()[0]?.code || "C";
        return String(document.getElementById("tr2-receiver")?.value || fallback).trim().toUpperCase() || fallback;
    }

    function currentDirectionCode() {
        const fallback = directionOptions()[0]?.code || "O";
        return String(document.getElementById("tr2-direction")?.value || fallback).trim().toUpperCase() || fallback;
    }

    async function runTransmittalBulkAction(actionId, selectedKeys) {
        const ids = parseBulkTransmittalIds(selectedKeys);
        if (!ids.length) {
            notify("warning", "هیچ ترنسمیتالی انتخاب نشده است.");
            return;
        }

        const selectedRows = selectedTransmittalRows(ids);
        if (!selectedRows.length) {
            notify("warning", "ترنسمیتال‌های انتخاب‌شده دیگر در دسترس نیستند.");
            return;
        }

        let targetRows = selectedRows;
        let operation = "";
        let confirmMessage = "";
        let task = null;

        if (actionId === TR2_BULK_ACTION_ISSUE) {
            operation = "issued";
            targetRows = selectedRows.filter((item) => isDraftTransmittal(item));
            confirmMessage = `آیا ${targetRows.length} ترنسمیتال پیش‌نویس انتخاب‌شده صادر شود؟`;
            task = async (row) => {
                const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
                await mutationBridge.issue(String(row.id), { fetch: getTransmittalFetchFn() });
            };
        } else if (actionId === TR2_BULK_ACTION_VOID) {
            operation = "voided";
            targetRows = selectedRows.filter((item) => canVoidTransmittal(item));
            const reasonInput = prompt("Enter a single void reason for all selected transmittals:");
            if (reasonInput === null) return;
            const reason = reasonInput.trim();
            if (!reason) {
                notify("error", "ثبت دلیل ابطال الزامی است.");
                return;
            }
            confirmMessage = `آیا ${targetRows.length} ترنسمیتال انتخاب‌شده باطل شود؟`;
            task = async (row) => {
                const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
                await mutationBridge.voidItem(String(row.id), reason, { fetch: getTransmittalFetchFn() });
            };
        }

        if (!task) {
            notify("warning", "عملیات گروهی ناشناخته است.");
            return;
        }
        if (!targetRows.length) {
            notify("warning", "هیچ ترنسمیتال واجد شرایطی برای این عملیات وجود ندارد.");
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
                const label = String(row?.transmittal_no || row?.id || "-");
                failures.push(`${label}: ${error?.message || "درخواست ناموفق بود"}`);
            }
        }

        if (success > 0) {
            notify("success", operation === "issued" ? `${success} ترنسمیتال صادر شد.` : `${success} ترنسمیتال باطل شد.`);
        }
        if (failures.length > 0) {
            notify("warning", `${failures.length} عملیات ناموفق بود. ${summarizeBulkErrors(failures)}`);
        }

        const bulk = transmittalBulkBridge();
        if (bulk && typeof bulk.clearSelection === "function") {
            bulk.clearSelection("tr2ListTable");
        }
        if (typeof window.loadTransmittals === "function") {
            await window.loadTransmittals();
        }
    }

    function registerTransmittalBulkActions() {
        if (state.bulkRegistered) return;
        const bulk = transmittalBulkBridge();
        if (!bulk) return;

        bulk.register({
            tableId: "tr2ListTable",
            actions: [
                { id: TR2_BULK_ACTION_ISSUE, label: "صدور پیش‌نویس‌های انتخاب‌شده" },
                { id: TR2_BULK_ACTION_VOID, label: "ابطال ترنسمیتال‌های انتخاب‌شده" },
            ],
            getRowKey(row) {
                return row && row.dataset ? row.dataset.bulkKey : "";
            },
            onAction({ actionId, selectedKeys }) {
                return runTransmittalBulkAction(actionId, selectedKeys);
            },
        });

        state.bulkRegistered = true;
    }

    function getTransmittalFetchFn() {
        return typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch;
    }

    function requireBridge(bridge, name) {
        if (!bridge || typeof bridge !== "object") {
            throw new Error(`ماژول ${name} در دسترس نیست.`);
        }
        return bridge;
    }

    async function request(url, options = {}) {
        const bridge = requireBridge(TS_TRANSMITTAL_DATA, "Transmittal data");
        return bridge.requestJson(url, options, {
            fetch: getTransmittalFetchFn(),
        });
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function tr2DocFileKey(docNumber, fileKind) {
        return `${String(docNumber || "").trim()}::${normalizeTr2FileKind(fileKind)}`;
    }

    function selectedFileKeySet() {
        return new Set(
            state.selectedDocs.map((d) => tr2DocFileKey(d.document_code, d.file_kind || "pdf"))
        );
    }

    function normalizeTr2FileKind(value) {
        const raw = String(value || "").trim().toLowerCase();
        return raw === "native" || raw === "dwg" || raw === "dxf" ? "native" : "pdf";
    }

    function tr2FileKindLabel(value) {
        return normalizeTr2FileKind(value) === "native" ? "Native" : "PDF";
    }

    function normalizeTr2FileOptions(options, fallback = "pdf", includeFallback = true) {
        const source = Array.isArray(options) ? options : [];
        const seen = new Set();
        const normalized = [];
        source.forEach((option) => {
            const value = normalizeTr2FileKind(option?.value || option?.file_kind || option);
            if (seen.has(value)) return;
            seen.add(value);
            normalized.push({
                value,
                label: option?.label || tr2FileKindLabel(value),
                file_name: option?.file_name || "",
            });
        });
        if (!normalized.length && includeFallback) {
            const value = normalizeTr2FileKind(fallback);
            normalized.push({ value, label: tr2FileKindLabel(value), file_name: "" });
        }
        return normalized.sort((a, b) => {
            const order = { pdf: 0, native: 1 };
            return (order[a.value] ?? 9) - (order[b.value] ?? 9);
        });
    }

    function hasTr2FileKind(options, fileKind) {
        return normalizeTr2FileOptions(options, "", false).some(
            (option) => option.value === normalizeTr2FileKind(fileKind)
        );
    }

    function renderTr2FileAction(item, fileKind, selectedKeys) {
        const docNumber = String(item?.doc_number || "").trim();
        const kind = normalizeTr2FileKind(fileKind);
        const label = tr2FileKindLabel(kind);
        const available = hasTr2FileKind(item?.file_options, kind);
        const alreadySelected = selectedKeys.has(tr2DocFileKey(docNumber, kind));
        let text = `+ ${label}`;
        let title = "";
        if (!available) {
            text = `${label} ندارد`;
            title = `${label} ندارد`;
        } else if (alreadySelected) {
            text = `✓ ${label}`;
            title = `${label} قبلاً به این ترنسمیتال اضافه شده`;
        }
        const disabled = !available || alreadySelected;
        return `
            <button
                class="btn-archive-icon"
                type="button"
                ${disabled ? "disabled" : ""}
                ${title ? `title="${escapeHtml(title)}"` : ""}
                data-tr2-action="doc-add"
                data-doc-number="${escapeHtml(docNumber)}"
                data-file-kind="${escapeHtml(kind)}"
            >${escapeHtml(text)}</button>
        `;
    }

    function currentProjectCode() {
        return String(document.getElementById("tr2-project")?.value || "").trim().toUpperCase();
    }

    function currentDisciplineCode() {
        const disciplineEl = document.getElementById("tr2-discipline");
        if (disciplineEl instanceof HTMLSelectElement && disciplineEl.multiple) {
            return Array.from(disciplineEl.selectedOptions)
                .map((option) => String(option.value || "").trim().toUpperCase())
                .filter(Boolean)
                .join(",");
        }
        return String(disciplineEl?.value || "").trim().toUpperCase();
    }

    function setSelectedDisciplineCodes(codes = []) {
        const disciplineEl = document.getElementById("tr2-discipline");
        if (!(disciplineEl instanceof HTMLSelectElement)) return;
        const selected = new Set((Array.isArray(codes) ? codes : [codes])
            .map((code) => String(code || "").trim().toUpperCase())
            .filter(Boolean));
        Array.from(disciplineEl.options).forEach((option) => {
            const code = String(option.value || "").trim().toUpperCase();
            option.selected = selected.size ? selected.has(code) : code === "";
        });
    }

    function currentHeaderStatus() {
        return normalizeTransmittalStatus(document.getElementById("tr2-edit-status")?.textContent || "draft");
    }

    function setEditBanner(id = null, status = "draft") {
        const el = document.getElementById("tr2-edit-status");
        const idEl = document.getElementById("tr2-edit-id");
        const titleEl = document.getElementById("tr2-editor-title");
        if (!el || !idEl) return;
        if (id) {
            idEl.textContent = id;
            el.textContent = formatStatusLabel(status);
            if (titleEl) titleEl.textContent = "ویرایش ترنسمیتال";
        } else {
            idEl.textContent = "جدید";
            el.textContent = formatStatusLabel("draft");
            if (titleEl) titleEl.textContent = "ترنسمیتال جدید";
        }
    }

    function resetCreateForm() {
        state.editingId = null;
        state.selectedDocs = [];
        state.searchDocs = [];
        const projectEl = document.getElementById("tr2-project");
        const subjectEl = document.getElementById("tr2-subject");
        const notesEl = document.getElementById("tr2-notes");
        const searchEl = document.getElementById("tr2-doc-search");
        const nextNoEl = document.getElementById("tr2-next-number");
        if (projectEl) projectEl.disabled = false;
        setSelectedDisciplineCodes([]);
        renderPartySelects();
        if (subjectEl) subjectEl.value = "";
        if (notesEl) notesEl.value = "";
        if (searchEl) searchEl.value = "";
        if (nextNoEl) nextNoEl.value = "";
        setEditBanner(null, "draft");
        renderSelectedDocs();
        renderSearchResults([]);
    }

    function renderSelectedDocs() {
        const tbody = document.getElementById("tr2-docs-body");
        if (!tbody) return;
        const selectedRows = Array.isArray(state.selectedDocs) ? state.selectedDocs : [];
        if (!selectedRows.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="center-text muted">هنوز مدرکی اضافه نشده است</td></tr>';
            return;
        }
        tbody.innerHTML = selectedRows.map((d, idx) => `
            <tr>
                <td>${escapeHtml(d.document_code)}</td>
                <td><input class="form-input" style="max-width:90px" value="${escapeHtml(d.revision)}" data-tr2-action="doc-field-change" data-index="${idx}" data-field="revision"></td>
                <td>
                    <select class="form-input" data-tr2-action="doc-field-change" data-index="${idx}" data-field="status">
                        <option value="IFA" ${d.status === "IFA" ? "selected" : ""}>IFA</option>
                        <option value="IFC" ${d.status === "IFC" ? "selected" : ""}>IFC</option>
                        <option value="IFI" ${d.status === "IFI" ? "selected" : ""}>IFI</option>
                    </select>
                </td>
                <td><span class="file-badge">${escapeHtml(tr2FileKindLabel(d.file_kind || "pdf"))}</span></td>
                <td><input class="form-input" style="min-width:170px" value="${escapeHtml(d.remarks || "")}" placeholder="توضیحات" data-tr2-action="doc-field-change" data-index="${idx}" data-field="remarks"></td>
                <td class="center-text"><input type="checkbox" ${d.electronic_copy ? "checked" : ""} data-tr2-action="doc-field-change" data-index="${idx}" data-field="electronic_copy"></td>
                <td class="center-text"><input type="checkbox" ${d.hard_copy ? "checked" : ""} data-tr2-action="doc-field-change" data-index="${idx}" data-field="hard_copy"></td>
                <td><button class="btn-archive-icon" type="button" data-tr2-action="doc-remove" data-index="${idx}">حذف</button></td>
            </tr>
        `).join("");
    }

    function renderStatusCell(item) {
        const normalizedStatus = normalizeTransmittalStatus(item?.status);
        const statusLabel = formatStatusLabel(normalizedStatus);
        if (normalizedStatus !== "void") {
            return escapeHtml(statusLabel);
        }

        const tooltipParts = [];
        if (item?.void_reason) tooltipParts.push(`دلیل: ${item.void_reason}`);
        if (item?.voided_by) tooltipParts.push(`توسط: ${item.voided_by}`);
        if (item?.voided_at) tooltipParts.push(`تاریخ: ${formatShamsiDateTime(item.voided_at)}`);
        const tooltip = tooltipParts.join(" | ") || "باطل";
        return `<span title="${escapeHtml(tooltip)}" style="cursor: help;">${escapeHtml(statusLabel)}</span>`;
    }

    function relationTypeLabel(value) {
        const normalized = String(value || "related").trim().toLowerCase();
        if (normalized === "references") return "ارجاع";
        if (normalized === "supersedes") return "جایگزین";
        if (normalized === "contains_document") return "شامل مدرک";
        return "مرتبط";
    }

    function renderDetailDocuments(documents) {
        const rows = Array.isArray(documents) ? documents : [];
        if (!rows.length) {
            return '<p class="center-text muted" style="margin:12px 0;">مدرکی در این ترنسمیتال ثبت نشده است.</p>';
        }
        return `
            <div class="table-responsive" style="margin-top:10px;">
                <table class="archive-table">
                    <thead>
                        <tr>
                            <th>Doc No</th>
                            <th>Title</th>
                            <th>Revision</th>
                            <th>Status</th>
                            <th>File</th>
                            <th>Remarks</th>
                            <th>E-Copy</th>
                            <th>Hard</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map((doc) => `
                            <tr>
                                <td style="font-family: monospace; font-weight: 700;">${escapeHtml(doc?.document_code || "-")}</td>
                                <td>${escapeHtml(doc?.document_title || "-")}</td>
                                <td>${escapeHtml(doc?.revision || "-")}</td>
                                <td>${escapeHtml(doc?.status || "-")}</td>
                                <td>${escapeHtml(doc?.file_label || tr2FileKindLabel(doc?.file_kind || "pdf"))}</td>
                                <td>${escapeHtml(doc?.remarks || "-")}</td>
                                <td>${doc?.electronic_copy ? "دارد" : "ندارد"}</td>
                                <td>${doc?.hard_copy ? "دارد" : "ندارد"}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function renderDetailCorrespondenceRelations(relations) {
        const rows = Array.isArray(relations) ? relations : [];
        if (!rows.length) {
            return '<p class="center-text muted" style="margin:12px 0;">مکاتبه‌ای به این ترنسمیتال لینک نشده است.</p>';
        }
        return `
            <div class="table-responsive" style="margin-top:10px;">
                <table class="archive-table">
                    <thead>
                        <tr>
                            <th>شماره مکاتبه</th>
                            <th>موضوع</th>
                            <th>نوع ارتباط</th>
                            <th>وضعیت</th>
                            <th>تاریخ لینک</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map((relation) => `
                            <tr>
                                <td style="font-family: monospace; font-weight: 700;">${escapeHtml(relation?.reference_no || "-")}</td>
                                <td>${escapeHtml(relation?.subject || "-")}</td>
                                <td>${escapeHtml(relationTypeLabel(relation?.relation_type))}</td>
                                <td>${escapeHtml(relation?.status || "-")}</td>
                                <td>${formatShamsiDate(relation?.created_at)}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function renderDetailActions(detail) {
        const id = String(detail?.id || detail?.transmittal_no || "").trim();
        const status = normalizeTransmittalStatus(detail?.status);
        if (!id) return "";
        return `
            <div class="tr2-detail-actions">
                ${status === "draft" ? `<button class="btn btn-primary" type="button" data-tr2-action="edit-item" data-id="${escapeHtml(id)}"><span class="material-icons-round">edit</span>ویرایش کامل</button>` : ""}
                <button class="btn btn-secondary" type="button" data-tr2-action="download-cover" data-id="${escapeHtml(id)}"><span class="material-icons-round">preview</span>پیش‌نمایش چاپ</button>
                ${status === "draft" ? `<button class="btn btn-primary" type="button" data-tr2-action="issue-item" data-id="${escapeHtml(id)}"><span class="material-icons-round">send</span>صدور</button>` : ""}
                ${status === "draft" || status === "issued" ? `<button class="btn btn-secondary" type="button" data-tr2-action="void-item" data-id="${escapeHtml(id)}"><span class="material-icons-round">cancel</span>ابطال</button>` : ""}
            </div>
        `;
    }

    function renderTransmittalDetail(detail) {
        const drawer = document.getElementById("tr2-detail-drawer");
        const content = document.getElementById("tr2-detail-content");
        const meta = document.getElementById("tr2-detail-drawer-meta");
        if (!drawer || !content) return;
        const relations = Array.isArray(detail?.correspondence_relations) ? detail.correspondence_relations : [];
        const senderLabel = partyLabel("sender", detail?.sender, detail?.sender_label);
        const receiverLabel = partyLabel("recipient", detail?.receiver, detail?.receiver_label);
        const directionLabel = partyLabel("direction", detail?.direction, detail?.direction_label);
        if (meta) {
            meta.innerHTML = `
                <span class="ci-form-badge ci-form-status-badge">${escapeHtml(formatStatusLabel(detail?.status))}</span>
            `;
        }
        content.innerHTML = `
            <div class="tr2-detail-hero">
                <div>
                    <div class="tr2-detail-kicker">شماره ترنسمیتال</div>
                    <div class="tr2-detail-number">${escapeHtml(detail?.transmittal_no || detail?.id || "-")}</div>
                    <div class="tr2-detail-subject">${escapeHtml(detail?.subject || "-")}</div>
                </div>
                ${renderDetailActions(detail)}
            </div>
            <div class="general-overview-grid" style="margin-bottom: 12px;">
                <div class="general-overview-card">
                    <div class="general-overview-value">${escapeHtml(senderLabel)}</div>
                    <div class="general-overview-label">فرستنده</div>
                </div>
                <div class="general-overview-card">
                    <div class="general-overview-value">${escapeHtml(receiverLabel)}</div>
                    <div class="general-overview-label">طرف مقابل</div>
                </div>
                <div class="general-overview-card">
                    <div class="general-overview-value">${escapeHtml(directionLabel)}</div>
                    <div class="general-overview-label">جهت</div>
                </div>
                <div class="general-overview-card">
                    <div class="general-overview-value">${escapeHtml(formatStatusLabel(detail?.status))}</div>
                    <div class="general-overview-label">وضعیت</div>
                </div>
                <div class="general-overview-card">
                    <div class="general-overview-value">${escapeHtml(Array.isArray(detail?.documents) ? detail.documents.length : 0)}</div>
                    <div class="general-overview-label">مدارک</div>
                </div>
                <div class="general-overview-card">
                    <div class="general-overview-value">${escapeHtml(relations.length)}</div>
                    <div class="general-overview-label">مکاتبات مرتبط</div>
                </div>
                <div class="general-overview-card">
                    <div class="general-overview-value">${formatShamsiDate(detail?.created_at)}</div>
                    <div class="general-overview-label">تاریخ ایجاد</div>
                </div>
            </div>
            <div style="margin-bottom: 14px;">
                <h4 class="general-settings-title" style="font-size:0.9rem; margin-bottom:6px;">
                    <span class="material-icons-round">description</span>
                    مدارک ترنسمیتال
                </h4>
                ${renderDetailDocuments(detail?.documents)}
            </div>
            <div>
                <h4 class="general-settings-title" style="font-size:0.9rem; margin-bottom:6px;">
                    <span class="material-icons-round">mail</span>
                    مکاتبات لینک‌شده به این ترنسمیتال
                </h4>
                ${renderDetailCorrespondenceRelations(relations)}
            </div>
        `;
        drawer.hidden = false;
        drawer.classList.add("is-open");
        document.body.classList.add("ci-drawer-open");
    }

    window.closeTransmittalDetail = function closeTransmittalDetail() {
        state.activeDetailId = null;
        const drawer = document.getElementById("tr2-detail-drawer");
        const content = document.getElementById("tr2-detail-content");
        const meta = document.getElementById("tr2-detail-drawer-meta");
        if (drawer) {
            drawer.classList.remove("is-open");
            drawer.hidden = true;
        }
        if (content) content.innerHTML = "";
        if (meta) meta.innerHTML = "";
        if (!document.querySelector(".ci-drawer.is-open")) {
            document.body.classList.remove("ci-drawer-open");
        }
    };

    window.openTransmittalDetail = async function openTransmittalDetail(transmittalId) {
        const id = String(transmittalId || "").trim();
        if (!id) return;
        try {
            const drawer = document.getElementById("tr2-detail-drawer");
            const content = document.getElementById("tr2-detail-content");
            if (drawer) {
                drawer.hidden = false;
                drawer.classList.add("is-open");
                document.body.classList.add("ci-drawer-open");
            }
            if (content) content.innerHTML = '<p class="center-text muted" style="margin:12px 0;">در حال بارگذاری جزئیات...</p>';
            const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
            const detail = await mutationBridge.getDetail(id, { fetch: getTransmittalFetchFn() });
            state.activeDetailId = id;
            renderTransmittalDetail(detail);
        } catch (error) {
            notify("error", error.message || "بارگذاری جزئیات ترنسمیتال ناموفق بود");
        }
    };

    function renderSearchResults(items) {
        const tbody = document.getElementById("tr2-search-body");
        if (!tbody) return;
        state.searchDocs = Array.isArray(items) ? items : [];
        if (!items.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="center-text muted">مدرکی یافت نشد</td></tr>';
            return;
        }

        const selectedKeys = selectedFileKeySet();
        tbody.innerHTML = items.map((item) => {
            const docNumber = String(item.doc_number || "").trim();
            return `
                <tr>
                    <td>${escapeHtml(docNumber)}</td>
                    <td>${escapeHtml(item.doc_title || "-")}</td>
                    <td>${escapeHtml(item.revision || "00")}</td>
                    <td>${escapeHtml(item.status || "-")}</td>
                    <td><div style="display:flex; gap:6px; justify-content:center;">${renderTr2FileAction(item, "pdf", selectedKeys)}${renderTr2FileAction(item, "native", selectedKeys)}</div></td>
                </tr>
            `;
        }).join("");
    }

    async function loadTransmittalOptions() {
        try {
            const dataBridge = requireBridge(TS_TRANSMITTAL_DATA, "Transmittal data");
            const options = await dataBridge.loadOptions({ fetch: getTransmittalFetchFn() });
            state.directionOptions = normalizePartyOptions(options?.direction_options, DEFAULT_DIRECTION_OPTIONS);
            state.recipientOptions = normalizePartyOptions(options?.recipient_options, DEFAULT_RECIPIENT_OPTIONS);
            state.senderOptions = normalizePartyOptions(options?.sender_options, state.recipientOptions);
        } catch (_) {
            state.directionOptions = DEFAULT_DIRECTION_OPTIONS;
            state.recipientOptions = DEFAULT_RECIPIENT_OPTIONS;
            state.senderOptions = DEFAULT_RECIPIENT_OPTIONS;
        }
    }

    async function loadCreateFormData() {
        const [formData] = await Promise.all([
            request("/api/v1/archive/form-data"),
            loadTransmittalOptions(),
        ]);
        state.formData = formData;
        const projects = Array.isArray(state.formData.projects) ? state.formData.projects : [];
        const disciplines = Array.isArray(state.formData.disciplines) ? state.formData.disciplines : [];

        const projectEl = document.getElementById("tr2-project");
        const disciplineEl = document.getElementById("tr2-discipline");
        if (projectEl) {
            projectEl.innerHTML = projects.map((p) => {
                const code = (p.code || "").toUpperCase();
                const label = `${code} - ${p.name || code}`;
                return `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`;
            }).join("");
        }
        renderPartySelects();
        if (disciplineEl) {
            disciplineEl.innerHTML = `<option value="">همه دیسیپلین‌ها</option>` + disciplines.map((d) => {
                const code = (d.code || "").toUpperCase();
                const label = `${code} - ${d.name || code}`;
                return `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`;
            }).join("");
            setSelectedDisciplineCodes([]);
        }
        state.createReady = true;
    }

    async function loadTransmittalStats() {
        const dataBridge = requireBridge(TS_TRANSMITTAL_DATA, "Transmittal data");
        const stats = await dataBridge.loadStats({ fetch: getTransmittalFetchFn() });
        const totalEl = document.getElementById("tr2-stat-total");
        const monthEl = document.getElementById("tr2-stat-month");
        const lastEl = document.getElementById("tr2-stat-last");
        if (totalEl) totalEl.textContent = String(stats.total_transmittals ?? 0);
        if (monthEl) monthEl.textContent = String(stats.this_month ?? 0);
        if (lastEl) lastEl.textContent = String(stats.last_created || "-");
    }

    function setTransmittalMode(mode = "list") {
        const uiBridge = requireBridge(TS_TRANSMITTAL_UI, "Transmittal UI");
        const handled = uiBridge.setMode(mode, {
            getElementById: (id) => document.getElementById(id),
        });
        if (!handled) {
            throw new Error("Transmittal UI bridge did not handle setMode.");
        }
        return handled;
    }

    window.loadTransmittals = async function loadTransmittals() {
        const tbody = document.getElementById("tr2-list-body");
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="8" class="center-text muted" style="padding: 26px;">در حال بارگذاری...</td></tr>';
        }
        try {
            const dataBridge = requireBridge(TS_TRANSMITTAL_DATA, "Transmittal data");
            const [items] = await Promise.all([
                dataBridge.loadList({ fetch: getTransmittalFetchFn() }),
                loadTransmittalStats(),
            ]);
            state.listItems = Array.isArray(items) ? items : [];
            if (!tbody) return;
            if (!state.listItems.length) {
                tbody.innerHTML = '<tr><td colspan="8" class="center-text muted">ترنسمیتالی یافت نشد</td></tr>';
                return;
            }
            tbody.innerHTML = state.listItems.map((t) => {
                const status = normalizeTransmittalStatus(t.status);
                const senderLabel = partyLabel("sender", t.sender, t.sender_label);
                const receiverLabel = partyLabel("recipient", t.receiver, t.receiver_label);
                return `
                <tr class="tr2-list-row" data-bulk-key="${escapeHtml(String(t.id || '').trim())}" data-transmittal-id="${escapeHtml(String(t.id || '').trim())}" data-transmittal-status="${escapeHtml(status)}">
                    <td style="font-family: monospace; font-weight: 700;">${escapeHtml(t.transmittal_no || t.id)}</td>
                    <td>${escapeHtml(t.subject || "-")}</td>
                    <td>${escapeHtml(senderLabel)}</td>
                    <td>${escapeHtml(receiverLabel)}</td>
                    <td>${escapeHtml(t.doc_count)}</td>
                    <td>${renderStatusCell(t)}</td>
                    <td>${formatShamsiDate(t.created_at)}</td>
                    <td>
                        <div class="archive-row-menu" data-tr2-row-menu>
                            <button class="btn-archive-icon archive-row-menu-trigger" type="button" title="عملیات" data-tr2-action="toggle-row-menu" aria-expanded="false">
                                <span class="material-icons-round">more_vert</span>
                            </button>
                            <div class="archive-row-menu-dropdown">
                                <button class="archive-row-menu-item" type="button" data-tr2-action="detail-item" data-id="${escapeHtml(t.id)}">
                                    <span class="material-icons-round">visibility</span>
                                    <span>جزئیات</span>
                                </button>
                                <button class="archive-row-menu-item" type="button" data-tr2-action="download-cover" data-id="${escapeHtml(t.id)}">
                                    <span class="material-icons-round">preview</span>
                                    <span>پیش‌نمایش چاپ</span>
                                </button>
                                ${status === "draft" ? `<button class="archive-row-menu-item" type="button" data-tr2-action="edit-item" data-id="${escapeHtml(t.id)}"><span class="material-icons-round">edit</span><span>ویرایش</span></button>` : ""}
                                ${status === "draft" ? `<button class="archive-row-menu-item" type="button" data-tr2-action="issue-item" data-id="${escapeHtml(t.id)}"><span class="material-icons-round">send</span><span>ارسال</span></button>` : ""}
                                ${status === "draft" || status === "issued" ? `<button class="archive-row-menu-item" type="button" data-tr2-action="void-item" data-id="${escapeHtml(t.id)}"><span class="material-icons-round">cancel</span><span>ابطال</span></button>` : ""}
                            </div>
                        </div>
                    </td>
                </tr>
            `;
            }).join("");
        } catch (error) {
            state.listItems = [];
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="8" class="center-text text-danger">خطا در بارگذاری</td></tr>';
            }
            notify("error", error.message || "بارگذاری ترنسمیتال ناموفق بود");
        }
    };

    window.showCreateMode = async function showCreateMode() {
        setTransmittalMode("create");
        if (typeof window.closeTransmittalDetail === "function") {
            window.closeTransmittalDetail();
        }
        if (!state.createReady) {
            await loadCreateFormData();
        }
        resetCreateForm();
        const pendingDoc =
            typeof window.consumePendingTransmittalDoc === "function"
                ? window.consumePendingTransmittalDoc()
                : null;
        if (pendingDoc && typeof pendingDoc === "object") {
            const projectCode = String(pendingDoc.project_code || "").trim().toUpperCase();
            const disciplineCode = String(pendingDoc.discipline_code || "").trim().toUpperCase();
            const docNumber = String(pendingDoc.doc_number || "").trim();
            const revision = String(pendingDoc.revision || "00").trim() || "00";
            const status = String(pendingDoc.status || "IFA").trim() || "IFA";

            const projectEl = document.getElementById("tr2-project");
            if (projectEl && projectCode) projectEl.value = projectCode;
            if (disciplineCode) setSelectedDisciplineCodes([disciplineCode]);

            await refreshTransmittalNumber();
            await searchEligibleDocs();

            if (docNumber) {
                window.addTr2Doc({
                    doc_number: docNumber,
                    revision,
                    status,
                    doc_title: pendingDoc.doc_title || pendingDoc.doc_title_p || pendingDoc.doc_title_e || docNumber,
                    file_kind: pendingDoc.file_kind || "pdf",
                    file_options: pendingDoc.file_options,
                });
            }
            return;
        }
        await refreshTransmittalNumber();
        await searchEligibleDocs();
    };

    window.showListMode = function showListMode() {
        setTransmittalMode("list");
    };

    window.openEditTransmittal = async function openEditTransmittal(transmittalId) {
        try {
            if (!state.createReady) {
                await loadCreateFormData();
            }
            const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
            const detail = await mutationBridge.getDetail(String(transmittalId), { fetch: getTransmittalFetchFn() });
            if ((detail.status || "").toLowerCase() !== "draft") {
                notify("error", "ÙÙ‚Ø· Draft Ù‚Ø§Ø¨Ù„ ÙˆÛŒØ±Ø§ÛŒØ´ Ø§Ø³Øª");
                return;
            }

            if (typeof window.closeTransmittalDetail === "function") {
                window.closeTransmittalDetail();
            }
            setTransmittalMode("create");

            state.editingId = detail.id;
            setEditBanner(detail.id, detail.status || "draft");

            const projectEl = document.getElementById("tr2-project");
            const subjectEl = document.getElementById("tr2-subject");
            const notesEl = document.getElementById("tr2-notes");
            if (projectEl) {
                projectEl.value = (detail.project_code || "").toUpperCase();
                projectEl.disabled = true;
            }
            setSelectedDisciplineCodes([]);
            renderPartySelects(detail.sender || "", detail.receiver || "", detail.direction || "O");
            if (subjectEl) subjectEl.value = "";
            if (notesEl) notesEl.value = detail.notes || "";

            state.selectedDocs = Array.isArray(detail.documents) ? detail.documents.map((d) => {
                const fileOptions = normalizeTr2FileOptions(d.file_options, d.file_kind || "pdf");
                const rawKind = normalizeTr2FileKind(d.file_kind || fileOptions[0]?.value || "pdf");
                const fileKind = fileOptions.some((option) => option.value === rawKind)
                    ? rawKind
                    : normalizeTr2FileKind(fileOptions[0]?.value || "pdf");
                return {
                    document_code: d.document_code,
                    revision: d.revision || "00",
                    status: d.status || "IFA",
                    file_kind: fileKind,
                    file_options: fileOptions,
                    remarks: d.remarks || "",
                    electronic_copy: Boolean(d.electronic_copy),
                    hard_copy: Boolean(d.hard_copy),
                };
            }) : [];
            renderSelectedDocs();
            await refreshTransmittalNumber();
            await searchEligibleDocs();
        } catch (error) {
            notify("error", error.message || "Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Draft Ø¨Ø±Ø§ÛŒ ÙˆÛŒØ±Ø§ÛŒØ´ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        }
    };

    async function refreshTransmittalNumber() {
        const project = currentProjectCode();
        const sender = currentSenderCode();
        const receiver = currentReceiverCode();
        const output = document.getElementById("tr2-next-number");
        if (!project) {
            if (output) output.value = "";
            return;
        }
        try {
            const dataBridge = requireBridge(TS_TRANSMITTAL_DATA, "Transmittal data");
            const transmittalNo = await dataBridge.getNextNumber(
                {
                    projectCode: project,
                    sender,
                    receiver,
                },
                { fetch: getTransmittalFetchFn() }
            );
            if (output) output.value = transmittalNo || "";
        } catch (error) {
            if (output) output.value = "";
            notify("error", error.message || "Ø´Ù…Ø§Ø±Ù‡â€ŒØ¯Ù‡ÛŒ Ø®ÙˆØ¯Ú©Ø§Ø± Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        }
    }
    window.refreshTransmittalNumber = refreshTransmittalNumber;

    window.searchEligibleDocs = async function searchEligibleDocs() {
        const project = currentProjectCode();
        const discipline = currentDisciplineCode();
        const q = String(document.getElementById("tr2-doc-search")?.value || "").trim();
        if (!project) {
            renderSearchResults([]);
            return;
        }
        try {
            const dataBridge = requireBridge(TS_TRANSMITTAL_DATA, "Transmittal data");
            const items = await dataBridge.searchEligibleDocs(
                {
                    projectCode: project,
                    disciplineCode: discipline,
                    q,
                    limit: 30,
                },
                { fetch: getTransmittalFetchFn() }
            );
            renderSearchResults(Array.isArray(items) ? items : []);
        } catch (error) {
            renderSearchResults([]);
            notify("error", error.message || "Ø¬Ø³ØªØ¬ÙˆÛŒ Ù…Ø¯Ø§Ø±Ú© Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        }
    };

    function findSearchDocByNumber(docNumber) {
        const normalized = String(docNumber || "").trim();
        if (!normalized) return null;
        return state.searchDocs.find((item) => String(item?.doc_number || "").trim() === normalized) || null;
    }

    window.addTr2Doc = function addTr2Doc(item, requestedFileKind = "") {
        const resolved = typeof item === "string" ? findSearchDocByNumber(item) : item;
        if (!resolved || !resolved.doc_number) return;
        const docNumber = String(resolved.doc_number || "").trim();
        const fileOptions = normalizeTr2FileOptions(
            resolved.file_options,
            resolved.default_file_kind || resolved.file_kind || requestedFileKind || "pdf",
            !Array.isArray(resolved.file_options)
        );
        const requestedKind = normalizeTr2FileKind(requestedFileKind || resolved.default_file_kind || resolved.file_kind || fileOptions[0]?.value || "pdf");
        const fileKind = fileOptions.some((option) => option.value === requestedKind)
            ? requestedKind
            : normalizeTr2FileKind(fileOptions[0]?.value || "pdf");
        if (!fileOptions.some((option) => option.value === fileKind)) {
            notify("error", `${tr2FileKindLabel(fileKind)} برای این مدرک موجود نیست`);
            return;
        }
        if (state.selectedDocs.some((d) => tr2DocFileKey(d.document_code, d.file_kind || "pdf") === tr2DocFileKey(docNumber, fileKind))) return;
        state.selectedDocs.push({
            document_code: docNumber,
            revision: resolved.revision || "00",
            status: resolved.status && resolved.status !== "Registered" ? resolved.status : "IFA",
            file_kind: fileKind,
            file_options: fileOptions,
            remarks: "",
            electronic_copy: true,
            hard_copy: false,
        });
        renderSelectedDocs();
        renderSearchResults(state.searchDocs);
    };

    window.updateTr2Doc = function updateTr2Doc(index, field, value) {
        if (!state.selectedDocs[index]) return;
        state.selectedDocs[index][field] = field === "file_kind" ? normalizeTr2FileKind(value) : value;
    };

    window.removeTr2Doc = function removeTr2Doc(index) {
        if (!Number.isInteger(index) || index < 0 || index >= state.selectedDocs.length) return;
        state.selectedDocs.splice(index, 1);
        renderSelectedDocs();
        renderSearchResults(state.searchDocs);
    };

    async function submitTransmittal(issueNow = false) {
        const project = currentProjectCode();
        const sender = currentSenderCode();
        const receiver = currentReceiverCode();
        const direction = currentDirectionCode();
        const subject = String(document.getElementById("tr2-subject")?.value || "").trim();
        const notes = String(document.getElementById("tr2-notes")?.value || "").trim();
        const btn = document.getElementById("tr2-submit-btn");

        if (!project) {
            notify("error", "Ù¾Ø±ÙˆÚ˜Ù‡ Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª");
            return;
        }
        if (!state.selectedDocs.length) {
            notify("error", "Ø­Ø¯Ø§Ù‚Ù„ ÛŒÚ© Ù…Ø¯Ø±Ú© Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯");
            return;
        }
        if (!sender || !receiver || !direction) {
            notify("error", "فرستنده، طرف مقابل و جهت ترنسمیتال الزامی است");
            return;
        }

        if (window.UI && typeof window.UI.setBtnLoading === "function") {
            window.UI.setBtnLoading(btn, true);
        }
        try {
            const payload = {
                project_code: project,
                sender,
                receiver,
                direction,
                subject,
                notes,
                issue_now: issueNow,
                documents: state.selectedDocs.map((d) => ({
                    document_code: d.document_code,
                    revision: d.revision || "00",
                    status: d.status || "IFA",
                    file_kind: normalizeTr2FileKind(d.file_kind || "pdf"),
                    remarks: d.remarks || "",
                    electronic_copy: Boolean(d.electronic_copy),
                    hard_copy: Boolean(d.hard_copy),
                })),
            };
            let result;
            const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
            if (state.editingId) {
                result = await mutationBridge.update(String(state.editingId), payload, { fetch: getTransmittalFetchFn() });
                if (issueNow && currentHeaderStatus() === "draft") {
                    await mutationBridge.issue(String(state.editingId), { fetch: getTransmittalFetchFn() });
                }
            } else {
                result = await mutationBridge.create(payload, { fetch: getTransmittalFetchFn() });
            }
            notify("success", issueNow ? `ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ ØµØ§Ø¯Ø± Ø´Ø¯: ${result.transmittal_no || state.editingId}` : "Draft Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯");
            showListMode();
            await loadTransmittals();
        } catch (error) {
            notify("error", error.message || "Ø«Ø¨Øª ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        } finally {
            if (window.UI && typeof window.UI.setBtnLoading === "function") {
                window.UI.setBtnLoading(btn, false);
            }
        }
    }
    window.submitTransmittal = () => submitTransmittal(false);
    window.submitAndIssueTransmittal = () => submitTransmittal(true);

    window.issueTransmittal = async function issueTransmittal(id) {
        try {
            const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
            await mutationBridge.issue(String(id), { fetch: getTransmittalFetchFn() });
            notify("success", "ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ ØµØ§Ø¯Ø± Ø´Ø¯");
            await loadTransmittals();
            if (state.activeDetailId === String(id) && typeof window.openTransmittalDetail === "function") {
                await window.openTransmittalDetail(String(id));
            }
        } catch (error) {
            notify("error", error.message || "ØµØ¯ÙˆØ± ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        }
    };

    window.voidTransmittal = async function voidTransmittal(id) {
        const reasonInput = prompt("Ø¯Ù„ÛŒÙ„ Ø§Ø¨Ø·Ø§Ù„ ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ Ø±Ø§ ÙˆØ§Ø±Ø¯ Ú©Ù†ÛŒØ¯:");
        if (reasonInput === null) return;
        const reason = reasonInput.trim();
        if (!reason) {
            notify("error", "Ø«Ø¨Øª Ø¯Ù„ÛŒÙ„ Ø§Ø¨Ø·Ø§Ù„ Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª");
            return;
        }
        try {
            const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
            await mutationBridge.voidItem(String(id), reason, { fetch: getTransmittalFetchFn() });
            notify("success", "ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ Ø¨Ø§Ø·Ù„ Ø´Ø¯");
            await loadTransmittals();
            if (state.activeDetailId === String(id) && typeof window.openTransmittalDetail === "function") {
                await window.openTransmittalDetail(String(id));
            }
        } catch (error) {
            notify("error", error.message || "Ø§Ø¨Ø·Ø§Ù„ ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        }
    };

    function closeTransmittalPrintPreview() {
        const modal = document.getElementById("tr2-print-preview-modal");
        const body = document.getElementById("tr2-print-preview-body");
        const meta = document.getElementById("tr2-print-preview-meta");
        if (modal) {
            modal.style.display = "none";
            modal.setAttribute("aria-hidden", "true");
        }
        if (body) body.innerHTML = "";
        if (meta) meta.textContent = "-";
        if (state.printPreviewUrl) {
            window.URL.revokeObjectURL(state.printPreviewUrl);
        }
        state.printPreviewUrl = "";
        state.printPreviewId = null;
    }

    function downloadBlob(blob, fileName) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    }

    window.closeTransmittalPrintPreview = function closeTransmittalPrintPreviewWindow() {
        closeTransmittalPrintPreview();
    };

    window.printTransmittalPreview = function printTransmittalPreview() {
        const frame = document.querySelector("#tr2-print-preview-body iframe");
        const frameWindow = frame?.contentWindow;
        if (!frameWindow) {
            notify("error", "پیش‌نمایش چاپ هنوز آماده نیست");
            return;
        }
        frameWindow.focus();
        frameWindow.print();
    };

    window.downloadTransmittalPreviewPdf = async function downloadTransmittalPreviewPdf() {
        const id = String(state.printPreviewId || "").trim();
        if (!id) {
            notify("error", "ترنسمیتال برای دانلود مشخص نیست");
            return;
        }
        try {
            const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
            const blob = await mutationBridge.downloadCover(id, { fetch: getTransmittalFetchFn() });
            downloadBlob(blob, `Transmittal_${id}.pdf`);
            notify("success", "فایل PDF دانلود شد");
        } catch (error) {
            notify("error", error.message || "دانلود PDF ناموفق بود");
        }
    };

    window.downloadTransmittalCover = async function downloadTransmittalCover(id) {
        try {
            const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
            const result = await mutationBridge.previewCover(String(id), { fetch: getTransmittalFetchFn() });
            closeTransmittalPrintPreview();
            const modal = document.getElementById("tr2-print-preview-modal");
            const body = document.getElementById("tr2-print-preview-body");
            const meta = document.getElementById("tr2-print-preview-meta");
            if (!modal || !body) {
                throw new Error("پنجره پیش‌نمایش چاپ در صفحه پیدا نشد");
            }
            const blob = new Blob([result.html || ""], { type: "text/html;charset=utf-8" });
            const url = window.URL.createObjectURL(blob);
            state.printPreviewUrl = url;
            state.printPreviewId = String(id);
            if (meta) meta.textContent = `ترنسمیتال ${String(id)}`;
            body.innerHTML = `<iframe class="tr2-print-preview-frame" src="${url}" title="پیش‌نمایش چاپ ترنسمیتال"></iframe>`;
            modal.style.display = "flex";
            modal.setAttribute("aria-hidden", "false");
        } catch (error) {
            notify("error", error.message || "پیش‌نمایش چاپ ترنسمیتال ناموفق بود");
        }
    };

    function bindTransmittalTemplateActions() {
        const root = document.getElementById("view-transmittal");
        if (!root || root.dataset.tr2ActionsBound === "1") return;

        const uiBridge = requireBridge(TS_TRANSMITTAL_UI, "Transmittal UI");
        const handled = uiBridge.bindTemplateActions(root, {
            refreshList: () => window.loadTransmittals(),
            showCreate: () => window.showCreateMode(),
            previewNumber: () => refreshTransmittalNumber(),
            showList: () => window.showListMode(),
            searchDocs: () => window.searchEligibleDocs(),
            submitDraft: () => window.submitTransmittal(),
            submitIssue: () => window.submitAndIssueTransmittal(),
            downloadCover: (id) => window.downloadTransmittalCover(id),
            closePrintPreview: () => window.closeTransmittalPrintPreview(),
            printPreview: () => window.printTransmittalPreview(),
            downloadPreview: () => window.downloadTransmittalPreviewPdf(),
            detailItem: (id) => window.openTransmittalDetail(id),
            closeDetail: () => window.closeTransmittalDetail(),
            editItem: (id) => window.openEditTransmittal(id),
            issueItem: (id) => window.issueTransmittal(id),
            voidItem: (id) => window.voidTransmittal(id),
            addDoc: (docNumber, fileKind) => window.addTr2Doc(docNumber, fileKind),
            removeDoc: (index) => window.removeTr2Doc(index),
        });
        if (!handled) {
            throw new Error("Transmittal UI bridge did not bind template actions.");
        }

        root.dataset.tr2ActionsBound = "1";
    }

    function bindTransmittalFieldEvents() {
        const root = document.getElementById("view-transmittal");
        if (!root || root.dataset.tr2FieldsBound === "1") return;
        const uiBridge = requireBridge(TS_TRANSMITTAL_UI, "Transmittal UI");
        const handled = uiBridge.bindFieldEvents(root, {
            refreshNumber: () => refreshTransmittalNumber(),
            searchDocs: () => searchEligibleDocs(),
            updateDocField: (index, field, value) => window.updateTr2Doc(index, field, value),
        });
        if (!handled) {
            throw new Error("Transmittal UI bridge did not bind field events.");
        }
        root.dataset.tr2FieldsBound = "1";
    }

    function initTransmittalUiBindings() {
        bindTransmittalTemplateActions();
        bindTransmittalFieldEvents();
        registerTransmittalBulkActions();
    }

    window.initTransmittalView = async function initTransmittalView() {
        initTransmittalUiBindings();
        if (typeof window.showListMode === "function") {
            window.showListMode();
        }
        if (typeof window.loadTransmittals === "function") {
            await window.loadTransmittals();
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initTransmittalUiBindings);
    } else {
        initTransmittalUiBindings();
    }
})();


