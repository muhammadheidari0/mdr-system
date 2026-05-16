import { formatShamsiDate } from "./persian_datetime";

export interface CorrespondenceStateDeps {
  getElementById: (id: string) => HTMLElement | null;
}

export interface CorrespondencePagerState {
  page: number;
  size: number;
  total: number;
  loading: boolean;
}

export interface CorrespondenceListItem {
  id?: number;
  reference_no?: string | null;
  subject?: string | null;
  issuing_name?: string | null;
  issuing_code?: string | null;
  category_name?: string | null;
  category_code?: string | null;
  department_name?: string | null;
  department_code?: string | null;
  direction?: string | null;
  sender?: string | null;
  recipient?: string | null;
  cc_recipients?: string | null;
  corr_date?: string | null;
  status?: string | null;
  tag_id?: number | null;
  tag_ids?: number[] | null;
  tags?: Array<{ id?: number | null; name?: string | null; color?: string | null }> | null;
  open_actions_count?: number | null;
  attachments_count?: number | null;
}

export interface CorrespondenceActionItem {
  id?: number;
  title?: string | null;
  description?: string | null;
  action_type?: string | null;
  due_date?: string | null;
  status?: string | null;
  is_closed?: boolean | null;
}

export interface CorrespondenceAttachmentItem {
  id?: number;
  file_name?: string | null;
  file_kind?: string | null;
  action_id?: number | null;
  uploaded_at?: string | null;
  detected_mime?: string | null;
  validation_status?: string | null;
  sha256?: string | null;
  mirror_status?: string | null;
  openproject_sync_status?: string | null;
  mirror_updated_at?: string | null;
  is_pinned?: boolean | null;
  preview_supported?: boolean | null;
}

export interface CorrespondenceRelationItem {
  id?: string | number | null;
  target_entity_type?: string | null;
  target_code?: string | null;
  target_title?: string | null;
  target_project_code?: string | null;
  target_status?: string | null;
  relation_type?: string | null;
  notes?: string | null;
  revision?: string | null;
  inferred?: boolean | null;
  direction?: string | null;
}

export interface CorrespondenceCatalogItem {
  code?: string | null;
  name_p?: string | null;
  name_e?: string | null;
}

export interface CorrespondenceRowsState extends CorrespondencePagerState {
  items: CorrespondenceListItem[];
}

export interface CorrespondenceReferenceInput {
  issuingCode?: string | null;
  categoryCode?: string | null;
  direction?: string | null;
  dateValue?: string | null;
}

export interface CorrespondenceStateBridge {
  fillSelect(
    id: string,
    rows: CorrespondenceCatalogItem[] | null | undefined,
    first: string,
    allowEmpty: boolean,
    deps: CorrespondenceStateDeps
  ): boolean;
  buildReferencePreview(input: CorrespondenceReferenceInput): string;
  renderPager(state: CorrespondencePagerState, deps: CorrespondenceStateDeps): boolean;
  renderRows(state: CorrespondenceRowsState, deps: CorrespondenceStateDeps): boolean;
  fillActionOptions(
    actions: CorrespondenceActionItem[] | null | undefined,
    deps: CorrespondenceStateDeps
  ): boolean;
  renderActions(
    actions: CorrespondenceActionItem[] | null | undefined,
    deps: CorrespondenceStateDeps
  ): boolean;
  renderAttachments(
    attachments: CorrespondenceAttachmentItem[] | null | undefined,
    actions: CorrespondenceActionItem[] | null | undefined,
    deps: CorrespondenceStateDeps
  ): boolean;
  renderRelations(
    relations: CorrespondenceRelationItem[] | null | undefined,
    deps: CorrespondenceStateDeps
  ): boolean;
}

function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function dFa(value: unknown): string {
  return formatShamsiDate(value);
}

