// @ts-nocheck
import {
  assignDocumentTag,
  createDocumentComment,
  createDocumentRelation,
  deleteDocument,
  deleteDocumentComment,
  deleteDocumentRelation,
  loadDocumentDetail,
  removeDocumentTag,
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
  }

  async function loadAndRender(forceDocumentId = 0) {
    const targetId = Number(forceDocumentId || state.documentId || 0);
    if (!Number.isFinite(targetId) || targetId <= 0) {
      notify("شناسه سند برای نمایش جزئیات معتبر نیست.", "error");
      return;
    }
    state.documentId = targetId;
    const payload = await loadDocumentDetail(targetId);
    state.detail = payload || null;
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
      window.open(`/api/v1/archive/download/${fileId}`, "_blank");
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
      const typeEl = document.getElementById("docDetailRelationType") as HTMLSelectElement | null;
      const notesEl = document.getElementById("docDetailRelationNotes") as HTMLInputElement | null;
      const targetId = Number(targetEl?.value || 0);
      const relationType = String(typeEl?.value || "related");
      const notes = String(notesEl?.value || "").trim();
      if (!targetId) {
        notify("شناسه سند مقصد را وارد کنید.", "warning");
        return;
      }
      await createDocumentRelation(Number(state.documentId), targetId, relationType, notes);
      if (targetEl) targetEl.value = "";
      if (notesEl) notesEl.value = "";
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "remove-relation") {
      const relationId = Number(actionEl?.dataset?.relationId || 0);
      if (!relationId) return;
      if (!window.confirm("ارتباط حذف شود؟")) return;
      await deleteDocumentRelation(Number(state.documentId), relationId);
      await loadAndRender(Number(state.documentId));
      return;
    }

    if (action === "add-tag") {
      const tagInput = document.getElementById("docDetailTagInput") as HTMLInputElement | null;
      const colorInput = document.getElementById("docDetailTagColor") as HTMLInputElement | null;
      const tagName = String(tagInput?.value || "").trim();
      const color = String(colorInput?.value || "").trim();
      if (!tagName) {
        notify("نام تگ را وارد کنید.", "warning");
        return;
      }
      await assignDocumentTag(Number(state.documentId), { tag_name: tagName, color });
      if (tagInput) tagInput.value = "";
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
        setTimeout(() => {
          if (typeof (window as any).showListMode === "function") {
            (window as any).showListMode();
          }
          if (typeof (window as any).loadTransmittals === "function") {
            (window as any).loadTransmittals();
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
