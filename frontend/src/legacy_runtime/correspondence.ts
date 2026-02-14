// @ts-nocheck
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
  const S = { inited: false, bound: false, page: 1, size: 20, total: 0, items: [], loading: false, timer: null, actions: [], atts: [], cat: { issuing: [], categories: [], projects: [], disciplines: [] } };
  const q = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const dIn = (v) => !v ? "" : (String(v).includes("T") ? String(v).split("T")[0] : String(v).slice(0, 10));
  const dIso = (v) => (String(v || "").trim() ? `${String(v).trim()}T00:00:00` : null);
  const dFa = (v) => { if (!v) return "-"; const d = new Date(v); return Number.isNaN(d.getTime()) ? "-" : d.toLocaleDateString("fa-IR"); };
  const dirCode = (v) => ["I", "IN", "INBOUND"].includes(String(v || "").toUpperCase()) ? "I" : "O";
  const dirFa = (v) => dirCode(v) === "I" ? "Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â§ÃƒËœÃ‚Â±ÃƒËœÃ‚Â¯Ãƒâ„¢Ã¢â‚¬Â¡" : "ÃƒËœÃ‚ÂµÃƒËœÃ‚Â§ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡";
  const statusClass = (s) => { const k = String(s || "").toLowerCase(); return k === "closed" ? "is-closed" : (k === "overdue" ? "is-overdue" : "is-open"); };
  const kindFa = (k) => ({ letter: "Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ Ãƒâ„¢Ã¢â‚¬Â ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦Ãƒâ„¢Ã¢â‚¬Â¡", original: "Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂµÃƒâ„¢Ã¢â‚¬Å¾Ãƒâ€ºÃ…â€™", attachment: "Ãƒâ„¢Ã‚Â¾Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â³ÃƒËœÃ‚Âª" }[String(k || "").toLowerCase()] || "Ãƒâ„¢Ã‚Â¾Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â³ÃƒËœÃ‚Âª");
  const info = (m) => window.UI?.success?.(m); const warn = (m) => window.UI?.warning?.(m); const err = (m) => window.UI?.error?.(m);
  const nowYyMm = (v) => { const d = v ? new Date(`${v}T00:00:00`) : new Date(); return Number.isNaN(d.getTime()) ? "0000" : `${String(d.getFullYear()).slice(-2)}${String(d.getMonth() + 1).padStart(2, "0")}`; };
  const curId = () => Number(q("corrIdInput")?.value || 0);
  const getCorrFetchFn = () => (typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch);
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
    el.innerHTML = manual ? `<span class="manual-label">ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â³ÃƒËœÃ‚ÂªÃƒâ€ºÃ…â€™</span> ${esc(manual)}` : `<span class="auto-label">ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒâ„¢Ã‹â€ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒâ€ºÃ…â€™ÃƒÅ¡Ã‚Â©</span> ${esc(refPreview())}`;
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
    S.cat.issuing = b.issuing_entities || []; S.cat.categories = b.categories || []; S.cat.projects = b.projects || []; S.cat.disciplines = b.disciplines || [];
    fillSelect("corrIssuingFilter", S.cat.issuing, "\u0647\u0645\u0647 \u0645\u0631\u0627\u062c\u0639 \u0635\u062f\u0648\u0631"); fillSelect("corrCategoryFilter", S.cat.categories, "\u0647\u0645\u0647 \u062f\u0633\u062a\u0647\u200c\u0647\u0627");
    fillSelect("corrIssuingInput", S.cat.issuing, "\u0627\u0646\u062a\u062e\u0627\u0628 \u0645\u0631\u062c\u0639 \u0635\u062f\u0648\u0631", false); fillSelect("corrCategoryInput", S.cat.categories, "\u0627\u0646\u062a\u062e\u0627\u0628 \u062f\u0633\u062a\u0647", false);
    fillSelect("corrProjectInput", S.cat.projects, "\u0627\u062a\u0648\u0645\u0627\u062a\u06cc\u06a9 \u0627\u0632 \u0645\u0631\u062c\u0639 / \u0628\u062f\u0648\u0646 \u067e\u0631\u0648\u0698\u0647"); fillSelect("corrDisciplineInput", S.cat.disciplines, "\u0628\u062f\u0648\u0646 \u062f\u06cc\u0633\u06cc\u067e\u0644\u06cc\u0646");
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
    return { search: String(q("corrSearchInput")?.value || "").trim(), issuing_code: String(q("corrIssuingFilter")?.value || "").trim(), category_code: String(q("corrCategoryFilter")?.value || "").trim(), direction: String(q("corrDirectionFilter")?.value || "").trim(), status: String(q("corrStatusFilter")?.value || "").trim(), date_from: String(q("corrDateFromFilter")?.value || "").trim(), date_to: String(q("corrDateToFilter")?.value || "").trim() };
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
  function corrDebouncedSearch() { clearTimeout(S.timer); S.timer = setTimeout(() => corrApplyFilters(true), 350); }
  function corrResetFilters() { ["corrSearchInput", "corrIssuingFilter", "corrCategoryFilter", "corrDirectionFilter", "corrStatusFilter", "corrDateFromFilter", "corrDateToFilter"].forEach((id) => { const e = q(id); if (e) e.value = ""; }); S.page = 1; loadList(); }
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
      if (!b?.ok) { err(b?.detail || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â±Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â§Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Âª ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦ÃƒËœÃ‚Â§ÃƒËœÃ‚Âª"); S.actions = []; renderActions(); return; }
      S.actions = Array.isArray(b.data) ? b.data : [];
      renderActions();
    } catch (error) {
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â±Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â§Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Âª ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦ÃƒËœÃ‚Â§ÃƒËœÃ‚Âª");
      S.actions = [];
      renderActions();
    }
  }
  async function corrSubmitAction() {
    const id = curId(); if (!id) return warn("ÃƒËœÃ‚Â§ÃƒËœÃ‚Â¨ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â°ÃƒËœÃ‚Â®Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒÅ¡Ã‚Â©Ãƒâ„¢Ã¢â‚¬Â Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â¯.");
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
    if (!payload.title && !payload.description) return warn("ÃƒËœÃ‚Â¹Ãƒâ„¢Ã¢â‚¬Â Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â  Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â´ÃƒËœÃ‚Â±ÃƒËœÃ‚Â­ ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦ ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§ Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â§ÃƒËœÃ‚Â±ÃƒËœÃ‚Â¯ ÃƒÅ¡Ã‚Â©Ãƒâ„¢Ã¢â‚¬Â Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â¯.");
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.upsertAction) {
        throw new Error("Save action bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.upsertAction(Number(id), Number(aid), payload, { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â°ÃƒËœÃ‚Â®Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦");
      info(aid > 0 ? "ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦ Ãƒâ„¢Ã‹â€ Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â´ ÃƒËœÃ‚Â´ÃƒËœÃ‚Â¯." : "ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦ ÃƒËœÃ‚Â«ÃƒËœÃ‚Â¨ÃƒËœÃ‚Âª ÃƒËœÃ‚Â´ÃƒËœÃ‚Â¯."); if (TS_CORRESPONDENCE_WORKFLOW?.afterActionMutation) {
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
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â°ÃƒËœÃ‚Â®Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦");
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
      if (!b?.ok) return err(b?.detail || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚ÂªÃƒËœÃ‚ÂºÃƒâ€ºÃ…â€™Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â± Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¶ÃƒËœÃ‚Â¹Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Âª ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦");
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
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚ÂªÃƒËœÃ‚ÂºÃƒâ€ºÃ…â€™Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â± Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¶ÃƒËœÃ‚Â¹Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Âª ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦");
    }
  }
  async function corrDeleteAction(id) {
    if (!confirm("ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦ ÃƒËœÃ‚Â­ÃƒËœÃ‚Â°Ãƒâ„¢Ã‚Â ÃƒËœÃ‚Â´Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¯ÃƒËœÃ…Â¸")) return;
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.deleteAction) {
        throw new Error("Delete action bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.deleteAction(Number(id), { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â­ÃƒËœÃ‚Â°Ãƒâ„¢Ã‚Â ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦");
      info("ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦ ÃƒËœÃ‚Â­ÃƒËœÃ‚Â°Ãƒâ„¢Ã‚Â ÃƒËœÃ‚Â´ÃƒËœÃ‚Â¯."); clearActionEditor(); if (TS_CORRESPONDENCE_WORKFLOW?.afterActionMutation) {
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
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â­ÃƒËœÃ‚Â°Ãƒâ„¢Ã‚Â ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦");
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
  async function loadAtts(id) {
    if (!id) { S.atts = []; renderAtts(); return; }
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.loadAttachments) {
        throw new Error("Load attachments bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.loadAttachments(Number(id), { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â±Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â§Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Âª Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ÃƒÂ¢Ã¢â€šÂ¬Ã…â€™Ãƒâ„¢Ã¢â‚¬Â¡ÃƒËœÃ‚Â§"), S.atts = [], renderAtts();
      S.atts = Array.isArray(b.data) ? b.data : [];
      renderAtts();
    } catch (error) {
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â±Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â§Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Âª Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ÃƒÂ¢Ã¢â€šÂ¬Ã…â€™Ãƒâ„¢Ã¢â‚¬Â¡ÃƒËœÃ‚Â§");
      S.atts = [];
      renderAtts();
    }
  }
  async function corrUploadAttachment() {
    const id = curId(); if (!id) return warn("ÃƒËœÃ‚Â§ÃƒËœÃ‚Â¨ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â°ÃƒËœÃ‚Â®Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒÅ¡Ã‚Â©Ãƒâ„¢Ã¢â‚¬Â Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â¯.");
    const f = q("corrAttachmentFileInput")?.files?.[0]; if (!f) return warn("Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â ÃƒËœÃ‚ÂªÃƒËœÃ‚Â®ÃƒËœÃ‚Â§ÃƒËœÃ‚Â¨ ÃƒÅ¡Ã‚Â©Ãƒâ„¢Ã¢â‚¬Â Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â¯.");
    const fd = new FormData(); fd.append("file", f); fd.append("file_kind", String(q("corrAttachmentKindInput")?.value || "attachment")); const aid = String(q("corrAttachmentActionInput")?.value || ""); if (aid) fd.append("action_id", aid);
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.uploadAttachment) {
        throw new Error("Upload attachment bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.uploadAttachment(Number(id), fd, { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â¢Ãƒâ„¢Ã‚Â¾Ãƒâ„¢Ã¢â‚¬Å¾Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¯ Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾");
      q("corrAttachmentFileInput").value = ""; info("Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ ÃƒËœÃ‚Â¢Ãƒâ„¢Ã‚Â¾Ãƒâ„¢Ã¢â‚¬Å¾Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¯ ÃƒËœÃ‚Â´ÃƒËœÃ‚Â¯."); if (TS_CORRESPONDENCE_WORKFLOW?.afterAttachmentMutation) {
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
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â¢Ãƒâ„¢Ã‚Â¾Ãƒâ„¢Ã¢â‚¬Å¾Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¯ Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾");
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
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â Ãƒâ„¢Ã¢â‚¬Å¾Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¯");
    }
  }
  async function corrDeleteAttachment(id) {
    if (!confirm("Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ ÃƒËœÃ‚Â­ÃƒËœÃ‚Â°Ãƒâ„¢Ã‚Â ÃƒËœÃ‚Â´Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¯ÃƒËœÃ…Â¸")) return;
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.deleteAttachment) {
        throw new Error("Delete attachment bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.deleteAttachment(Number(id), { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â­ÃƒËœÃ‚Â°Ãƒâ„¢Ã‚Â Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾");
      info("Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ ÃƒËœÃ‚Â­ÃƒËœÃ‚Â°Ãƒâ„¢Ã‚Â ÃƒËœÃ‚Â´ÃƒËœÃ‚Â¯."); if (TS_CORRESPONDENCE_WORKFLOW?.afterAttachmentMutation) {
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
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â­ÃƒËœÃ‚Â°Ãƒâ„¢Ã‚Â Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾");
    }
  }

  function applyFormValues(values) {
    const v = values || {};
    q("corrIdInput").value = String(v.id || "");
    q("corrIssuingInput").value = String(v.issuing_code || "");
    q("corrCategoryInput").value = String(v.category_code || "");
    q("corrDirectionInput").value = String(v.direction || "O");
    q("corrProjectInput").value = String(v.project_code || "");
    q("corrDisciplineInput").value = String(v.discipline_code || "");
    q("corrReferenceInput").value = String(v.reference_no || "");
    q("corrSubjectInput").value = String(v.subject || "");
    q("corrSenderInput").value = String(v.sender || "");
    q("corrRecipientInput").value = String(v.recipient || "");
    q("corrDateInput").value = String(v.corr_date || "");
    q("corrDueDateInput").value = String(v.due_date || "");
    q("corrStatusInput").value = String(v.status || "Open");
    q("corrPriorityInput").value = String(v.priority || "Normal");
    q("corrNotesInput").value = String(v.notes || "");
  }

  function formDefaults() {
    const formBridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    applyFormValues(formBridge.createDefaultValues());
    if (!q("corrIssuingInput").value && q("corrIssuingInput").options.length) q("corrIssuingInput").selectedIndex = 0;
    if (!q("corrCategoryInput").value && q("corrCategoryInput").options.length) q("corrCategoryInput").selectedIndex = 0;
    S.actions = []; S.atts = []; clearActionEditor(); q("corrActionsBody").innerHTML = `<tr><td colspan="5" class="corr-empty-row">ÃƒËœÃ‚Â§ÃƒËœÃ‚Â¨ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â°ÃƒËœÃ‚Â®Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒÅ¡Ã‚Â©Ãƒâ„¢Ã¢â‚¬Â Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â¯.</td></tr>`; q("corrAttachmentsBody").innerHTML = `<tr><td colspan="5" class="corr-empty-row">ÃƒËœÃ‚Â§ÃƒËœÃ‚Â¨ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â°ÃƒËœÃ‚Â®Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒÅ¡Ã‚Â©Ãƒâ„¢Ã¢â‚¬Â Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â¯.</td></tr>`; fillActionOptions(); corrUpdateReferencePreview();
  }
  function payloadForm() {
    const input = {
      project_code: q("corrProjectInput").value,
      issuing_code: q("corrIssuingInput").value,
      category_code: q("corrCategoryInput").value,
      discipline_code: q("corrDisciplineInput").value,
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
    if (!p.issuing_code || !p.category_code || !p.subject) return warn("Ãƒâ„¢Ã¢â‚¬Â¦ÃƒËœÃ‚Â±ÃƒËœÃ‚Â¬ÃƒËœÃ‚Â¹ ÃƒËœÃ‚ÂµÃƒËœÃ‚Â¯Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â±ÃƒËœÃ…â€™ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â³ÃƒËœÃ‚ÂªÃƒâ„¢Ã¢â‚¬Â¡ Ãƒâ„¢Ã‹â€  Ãƒâ„¢Ã¢â‚¬Â¦Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¶Ãƒâ„¢Ã‹â€ ÃƒËœÃ‚Â¹ ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¾ÃƒËœÃ‚Â²ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦Ãƒâ€ºÃ…â€™ ÃƒËœÃ‚Â§ÃƒËœÃ‚Â³ÃƒËœÃ‚Âª.");
    if (!p.corr_date) return warn("ÃƒËœÃ‚ÂªÃƒËœÃ‚Â§ÃƒËœÃ‚Â±Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â® Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¾ÃƒËœÃ‚Â²ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦Ãƒâ€ºÃ…â€™ ÃƒËœÃ‚Â§ÃƒËœÃ‚Â³ÃƒËœÃ‚Âª.");
    btn.disabled = true;
    try {
      if (!TS_CORRESPONDENCE_WORKFLOW?.saveCorrespondence) {
        throw new Error("Save correspondence bridge unavailable.");
      }
      const b = await TS_CORRESPONDENCE_WORKFLOW.saveCorrespondence(Number(id), p, { fetch: getCorrFetchFn() });
      if (!b?.ok) return err(b?.detail || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â°ÃƒËœÃ‚Â®Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡");
      const sid = Number(b.data?.id || 0); if (sid) { q("corrIdInput").value = String(sid); q("corrModalTitle").innerText = "Ãƒâ„¢Ã‹â€ Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â´ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡"; await loadActions(sid); await loadAtts(sid); }
      info(id > 0 ? "Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡ Ãƒâ„¢Ã‹â€ Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â´ ÃƒËœÃ‚Â´ÃƒËœÃ‚Â¯." : "Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â«ÃƒËœÃ‚Â¨ÃƒËœÃ‚Âª ÃƒËœÃ‚Â´ÃƒËœÃ‚Â¯. ÃƒËœÃ‚Â­ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¾ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Å¡ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â§Ãƒâ„¢Ã¢â‚¬Â¦ Ãƒâ„¢Ã‹â€  Ãƒâ„¢Ã‚ÂÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™Ãƒâ„¢Ã¢â‚¬Å¾ ÃƒËœÃ‚Â«ÃƒËœÃ‚Â¨ÃƒËœÃ‚Âª ÃƒÅ¡Ã‚Â©Ãƒâ„¢Ã¢â‚¬Â Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â¯."); await loadDashboard(); await loadList();
    } catch (error) {
      err(error?.message || "ÃƒËœÃ‚Â®ÃƒËœÃ‚Â·ÃƒËœÃ‚Â§ ÃƒËœÃ‚Â¯ÃƒËœÃ‚Â± ÃƒËœÃ‚Â°ÃƒËœÃ‚Â®Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±Ãƒâ„¢Ã¢â‚¬Â¡ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡");
    } finally { btn.disabled = false; }
  }
  function corrOpenCreate() { q("corrModalTitle").innerText = "Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡ ÃƒËœÃ‚Â¬ÃƒËœÃ‚Â¯Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â¯"; formDefaults(); syncProjectFromIssuing(); q("corrModal").style.display = "flex"; }
  async function corrOpenEdit(id) {
    const x = S.items.find((r) => Number(r.id) === Number(id)); if (!x) return;
    q("corrModalTitle").innerText = "Ãƒâ„¢Ã‹â€ Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â±ÃƒËœÃ‚Â§Ãƒâ€ºÃ…â€™ÃƒËœÃ‚Â´ Ãƒâ„¢Ã¢â‚¬Â¦ÃƒÅ¡Ã‚Â©ÃƒËœÃ‚Â§ÃƒËœÃ‚ÂªÃƒËœÃ‚Â¨Ãƒâ„¢Ã¢â‚¬Â¡";
    const formBridge = requireBridge(TS_CORRESPONDENCE_FORM, "Correspondence form");
    applyFormValues(formBridge.normalizeEditValues(x));
    clearActionEditor(); corrUpdateReferencePreview(); q("corrModal").style.display = "flex"; await loadActions(Number(x.id)); await loadAtts(Number(x.id));
  }
  async function corrOpenWorkflow(id) { if (TS_CORRESPONDENCE_WORKFLOW?.openWorkflow) return TS_CORRESPONDENCE_WORKFLOW.openWorkflow(Number(id), { openEdit: (corrId) => corrOpenEdit(corrId), scrollToActions: () => q("corrActionsSection")?.scrollIntoView({ behavior: "smooth", block: "start" }) }); await corrOpenEdit(id); q("corrActionsSection")?.scrollIntoView({ behavior: "smooth", block: "start" }); }
  function corrCloseModal() { q("corrModal").style.display = "none"; }

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
      copyRef: (value) => corrCopyRef(value),
      editAction: (id) => corrEditAction(id),
      deleteAction: (id) => corrDeleteAction(id),
      downloadAttachment: (id) => corrDownloadAttachment(id),
      deleteAttachment: (id) => corrDeleteAttachment(id),
      toggleActionClosed: (id, checked) => corrToggleActionClosed(id, checked),
    });
    if (!handled) {
      throw new Error("Correspondence UI bridge did not bind events.");
    }
    S.bound = true;
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
  const corrRoot = q("view-correspondence");
  if (corrRoot && corrRoot.style.display !== "none") init();
})();











