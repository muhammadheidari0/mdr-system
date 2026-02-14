// @ts-nocheck
function initReportsView() {
    bindReportsActions();
    if (window.CACHE && window.CACHE.projects) {
        const projSel = document.getElementById('rpt-project');
        if (projSel && projSel.options.length <= 1) {
            window.CACHE.projects.forEach((p) => {
                projSel.innerHTML += `<option value="${p.code}">${p.code} - ${p.project_name || p.name || ''}</option>`;
            });
        }
    }
    if (window.CACHE && window.CACHE.disciplines) {
        const discSel = document.getElementById('rpt-discipline');
        if (discSel && discSel.options.length <= 1) {
            window.CACHE.disciplines.forEach((d) => {
                discSel.innerHTML += `<option value="${d.code}">${d.name_e || d.name || d.code}</option>`;
            });
        }
    }
}

function bindReportsActions() {
    const root = document.getElementById('view-reports');
    if (!root || root.dataset.reportsActionsBound === '1') return;
    root.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-report-action]');
        if (!trigger || !root.contains(trigger)) return;
        const action = String(trigger.getAttribute('data-report-action') || '').trim().toLowerCase();
        if (action === 'generate') {
            event.preventDefault();
            generateReport();
            return;
        }
        if (action === 'export') {
            event.preventDefault();
            exportReportToExcel();
        }
    });
    root.dataset.reportsActionsBound = '1';
}

async function generateReport() {
    const tbody = document.getElementById('rpt-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" class="center-text">â³ Ø¯Ø± Ø­Ø§Ù„ Ù¾Ø±Ø¯Ø§Ø²Ø´ Ùˆ Ø¯Ø±ÛŒØ§ÙØª Ø§Ø·Ù„Ø§Ø¹Ø§Øª...</td></tr>';

    const params = new URLSearchParams();
    const project = document.getElementById('rpt-project')?.value || '';
    const disc = document.getElementById('rpt-discipline')?.value || '';
    const status = document.getElementById('rpt-status')?.value || '';
    const dateStart = document.getElementById('rpt-date-start')?.value || '';
    const dateEnd = document.getElementById('rpt-date-end')?.value || '';

    if (project) params.append('project_code', project);
    if (status) params.append('status', status);
    params.append('page', '1');
    params.append('size', '1000');

    try {
        const res = await window.fetchWithAuth(`/api/v1/mdr/search?${params.toString()}`);
        const data = await res.json();

        let items = data.items || [];
        if (disc) {
            items = items.filter((item) => getDisciplineFromCode(item.doc_number) === disc);
        }
        if (dateStart) {
            const start = new Date(`${dateStart}T00:00:00`);
            items = items.filter((item) => item.created_at && new Date(item.created_at) >= start);
        }
        if (dateEnd) {
            const end = new Date(`${dateEnd}T23:59:59`);
            items = items.filter((item) => item.created_at && new Date(item.created_at) <= end);
        }

        if (items.length > 0) {
            renderReportTable(items);
            calculateKPIs(items);
        } else {
            tbody.innerHTML = '<tr><td colspan="7" class="center-text" style="color:#ef4444;">Ù‡ÛŒÚ† Ø³Ù†Ø¯ÛŒ Ø¨Ø§ Ø§ÛŒÙ† Ù…Ø´Ø®ØµØ§Øª ÛŒØ§ÙØª Ù†Ø´Ø¯.</td></tr>';
            resetKPIs();
        }
    } catch (error) {
        console.error(error);
        tbody.innerHTML = '<tr><td colspan="7" class="center-text text-danger">Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±ØªØ¨Ø§Ø· Ø¨Ø§ Ø³Ø±ÙˆØ±</td></tr>';
    }
}

function renderReportTable(items) {
    const tbody = document.getElementById('rpt-tbody');
    if (!tbody) return;
    tbody.innerHTML = items.map((item, index) => `
        <tr>
            <td>${index + 1}</td>
            <td class="ltr-cell font-mono bold">${item.doc_number}</td>
            <td>${item.doc_title_p || item.doc_title_e || '-'}</td>
            <td>${getDisciplineFromCode(item.doc_number)}</td>
            <td class="center-text"><span class="rev-badge">${item.revision}</span></td>
            <td class="center-text">${item.status}</td>
            <td class="center-text" style="font-size:0.8rem;">
                ${item.created_at ? new Date(item.created_at).toLocaleDateString('fa-IR') : '-'}
            </td>
        </tr>
    `).join('');
}

function calculateKPIs(items) {
    const total = items.length;
    const ifcCount = items.filter((i) => i.status === 'IFC' || i.status === 'AB').length;
    const progress = total > 0 ? Math.round((ifcCount / total) * 100) : 0;

    const totalEl = document.getElementById('rpt-total-count');
    const ifcEl = document.getElementById('rpt-ifc-count');
    const revEl = document.getElementById('rpt-rev-avg');
    if (totalEl) totalEl.innerText = total;
    if (ifcEl) ifcEl.innerText = `${progress}%`;
    if (revEl) revEl.innerText = '-';
}

function resetKPIs() {
    const totalEl = document.getElementById('rpt-total-count');
    const ifcEl = document.getElementById('rpt-ifc-count');
    if (totalEl) totalEl.innerText = '0';
    if (ifcEl) ifcEl.innerText = '0%';
}

function getDisciplineFromCode(docNum) {
    if (!docNum) return '-';
    const parts = docNum.split('-');
    if (parts.length < 2) return '-';
    const middle = parts[1] || '';
    if (middle.length < 6) return '-';

    const serialMatch = middle.match(/(\d{2})$/);
    const serialLen = serialMatch ? 2 : 0;
    const pkg = middle.slice(2, middle.length - serialLen);
    return pkg.length >= 2 ? pkg.slice(0, 2) : '-';
}

async function exportReportToExcel() {
    const table = document.getElementById('report-table');
    if (!table) return;
    try {
        await window.ensureXlsxLoaded?.();
        if (!window.XLSX) {
            throw new Error('XLSX library not available');
        }
        const wb = window.XLSX.utils.table_to_book(table, { sheet: 'Report' });
        window.XLSX.writeFile(wb, `MDR_Report_${new Date().toLocaleDateString('fa-IR')}.xlsx`);
    } catch (error) {
        console.error(error);
        if (typeof showToast === 'function') {
            showToast('Ø§Ù…Ú©Ø§Ù† ØªÙˆÙ„ÛŒØ¯ ÙØ§ÛŒÙ„ Excel ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ø¯.', 'error');
        }
    }
}

window.initReportsView = initReportsView;
window.generateReport = generateReport;
window.exportReportToExcel = exportReportToExcel;

