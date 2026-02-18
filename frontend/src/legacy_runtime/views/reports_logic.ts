// @ts-nocheck
import { formatShamsiDate, formatShamsiDateForFileName } from "../../lib/persian_datetime";

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function queryParams() {
  const projectCode = String(document.getElementById("rpt-project")?.value || "").trim();
  const disciplineCode = String(document.getElementById("rpt-discipline")?.value || "").trim();
  const statusCode = String(document.getElementById("rpt-status")?.value || "").trim();
  const dateStart = String(document.getElementById("rpt-date-start")?.value || "").trim();
  const dateEnd = String(document.getElementById("rpt-date-end")?.value || "").trim();

  return {
    project_code: projectCode || undefined,
    discipline_code: disciplineCode || undefined,
    status_code: statusCode || undefined,
    date_start: dateStart || undefined,
    date_end: dateEnd || undefined,
  };
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

function fillCatalogSelects() {
  if (window.CACHE && Array.isArray(window.CACHE.projects)) {
    const projectSelect = document.getElementById("rpt-project");
    if (projectSelect && projectSelect.options.length <= 1) {
      window.CACHE.projects.forEach((row) => {
        const code = String(row.code || row.project_code || "").trim();
        if (!code) return;
        const name = String(row.project_name || row.name_e || row.name_p || row.name || code).trim();
        projectSelect.innerHTML += `<option value="${esc(code)}">${esc(code)} - ${esc(name)}</option>`;
      });
    }
  }
  if (window.CACHE && Array.isArray(window.CACHE.disciplines)) {
    const disciplineSelect = document.getElementById("rpt-discipline");
    if (disciplineSelect && disciplineSelect.options.length <= 1) {
      window.CACHE.disciplines.forEach((row) => {
        const code = String(row.code || row.discipline_code || "").trim();
        if (!code) return;
        const name = String(row.name_e || row.name_p || row.name || code).trim();
        disciplineSelect.innerHTML += `<option value="${esc(code)}">${esc(code)} - ${esc(name)}</option>`;
      });
    }
  }
}

function bindReportsActions() {
  const root = document.getElementById("view-reports");
  if (!root || root.dataset.reportsActionsBound === "1") return;

  root.addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-report-action]");
    if (!trigger || !root.contains(trigger)) return;
    const action = String(trigger.getAttribute("data-report-action") || "").trim().toLowerCase();

    if (action === "generate") {
      event.preventDefault();
      await generateReport();
      return;
    }
    if (action === "export") {
      event.preventDefault();
      await exportReportToExcel();
      return;
    }
  });

  root.dataset.reportsActionsBound = "1";
}

function renderAgingTable(rows) {
  const body = document.getElementById("rpt-aging-tbody");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="7" class="center-text" style="padding:20px;color:#64748b;">No aging data.</td></tr>';
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

function renderImpactTable(rows) {
  const body = document.getElementById("rpt-impact-tbody");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="7" class="center-text" style="padding:20px;color:#64748b;">No impact signals.</td></tr>';
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
        <td>${row.is_overdue ? "Yes" : "No"}</td>
        <td>${row.potential_impact_time || row.potential_impact_cost || row.potential_impact_quality || row.potential_impact_safety ? "Yes" : "No"}</td>
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
      <div><strong>RFI</strong><div>count: ${Number(rfi.count || 0)}</div><div>avg days: ${rfi.avg_days ?? "-"}</div></div>
      <div><strong>NCR</strong><div>count: ${Number(ncr.count || 0)}</div><div>avg days: ${ncr.avg_days ?? "-"}</div></div>
      <div><strong>TECH Submittal</strong><div>count: ${Number(tech.count || 0)}</div><div>avg days: ${tech.avg_days ?? "-"}</div></div>
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

async function generateReport() {
  const params = queryParams();
  const shared = {
    project_code: params.project_code,
    discipline_code: params.discipline_code,
  };

  const agingBody = document.getElementById("rpt-aging-tbody");
  const impactBody = document.getElementById("rpt-impact-tbody");
  if (agingBody) agingBody.innerHTML = '<tr><td colspan="7" class="center-text" style="padding:20px;color:#64748b;">Loading...</td></tr>';
  if (impactBody) impactBody.innerHTML = '<tr><td colspan="7" class="center-text" style="padding:20px;color:#64748b;">Loading...</td></tr>';

  try {
    const [agingRes, cycleRes, impactRes] = await Promise.all([
      window.fetchWithAuth(`/api/v1/comm-items/reports/aging?${buildSearchParams({ ...shared, only_overdue: false })}`),
      window.fetchWithAuth(`/api/v1/comm-items/reports/cycle-time?${buildSearchParams(shared)}`),
      window.fetchWithAuth(`/api/v1/comm-items/reports/impact-signals?${buildSearchParams(shared)}`),
    ]);

    const aging = await agingRes.json();
    const cycle = await cycleRes.json();
    const impact = await impactRes.json();

    if (!agingRes.ok) throw new Error(aging.detail || "Aging report failed");
    if (!cycleRes.ok) throw new Error(cycle.detail || "Cycle-time report failed");
    if (!impactRes.ok) throw new Error(impact.detail || "Impact signals report failed");

    const agingRows = Array.isArray(aging.data) ? aging.data : [];
    const impactRows = Array.isArray(impact.data) ? impact.data : [];

    renderAgingTable(agingRows);
    renderCycleSummary(cycle || {});
    renderImpactTable(impactRows);

    setKpi("rpt-aging-overdue", Number(aging?.summary?.overdue || 0));
    setKpi("rpt-impact-count", Number(impact.count || 0));
  } catch (error) {
    console.error(error);
    if (typeof showToast === "function") {
      showToast(error instanceof Error ? error.message : "Report generation failed", "error");
    }
  }
}

async function exportReportToExcel() {
  const tableAging = document.getElementById("rpt-aging-table");
  const tableImpact = document.getElementById("rpt-impact-table");
  if (!tableAging || !tableImpact) return;

  try {
    await window.ensureXlsxLoaded?.();
    if (!window.XLSX) throw new Error("XLSX library not available");

    const wb = window.XLSX.utils.book_new();
    const sheetAging = window.XLSX.utils.table_to_sheet(tableAging);
    const sheetImpact = window.XLSX.utils.table_to_sheet(tableImpact);
    window.XLSX.utils.book_append_sheet(wb, sheetAging, "Aging");
    window.XLSX.utils.book_append_sheet(wb, sheetImpact, "ImpactSignals");
    window.XLSX.writeFile(wb, `CommItems_Reports_${formatShamsiDateForFileName(new Date())}.xlsx`);
  } catch (error) {
    console.error(error);
    if (typeof showToast === "function") showToast("Export failed", "error");
  }
}

function initReportsView() {
  fillCatalogSelects();
  bindReportsActions();
}

window.initReportsView = initReportsView;
window.generateReport = generateReport;
window.exportReportToExcel = exportReportToExcel;
