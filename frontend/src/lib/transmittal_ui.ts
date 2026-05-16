export interface TransmittalModeDeps {
  getElementById: (id: string) => HTMLElement | null;
}

export interface TransmittalTemplateActionDeps {
  refreshList: () => Promise<void> | void;
  showCreate: () => Promise<void> | void;
  previewNumber: () => Promise<void> | void;
  showList: () => Promise<void> | void;
  searchDocs: () => Promise<void> | void;
  submitDraft: () => Promise<void> | void;
  submitIssue: () => Promise<void> | void;
  downloadCover?: (id: string) => Promise<void> | void;
  closePrintPreview?: () => Promise<void> | void;
  printPreview?: () => Promise<void> | void;
  downloadPreview?: () => Promise<void> | void;
  detailItem?: (id: string) => Promise<void> | void;
  closeDetail?: () => Promise<void> | void;
  editItem?: (id: string) => Promise<void> | void;
  issueItem?: (id: string) => Promise<void> | void;
  voidItem?: (id: string) => Promise<void> | void;
  addDoc?: (docNumber: string, fileKind?: string) => Promise<void> | void;
  removeDoc?: (index: number) => Promise<void> | void;
}

export interface TransmittalFieldEventDeps {
  refreshNumber: () => Promise<void> | void;
  searchDocs: () => Promise<void> | void;
  updateDocField?: (index: number, field: string, value: unknown) => void;
}

export interface TransmittalUiBridge {
  setMode(mode: string, deps: TransmittalModeDeps): boolean;
  bindTemplateActions(root: HTMLElement | null, deps: TransmittalTemplateActionDeps): boolean;
  bindFieldEvents(root: HTMLElement | null, deps: TransmittalFieldEventDeps): boolean;
}

function normalizeMode(input: unknown): "list" | "create" {
  return String(input || "").trim().toLowerCase() === "create" ? "create" : "list";
}

async function invoke(handler: () => Promise<void> | void): Promise<void> {
  await Promise.resolve(handler());
}

function shouldIgnoreRowClick(target: HTMLElement | null): boolean {
  if (!(target instanceof HTMLElement)) return true;
  return Boolean(
    target.closest(
      "button,a,input,select,textarea,label,[data-tr2-action],[data-tr2-row-menu],.archive-row-menu"
    )
  );
}

function closeTransmittalRowMenus(root: HTMLElement, exceptMenu: HTMLElement | null = null): void {
  root.querySelectorAll<HTMLElement>(".archive-row-menu.is-open[data-tr2-row-menu]").forEach((menu) => {
    if (exceptMenu && menu === exceptMenu) return;
    menu.classList.remove("is-open");
    const trigger = menu.querySelector<HTMLElement>("[data-tr2-action='toggle-row-menu']");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  });
}

function toggleTransmittalRowMenu(root: HTMLElement, triggerEl: HTMLElement): void {
  const menu = triggerEl.closest<HTMLElement>("[data-tr2-row-menu]");
  if (!(menu instanceof HTMLElement)) return;
  const willOpen = !menu.classList.contains("is-open");
  closeTransmittalRowMenus(root, menu);
  menu.classList.toggle("is-open", willOpen);
  triggerEl.setAttribute("aria-expanded", willOpen ? "true" : "false");
}

function setMode(mode: string, deps: TransmittalModeDeps): boolean {
  const normalized = normalizeMode(mode);
  const listEl = deps.getElementById("tr2-list-mode");
  const createEl = deps.getElementById("tr2-create-mode");
  if (!(listEl instanceof HTMLElement) || !(createEl instanceof HTMLElement)) return false;

  const isCreate = normalized === "create";
  listEl.style.display = isCreate ? "none" : "block";
  createEl.style.display = isCreate ? "flex" : "none";
  return true;
}

