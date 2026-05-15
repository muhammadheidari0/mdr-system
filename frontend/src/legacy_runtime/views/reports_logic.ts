// @ts-nocheck
import { formatShamsiDate, formatShamsiDateForFileName } from "../../lib/persian_datetime";

const SITE_LOG_REPORT_SECTION_LABELS = {
  general: "عمومی",
  manpower: "نفرات",
  equipment: "تجهیزات",
  material: "مصالح",
  activity: "فعالیت",
};

const SITE_LOG_DEFAULT_COLUMNS_BY_SECTION = {
  general: [
    "log_no",
    "log_date",
    "project_code",
    "organization_name",
    "contract_number",
    "log_type_label",
    "status_label",
    "claimed_manpower_count",
    "verified_manpower_count",
    "manpower_count_delta",
    "claimed_equipment_count",
    "verified_equipment_count",
    "activity_count",
    "claimed_avg_progress_pct",
    "verified_avg_progress_pct",
    "progress_delta_pct",
    "issue_count",
    "attachment_count",
  ],
  manpower: [
    "log_no",
    "log_date",
    "project_code",
    "organization_name",
    "work_section_label",
    "role_label",
    "claimed_count",
    "verified_count",
    "count_delta",
    "claimed_hours",
    "verified_hours",
    "hours_delta",
    "row_attachment_count",
  ],
  equipment: [
    "log_no",
    "log_date",
    "project_code",
    "organization_name",
    "equipment_label",
    "work_location",
    "claimed_count",
    "verified_count",
    "count_delta",
    "claimed_status",
    "verified_status",
    "claimed_hours",
    "verified_hours",
    "hours_delta",
    "row_attachment_count",
  ],
  material: [
    "log_no",
    "log_date",
    "project_code",
    "organization_name",
    "material_title",
    "consumption_location",
    "unit",
    "incoming_quantity",
    "consumed_quantity",
    "cumulative_quantity",
    "row_attachment_count",
  ],
  activity: [
    "log_no",
    "log_date",
    "project_code",
    "organization_name",
    "activity_title",
    "location",
    "unit",
    "today_quantity",
    "cumulative_quantity",
    "personnel_count",
    "claimed_progress_pct",
    "verified_progress_pct",
    "progress_delta_pct",
    "activity_status",
    "row_attachment_count",
  ],
};

const siteLogReportState = {
  catalog: null,
  columns: [],
  data: [],
  summary: {},
  pagination: { page: 1, page_size: 50, total: 0, pages: 1 },
  sortBy: "log_date",
  sortDir: "desc",
  section: "general",
  visibleColumns: new Set(),
  loaded: false,
};

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function toast(message, type = "info") {
  if (typeof showToast === "function") showToast(message, type);
}

function buildSearchParams(raw) {
  const params = new URLSearchParams();
  Object.entries(raw || {}).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    const text = String(value).trim();
    if (!text) return;
    params.set(key, text);
  });
  return params.toString();
}

async function readJsonResponse(res, fallbackMessage) {
  const text = await res.text();
  let body = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new Error(res.ok ? "پاسخ سرور JSON معتبر نیست." : `${fallbackMessage} (${res.status})`);
    }
  }
  if (!res.ok || body?.ok === false) {
    throw new Error(body?.detail || body?.message || `${fallbackMessage} (${res.status})`);
  }
  return body;
}

function setSelectOptions(select, rows, placeholder, valueGetter, labelGetter) {
  if (!select) return;
  const previous = String(select.value || "");
  select.innerHTML = `<option value="">${esc(placeholder)}</option>`;
  rows.forEach((row) => {
    const value = String(valueGetter(row) ?? "").trim();
    if (!value) return;
    const label = String(labelGetter(row) ?? value).trim();
    select.innerHTML += `<option value="${esc(value)}">${esc(label)}</option>`;
  });
  if (previous && Array.from(select.options).some((option) => option.value === previous)) {
    select.value = previous;
  }
}

function fillProjectAndDisciplineSelects() {
  const projects = asArray(window.CACHE?.projects);
  const disciplines = asArray(window.CACHE?.disciplines);
  ["rpt-project", "rpt-site-project"].forEach((id) => {
    const select = document.getElementById(id);
    if (!select || select.options.length > 1) return;
    setSelectOptions(
      select,
      projects,
      id === "rpt-project" ? "همه" : "همه پروژه‌ها",
      (row) => row.code || row.project_code,
      (row) => {
        const code = String(row.code || row.project_code || "").trim();
        const name = String(row.project_name || row.name_e || row.name_p || row.name || code).trim();
        return `${code} - ${name}`;
      }
    );
  });
  ["rpt-discipline", "rpt-site-discipline"].forEach((id) => {
    const select = document.getElementById(id);
    if (!select || select.options.length > 1) return;
    setSelectOptions(
      select,
      disciplines,
      id === "rpt-discipline" ? "همه" : "همه دیسپلین‌ها",
      (row) => row.code || row.discipline_code,
      (row) => {
        const code = String(row.code || row.discipline_code || "").trim();
        const name = String(row.name_e || row.name_p || row.name || code).trim();
        return `${code} - ${name}`;
      }
    );
  });
}

function fillCatalogSelects() {
  fillProjectAndDisciplineSelects();
}

