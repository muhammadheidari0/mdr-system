// @ts-nocheck

function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmtDate(value: unknown): string {
  if (!value) return "-";
  try {
    if (typeof (window as any).formatShamsiDateTime === "function") {
      return String((window as any).formatShamsiDateTime(value));
    }
  } catch (_) {}
  return String(value || "-");
}

function setText(id: string, value: unknown): void {
  const el = document.getElementById(id);
  if (el) el.textContent = String(value ?? "");
}

function toCount(value: unknown): number {
  const next = Number(value || 0);
  return Number.isFinite(next) && next >= 0 ? next : 0;
}

function actionLabel(action: unknown): string {
  const key = String(action || "").trim();
  const labels: Record<string, string> = {
    created: "ایجاد مدرک",
    metadata_updated: "ویرایش اطلاعات",
    revision_uploaded: "آپلود نسخه",
    deleted: "حذف مدرک",
    comment_added: "ثبت کامنت",
    comment_updated: "ویرایش کامنت",
    comment_deleted: "حذف کامنت",
    relation_added: "افزودن ارتباط",
    relation_removed: "حذف ارتباط",
    revision_file_added: "افزودن فایل تکمیلی",
    tag_added: "افزودن تگ",
    tag_removed: "حذف تگ",
    transmittal_sent: "ارسال ترنسمیتال",
  };
  return labels[key] || key || "-";
}

function actionIcon(action: unknown): string {
  const key = String(action || "").trim();
  const icons: Record<string, string> = {
    created: "add_circle",
    metadata_updated: "edit_note",
    revision_uploaded: "upload_file",
    deleted: "delete",
    comment_added: "chat_bubble",
    comment_updated: "mode_comment",
    comment_deleted: "speaker_notes_off",
    relation_added: "account_tree",
    relation_removed: "link_off",
    revision_file_added: "note_add",
    tag_added: "sell",
    tag_removed: "label_off",
    transmittal_sent: "send",
  };
  return icons[key] || "radio_button_checked";
}

function relationTypeLabel(type: unknown): string {
  const labels: Record<string, string> = {
    related: "مرتبط",
    supersedes: "جایگزین می‌کند",
    references: "ارجاع می‌دهد",
    parent: "والد",
    child: "فرزند",
  };
  return labels[String(type || "")] || String(type || "مرتبط");
}

function relationTargetLabel(type: unknown): string {
  const key = String(type || "document").trim().toLowerCase();
  const labels: Record<string, string> = {
    document: "مدرک",
    correspondence: "مکاتبه",
    meeting_minute: "صورتجلسه",
    rfi: "RFI",
    ncr: "NCR",
    tech: "فنی/TECH",
    comm_item: "فرم",
    site_log: "گزارش کارگاهی",
    permit_qc: "Permit QC",
  };
  return labels[key] || key || "مدرک";
}

function publicShareUnavailableMessage(file: any): string {
  const status = String(file?.public_share_status || "").trim();
  if (status === "not_nextcloud") {
    return "برای این فایل لینک عمومی فقط بعد از ذخیره در Nextcloud فعال می‌شود.";
  }
  if (status === "mirror_not_ready") {
    return "mirror Nextcloud برای این فایل آماده نیست.";
  }
  if (status === "missing_remote_path") {
    return "مسیر دقیق فایل در Nextcloud پیدا نشد.";
  }
  return "این فایل هنوز در Nextcloud قابل اشتراک‌گذاری نیست.";
}

function publicShareButton(file: any, capabilities: any, isDeleted: boolean): string {
  if (!capabilities?.can_share_public || isDeleted) return "";
  const fileId = Number(file?.id || 0);
  if (!fileId) return "";
  const supported = Boolean(file?.public_share_supported);
  const active = Boolean(file?.public_share?.url);
  const title = supported ? (active ? "مدیریت لینک عمومی" : "ساخت لینک عمومی") : publicShareUnavailableMessage(file);
  const disabled = supported ? "" : "disabled aria-disabled=\"true\"";
  return `<button type="button" class="doc-mini-btn ${supported ? "" : "is-disabled"}" data-doc-detail-action="public-share" data-file-id="${fileId}" data-file-name="${esc(file?.name || file?.filename || "")}" title="${esc(title)}" ${disabled}>
    <span class="material-icons-round">${active ? "link" : "add_link"}</span>لینک عمومی
  </button>`;
}

