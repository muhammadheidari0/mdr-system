// @ts-nocheck
import { formatShamsiDate } from "../lib/persian_datetime";
import { initShamsiDateInputs } from "../lib/shamsi_date_input";
(function () {
  const APP_RUNTIME = (window.AppRuntime && typeof window.AppRuntime === "object")
    ? window.AppRuntime
    : null;
  const TS_CORRESPONDENCE_DATA = (APP_RUNTIME?.correspondenceData && typeof APP_RUNTIME.correspondenceData === "object")
    ? APP_RUNTIME.correspondenceData
    : null;
  const TS_CORRESPONDENCE_UI = (APP_RUNTIME?.correspondenceUi && typeof APP_RUNTIME.correspondenceUi === "object")
    ? APP_RUNTIME.correspondenceUi
    : null;
  const TS_CORRESPONDENCE_STATE = (APP_RUNTIME?.correspondenceState && typeof APP_RUNTIME.correspondenceState === "object")
    ? APP_RUNTIME.correspondenceState
    : null;
  const TS_CORRESPONDENCE_FORM = (APP_RUNTIME?.correspondenceForm && typeof APP_RUNTIME.correspondenceForm === "object")
    ? APP_RUNTIME.correspondenceForm
    : null;
  const TS_CORRESPONDENCE_WORKFLOW = (APP_RUNTIME?.correspondenceWorkflow && typeof APP_RUNTIME.correspondenceWorkflow === "object")
    ? APP_RUNTIME.correspondenceWorkflow
    : null;
  const S = { inited: false, bound: false, page: 1, size: 20, total: 0, items: [], loading: false, timer: null, suggestionsTimer: null, previewUrl: "", actions: [], atts: [], relations: [], cat: { issuing: [], categories: [], projects: [], tags: [] } };
  const q = (id) => document.getElementById(id);
  let shamsiDates = null;
  const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const dIn = (v) => !v ? "" : (String(v).includes("T") ? String(v).split("T")[0] : String(v).slice(0, 10));
  const dIso = (v) => (String(v || "").trim() ? `${String(v).trim()}T00:00:00` : null);
  const dFa = (v) => formatShamsiDate(v);
  const dirCode = (v) => ["I", "IN", "INBOUND"].includes(String(v || "").toUpperCase()) ? "I" : "O";
  const dirFa = (v) => dirCode(v) === "I" ? "وارده" : "صادره";
  const statusClass = (s) => { const k = String(s || "").toLowerCase(); return k === "closed" ? "is-closed" : (k === "overdue" ? "is-overdue" : "is-open"); };
  const kindFa = (k) => ({ letter: "فایل نامه", original: "فایل اصلی", attachment: "پیوست" }[String(k || "").toLowerCase()] || "پیوست");
  const info = (m) => window.UI?.success?.(m); const warn = (m) => window.UI?.warning?.(m); const err = (m) => window.UI?.error?.(m);
  const nowYyMm = (v) => { const d = v ? new Date(`${v}T00:00:00`) : new Date(); return Number.isNaN(d.getTime()) ? "0000" : `${String(d.getFullYear()).slice(-2)}${String(d.getMonth() + 1).padStart(2, "0")}`; };
  const curId = () => Number(q("corrIdInput")?.value || 0);
  const getCorrFetchFn = () => (typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch);
  const STORAGE_ENTITY_ATTACHMENT = "correspondence_attachment";
  async function corrReadJsonSafe(response) {
    try {
      return await response.json();
    } catch (_) {
      return null;
    }
  }
  async function corrRequestJson(url, init = undefined) {
    const response = await getCorrFetchFn()(url, init);
    const payload = await corrReadJsonSafe(response);
    if (!response.ok || (payload && payload.ok === false)) {
      const detail = String(payload?.detail || payload?.message || `Request failed (${response.status})`).trim();
      const error = new Error(detail || `Request failed (${response.status})`);
      error.statusCode = Number(response.status || 0);
      error.detail = detail;
      throw error;
    }
    return payload || {};
  }
  function corrFriendlyUploadErrorMessage(inputError) {
    const statusCode = Number(inputError?.statusCode || 0);
    const detail = String(inputError?.detail || inputError?.message || "").trim();
    const lower = detail.toLowerCase();
    let friendly = "خطا در آپلود فایل مکاتبه.";
    if (statusCode === 413 || lower.includes("too large") || lower.includes("size")) {
      friendly = "حجم فایل بیشتر از حد مجاز است.";
    } else if (lower.includes("magic") || lower.includes("mime") || lower.includes("content type")) {
      friendly = "نوع واقعی فایل با فرمت مجاز هم‌خوانی ندارد.";
    } else if (lower.includes("blocked extension") || lower.includes("extension")) {
      friendly = "پسوند فایل مجاز نیست.";
    } else if (lower.includes("validation") || lower.includes("invalid")) {
      friendly = "فایل معتبر نیست یا با سیاست امنیتی سیستم سازگار نیست.";
    }
    return detail ? `${friendly}\nجزئیات: ${detail}` : friendly;
  }
  function ensureShamsiInputs() {
    if (shamsiDates) return;
    shamsiDates = initShamsiDateInputs([
      "corrDateFromFilter",
      "corrDateToFilter",
      "corrDateInput",
      "corrDueDateInput",
      "corrActionDueInput",
    ]);
  }
  function syncShamsiInputs() {
    shamsiDates?.syncAll?.();
  }
  function requireBridge(bridge, bridgeName) {
    if (!bridge || typeof bridge !== "object") {
      throw new Error(`${bridgeName} bridge unavailable.`);
    }
    return bridge;
  }

  function fillSelect(id, rows, first, allowEmpty = true) {
    const bridge = requireBridge(TS_CORRESPONDENCE_STATE, "Correspondence state");
    bridge.fillSelect(
      id,
      Array.isArray(rows) ? rows : [],
      String(first || ""),
      Boolean(allowEmpty),
      { getElementById: q }
    );
  }
  function refPreview() {
    const bridge = requireBridge(TS_CORRESPONDENCE_STATE, "Correspondence state");
    return bridge.buildReferencePreview({
      issuingCode: String(q("corrIssuingInput")?.value || ""),
      categoryCode: String(q("corrCategoryInput")?.value || ""),
      direction: String(q("corrDirectionInput")?.value || ""),
      dateValue: String(q("corrDateInput")?.value || ""),
    });
  }
  function corrUpdateReferencePreview() {
    const el = q("corrRefPreview"); if (!el) return;
    const manual = String(q("corrReferenceInput")?.value || "").trim();
    el.innerHTML = manual ? `<span class="manual-label">دستی</span> ${esc(manual)}` : `<span class="auto-label">اتوماتیک</span> ${esc(refPreview())}`;
  }
  function syncProjectFromIssuing() {
    const issuing = String(q("corrIssuingInput")?.value || "").toUpperCase(); const p = q("corrProjectInput");
    if (!issuing || !p || p.value) return;
    const bridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    const resolved = bridge.resolveProjectFromIssuing(
      issuing,
      Array.isArray(S.cat.issuing) ? S.cat.issuing : []
    );
    if (resolved) p.value = String(resolved);
  }

  async function loadCatalog() {
    const bridge = requireBridge(TS_CORRESPONDENCE_DATA, "Correspondence data");
    const b = await bridge.loadCatalog({ fetch: getCorrFetchFn() });
    if (!b?.ok) throw new Error(b?.detail || "Catalog load failed.");
    S.cat.issuing = b.issuing_entities || []; S.cat.categories = b.categories || []; S.cat.projects = b.projects || []; S.cat.tags = Array.isArray(b.tags) ? b.tags.map((row) => ({ code: String(row?.id || ""), name_e: row?.name || "", name_p: row?.name || "", color: row?.color || "" })) : [];
    fillSelect("corrIssuingFilter", S.cat.issuing, "\u0647\u0645\u0647 \u0645\u0631\u0627\u062c\u0639 \u0635\u062f\u0648\u0631"); fillSelect("corrCategoryFilter", S.cat.categories, "\u0647\u0645\u0647 \u062f\u0633\u062a\u0647\u200c\u0647\u0627");
    fillSelect("corrTagFilter", S.cat.tags, "همه تگ‌ها");
    fillSelect("corrIssuingInput", S.cat.issuing, "\u0627\u0646\u062a\u062e\u0627\u0628 \u0645\u0631\u062c\u0639 \u0635\u062f\u0648\u0631", false); fillSelect("corrCategoryInput", S.cat.categories, "\u0627\u0646\u062a\u062e\u0627\u0628 \u062f\u0633\u062a\u0647", false);
    fillSelect("corrProjectInput", S.cat.projects, "\u0627\u062a\u0648\u0645\u0627\u062a\u06cc\u06a9 \u0627\u0632 \u0645\u0631\u062c\u0639 / \u0628\u062f\u0648\u0646 \u067e\u0631\u0648\u0698\u0647"); fillSelect("corrTagInput", S.cat.tags, "بدون تگ");
    const tagWrap = q("corrTagInput")?.closest?.("div");
    const tagLabel = tagWrap?.querySelector?.("label");
    if (tagLabel) tagLabel.textContent = "تگ (اختیاری)";
  }
  async function loadDashboard() {
    try {
      const bridge = requireBridge(TS_CORRESPONDENCE_DATA, "Correspondence data");
      const b = await bridge.loadDashboard({ fetch: getCorrFetchFn() });
      if (!b?.ok) return;
      q("corrStatTotal").innerText = String(b.stats?.total || 0); q("corrStatOpen").innerText = String(b.stats?.open || 0); q("corrStatOverdue").innerText = String(b.stats?.overdue || 0); q("corrStatOpenActions").innerText = String(b.stats?.open_actions || 0);
    } catch (_) {
      // Keep UI usable even if dashboard counters fail to load.
    }
  }
  function filters() {
    return { search: String(q("corrSearchInput")?.value || "").trim(), issuing_code: String(q("corrIssuingFilter")?.value || "").trim(), category_code: String(q("corrCategoryFilter")?.value || "").trim(), tag_id: String(q("corrTagFilter")?.value || "").trim(), direction: String(q("corrDirectionFilter")?.value || "").trim(), status: String(q("corrStatusFilter")?.value || "").trim(), date_from: String(q("corrDateFromFilter")?.value || "").trim(), date_to: String(q("corrDateToFilter")?.value || "").trim() };
  }
  async function loadSearchSuggestions() {
    const input = q("corrSearchInput");
    const list = q("corrSearchSuggestions");
    if (!(input instanceof HTMLInputElement) || !(list instanceof HTMLDataListElement)) return;
    const value = String(input.value || "").trim();
    if (value.length < 2) {
      list.innerHTML = "";
      return;
    }
    try {
      const bridge = requireBridge(TS_CORRESPONDENCE_DATA, "Correspondence data");
      const body = await bridge.loadSuggestions(value, { fetch: getCorrFetchFn() });
      const items = Array.isArray(body?.items) ? body.items : [];
      list.innerHTML = items
        .map((item) => {
          const ref = esc(item?.reference_no || "");
          if (!ref) return "";
          const subject = esc(item?.subject || "");
          return `<option value="${ref}" label="${subject}"></option>`;
        })
        .join("");
    } catch (error) {
      console.error("Correspondence suggestions failed", error);
    }
  }
  function renderPager() {
    const bridge = requireBridge(TS_CORRESPONDENCE_STATE, "Correspondence state");
    bridge.renderPager(
      {
        page: S.page,
        size: S.size,
        total: S.total,
        loading: S.loading,
      },
      { getElementById: q }
    );
  }
  function renderRows() {
    const bridge = requireBridge(TS_CORRESPONDENCE_STATE, "Correspondence state");
    bridge.renderRows(
      {
        page: S.page,
        size: S.size,
        total: S.total,
        loading: S.loading,
        items: Array.isArray(S.items) ? S.items : [],
      },
      { getElementById: q }
    );
  }
  async function loadList() {
    S.loading = true; renderPager(); q("corrLoader").style.display = "block"; q("corrTableBody").innerHTML = "";
    try {
      const f = filters();
      const bridge = requireBridge(TS_CORRESPONDENCE_DATA, "Correspondence data");
      const b = await bridge.loadList(
        {
          skip: Math.max(0, (S.page - 1) * S.size),
          limit: S.size,
          ...f,
        },
        { fetch: getCorrFetchFn() }
      );
      if (!b?.ok) { err(b?.detail || "\u062e\u0637\u0627 \u062f\u0631 \u0644\u06cc\u0633\u062a \u0645\u06a9\u0627\u062a\u0628\u0627\u062a"); S.items = []; S.total = 0; renderRows(); return; }
      S.items = Array.isArray(b.data) ? b.data : []; S.total = Number(b.total || 0); renderRows();
    } catch (e) {
      console.error(e);
      err(e?.message || "\u062e\u0637\u0627 \u062f\u0631 \u0644\u06cc\u0633\u062a \u0645\u06a9\u0627\u062a\u0628\u0627\u062a");
      S.items = [];
      S.total = 0;
      renderRows();
    }
    finally { S.loading = false; q("corrLoader").style.display = "none"; renderPager(); }
  }
  function corrApplyFilters(reset = true) { if (reset) S.page = 1; loadList(); }
  function corrDebouncedSearch() {
    clearTimeout(S.suggestionsTimer);
    S.suggestionsTimer = setTimeout(() => loadSearchSuggestions(), 150);
    clearTimeout(S.timer);
    S.timer = setTimeout(() => corrApplyFilters(true), 350);
  }
  function corrResetFilters() { ["corrSearchInput", "corrIssuingFilter", "corrCategoryFilter", "corrTagFilter", "corrDirectionFilter", "corrStatusFilter", "corrDateFromFilter", "corrDateToFilter"].forEach((id) => { const e = q(id); if (e) e.value = ""; }); syncShamsiInputs(); S.page = 1; loadList(); }
  function corrPrevPage() { if (S.page <= 1 || S.loading) return; S.page -= 1; loadList(); }
  function corrNextPage() { if (S.loading) return; if (S.page * S.size >= S.total) return; S.page += 1; loadList(); }
  function corrChangePageSize(v) { S.size = Math.max(1, Number(v || 20)); S.page = 1; loadList(); }
  async function corrRefresh() { await loadDashboard(); await loadList(); }
  function corrCopyRef(v) { if (!v) return; if (window.copyToClipboard) return window.copyToClipboard(v); navigator.clipboard?.writeText(v); }

  function clearActionEditor() {
    const bridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    const defaults = bridge.createActionEditorDefaults();

    q("corrActionIdInput").value = String(defaults?.id ?? "");
    q("corrActionTypeInput").value = String(defaults?.action_type ?? "task");
    q("corrActionTitleInput").value = String(defaults?.title ?? "");
    q("corrActionDueInput").value = String(defaults?.due_date ?? "");
    q("corrActionStatusInput").value = String(defaults?.status ?? "Open");
    q("corrActionDescInput").value = String(defaults?.description ?? "");
    syncShamsiInputs();

    const submitBtn = q("corrActionSubmitBtn");
    if (submitBtn) {
      submitBtn.innerHTML = `<span class="material-icons-round">playlist_add_check</span> \u0627\u0641\u0632\u0648\u062F\u0646 \u0627\u0642\u062F\u0627\u0645`;
    }
  }
  function fillActionOptions() {
    const bridge = requireBridge(TS_CORRESPONDENCE_STATE, "Correspondence state");
    bridge.fillActionOptions(
      Array.isArray(S.actions) ? S.actions : [],
      { getElementById: q }
    );
  }
  function renderActions() {
    const bridge = requireBridge(TS_CORRESPONDENCE_STATE, "Correspondence state");
    bridge.renderActions(
      Array.isArray(S.actions) ? S.actions : [],
      { getElementById: q }
    );
  }
  async function loadActions(id) {
    if (!id) { S.actions = []; renderActions(); return; }
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.loadActions) {
        throw new Error("Load actions bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.loadActions(Number(id), { fetch: getCorrFetchFn() });
      if (!b?.ok) { err(b?.detail || "خطا در دریافت اقدامات"); S.actions = []; renderActions(); return; }
      S.actions = Array.isArray(b.data) ? b.data : [];
      renderActions();
    } catch (error) {
      err(error?.message || "خطا در دریافت اقدامات");
      S.actions = [];
      renderActions();
    }
  }
  async function corrSubmitAction() {
    const id = curId(); if (!id) return warn("ابتدا مکاتبه را ذخیره کنید.");
    const aid = Number(q("corrActionIdInput").value || 0);
    const actionInput = {
      action_type: q("corrActionTypeInput").value,
      title: q("corrActionTitleInput").value,
      description: q("corrActionDescInput").value,
      due_date: q("corrActionDueInput").value,
      status: q("corrActionStatusInput").value,
    };
    const formBridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    const payload = formBridge.buildActionPayload(actionInput);
    if (!payload.title && !payload.description) return warn("عنوان یا شرح اقدام را وارد کنید.");
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.upsertAction) {
        throw new Error("Save action bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.upsertAction(Number(id), Number(aid), payload, { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "خطا در ذخیره اقدام");
      info(aid > 0 ? "اقدام ویرایش شد." : "اقدام ثبت شد."); if (TS_CORRESPONDENCE_WORKFLOW?.afterActionMutation) {
        await TS_CORRESPONDENCE_WORKFLOW.afterActionMutation({
          correspondenceId: Number(id),
          clearActionEditor: () => clearActionEditor(),
          loadActions: (corrId) => loadActions(corrId),
          loadDashboard: () => loadDashboard(),
          loadList: () => loadList()
        });
      } else {
        clearActionEditor(); await loadActions(id); await loadDashboard(); await loadList();
      }
    } catch (error) {
      err(error?.message || "خطا در ذخیره اقدام");
    }
  }
  function corrEditAction(id) {
    const a = S.actions.find((x) => Number(x.id) === Number(id));
    if (!a) return;

    const formBridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    const editValues = formBridge.normalizeActionEditValues(a);

    q("corrActionIdInput").value = String(editValues?.id ?? a.id);
    q("corrActionTypeInput").value = String((editValues?.action_type ?? a.action_type) || "task");
    q("corrActionTitleInput").value = String((editValues?.title ?? a.title) || "");
    q("corrActionDueInput").value = String(editValues?.due_date || "");
    q("corrActionStatusInput").value = String((editValues?.status ?? a.status) || "Open");
    q("corrActionDescInput").value = String((editValues?.description ?? a.description) || "");
    syncShamsiInputs();

    const submitBtn = q("corrActionSubmitBtn");
    if (submitBtn) {
      submitBtn.innerHTML = `<span class="material-icons-round">save</span> \u0630\u062E\u06CC\u0631\u0647 \u062A\u063A\u06CC\u06CC\u0631 \u0627\u0642\u062F\u0627\u0645`;
    }
  }
  async function corrToggleActionClosed(id, checked) {
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.toggleActionClosed) {
        throw new Error("Toggle action bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.toggleActionClosed(Number(id), !!checked, { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "خطا در تغییر وضعیت اقدام");
      if (TS_CORRESPONDENCE_WORKFLOW?.afterActionMutation) {
        await TS_CORRESPONDENCE_WORKFLOW.afterActionMutation({
          correspondenceId: Number(curId()),
          loadActions: (corrId) => loadActions(corrId),
          loadDashboard: () => loadDashboard(),
          loadList: () => loadList()
        });
      } else {
        await loadActions(curId()); await loadDashboard(); await loadList();
      }
    } catch (error) {
      err(error?.message || "خطا در تغییر وضعیت اقدام");
    }
  }
  async function corrDeleteAction(id) {
    if (!confirm("اقدام حذف شود؟")) return;
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.deleteAction) {
        throw new Error("Delete action bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.deleteAction(Number(id), { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "خطا در حذف اقدام");
      info("اقدام حذف شد."); clearActionEditor(); if (TS_CORRESPONDENCE_WORKFLOW?.afterActionMutation) {
        await TS_CORRESPONDENCE_WORKFLOW.afterActionMutation({
          correspondenceId: Number(curId()),
          loadActions: (corrId) => loadActions(corrId),
          loadDashboard: () => loadDashboard(),
          loadList: () => loadList()
        });
      } else {
        await loadActions(curId()); await loadDashboard(); await loadList();
      }
    } catch (error) {
      err(error?.message || "خطا در حذف اقدام");
    }
  }

  function renderAtts() {
    const bridge = requireBridge(TS_CORRESPONDENCE_STATE, "Correspondence state");
    bridge.renderAttachments(
      Array.isArray(S.atts) ? S.atts : [],
      Array.isArray(S.actions) ? S.actions : [],
      { getElementById: q }
    );
  }
  async function loadAttachmentPinState() {
    try {
      const payload = await corrRequestJson(
        `/api/v1/storage/local-cache/manifest?entity_type=${STORAGE_ENTITY_ATTACHMENT}&only_pinned=true`
      );
      const pinned = new Set(
        (Array.isArray(payload?.items) ? payload.items : [])
          .map((row) => Number(row?.file_id || 0))
          .filter((id) => id > 0)
      );
      S.atts = (Array.isArray(S.atts) ? S.atts : []).map((item) => ({
        ...item,
        is_pinned: pinned.has(Number(item?.id || 0)),
      }));
    } catch (error) {
      console.error("Failed to load attachment pin manifest", error);
    }
  }
  async function enrichAttachmentOpenProjectStatus() {
    const items = (Array.isArray(S.atts) ? S.atts : [])
      .map((row) => ({
        entity_type: STORAGE_ENTITY_ATTACHMENT,
        entity_id: Number(row?.id || 0),
      }))
      .filter((row) => row.entity_id > 0);
    if (!items.length) return;
    try {
      const payload = await corrRequestJson("/api/v1/storage/openproject/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      const map = new Map(
        (Array.isArray(payload?.items) ? payload.items : []).map((row) => [
          Number(row?.entity_id || 0),
          row || {},
        ])
      );
      S.atts = (Array.isArray(S.atts) ? S.atts : []).map((item) => {
        const resolved = map.get(Number(item?.id || 0));
        if (!resolved) return item;
        return {
          ...item,
          openproject_sync_status:
            resolved.sync_status ?? item?.openproject_sync_status ?? null,
          openproject_work_package_id:
            resolved.work_package_id ?? item?.openproject_work_package_id ?? null,
          openproject_attachment_id:
            resolved.openproject_attachment_id ?? item?.openproject_attachment_id ?? null,
          openproject_last_synced_at:
            resolved.last_synced_at ?? item?.openproject_last_synced_at ?? null,
        };
      });
    } catch (error) {
      console.error("Failed to fetch OpenProject status for attachments", error);
    }
  }
  async function loadAtts(id) {
    if (!id) { S.atts = []; renderAtts(); return; }
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.loadAttachments) {
        throw new Error("Load attachments bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.loadAttachments(Number(id), { fetch: getCorrFetchFn() });
      if (!b?.ok) {
        err(b?.detail || "Failed to load attachments.");
        S.atts = [];
        renderAtts();
        return;
      }
      S.atts = Array.isArray(b.data) ? b.data : [];
      await enrichAttachmentOpenProjectStatus();
      await loadAttachmentPinState();
      renderAtts();
    } catch (error) {
      err(error?.message || "Failed to load attachments.");
      S.atts = [];
      renderAtts();
    }
  }
  function renderRelations() {
    const bridge = requireBridge(TS_CORRESPONDENCE_STATE, "Correspondence state");
    bridge.renderRelations(
      Array.isArray(S.relations) ? S.relations : [],
      { getElementById: q }
    );
  }
  async function loadRelations(id) {
    if (!id) { S.relations = []; renderRelations(); return; }
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.loadRelations) {
        throw new Error("Load relations bridge unavailable.");
      }
      const body = await TS_CORRESPONDENCE_WORKFLOW.loadRelations(Number(id), { fetch: getCorrFetchFn() });
      if (!body?.ok) {
        err(body?.detail || "خطا در دریافت ارتباطات.");
        S.relations = [];
        renderRelations();
        return;
      }
      S.relations = Array.isArray(body.data) ? body.data : [];
      renderRelations();
    } catch (error) {
      err(error?.message || "خطا در دریافت ارتباطات.");
      S.relations = [];
      renderRelations();
    }
  }
  async function corrToggleAttachmentPin(id, isPinned) {
    const attachmentId = Number(id || 0);
    if (!attachmentId) return;
    const endpoint = isPinned
      ? "/api/v1/storage/local-cache/unpin"
      : "/api/v1/storage/local-cache/pin";
    try {
      await corrRequestJson(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_id: attachmentId,
          entity_type: STORAGE_ENTITY_ATTACHMENT,
        }),
      });
      await loadAtts(curId());
    } catch (error) {
      err(`خطا در تغییر وضعیت Pin.\n${String(error?.message || "")}`);
    }
  }
  async function corrUploadAttachment() {
    const id = curId();
    if (!id) return warn("ابتدا مکاتبه را ذخیره کنید.");

    const f = q("corrAttachmentFileInput")?.files?.[0];
    if (!f) return warn("فایلی انتخاب نشده است.");

    const fd = new FormData();
    fd.append("file", f);
    fd.append("file_kind", String(q("corrAttachmentKindInput")?.value || "attachment"));
    const aid = String(q("corrAttachmentActionInput")?.value || "");
    if (aid) fd.append("action_id", aid);

    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.uploadAttachment) {
        throw new Error("Upload attachment bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.uploadAttachment(Number(id), fd, { fetch: getCorrFetchFn() });
      if (!b?.ok) {
        return err(corrFriendlyUploadErrorMessage({ message: b?.detail || "Upload failed" }));
      }
      q("corrAttachmentFileInput").value = "";
      info("فایل با موفقیت آپلود شد.");
      if (TS_CORRESPONDENCE_WORKFLOW?.afterAttachmentMutation) {
        await TS_CORRESPONDENCE_WORKFLOW.afterAttachmentMutation({
          correspondenceId: Number(id),
          loadAttachments: (corrId) => loadAtts(corrId),
          loadDashboard: () => loadDashboard(),
          loadList: () => loadList()
        });
      } else {
        await loadAtts(id); await loadDashboard(); await loadList();
      }
    } catch (error) {
      err(corrFriendlyUploadErrorMessage(error));
    }
  }
  async function corrDownloadAttachment(id) {
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.downloadAttachment) {
        throw new Error("Download bridge unavailable.");
      }
      const result = await TS_CORRESPONDENCE_WORKFLOW.downloadAttachment(Number(id), { fetch: getCorrFetchFn() });
      const fn = String(result?.fileName || "").trim() || `attachment-${id}`;
      const url = URL.createObjectURL(result.blob), a = document.createElement("a");
      a.href = url; a.download = fn; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (error) {
      err(error?.message || "خطا در دانلود");
    }
  }
  function corrPreviewUnsupportedMessage() {
    return "پیش‌نمایش فقط برای PDF و فایل‌های تصویری پشتیبانی می‌شود. برای این فایل از دانلود استفاده کنید.";
  }
  function corrPreviewType(result, fallbackName = "") {
    const rawType = String(result?.contentType || result?.blob?.type || "").split(";")[0].trim().toLowerCase();
    if (rawType === "application/pdf" || rawType === "application/x-pdf") return "pdf";
    if (rawType.startsWith("image/")) return "image";
    const name = String(result?.fileName || fallbackName || "").toLowerCase();
    if (name.endsWith(".pdf")) return "pdf";
    if (/\.(png|jpe?g|gif|webp|bmp)$/.test(name)) return "image";
    return "";
  }
  function corrClosePreview() {
    const modal = q("corrPreviewModal");
    const body = q("corrPreviewBody");
    const download = q("corrPreviewDownload");
    if (modal) {
      modal.style.display = "none";
      modal.setAttribute("aria-hidden", "true");
    }
    if (body) body.innerHTML = "";
    if (download) {
      download.removeAttribute("href");
      download.removeAttribute("download");
    }
    if (S.previewUrl) {
      URL.revokeObjectURL(S.previewUrl);
      S.previewUrl = "";
    }
  }
  function corrOpenBlobPreview(result, fallbackName = "preview") {
    if (!result?.blob) return err("فایلی برای پیش‌نمایش دریافت نشد.");
    const previewType = corrPreviewType(result, fallbackName);
    if (!previewType) return warn(corrPreviewUnsupportedMessage());
    corrClosePreview();
    const url = URL.createObjectURL(result.blob);
    S.previewUrl = url;
    const modal = q("corrPreviewModal");
    const title = q("corrPreviewTitle");
    const body = q("corrPreviewBody");
    const download = q("corrPreviewDownload");
    const fileName = String(result?.fileName || fallbackName || "preview").trim() || "preview";
    if (!modal || !body) {
      URL.revokeObjectURL(url);
      S.previewUrl = "";
      return err("پنجره پیش‌نمایش در صفحه پیدا نشد.");
    }
    if (title) title.textContent = `پیش‌نمایش: ${fileName}`;
    if (download) {
      download.href = url;
      download.download = fileName;
    }
    body.innerHTML = previewType === "pdf"
      ? `<iframe class="corr-preview-frame" src="${url}" title="${esc(fileName)}"></iframe>`
      : `<img class="corr-preview-image" src="${url}" alt="${esc(fileName)}">`;
    modal.style.display = "flex";
    modal.setAttribute("aria-hidden", "false");
  }
  async function corrPreviewCorrespondence(id) {
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.previewCorrespondence) {
        throw new Error("Preview bridge unavailable.");
      }
      const result = await TS_CORRESPONDENCE_WORKFLOW.previewCorrespondence(Number(id), { fetch: getCorrFetchFn() });
      corrOpenBlobPreview(result, `correspondence-${id}`);
    } catch (error) {
      err(error?.message || "پیش‌نمایش برای این مکاتبه در دسترس نیست.");
    }
  }
  async function corrPreviewAttachment(id) {
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.previewAttachment) {
        throw new Error("Attachment preview bridge unavailable.");
      }
      const result = await TS_CORRESPONDENCE_WORKFLOW.previewAttachment(Number(id), { fetch: getCorrFetchFn() });
      corrOpenBlobPreview(result, `attachment-${id}`);
    } catch (error) {
      err(error?.message || "پیش‌نمایش برای این فایل در دسترس نیست.");
    }
  }
  function corrPreviewUnsupported() {
    warn(corrPreviewUnsupportedMessage());
  }
  async function corrSubmitRelation() {
    const id = curId();
    if (!id) return warn("ابتدا مکاتبه را ذخیره کنید.");
    const targetCode = String(q("corrRelationTargetCodeInput")?.value || "").trim();
    if (!targetCode) return warn("کد مقصد ارتباط را وارد کنید.");
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.createRelation) {
        throw new Error("Relation bridge unavailable.");
      }
      const body = await TS_CORRESPONDENCE_WORKFLOW.createRelation(
        Number(id),
        {
          target_entity_type: String(q("corrRelationTargetTypeInput")?.value || "document"),
          target_code: targetCode,
          relation_type: String(q("corrRelationTypeInput")?.value || "related"),
          notes: String(q("corrRelationNotesInput")?.value || "").trim() || null,
        },
        { fetch: getCorrFetchFn() }
      );
      if (!body?.ok) return err(body?.detail || "خطا در ثبت ارتباط.");
      q("corrRelationTargetCodeInput").value = "";
      q("corrRelationNotesInput").value = "";
      info("ارتباط ثبت شد.");
      await loadRelations(id);
    } catch (error) {
      err(error?.message || "خطا در ثبت ارتباط.");
    }
  }
  async function corrDeleteRelation(relationId) {
    const id = curId();
    if (!id || !relationId) return;
    if (!confirm("ارتباط حذف شود؟")) return;
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.deleteRelation) {
        throw new Error("Delete relation bridge unavailable.");
      }
      const body = await TS_CORRESPONDENCE_WORKFLOW.deleteRelation(Number(id), String(relationId), { fetch: getCorrFetchFn() });
      if (!body?.ok) return err(body?.detail || "خطا در حذف ارتباط.");
      info("ارتباط حذف شد.");
      await loadRelations(id);
    } catch (error) {
      err(error?.message || "خطا در حذف ارتباط.");
    }
  }
  async function corrDeleteCorrespondence(id) {
    const correspondenceId = Number(id || 0);
    if (!correspondenceId) return;
    if (!confirm("این مکاتبه و همه اقدامات و پیوست‌های آن حذف شود؟")) return;
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.deleteCorrespondence) {
        throw new Error("Delete correspondence bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.deleteCorrespondence(correspondenceId, { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "خطا در حذف مکاتبه");
      info("مکاتبه حذف شد.");
      await loadDashboard();
      await loadList();
    } catch (error) {
      err(error?.message || "خطا در حذف مکاتبه");
    }
  }
  async function corrDeleteAttachment(id) {
    if (!confirm("فایل حذف شود؟")) return;
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.deleteAttachment) {
        throw new Error("Delete attachment bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.deleteAttachment(Number(id), { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "خطا در حذف فایل");
      info("فایل حذف شد."); if (TS_CORRESPONDENCE_WORKFLOW?.afterAttachmentMutation) {
        await TS_CORRESPONDENCE_WORKFLOW.afterAttachmentMutation({
          correspondenceId: Number(curId()),
          loadAttachments: (corrId) => loadAtts(corrId),
          loadDashboard: () => loadDashboard(),
          loadList: () => loadList()
        });
      } else {
        await loadAtts(curId()); await loadDashboard(); await loadList();
      }
    } catch (error) {
      err(error?.message || "خطا در حذف فایل");
    }
  }

  function applyFormValues(values) {
    const v = values || {};
    q("corrIdInput").value = String(v.id || "");
    q("corrIssuingInput").value = String(v.issuing_code || "");
    q("corrCategoryInput").value = String(v.category_code || "");
    q("corrDirectionInput").value = String(v.direction || "O");
    q("corrProjectInput").value = String(v.project_code || "");
    q("corrTagInput").value = String(v.tag_id || "");
    q("corrReferenceInput").value = String(v.reference_no || "");
    q("corrSubjectInput").value = String(v.subject || "");
    q("corrSenderInput").value = String(v.sender || "");
    q("corrRecipientInput").value = String(v.recipient || "");
    q("corrDateInput").value = String(v.corr_date || "");
    q("corrDueDateInput").value = String(v.due_date || "");
    q("corrStatusInput").value = String(v.status || "Open");
    q("corrPriorityInput").value = String(v.priority || "Normal");
    q("corrNotesInput").value = String(v.notes || "");
    syncShamsiInputs();
  }

  function formDefaults() {
    const formBridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    applyFormValues(formBridge.createDefaultValues());
    if (!q("corrIssuingInput").value && q("corrIssuingInput").options.length) q("corrIssuingInput").selectedIndex = 0;
    if (!q("corrCategoryInput").value && q("corrCategoryInput").options.length) q("corrCategoryInput").selectedIndex = 0;
    S.actions = []; S.atts = []; S.relations = []; clearActionEditor(); q("corrActionsBody").innerHTML = `<tr><td colspan="5" class="corr-empty-row">ابتدا مکاتبه را ذخیره کنید.</td></tr>`; q("corrAttachmentsBody").innerHTML = `<tr><td colspan="7" class="corr-empty-row">ابتدا مکاتبه را ذخیره کنید.</td></tr>`; q("corrRelationsBody").innerHTML = `<tr><td colspan="6" class="corr-empty-row">ابتدا مکاتبه را ذخیره کنید.</td></tr>`; fillActionOptions(); corrUpdateReferencePreview();
  }
  function payloadForm() {
    const input = {
      project_code: q("corrProjectInput").value,
      issuing_code: q("corrIssuingInput").value,
      category_code: q("corrCategoryInput").value,
      tag_id: q("corrTagInput").value,
      direction: q("corrDirectionInput").value,
      reference_no: q("corrReferenceInput").value,
      subject: q("corrSubjectInput").value,
      sender: q("corrSenderInput").value,
      recipient: q("corrRecipientInput").value,
      corr_date: q("corrDateInput").value,
      due_date: q("corrDueDateInput").value,
      status: q("corrStatusInput").value,
      priority: q("corrPriorityInput").value,
      notes: q("corrNotesInput").value
    };
    const formBridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    return formBridge.buildPayload(input);
  }
  async function corrSave(e) {
    e.preventDefault(); const id = curId(), p = payloadForm(), btn = q("corrSaveBtn");
    if (!p.issuing_code || !p.category_code || !p.subject) return warn("مرجع صدور، دسته و موضوع الزامی است.");
    if (!p.corr_date) return warn("تاریخ مکاتبه الزامی است.");
    btn.disabled = true;
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.saveCorrespondence) {
        throw new Error("Save correspondence bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.saveCorrespondence(Number(id), p, { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "خطا در ذخیره مکاتبه");
      const sid = Number(b.data?.id || 0); if (sid) { q("corrIdInput").value = String(sid); q("corrModalTitle").innerText = "ویرایش مکاتبه"; await loadActions(sid); await loadAtts(sid); await loadRelations(sid); }
      info(id > 0 ? "مکاتبه ویرایش شد." : "مکاتبه ثبت شد. حالا اقدام و فایل ثبت کنید."); await loadDashboard(); await loadList();
    } catch (error) {
      err(error?.message || "خطا در ذخیره مکاتبه");
    } finally { btn.disabled = false; }
  }
  function corrOpenCreate() { q("corrModalTitle").innerText = "مکاتبه جدید"; formDefaults(); syncProjectFromIssuing(); q("corrModal").style.display = "flex"; }
  async function corrOpenEdit(id) {
    const x = S.items.find((r) => Number(r.id) === Number(id)); if (!x) return;
    q("corrModalTitle").innerText = "ویرایش مکاتبه";
    const formBridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    applyFormValues(formBridge.normalizeEditValues(x));
    clearActionEditor(); corrUpdateReferencePreview(); q("corrModal").style.display = "flex"; await loadActions(Number(x.id)); await loadAtts(Number(x.id)); await loadRelations(Number(x.id));
  }
  async function corrOpenWorkflow(id) { if (TS_CORRESPONDENCE_WORKFLOW?.openWorkflow) return TS_CORRESPONDENCE_WORKFLOW.openWorkflow(Number(id), { openEdit: (corrId) => corrOpenEdit(corrId), scrollToActions: () => q("corrActionsSection")?.scrollIntoView({ behavior: "smooth", block: "start" }) }); await corrOpenEdit(id); q("corrActionsSection")?.scrollIntoView({ behavior: "smooth", block: "start" }); }
  function corrCloseModal() { corrClosePreview(); q("corrModal").style.display = "none"; }

  function bindEvents() {
    if (S.bound) return;
    const root = q("view-correspondence");
    if (!root) return;
    const bridge = requireBridge(TS_CORRESPONDENCE_UI, "Correspondence UI");
    const handled = bridge.bindEvents(root, {
      debouncedSearch: () => corrDebouncedSearch(),
      applyFilters: (reset = true) => corrApplyFilters(reset),
      changePageSize: (value) => corrChangePageSize(value),
      save: (event) => corrSave(event),
      updateReferencePreview: () => corrUpdateReferencePreview(),
      syncProjectFromIssuing: () => syncProjectFromIssuing(),
      openCreate: () => corrOpenCreate(),
      resetFilters: () => corrResetFilters(),
      refresh: () => corrRefresh(),
      prevPage: () => corrPrevPage(),
      nextPage: () => corrNextPage(),
      closeModal: () => corrCloseModal(),
      submitAction: () => corrSubmitAction(),
      clearActionEditor: () => clearActionEditor(),
      uploadAttachment: () => corrUploadAttachment(),
      openEdit: (id) => corrOpenEdit(id),
      openWorkflow: (id) => corrOpenWorkflow(id),
      previewCorrespondence: (id) => corrPreviewCorrespondence(id),
      previewAttachment: (id) => corrPreviewAttachment(id),
      previewUnsupported: () => corrPreviewUnsupported(),
      closePreview: () => corrClosePreview(),
      deleteCorrespondence: (id) => corrDeleteCorrespondence(id),
      copyRef: (value) => corrCopyRef(value),
      submitRelation: () => corrSubmitRelation(),
      deleteRelation: (id) => corrDeleteRelation(id),
      editAction: (id) => corrEditAction(id),
      deleteAction: (id) => corrDeleteAction(id),
      downloadAttachment: (id) => corrDownloadAttachment(id),
      deleteAttachment: (id) => corrDeleteAttachment(id),
      toggleAttachmentPin: (id, isPinned) => corrToggleAttachmentPin(id, isPinned),
      toggleActionClosed: (id, checked) => corrToggleActionClosed(id, checked),
    });
    if (!handled) {
      throw new Error("Correspondence UI bridge did not bind events.");
    }
    S.bound = true;
  }

  async function init() {
    ensureShamsiInputs();
    bindEvents();
    await loadCatalog();
    if (!S.inited) { S.inited = true; formDefaults(); }
    await loadDashboard();
    await loadList();
  }
  window.initCorrespondenceView = init; window.corrOpenCreate = corrOpenCreate; window.corrOpenEdit = corrOpenEdit; window.corrOpenWorkflow = corrOpenWorkflow; window.corrCloseModal = corrCloseModal; window.corrSave = corrSave;
  window.corrDebouncedSearch = corrDebouncedSearch; window.corrApplyFilters = corrApplyFilters; window.corrResetFilters = corrResetFilters; window.corrPrevPage = corrPrevPage; window.corrNextPage = corrNextPage; window.corrChangePageSize = corrChangePageSize; window.corrRefresh = corrRefresh; window.corrUpdateReferencePreview = corrUpdateReferencePreview; window.corrSubmitAction = corrSubmitAction; window.corrClearActionEditor = clearActionEditor; window.corrUploadAttachment = corrUploadAttachment; window.corrPreviewCorrespondence = corrPreviewCorrespondence; window.corrPreviewAttachment = corrPreviewAttachment; window.corrPreviewUnsupported = corrPreviewUnsupported; window.corrClosePreview = corrClosePreview; window.corrSubmitRelation = corrSubmitRelation; window.corrDeleteRelation = corrDeleteRelation; window.corrDeleteCorrespondence = corrDeleteCorrespondence; window.corrCopyRef = corrCopyRef; window.corrEditAction = corrEditAction; window.corrDeleteAction = corrDeleteAction; window.corrToggleActionClosed = corrToggleActionClosed; window.corrDownloadAttachment = corrDownloadAttachment; window.corrDeleteAttachment = corrDeleteAttachment;
  const corrRoot = q("view-correspondence");
  if (corrRoot && corrRoot.style.display !== "none") init();
})();