function nowYyMm(dateValue: unknown): string {
  const date = dateValue ? new Date(`${String(dateValue)}T00:00:00`) : new Date();
  if (Number.isNaN(date.getTime())) return "0000";
  return `${String(date.getFullYear()).slice(-2)}${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function dirCode(value: unknown): "I" | "O" {
  return ["I", "IN", "INBOUND"].includes(String(value || "").toUpperCase()) ? "I" : "O";
}

function dirFa(value: unknown): string {
  return dirCode(value) === "I" ? "وارده" : "صادره";
}

function statusClass(status: unknown): string {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "closed") return "is-closed";
  if (normalized === "overdue") return "is-overdue";
  return "is-open";
}

function kindFa(kind: unknown): string {
  const normalized = normalizeAttachmentKind(kind);
  if (normalized === "letter") return "فایل نامه";
  if (normalized === "original") return "فایل قابل ویرایش";
  return "پیوست";
}

function normalizeAttachmentKind(kind: unknown): string {
  const normalized = String(kind || "").toLowerCase();
  if (normalized === "main") return "letter";
  if (normalized === "inside") return "original";
  if (normalized === "attachments") return "attachment";
  if (normalized === "letter" || normalized === "original" || normalized === "attachment") return normalized;
  return "attachment";
}

function attachmentPreviewUnsupportedTitle(kind: unknown): string {
  const normalized = normalizeAttachmentKind(kind);
  if (normalized === "original") return "فایل قابل ویرایش فقط دانلود می‌شود";
  return "پیش‌نمایش فقط برای فایل نامه یا پیوست PDF/تصویر پشتیبانی می‌شود";
}

function compactCcRecipients(value: unknown): string {
  return String(value || "")
    .replace(/\s*[\r\n;]+\s*/g, "، ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function relationTargetFa(type: unknown): string {
  const normalized = String(type || "").toLowerCase();
  if (normalized === "document") return "مدرک";
  if (normalized === "transmittal") return "ترنسمیتال";
  if (normalized === "meeting_minute") return "صورتجلسه";
  if (normalized === "correspondence") return "مکاتبه";
  return normalized || "-";
}

function relationTypeFa(type: unknown): string {
  const normalized = String(type || "").toLowerCase();
  if (normalized === "references") return "ارجاع";
  if (normalized === "supersedes") return "جایگزین";
  if (normalized === "attachment" || normalized === "attached") return "پیوست";
  if (normalized === "contains_document") return "از روی مدرک";
  return "مرتبط";
}

function storageBadge(label: string, cssClass: string): string {
  return `<span class="storage-badge ${cssClass}">${esc(label)}</span>`;
}

function validationBadge(status: unknown): string {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "valid") return storageBadge("معتبر", "is-valid");
  if (normalized === "warning") return storageBadge("نیازمند بررسی", "is-warning");
  if (normalized === "rejected") return storageBadge("رد شده", "is-rejected");
  if (normalized === "legacy") return storageBadge("قدیمی", "is-legacy");
  return storageBadge("-", "is-legacy");
}

function mirrorBadge(status: unknown): string {
  const normalized = String(status || "").toLowerCase();
  if (["synced", "mirrored"].includes(normalized)) return storageBadge("Drive: synced", "is-synced");
  if (["pending", "queued"].includes(normalized)) return storageBadge("Drive: pending", "is-pending");
  if (normalized === "failed") return storageBadge("Drive: failed", "is-failed");
  if (["disabled", "not_linked"].includes(normalized)) return storageBadge("Drive: disabled", "is-disabled");
  return storageBadge("Drive: -", "is-disabled");
}

function openProjectBadge(status: unknown): string {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "synced") return storageBadge("OpenProject: synced", "is-synced");
  if (normalized === "pending") return storageBadge("OpenProject: pending", "is-pending");
  if (normalized === "failed") return storageBadge("OpenProject: failed", "is-failed");
  if (["disabled", "not_linked"].includes(normalized)) return storageBadge("OpenProject: disabled", "is-disabled");
  return storageBadge("OpenProject: -", "is-disabled");
}

function fillSelect(
  id: string,
  rows: CorrespondenceCatalogItem[] | null | undefined,
  first: string,
  allowEmpty: boolean,
  deps: CorrespondenceStateDeps
): boolean {
  const el = deps.getElementById(id);
  if (!(el instanceof HTMLSelectElement)) return false;

  const previous = String(el.value || "");
  el.innerHTML = "";

  if (allowEmpty) {
    const option = document.createElement("option");
    option.value = "";
    option.innerText = first;
    el.appendChild(option);
  }

  (rows || []).forEach((row) => {
    const code = String(row?.code || "").trim();
    if (!code) return;
    const option = document.createElement("option");
    option.value = code;
    const name = String(row?.name_p || row?.name_e || "").trim();
    option.innerText = name ? `${code} - ${name}` : code;
    el.appendChild(option);
  });

  if (previous) el.value = previous;
  return true;
}

function buildReferencePreview(input: CorrespondenceReferenceInput): string {
  const issuing = String(input.issuingCode || "").toUpperCase() || "COM";
  const category = String(input.categoryCode || "").toUpperCase() || "CO";
  const direction = dirCode(input.direction);
  const period = nowYyMm(input.dateValue);
  return `${issuing}-${category}-${direction}-${period}010`;
}

function renderPager(state: CorrespondencePagerState, deps: CorrespondenceStateDeps): boolean {
  const infoEl = deps.getElementById("corrPagerInfo");
  const prevEl = deps.getElementById("corrPrevBtn");
  const nextEl = deps.getElementById("corrNextBtn");
  if (!(infoEl instanceof HTMLElement)) return false;
  if (!(prevEl instanceof HTMLButtonElement)) return false;
  if (!(nextEl instanceof HTMLButtonElement)) return false;

  const page = Math.max(1, toNumber(state.page, 1));
  const size = Math.max(1, toNumber(state.size, 20));
  const total = Math.max(0, toNumber(state.total, 0));
  const loading = Boolean(state.loading);

  const start = total === 0 ? 0 : (page - 1) * size + 1;
  const end = Math.min(total, page * size);

  infoEl.innerText = `${start}-${end} از ${total}`;
  prevEl.disabled = page <= 1 || loading;
  nextEl.disabled = end >= total || loading;
  return true;
}

function renderRows(state: CorrespondenceRowsState, deps: CorrespondenceStateDeps): boolean {
  const body = deps.getElementById("corrTableBody");
  const empty = deps.getElementById("corrEmpty");
  if (!(body instanceof HTMLElement)) return false;
  if (!(empty instanceof HTMLElement)) return false;

  const items = Array.isArray(state.items) ? state.items : [];
  if (!items.length) {
    body.innerHTML = "";
    empty.style.display = "block";
    renderPager(state, deps);
    return true;
  }

  empty.style.display = "none";
  const offset = (Math.max(1, toNumber(state.page, 1)) - 1) * Math.max(1, toNumber(state.size, 20));
  body.innerHTML = items
    .map((item, index) => {
      const itemId = toNumber(item?.id, 0);
      const ref = esc(item?.reference_no || "-");
      const subject = esc(item?.subject || "-");
      const ccRecipients = compactCcRecipients(item?.cc_recipients);
      const ccHtml = ccRecipients
        ? `<div title="${esc(ccRecipients)}" style="font-size:0.78rem;color:#64748b;margin-top:4px;max-width:380px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">رونوشت: ${esc(ccRecipients)}</div>`
        : "";
      const issuing = esc(item?.issuing_name || item?.issuing_code || "-");
      const category = esc(item?.category_name || item?.category_code || "-");
      const department = esc(item?.department_name || item?.department_code || "-");
      const tags = Array.isArray(item?.tags) ? item.tags : [];
      const tagHtml = tags.length
        ? tags
            .map((tag) => {
              const color = esc(tag?.color || "#2563eb");
              const name = esc(tag?.name || "Tag");
              return `<span class="doc-tag-chip" style="--tag-color:${color}"><span class="doc-tag-dot"></span><span>${name}</span></span>`;
            })
            .join("")
        : '<span class="doc-muted-pill">-</span>';
      const direction = esc(dirFa(item?.direction));
      const corrDate = dFa(item?.corr_date);
      const status = esc(item?.status || "-");
      const openActions = toNumber(item?.open_actions_count, 0);
      const attachments = toNumber(item?.attachments_count, 0);
      return `
      <tr>
        <td>${offset + index + 1}</td><td style="font-family:monospace;">${ref}</td><td>${subject}${ccHtml}</td>
        <td>${issuing}</td><td>${category}</td><td>${department}</td><td>${tagHtml}</td><td>${direction}</td>
        <td>${corrDate}</td><td><span class="corr-status-badge ${statusClass(item?.status)}">${status}</span></td><td>${openActions}</td><td>${attachments}</td>
        <td class="corr-row-actions-cell">
          <div class="archive-row-menu corr-row-menu" data-corr-row-menu>
            <button class="btn-archive-icon archive-row-menu-trigger" type="button" title="عملیات" data-corr-action="toggle-row-menu" aria-expanded="false">
              <span class="material-icons-round" style="font-size:18px;">more_vert</span>
            </button>
            <div class="archive-row-menu-dropdown corr-row-menu-dropdown">
              <button class="archive-row-menu-item" type="button" data-corr-action="open-edit" data-corr-id="${itemId}">
                <span class="material-icons-round">edit</span> ویرایش
              </button>
              <button class="archive-row-menu-item" type="button" data-corr-action="open-workflow" data-corr-id="${itemId}">
                <span class="material-icons-round">assignment</span> اقدامات و پیوست‌ها
              </button>
              <button class="archive-row-menu-item" type="button" data-corr-action="preview-correspondence" data-corr-id="${itemId}">
                <span class="material-icons-round">visibility</span> پیش‌نمایش
              </button>
              <button class="archive-row-menu-item" type="button" data-corr-action="copy-ref" data-corr-ref="${ref}">
                <span class="material-icons-round">content_copy</span> کپی شماره
              </button>
              <button class="archive-row-menu-item text-danger" type="button" data-corr-action="delete-correspondence" data-corr-id="${itemId}">
                <span class="material-icons-round">delete</span> حذف مدرک
              </button>
            </div>
          </div>
        </td>
      </tr>`;
    })
    .join("");
  renderPager(state, deps);
  return true;
}

function fillActionOptions(
  actions: CorrespondenceActionItem[] | null | undefined,
  deps: CorrespondenceStateDeps
): boolean {
  const selectEl = deps.getElementById("corrAttachmentActionInput");
  if (!(selectEl instanceof HTMLSelectElement)) return false;

  const previous = String(selectEl.value || "");
  selectEl.innerHTML = `<option value="">بدون اقدام</option>`;
  (actions || []).forEach((action) => {
    const option = document.createElement("option");
    option.value = String(toNumber(action?.id, 0));
    option.innerText = String(action?.title || action?.description || `#${toNumber(action?.id, 0)}`);
    selectEl.appendChild(option);
  });
  if (previous) selectEl.value = previous;
  return true;
}