function statusLabel(code) {
  return (
    {
      DRAFT: "پیش‌نویس",
      SUBMITTED: "ارسال‌شده",
      VERIFIED: "تاییدشده",
    }[String(code || "").toUpperCase()] || code || "-"
  );
}

function logTypeLabel(code) {
  return (
    {
      DAILY: "روزانه",
      WEEKLY: "هفتگی",
      SAFETY_INCIDENT: "حادثه ایمنی",
    }[String(code || "").toUpperCase()] || code || "-"
  );
}

async function loadSiteLogCatalog() {
  if (siteLogReportState.catalog) return siteLogReportState.catalog;
  const res = await window.fetchWithAuth("/api/v1/site-logs/catalog");
  const body = await readJsonResponse(res, "بارگذاری کاتالوگ گزارش کارگاهی ناموفق بود");
  siteLogReportState.catalog = body || {};
  fillSiteLogCatalogSelects();
  return siteLogReportState.catalog;
}

function fillSiteLogCatalogSelects() {
  const catalog = siteLogReportState.catalog || {};
  if (!catalog) return;
  const projectSelect = document.getElementById("rpt-site-project");
  if (projectSelect && asArray(catalog.projects).length) {
    setSelectOptions(
      projectSelect,
      asArray(catalog.projects),
      "همه پروژه‌ها",
      (row) => row.code,
      (row) => `${row.code || ""} - ${row.name || row.code || ""}`
    );
  }
  const disciplineSelect = document.getElementById("rpt-site-discipline");
  if (disciplineSelect && asArray(catalog.disciplines).length) {
    setSelectOptions(
      disciplineSelect,
      asArray(catalog.disciplines),
      "همه دیسپلین‌ها",
      (row) => row.code,
      (row) => `${row.code || ""} - ${row.name || row.code || ""}`
    );
  }
  setSelectOptions(
    document.getElementById("rpt-site-organization"),
    asArray(catalog.organizations),
    "همه سازمان‌ها",
    (row) => row.id,
    (row) => row.name || row.id
  );
  refreshSiteLogContractOptions();
}

function refreshSiteLogContractOptions() {
  const catalog = siteLogReportState.catalog || {};
  const selectedOrg = String(document.getElementById("rpt-site-organization")?.value || "").trim();
  const organizations = asArray(catalog.organizations);
  const contracts = selectedOrg
    ? asArray(organizations.find((row) => String(row.id || "") === selectedOrg)?.contracts)
    : organizations.flatMap((row) => asArray(row.contracts).map((contract) => ({ ...contract, organization_name: row.name })));
  setSelectOptions(
    document.getElementById("rpt-site-contract"),
    contracts,
    "همه قراردادها",
    (row) => row.id,
    (row) => {
      const number = String(row.contract_number || row.id || "").trim();
      const subject = String(row.subject || "").trim();
      const org = String(row.organization_name || "").trim();
      return [number, subject, org].filter(Boolean).join(" - ");
    }
  );
}

function commQueryParams() {
  const projectCode = String(document.getElementById("rpt-project")?.value || "").trim();
  const disciplineCode = String(document.getElementById("rpt-discipline")?.value || "").trim();
  const statusCode = String(document.getElementById("rpt-status")?.value || "").trim();
  const dateStart = String(document.getElementById("rpt-date-start")?.value || "").trim();
  const dateEnd = String(document.getElementById("rpt-date-end")?.value || "").trim();
  return {
    project_code: projectCode || undefined,
    discipline_code: disciplineCode || undefined,
    status: statusCode || undefined,
    status_code: statusCode || undefined,
    date_from: dateStart || undefined,
    date_to: dateEnd || undefined,
    date_start: dateStart || undefined,
    date_end: dateEnd || undefined,
  };
}

function siteLogFilters() {
  return {
    project_code: document.getElementById("rpt-site-project")?.value || undefined,
    discipline_code: document.getElementById("rpt-site-discipline")?.value || undefined,
    organization_id: document.getElementById("rpt-site-organization")?.value || undefined,
    organization_contract_id: document.getElementById("rpt-site-contract")?.value || undefined,
    log_type: document.getElementById("rpt-site-log-type")?.value || undefined,
    status_code: document.getElementById("rpt-site-status")?.value || undefined,
    log_date_from: document.getElementById("rpt-site-date-from")?.value || undefined,
    log_date_to: document.getElementById("rpt-site-date-to")?.value || undefined,
    search: document.getElementById("rpt-site-search")?.value || undefined,
  };
}

function siteLogPageSize() {
  return Number(document.getElementById("rpt-site-page-size")?.value || siteLogReportState.pagination.page_size || 50);
}

function siteLogTableParams(includePagination = true) {
  const params = {
    ...siteLogFilters(),
    report_section: siteLogReportState.section || "general",
    sort_by: siteLogReportState.sortBy,
    sort_dir: siteLogReportState.sortDir,
  };
  if (includePagination) {
    params.page = siteLogReportState.pagination.page || 1;
    params.page_size = siteLogPageSize();
  }
  return params;
}

function siteLogTableUrl(format = "json", includePagination = true, absolute = false) {
  const path = format === "csv" ? "/api/v1/site-logs/reports/table.csv" : "/api/v1/site-logs/reports/table";
  const query = buildSearchParams(siteLogTableParams(includePagination));
  const url = `${path}${query ? `?${query}` : ""}`;
  return absolute ? new URL(url, window.location.origin).toString() : url;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(value ?? "-");
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 }).format(num);
}