function revisionSupplementButtons(row: any, capabilities: any, isDeleted: boolean): string {
  if (!capabilities?.can_replace_files || isDeleted) return "";
  const revisionId = Number(row?.revision_id || 0);
  if (!revisionId) return "";
  const files = Array.isArray(row?.files) ? row.files : [];
  const hasPdf = files.some((file: any) => String(file?.file_kind || "pdf").toLowerCase() !== "native");
  const hasNative = files.some((file: any) => String(file?.file_kind || "").toLowerCase() === "native");
  const status = esc(row?.status || "");
  const actions: string[] = [];
  if (!hasPdf) {
    actions.push(`<button type="button" class="doc-mini-btn" data-doc-detail-action="add-revision-file" data-revision-id="${revisionId}" data-file-kind="pdf" data-status="${status}">
      <span class="material-icons-round">picture_as_pdf</span>افزودن PDF/خروجی
    </button>`);
  }
  if (!hasNative) {
    actions.push(`<button type="button" class="doc-mini-btn" data-doc-detail-action="add-revision-file" data-revision-id="${revisionId}" data-file-kind="native" data-status="${status}">
      <span class="material-icons-round">description</span>افزودن Native
    </button>`);
  }
  return actions.length ? `<div class="doc-file-supplement-actions">${actions.join("")}</div>` : "";
}

function commentRevisionLabel(row: any): string {
  const explicit = String(row?.revision_label || "").trim();
  if (explicit) return explicit;
  const revisionId = Number(row?.revision_id || 0);
  if (!revisionId) return "کل مدرک";
  const revision = String(row?.revision || "").trim() || "-";
  const status = String(row?.revision_status || row?.status || "").trim();
  return status ? `Rev ${revision} | ${status}` : `Rev ${revision}`;
}

function documentRevisionRows(detail: any): any[] {
  return (Array.isArray(detail?.revisions) ? detail.revisions : []).filter(
    (row: any) => Number(row?.revision_id || 0) > 0,
  );
}

function commentRevisionSelectOptions(detail: any, selectedValue: unknown, includeAll = false): string {
  const selected = String(selectedValue ?? "").trim();
  const options: Array<{ value: string; label: string }> = includeAll ? [{ value: "", label: "همه" }] : [];
  options.push({ value: "0", label: "کل مدرک" });
  documentRevisionRows(detail).forEach((row: any) => {
    options.push({ value: String(Number(row?.revision_id || 0)), label: commentRevisionLabel(row) });
  });
  return options
    .map((option) => `<option value="${esc(option.value)}" ${option.value === selected ? "selected" : ""}>${esc(option.label)}</option>`)
    .join("");
}

function defaultCommentRevisionValue(detail: any): string {
  const latestId = Number(detail?.latest_revision?.revision_id || 0);
  if (latestId > 0) return String(latestId);
  const firstRevision = documentRevisionRows(detail)[0];
  const firstRevisionId = Number(firstRevision?.revision_id || 0);
  return firstRevisionId > 0 ? String(firstRevisionId) : "0";
}

function filterCommentNodes(nodes: any[], selectedValue: unknown): any[] {
  const selected = String(selectedValue ?? "").trim();
  if (!selected) return nodes;
  const targetRevisionId = Number(selected || 0);
  const output: any[] = [];
  (Array.isArray(nodes) ? nodes : []).forEach((node: any) => {
    const children = filterCommentNodes(Array.isArray(node?.children) ? node.children : [], selected);
    const nodeRevisionId = Number(node?.revision_id || 0);
    const matches = targetRevisionId <= 0 ? nodeRevisionId <= 0 : nodeRevisionId === targetRevisionId;
    if (matches) {
      output.push({ ...node, children });
      return;
    }
    output.push(...children);
  });
  return output;
}

function statCard(icon: string, label: string, value: unknown, caption = ""): string {
  return `
    <div class="doc-stat-card">
      <span class="material-icons-round">${esc(icon)}</span>
      <div>
        <strong>${esc(value || "-")}</strong>
        <span>${esc(label)}</span>
        ${caption ? `<small>${esc(caption)}</small>` : ""}
      </div>
    </div>
  `;
}

function emptyState(icon: string, title: string, body: string, actionHtml = ""): string {
  return `
    <div class="doc-empty-state">
      <span class="material-icons-round">${esc(icon)}</span>
      <strong>${esc(title)}</strong>
      <p>${esc(body)}</p>
      ${actionHtml}
    </div>
  `;
}

function panelHeader(icon: string, title: string, subtitle = ""): string {
  return `
    <div class="doc-panel-header">
      <div>
        <span class="doc-panel-kicker"><span class="material-icons-round">${esc(icon)}</span>${esc(title)}</span>
        ${subtitle ? `<p>${esc(subtitle)}</p>` : ""}
      </div>
    </div>
  `;
}

