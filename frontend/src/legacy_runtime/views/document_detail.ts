// @ts-nocheck
import {
  addArchiveRevisionFile,
  assignDocumentTag,
  createDocumentComment,
  createDocumentRelation,
  createArchiveFilePublicShare,
  deleteDocument,
  deleteDocumentComment,
  deleteDocumentRelation,
  fetchArchiveFileBlob,
  fetchDocumentPreviewBlob,
  loadArchiveFilePublicShare,
  loadArchiveFormData,
  loadDocumentDetail,
  loadTagsCatalog,
  previewDocumentReclassification,
  reclassifyDocument,
  removeDocumentTag,
  replaceArchiveFile,
  revokeArchiveFilePublicShare,
  updateDocumentComment,
  updateDocumentMetadata,
} from "../../lib/document_detail_data";
import { sanitizeMetadataDraft, validateMetadataPayload } from "../../lib/document_detail_form";
import { activateDocumentDetailTab, renderDocumentDetail } from "../../lib/document_detail_state";

(() => {
  const state = {
    initialized: false,
    bound: false,
    documentId: null,
    detail: null,
    isEditMode: false,
    metadataDraft: {},
    tagCatalog: [],
    archiveFormData: null,
    previewObjectUrl: "",
  };

  function notify(message: string, type = "info") {
    if (typeof (window as any).showToast === "function") {
      (window as any).showToast(message, type);
      return;
    }
    if ((window as any).UI && typeof (window as any).UI[type] === "function") {
      (window as any).UI[type](message);
      return;
    }
    window.alert(message);
  }

  function escHtml(value: unknown): string {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function disposePreviewObjectUrl() {
    if (state.previewObjectUrl) {
      try {
        URL.revokeObjectURL(state.previewObjectUrl);
      } catch (_) {}
      state.previewObjectUrl = "";
    }
  }

  async function downloadBlobFile(fileId: number, fileName = "download") {
    const blob = await fetchArchiveFileBlob(Number(fileId || 0));
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = String(fileName || "download").trim() || "download";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function hydratePreviewBlob() {
    disposePreviewObjectUrl();
    const docId = Number(state.documentId || 0);
    const meta = state.detail?.preview_meta || {};
    if (!docId || !meta?.supported) return;
    const frame = document.querySelector("[data-doc-preview-frame]") as HTMLIFrameElement | null;
    const image = document.querySelector("[data-doc-preview-image]") as HTMLImageElement | null;
    if (!frame && !image) return;
    try {
      const blob = await fetchDocumentPreviewBlob(docId);
      const url = URL.createObjectURL(blob);
      state.previewObjectUrl = url;
      if (frame) frame.src = url;
      if (image) image.src = url;
    } catch (error: any) {
      const target = frame?.parentElement || image?.parentElement || document.getElementById("docDetailPanelPreview");
      if (target) {
        target.innerHTML = `<div class="doc-readonly-note"><span class="material-icons-round">warning</span>${String(error?.message || "Preview failed.")}</div>`;
      }
    }
  }

  function optionList(items: any[], selected: string, codeKey = "code", labelKey = "name") {
    return (Array.isArray(items) ? items : [])
      .map((item) => {
        const code = String(item?.[codeKey] ?? item ?? "").trim();
        if (!code) return "";
        const label = String(item?.[labelKey] || item?.name_e || item?.name_p || code).trim();
        return `<option value="${code}" ${code.toUpperCase() === String(selected || "").toUpperCase() ? "selected" : ""}>${code} - ${label}</option>`;
      })
      .join("");
  }

  async function ensureArchiveFormData() {
    state.archiveFormData = await loadArchiveFormData();
    return state.archiveFormData || {};
  }

  async function openReclassifyModal() {
    if (!state.detail?.capabilities?.can_reclassify || state.detail?.is_deleted) return;
    const data = await ensureArchiveFormData();
    const doc = state.detail?.document || {};
    let overlay = document.getElementById("docReclassifyModal") as HTMLElement | null;
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "docReclassifyModal";
      overlay.className = "am-modal-overlay";
      (document.getElementById("view-document-detail") || document.body).appendChild(overlay);
    }
    overlay.innerHTML = `
      <div class="am-modal-box doc-reclassify-box">
        <div class="doc-panel-header">
          <div>
            <span class="doc-panel-kicker"><span class="material-icons-round">rule_settings</span>اصلاح کدگذاری</span>
            <p>شماره مدرک و عنوان از روی انتخاب‌های دیتابیس دوباره محاسبه می‌شود.</p>
          </div>
        </div>
        <div class="doc-metadata-grid">
          <label class="doc-metadata-field"><span class="doc-metadata-label">پروژه</span><select class="doc-form-control" data-reclass-field="project_code">${optionList(data.projects, doc.project_code)}</select></label>
          <label class="doc-metadata-field"><span class="doc-metadata-label">MDR</span><select class="doc-form-control" data-reclass-field="mdr_code">${optionList(data.mdr_categories, doc.mdr_code)}</select></label>
          <label class="doc-metadata-field"><span class="doc-metadata-label">فاز</span><select class="doc-form-control" data-reclass-field="phase_code">${optionList(data.phases, doc.phase_code)}</select></label>
          <label class="doc-metadata-field"><span class="doc-metadata-label">دیسیپلین</span><select class="doc-form-control" data-reclass-field="discipline_code">${optionList(data.disciplines, doc.discipline_code)}</select></label>
          <label class="doc-metadata-field"><span class="doc-metadata-label">پکیج</span><select class="doc-form-control" data-reclass-field="package_code">${optionList((data.packages || []).filter((p: any) => !doc.discipline_code || String(p?.discipline_code || "").toUpperCase() === String(doc.discipline_code || "").toUpperCase()), doc.package_code)}</select></label>
          <label class="doc-metadata-field"><span class="doc-metadata-label">بلوک</span><select class="doc-form-control" data-reclass-field="block">${optionList((data.blocks || []).filter((b: any) => !doc.project_code || String(b?.project_code || "").toUpperCase() === String(doc.project_code || "").toUpperCase()), doc.block)}</select></label>
          <label class="doc-metadata-field"><span class="doc-metadata-label">سطح</span><select class="doc-form-control" data-reclass-field="level_code">${optionList((data.levels || []).map((code: string) => ({ code, name: code })), doc.level_code)}</select></label>
        </div>
        <div id="docReclassifyPreview" class="doc-readonly-note"><span class="material-icons-round">info</span>برای دیدن نتیجه، پیش‌نمایش را بزنید.</div>
        <div class="archive-modal-actions">
          <button type="button" class="doc-action-btn" data-doc-detail-action="close-reclassify"><span class="material-icons-round">close</span>انصراف</button>
          <button type="button" class="doc-action-btn" data-doc-detail-action="reclassify-preview"><span class="material-icons-round">visibility</span>پیش‌نمایش</button>
          <button type="button" class="doc-action-btn doc-action-primary" data-doc-detail-action="submit-reclassify"><span class="material-icons-round">save</span>ذخیره</button>
        </div>
      </div>
    `;
    overlay.style.display = "flex";
  }

  function closeReclassifyModal() {
    const overlay = document.getElementById("docReclassifyModal") as HTMLElement | null;
    if (overlay) overlay.style.display = "none";
  }

  function defaultShareExpireDate() {
    const day = new Date();
    day.setDate(day.getDate() + 60);
    return day.toISOString().slice(0, 10);
  }

  function renderPublicShareModal(fileId: number, fileName: string, payload: any) {
    let overlay = document.getElementById("docPublicShareModal") as HTMLElement | null;
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "docPublicShareModal";
      overlay.className = "am-modal-overlay";
      (document.getElementById("view-document-detail") || document.body).appendChild(overlay);
    }
    overlay.dataset.fileId = String(fileId || 0);
    overlay.dataset.fileName = String(fileName || "");
    const share = payload?.public_share || null;
    const supported = Boolean(payload?.public_share_supported);
    const status = String(payload?.public_share_status || "").trim();
    const statusMessage =
      status === "not_nextcloud"
        ? "برای این فایل لینک عمومی فقط بعد از ذخیره در Nextcloud فعال می‌شود."
        : status === "mirror_not_ready"
          ? "mirror Nextcloud برای این فایل آماده نیست."
          : status === "missing_remote_path"
            ? "مسیر دقیق فایل در Nextcloud پیدا نشد."
            : "این فایل هنوز در Nextcloud قابل اشتراک‌گذاری نیست.";
    const expireDate = share?.expires_at ? String(share.expires_at).slice(0, 10) : defaultShareExpireDate();
    const password = String(share?.password || "").trim();
    overlay.innerHTML = `
      <div class="am-modal-box doc-public-share-box">
        <div class="doc-panel-header">
          <div>
            <span class="doc-panel-kicker"><span class="material-icons-round">link</span>لینک عمومی Nextcloud</span>
            <p>${escHtml(fileName || "فایل نسخه")}</p>
          </div>
        </div>
        ${
          supported
            ? `
          <div class="doc-metadata-grid">
            <label class="doc-metadata-field"><span class="doc-metadata-label">انقضا</span><input class="doc-form-control" type="date" value="${expireDate}" data-public-share-field="expire_date"></label>
            <label class="doc-metadata-field"><span class="doc-metadata-label">رمز عبور</span><input class="doc-form-control" type="text" placeholder="خالی بماند، طبق تنظیمات Nextcloud عمل می‌شود" data-public-share-field="password"></label>
          </div>
          ${
            share?.url
              ? `<div class="doc-readonly-note doc-public-share-result">
                  <span class="material-icons-round">link</span>
                  <div>
                    <strong>لینک آماده است</strong>
                    <a href="${escHtml(share.url)}" target="_blank" rel="noopener">${escHtml(share.url)}</a>
                    ${password ? `<small>رمز جدید: <code>${escHtml(password)}</code></small>` : ""}
                  </div>
                  <button type="button" class="doc-mini-btn" data-doc-detail-action="copy-public-share-link" data-copy-value="${escHtml(share.url)}"><span class="material-icons-round">content_copy</span>کپی لینک</button>
                  ${password ? `<button type="button" class="doc-mini-btn" data-doc-detail-action="copy-public-share-password" data-copy-value="${escHtml(password)}"><span class="material-icons-round">password</span>کپی رمز</button>` : ""}
                </div>`
              : `<div class="doc-readonly-note"><span class="material-icons-round">info</span>رمز و تاریخ انقضا را تنظیم کنید و لینک را بسازید.</div>`
          }
        `
            : `<div class="doc-readonly-note"><span class="material-icons-round">warning</span>${escHtml(statusMessage)}</div>`
        }
        <div class="archive-modal-actions">
          <button type="button" class="doc-action-btn" data-doc-detail-action="close-public-share"><span class="material-icons-round">close</span>انصراف</button>
          ${
            share?.url && supported
              ? `<button type="button" class="doc-action-btn is-danger" data-doc-detail-action="revoke-public-share"><span class="material-icons-round">link_off</span>حذف لینک</button>`
              : ""
          }
          ${
            supported
              ? `<button type="button" class="doc-action-btn doc-action-primary" data-doc-detail-action="${share?.url ? "renew-public-share" : "create-public-share"}"><span class="material-icons-round">add_link</span>${share?.url ? "ساخت لینک جدید" : "ساخت لینک"}</button>`
              : ""
          }
        </div>
      </div>
    `;
    overlay.style.display = "flex";
  }

  async function openPublicShareModal(fileId: number, fileName = "") {
    const payload = await loadArchiveFilePublicShare(fileId);
    renderPublicShareModal(fileId, fileName, payload);
  }

  function closePublicShareModal() {
    const overlay = document.getElementById("docPublicShareModal") as HTMLElement | null;
    if (overlay) overlay.style.display = "none";
  }

  function collectPublicSharePayload(regenerate = false) {
    const overlay = document.getElementById("docPublicShareModal") as HTMLElement | null;
    const expireEl = overlay?.querySelector('[data-public-share-field="expire_date"]') as HTMLInputElement | null;
    const passwordEl = overlay?.querySelector('[data-public-share-field="password"]') as HTMLInputElement | null;
    return {
      expire_date: String(expireEl?.value || "").trim() || defaultShareExpireDate(),
      password: String(passwordEl?.value || "").trim() || undefined,
      regenerate,
    };
  }

  async function submitPublicShare(regenerate = false) {
    const overlay = document.getElementById("docPublicShareModal") as HTMLElement | null;
    const fileId = Number(overlay?.dataset?.fileId || 0);
    const fileName = String(overlay?.dataset?.fileName || "");
    if (!fileId) return;
    const response = await createArchiveFilePublicShare(fileId, collectPublicSharePayload(regenerate));
    await loadAndRender(Number(state.documentId));
    renderPublicShareModal(fileId, fileName, response);
    notify(regenerate ? "لینک عمومی جدید ساخته شد." : "لینک عمومی ساخته شد.", "success");
  }

  async function revokePublicShare() {
    const overlay = document.getElementById("docPublicShareModal") as HTMLElement | null;
    const fileId = Number(overlay?.dataset?.fileId || 0);
    const fileName = String(overlay?.dataset?.fileName || "");
    if (!fileId) return;
    if (!window.confirm("لینک عمومی حذف شود؟")) return;
    await revokeArchiveFilePublicShare(fileId);
    const fresh = await loadArchiveFilePublicShare(fileId);
    await loadAndRender(Number(state.documentId));
    renderPublicShareModal(fileId, fileName, fresh);
    notify("لینک عمومی حذف شد.", "success");
  }

  async function copyTextToClipboard(value: string) {
    const text = String(value || "").trim();
    if (!text) return;
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const input = document.createElement("textarea");
      input.value = text;
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      input.remove();
    }
    notify("کپی شد.", "success");
  }

  function collectReclassifyPayload() {
    const payload: Record<string, string> = {};
    document.querySelectorAll("[data-reclass-field]").forEach((el: HTMLElement) => {
      const key = String(el.dataset?.reclassField || "").trim();
      if (!key) return;
      payload[key] = String((el as HTMLSelectElement).value || "").trim();
    });
    return payload;
  }

  function refreshReclassifyDependentOptions() {
    const data = state.archiveFormData || {};
    const payload = collectReclassifyPayload();
    const packageSelect = document.querySelector('[data-reclass-field="package_code"]') as HTMLSelectElement | null;
    const blockSelect = document.querySelector('[data-reclass-field="block"]') as HTMLSelectElement | null;
    if (packageSelect) {
      const current = packageSelect.value;
      const rows = (data.packages || []).filter(
        (p: any) => String(p?.discipline_code || "").toUpperCase() === String(payload.discipline_code || "").toUpperCase(),
      );
      packageSelect.innerHTML = optionList(rows, current);
    }
    if (blockSelect) {
      const current = blockSelect.value;
      const rows = (data.blocks || []).filter(
        (b: any) => String(b?.project_code || "").toUpperCase() === String(payload.project_code || "").toUpperCase(),
      );
      blockSelect.innerHTML = optionList(rows, current);
    }
  }

  async function pickAndReplaceFile(fileId: number, status = "") {
    const input = document.createElement("input");
    input.type = "file";
    input.style.display = "none";
    document.body.appendChild(input);
    await new Promise<void>((resolve) => {
      input.addEventListener(
        "change",
        async () => {
          const file = input.files?.[0] || null;
          input.remove();
          if (!file) return resolve();
          try {
            await replaceArchiveFile(fileId, file, status);
            await loadAndRender(Number(state.documentId));
            notify("فایل نسخه جایگزین شد.", "success");
          } catch (error: any) {
            notify(String(error?.message || "خطا در جایگزینی فایل."), "error");
          }
          resolve();
        },
        { once: true },
      );
      input.click();
    });
  }

  async function pickAndAddRevisionFile(revisionId: number, fileKind = "pdf", status = "") {
    const input = document.createElement("input");
    input.type = "file";
    input.style.display = "none";
    const normalizedKind = String(fileKind || "pdf").trim().toLowerCase() === "native" ? "native" : "pdf";
    input.accept =
      normalizedKind === "native"
        ? ".dwg,.dxf,.doc,.docx,.xls,.xlsx,.zip,.ifc"
        : ".pdf,.dwf,.dwfx,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.gif,.webp";
    document.body.appendChild(input);
    await new Promise<void>((resolve) => {
      input.addEventListener(
        "change",
        async () => {
          const file = input.files?.[0] || null;
          input.remove();
          if (!file) return resolve();
          try {
            await addArchiveRevisionFile(revisionId, file, normalizedKind, status);
            await loadAndRender(Number(state.documentId));
            notify("فایل تکمیلی به همین نسخه اضافه شد.", "success");
          } catch (error: any) {
            notify(String(error?.message || "خطا در افزودن فایل تکمیلی."), "error");
          }
          resolve();
        },
        { once: true },
      );
      input.click();
    });
  }

  function readQueryDocumentId(): number {
    const qs = new URLSearchParams(window.location.search || "");
    const id = Number(qs.get("document_id") || 0);
    return Number.isFinite(id) && id > 0 ? id : 0;
  }

  function resolvePendingDocumentId(): number {
    if (typeof (window as any).consumePendingDocumentDetailId === "function") {
      const val = Number((window as any).consumePendingDocumentDetailId() || 0);
      if (Number.isFinite(val) && val > 0) return val;
    }
    const fromQuery = readQueryDocumentId();
    if (fromQuery > 0) return fromQuery;
    const current = Number(state.documentId || 0);
    return Number.isFinite(current) && current > 0 ? current : 0;
  }

  function resolvePendingEditMode(): boolean {
    if (typeof (window as any).consumePendingDocumentDetailEditMode === "function") {
      return Boolean((window as any).consumePendingDocumentDetailEditMode());
    }
    return false;
  }

  function loadDraftFromDetail() {
    const doc = state.detail?.document || {};
    state.metadataDraft = sanitizeMetadataDraft(doc);
  }

  function rerender() {
    if (!state.detail) return;
    renderDocumentDetail(state.detail, state);
    void hydratePreviewBlob();
  }

  async function loadAndRender(forceDocumentId = 0) {
    const targetId = Number(forceDocumentId || state.documentId || 0);
    if (!Number.isFinite(targetId) || targetId <= 0) {
      notify("شناسه سند برای نمایش جزئیات معتبر نیست.", "error");
      return;
    }
    state.documentId = targetId;
    const [payload, tagsCatalog] = await Promise.all([
      loadDocumentDetail(targetId),
      loadTagsCatalog().catch(() => ({ items: [] })),
    ]);
    state.detail = payload || null;
    state.tagCatalog = Array.isArray(tagsCatalog?.items) ? tagsCatalog.items : [];
    if (!state.isEditMode) {
      loadDraftFromDetail();
    }
    rerender();
  }

  function collectMetadataFromDom() {
    const next = { ...(state.metadataDraft || {}) };
    document.querySelectorAll("[data-doc-field]").forEach((el: HTMLElement) => {
      const key = String(el?.dataset?.docField || "").trim();
      if (!key) return;
      next[key] = String((el as HTMLInputElement).value || "").trim();
    });
    state.metadataDraft = sanitizeMetadataDraft(next);
    return state.metadataDraft;
  }

  function findCommentById(nodes: any[], targetId: number): any | null {
    if (!Array.isArray(nodes)) return null;
    for (const node of nodes) {
      if (Number(node?.id || 0) === Number(targetId || 0)) return node;
      const inner = findCommentById(node?.children || [], targetId);
      if (inner) return inner;
    }
    return null;
  }

  async function onAction(action: string, actionEl: HTMLElement) {
    if (!state.documentId) return;

    if (action === "go-back") {
      const params = new URLSearchParams(window.location.search || "");
      params.delete("document_id");
      params.set("view", "edms");
      window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
      if (typeof (window as any).navigateTo === "function") {
        await (window as any).navigateTo("view-edms");
        if (typeof (window as any).openEdmsTab === "function") {
          (window as any).openEdmsTab("archive");
        }
      }
      return;
    }

    if (action === "edit-toggle") {
      if (!state.detail?.capabilities?.can_edit || state.detail?.is_deleted) return;
      state.isEditMode = true;
      loadDraftFromDetail();
      rerender();
      return;
    }

    if (action === "cancel-edit") {
      state.isEditMode = false;
      loadDraftFromDetail();
      rerender();
      return;
    }

    if (action === "save-metadata") {
      const draft = collectMetadataFromDom();
      const result = validateMetadataPayload(draft);
      if (!result.ok) {
        notify(result.errors?.[0] || "اطلاعات برای ذخیره معتبر نیست.", "error");
        return;
      }
      await updateDocumentMetadata(Number(state.documentId), result.payload);
      state.isEditMode = false;
      await loadAndRender(Number(state.documentId));
      notify("متادیتا با موفقیت ذخیره شد.", "success");
      return;
    }

    if (action === "delete-document") {
      if (!state.detail?.capabilities?.can_delete || state.detail?.is_deleted) return;
      if (!window.confirm("حذف نرم این سند انجام شود؟")) return;
      await deleteDocument(Number(state.documentId));
      await loadAndRender(Number(state.documentId));
      notify("سند حذف نرم شد.", "success");
      return;
    }

    if (action === "download-latest") {
      const latest = state.detail?.latest_files?.preview || state.detail?.latest_files?.latest || null;
      const fileId = Number(latest?.id || 0);
      if (fileId <= 0) {
        notify("فایل قابل دانلود پیدا نشد.", "warning");
        return;
      }
      await downloadBlobFile(fileId, String(latest?.name || "download"));
      return;
    }

    if (action === "download-file") {
      const fileId = Number(actionEl?.dataset?.fileId || 0);
      if (!fileId) return;
      await downloadBlobFile(fileId, String(actionEl?.dataset?.fileName || "download"));
      return;
    }

    if (action === "replace-file") {
      const fileId = Number(actionEl?.dataset?.fileId || 0);
      if (!fileId) return;
      await pickAndReplaceFile(fileId, String(actionEl?.dataset?.status || ""));
      return;
    }

    if (action === "add-revision-file") {
      const revisionId = Number(actionEl?.dataset?.revisionId || 0);
      if (!revisionId) return;
      await pickAndAddRevisionFile(
        revisionId,
        String(actionEl?.dataset?.fileKind || "pdf"),
        String(actionEl?.dataset?.status || ""),
      );
      return;
    }

    if (action === "public-share") {
      const fileId = Number(actionEl?.dataset?.fileId || 0);
      if (!fileId) return;
      await openPublicShareModal(fileId, String(actionEl?.dataset?.fileName || ""));
      return;
    }

    if (action === "close-public-share") {
      closePublicShareModal();
      return;
    }

    if (action === "create-public-share") {
      await submitPublicShare(false);
      return;
    }

    if (action === "renew-public-share") {
      await submitPublicShare(true);
      return;
    }

    if (action === "revoke-public-share") {
      await revokePublicShare();
      return;
    }

    if (action === "copy-public-share-link" || action === "copy-public-share-password") {
      await copyTextToClipboard(String(actionEl?.dataset?.copyValue || ""));
      return;
    }

    if (action === "open-reclassify") {
      await openReclassifyModal();
      return;
    }

    if (action === "close-reclassify") {
      closeReclassifyModal();
      return;
    }

    if (action === "reclassify-preview") {
      const response = await previewDocumentReclassification(Number(state.documentId), collectReclassifyPayload());
      const preview = response?.preview || {};
      const box = document.getElementById("docReclassifyPreview");
      if (box) {
        box.innerHTML = `<span class="material-icons-round">fact_check</span><strong>${String(preview?.doc_number || "-")}</strong><br>${String(preview?.doc_title_e || "")}<br>${String(preview?.doc_title_p || "")}`;
      }
      return;
    }

    if (action === "submit-reclassify") {
      if (!window.confirm("اصلاح کدگذاری مدرک ذخیره شود؟")) return;
      await reclassifyDocument(Number(state.documentId), collectReclassifyPayload());
      closeReclassifyModal();
      await loadAndRender(Number(state.documentId));
      notify("کدگذاری مدرک اصلاح شد.", "success");
      return;
    }

    if (action === "new-revision") {
      if (typeof (window as any).navigateTo === "function") {
        await (window as any).navigateTo("view-edms");
        if (typeof (window as any).openEdmsTab === "function") {
          (window as any).openEdmsTab("archive");
        }
        notify("از پنل آرشیو، Revision جدید را آپلود کنید.", "info");
      }
      return;
    }

    if (action === "send-transmittal") {
      const doc = state.detail?.document || {};
      const latestRevision = state.detail?.latest_revision?.revision || "00";
      if (typeof (window as any).setPendingTransmittalDoc === "function") {
        (window as any).setPendingTransmittalDoc({
          doc_number: doc?.doc_number,
          project_code: doc?.project_code,
          discipline_code: doc?.discipline_code,
          revision: latestRevision || "00",
          status: "IFA",
        });
      }
      if (typeof (window as any).navigateTo === "function") {
        await (window as any).navigateTo("view-transmittal");
        setTimeout(() => {
          if (typeof (window as any).showCreateMode === "function") {
            (window as any).showCreateMode();
          }
        }, 0);
      }
      return;
    }

    if (action === "add-comment") {
      const input = document.getElementById("docDetailCommentInput") as HTMLTextAreaElement | null;
      const body = String(input?.value || "").trim();
      if (!body) {
        notify("متن کامنت را وارد کنید.", "warning");
        return;
      }
      await createDocumentComment(Number(state.documentId), body, null);
      if (input) input.value = "";
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "reply-comment") {
      const commentId = Number(actionEl?.dataset?.commentId || 0);
      if (!commentId) return;
      const body = String(window.prompt("پاسخ کامنت را وارد کنید:") || "").trim();
      if (!body) return;
      await createDocumentComment(Number(state.documentId), body, commentId);
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "edit-comment") {
      const commentId = Number(actionEl?.dataset?.commentId || 0);
      if (!commentId) return;
      const target = findCommentById(state.detail?.comments || [], commentId);
      const current = String(target?.body || "").trim();
      const body = String(window.prompt("ویرایش کامنت:", current) || "").trim();
      if (!body) return;
      await updateDocumentComment(Number(state.documentId), commentId, body);
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "delete-comment") {
      const commentId = Number(actionEl?.dataset?.commentId || 0);
      if (!commentId) return;
      if (!window.confirm("کامنت حذف شود؟")) return;
      await deleteDocumentComment(Number(state.documentId), commentId);
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "add-relation") {
      const targetEl = document.getElementById("docDetailRelationTarget") as HTMLInputElement | null;
      const targetTypeEl = document.getElementById("docDetailRelationTargetType") as HTMLSelectElement | null;
      const typeEl = document.getElementById("docDetailRelationType") as HTMLSelectElement | null;
      const notesEl = document.getElementById("docDetailRelationNotes") as HTMLInputElement | null;
      const targetCode = String(targetEl?.value || "").trim();
      const targetType = String(targetTypeEl?.value || "document").trim() || "document";
      const relationType = String(typeEl?.value || "related");
      const notes = String(notesEl?.value || "").trim();
      if (!targetCode) {
        notify("کد مقصد ارتباط را وارد کنید.", "warning");
        return;
      }
      await createDocumentRelation(Number(state.documentId), targetCode, relationType, notes, targetType);
      if (targetEl) targetEl.value = "";
      if (notesEl) notesEl.value = "";
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "remove-relation") {
      const relationId = String(actionEl?.dataset?.relationId || "").trim();
      if (!relationId) return;
      if (!window.confirm("ارتباط حذف شود؟")) return;
      await deleteDocumentRelation(Number(state.documentId), relationId);
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "add-tag") {
      const tagSelect = document.getElementById("docDetailTagSelect") as HTMLSelectElement | null;
      const tagId = Number(tagSelect?.value || 0);
      if (!tagId) {
        notify("تگ را انتخاب کنید.", "warning");
        return;
      }
      await assignDocumentTag(Number(state.documentId), { tag_id: tagId });
      if (tagSelect) tagSelect.value = "";
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "remove-tag") {
      const tagId = Number(actionEl?.dataset?.tagId || 0);
      if (!tagId) return;
      await removeDocumentTag(Number(state.documentId), tagId);
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "open-transmittal") {
      const transmittalId = String(actionEl?.dataset?.transmittalId || "").trim();
      if (!transmittalId) return;
      if (typeof (window as any).navigateTo === "function") {
        await (window as any).navigateTo("view-transmittal");
        setTimeout(async () => {
          if (typeof (window as any).showListMode === "function") {
            (window as any).showListMode();
          }
          if (typeof (window as any).loadTransmittals === "function") {
            await (window as any).loadTransmittals();
          }
          if (typeof (window as any).openTransmittalDetail === "function") {
            await (window as any).openTransmittalDetail(transmittalId);
          }
        }, 0);
      }
      return;
    }
  }

  function bindEvents() {
    if (state.bound) return;
    const root = document.getElementById("view-document-detail");
    if (!root) return;
    state.bound = true;

    root.addEventListener("click", async (event: Event) => {
      const target = (event.target as HTMLElement | null)?.closest?.("[data-doc-detail-action]") as HTMLElement | null;
      if (!target || !root.contains(target)) return;
      const action = String(target.dataset?.docDetailAction || "").trim();
      if (!action) return;
      try {
        await onAction(action, target);
      } catch (error: any) {
        notify(String(error?.message || "خطا در انجام عملیات."), "error");
      }
    });

    root.addEventListener("click", (event: Event) => {
      const tabBtn = (event.target as HTMLElement | null)?.closest?.("[data-doc-detail-tab]") as HTMLElement | null;
      if (!tabBtn || !root.contains(tabBtn)) return;
      const tab = String(tabBtn.dataset?.docDetailTab || "metadata").trim().toLowerCase();
      activateDocumentDetailTab(tab);
    });

    document.addEventListener("change", (event: Event) => {
      const target = (event.target as HTMLElement | null)?.closest?.("[data-reclass-field]") as HTMLElement | null;
      if (!target) return;
      refreshReclassifyDependentOptions();
    });
  }

  async function initDocumentDetailView() {
    bindEvents();
    const root = document.getElementById("view-document-detail");
    if (!root) return;
    const pendingId = resolvePendingDocumentId();
    if (!pendingId) {
      root.innerHTML = '<div class="archive-card" style="padding:16px;">سندی برای نمایش انتخاب نشده است.</div>';
      return;
    }
    const forceEdit = resolvePendingEditMode();
    if (forceEdit) state.isEditMode = true;
    await loadAndRender(pendingId);
    if (state.isEditMode) {
      loadDraftFromDetail();
      rerender();
    }
    state.initialized = true;
  }

  (window as any).initDocumentDetailView = initDocumentDetailView;

  if ((window as any).AppEvents?.on) {
    (window as any).AppEvents.on("view:loaded", ({ viewId, partialName }: any) => {
      if (String(viewId || "").trim() === "view-document-detail" || String(partialName || "").trim() === "document-detail") {
        void initDocumentDetailView();
      }
    });
    (window as any).AppEvents.on("view:activated", ({ viewId }: any) => {
      if (String(viewId || "").trim() === "view-document-detail") {
        void initDocumentDetailView();
      }
    });
  }
})();
