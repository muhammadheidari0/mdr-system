(() => {
    const state = {
        formData: null,
        selectedDocs: [],
        createReady: false,
        editingId: null,
    };

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

    async function request(url, options = {}) {
        const fn = typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch;
        const response = await fn(url, options);
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
            tbody.innerHTML = '<tr><td colspan="6" class="center-text muted">هنوز آیتمی اضافه نشده است</td></tr>';
            return;
        }
        tbody.innerHTML = state.selectedDocs.map((d, idx) => `
            <tr>
                <td>${escapeHtml(d.document_code)}</td>
                <td><input class="form-input" style="max-width:90px" value="${escapeHtml(d.revision)}" onchange="updateTr2Doc(${idx}, 'revision', this.value)"></td>
                <td>
                    <select class="form-input" onchange="updateTr2Doc(${idx}, 'status', this.value)">
                        <option value="IFA" ${d.status === "IFA" ? "selected" : ""}>IFA</option>
                        <option value="IFC" ${d.status === "IFC" ? "selected" : ""}>IFC</option>
                        <option value="IFI" ${d.status === "IFI" ? "selected" : ""}>IFI</option>
                    </select>
                </td>
                <td class="center-text"><input type="checkbox" ${d.electronic_copy ? "checked" : ""} onchange="updateTr2Doc(${idx}, 'electronic_copy', this.checked)"></td>
                <td class="center-text"><input type="checkbox" ${d.hard_copy ? "checked" : ""} onchange="updateTr2Doc(${idx}, 'hard_copy', this.checked)"></td>
                <td><button class="btn-archive-icon" type="button" onclick="removeTr2Doc(${idx})">حذف</button></td>
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
        if (item?.voided_at) tooltipParts.push(`At: ${new Date(item.voided_at).toLocaleString("fa-IR")}`);
        const tooltip = tooltipParts.join(" | ") || "VOID";
        return `<span title="${escapeHtml(tooltip)}" style="cursor: help;">${escapeHtml(statusLabel)}</span>`;
    }

    function renderSearchResults(items) {
        const tbody = document.getElementById("tr2-search-body");
        if (!tbody) return;
        if (!items.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="center-text muted">مدرکی یافت نشد</td></tr>';
            return;
        }

        const chosen = selectedMap();
        tbody.innerHTML = items.map((item) => {
            const disabled = chosen.has(item.doc_number);
            return `
                <tr>
                    <td>${escapeHtml(item.doc_number)}</td>
                    <td>${escapeHtml(item.doc_title || "-")}</td>
                    <td>${escapeHtml(item.revision || "00")}</td>
                    <td>${escapeHtml(item.status || "-")}</td>
                    <td>
                        <button class="btn-archive-icon" type="button" ${disabled ? "disabled" : ""} onclick='addTr2Doc(${JSON.stringify(item).replace(/'/g, "&#39;")})'>
                            ${disabled ? "افزوده شده" : "افزودن"}
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
            disciplineEl.innerHTML = `<option value="">همه دیسیپلین‌ها</option>` + disciplines.map((d) => {
                const code = (d.code || "").toUpperCase();
                const label = `${code} - ${d.name || code}`;
                return `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`;
            }).join("");
        }
        state.createReady = true;
    }

    async function loadTransmittalStats() {
        const stats = await request("/api/v1/transmittal/stats/summary");
        const totalEl = document.getElementById("tr2-stat-total");
        const monthEl = document.getElementById("tr2-stat-month");
        const lastEl = document.getElementById("tr2-stat-last");
        if (totalEl) totalEl.textContent = String(stats.total_transmittals ?? 0);
        if (monthEl) monthEl.textContent = String(stats.this_month ?? 0);
        if (lastEl) lastEl.textContent = String(stats.last_created || "-");
    }

    window.loadTransmittals = async function loadTransmittals() {
        const tbody = document.getElementById("tr2-list-body");
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="6" class="center-text muted" style="padding: 26px;">در حال بارگذاری...</td></tr>';
        }
        try {
            const [items] = await Promise.all([
                request("/api/v1/transmittal/"),
                loadTransmittalStats(),
            ]);
            if (!tbody) return;
            if (!Array.isArray(items) || !items.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="center-text muted">ترنسمیتالی یافت نشد</td></tr>';
                return;
            }
            tbody.innerHTML = items.map((t) => `
                <tr>
                    <td style="font-family: monospace; font-weight: 700;">${escapeHtml(t.transmittal_no || t.id)}</td>
                    <td>${escapeHtml(t.subject || "-")}</td>
                    <td>${escapeHtml(t.doc_count)}</td>
                    <td>${renderStatusCell(t)}</td>
                    <td>${t.created_at ? new Date(t.created_at).toLocaleDateString("fa-IR") : "-"}</td>
                    <td>
                        <button class="btn-archive-icon" type="button" onclick="downloadTransmittalCover('${escapeHtml(t.id)}')">PDF</button>
                        ${t.status === "draft" ? `<button class="btn-archive-icon" type="button" onclick="openEditTransmittal('${escapeHtml(t.id)}')">Edit</button>` : ""}
                        ${t.status === "draft" ? `<button class="btn-archive-icon" type="button" onclick="issueTransmittal('${escapeHtml(t.id)}')">Issue</button>` : ""}
                        ${t.status === "draft" || t.status === "issued" ? `<button class="btn-archive-icon" type="button" onclick="voidTransmittal('${escapeHtml(t.id)}')">Void</button>` : ""}
                    </td>
                </tr>
            `).join("");
        } catch (error) {
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="6" class="center-text text-danger">خطا در بارگذاری</td></tr>';
            }
            notify("error", error.message || "بارگذاری ترنسمیتال ناموفق بود");
        }
    };

    window.showCreateMode = async function showCreateMode() {
        document.getElementById("tr2-list-mode").style.display = "none";
        document.getElementById("tr2-create-mode").style.display = "block";
        if (!state.createReady) {
            await loadCreateFormData();
        }
        resetCreateForm();
        await refreshTransmittalNumber();
        await searchEligibleDocs();
    };

    window.showListMode = function showListMode() {
        document.getElementById("tr2-list-mode").style.display = "block";
        document.getElementById("tr2-create-mode").style.display = "none";
    };

    window.openEditTransmittal = async function openEditTransmittal(transmittalId) {
        try {
            if (!state.createReady) {
                await loadCreateFormData();
            }
            const detail = await request(`/api/v1/transmittal/item/${encodeURIComponent(transmittalId)}`);
            if ((detail.status || "").toLowerCase() !== "draft") {
                notify("error", "فقط Draft قابل ویرایش است");
                return;
            }

            document.getElementById("tr2-list-mode").style.display = "none";
            document.getElementById("tr2-create-mode").style.display = "block";

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
            notify("error", error.message || "بارگذاری Draft برای ویرایش ناموفق بود");
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
            const data = await request(`/api/v1/transmittal/next-number?project_code=${encodeURIComponent(project)}&sender=${encodeURIComponent(sender)}&receiver=${encodeURIComponent(receiver)}`);
            if (output) output.value = data.transmittal_no || "";
        } catch (error) {
            if (output) output.value = "";
            notify("error", error.message || "شماره‌دهی خودکار ناموفق بود");
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
            const url = `/api/v1/transmittal/eligible-docs?project_code=${encodeURIComponent(project)}&discipline_code=${encodeURIComponent(discipline)}&q=${encodeURIComponent(q)}&limit=30`;
            const items = await request(url);
            renderSearchResults(Array.isArray(items) ? items : []);
        } catch (error) {
            renderSearchResults([]);
            notify("error", error.message || "جستجوی مدارک ناموفق بود");
        }
    };

    window.addTr2Doc = function addTr2Doc(item) {
        if (!item || !item.doc_number) return;
        if (state.selectedDocs.some((d) => d.document_code === item.doc_number)) return;
        state.selectedDocs.push({
            document_code: item.doc_number,
            revision: item.revision || "00",
            status: item.status && item.status !== "Registered" ? item.status : "IFA",
            electronic_copy: true,
            hard_copy: false,
        });
        renderSelectedDocs();
        renderSearchResults([]);
    };

    window.updateTr2Doc = function updateTr2Doc(index, field, value) {
        if (!state.selectedDocs[index]) return;
        state.selectedDocs[index][field] = value;
    };

    window.removeTr2Doc = function removeTr2Doc(index) {
        state.selectedDocs.splice(index, 1);
        renderSelectedDocs();
    };

    async function submitTransmittal(issueNow = false) {
        const project = currentProjectCode();
        const sender = String(document.getElementById("tr2-sender")?.value || "O").trim().toUpperCase() || "O";
        const receiver = String(document.getElementById("tr2-receiver")?.value || "C").trim().toUpperCase() || "C";
        const subject = String(document.getElementById("tr2-subject")?.value || "").trim();
        const btn = document.getElementById("tr2-submit-btn");

        if (!project) {
            notify("error", "پروژه الزامی است");
            return;
        }
        if (!state.selectedDocs.length) {
            notify("error", "حداقل یک مدرک انتخاب کنید");
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
            if (state.editingId) {
                result = await request(`/api/v1/transmittal/item/${encodeURIComponent(state.editingId)}`, {
                    method: "PUT",
                    body: JSON.stringify(payload),
                });
                if (issueNow && currentHeaderStatus() === "draft") {
                    await request(`/api/v1/transmittal/item/${encodeURIComponent(state.editingId)}/issue`, {
                        method: "POST",
                    });
                }
            } else {
                result = await request("/api/v1/transmittal/create", {
                    method: "POST",
                    body: JSON.stringify(payload),
                });
            }
            notify("success", issueNow ? `ترنسمیتال صادر شد: ${result.transmittal_no || state.editingId}` : "Draft ذخیره شد");
            showListMode();
            await loadTransmittals();
        } catch (error) {
            notify("error", error.message || "ثبت ترنسمیتال ناموفق بود");
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
            await request(`/api/v1/transmittal/item/${encodeURIComponent(id)}/issue`, { method: "POST" });
            notify("success", "ترنسمیتال صادر شد");
            await loadTransmittals();
        } catch (error) {
            notify("error", error.message || "صدور ترنسمیتال ناموفق بود");
        }
    };

    window.voidTransmittal = async function voidTransmittal(id) {
        const reasonInput = prompt("دلیل ابطال ترنسمیتال را وارد کنید:");
        if (reasonInput === null) return;
        const reason = reasonInput.trim();
        if (!reason) {
            notify("error", "ثبت دلیل ابطال الزامی است");
            return;
        }
        try {
            await request(`/api/v1/transmittal/item/${encodeURIComponent(id)}/void`, {
                method: "POST",
                body: JSON.stringify({ reason }),
            });
            notify("success", "ترنسمیتال باطل شد");
            await loadTransmittals();
        } catch (error) {
            notify("error", error.message || "ابطال ترنسمیتال ناموفق بود");
        }
    };

    window.downloadTransmittalCover = async function downloadTransmittalCover(id) {
        try {
            const response = await fetchWithAuth(`/api/v1/transmittal/${encodeURIComponent(id)}/download-cover`);
            if (!response.ok) {
                let message = "دانلود فایل ناموفق بود";
                try {
                    const body = await response.clone().json();
                    message = body.detail || message;
                } catch (_) {}
                throw new Error(message);
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `Transmittal_${id}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            notify("success", "فایل PDF دانلود شد");
        } catch (error) {
            notify("error", error.message || "دانلود PDF ناموفق بود");
        }
    };

    // Called by app.js during navigation.
    document.addEventListener("DOMContentLoaded", () => {
        const projectEl = document.getElementById("tr2-project");
        const disciplineEl = document.getElementById("tr2-discipline");
        const senderEl = document.getElementById("tr2-sender");
        const receiverEl = document.getElementById("tr2-receiver");
        const searchEl = document.getElementById("tr2-doc-search");
        if (projectEl) projectEl.addEventListener("change", async () => { await refreshTransmittalNumber(); await searchEligibleDocs(); });
        if (disciplineEl) disciplineEl.addEventListener("change", searchEligibleDocs);
        if (senderEl) senderEl.addEventListener("change", refreshTransmittalNumber);
        if (receiverEl) receiverEl.addEventListener("change", refreshTransmittalNumber);
        if (searchEl) searchEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                searchEligibleDocs();
            }
        });
    });
})();
