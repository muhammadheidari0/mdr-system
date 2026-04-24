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
    };

    const TR2_BULK_ACTION_ISSUE = 'tr2-bulk-issue';
    const TR2_BULK_ACTION_VOID = 'tr2-bulk-void';

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
        return items.length > 3 ? `${head} | +${items.length - 3} more` : head;
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

    async function runTransmittalBulkAction(actionId, selectedKeys) {
        const ids = parseBulkTransmittalIds(selectedKeys);
        if (!ids.length) {
            notify("warning", "No transmittal selected.");
            return;
        }

        const selectedRows = selectedTransmittalRows(ids);
        if (!selectedRows.length) {
            notify("warning", "Selected transmittals are no longer available.");
            return;
        }

        let targetRows = selectedRows;
        let operation = "";
        let confirmMessage = "";
        let task = null;

        if (actionId === TR2_BULK_ACTION_ISSUE) {
            operation = "issued";
            targetRows = selectedRows.filter((item) => isDraftTransmittal(item));
            confirmMessage = `Issue ${targetRows.length} selected draft transmittal(s)?`;
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
                notify("error", "Void reason is required.");
                return;
            }
            confirmMessage = `Void ${targetRows.length} selected transmittal(s)?`;
            task = async (row) => {
                const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
                await mutationBridge.voidItem(String(row.id), reason, { fetch: getTransmittalFetchFn() });
            };
        }

        if (!task) {
            notify("warning", "Unknown bulk action.");
            return;
        }
        if (!targetRows.length) {
            notify("warning", "No eligible transmittal for this operation.");
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
                failures.push(`${label}: ${error?.message || "Request failed"}`);
            }
        }

        if (success > 0) {
            notify("success", `${success} transmittal(s) ${operation}.`);
        }
        if (failures.length > 0) {
            notify("warning", `${failures.length} operation(s) failed. ${summarizeBulkErrors(failures)}`);
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
                { id: TR2_BULK_ACTION_ISSUE, label: "Issue selected drafts" },
                { id: TR2_BULK_ACTION_VOID, label: "Void selected transmittals" },
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
            throw new Error(`${name} bridge unavailable.`);
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

    function selectedMap() {
        return new Map(state.selectedDocs.map((d) => [d.document_code, d]));
    }

    function currentProjectCode() {
        return String(document.getElementById("tr2-project")?.value || "").trim().toUpperCase();
    }

    function currentDisciplineCode() {
        return String(document.getElementById("tr2-discipline")?.value || "").trim().toUpperCase();
    }

    function currentHeaderStatus() {
        return String(document.getElementById("tr2-edit-status")?.textContent || "draft").trim().toLowerCase();
    }

    function setEditBanner(id = null, status = "draft") {
        const el = document.getElementById("tr2-edit-status");
        const idEl = document.getElementById("tr2-edit-id");
        if (!el || !idEl) return;
        if (id) {
            idEl.textContent = id;
            el.textContent = status;
        } else {
            idEl.textContent = "NEW";
            el.textContent = "draft";
        }
    }

    function resetCreateForm() {
        state.editingId = null;
        state.selectedDocs = [];
        state.searchDocs = [];
        const projectEl = document.getElementById("tr2-project");
        const disciplineEl = document.getElementById("tr2-discipline");
        const senderEl = document.getElementById("tr2-sender");
        const receiverEl = document.getElementById("tr2-receiver");
        const subjectEl = document.getElementById("tr2-subject");
        const searchEl = document.getElementById("tr2-doc-search");
        const nextNoEl = document.getElementById("tr2-next-number");
        if (projectEl) projectEl.disabled = false;
        if (disciplineEl) disciplineEl.value = "";
        if (senderEl) senderEl.value = "O";
        if (receiverEl) receiverEl.value = "C";
        if (subjectEl) subjectEl.value = "";
        if (searchEl) searchEl.value = "";
        if (nextNoEl) nextNoEl.value = "";
        setEditBanner(null, "draft");
        renderSelectedDocs();
        renderSearchResults([]);
    }

    function renderSelectedDocs() {
        const tbody = document.getElementById("tr2-docs-body");
        if (!tbody) return;
        if (!state.selectedDocs.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="center-text muted">Ù‡Ù†ÙˆØ² Ø¢ÛŒØªÙ…ÛŒ Ø§Ø¶Ø§ÙÙ‡ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª</td></tr>';
            return;
        }
        tbody.innerHTML = state.selectedDocs.map((d, idx) => `
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
                <td class="center-text"><input type="checkbox" ${d.electronic_copy ? "checked" : ""} data-tr2-action="doc-field-change" data-index="${idx}" data-field="electronic_copy"></td>
                <td class="center-text"><input type="checkbox" ${d.hard_copy ? "checked" : ""} data-tr2-action="doc-field-change" data-index="${idx}" data-field="hard_copy"></td>
                <td><button class="btn-archive-icon" type="button" data-tr2-action="doc-remove" data-index="${idx}">Ø­Ø°Ù</button></td>
            </tr>
        `).join("");
    }

    function renderStatusCell(item) {
        const status = String(item?.status || "draft").trim().toLowerCase();
        const statusLabel = status.toUpperCase();
        if (status !== "void") {
            return escapeHtml(statusLabel);
        }

        const tooltipParts = [];
        if (item?.void_reason) tooltipParts.push(`Reason: ${item.void_reason}`);
        if (item?.voided_by) tooltipParts.push(`By: ${item.voided_by}`);
        if (item?.voided_at) tooltipParts.push(`At: ${formatShamsiDateTime(item.voided_at)}`);
        const tooltip = tooltipParts.join(" | ") || "VOID";
        return `<span title="${escapeHtml(tooltip)}" style="cursor: help;">${escapeHtml(statusLabel)}</span>`;
    }

    function renderSearchResults(items) {
        const tbody = document.getElementById("tr2-search-body");
        if (!tbody) return;
        state.searchDocs = Array.isArray(items) ? items : [];
        if (!items.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="center-text muted">Ù…Ø¯Ø±Ú©ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯</td></tr>';
            return;
        }

        const chosen = selectedMap();
        tbody.innerHTML = items.map((item) => {
            const docNumber = String(item.doc_number || "").trim();
            const disabled = chosen.has(docNumber);
            return `
                <tr>
                    <td>${escapeHtml(docNumber)}</td>
                    <td>${escapeHtml(item.doc_title || "-")}</td>
                    <td>${escapeHtml(item.revision || "00")}</td>
                    <td>${escapeHtml(item.status || "-")}</td>
                    <td>
                        <button class="btn-archive-icon" type="button" ${disabled ? "disabled" : ""} data-tr2-action="doc-add" data-doc-number="${escapeHtml(docNumber)}">
                            ${disabled ? "Ø§ÙØ²ÙˆØ¯Ù‡ Ø´Ø¯Ù‡" : "Ø§ÙØ²ÙˆØ¯Ù†"}
                        </button>
                    </td>
                </tr>
            `;
        }).join("");
    }

    async function loadCreateFormData() {
        state.formData = await request("/api/v1/archive/form-data");
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
        if (disciplineEl) {
            disciplineEl.innerHTML = `<option value="">Ù‡Ù…Ù‡ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†â€ŒÙ‡Ø§</option>` + disciplines.map((d) => {
                const code = (d.code || "").toUpperCase();
                const label = `${code} - ${d.name || code}`;
                return `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`;
            }).join("");
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
            tbody.innerHTML = '<tr><td colspan="6" class="center-text muted" style="padding: 26px;">Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ...</td></tr>';
        }
        try {
            const dataBridge = requireBridge(TS_TRANSMITTAL_DATA, "Transmittal data");
            const [items] = await Promise.all([
                dataBridge.loadList({ fetch: getTransmittalFetchFn() }),
                loadTransmittalStats(),
            ]);
            state.listItems = Array.isArray(items) ? items : [];
            if (!tbody) return;
            if (!Array.isArray(items) || !items.length) {
                state.listItems = [];
                tbody.innerHTML = '<tr><td colspan="6" class="center-text muted">ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯</td></tr>';
                return;
            }
            tbody.innerHTML = items.map((t) => `
                <tr data-bulk-key="${escapeHtml(String(t.id || '').trim())}" data-transmittal-id="${escapeHtml(String(t.id || '').trim())}" data-transmittal-status="${escapeHtml(String(t.status || '').trim().toLowerCase())}">
                    <td style="font-family: monospace; font-weight: 700;">${escapeHtml(t.transmittal_no || t.id)}</td>
                    <td>${escapeHtml(t.subject || "-")}</td>
                    <td>${escapeHtml(t.doc_count)}</td>
                    <td>${renderStatusCell(t)}</td>
                    <td>${formatShamsiDate(t.created_at)}</td>
                    <td>
                        <button class="btn-archive-icon" type="button" data-tr2-action="download-cover" data-id="${escapeHtml(t.id)}">PDF</button>
                        ${t.status === "draft" ? `<button class="btn-archive-icon" type="button" data-tr2-action="edit-item" data-id="${escapeHtml(t.id)}">Edit</button>` : ""}
                        ${t.status === "draft" ? `<button class="btn-archive-icon" type="button" data-tr2-action="issue-item" data-id="${escapeHtml(t.id)}">Issue</button>` : ""}
                        ${t.status === "draft" || t.status === "issued" ? `<button class="btn-archive-icon" type="button" data-tr2-action="void-item" data-id="${escapeHtml(t.id)}">Void</button>` : ""}
                    </td>
                </tr>
            `).join("");
        } catch (error) {
            state.listItems = [];
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="6" class="center-text text-danger">Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ</td></tr>';
            }
            notify("error", error.message || "Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        }
    };

    window.showCreateMode = async function showCreateMode() {
        setTransmittalMode("create");
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
            const disciplineEl = document.getElementById("tr2-discipline");
            if (projectEl && projectCode) projectEl.value = projectCode;
            if (disciplineEl && disciplineCode) disciplineEl.value = disciplineCode;

            await refreshTransmittalNumber();
            await searchEligibleDocs();

            if (docNumber) {
                window.addTr2Doc({
                    doc_number: docNumber,
                    revision,
                    status,
                    doc_title: pendingDoc.doc_title || pendingDoc.doc_title_p || pendingDoc.doc_title_e || docNumber,
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

            setTransmittalMode("create");

            state.editingId = detail.id;
            setEditBanner(detail.id, detail.status || "draft");

            const projectEl = document.getElementById("tr2-project");
            const disciplineEl = document.getElementById("tr2-discipline");
            const senderEl = document.getElementById("tr2-sender");
            const receiverEl = document.getElementById("tr2-receiver");
            const subjectEl = document.getElementById("tr2-subject");
            if (projectEl) {
                projectEl.value = (detail.project_code || "").toUpperCase();
                projectEl.disabled = true;
            }
            if (disciplineEl) disciplineEl.value = "";
            if (senderEl) senderEl.value = detail.sender || "O";
            if (receiverEl) receiverEl.value = detail.receiver || "C";
            if (subjectEl) subjectEl.value = "";

            state.selectedDocs = Array.isArray(detail.documents) ? detail.documents.map((d) => ({
                document_code: d.document_code,
                revision: d.revision || "00",
                status: d.status || "IFA",
                electronic_copy: Boolean(d.electronic_copy),
                hard_copy: Boolean(d.hard_copy),
            })) : [];
            renderSelectedDocs();
            await refreshTransmittalNumber();
            await searchEligibleDocs();
        } catch (error) {
            notify("error", error.message || "Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Draft Ø¨Ø±Ø§ÛŒ ÙˆÛŒØ±Ø§ÛŒØ´ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        }
    };

    async function refreshTransmittalNumber() {
        const project = currentProjectCode();
        const sender = String(document.getElementById("tr2-sender")?.value || "O").trim().toUpperCase() || "O";
        const receiver = String(document.getElementById("tr2-receiver")?.value || "C").trim().toUpperCase() || "C";
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

    window.addTr2Doc = function addTr2Doc(item) {
        const resolved = typeof item === "string" ? findSearchDocByNumber(item) : item;
        if (!resolved || !resolved.doc_number) return;
        if (state.selectedDocs.some((d) => d.document_code === resolved.doc_number)) return;
        state.selectedDocs.push({
            document_code: resolved.doc_number,
            revision: resolved.revision || "00",
            status: resolved.status && resolved.status !== "Registered" ? resolved.status : "IFA",
            electronic_copy: true,
            hard_copy: false,
        });
        renderSelectedDocs();
        renderSearchResults(state.searchDocs);
    };

    window.updateTr2Doc = function updateTr2Doc(index, field, value) {
        if (!state.selectedDocs[index]) return;
        state.selectedDocs[index][field] = value;
    };

    window.removeTr2Doc = function removeTr2Doc(index) {
        if (!Number.isInteger(index) || index < 0 || index >= state.selectedDocs.length) return;
        state.selectedDocs.splice(index, 1);
        renderSelectedDocs();
        renderSearchResults(state.searchDocs);
    };

    async function submitTransmittal(issueNow = false) {
        const project = currentProjectCode();
        const sender = String(document.getElementById("tr2-sender")?.value || "O").trim().toUpperCase() || "O";
        const receiver = String(document.getElementById("tr2-receiver")?.value || "C").trim().toUpperCase() || "C";
        const subject = String(document.getElementById("tr2-subject")?.value || "").trim();
        const btn = document.getElementById("tr2-submit-btn");

        if (!project) {
            notify("error", "Ù¾Ø±ÙˆÚ˜Ù‡ Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª");
            return;
        }
        if (!state.selectedDocs.length) {
            notify("error", "Ø­Ø¯Ø§Ù‚Ù„ ÛŒÚ© Ù…Ø¯Ø±Ú© Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯");
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
                subject,
                notes: "",
                issue_now: issueNow,
                documents: state.selectedDocs.map((d) => ({
                    document_code: d.document_code,
                    revision: d.revision || "00",
                    status: d.status || "IFA",
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
        } catch (error) {
            notify("error", error.message || "Ø§Ø¨Ø·Ø§Ù„ ØªØ±Ù†Ø³Ù…ÛŒØªØ§Ù„ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
        }
    };

    window.downloadTransmittalCover = async function downloadTransmittalCover(id) {
        try {
            const mutationBridge = requireBridge(TS_TRANSMITTAL_MUTATIONS, "Transmittal mutations");
            const blob = await mutationBridge.downloadCover(String(id), { fetch: getTransmittalFetchFn() });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `Transmittal_${id}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            notify("success", "ÙØ§ÛŒÙ„ PDF Ø¯Ø§Ù†Ù„ÙˆØ¯ Ø´Ø¯");
        } catch (error) {
            notify("error", error.message || "Ø¯Ø§Ù†Ù„ÙˆØ¯ PDF Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯");
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
            editItem: (id) => window.openEditTransmittal(id),
            issueItem: (id) => window.issueTransmittal(id),
            voidItem: (id) => window.voidTransmittal(id),
            addDoc: (docNumber) => window.addTr2Doc(docNumber),
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