function formatCell(column, row) {
  const key = column.key;
  const value = row[key];
  if (key === "log_date" || key === "created_at" || key === "updated_at") return formatShamsiDate(value) || "-";
  if (column.type === "number") return formatNumber(value);
  if (column.type === "percent") return value === null || value === undefined ? "-" : `${formatNumber(value)}%`;
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function renderSiteLogKpis(summary = {}) {
  const section = siteLogReportState.section || "general";
  const labelSets = {
    general: {
      title: "گزارش عمومی کارگاهی",
      total: "کل گزارش‌ها",
      manpower: "نفرات تاییدی",
      equipment: "تجهیزات تاییدی",
      progress: "میانگین پیشرفت تاییدی",
      delta: "اختلاف تایید با اعلام",
    },
    manpower: {
      title: "گزارش نفرات کارگاهی",
      total: "ردیف نفرات",
      manpower: "تعداد تاییدی",
      equipment: "ساعت تاییدی",
      progress: "تعداد اعلامی",
      delta: "اختلاف تعداد",
    },
    equipment: {
      title: "گزارش تجهیزات کارگاهی",
      total: "ردیف تجهیزات",
      manpower: "تعداد تاییدی",
      equipment: "ساعت تاییدی",
      progress: "تعداد اعلامی",
      delta: "اختلاف تعداد",
    },
    material: {
      title: "گزارش مصالح کارگاهی",
      total: "ردیف مصالح",
      manpower: "ورودی",
      equipment: "مصرفی",
      progress: "تجمعی",
      delta: "پیوست ردیف‌ها",
    },
    activity: {
      title: "گزارش فعالیت‌های کارگاهی",
      total: "ردیف فعالیت",
      manpower: "تعداد نفرات",
      equipment: "میانگین پیشرفت تاییدی",
      progress: "پیشرفت اعلامی",
      delta: "اختلاف پیشرفت",
    },
  };
  const labels = labelSets[section] || labelSets.general;
  setText("rpt-site-section-title", labels.title);
  setText("rpt-site-kpi-total-label", labels.total);
  setText("rpt-site-kpi-draft-label", "پیش‌نویس");
  setText("rpt-site-kpi-submitted-label", "ارسال‌شده");
  setText("rpt-site-kpi-verified-label", "تاییدشده");
  setText("rpt-site-kpi-manpower-label", labels.manpower);
  setText("rpt-site-kpi-equipment-label", labels.equipment);
  setText("rpt-site-kpi-progress-label", labels.progress);
  setText("rpt-site-kpi-delta-label", labels.delta);

  setText("rpt-site-kpi-total", formatNumber(summary.total || 0));
  setText("rpt-site-kpi-draft", formatNumber(summary.draft || 0));
  setText("rpt-site-kpi-submitted", formatNumber(summary.submitted || 0));
  setText("rpt-site-kpi-verified", formatNumber(summary.verified || 0));
  if (section === "manpower") {
    setText("rpt-site-kpi-manpower", formatNumber(summary.verified_count || 0));
    setText("rpt-site-kpi-equipment", formatNumber(summary.verified_hours || 0));
    setText("rpt-site-kpi-progress", formatNumber(summary.claimed_count || 0));
    setText("rpt-site-kpi-delta", formatNumber(summary.count_delta || 0));
    return;
  }
  if (section === "equipment") {
    setText("rpt-site-kpi-manpower", formatNumber(summary.verified_count || 0));
    setText("rpt-site-kpi-equipment", formatNumber(summary.verified_hours || 0));
    setText("rpt-site-kpi-progress", formatNumber(summary.claimed_count || 0));
    setText("rpt-site-kpi-delta", formatNumber(summary.count_delta || 0));
    return;
  }
  if (section === "material") {
    setText("rpt-site-kpi-manpower", formatNumber(summary.incoming_quantity || 0));
    setText("rpt-site-kpi-equipment", formatNumber(summary.consumed_quantity || 0));
    setText("rpt-site-kpi-progress", formatNumber(summary.cumulative_quantity || 0));
    setText("rpt-site-kpi-delta", formatNumber(summary.row_attachment_count || 0));
    return;
  }
  if (section === "activity") {
    setText("rpt-site-kpi-manpower", formatNumber(summary.personnel_count || 0));
    setText("rpt-site-kpi-equipment", summary.verified_avg_progress_pct === null || summary.verified_avg_progress_pct === undefined ? "-" : `${formatNumber(summary.verified_avg_progress_pct)}%`);
    setText("rpt-site-kpi-progress", summary.claimed_avg_progress_pct === null || summary.claimed_avg_progress_pct === undefined ? "-" : `${formatNumber(summary.claimed_avg_progress_pct)}%`);
    setText("rpt-site-kpi-delta", summary.progress_delta_pct === null || summary.progress_delta_pct === undefined ? "-" : `${formatNumber(summary.progress_delta_pct)}%`);
    return;
  }
  setText("rpt-site-kpi-manpower", formatNumber(summary.verified_manpower_count ?? summary.claimed_manpower_count ?? 0));
  setText("rpt-site-kpi-equipment", formatNumber(summary.verified_equipment_count ?? summary.claimed_equipment_count ?? 0));
  setText("rpt-site-kpi-progress", summary.verified_avg_progress_pct === null || summary.verified_avg_progress_pct === undefined ? "-" : `${formatNumber(summary.verified_avg_progress_pct)}%`);
  setText("rpt-site-kpi-delta", summary.progress_delta_pct === null || summary.progress_delta_pct === undefined ? "-" : `${formatNumber(summary.progress_delta_pct)}%`);
}

function initializeVisibleColumns() {
  if (siteLogReportState.visibleColumns.size) return;
  const available = new Set(siteLogReportState.columns.map((column) => column.key));
  const defaults = SITE_LOG_DEFAULT_COLUMNS_BY_SECTION[siteLogReportState.section || "general"] || SITE_LOG_DEFAULT_COLUMNS_BY_SECTION.general;
  defaults.filter((key) => available.has(key)).forEach((key) => siteLogReportState.visibleColumns.add(key));
}

function renderSiteLogColumnMenu() {
  const menu = document.getElementById("rpt-site-column-menu");
  if (!menu) return;
  initializeVisibleColumns();
  menu.innerHTML = siteLogReportState.columns
    .filter((column) => column.key !== "log_id")
    .map((column) => {
      const checked = siteLogReportState.visibleColumns.has(column.key) ? "checked" : "";
      return `<label><input type="checkbox" ${checked} data-report-action="site-log-toggle-column" data-column-key="${esc(column.key)}"> ${esc(column.label || column.key)}</label>`;
    })
    .join("");
}

function sortIconFor(key) {
  if (siteLogReportState.sortBy !== key) return "unfold_more";
  return siteLogReportState.sortDir === "asc" ? "arrow_upward" : "arrow_downward";
}

function visibleColumns() {
  initializeVisibleColumns();
  return siteLogReportState.columns.filter((column) => siteLogReportState.visibleColumns.has(column.key));
}

function renderSiteLogTable() {
  const head = document.getElementById("rpt-site-table-head");
  const body = document.getElementById("rpt-site-table-body");
  if (!head || !body) return;
  const columns = visibleColumns();
  head.innerHTML = `
    <tr>
      ${columns
        .map(
          (column) => `
            <th>
              <button class="reports-sort-btn" type="button" data-report-action="site-log-sort" data-sort-key="${esc(column.key)}">
                ${esc(column.label || column.key)}
                <span class="material-icons-round" style="font-size:16px;">${sortIconFor(column.key)}</span>
              </button>
            </th>`
        )
        .join("")}
      <th>عملیات</th>
    </tr>`;

  if (!siteLogReportState.data.length) {
    body.innerHTML = `<tr><td colspan="${columns.length + 1}" class="center-text" style="padding:24px;color:#64748b;">ردیفی برای فیلترهای فعلی پیدا نشد.</td></tr>`;
    return;
  }

  body.innerHTML = siteLogReportState.data
    .map((row, rowIndex) => {
      const id = Number(row.log_id || row.id || 0);
      return `
        <tr>
          ${columns.map((column) => `<td>${esc(formatCell(column, row))}</td>`).join("")}
          <td>
            <div class="reports-row-actions">
              <button class="reports-mini-btn" type="button" data-report-action="site-log-open" data-log-id="${id}" data-row-index="${rowIndex}" title="مشاهده">
                <span class="material-icons-round">visibility</span>
              </button>
              <button class="reports-mini-btn" type="button" data-report-action="site-log-pdf" data-log-id="${id}" data-row-index="${rowIndex}" title="PDF">
                <span class="material-icons-round">picture_as_pdf</span>
              </button>
              <button class="reports-mini-btn" type="button" data-report-action="site-log-row-csv" data-log-id="${id}" data-row-index="${rowIndex}" title="CSV ردیف">
                <span class="material-icons-round">download</span>
              </button>
            </div>
          </td>
        </tr>`;
    })
    .join("");
}

function renderSiteLogPagination() {
  const page = siteLogReportState.pagination.page || 1;
  const pages = siteLogReportState.pagination.pages || 1;
  const total = siteLogReportState.pagination.total || 0;
  setText("rpt-site-page-label", `صفحه ${formatNumber(page)} از ${formatNumber(pages)}`);
  setText("rpt-site-result-meta", `${formatNumber(total)} ردیف`);
}

async function loadSiteLogReport() {
  await loadSiteLogCatalog().catch((error) => {
    console.warn(error);
  });
  const body = document.getElementById("rpt-site-table-body");
  if (body) body.innerHTML = '<tr><td class="center-text" style="padding:24px;color:#64748b;">در حال بارگذاری...</td></tr>';
  try {
    const res = await window.fetchWithAuth(siteLogTableUrl("json", true));
    const data = await readJsonResponse(res, "اجرای گزارش کارگاهی ناموفق بود");
    siteLogReportState.columns = asArray(data.columns);
    siteLogReportState.data = asArray(data.data);
    siteLogReportState.summary = data.summary || {};
    siteLogReportState.pagination = data.pagination || siteLogReportState.pagination;
    siteLogReportState.sortBy = data.sort?.sort_by || siteLogReportState.sortBy;
    siteLogReportState.sortDir = data.sort?.sort_dir || siteLogReportState.sortDir;
    siteLogReportState.section = data.report_section || siteLogReportState.section || "general";
    siteLogReportState.loaded = true;
    renderSiteLogKpis(siteLogReportState.summary);
    renderSiteLogColumnMenu();
    renderSiteLogTable();
    renderSiteLogPagination();
  } catch (error) {
    console.error(error);
    toast(error instanceof Error ? error.message : "اجرای گزارش ناموفق بود.", "error");
    if (body) body.innerHTML = '<tr><td class="center-text" style="padding:24px;color:#b91c1c;">بارگذاری گزارش ناموفق بود.</td></tr>';
  }
}

function parseFilenameFromDisposition(headerValue, fallback) {
  const raw = String(headerValue || "");
  const utf8 = raw.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      return utf8[1];
    }
  }
  const normal = raw.match(/filename="?([^";]+)"?/i);
  return normal ? normal[1] : fallback;
}

