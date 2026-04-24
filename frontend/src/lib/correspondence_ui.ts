export interface CorrespondenceUiDeps {
  debouncedSearch: () => Promise<void> | void;
  applyFilters: (reset?: boolean) => Promise<void> | void;
  changePageSize: (value: string) => Promise<void> | void;
  save: (event: Event) => Promise<void> | void;
  updateReferencePreview: () => Promise<void> | void;
  syncProjectFromIssuing: () => Promise<void> | void;
  openCreate: () => Promise<void> | void;
  resetFilters: () => Promise<void> | void;
  refresh: () => Promise<void> | void;
  prevPage: () => Promise<void> | void;
  nextPage: () => Promise<void> | void;
  closeModal: () => Promise<void> | void;
  submitAction: () => Promise<void> | void;
  clearActionEditor: () => Promise<void> | void;
  uploadAttachment: () => Promise<void> | void;
  openEdit: (id: number) => Promise<void> | void;
  openWorkflow: (id: number) => Promise<void> | void;
  previewCorrespondence: (id: number) => Promise<void> | void;
  deleteCorrespondence: (id: number) => Promise<void> | void;
  copyRef: (value: string) => Promise<void> | void;
  editAction: (id: number) => Promise<void> | void;
  deleteAction: (id: number) => Promise<void> | void;
  downloadAttachment: (id: number) => Promise<void> | void;
  deleteAttachment: (id: number) => Promise<void> | void;
  toggleAttachmentPin: (id: number, isPinned: boolean) => Promise<void> | void;
  toggleActionClosed: (id: number, checked: boolean) => Promise<void> | void;
}

export interface CorrespondenceUiBridge {
  bindEvents(root: HTMLElement | null, deps: CorrespondenceUiDeps): boolean;
}

const FILTER_IDS = [
  "corrIssuingFilter",
  "corrCategoryFilter",
  "corrDirectionFilter",
  "corrStatusFilter",
  "corrDateFromFilter",
  "corrDateToFilter",
] as const;

const REFRESH_IDS = ["corrCategoryInput", "corrDirectionInput", "corrDateInput"] as const;

async function invoke(handler: () => Promise<void> | void): Promise<void> {
  await Promise.resolve(handler());
}