function renderActions(
  actions: CorrespondenceActionItem[] | null | undefined,
  deps: CorrespondenceStateDeps
): boolean {
  const body = deps.getElementById("corrActionsBody");
  if (!(body instanceof HTMLElement)) return false;

  const list = Array.isArray(actions) ? actions : [];
  if (!list.length) {
    body.innerHTML = `<tr><td colspan="5" class="corr-empty-row">اقدامی ثبت نشده است.</td></tr>`;
    fillActionOptions(list, deps);
    return true;
  }

  body.innerHTML = list
    .map((action) => {
      const actionId = toNumber(action?.id, 0);
      const title = esc(action?.title || action?.description || "-");
      const actionType = esc(action?.action_type || "-");
      const dueDate = dFa(action?.due_date);
      const status = esc(action?.status || "-");
      const checked = action?.is_closed ? "checked" : "";
      return `<tr><td>${title}</td><td>${actionType}</td><td>${dueDate}</td><td><div class="corr-action-status-cell"><span class="corr-status-badge ${statusClass(action?.status)}">${status}</span><label class="corr-action-check"><input type="checkbox" ${checked} data-corr-action="toggle-action-closed" data-action-id="${actionId}"><span>بسته</span></label></div></td><td><div class="corr-row-actions"><button class="btn-archive-icon" type="button" data-corr-action="edit-action" data-action-id="${actionId}"><span class="material-icons-round">edit</span></button><button class="btn-archive-icon" type="button" data-corr-action="delete-action" data-action-id="${actionId}"><span class="material-icons-round">delete</span></button></div></td></tr>`;
    })
    .join("");
  fillActionOptions(list, deps);
  return true;
}