async function downloadBlobFromUrl(url, fallbackName) {
  const res = await window.fetchWithAuth(url);
  if (!res.ok) {
    let message = "دانلود ناموفق بود.";
    try {
      const body = await res.json();
      message = body?.detail || message;
    } catch {
      // ignore non-json error bodies
    }
    throw new Error(message);
  }
  const blob = await res.blob();
  const filename = parseFilenameFromDisposition(res.headers.get("Content-Disposition"), fallbackName);
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename || fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 5000);
}

async function exportSiteLogReportCsv() {
  const section = siteLogReportState.section || "general";
  await downloadBlobFromUrl(siteLogTableUrl("csv", false), `SiteLog_${section}_Report_${formatShamsiDateForFileName(new Date())}.csv`);
}

async function exportSiteLogReportXlsx() {
  try {
    await window.ensureXlsxLoaded?.();
    if (!window.XLSX) throw new Error("XLSX library not available");
    const params = { ...siteLogTableParams(true), page: 1, page_size: 5000 };
    const res = await window.fetchWithAuth(`/api/v1/site-logs/reports/table?${buildSearchParams(params)}`);
    const body = await readJsonResponse(res, "بارگذاری داده Excel ناموفق بود");
    const columns = asArray(body.columns);
    const rows = asArray(body.data).map((row) => {
      const out = {};
      columns.forEach((column) => {
        out[column.label || column.key] = formatCell(column, row);
      });
      return out;
    });
    const wb = window.XLSX.utils.book_new();
    const ws = window.XLSX.utils.json_to_sheet(rows);
    const section = siteLogReportState.section || "general";
    window.XLSX.utils.book_append_sheet(wb, ws, `SiteLog_${section}`.slice(0, 31));
    window.XLSX.writeFile(wb, `SiteLog_${section}_Report_${formatShamsiDateForFileName(new Date())}.xlsx`);
    if ((body.pagination?.total || 0) > rows.length) {
      toast("برای Excel حداکثر ۵۰۰۰ ردیف اول صادر شد؛ خروجی CSV شامل همه ردیف‌های فیلترشده است.", "warning");
    }
  } catch (error) {
    console.error(error);
    toast(error instanceof Error ? error.message : "خروجی Excel ناموفق بود.", "error");
  }
}