function metadataFieldRow(
  label: string,
  key: string,
  value: unknown,
  isEdit = false,
  options: { wide?: boolean; multiline?: boolean; locked?: boolean } = {},
): string {
  const lockedKeys = new Set(["doc_title_e", "doc_title_p", "phase_code", "package_code", "block", "level_code"]);
  if (lockedKeys.has(String(key || ""))) {
    isEdit = false;
    options = { ...options, locked: true };
  }
  const classes = ["doc-metadata-field"];
  if (options.wide) classes.push("is-wide");
  if (options.locked) classes.push("is-locked");

  if (!isEdit) {
    return `
      <div class="${classes.join(" ")}">
        <div class="doc-metadata-label">${esc(label)}</div>
        <div class="doc-metadata-value">${esc(value || "-")}</div>
      </div>
    `;
  }

  const control = options.multiline
    ? `<textarea id="docDetailField_${esc(key)}" class="doc-form-control" rows="4" data-doc-field="${esc(key)}">${esc(value || "")}</textarea>`
    : `<input id="docDetailField_${esc(key)}" class="doc-form-control" data-doc-field="${esc(key)}" value="${esc(value || "")}">`;

  return `
    <div class="${classes.join(" ")}">
      <label class="doc-metadata-label" for="docDetailField_${esc(key)}">${esc(label)}</label>
      ${control}
    </div>
  `;
}

function renderCommentNode(node: any, depth = 0): string {
  const isDeleted = Boolean(node?.is_deleted);
  const bodyText = isDeleted ? "این کامنت حذف شده است." : String(node?.body || "");
  const margin = Math.min(Math.max(0, Number(depth || 0)) * 18, 54);
  const children = Array.isArray(node?.children) ? node.children : [];
  const author = String(node?.author_name || node?.author_email || "کاربر نامشخص").trim();
  const revisionLabel = commentRevisionLabel(node);
  const isEdited = !isDeleted && Boolean(node?.updated_at);
  const initials = author
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "U";

  return `
    <div class="doc-comment-thread" style="margin-left:${margin}px;">
      <div class="doc-comment-item">
        <div class="doc-comment-avatar">${esc(initials)}</div>
        <div class="doc-comment-content">
          <div class="doc-comment-head">
            <div class="doc-comment-meta">
              <strong>${esc(author)}</strong>
              <span>${esc(fmtDate(node?.created_at))}</span>
              <span class="doc-comment-revision-badge">${esc(revisionLabel)}</span>
              ${isEdited ? '<span class="doc-comment-edited-badge">ویرایش شده</span>' : ""}
            </div>
          </div>
          <div class="doc-comment-body ${isDeleted ? "is-deleted" : ""}">${esc(bodyText)}</div>
          <div class="doc-comment-actions">
            <button type="button" class="doc-mini-btn" data-doc-detail-action="reply-comment" data-comment-id="${Number(node?.id || 0)}">
              <span class="material-icons-round">reply</span> پاسخ
            </button>
            ${
              isDeleted
                ? ""
                : `<button type="button" class="doc-mini-btn" data-doc-detail-action="edit-comment" data-comment-id="${Number(node?.id || 0)}">
                    <span class="material-icons-round">edit</span> ویرایش
                  </button>`
            }
            ${
              isDeleted
                ? ""
                : `<button type="button" class="doc-mini-btn is-danger" data-doc-detail-action="delete-comment" data-comment-id="${Number(node?.id || 0)}">
                    <span class="material-icons-round">delete</span> حذف
                  </button>`
            }
          </div>
        </div>
      </div>
      ${children.map((child: any) => renderCommentNode(child, depth + 1)).join("")}
    </div>
  `;
}