function renderAttachments(
  attachments: CorrespondenceAttachmentItem[] | null | undefined,
  actions: CorrespondenceActionItem[] | null | undefined,
  deps: CorrespondenceStateDeps
): boolean {
  const body = deps.getElementById("corrAttachmentsBody");
  if (!(body instanceof HTMLElement)) return false;

  const list = Array.isArray(attachments) ? attachments : [];
  if (!list.length) {
    body.innerHTML = `<tr><td colspan="7" class="corr-empty-row">فایلی ثبت نشده است.</td></tr>`;
    return true;
  }

  const actionsById = new Map<number, CorrespondenceActionItem>();
  (actions || []).forEach((action) => {
    actionsById.set(toNumber(action?.id, 0), action);
  });

  body.innerHTML = list
    .map((attachment) => {
      const attachmentId = toNumber(attachment?.id, 0);
      const fileName = esc(attachment?.file_name || "-");
      const normalizedKind = normalizeAttachmentKind(attachment?.file_kind);
      const fileKind = esc(kindFa(attachment?.file_kind));
      const related = actionsById.get(toNumber(attachment?.action_id, 0));
      const relatedTitle = esc(related?.title || "-");
      const uploadedAt = dFa(attachment?.uploaded_at);
      const syncHtml = `<div class="archive-status-stack">${validationBadge(
        attachment?.validation_status
      )}${mirrorBadge(attachment?.mirror_status)}${openProjectBadge(
        attachment?.openproject_sync_status
      )}</div>`;
      const isPinned = Boolean(attachment?.is_pinned);
      const pinIcon = isPinned ? "push_pin" : "keep_off";
      const pinClass = isPinned
        ? "btn-archive-icon archive-pin-btn is-pinned"
        : "btn-archive-icon archive-pin-btn";
      const canPreview =
        Boolean(attachment?.preview_supported) &&
        (normalizedKind === "letter" || normalizedKind === "attachment");
      const previewButton = canPreview
        ? `<button class="btn-archive-icon" type="button" data-corr-action="preview-attachment" data-attachment-id="${attachmentId}" title="پیش‌نمایش"><span class="material-icons-round">visibility</span></button>`
        : `<button class="btn-archive-icon" type="button" data-corr-action="preview-unsupported" title="${esc(attachmentPreviewUnsupportedTitle(attachment?.file_kind))}"><span class="material-icons-round">visibility_off</span></button>`;
      return `<tr><td>${fileName}</td><td>${fileKind}</td><td>${relatedTitle}</td><td>${syncHtml}</td><td>${uploadedAt}</td><td><button class="${pinClass}" type="button" data-corr-action="toggle-attachment-pin" data-attachment-id="${attachmentId}" data-pinned="${isPinned ? "1" : "0"}"><span class="material-icons-round">${pinIcon}</span></button></td><td><div class="corr-row-actions">${previewButton}<button class="btn-archive-icon" type="button" data-corr-action="download-attachment" data-attachment-id="${attachmentId}"><span class="material-icons-round">download</span></button><button class="btn-archive-icon" type="button" data-corr-action="delete-attachment" data-attachment-id="${attachmentId}"><span class="material-icons-round">delete</span></button></div></td></tr>`;
    })
    .join("");
  return true;
}