function csvEscape(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadTextFile(text, filename, type = "text/csv;charset=utf-8") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function exportSiteLogRowCsv(logId, rowIndex = -1) {
  const row =
    Number(rowIndex) >= 0
      ? siteLogReportState.data[Number(rowIndex)]
      : siteLogReportState.data.find((item) => Number(item.log_id || item.id || 0) === Number(logId));
  if (!row) {
    toast("ردیف انتخاب‌شده پیدا نشد.", "error");
    return;
  }
  const columns = siteLogReportState.columns;
  const headers = columns.map((column) => column.key);
  const line = headers.map((key) => csvEscape(row[key])).join(",");
  downloadTextFile(`\ufeff${headers.join(",")}\r\n${line}\r\n`, `${row.log_no || "site-log-row"}.csv`);
}

async function downloadSiteLogPdf(logId) {
  await downloadBlobFromUrl(`/api/v1/site-logs/${Number(logId)}/pdf`, `site-log-${Number(logId)}.pdf`);
}

function renderSiteLogDetail(data) {
  const body = document.getElementById("rpt-site-detail-body");
  const title = document.getElementById("rpt-site-detail-title");
  const subtitle = document.getElementById("rpt-site-detail-subtitle");
  const row = data || {};
  if (title) title.textContent = row.log_no || "جزئیات گزارش کارگاهی";
  if (subtitle) subtitle.textContent = `${logTypeLabel(row.log_type)} | ${statusLabel(row.status_code)} | ${formatShamsiDate(row.log_date) || "-"}`;
  if (!body) return;
  const stats = [
    ["پروژه", row.project_code],
    ["دیسپلین", row.discipline_code],
    ["سازمان", row.organization_name],
    ["قرارداد", row.contract_number],
    ["موضوع قرارداد", row.contract_subject],
    ["شیفت", row.shift_label || row.shift],
    ["نفرات", row.manpower_count],
    ["تجهیزات", row.equipment_count],
    ["فعالیت‌ها", row.activity_count],
    ["موانع", row.issue_count],
    ["پیوست‌ها", row.attachments?.length || row.attachment_row_count || 0],
    ["آخرین بروزرسانی", formatShamsiDate(row.updated_at)],
  ];
  body.innerHTML = `
    <div class="reports-detail-grid">
      ${stats
        .map(
          ([label, value]) => `
            <div class="reports-detail-item">
              <label>${esc(label)}</label>
              <strong>${esc(value ?? "-")}</strong>
            </div>`
        )
        .join("")}
    </div>
    <div class="reports-muted-panel">
      <strong>خلاصه کارهای در حال انجام</strong>
      <div style="margin-top:8px;white-space:pre-wrap;color:#475569;">${esc(row.current_work_summary || row.summary || "-")}</div>
    </div>
    <div class="reports-muted-panel">
      <strong>برنامه بعدی</strong>
      <div style="margin-top:8px;white-space:pre-wrap;color:#475569;">${esc(row.next_plan_summary || "-")}</div>
    </div>
    <div class="reports-row-actions">
      <button class="btn-archive-primary" type="button" data-report-action="site-log-pdf" data-log-id="${Number(row.id || 0)}">
        <span class="material-icons-round">picture_as_pdf</span>
        دانلود PDF
      </button>
    </div>
  `;
}

async function openSiteLogDetail(logId) {
  const modal = document.getElementById("rpt-site-detail-modal");
  const body = document.getElementById("rpt-site-detail-body");
  if (body) body.innerHTML = '<div style="padding:20px;color:#64748b;">در حال بارگذاری...</div>';
  if (modal) modal.hidden = false;
  try {
    const res = await window.fetchWithAuth(`/api/v1/site-logs/${Number(logId)}`);
    const payload = await res.json();
    if (!res.ok || payload?.ok === false) throw new Error(payload?.detail || "باز کردن جزئیات گزارش ناموفق بود.");
    renderSiteLogDetail(payload.data || {});
  } catch (error) {
    console.error(error);
    toast(error instanceof Error ? error.message : "باز کردن جزئیات ناموفق بود.", "error");
    if (body) body.innerHTML = '<div style="padding:20px;color:#b91c1c;">جزئیات گزارش بارگذاری نشد.</div>';
  }
}

function closeSiteLogDetail() {
  const modal = document.getElementById("rpt-site-detail-modal");
  if (modal) modal.hidden = true;
}

function activateReportsTab(tabKey) {
  const root = document.getElementById("view-reports");
  if (!root) return;
  root.querySelectorAll("[data-report-tab-target]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-report-tab-target") === tabKey);
  });
  root.querySelectorAll("[data-report-tab-panel]").forEach((panel) => {
    const active = panel.getAttribute("data-report-tab-panel") === tabKey;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  if (tabKey === "site-log" && !siteLogReportState.loaded) void loadSiteLogReport();
}

function bindReportsActions() {
  const root = document.getElementById("view-reports");
  if (!root || root.dataset.reportsActionsBound === "1") return;

  root.addEventListener("click", async (event) => {
    const tab = event.target.closest("[data-report-tab-target]");
    if (tab && root.contains(tab)) {
      event.preventDefault();
      activateReportsTab(String(tab.getAttribute("data-report-tab-target") || "site-log"));
      return;
    }

    const trigger = event.target.closest("[data-report-action]");
    if (!trigger || !root.contains(trigger)) return;
    const action = String(trigger.getAttribute("data-report-action") || "").trim().toLowerCase();
    const logId = Number(trigger.getAttribute("data-log-id") || 0);
    const rowIndex = Number(trigger.getAttribute("data-row-index") ?? -1);

    try {
      if (action === "site-log-section") {
        event.preventDefault();
        const section = String(trigger.getAttribute("data-report-section") || "general").trim().toLowerCase();
        siteLogReportState.section = SITE_LOG_REPORT_SECTION_LABELS[section] ? section : "general";
        siteLogReportState.pagination.page = 1;
        siteLogReportState.sortBy = "log_date";
        siteLogReportState.sortDir = "desc";
        siteLogReportState.visibleColumns = new Set();
        root.querySelectorAll("[data-report-section]").forEach((button) => {
          button.classList.toggle("active", button.getAttribute("data-report-section") === siteLogReportState.section);
        });
        await loadSiteLogReport();
        return;
      }
      if (action === "site-log-generate") {
        event.preventDefault();
        siteLogReportState.pagination.page = 1;
        await loadSiteLogReport();
        return;
      }
      if (action === "site-log-export-csv") {
        event.preventDefault();
        await exportSiteLogReportCsv();
        return;
      }
      if (action === "site-log-export-xlsx") {
        event.preventDefault();
        await exportSiteLogReportXlsx();
        return;
      }
      if (action === "site-log-sort") {
        event.preventDefault();
        const key = String(trigger.getAttribute("data-sort-key") || "").trim();
        if (siteLogReportState.sortBy === key) {
          siteLogReportState.sortDir = siteLogReportState.sortDir === "asc" ? "desc" : "asc";
        } else {
          siteLogReportState.sortBy = key;
          siteLogReportState.sortDir = "asc";
        }
        siteLogReportState.pagination.page = 1;
        await loadSiteLogReport();
        return;
      }
      if (action === "site-log-toggle-column") {
        const key = String(trigger.getAttribute("data-column-key") || "").trim();
        if (!key) return;
        if (trigger.checked) siteLogReportState.visibleColumns.add(key);
        else siteLogReportState.visibleColumns.delete(key);
        renderSiteLogTable();
        return;
      }
      if (action === "site-log-page-prev") {
        event.preventDefault();
        if ((siteLogReportState.pagination.page || 1) > 1) {
          siteLogReportState.pagination.page -= 1;
          await loadSiteLogReport();
        }
        return;
      }
      if (action === "site-log-page-next") {
        event.preventDefault();
        if ((siteLogReportState.pagination.page || 1) < (siteLogReportState.pagination.pages || 1)) {
          siteLogReportState.pagination.page += 1;
          await loadSiteLogReport();
        }
        return;
      }
      if (action === "site-log-open" && logId > 0) {
        event.preventDefault();
        await openSiteLogDetail(logId);
        return;
      }
      if (action === "site-log-close-detail") {
        event.preventDefault();
        closeSiteLogDetail();
        return;
      }
      if (action === "site-log-pdf" && logId > 0) {
        event.preventDefault();
        await downloadSiteLogPdf(logId);
        return;
      }
      if (action === "site-log-row-csv" && logId > 0) {
        event.preventDefault();
        exportSiteLogRowCsv(logId, rowIndex);
        return;
      }
      if (action === "comm-generate" || action === "generate") {
        event.preventDefault();
        await generateCommReport();
        return;
      }
      if (action === "comm-export" || action === "export") {
        event.preventDefault();
        await exportCommReportToExcel();
      }
    } catch (error) {
      console.error(error);
      toast(error instanceof Error ? error.message : "عملیات گزارش ناموفق بود.", "error");
    }
  });

  root.addEventListener("change", (event) => {
    const target = event.target;
    if (!target) return;
    if (target.matches?.('[data-report-action="site-log-toggle-column"]')) {
      const key = String(target.getAttribute("data-column-key") || "").trim();
      if (!key) return;
      if (target.checked) siteLogReportState.visibleColumns.add(key);
      else siteLogReportState.visibleColumns.delete(key);
      renderSiteLogTable();
      return;
    }
    if (target.id === "rpt-site-organization") {
      refreshSiteLogContractOptions();
      siteLogReportState.pagination.page = 1;
      renderPowerBiUrl();
    }
    if (String(target.id || "").startsWith("rpt-site-")) {
      siteLogReportState.pagination.page = 1;
      renderPowerBiUrl();
    }
  });

  root.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target?.id === "rpt-site-search") {
      event.preventDefault();
      siteLogReportState.pagination.page = 1;
      void loadSiteLogReport();
    }
  });

  root.dataset.reportsActionsBound = "1";
}