function bindTemplateActions(root: HTMLElement | null, deps: TransmittalTemplateActionDeps): boolean {
  if (!(root instanceof HTMLElement)) return false;
  if (root.dataset.tr2ActionsBound === "1") return true;

  root.addEventListener("click", async (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-tr2-action]") as HTMLElement | null;
    if (!actionEl || !root.contains(actionEl)) {
      const rowEl = target?.closest("tr[data-transmittal-id]") as HTMLElement | null;
      const rowId = String(rowEl?.getAttribute("data-transmittal-id") || "").trim();
      if (rowEl && root.contains(rowEl) && rowId && deps.detailItem && !shouldIgnoreRowClick(target)) {
        event.preventDefault();
        closeTransmittalRowMenus(root);
        await invoke(() => deps.detailItem?.(rowId));
        return;
      }
      closeTransmittalRowMenus(root);
      return;
    }
    event.preventDefault();

    const action = String(actionEl.getAttribute("data-tr2-action") || "").trim().toLowerCase();
    if (action !== "toggle-row-menu") {
      closeTransmittalRowMenus(root);
    }
    switch (action) {
      case "toggle-row-menu":
        toggleTransmittalRowMenu(root, actionEl);
        break;
      case "refresh-list":
        await invoke(deps.refreshList);
        break;
      case "show-create":
        await invoke(deps.showCreate);
        break;
      case "preview-number":
        await invoke(deps.previewNumber);
        break;
      case "show-list":
        await invoke(deps.showList);
        break;
      case "search-docs":
        await invoke(deps.searchDocs);
        break;
      case "submit-draft":
        await invoke(deps.submitDraft);
        break;
      case "submit-issue":
        await invoke(deps.submitIssue);
        break;
      case "download-cover": {
        const id = String(actionEl.getAttribute("data-id") || "").trim();
        if (id && deps.downloadCover) await invoke(() => deps.downloadCover?.(id));
        break;
      }
      case "close-print-preview":
        if (deps.closePrintPreview) await invoke(deps.closePrintPreview);
        break;
      case "print-preview-print":
        if (deps.printPreview) await invoke(deps.printPreview);
        break;
      case "print-preview-download":
        if (deps.downloadPreview) await invoke(deps.downloadPreview);
        break;
      case "detail-item": {
        const id = String(actionEl.getAttribute("data-id") || "").trim();
        if (id && deps.detailItem) await invoke(() => deps.detailItem?.(id));
        break;
      }
      case "close-detail":
        if (deps.closeDetail) await invoke(deps.closeDetail);
        break;
      case "edit-item": {
        const id = String(actionEl.getAttribute("data-id") || "").trim();
        if (id && deps.editItem) await invoke(() => deps.editItem?.(id));
        break;
      }
      case "issue-item": {
        const id = String(actionEl.getAttribute("data-id") || "").trim();
        if (id && deps.issueItem) await invoke(() => deps.issueItem?.(id));
        break;
      }
      case "void-item": {
        const id = String(actionEl.getAttribute("data-id") || "").trim();
        if (id && deps.voidItem) await invoke(() => deps.voidItem?.(id));
        break;
      }
      case "doc-add": {
        const docNumber = String(actionEl.getAttribute("data-doc-number") || "").trim();
        const fileKind = String(actionEl.getAttribute("data-file-kind") || "").trim();
        if (docNumber && deps.addDoc) await invoke(() => deps.addDoc?.(docNumber, fileKind));
        break;
      }
      case "doc-remove": {
        const index = Number(actionEl.getAttribute("data-index") || -1);
        if (index >= 0 && deps.removeDoc) await invoke(() => deps.removeDoc?.(index));
        break;
      }
      default:
        break;
    }
  });

  root.dataset.tr2ActionsBound = "1";
  return true;
}

function bindFieldEvents(root: HTMLElement | null, deps: TransmittalFieldEventDeps): boolean {
  if (!(root instanceof HTMLElement)) return false;
  if (root.dataset.tr2FieldsBound === "1") return true;

  const projectEl = document.getElementById("tr2-project");
  const disciplineEl = document.getElementById("tr2-discipline");
  const senderEl = document.getElementById("tr2-sender");
  const receiverEl = document.getElementById("tr2-receiver");
  const searchEl = document.getElementById("tr2-doc-search");

  if (projectEl instanceof HTMLInputElement || projectEl instanceof HTMLSelectElement) {
    projectEl.addEventListener("change", async () => {
      await invoke(deps.refreshNumber);
      await invoke(deps.searchDocs);
    });
  }

  if (disciplineEl instanceof HTMLInputElement || disciplineEl instanceof HTMLSelectElement) {
    disciplineEl.addEventListener("change", () => {
      void invoke(deps.searchDocs);
    });
  }

  if (senderEl instanceof HTMLInputElement || senderEl instanceof HTMLSelectElement) {
    senderEl.addEventListener("change", () => {
      void invoke(deps.refreshNumber);
    });
  }

  if (receiverEl instanceof HTMLInputElement || receiverEl instanceof HTMLSelectElement) {
    receiverEl.addEventListener("change", () => {
      void invoke(deps.refreshNumber);
    });
  }

  if (searchEl instanceof HTMLInputElement) {
    searchEl.addEventListener("keydown", (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void invoke(deps.searchDocs);
      }
    });
  }

  root.addEventListener("change", (event) => {
    const target = event.target as HTMLElement | null;
    const actionEl = target?.closest("[data-tr2-action='doc-field-change']") as HTMLElement | null;
    if (!actionEl || !root.contains(actionEl) || !deps.updateDocField) return;

    const index = Number(actionEl.getAttribute("data-index") || -1);
    const field = String(actionEl.getAttribute("data-field") || "").trim();
    if (index < 0 || !field) return;

    let value: unknown = null;
    if (actionEl instanceof HTMLInputElement && actionEl.type === "checkbox") {
      value = actionEl.checked;
    } else if (
      actionEl instanceof HTMLInputElement ||
      actionEl instanceof HTMLSelectElement ||
      actionEl instanceof HTMLTextAreaElement
    ) {
      value = actionEl.value;
    }
    deps.updateDocField(index, field, value);
  });

  root.dataset.tr2FieldsBound = "1";
  return true;
}

export function createTransmittalUiBridge(): TransmittalUiBridge {
  return {
    setMode,
    bindTemplateActions,
    bindFieldEvents,
  };
}