function toInt(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function closeRowMenus(root: HTMLElement): void {
  root.querySelectorAll("[data-corr-row-menu].is-open").forEach((menu) => {
    menu.classList.remove("is-open");
    const trigger = menu.querySelector("[data-corr-action='toggle-row-menu']");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  });
}

function toggleRowMenu(root: HTMLElement, trigger: HTMLElement): void {
  const menu = trigger.closest("[data-corr-row-menu]");
  if (!(menu instanceof HTMLElement)) return;
  const shouldOpen = !menu.classList.contains("is-open");
  closeRowMenus(root);
  if (shouldOpen) {
    menu.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
  }
}

function bindEvents(root: HTMLElement | null, deps: CorrespondenceUiDeps): boolean {
  if (!(root instanceof HTMLElement)) return false;
  if (root.dataset.corrEventsBound === "1") return true;

  const searchInput = document.getElementById("corrSearchInput");
  if (searchInput instanceof HTMLInputElement) {
    searchInput.addEventListener("keyup", () => {
      void invoke(deps.debouncedSearch);
    });
  }

  FILTER_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement) {
      el.addEventListener("change", () => {
        void invoke(() => deps.applyFilters(true));
      });
    }
  });

  const pageSize = document.getElementById("corrPageSize");
  if (pageSize instanceof HTMLInputElement || pageSize instanceof HTMLSelectElement) {
    pageSize.addEventListener("change", (event) => {
      const target = event.target as HTMLInputElement | HTMLSelectElement | null;
      void invoke(() => deps.changePageSize(String(target?.value || "")));
    });
  }

  const form = document.getElementById("corrForm");
  if (form instanceof HTMLFormElement) {
    form.addEventListener("submit", (event) => {
      void invoke(() => deps.save(event));
    });
  }

  const refInput = document.getElementById("corrReferenceInput");
  if (refInput instanceof HTMLInputElement) {
    refInput.addEventListener("input", () => {
      void invoke(deps.updateReferencePreview);
    });
  }

  const issuingInput = document.getElementById("corrIssuingInput");
  if (issuingInput instanceof HTMLInputElement || issuingInput instanceof HTMLSelectElement) {
    issuingInput.addEventListener("change", () => {
      void invoke(async () => {
        await deps.syncProjectFromIssuing();
        await deps.updateReferencePreview();
      });
    });
  }

  REFRESH_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement) {
      el.addEventListener("change", () => {
        void invoke(deps.updateReferencePreview);
      });
    }
  });

  root.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-corr-action]") as HTMLElement | null;
    if (!actionEl || !root.contains(actionEl)) return;

    const action = String(actionEl.getAttribute("data-corr-action") || "").trim();
    if (action && action !== "toggle-row-menu") {
      closeRowMenus(root);
    }
    switch (action) {
      case "toggle-row-menu":
        toggleRowMenu(root, actionEl);
        break;
      case "open-create":
        void invoke(deps.openCreate);
        break;
      case "reset-filters":
        void invoke(deps.resetFilters);
        break;
      case "refresh":
        void invoke(deps.refresh);
        break;
      case "prev-page":
        void invoke(deps.prevPage);
        break;
      case "next-page":
        void invoke(deps.nextPage);
        break;
      case "close-modal":
        void invoke(deps.closeModal);
        break;
      case "submit-action":
        void invoke(deps.submitAction);
        break;
      case "clear-action-editor":
        void invoke(deps.clearActionEditor);
        break;
      case "upload-attachment":
        void invoke(deps.uploadAttachment);
        break;
      case "open-edit":
        void invoke(() => deps.openEdit(toInt(actionEl.getAttribute("data-corr-id"))));
        break;
      case "open-workflow":
        void invoke(() => deps.openWorkflow(toInt(actionEl.getAttribute("data-corr-id"))));
        break;
      case "preview-correspondence":
        void invoke(() => deps.previewCorrespondence(toInt(actionEl.getAttribute("data-corr-id"))));
        break;
      case "delete-correspondence":
        void invoke(() => deps.deleteCorrespondence(toInt(actionEl.getAttribute("data-corr-id"))));
        break;
      case "copy-ref":
        void invoke(() => deps.copyRef(String(actionEl.getAttribute("data-corr-ref") || "")));
        break;
      case "edit-action":
        void invoke(() => deps.editAction(toInt(actionEl.getAttribute("data-action-id"))));
        break;
      case "delete-action":
        void invoke(() => deps.deleteAction(toInt(actionEl.getAttribute("data-action-id"))));
        break;
      case "download-attachment":
        void invoke(() => deps.downloadAttachment(toInt(actionEl.getAttribute("data-attachment-id"))));
        break;
      case "delete-attachment":
        void invoke(() => deps.deleteAttachment(toInt(actionEl.getAttribute("data-attachment-id"))));
        break;
      case "toggle-attachment-pin":
        void invoke(() =>
          deps.toggleAttachmentPin(
            toInt(actionEl.getAttribute("data-attachment-id")),
            String(actionEl.getAttribute("data-pinned") || "0") === "1"
          )
        );
        break;
      default:
        break;
    }
  });

  root.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null;
    if (!target?.closest("[data-corr-row-menu]")) {
      closeRowMenus(root);
    }
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target as Node | null)) {
      closeRowMenus(root);
    }
  });

  root.addEventListener("change", (event) => {
    const target = event.target as HTMLElement | null;
    if (!(target instanceof HTMLInputElement)) return;
    if (!target.matches("input[data-corr-action='toggle-action-closed']")) return;
    void invoke(() =>
      deps.toggleActionClosed(toInt(target.getAttribute("data-action-id")), Boolean(target.checked))
    );
  });

  const modal = document.getElementById("corrModal");
  if (modal instanceof HTMLElement) {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        void invoke(deps.closeModal);
      }
    });
  }

  root.dataset.corrEventsBound = "1";
  return true;
}

export function createCorrespondenceUiBridge(): CorrespondenceUiBridge {
  return {
    bindEvents,
  };
}