function renderAgingTable(rows) {
  const body = document.getElementById("rpt-aging-tbody");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="7" class="center-text" style="padding:20px;color:#64748b;">داده‌ای برای Aging وجود ندارد.</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map(
      (row, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td style="font-family:monospace;">${esc(row.item_no || "-")}</td>
        <td>${esc(row.item_type || "-")}</td>
        <td>${esc(row.title || "-")}</td>
        <td>${esc(row.status_code || "-")}</td>
        <td>${esc(formatShamsiDate(row.response_due_date))}</td>
        <td>${Number(row.aging_days || 0) > 0 ? Number(row.aging_days || 0) : "-"}</td>
      </tr>`
    )
    .join("");
}

function correspondenceDirectionLabel(value) {
  const normalized = String(value || "").trim().toUpperCase();
  if (["I", "IN", "INBOUND"].includes(normalized)) return "وارده";
  if (["O", "OUT", "OUTBOUND"].includes(normalized)) return "صادره";
  return value || "-";
}

function renderCorrespondenceTable(rows) {
  const body = document.getElementById("rpt-correspondence-tbody");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="15" class="center-text" style="padding:20px;color:#64748b;">مکاتبه‌ای برای فیلترهای فعلی پیدا نشد.</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map(
      (row, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td style="font-family:monospace;">${esc(row.reference_no || "-")}</td>
        <td>${esc(formatShamsiDate(row.corr_date))}</td>
        <td>${esc(row.project_code || "-")}</td>
        <td>${esc(row.discipline_code || "-")}</td>
        <td>${esc(row.category_name || row.category_code || row.doc_type || "-")}</td>
        <td>${esc(correspondenceDirectionLabel(row.direction))}</td>
        <td>${esc(row.subject || "-")}</td>
        <td>${esc(row.sender || "-")}</td>
        <td>${esc(row.recipient || "-")}</td>
        <td>${esc(row.status || "-")}</td>
        <td>${esc(formatShamsiDate(row.due_date))}</td>
        <td>${row.is_overdue ? Number(row.aging_days || 0) : "-"}</td>
        <td>${Number(row.open_actions_count || 0)}</td>
        <td>${Number(row.attachments_count || 0)}</td>
      </tr>`
    )
    .join("");
}

function renderImpactTable(rows) {
  const body = document.getElementById("rpt-impact-tbody");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="7" class="center-text" style="padding:20px;color:#64748b;">سیگنال اثری پیدا نشد.</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map(
      (row, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td style="font-family:monospace;">${esc(row.item_no || "-")}</td>
        <td>${esc(row.item_type || "-")}</td>
        <td>${esc(row.title || "-")}</td>
        <td>${esc(row.status_code || "-")}</td>
        <td>${row.is_overdue ? "بله" : "خیر"}</td>
        <td>${row.potential_impact_time || row.potential_impact_cost || row.potential_impact_quality || row.potential_impact_safety ? "بله" : "خیر"}</td>
      </tr>`
    )
    .join("");
}

function renderCycleSummary(cycle) {
  const wrap = document.getElementById("rpt-cycle-summary");
  if (!wrap) return;

  const rfi = cycle.rfi_answered || {};
  const ncr = cycle.ncr_closed || {};
  const tech = cycle.tech_submittal_reviewed || {};
  wrap.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;">
      <div><strong>RFI</strong><div>تعداد: ${Number(rfi.count || 0)}</div><div>میانگین روز: ${rfi.avg_days ?? "-"}</div></div>
      <div><strong>NCR</strong><div>تعداد: ${Number(ncr.count || 0)}</div><div>میانگین روز: ${ncr.avg_days ?? "-"}</div></div>
      <div><strong>TECH Submittal</strong><div>تعداد: ${Number(tech.count || 0)}</div><div>میانگین روز: ${tech.avg_days ?? "-"}</div></div>
    </div>
  `;

  const rfiKpi = document.getElementById("rpt-cycle-rfi");
  if (rfiKpi) rfiKpi.textContent = String(rfi.avg_days ?? 0);
}

function setKpi(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = String(value ?? 0);
}

async function generateCommReport() {
  const params = commQueryParams();
  const shared = {
    project_code: params.project_code,
    discipline_code: params.discipline_code,
  };

  const agingBody = document.getElementById("rpt-aging-tbody");
  const impactBody = document.getElementById("rpt-impact-tbody");
  const correspondenceBody = document.getElementById("rpt-correspondence-tbody");
  if (agingBody) agingBody.innerHTML = '<tr><td colspan="7" class="center-text" style="padding:20px;color:#64748b;">در حال بارگذاری...</td></tr>';
  if (impactBody) impactBody.innerHTML = '<tr><td colspan="7" class="center-text" style="padding:20px;color:#64748b;">در حال بارگذاری...</td></tr>';
  if (correspondenceBody) correspondenceBody.innerHTML = '<tr><td colspan="15" class="center-text" style="padding:20px;color:#64748b;">در حال بارگذاری...</td></tr>';

  try {
    const [correspondenceRes, agingRes, cycleRes, impactRes] = await Promise.all([
      window.fetchWithAuth(`/api/v1/correspondence/reports/table?${buildSearchParams({ ...params, limit: 1000 })}`),
      window.fetchWithAuth(`/api/v1/comm-items/reports/aging?${buildSearchParams({ ...shared, only_overdue: false })}`),
      window.fetchWithAuth(`/api/v1/comm-items/reports/cycle-time?${buildSearchParams(shared)}`),
      window.fetchWithAuth(`/api/v1/comm-items/reports/impact-signals?${buildSearchParams(shared)}`),
    ]);

    const correspondence = await correspondenceRes.json();
    const aging = await agingRes.json();
    const cycle = await cycleRes.json();
    const impact = await impactRes.json();

    if (!correspondenceRes.ok) throw new Error(correspondence.detail || "Correspondence report failed");
    if (!agingRes.ok) throw new Error(aging.detail || "Aging report failed");
    if (!cycleRes.ok) throw new Error(cycle.detail || "Cycle-time report failed");
    if (!impactRes.ok) throw new Error(impact.detail || "Impact signals report failed");

    const correspondenceRows = asArray(correspondence.data);
    const agingRows = asArray(aging.data);
    const impactRows = asArray(impact.data);

    renderCorrespondenceTable(correspondenceRows);
    renderAgingTable(agingRows);
    renderCycleSummary(cycle || {});
    renderImpactTable(impactRows);

    setKpi("rpt-correspondence-total", Number(correspondence?.summary?.total || correspondence?.total || 0));
    setKpi("rpt-aging-overdue", Number(aging?.summary?.overdue || 0));
    setKpi("rpt-impact-count", Number(impact.count || 0));
  } catch (error) {
    console.error(error);
    toast(error instanceof Error ? error.message : "Report generation failed", "error");
  }
}

async function exportCommReportToExcel() {
  const tableCorrespondence = document.getElementById("rpt-correspondence-table");
  const tableAging = document.getElementById("rpt-aging-table");
  const tableImpact = document.getElementById("rpt-impact-table");
  if (!tableCorrespondence || !tableAging || !tableImpact) return;

  try {
    await window.ensureXlsxLoaded?.();
    if (!window.XLSX) throw new Error("XLSX library not available");

    const wb = window.XLSX.utils.book_new();
    const sheetCorrespondence = window.XLSX.utils.table_to_sheet(tableCorrespondence);
    const sheetAging = window.XLSX.utils.table_to_sheet(tableAging);
    const sheetImpact = window.XLSX.utils.table_to_sheet(tableImpact);
    window.XLSX.utils.book_append_sheet(wb, sheetCorrespondence, "Correspondence");
    window.XLSX.utils.book_append_sheet(wb, sheetAging, "Aging");
    window.XLSX.utils.book_append_sheet(wb, sheetImpact, "ImpactSignals");
    window.XLSX.writeFile(wb, `CommItems_Reports_${formatShamsiDateForFileName(new Date())}.xlsx`);
  } catch (error) {
    console.error(error);
    toast("Export failed", "error");
  }
}

function initReportsView() {
  fillCatalogSelects();
  bindReportsActions();
  void loadSiteLogCatalog().catch((error) => console.warn(error));
  activateReportsTab("site-log");
}

window.initReportsView = initReportsView;
window.generateReport = generateCommReport;
window.exportReportToExcel = exportCommReportToExcel;
