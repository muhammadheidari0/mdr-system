// @ts-nocheck
import { formatShamsiDate } from "./persian_datetime";

export interface WorkInstructionsUiDeps {
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
  canEdit: () => boolean;
  showToast: (message: string, type?: string) => void;
  cache: Record<string, unknown>;
}

export interface WorkInstructionsUiBridge {
  onTabOpened(moduleKey: string, tabKey: string, deps: WorkInstructionsUiDeps): Promise<boolean>;
  initModule(moduleKey: string, deps: WorkInstructionsUiDeps): Promise<boolean>;
}

const state: Record<string, any> = {};

function normalize(v: unknown): string { return String(v ?? "").trim().toLowerCase(); }
function upper(v: unknown): string { return String(v ?? "").trim().toUpperCase(); }
function keyOf(m: unknown, t: unknown): string { return `${normalize(m)}-${normalize(t)}`; }
function esc(v: unknown): string {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
function asArray(v: unknown): any[] { return Array.isArray(v) ? v : []; }
function q(root: HTMLElement, selector: string): HTMLElement | null { return root.querySelector(selector); }
function value(root: HTMLElement, selector: string): string {
  const el = q(root, selector);
  if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
    return String(el.value || "").trim();
  }
  return "";
}
function selectedText(root: HTMLElement, selector: string): string {
  const el = q(root, selector);
  if (el instanceof HTMLSelectElement && el.selectedOptions.length) return el.selectedOptions[0].textContent || "";
  return "";
}
function getUserOrgId(deps: WorkInstructionsUiDeps): number | null {
  const current = (deps.cache?.currentUser || (window as any).CURRENT_USER || {}) as Record<string, unknown>;
  const parsed = Number(current.organization_id || current.org_id || 0);
  return parsed > 0 ? parsed : null;
}
function optionHtml(rows: any[], valueKey: string, labelKey: string, selected?: unknown, empty = "انتخاب..."): string {
  const sel = String(selected ?? "");
  return `<option value="">${esc(empty)}</option>` + rows.map((row) => {
    const value = String(row?.[valueKey] ?? "");
    const label = row?.[labelKey] || row?.name || row?.label || value;
    return `<option value="${esc(value)}"${value === sel ? " selected" : ""}>${esc(label)}</option>`;
  }).join("");
}
async function fetchJson(deps: WorkInstructionsUiDeps, url: string, init?: RequestInit): Promise<any> {
  const resp = await deps.fetch(url, init);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data?.ok === false) {
    throw new Error(data?.detail || data?.message || `Request failed: ${resp.status}`);
  }
  return data;
}
function rootFor(moduleKey: string, tabKey: string): HTMLElement | null {
  return document.querySelector(`.work-instructions-root[data-module="${normalize(moduleKey)}"][data-tab="${normalize(tabKey)}"]`);
}
async function ensureCatalog(key: string, deps: WorkInstructionsUiDeps): Promise<any> {
  state[key] ||= {};
  if (!state[key].catalog) {
    state[key].catalog = await fetchJson(deps, "/api/v1/work-instructions/catalog");
  }
  return state[key].catalog;
}
function statusLabel(catalog: any, code: unknown): string {
  const target = upper(code);
  const row = asArray(catalog?.workflow_statuses).find((item) => upper(item.code) === target);
  return row?.label || target || "-";
}
function priorityLabel(code: unknown): string {
  const map: Record<string, string> = { LOW: "کم", NORMAL: "عادی", HIGH: "بالا", URGENT: "فوری" };
  return map[upper(code)] || String(code || "-");
}
function relationTypeLabel(code: unknown): string {
  const map: Record<string, string> = {
    CAUSED_BY: "ناشی از",
    RESULTS_IN: "منجر به",
    REFERENCES: "ارجاع",
    SUPERSEDES: "جایگزین",
    LINKED_TO_CLAIM: "مرتبط با ادعا",
  };
  return map[upper(code)] || String(code || "-");
}
function targetTypeLabel(code: unknown): string {
  return normalize(code) === "comm_item" ? "RFI/NCR" : "دستورکار";
}
function entityTitle(entity: any): string {
  return [entity?.no, entity?.title].filter(Boolean).join(" - ") || "-";
}
function renderReferenceLinks(row: any): string {
  const refs = [
    ["مدرک", row.document_no],
    ["ترنسمیتال", row.transmittal_no],
    ["فعالیت", row.activity_code],
    ["WBS", row.wbs_code],
  ].filter(([, value]) => String(value || "").trim());
  return refs.length
    ? refs.map(([label, val]) => `<span class="wi-ref-pill"><b>${esc(label)}</b>${esc(val)}</span>`).join("")
    : `<span class="muted">ارجاعی ثبت نشده است.</span>`;
}
function renderRelationCards(relations: any[], direction: "outgoing" | "incoming", editable: boolean): string {
  return relations.map((rel) => {
    const entity = direction === "outgoing" ? rel.to : rel.from;
    return `
      <div class="wi-relation-card">
        <div>
          <strong>${esc(entityTitle(entity))}</strong>
          <span>${esc(targetTypeLabel(entity?.type))} · ${esc(relationTypeLabel(rel.relation_type))} · ${direction === "incoming" ? "ورودی" : "خروجی"}</span>
          ${rel.note ? `<p>${esc(rel.note)}</p>` : ""}
        </div>
        ${editable ? `<button type="button" class="btn btn-sm" data-wi-delete-relation="${esc(rel.id)}"><span class="material-icons-round">link_off</span></button>` : ""}
      </div>
    `;
  }).join("");
}
function renderKpis(root: HTMLElement, rows: any[]): void {
  const total = rows.length;
  const drafts = rows.filter((r) => upper(r.status_code) === "DRAFT").length;
  const submitted = rows.filter((r) => ["SUBMITTED", "IN_REVIEW"].includes(upper(r.status_code))).length;
  const overdue = rows.filter((r) => r.is_overdue).length;
  const html = [
    ["کل دستورکار", total],
    ["پیش‌نویس", drafts],
    ["در جریان", submitted],
    ["معوق", overdue],
  ].map(([label, val]) => `
    <div class="edms-info-card">
      <div class="edms-info-card-value">${esc(val)}</div>
      <div class="edms-info-card-label">${esc(label)}</div>
    </div>
  `).join("");
  q(root, "[data-wi-kpis]")!.innerHTML = html;
}
function renderRows(root: HTMLElement, key: string, catalog: any): void {
  const rows = asArray(state[key]?.rows);
  renderKpis(root, rows);
  q(root, "[data-wi-tbody]")!.innerHTML = rows.map((row) => `
    <tr class="wi-row" data-id="${esc(row.id)}">
      <td><input type="checkbox" data-stop-row></td>
      <td class="mono">${esc(row.instruction_no)}</td>
      <td>${esc(row.title)}</td>
      <td>${esc(row.project_code)}</td>
      <td>${esc(row.discipline_code)}</td>
      <td>${esc(row.recipient_org_name || "-")}</td>
      <td><span class="status-pill">${esc(statusLabel(catalog, row.status_code))}</span></td>
      <td>${esc(priorityLabel(row.priority))}</td>
      <td>${esc(formatShamsiDate(row.response_due_date) || "-")}</td>
      <td>
        <button type="button" class="btn btn-sm" data-wi-action="detail" data-id="${esc(row.id)}" title="مشاهده">
          <span class="material-icons-round">visibility</span>
        </button>
        ${upper(row.status_code) === "DRAFT" && !row.is_legacy_readonly ? `
          <button type="button" class="btn btn-sm" data-wi-action="edit" data-id="${esc(row.id)}" title="ویرایش">
            <span class="material-icons-round">edit</span>
          </button>
        ` : ""}
      </td>
    </tr>
  `).join("") || `<tr><td colspan="10" class="muted">دستورکاری ثبت نشده است.</td></tr>`;
}
async function loadRows(root: HTMLElement, key: string, deps: WorkInstructionsUiDeps): Promise<void> {
  const catalog = await ensureCatalog(key, deps);
  const params = new URLSearchParams();
  const search = value(root, "[data-wi-filter='search']");
  const project = value(root, "[data-wi-filter='project']");
  const discipline = value(root, "[data-wi-filter='discipline']");
  const status = value(root, "[data-wi-filter='status']");
  if (search) params.set("search", search);
  if (project) params.set("project_code", project);
  if (discipline) params.set("discipline_code", discipline);
  if (status) params.set("status_code", status);
  params.set("limit", "200");
  const data = await fetchJson(deps, `/api/v1/work-instructions/list?${params}`);
  state[key].rows = asArray(data.data);
  renderRows(root, key, catalog);
}
function renderShell(root: HTMLElement, key: string, deps: WorkInstructionsUiDeps, catalog: any): void {
  if (root.dataset.wiReady === "1") return;
  root.dataset.wiReady = "1";
  root.innerHTML = `
    <div class="module-card module-card-flat wi-card">
      <div class="module-toolbar">
        <div>
          <h3 class="module-title"><span class="material-icons-round">edit_note</span> دستورکار</h3>
          <p class="module-subtitle">دستورکارهای مستقل با پیوست، کامنت و گردش وضعیت.</p>
        </div>
        <div class="module-actions">
          <button type="button" class="btn btn-primary" data-wi-action="new">
            <span class="material-icons-round">add</span> دستورکار جدید
          </button>
          <button type="button" class="btn" data-wi-action="reload">
            <span class="material-icons-round">refresh</span> به‌روزرسانی
          </button>
        </div>
      </div>
      <div class="module-filter-bar compact wi-filter-grid">
        <input class="form-control wi-filter-search" data-wi-filter="search" placeholder="جستجو در شماره، عنوان، شرح...">
        <select class="form-control" data-wi-filter="project">${optionHtml(catalog.projects, "code", "name", "", "همه پروژه‌ها")}</select>
        <select class="form-control" data-wi-filter="discipline">${optionHtml(catalog.disciplines, "code", "name", "", "همه دیسیپلین‌ها")}</select>
        <select class="form-control" data-wi-filter="status">
          <option value="">همه وضعیت‌ها</option>
          ${asArray(catalog.workflow_statuses).map((row) => `<option value="${esc(row.code)}">${esc(row.label || row.code)}</option>`).join("")}
        </select>
        <button type="button" class="btn btn-primary" data-wi-action="run">
          <span class="material-icons-round">manage_search</span> اجرا
        </button>
      </div>
      <div class="edms-info-grid wi-kpi-grid" data-wi-kpis></div>
      <div class="table-responsive wi-table-wrap">
        <table class="edms-table compact wi-table">
          <thead>
            <tr>
              <th></th><th>شماره</th><th>عنوان</th><th>پروژه</th><th>دیسیپلین</th><th>گیرنده</th><th>وضعیت</th><th>اولویت</th><th>سررسید</th><th>عملیات</th>
            </tr>
          </thead>
          <tbody data-wi-tbody><tr><td colspan="10" class="muted">در حال بارگذاری...</td></tr></tbody>
        </table>
      </div>
    </div>
    <div class="wi-editor-host" data-wi-editor-host hidden></div>
    <aside class="wi-drawer" data-wi-drawer hidden></aside>
  `;
  root.addEventListener("click", (ev) => {
    const target = ev.target as HTMLElement;
    if (target.closest("[data-stop-row]")) return;
    const actionEl = target.closest("[data-wi-action]") as HTMLElement | null;
    if (actionEl) {
      const action = actionEl.dataset.wiAction || "";
      const id = Number(actionEl.dataset.id || 0);
      void handleAction(root, key, deps, action, id);
      return;
    }
    const row = target.closest(".wi-row") as HTMLElement | null;
    if (row?.dataset.id) void openDrawer(root, key, deps, Number(row.dataset.id));
  });
  root.addEventListener("change", (ev) => {
    const target = ev.target as HTMLElement;
    if (target.matches("[data-wi-filter]")) void loadRows(root, key, deps);
  });
}
async function handleAction(root: HTMLElement, key: string, deps: WorkInstructionsUiDeps, action: string, id: number): Promise<void> {
  try {
    if (action === "reload" || action === "run") await loadRows(root, key, deps);
    if (action === "new") await openEditor(root, key, deps, null);
    if (action === "detail" && id) await openDrawer(root, key, deps, id);
    if (action === "edit" && id) {
      const data = await fetchJson(deps, `/api/v1/work-instructions/${id}`);
      await openEditor(root, key, deps, data.data);
    }
    if (action === "close-drawer") closeDrawer(root);
    if (action === "print" && id) await printInstruction(deps, id);
    if (action === "issue" && id) await transition(root, key, deps, id, "SUBMITTED");
    if (action === "close" && id) await transition(root, key, deps, id, "CLOSED");
  } catch (error) {
    deps.showToast(error?.message || "عملیات دستورکار ناموفق بود.", "error");
  }
}
async function transition(root: HTMLElement, key: string, deps: WorkInstructionsUiDeps, id: number, status: string): Promise<void> {
  await fetchJson(deps, `/api/v1/work-instructions/${id}/transition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to_status_code: status }),
  });
  deps.showToast("وضعیت دستورکار به‌روزرسانی شد.", "success");
  await loadRows(root, key, deps);
  await openDrawer(root, key, deps, id);
}
function closeDrawer(root: HTMLElement): void {
  const drawer = q(root, "[data-wi-drawer]");
  if (drawer) {
    drawer.hidden = true;
    drawer.innerHTML = "";
  }
}
async function openDrawer(root: HTMLElement, key: string, deps: WorkInstructionsUiDeps, id: number): Promise<void> {
  const catalog = await ensureCatalog(key, deps);
  const data = await fetchJson(deps, `/api/v1/work-instructions/${id}`);
  const comments = await fetchJson(deps, `/api/v1/work-instructions/${id}/comments`).catch(() => ({ data: [] }));
  const attachments = await fetchJson(deps, `/api/v1/work-instructions/${id}/attachments`).catch(() => ({ data: [] }));
  const relations = await fetchJson(deps, `/api/v1/work-instructions/${id}/relations`).catch(() => ({ outgoing: [], incoming: [] }));
  const row = data.data || {};
  const editableRelations = !row.is_legacy_readonly && deps.canEdit();
  const drawer = q(root, "[data-wi-drawer]")!;
  drawer.hidden = false;
  drawer.innerHTML = `
    <div class="wi-drawer-backdrop" data-wi-action="close-drawer"></div>
    <section class="wi-drawer-panel" role="dialog" aria-modal="true" aria-label="جزئیات دستورکار">
      <header class="wi-drawer-header">
        <button type="button" class="btn btn-icon" data-wi-action="close-drawer" title="بستن"><span class="material-icons-round">close</span></button>
        <div>
          <h3>${esc(row.instruction_no)}</h3>
          <p>${esc(statusLabel(catalog, row.status_code))} · ${esc(priorityLabel(row.priority))}</p>
        </div>
      </header>
      <div class="wi-drawer-actions">
        ${upper(row.status_code) === "DRAFT" && !row.is_legacy_readonly ? `<button class="btn btn-primary" data-wi-action="edit" data-id="${esc(id)}"><span class="material-icons-round">edit</span> ویرایش</button>` : ""}
        <button class="btn" data-wi-action="print" data-id="${esc(id)}"><span class="material-icons-round">print</span> پیش‌نمایش چاپ</button>
        ${upper(row.status_code) === "DRAFT" && !row.is_legacy_readonly ? `<button class="btn" data-wi-action="issue" data-id="${esc(id)}"><span class="material-icons-round">send</span> ارسال</button>` : ""}
      </div>
      <div class="wi-drawer-body">
        <div class="wi-detail-title">${esc(row.title)}</div>
        <div class="wi-detail-grid">
          <div><b>پروژه</b><span>${esc(row.project_code)}</span></div>
          <div><b>دیسیپلین</b><span>${esc(row.discipline_code)}</span></div>
          <div><b>فرستنده</b><span>${esc(row.sender_org_name || "-")}</span></div>
          <div><b>گیرنده</b><span>${esc(row.recipient_org_name || "-")}</span></div>
          <div><b>سررسید</b><span>${esc(formatShamsiDate(row.response_due_date) || "-")}</span></div>
          <div><b>ارجاع</b><span>${esc(row.document_no || row.transmittal_no || "-")}</span></div>
        </div>
        <section class="wi-section"><h4>شرح دستور</h4><p>${esc(row.description || "-")}</p></section>
        <section class="wi-section"><h4>اقدام موردنیاز</h4><p>${esc(row.required_action || "-")}</p></section>
        <section class="wi-section">
          <h4>ارتباطات و ارجاعات</h4>
          <div class="wi-ref-list">${renderReferenceLinks(row)}</div>
          <div class="wi-relation-list">
            ${renderRelationCards(asArray(relations.outgoing), "outgoing", editableRelations)}
            ${renderRelationCards(asArray(relations.incoming), "incoming", false)}
            ${!asArray(relations.outgoing).length && !asArray(relations.incoming).length ? `<span class="muted">ارتباط رسمی ثبت نشده است.</span>` : ""}
          </div>
          ${editableRelations ? `
            <form class="wi-relation-form" data-wi-relation-form data-id="${esc(id)}">
              <select class="form-control" name="target_type">
                <option value="work_instruction">دستورکار</option>
                <option value="comm_item">RFI/NCR</option>
              </select>
              <input class="form-control" type="number" min="1" name="target_id" placeholder="شناسه مقصد">
              <select class="form-control" name="relation_type">
                ${asArray(catalog.relation_types || ["REFERENCES"]).map((code) => `<option value="${esc(code)}">${esc(relationTypeLabel(code))}</option>`).join("")}
              </select>
              <input class="form-control" name="note" placeholder="یادداشت اختیاری">
              <button class="btn btn-sm" type="submit"><span class="material-icons-round">add_link</span> افزودن ارتباط</button>
            </form>
          ` : ""}
        </section>
        <section class="wi-section">
          <h4>پیوست‌ها</h4>
          <div class="wi-file-list">${asArray(attachments.data).map((att) => `<a class="file-link" href="${esc(att.download_url)}" target="_blank">${esc(att.file_name)}</a>`).join("") || `<span class="muted">پیوستی ثبت نشده است.</span>`}</div>
          ${!row.is_legacy_readonly && deps.canEdit() ? `<form class="wi-inline-form" data-wi-upload-form data-id="${esc(id)}"><input class="form-control" type="file" name="file"><button class="btn btn-sm" type="submit">آپلود</button></form>` : ""}
        </section>
        <section class="wi-section">
          <h4>کامنت‌ها</h4>
          <div class="wi-comment-list">${asArray(comments.data).map((c) => `<div class="comment-row"><b>${esc(c.created_by_name || "")}</b><span>${esc(c.comment_text)}</span></div>`).join("") || `<span class="muted">کامنتی ثبت نشده است.</span>`}</div>
          ${!row.is_legacy_readonly && deps.canEdit() ? `<form class="wi-comment-form" data-wi-comment-form data-id="${esc(id)}"><textarea class="form-control" name="comment_text" placeholder="کامنت..."></textarea><button class="btn btn-sm" type="submit">ثبت کامنت</button></form>` : ""}
        </section>
      </div>
    </section>
  `;
  const uploadForm = drawer.querySelector("[data-wi-upload-form]") as HTMLFormElement | null;
  uploadForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(uploadForm);
    await fetchJson(deps, `/api/v1/work-instructions/${id}/attachments`, { method: "POST", body: fd });
    deps.showToast("پیوست اضافه شد.", "success");
    await openDrawer(root, key, deps, id);
  });
  const commentForm = drawer.querySelector("[data-wi-comment-form]") as HTMLFormElement | null;
  commentForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    await fetchJson(deps, `/api/v1/work-instructions/${id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment_text: String(new FormData(commentForm).get("comment_text") || "") }),
    });
    deps.showToast("کامنت ثبت شد.", "success");
    await openDrawer(root, key, deps, id);
  });
  const relationForm = drawer.querySelector("[data-wi-relation-form]") as HTMLFormElement | null;
  relationForm?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(relationForm);
    const targetId = Number(fd.get("target_id") || 0);
    if (!targetId) {
      deps.showToast("شناسه مقصد ارتباط الزامی است.", "error");
      return;
    }
    await fetchJson(deps, `/api/v1/work-instructions/${id}/relations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_type: String(fd.get("target_type") || "work_instruction"),
        target_id: targetId,
        relation_type: String(fd.get("relation_type") || "REFERENCES"),
        note: String(fd.get("note") || "").trim() || null,
      }),
    });
    deps.showToast("ارتباط دستورکار ثبت شد.", "success");
    await openDrawer(root, key, deps, id);
  });
  drawer.querySelectorAll("[data-wi-delete-relation]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const relationId = Number((btn as HTMLElement).dataset.wiDeleteRelation || 0);
      if (!relationId) return;
      await fetchJson(deps, `/api/v1/work-instructions/${id}/relations?relation_id=${relationId}`, { method: "DELETE" });
      deps.showToast("ارتباط حذف شد.", "success");
      await openDrawer(root, key, deps, id);
    });
  });
}
async function openEditor(root: HTMLElement, key: string, deps: WorkInstructionsUiDeps, row: any | null): Promise<void> {
  const catalog = await ensureCatalog(key, deps);
  const host = q(root, ".wi-editor-host")!;
  const orgId = row?.organization_id || getUserOrgId(deps) || "";
  const orgLabel = asArray(catalog.organizations).find((o) => String(o.id) === String(orgId))?.name || row?.sender_org_name || "سازمان کاربر";
  closeDrawer(root);
  host.hidden = false;
  document.body.classList.add("wi-drawer-open");
  host.innerHTML = `
    <div class="wi-editor-backdrop" data-wi-editor-cancel></div>
    <section class="wi-editor-panel" role="dialog" aria-modal="true" aria-label="${row?.id ? "ویرایش دستورکار" : "دستورکار جدید"}">
      <header class="wi-editor-header">
        <button class="btn btn-icon" data-wi-editor-cancel title="بستن"><span class="material-icons-round">close</span></button>
        <div>
          <h3 class="module-title">${row?.id ? "ویرایش دستورکار" : "دستورکار جدید"}</h3>
          <p class="module-subtitle">${row?.id ? esc(row.instruction_no || "") : "Draft"}</p>
        </div>
      </header>
      <div class="wi-editor-body">
        <section class="wi-editor-section">
          <h4>اطلاعات اصلی</h4>
          <div class="wi-editor-grid">
            <label>پروژه<select class="form-control" data-field="project_code">${optionHtml(catalog.projects, "code", "name", row?.project_code)}</select></label>
            <label>دیسیپلین<select class="form-control" data-field="discipline_code">${optionHtml(catalog.disciplines, "code", "name", row?.discipline_code)}</select></label>
            <label>فرستنده<input class="form-control" value="${esc(orgLabel)}" readonly><input type="hidden" data-field="organization_id" value="${esc(orgId)}"></label>
            <label>گیرنده<select class="form-control" data-field="recipient_org_id">${optionHtml(catalog.organizations, "id", "name", row?.recipient_org_id)}</select></label>
            <label class="wi-span-2">عنوان<input class="form-control" data-field="title" value="${esc(row?.title || "")}" placeholder="عنوان دستورکار"></label>
            <label>سررسید<input class="form-control" type="datetime-local" data-field="response_due_date" value="${esc(String(row?.response_due_date || "").slice(0, 16))}"></label>
            <label>اولویت<select class="form-control" data-field="priority">${["LOW","NORMAL","HIGH","URGENT"].map((p) => `<option value="${p}"${upper(row?.priority || "NORMAL") === p ? " selected" : ""}>${esc(priorityLabel(p))}</option>`).join("")}</select></label>
            <label>مسئول<input class="form-control" data-field="assignee_user_id" value="${esc(row?.assignee_user_id || "")}" placeholder="شناسه کاربر اختیاری"></label>
          </div>
        </section>
        <section class="wi-editor-section">
          <h4>شرح و اقدام</h4>
          <div class="wi-editor-grid">
            <label class="wi-span-2">شرح دستور<textarea class="form-control" rows="5" data-field="description">${esc(row?.description || "")}</textarea></label>
            <label class="wi-span-2">اقدام موردنیاز<textarea class="form-control" rows="4" data-field="required_action">${esc(row?.required_action || "")}</textarea></label>
          </div>
        </section>
        <section class="wi-editor-section">
          <h4>ارجاعات</h4>
          <div class="wi-editor-grid">
            <label>شماره مدرک<input class="form-control" data-field="document_no" value="${esc(row?.document_no || "")}" placeholder="Doc No"></label>
            <label>شماره ترنسمیتال<input class="form-control" data-field="transmittal_no" value="${esc(row?.transmittal_no || "")}" placeholder="Transmittal No"></label>
            <label>کد فعالیت<input class="form-control" data-field="activity_code" value="${esc(row?.activity_code || "")}" placeholder="Activity"></label>
            <label>WBS<input class="form-control" data-field="wbs_code" value="${esc(row?.wbs_code || "")}" placeholder="WBS"></label>
            <label>بند قرارداد<input class="form-control" data-field="contract_clause_ref" value="${esc(row?.contract_clause_ref || "")}"></label>
            <label>بند مشخصات<input class="form-control" data-field="spec_clause_ref" value="${esc(row?.spec_clause_ref || "")}"></label>
          </div>
        </section>
      </div>
      <footer class="wi-editor-footer">
        <button class="btn btn-primary" data-wi-editor-save><span class="material-icons-round">save</span> ذخیره پیش‌نویس</button>
        <button class="btn btn-primary" data-wi-editor-issue><span class="material-icons-round">send</span> ذخیره و ارسال</button>
        <button class="btn" data-wi-editor-cancel>انصراف</button>
      </footer>
    </section>
  `;
  const collect = () => {
    const get = (name: string) => value(host, `[data-field="${name}"]`);
    const payload: any = {
      project_code: get("project_code"),
      discipline_code: get("discipline_code"),
      organization_id: Number(get("organization_id")) || null,
      recipient_org_id: Number(get("recipient_org_id")) || null,
      title: get("title"),
      description: get("description"),
      required_action: get("required_action"),
      response_due_date: get("response_due_date") || null,
      priority: get("priority") || "NORMAL",
      document_no: get("document_no") || null,
      transmittal_no: get("transmittal_no") || null,
      activity_code: get("activity_code") || null,
      wbs_code: get("wbs_code") || null,
      contract_clause_ref: get("contract_clause_ref") || null,
      spec_clause_ref: get("spec_clause_ref") || null,
    };
    const assignee = Number(get("assignee_user_id") || 0);
    if (assignee > 0) payload.assignee_user_id = assignee;
    return payload;
  };
  const closeEditor = async () => {
    host.hidden = true;
    host.innerHTML = "";
    document.body.classList.remove("wi-drawer-open");
    await loadRows(root, key, deps);
  };
  host.querySelectorAll("[data-wi-editor-cancel]").forEach((btn) => btn.addEventListener("click", () => void closeEditor()));
  const save = async (issue: boolean) => {
    const payload = collect();
    if (!payload.project_code || !payload.discipline_code || !payload.recipient_org_id || !payload.title) {
      deps.showToast("پروژه، دیسیپلین، گیرنده و عنوان الزامی است.", "error");
      return;
    }
    if (issue && (!payload.response_due_date || `${payload.description || ""} ${payload.required_action || ""}`.trim().length < 10)) {
      deps.showToast("برای ارسال، سررسید و شرح/اقدام کافی لازم است.", "error");
      return;
    }
    const saved = row?.id
      ? await fetchJson(deps, `/api/v1/work-instructions/${row.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
      : await fetchJson(deps, "/api/v1/work-instructions/create", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const savedId = saved?.data?.id || row?.id;
    if (issue && savedId && upper(saved?.data?.status_code) === "DRAFT") {
      await fetchJson(deps, `/api/v1/work-instructions/${savedId}/transition`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ to_status_code: "SUBMITTED" }) });
    }
    deps.showToast(issue ? "دستورکار ارسال شد." : "دستورکار ذخیره شد.", "success");
    await closeEditor();
    if (savedId) await openDrawer(root, key, deps, savedId);
  };
  q(host, "[data-wi-editor-save]")?.addEventListener("click", () => void save(false));
  q(host, "[data-wi-editor-issue]")?.addEventListener("click", () => void save(true));
}
async function printInstruction(deps: WorkInstructionsUiDeps, id: number): Promise<void> {
  const data = await fetchJson(deps, `/api/v1/work-instructions/${id}`);
  const row = data.data || {};
  const html = `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>${esc(row.instruction_no)}</title>
  <style>@page{size:A4;margin:14mm}body{font-family:Tahoma,Arial,sans-serif;color:#111}.page{border:1px solid #111;min-height:260mm;padding:10mm}.head{display:grid;grid-template-columns:1fr 2fr 1fr;border-bottom:2px solid #111;padding-bottom:8px;align-items:center;text-align:center}.logo{border:1px solid #999;padding:24px 8px}.meta{font-size:12px;text-align:right}.title h1{margin:0;font-size:22px}.box{border:1px solid #222;margin-top:10px}.box h2{background:#e5e7eb;margin:0;padding:6px;font-size:14px;text-align:center}.grid{display:grid;grid-template-columns:repeat(4,1fr)}.cell{border-top:1px solid #222;border-left:1px solid #222;padding:7px;min-height:28px}.cell b{display:block;color:#555;font-size:11px}.desc{padding:10px;line-height:1.9;min-height:90px}</style>
  </head><body><button onclick="window.print()">چاپ / ذخیره PDF</button><div class="page">
  <div class="head"><div class="logo">لوگوی شرکت</div><div class="title"><h1>فرم دستورکار</h1><strong>WORK INSTRUCTION</strong></div><div class="meta"><div>شماره: ${esc(row.instruction_no)}</div><div>وضعیت: ${esc(row.status_code)}</div><div>تاریخ: ${esc(formatShamsiDate(row.created_at) || "")}</div></div></div>
  <div class="box"><h2>مشخصات</h2><div class="grid"><div class="cell"><b>پروژه</b>${esc(row.project_code)}</div><div class="cell"><b>دیسیپلین</b>${esc(row.discipline_code)}</div><div class="cell"><b>فرستنده</b>${esc(row.sender_org_name || "-")}</div><div class="cell"><b>گیرنده</b>${esc(row.recipient_org_name || "-")}</div><div class="cell"><b>عنوان</b>${esc(row.title)}</div><div class="cell"><b>اولویت</b>${esc(priorityLabel(row.priority))}</div><div class="cell"><b>سررسید</b>${esc(formatShamsiDate(row.response_due_date) || "-")}</div><div class="cell"><b>ارجاع</b>${esc(row.document_no || "-")}</div></div></div>
  <div class="box"><h2>شرح دستور</h2><div class="desc">${esc(row.description || "-")}</div></div>
  <div class="box"><h2>اقدام موردنیاز</h2><div class="desc">${esc(row.required_action || "-")}</div></div>
  </div></body></html>`;
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.open();
  win.document.write(html);
  win.document.close();
}
async function open(moduleKey: string, tabKey: string, deps: WorkInstructionsUiDeps): Promise<boolean> {
  const root = rootFor(moduleKey, tabKey);
  if (!root) return false;
  const key = keyOf(moduleKey, tabKey);
  const catalog = await ensureCatalog(key, deps);
  renderShell(root, key, deps, catalog);
  await loadRows(root, key, deps);
  return true;
}
export function createWorkInstructionsUiBridge(): WorkInstructionsUiBridge {
  return {
    async onTabOpened(moduleKey, tabKey, deps) {
      return open(moduleKey, tabKey, deps);
    },
    async initModule(moduleKey, deps) {
      const roots = document.querySelectorAll(`.work-instructions-root[data-module="${normalize(moduleKey)}"][data-tab]`);
      for (const root of Array.from(roots)) {
        await open(moduleKey, (root as HTMLElement).dataset.tab || "instructions", deps);
      }
      return roots.length > 0;
    },
  };
}
