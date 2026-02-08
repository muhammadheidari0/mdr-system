(function () {
  const S = { inited: false, bound: false, page: 1, size: 20, total: 0, items: [], loading: false, timer: null, actions: [], atts: [], cat: { issuing: [], categories: [], projects: [], disciplines: [] } };
  const q = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const dIn = (v) => !v ? "" : (String(v).includes("T") ? String(v).split("T")[0] : String(v).slice(0, 10));
  const dIso = (v) => (String(v || "").trim() ? `${String(v).trim()}T00:00:00` : null);
  const dFa = (v) => { if (!v) return "-"; const d = new Date(v); return Number.isNaN(d.getTime()) ? "-" : d.toLocaleDateString("fa-IR"); };
  const dirCode = (v) => ["I", "IN", "INBOUND"].includes(String(v || "").toUpperCase()) ? "I" : "O";
  const dirFa = (v) => dirCode(v) === "I" ? "وارده" : "صادره";
  const statusClass = (s) => { const k = String(s || "").toLowerCase(); return k === "closed" ? "is-closed" : (k === "overdue" ? "is-overdue" : "is-open"); };
  const kindFa = (k) => ({ letter: "فایل نامه", original: "فایل اصلی", attachment: "پیوست" }[String(k || "").toLowerCase()] || "پیوست");
  const info = (m) => window.UI?.success?.(m); const warn = (m) => window.UI?.warning?.(m); const err = (m) => window.UI?.error?.(m);
  const nowYyMm = (v) => { const d = v ? new Date(`${v}T00:00:00`) : new Date(); return Number.isNaN(d.getTime()) ? "0000" : `${String(d.getFullYear()).slice(-2)}${String(d.getMonth() + 1).padStart(2, "0")}`; };
  const curId = () => Number(q("corrIdInput")?.value || 0);

  function fillSelect(id, rows, first, allowEmpty = true) {
    const el = q(id); if (!el) return; const prev = String(el.value || ""); el.innerHTML = "";
    if (allowEmpty) { const o = document.createElement("option"); o.value = ""; o.innerText = first; el.appendChild(o); }
    (rows || []).forEach((r) => { const c = String(r.code || "").trim(); if (!c) return; const o = document.createElement("option"); o.value = c; const n = String(r.name_p || r.name_e || "").trim(); o.innerText = n ? `${c} - ${n}` : c; el.appendChild(o); });
    if (prev) el.value = prev;
  }
  function refPreview() {
    const i = String(q("corrIssuingInput")?.value || "").toUpperCase() || "COM";
    const c = String(q("corrCategoryInput")?.value || "").toUpperCase() || "CO";
    const d = dirCode(q("corrDirectionInput")?.value); const p = nowYyMm(q("corrDateInput")?.value);
    return `${i}-${c}-${d}-${p}010`;
  }
  function corrUpdateReferencePreview() {
    const el = q("corrRefPreview"); if (!el) return;
    const manual = String(q("corrReferenceInput")?.value || "").trim();
    el.innerHTML = manual ? `<span class="manual-label">دستی</span> ${esc(manual)}` : `<span class="auto-label">اتوماتیک</span> ${esc(refPreview())}`;
  }
  function syncProjectFromIssuing() {
    const issuing = String(q("corrIssuingInput")?.value || "").toUpperCase(); const p = q("corrProjectInput");
    if (!issuing || !p || p.value) return;
    const row = (S.cat.issuing || []).find((x) => String(x.code || "").toUpperCase() === issuing);
    const pc = String(row?.project_code || "").toUpperCase(); if (pc) p.value = pc;
  }

  async function loadCatalog() {
    const r = await fetchWithAuth("/api/v1/correspondence/catalog"); const b = await r.json();
    if (!r.ok || !b?.ok) throw new Error(b?.detail || "خطا در بارگذاری کاتالوگ");
    S.cat.issuing = b.issuing_entities || []; S.cat.categories = b.categories || []; S.cat.projects = b.projects || []; S.cat.disciplines = b.disciplines || [];
    fillSelect("corrIssuingFilter", S.cat.issuing, "همه مراجع صدور"); fillSelect("corrCategoryFilter", S.cat.categories, "همه دسته‌ها");
    fillSelect("corrIssuingInput", S.cat.issuing, "انتخاب مرجع صدور", false); fillSelect("corrCategoryInput", S.cat.categories, "انتخاب دسته", false);
    fillSelect("corrProjectInput", S.cat.projects, "اتوماتیک از مرجع / بدون پروژه"); fillSelect("corrDisciplineInput", S.cat.disciplines, "بدون دیسیپلین");
  }
  async function loadDashboard() {
    const r = await fetchWithAuth("/api/v1/correspondence/dashboard"); if (!r.ok) return; const b = await r.json(); if (!b?.ok) return;
    q("corrStatTotal").innerText = String(b.stats?.total || 0); q("corrStatOpen").innerText = String(b.stats?.open || 0); q("corrStatOverdue").innerText = String(b.stats?.overdue || 0); q("corrStatOpenActions").innerText = String(b.stats?.open_actions || 0);
  }
  function filters() {
    return { search: String(q("corrSearchInput")?.value || "").trim(), issuing_code: String(q("corrIssuingFilter")?.value || "").trim(), category_code: String(q("corrCategoryFilter")?.value || "").trim(), direction: String(q("corrDirectionFilter")?.value || "").trim(), status: String(q("corrStatusFilter")?.value || "").trim(), date_from: String(q("corrDateFromFilter")?.value || "").trim(), date_to: String(q("corrDateToFilter")?.value || "").trim() };
  }
  function renderPager() {
    const start = S.total === 0 ? 0 : ((S.page - 1) * S.size) + 1, end = Math.min(S.total, S.page * S.size);
    q("corrPagerInfo").innerText = `${start}-${end} از ${S.total}`;
    q("corrPrevBtn").disabled = S.page <= 1 || S.loading; q("corrNextBtn").disabled = end >= S.total || S.loading;
  }
  function renderRows() {
    const tb = q("corrTableBody"), empty = q("corrEmpty"); if (!tb || !empty) return;
    if (!S.items.length) { tb.innerHTML = ""; empty.style.display = "block"; renderPager(); return; }
    empty.style.display = "none"; const off = (S.page - 1) * S.size;
    tb.innerHTML = S.items.map((x, i) => `
      <tr>
        <td>${off + i + 1}</td><td style="font-family:monospace;">${esc(x.reference_no || "-")}</td><td>${esc(x.subject || "-")}</td>
        <td>${esc(x.issuing_name || x.issuing_code || "-")}</td><td>${esc(x.category_name || x.category_code || "-")}</td><td>${esc(dirFa(x.direction))}</td>
        <td>${dFa(x.corr_date)}</td><td><span class="corr-status-badge ${statusClass(x.status)}">${esc(x.status || "-")}</span></td><td>${Number(x.open_actions_count || 0)}</td><td>${Number(x.attachments_count || 0)}</td>
        <td><div class="corr-row-actions">
          <button class="btn-archive-icon" type="button" data-corr-action="open-edit" data-corr-id="${Number(x.id || 0)}"><span class="material-icons-round">edit</span></button>
          <button class="btn-archive-icon" type="button" data-corr-action="open-workflow" data-corr-id="${Number(x.id || 0)}"><span class="material-icons-round">assignment</span></button>
          <button class="btn-archive-icon" type="button" data-corr-action="copy-ref" data-corr-ref="${esc(x.reference_no || "")}"><span class="material-icons-round">content_copy</span></button>
        </div></td>
      </tr>`).join("");
    renderPager();
  }
  async function loadList() {
    S.loading = true; renderPager(); q("corrLoader").style.display = "block"; q("corrTableBody").innerHTML = "";
    try {
      const f = filters(), p = new URLSearchParams(); p.set("skip", String(Math.max(0, (S.page - 1) * S.size))); p.set("limit", String(S.size));
      Object.entries(f).forEach(([k, v]) => v && p.set(k, v));
      const r = await fetchWithAuth(`/api/v1/correspondence/list?${p.toString()}`), b = await r.json();
      if (!r.ok || !b?.ok) { err(b?.detail || "خطا در لیست مکاتبات"); S.items = []; S.total = 0; renderRows(); return; }
      S.items = Array.isArray(b.data) ? b.data : []; S.total = Number(b.total || 0); renderRows();
    } catch (e) { console.error(e); S.items = []; S.total = 0; renderRows(); }
    finally { S.loading = false; q("corrLoader").style.display = "none"; renderPager(); }
  }
  function corrApplyFilters(reset = true) { if (reset) S.page = 1; loadList(); }
  function corrDebouncedSearch() { clearTimeout(S.timer); S.timer = setTimeout(() => corrApplyFilters(true), 350); }
  function corrResetFilters() { ["corrSearchInput", "corrIssuingFilter", "corrCategoryFilter", "corrDirectionFilter", "corrStatusFilter", "corrDateFromFilter", "corrDateToFilter"].forEach((id) => { const e = q(id); if (e) e.value = ""; }); S.page = 1; loadList(); }
  function corrPrevPage() { if (S.page <= 1 || S.loading) return; S.page -= 1; loadList(); }
  function corrNextPage() { if (S.loading) return; if (S.page * S.size >= S.total) return; S.page += 1; loadList(); }
  function corrChangePageSize(v) { S.size = Math.max(1, Number(v || 20)); S.page = 1; loadList(); }
  async function corrRefresh() { await loadDashboard(); await loadList(); }
  function corrCopyRef(v) { if (!v) return; if (window.copyToClipboard) return window.copyToClipboard(v); navigator.clipboard?.writeText(v); }

  function clearActionEditor() {
    q("corrActionIdInput").value = ""; q("corrActionTypeInput").value = "task"; q("corrActionTitleInput").value = ""; q("corrActionDueInput").value = ""; q("corrActionStatusInput").value = "Open"; q("corrActionDescInput").value = "";
    q("corrActionSubmitBtn").innerHTML = `<span class="material-icons-round">playlist_add_check</span> افزودن اقدام`;
  }
  function fillActionOptions() {
    const s = q("corrAttachmentActionInput"); if (!s) return; const prev = String(s.value || ""); s.innerHTML = `<option value="">بدون اقدام</option>`;
    S.actions.forEach((a) => { const o = document.createElement("option"); o.value = String(a.id); o.innerText = String(a.title || a.description || `#${a.id}`); s.appendChild(o); });
    if (prev) s.value = prev;
  }
  function renderActions() {
    const b = q("corrActionsBody"); if (!b) return;
    if (!S.actions.length) { b.innerHTML = `<tr><td colspan="5" class="corr-empty-row">اقدامی ثبت نشده است.</td></tr>`; fillActionOptions(); return; }
    b.innerHTML = S.actions.map((a) => `<tr><td>${esc(a.title || a.description || "-")}</td><td>${esc(a.action_type || "-")}</td><td>${dFa(a.due_date)}</td><td><div class="corr-action-status-cell"><span class="corr-status-badge ${statusClass(a.status)}">${esc(a.status || "-")}</span><label class="corr-action-check"><input type="checkbox" ${a.is_closed ? "checked" : ""} data-corr-action="toggle-action-closed" data-action-id="${Number(a.id)}"><span>بسته</span></label></div></td><td><div class="corr-row-actions"><button class="btn-archive-icon" type="button" data-corr-action="edit-action" data-action-id="${Number(a.id)}"><span class="material-icons-round">edit</span></button><button class="btn-archive-icon" type="button" data-corr-action="delete-action" data-action-id="${Number(a.id)}"><span class="material-icons-round">delete</span></button></div></td></tr>`).join("");
    fillActionOptions();
  }
  async function loadActions(id) {
    if (!id) { S.actions = []; renderActions(); return; }
    const r = await fetchWithAuth(`/api/v1/correspondence/${id}/actions`), b = await r.json();
    if (!r.ok || !b?.ok) { err(b?.detail || "خطا در دریافت اقدامات"); S.actions = []; renderActions(); return; }
    S.actions = Array.isArray(b.data) ? b.data : []; renderActions();
  }
  async function corrSubmitAction() {
    const id = curId(); if (!id) return warn("ابتدا مکاتبه را ذخیره کنید.");
    const aid = Number(q("corrActionIdInput").value || 0), payload = { action_type: String(q("corrActionTypeInput").value || "").trim() || "task", title: String(q("corrActionTitleInput").value || "").trim() || null, description: String(q("corrActionDescInput").value || "").trim() || null, due_date: dIso(q("corrActionDueInput").value), status: String(q("corrActionStatusInput").value || "").trim() || "Open", is_closed: String(q("corrActionStatusInput").value || "").toLowerCase() === "closed" };
    if (!payload.title && !payload.description) return warn("عنوان یا شرح اقدام را وارد کنید.");
    const r = await fetchWithAuth(aid > 0 ? `/api/v1/correspondence/actions/${aid}` : `/api/v1/correspondence/${id}/actions`, { method: aid > 0 ? "PUT" : "POST", body: JSON.stringify(payload) });
    const b = await r.json(); if (!r.ok || !b?.ok) return err(b?.detail || "خطا در ذخیره اقدام");
    info(aid > 0 ? "اقدام ویرایش شد." : "اقدام ثبت شد."); clearActionEditor(); await loadActions(id); await loadDashboard(); await loadList();
  }
  function corrEditAction(id) { const a = S.actions.find((x) => Number(x.id) === Number(id)); if (!a) return; q("corrActionIdInput").value = String(a.id); q("corrActionTypeInput").value = String(a.action_type || "task"); q("corrActionTitleInput").value = String(a.title || ""); q("corrActionDueInput").value = dIn(a.due_date); q("corrActionStatusInput").value = String(a.status || "Open"); q("corrActionDescInput").value = String(a.description || ""); q("corrActionSubmitBtn").innerHTML = `<span class="material-icons-round">save</span> ذخیره تغییر اقدام`; }
  async function corrToggleActionClosed(id, checked) { const r = await fetchWithAuth(`/api/v1/correspondence/actions/${Number(id)}`, { method: "PUT", body: JSON.stringify({ is_closed: !!checked, status: checked ? "Closed" : "Open" }) }); const b = await r.json(); if (!r.ok || !b?.ok) return err(b?.detail || "خطا در تغییر وضعیت اقدام"); await loadActions(curId()); await loadDashboard(); await loadList(); }
  async function corrDeleteAction(id) { if (!confirm("اقدام حذف شود؟")) return; const r = await fetchWithAuth(`/api/v1/correspondence/actions/${Number(id)}`, { method: "DELETE" }); const b = await r.json(); if (!r.ok || !b?.ok) return err(b?.detail || "خطا در حذف اقدام"); info("اقدام حذف شد."); clearActionEditor(); await loadActions(curId()); await loadDashboard(); await loadList(); }

  function renderAtts() {
    const b = q("corrAttachmentsBody"); if (!b) return;
    if (!S.atts.length) { b.innerHTML = `<tr><td colspan="5" class="corr-empty-row">فایلی ثبت نشده است.</td></tr>`; return; }
    b.innerHTML = S.atts.map((a) => `<tr><td>${esc(a.file_name || "-")}</td><td>${esc(kindFa(a.file_kind))}</td><td>${esc(S.actions.find((x) => Number(x.id) === Number(a.action_id))?.title || "-")}</td><td>${dFa(a.uploaded_at)}</td><td><div class="corr-row-actions"><button class="btn-archive-icon" type="button" data-corr-action="download-attachment" data-attachment-id="${Number(a.id)}"><span class="material-icons-round">download</span></button><button class="btn-archive-icon" type="button" data-corr-action="delete-attachment" data-attachment-id="${Number(a.id)}"><span class="material-icons-round">delete</span></button></div></td></tr>`).join("");
  }
  async function loadAtts(id) { if (!id) { S.atts = []; renderAtts(); return; } const r = await fetchWithAuth(`/api/v1/correspondence/${id}/attachments`), b = await r.json(); if (!r.ok || !b?.ok) return err(b?.detail || "خطا در دریافت فایل‌ها"), S.atts = [], renderAtts(); S.atts = Array.isArray(b.data) ? b.data : []; renderAtts(); }
  async function corrUploadAttachment() {
    const id = curId(); if (!id) return warn("ابتدا مکاتبه را ذخیره کنید.");
    const f = q("corrAttachmentFileInput")?.files?.[0]; if (!f) return warn("فایل را انتخاب کنید.");
    const fd = new FormData(); fd.append("file", f); fd.append("file_kind", String(q("corrAttachmentKindInput")?.value || "attachment")); const aid = String(q("corrAttachmentActionInput")?.value || ""); if (aid) fd.append("action_id", aid);
    const r = await fetchWithAuth(`/api/v1/correspondence/${id}/attachments/upload`, { method: "POST", body: fd }); const b = await r.json(); if (!r.ok || !b?.ok) return err(b?.detail || "خطا در آپلود فایل");
    q("corrAttachmentFileInput").value = ""; info("فایل آپلود شد."); await loadAtts(id); await loadDashboard(); await loadList();
  }
  function parseFileName(h) { const cd = h.get("Content-Disposition") || h.get("content-disposition") || ""; const m = cd.match(/filename\\*=UTF-8''([^;]+)|filename=\\\"?([^\\\";]+)\\\"?/i); return m ? decodeURIComponent(m[1] || m[2] || "") : null; }
  async function corrDownloadAttachment(id) { const r = await fetchWithAuth(`/api/v1/correspondence/attachments/${Number(id)}/download`); if (!r.ok) { const b = await r.json(); return err(b?.detail || "خطا در دانلود"); } const blob = await r.blob(), fn = parseFileName(r.headers) || `attachment-${id}`, url = URL.createObjectURL(blob), a = document.createElement("a"); a.href = url; a.download = fn; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url); }
  async function corrDeleteAttachment(id) { if (!confirm("فایل حذف شود؟")) return; const r = await fetchWithAuth(`/api/v1/correspondence/attachments/${Number(id)}`, { method: "DELETE" }); const b = await r.json(); if (!r.ok || !b?.ok) return err(b?.detail || "خطا در حذف فایل"); info("فایل حذف شد."); await loadAtts(curId()); await loadDashboard(); await loadList(); }

  function formDefaults() {
    const t = new Date(), ds = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
    ["corrIdInput", "corrReferenceInput", "corrSubjectInput", "corrSenderInput", "corrRecipientInput", "corrDueDateInput", "corrNotesInput"].forEach((id) => q(id).value = "");
    q("corrDateInput").value = ds; q("corrStatusInput").value = "Open"; q("corrPriorityInput").value = "Normal"; q("corrDirectionInput").value = "O"; q("corrProjectInput").value = ""; q("corrDisciplineInput").value = ""; if (q("corrIssuingInput").options.length) q("corrIssuingInput").selectedIndex = 0; if (q("corrCategoryInput").options.length) q("corrCategoryInput").selectedIndex = 0;
    S.actions = []; S.atts = []; clearActionEditor(); q("corrActionsBody").innerHTML = `<tr><td colspan="5" class="corr-empty-row">ابتدا مکاتبه را ذخیره کنید.</td></tr>`; q("corrAttachmentsBody").innerHTML = `<tr><td colspan="5" class="corr-empty-row">ابتدا مکاتبه را ذخیره کنید.</td></tr>`; fillActionOptions(); corrUpdateReferencePreview();
  }
  function payloadForm() { const c = String(q("corrCategoryInput").value || "").trim().toUpperCase(); return { project_code: String(q("corrProjectInput").value || "").trim().toUpperCase() || null, issuing_code: String(q("corrIssuingInput").value || "").trim().toUpperCase() || null, category_code: c || null, discipline_code: String(q("corrDisciplineInput").value || "").trim().toUpperCase() || null, doc_type: c || null, direction: dirCode(q("corrDirectionInput").value), reference_no: String(q("corrReferenceInput").value || "").trim() || null, subject: String(q("corrSubjectInput").value || "").trim(), sender: String(q("corrSenderInput").value || "").trim() || null, recipient: String(q("corrRecipientInput").value || "").trim() || null, corr_date: dIso(q("corrDateInput").value), due_date: dIso(q("corrDueDateInput").value), status: String(q("corrStatusInput").value || "").trim() || "Open", priority: String(q("corrPriorityInput").value || "").trim() || "Normal", notes: String(q("corrNotesInput").value || "").trim() || null }; }
  async function corrSave(e) {
    e.preventDefault(); const id = curId(), p = payloadForm(), btn = q("corrSaveBtn");
    if (!p.issuing_code || !p.category_code || !p.subject) return warn("مرجع صدور، دسته و موضوع الزامی است.");
    if (!p.corr_date) return warn("تاریخ مکاتبه الزامی است.");
    btn.disabled = true;
    try {
      const r = await fetchWithAuth(id > 0 ? `/api/v1/correspondence/${id}` : "/api/v1/correspondence/create", { method: id > 0 ? "PUT" : "POST", body: JSON.stringify(p) });
      const b = await r.json(); if (!r.ok || !b?.ok) return err(b?.detail || "خطا در ذخیره مکاتبه");
      const sid = Number(b.data?.id || 0); if (sid) { q("corrIdInput").value = String(sid); q("corrModalTitle").innerText = "ویرایش مکاتبه"; await loadActions(sid); await loadAtts(sid); }
      info(id > 0 ? "مکاتبه ویرایش شد." : "مکاتبه ثبت شد. حالا اقدام و فایل ثبت کنید."); await loadDashboard(); await loadList();
    } finally { btn.disabled = false; }
  }
  function corrOpenCreate() { q("corrModalTitle").innerText = "مکاتبه جدید"; formDefaults(); syncProjectFromIssuing(); q("corrModal").style.display = "flex"; }
  async function corrOpenEdit(id) {
    const x = S.items.find((r) => Number(r.id) === Number(id)); if (!x) return;
    q("corrModalTitle").innerText = "ویرایش مکاتبه"; q("corrIdInput").value = String(x.id || ""); q("corrIssuingInput").value = String(x.issuing_code || ""); q("corrCategoryInput").value = String(x.category_code || ""); q("corrDirectionInput").value = dirCode(x.direction); q("corrProjectInput").value = String(x.project_code || ""); q("corrDisciplineInput").value = String(x.discipline_code || ""); q("corrReferenceInput").value = String(x.reference_no || ""); q("corrSubjectInput").value = String(x.subject || ""); q("corrSenderInput").value = String(x.sender || ""); q("corrRecipientInput").value = String(x.recipient || ""); q("corrDateInput").value = dIn(x.corr_date); q("corrDueDateInput").value = dIn(x.due_date); q("corrStatusInput").value = String(x.status || "Open"); q("corrPriorityInput").value = String(x.priority || "Normal"); q("corrNotesInput").value = String(x.notes || ""); clearActionEditor(); corrUpdateReferencePreview(); q("corrModal").style.display = "flex"; await loadActions(Number(x.id)); await loadAtts(Number(x.id));
  }
  async function corrOpenWorkflow(id) { await corrOpenEdit(id); q("corrActionsSection")?.scrollIntoView({ behavior: "smooth", block: "start" }); }
  function corrCloseModal() { q("corrModal").style.display = "none"; }

  function bindEvents() {
    if (S.bound) return;
    const root = q("view-correspondence");
    if (!root) return;
    S.bound = true;

    q("corrSearchInput")?.addEventListener("keyup", corrDebouncedSearch);
    ["corrIssuingFilter", "corrCategoryFilter", "corrDirectionFilter", "corrStatusFilter", "corrDateFromFilter", "corrDateToFilter"].forEach((id) => {
      q(id)?.addEventListener("change", () => corrApplyFilters(true));
    });
    q("corrPageSize")?.addEventListener("change", (event) => corrChangePageSize(event?.target?.value));

    q("corrForm")?.addEventListener("submit", corrSave);
    q("corrReferenceInput")?.addEventListener("input", corrUpdateReferencePreview);
    q("corrIssuingInput")?.addEventListener("change", () => { syncProjectFromIssuing(); corrUpdateReferencePreview(); });
    ["corrCategoryInput", "corrDirectionInput", "corrDateInput"].forEach((id) => {
      q(id)?.addEventListener("change", corrUpdateReferencePreview);
    });

    root.addEventListener("click", (event) => {
      const el = event.target?.closest?.("[data-corr-action]");
      if (!el || !root.contains(el)) return;
      const action = String(el.getAttribute("data-corr-action") || "").trim();
      switch (action) {
        case "open-create":
          corrOpenCreate();
          break;
        case "reset-filters":
          corrResetFilters();
          break;
        case "refresh":
          corrRefresh();
          break;
        case "prev-page":
          corrPrevPage();
          break;
        case "next-page":
          corrNextPage();
          break;
        case "close-modal":
          corrCloseModal();
          break;
        case "submit-action":
          corrSubmitAction();
          break;
        case "clear-action-editor":
          clearActionEditor();
          break;
        case "upload-attachment":
          corrUploadAttachment();
          break;
        case "open-edit":
          corrOpenEdit(Number(el.getAttribute("data-corr-id") || 0));
          break;
        case "open-workflow":
          corrOpenWorkflow(Number(el.getAttribute("data-corr-id") || 0));
          break;
        case "copy-ref":
          corrCopyRef(el.getAttribute("data-corr-ref") || "");
          break;
        case "edit-action":
          corrEditAction(Number(el.getAttribute("data-action-id") || 0));
          break;
        case "delete-action":
          corrDeleteAction(Number(el.getAttribute("data-action-id") || 0));
          break;
        case "download-attachment":
          corrDownloadAttachment(Number(el.getAttribute("data-attachment-id") || 0));
          break;
        case "delete-attachment":
          corrDeleteAttachment(Number(el.getAttribute("data-attachment-id") || 0));
          break;
        default:
          break;
      }
    });

    root.addEventListener("change", (event) => {
      const target = event.target;
      if (!target) return;
      if (target.matches("input[data-corr-action='toggle-action-closed']")) {
        corrToggleActionClosed(Number(target.getAttribute("data-action-id") || 0), !!target.checked);
      }
    });

    q("corrModal")?.addEventListener("click", (event) => {
      if (event.target?.id === "corrModal") corrCloseModal();
    });
  }

  async function init() {
    bindEvents();
    await loadCatalog();
    if (!S.inited) { S.inited = true; formDefaults(); }
    await loadDashboard();
    await loadList();
  }
  window.initCorrespondenceView = init; window.corrOpenCreate = corrOpenCreate; window.corrOpenEdit = corrOpenEdit; window.corrOpenWorkflow = corrOpenWorkflow; window.corrCloseModal = corrCloseModal; window.corrSave = corrSave;
  window.corrDebouncedSearch = corrDebouncedSearch; window.corrApplyFilters = corrApplyFilters; window.corrResetFilters = corrResetFilters; window.corrPrevPage = corrPrevPage; window.corrNextPage = corrNextPage; window.corrChangePageSize = corrChangePageSize; window.corrRefresh = corrRefresh; window.corrUpdateReferencePreview = corrUpdateReferencePreview; window.corrSubmitAction = corrSubmitAction; window.corrClearActionEditor = clearActionEditor; window.corrUploadAttachment = corrUploadAttachment; window.corrCopyRef = corrCopyRef; window.corrEditAction = corrEditAction; window.corrDeleteAction = corrDeleteAction; window.corrToggleActionClosed = corrToggleActionClosed; window.corrDownloadAttachment = corrDownloadAttachment; window.corrDeleteAttachment = corrDeleteAttachment;
  if (q("view-correspondence")?.style.display !== "none") init();
})();