function renderTags(tags: any[], isReadOnly: boolean, tagCatalog: any[] = []): string {
  const rows = Array.isArray(tags) ? tags : [];
  const assignedIds = new Set(
    rows
      .map((row) => Number(row?.tag?.id || row?.tag_id || 0))
      .filter((value) => Number.isFinite(value) && value > 0),
  );
  const chips = rows
    .map((row) => {
      const tag = row?.tag || {};
      const color = String(tag?.color || "").trim() || "#2563eb";
      return `
        <span class="doc-tag-chip" style="--tag-color:${esc(color)}">
          <span class="doc-tag-dot"></span>
          <span>${esc(tag?.name || "Tag")}</span>
          ${
            isReadOnly
              ? ""
              : `<button type="button" data-doc-detail-action="remove-tag" data-tag-id="${Number(tag?.id || 0)}" title="حذف تگ">&times;</button>`
          }
        </span>
      `;
    })
    .join("");

  const addBox = isReadOnly
    ? ""
    : `
      <div class="doc-tag-add">
        <select id="docDetailTagSelect" class="doc-form-control">
          <option value="">انتخاب تگ</option>
          ${tagCatalog
            .filter((tag) => !assignedIds.has(Number(tag?.id || 0)))
            .map(
              (tag) =>
                `<option value="${Number(tag?.id || 0)}">${esc(tag?.name || `Tag #${Number(tag?.id || 0)}`)}</option>`,
            )
            .join("")}
        </select>
        <button type="button" class="doc-mini-btn" data-doc-detail-action="add-tag">
          <span class="material-icons-round">add</span> افزودن
        </button>
      </div>
    `;

  return `
    <div class="doc-tags-wrap">
      <div class="doc-tags-list">
        ${chips || '<span class="doc-muted-pill">تگی ثبت نشده</span>'}
      </div>
      ${addBox}
    </div>
  `;
}

function relationCard(row: any, canManage: boolean, removable = false): string {
  const counterpart = row?.counterpart || {};
  const targetType = row?.target_entity_type || counterpart?.entity_type || "document";
  const title = counterpart?.title || counterpart?.doc_title_e || counterpart?.doc_title_p || counterpart?.subject || "";
  return `
    <div class="doc-relation-card">
      <div>
        <strong>${esc(counterpart?.doc_number || counterpart?.code || row?.target_code || "-")}</strong>
        <span>${esc(relationTargetLabel(targetType))} | ${esc(relationTypeLabel(row?.relation_type || "related"))}</span>
      </div>
      ${title ? `<p>${esc(title)}</p>` : ""}
      ${row?.notes ? `<p>${esc(row.notes)}</p>` : ""}
      ${
        canManage && removable
          ? `<button type="button" class="doc-mini-btn is-danger" data-doc-detail-action="remove-relation" data-relation-id="${esc(row?.id || "")}">
              <span class="material-icons-round">link_off</span> حذف
            </button>`
          : ""
      }
    </div>
  `;
}