function renderRelations(
  relations: CorrespondenceRelationItem[] | null | undefined,
  deps: CorrespondenceStateDeps
): boolean {
  const body = deps.getElementById("corrRelationsBody");
  if (!(body instanceof HTMLElement)) return false;

  const list = Array.isArray(relations) ? relations : [];
  if (!list.length) {
    body.innerHTML = `<tr><td colspan="6" class="corr-empty-row">ارتباطی ثبت نشده است.</td></tr>`;
    return true;
  }

  body.innerHTML = list
    .map((relation) => {
      const relationId = esc(relation?.id || "");
      const targetType = esc(relationTargetFa(relation?.target_entity_type));
      const relationType = esc(relationTypeFa(relation?.relation_type));
      const code = esc(relation?.target_code || "-");
      const title = esc(relation?.target_title || relation?.notes || "-");
      const project = esc(relation?.target_project_code || "-");
      const status = esc(relation?.target_status || relation?.revision || "-");
      const inferred = Boolean(relation?.inferred);
      const direction = String(relation?.direction || "").toLowerCase();
      const actions = inferred
        ? `<span class="doc-muted-pill">خودکار</span>`
        : direction === "incoming"
          ? `<span class="doc-muted-pill">ورودی</span>`
        : `<button class="btn-archive-icon" type="button" data-corr-action="delete-relation" data-relation-id="${relationId}"><span class="material-icons-round">link_off</span></button>`;
      return `<tr><td>${targetType}</td><td style="font-family:monospace;">${code}</td><td>${title}</td><td>${project}</td><td><span class="corr-status-badge is-open">${relationType} / ${status}</span></td><td>${actions}</td></tr>`;
    })
    .join("");
  return true;
}

export function createCorrespondenceStateBridge(): CorrespondenceStateBridge {
  return {
    fillSelect,
    buildReferencePreview,
    renderPager,
    renderRows,
    fillActionOptions,
    renderActions,
    renderAttachments,
    renderRelations,
  };
}