export function renderDocumentDetail(detail: any, state: any) {
  const doc = detail?.document || {};
  const counts = detail?.counts || {};
  const capabilities = detail?.capabilities || {};
  const latestRevision = detail?.latest_revision || {};
  const latestFile = detail?.latest_files?.preview || detail?.latest_files?.latest || {};
  const isDeleted = Boolean(detail?.is_deleted);
  const canWrite = !isDeleted;
  const isEditMode = Boolean(state?.isEditMode && canWrite && capabilities?.can_edit);
  const draft = state?.metadataDraft || {};
  const revisionValue = latestRevision?.revision || latestFile?.revision || "-";
  const statusValue = latestRevision?.status || latestFile?.status || (isDeleted ? "حذف شده" : "فعال");
  const titleValue = doc?.doc_title_e || doc?.doc_title_p || doc?.subject || "بدون عنوان";
  const summary = `نسخه ${revisionValue} | ${statusValue} | آخرین بروزرسانی ${fmtDate(doc?.updated_at || doc?.created_at)}`;

  setText("docDetailDocNumber", doc?.doc_number || "-");
  setText("docDetailSummary", summary);
  setText("docDetailTitle", titleValue);
  setText("docDetailSubject", doc?.subject || doc?.doc_title_p || "موضوعی برای این مدرک ثبت نشده است.");
  setText("docDetailTabRevisionsCount", toCount(counts?.revisions));
  setText("docDetailTabCommentsCount", toCount(counts?.comments));
  setText("docDetailTabActivityCount", toCount(counts?.activities));

  const statusBadge = document.getElementById("docDetailStatusBadge");
  if (statusBadge) {
    statusBadge.className = `doc-status-badge ${isDeleted ? "is-deleted" : "is-active"}`;
    statusBadge.innerHTML = `<span class="material-icons-round">${isDeleted ? "lock" : "check_circle"}</span>${isDeleted ? "حذف شده" : "فعال"}`;
  }

  const deletedBanner = document.getElementById("docDetailDeletedBanner");
  if (deletedBanner) deletedBanner.style.display = isDeleted ? "block" : "none";

  const quickStats = document.getElementById("docDetailQuickStats");
  if (quickStats) {
    quickStats.innerHTML = `
      ${statCard("history", "آخرین نسخه", revisionValue, String(statusValue || ""))}
      ${statCard("attach_file", "آخرین فایل", latestFile?.name || latestFile?.filename || "بدون فایل", latestFile?.file_kind || "")}
      ${statCard("forum", "کامنت‌ها", toCount(counts?.comments))}
      ${statCard("timeline", "فعالیت‌ها", toCount(counts?.activities))}
    `;
  }

  const tagsRoot = document.getElementById("docDetailTags");
  if (tagsRoot) {
    tagsRoot.innerHTML = renderTags(
      detail?.tags || [],
      isDeleted || !capabilities?.can_manage_tags,
      Array.isArray(state?.tagCatalog) ? state.tagCatalog : [],
    );
  }

  const metadataRoot = document.getElementById("docDetailPanelMetadata");
  if (metadataRoot) {
    const value = (key: string) => {
      const locked = new Set(["doc_title_e", "doc_title_p", "phase_code", "package_code", "block", "level_code"]);
      return isEditMode && !locked.has(String(key || "")) ? draft?.[key] : doc?.[key];
    };
    metadataRoot.innerHTML = `
      ${panelHeader("badge", "اطلاعات مدرک", isEditMode ? "فیلدهای قابل ویرایش مدرک را اصلاح کنید." : "شناسه‌های قفل‌شده برای رهگیری نمایش داده می‌شوند.")}
      ${
        isEditMode
          ? `
        <div class="doc-edit-bar">
          <div>
            <strong>در حال ویرایش اطلاعات</strong>
            <span>شماره مدرک، پروژه، دیسیپلین و کد MDR قابل تغییر نیستند.</span>
          </div>
          <div class="doc-edit-actions">
            <button type="button" class="doc-action-btn doc-action-primary" data-doc-detail-action="save-metadata">
              <span class="material-icons-round">save</span> ذخیره
            </button>
            <button type="button" class="doc-action-btn" data-doc-detail-action="cancel-edit">
              <span class="material-icons-round">close</span> انصراف
            </button>
          </div>
        </div>`
          : ""
      }
      <div class="doc-metadata-section">
        <h4>شناسه مدرک</h4>
        <div class="doc-metadata-grid">
          ${metadataFieldRow("شماره مدرک", "doc_number", doc?.doc_number, false, { locked: true })}
          ${metadataFieldRow("پروژه", "project_code", doc?.project_code, false, { locked: true })}
          ${metadataFieldRow("دیسیپلین", "discipline_code", doc?.discipline_code, false, { locked: true })}
          ${metadataFieldRow("کد MDR", "mdr_code", doc?.mdr_code, false, { locked: true })}
        </div>
      </div>
      <div class="doc-metadata-section">
        <h4>اطلاعات قابل ویرایش</h4>
        <div class="doc-metadata-grid">
          ${metadataFieldRow("عنوان انگلیسی", "doc_title_e", value("doc_title_e"), isEditMode, { wide: true })}
          ${metadataFieldRow("عنوان فارسی", "doc_title_p", value("doc_title_p"), isEditMode, { wide: true })}
          ${metadataFieldRow("موضوع", "subject", value("subject"), isEditMode, { wide: true })}
          ${metadataFieldRow("فاز", "phase_code", value("phase_code"), isEditMode)}
          ${metadataFieldRow("پکیج", "package_code", value("package_code"), isEditMode)}
          ${metadataFieldRow("بلوک", "block", value("block"), isEditMode)}
          ${metadataFieldRow("سطح", "level_code", value("level_code"), isEditMode)}
          ${metadataFieldRow("یادداشت", "notes", value("notes"), isEditMode, { wide: true, multiline: true })}
        </div>
      </div>
      <div class="doc-metadata-section">
        <h4>سوابق</h4>
        <div class="doc-metadata-grid">
          ${metadataFieldRow("ایجاد شده", "created_at", fmtDate(doc?.created_at), false)}
          ${metadataFieldRow("بروزرسانی", "updated_at", fmtDate(doc?.updated_at), false)}
          ${metadataFieldRow("ویرایش توسط", "updated_by_name", doc?.updated_by_name || "-", false)}
          ${metadataFieldRow("حذف توسط", "deleted_by_name", doc?.deleted_by_name || "-", false)}
        </div>
      </div>
    `;
  }

  const revisionsRoot = document.getElementById("docDetailPanelRevisions");
  if (revisionsRoot) {
    const revisions = Array.isArray(detail?.revisions) ? detail.revisions : [];
    revisionsRoot.innerHTML = `
      ${panelHeader("history", "تاریخچه نسخه‌ها", "فایل‌های هر نسخه را دانلود کنید و مسیر تغییرات را ببینید.")}
      ${
        revisions.length
          ? `
        <div class="doc-table-wrap">
          <table class="archive-table doc-detail-table">
            <thead>
              <tr>
                <th>نسخه</th>
                <th>وضعیت</th>
                <th>تاریخ ایجاد</th>
                <th>فایل‌ها</th>
              </tr>
            </thead>
            <tbody>
              ${revisions
                .map(
                  (row: any) => `
                <tr>
                  <td><strong>${esc(row?.revision || "-")}</strong></td>
                  <td><span class="doc-muted-pill">${esc(row?.status || "-")}</span></td>
                  <td>${esc(fmtDate(row?.created_at))}</td>
                  <td>
                    <div class="doc-file-list">
                      ${(Array.isArray(row?.files) ? row.files : [])
                        .map(
                          (file: any) =>
                            `<button type="button" class="doc-mini-btn" data-doc-detail-action="download-file" data-file-id="${Number(file?.id || 0)}" data-file-name="${esc(file?.name || file?.filename || "download")}">
                              <span class="material-icons-round">download</span>${esc(file?.name || file?.filename || "دانلود")}
                            </button>
                            ${
                              capabilities?.can_replace_files && !isDeleted
                                ? `<button type="button" class="doc-mini-btn" data-doc-detail-action="replace-file" data-file-id="${Number(file?.id || 0)}" data-status="${esc(file?.status || row?.status || "")}">
                                    <span class="material-icons-round">published_with_changes</span> جایگزینی
                                  </button>`
                                : ""
                            }
                            ${publicShareButton(file, capabilities, isDeleted)}`,
                        )
                        .join("") || '<span class="text-muted">فایلی ثبت نشده</span>'}
                      ${revisionSupplementButtons(row, capabilities, isDeleted)}
                    </div>
                  </td>
                </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>`
          : emptyState("history", "نسخه‌ای ثبت نشده", "بعد از آپلود فایل، تاریخچه نسخه‌ها اینجا نمایش داده می‌شود.")
      }
    `;
  }

  const previewRoot = document.getElementById("docDetailPanelPreview");
  if (previewRoot) {
    const meta = detail?.preview_meta || {};
    const mime = String(meta?.mime_type || meta?.detected_mime || "").toLowerCase();
    const latest = detail?.latest_files?.latest || {};
    const latestId = Number(latest?.id || latestFile?.id || 0);
    const downloadAction =
      latestId > 0
        ? `<button type="button" class="doc-action-btn doc-action-primary" data-doc-detail-action="download-file" data-file-id="${latestId}" data-file-name="${esc(latest?.name || latestFile?.name || "download")}">
            <span class="material-icons-round">download</span> دانلود فایل
          </button>`
        : "";

    if (meta?.supported && mime.includes("pdf")) {
      previewRoot.innerHTML = `
        ${panelHeader("visibility", "پیش‌نمایش", "PDF و فایل‌های تصویری پشتیبانی می‌شوند؛ آخرین فایل قابل پیش‌نمایش نمایش داده می‌شود.")}
        <div class="doc-preview-toolbar">${downloadAction}</div>
        <iframe class="doc-preview-frame" data-doc-preview-frame title="preview"></iframe>
      `;
    } else if (meta?.supported && mime.startsWith("image/")) {
      previewRoot.innerHTML = `
        ${panelHeader("image", "پیش‌نمایش", "این فایل تصویری است و مستقیم در صفحه نمایش داده می‌شود.")}
        <div class="doc-preview-toolbar">${downloadAction}</div>
        <div class="doc-preview-image-wrap">
          <img class="doc-preview-image" data-doc-preview-image alt="پیش‌نمایش فایل">
        </div>
      `;
    } else {
      previewRoot.innerHTML = `
        ${panelHeader("visibility_off", "پیش‌نمایش", "فقط PDF و تصویر در مرورگر قابل نمایش هستند.")}
        ${emptyState("insert_drive_file", "پیش‌نمایش در دسترس نیست", "برای بررسی این نوع فایل، آخرین فایل را دانلود کنید.", downloadAction)}
      `;
    }
  }

  const commentsRoot = document.getElementById("docDetailPanelComments");
  if (commentsRoot) {
    const comments = Array.isArray(detail?.comments) ? detail.comments : [];
    const selectedCommentFilter = String(state?.commentRevisionFilter ?? "").trim();
    const filteredComments = filterCommentNodes(comments, selectedCommentFilter);
    const composerRevisionValue = defaultCommentRevisionValue(detail);
    commentsRoot.innerHTML = `
      ${panelHeader("forum", "کامنت‌ها", "گفتگوهای مرتبط با همین مدرک را اینجا نگه دارید.")}
      <div class="doc-comments-toolbar">
        <label class="doc-comment-filter-wrap" for="docDetailCommentRevisionFilter">
          <span>نمایش</span>
          <select id="docDetailCommentRevisionFilter" class="doc-form-control" data-doc-comment-filter>
            ${commentRevisionSelectOptions(detail, selectedCommentFilter, true)}
          </select>
        </label>
        <button type="button" class="doc-action-btn" data-doc-detail-action="open-comments-print-preview">
          <span class="material-icons-round">print</span> چاپ کامنت‌ها
        </button>
      </div>
      ${
        isDeleted
          ? '<div class="doc-readonly-note"><span class="material-icons-round">lock</span>این مدرک حذف شده و فقط خواندنی است.</div>'
          : `
        <div class="doc-comments-editor">
          <textarea id="docDetailCommentInput" class="doc-form-control" rows="5" placeholder="متن کامنت را وارد کنید..."></textarea>
          <div class="doc-comments-editor-side">
            <label class="doc-comment-filter-wrap" for="docDetailCommentRevisionInput">
              <span>مربوط به</span>
              <select id="docDetailCommentRevisionInput" class="doc-form-control">
                ${commentRevisionSelectOptions(detail, composerRevisionValue, false)}
              </select>
            </label>
            <button type="button" class="doc-action-btn doc-action-primary" data-doc-detail-action="add-comment">
              <span class="material-icons-round">add_comment</span> ثبت کامنت
            </button>
          </div>
        </div>`
      }
      <div class="doc-comments-list">
        ${filteredComments.length ? filteredComments.map((node: any) => renderCommentNode(node, 0)).join("") : emptyState("chat_bubble_outline", "کامنتی ثبت نشده", "برای این انتخاب هنوز کامنتی وجود ندارد.")}
      </div>
    `;
  }

  const activityRoot = document.getElementById("docDetailPanelActivity");
  if (activityRoot) {
    const activityRows = Array.isArray(detail?.activities) ? detail.activities : [];
    activityRoot.innerHTML = `
      ${panelHeader("timeline", "فعالیت‌ها", "ردیف زمانی عملیات انجام‌شده روی این مدرک.")}
      <div class="doc-activity-timeline">
        ${
          activityRows.length
            ? activityRows
                .map(
                  (row: any) => `
            <div class="doc-activity-item">
              <span class="doc-activity-icon material-icons-round">${esc(actionIcon(row?.action))}</span>
              <div>
                <strong>${esc(actionLabel(row?.action))}</strong>
                <span>${esc(row?.actor_name || row?.actor_email || "-")} | ${esc(fmtDate(row?.created_at))}</span>
                ${row?.detail ? `<p>${esc(row.detail)}</p>` : ""}
              </div>
            </div>`,
                )
                .join("")
            : emptyState("timeline", "فعالیتی ثبت نشده", "عملیات بعدی این مدرک اینجا ثبت می‌شود.")
        }
      </div>
    `;
  }

  const transmittalsRoot = document.getElementById("docDetailPanelTransmittals");
  if (transmittalsRoot) {
    const rows = Array.isArray(detail?.transmittals) ? detail.transmittals : [];
    transmittalsRoot.innerHTML = `
      ${panelHeader("send", "ترنسمیتال‌ها", "ترنسمیتال‌های مرتبط بر اساس شماره مدرک نمایش داده می‌شوند.")}
      ${
        rows.length
          ? `
        <div class="doc-table-wrap">
          <table class="archive-table doc-detail-table">
            <thead>
              <tr>
                <th>شماره</th>
                <th>وضعیت</th>
                <th>تاریخ ایجاد</th>
                <th>عملیات</th>
              </tr>
            </thead>
            <tbody>
              ${rows
                .map(
                  (row: any) => `
                <tr>
                  <td><strong>${esc(row?.transmittal_no || row?.id || "-")}</strong></td>
                  <td><span class="doc-muted-pill">${esc(row?.status || "-")}</span></td>
                  <td>${esc(fmtDate(row?.created_at))}</td>
                  <td>
                    <button type="button" class="doc-mini-btn" data-doc-detail-action="open-transmittal" data-transmittal-id="${esc(row?.id || "")}">
                      <span class="material-icons-round">open_in_new</span> باز کردن
                    </button>
                  </td>
                </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>`
          : emptyState("outbox", "ترنسمیتالی ثبت نشده", "برای این مدرک می‌توانید از دکمه ارسال ترنسمیتال استفاده کنید.")
      }
    `;
  }

  const relationsRoot = document.getElementById("docDetailPanelRelations");
  if (relationsRoot) {
    const outgoing = Array.isArray(detail?.relations?.outgoing) ? detail.relations.outgoing : [];
    const incoming = Array.isArray(detail?.relations?.incoming) ? detail.relations.incoming : [];
    const canManageRelations = Boolean(capabilities?.can_manage_relations) && !isDeleted;
    relationsRoot.innerHTML = `
      ${panelHeader("account_tree", "ارتباطات", "این مدرک را به مدرک، مکاتبه، صورتجلسه یا فرم مرتبط وصل کنید.")}
      ${
        canManageRelations
          ? `
        <div class="doc-relations-add">
          <div class="doc-relation-inputs">
            <input id="docDetailRelationTarget" class="doc-form-control" placeholder="کد مدرک / شماره مکاتبه / کد صورتجلسه / شماره فرم">
            <select id="docDetailRelationTargetType" class="doc-form-control">
              <option value="document">مدرک</option>
              <option value="correspondence">مکاتبه</option>
              <option value="meeting_minute">صورتجلسه</option>
              <option value="rfi">RFI</option>
              <option value="ncr">NCR</option>
              <option value="tech">فنی/TECH</option>
              <option value="site_log">گزارش کارگاهی</option>
              <option value="permit_qc">Permit QC</option>
            </select>
            <select id="docDetailRelationType" class="doc-form-control">
              <option value="related">مرتبط</option>
              <option value="supersedes">جایگزین می‌کند</option>
              <option value="references">ارجاع می‌دهد</option>
              <option value="parent">والد</option>
              <option value="child">فرزند</option>
            </select>
            <input id="docDetailRelationNotes" class="doc-form-control" placeholder="یادداشت اختیاری">
          </div>
          <button type="button" class="doc-action-btn doc-action-primary" data-doc-detail-action="add-relation">
            <span class="material-icons-round">add_link</span> افزودن ارتباط
          </button>
        </div>`
          : ""
      }
      <div class="doc-relations-grid">
        <section>
          <h4><span class="material-icons-round">call_made</span> ارتباطات خروجی</h4>
          ${outgoing.length ? outgoing.map((row: any) => relationCard(row, canManageRelations, true)).join("") : emptyState("call_made", "ارتباط خروجی ثبت نشده", "ارتباطاتی که از این مدرک ساخته شوند اینجا دیده می‌شوند.")}
        </section>
        <section>
          <h4><span class="material-icons-round">call_received</span> ارتباطات ورودی</h4>
          ${incoming.length ? incoming.map((row: any) => relationCard(row, false, false)).join("") : emptyState("call_received", "ارتباط ورودی ثبت نشده", "مدارکی که به این مدرک اشاره کنند اینجا دیده می‌شوند.")}
        </section>
      </div>
    `;
  }

  const editToggleBtn = document.querySelector('[data-doc-detail-action="edit-toggle"]') as HTMLButtonElement | null;
  if (editToggleBtn) {
    editToggleBtn.disabled = !capabilities?.can_edit || isDeleted;
  }
  const reclassifyBtn = document.querySelector('[data-doc-detail-action="open-reclassify"]') as HTMLButtonElement | null;
  if (reclassifyBtn) {
    reclassifyBtn.disabled = !capabilities?.can_reclassify || isDeleted;
    reclassifyBtn.style.display = capabilities?.can_reclassify && !isDeleted ? "" : "none";
  }
  const deleteBtn = document.querySelector('[data-doc-detail-action="delete-document"]') as HTMLButtonElement | null;
  if (deleteBtn) {
    deleteBtn.disabled = !capabilities?.can_delete || isDeleted;
  }
}

export function activateDocumentDetailTab(tabName: string) {
  const target = String(tabName || "metadata").trim().toLowerCase();
  document.querySelectorAll("[data-doc-detail-tab]").forEach((el) => {
    const isActive = String((el as HTMLElement).dataset.docDetailTab || "") === target;
    el.classList.toggle("active", isActive);
  });
  document.querySelectorAll("[data-doc-detail-panel]").forEach((el) => {
    const isActive = String((el as HTMLElement).dataset.docDetailPanel || "") === target;
    (el as HTMLElement).style.display = isActive ? "block" : "none";
    el.classList.toggle("active", isActive);
  });
}
