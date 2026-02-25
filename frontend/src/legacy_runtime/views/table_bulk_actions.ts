// @ts-nocheck
(() => {
    const TABLE_SELECTOR = 'table.archive-table';
    const DEFAULT_ACTIONS = [
        { id: 'select-visible', label: 'Select all rows in page', requiresSelection: false },
        { id: 'clear-selection', label: 'Clear selection', requiresSelection: false },
        { id: 'copy-selected', label: 'Copy selected rows', requiresSelection: true },
    ];

    const tableStates = new WeakMap();
    const tableConfigs = new Map();
    let globalScanQueued = false;

    function norm(value) {
        return String(value == null ? '' : value).trim();
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function notify(type, message) {
        if (window.UI && typeof window.UI[type] === 'function') {
            window.UI[type](message);
            return;
        }
        if (typeof window.showToast === 'function') {
            const tone = type === 'error'
                ? 'error'
                : type === 'warning'
                    ? 'warning'
                    : type === 'info'
                        ? 'info'
                        : 'success';
            window.showToast(message, tone);
            return;
        }
        if (type === 'error') {
            console.error(message);
            return;
        }
        console.log(message);
    }

    async function copyTextToClipboard(text) {
        const payload = String(text || '');
        if (!payload) return false;
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            await navigator.clipboard.writeText(payload);
            return true;
        }
        const textarea = document.createElement('textarea');
        textarea.value = payload;
        textarea.setAttribute('readonly', 'readonly');
        textarea.style.position = 'fixed';
        textarea.style.top = '-9999px';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        let copied = false;
        try {
            copied = document.execCommand('copy');
        } finally {
            textarea.remove();
        }
        return copied;
    }

    function resolveTable(input) {
        if (input instanceof HTMLTableElement) return input;
        const id = norm(input);
        if (!id) return null;
        const el = document.getElementById(id);
        return el instanceof HTMLTableElement ? el : null;
    }

    function shouldHandleTable(table) {
        if (!(table instanceof HTMLTableElement)) return false;
        if (table.dataset.bulkEnabled === 'false') return false;
        if (!table.tBodies || !table.tBodies.length) return false;
        return true;
    }

    function getTableConfig(table) {
        const tableId = norm(table && table.id);
        if (!tableId) return {};
        return tableConfigs.get(tableId) || {};
    }

    function getState(table) {
        let state = tableStates.get(table);
        if (!state) {
            state = {
                selected: new Set(),
                visibleKeys: new Set(),
                bound: false,
                busy: false,
                observer: null,
                observerTarget: null,
                syncQueued: false,
                toolbarBound: false,
            };
            tableStates.set(table, state);
        }
        return state;
    }

    function getBodyRows(table) {
        const tbody = table.tBodies && table.tBodies[0];
        if (!tbody) return [];
        return Array.from(tbody.rows || []);
    }

    function getHeaderRow(table) {
        if (table.tHead && table.tHead.rows && table.tHead.rows.length) {
            return table.tHead.rows[0];
        }
        const rows = table.rows || [];
        return rows.length ? rows[0] : null;
    }

    function isDataRow(row) {
        if (!row || !row.cells || !row.cells.length) return false;
        if (row.dataset.bulkRow === 'data') return true;
        if (row.dataset.bulkRow === 'skip') return false;

        const cells = Array.from(row.cells);
        const nonBulkCells = cells.filter((cell) => !cell.classList.contains('table-bulk-cell'));
        if (!nonBulkCells.length) return false;
        if (nonBulkCells.length > 1) return true;
        const single = nonBulkCells[0];
        return Number(single.colSpan || 1) <= 1;
    }

    function getRowDisplayText(row) {
        if (!row || !row.cells) return '';
        const values = Array.from(row.cells)
            .filter((cell) => !cell.classList.contains('table-bulk-cell'))
            .map((cell) => norm(cell.textContent).replace(/\s+/g, ' '))
            .filter(Boolean);
        return values.join('\t');
    }

    function resolveRowKey(table, row, index, usedKeys) {
        const config = getTableConfig(table);
        let key = norm(row.dataset.bulkKey);
        if (!key && typeof config.getRowKey === 'function') {
            try {
                key = norm(config.getRowKey(row, index, table));
            } catch (error) {
                console.warn('TableBulk.getRowKey failed:', error);
            }
        }
        if (!key) {
            const firstDataCell = Array.from(row.cells || []).find((cell) => !cell.classList.contains('table-bulk-cell'));
            key = norm(firstDataCell && firstDataCell.textContent);
        }
        if (!key) key = `row-${index + 1}`;

        let unique = key;
        let seed = 2;
        while (usedKeys.has(unique)) {
            unique = `${key}__${seed}`;
            seed += 1;
        }
        usedKeys.add(unique);
        return unique;
    }

    function ensureHeaderCell(table) {
        const headerRow = getHeaderRow(table);
        if (!headerRow) return null;

        let cell = headerRow.querySelector('th.table-bulk-cell');
        if (!cell) {
            cell = document.createElement('th');
            cell.className = 'table-bulk-cell table-bulk-header-cell';
            cell.innerHTML = `
                <label class="table-bulk-checkbox-wrap" aria-label="Select all rows">
                    <input type="checkbox" class="table-bulk-checkbox" data-bulk-role="head-checkbox">
                </label>
            `;
            headerRow.insertBefore(cell, headerRow.firstElementChild || null);
        } else if (!cell.querySelector('input[data-bulk-role="head-checkbox"]')) {
            cell.innerHTML = `
                <label class="table-bulk-checkbox-wrap" aria-label="Select all rows">
                    <input type="checkbox" class="table-bulk-checkbox" data-bulk-role="head-checkbox">
                </label>
            `;
        }
        return cell.querySelector('input[data-bulk-role="head-checkbox"]');
    }

    function ensureRowCell(row) {
        let cell = row.querySelector('td.table-bulk-cell');
        if (!cell) {
            cell = document.createElement('td');
            cell.className = 'table-bulk-cell table-bulk-row-cell';
            cell.innerHTML = `
                <label class="table-bulk-checkbox-wrap" aria-label="Select row">
                    <input type="checkbox" class="table-bulk-checkbox" data-bulk-role="row-checkbox">
                </label>
            `;
            row.insertBefore(cell, row.firstElementChild || null);
        } else if (!cell.querySelector('input[data-bulk-role="row-checkbox"]')) {
            cell.innerHTML = `
                <label class="table-bulk-checkbox-wrap" aria-label="Select row">
                    <input type="checkbox" class="table-bulk-checkbox" data-bulk-role="row-checkbox">
                </label>
            `;
        }
        return cell.querySelector('input[data-bulk-role="row-checkbox"]');
    }

    function ensurePlaceholderColspan(table, row) {
        if (!row || !row.cells || !row.cells.length) return;
        const dataCells = Array.from(row.cells).filter((cell) => !cell.classList.contains('table-bulk-cell'));
        if (dataCells.length !== 1) return;
        const single = dataCells[0];
        const headerRow = getHeaderRow(table);
        const target = Math.max(1, Number(headerRow && headerRow.cells ? headerRow.cells.length : single.colSpan || 1));
        if (Number(single.colSpan || 1) !== target) {
            single.colSpan = target;
        }
    }

    function actionCatalog(table) {
        const config = getTableConfig(table);
        const custom = Array.isArray(config.actions) ? config.actions : [];
        const merged = [];
        const seen = new Set();
        [...custom, ...DEFAULT_ACTIONS].forEach((entry) => {
            if (!entry || !norm(entry.id)) return;
            const id = norm(entry.id);
            if (seen.has(id)) return;
            seen.add(id);
            merged.push({
                id,
                label: norm(entry.label) || id,
                requiresSelection: entry.requiresSelection !== false,
                confirmMessage: entry.confirmMessage,
            });
        });
        return merged;
    }

    function ensureToolbar(table) {
        const parent = table.parentElement;
        if (!parent) return null;
        const tableId = norm(table.id) || `table-${Math.random().toString(36).slice(2)}`;
        if (!table.id) table.id = tableId;

        let toolbar = Array.from(parent.querySelectorAll('.table-bulk-toolbar'))
            .find((node) => node.dataset && node.dataset.bulkFor === table.id) || null;
        if (!toolbar) {
            toolbar = document.createElement('div');
            toolbar.className = 'table-bulk-toolbar';
            toolbar.dataset.bulkFor = table.id;
            toolbar.innerHTML = `
                <label class="table-bulk-master-wrap">
                    <input type="checkbox" class="table-bulk-checkbox" data-bulk-role="master-checkbox">
                    <span>Select all</span>
                </label>
                <span class="table-bulk-count" data-bulk-role="selected-count">0 selected</span>
                <select class="users-toolbar-select compact table-bulk-select" data-bulk-role="action-select"></select>
                <button type="button" class="btn-archive-icon table-bulk-apply" data-bulk-role="apply-action">Apply</button>
            `;
            parent.insertBefore(toolbar, table);
        }

        const selectEl = toolbar.querySelector('[data-bulk-role="action-select"]');
        if (selectEl) {
            const current = norm(selectEl.value);
            const options = actionCatalog(table);
            selectEl.innerHTML = `
                <option value="">Bulk action...</option>
                ${options.map((item) => `<option value="${esc(item.id)}">${esc(item.label)}</option>`).join('')}
            `;
            if (options.some((item) => item.id === current)) {
                selectEl.value = current;
            }
        }
        return toolbar;
    }

    function selectedRowsMap(table) {
        const map = new Map();
        getBodyRows(table).forEach((row) => {
            const key = norm(row.dataset.bulkResolvedKey);
            if (key) map.set(key, row);
        });
        return map;
    }

    function updateToolbarAndHeader(table) {
        const state = getState(table);
        const toolbar = ensureToolbar(table);
        if (!toolbar) return;

        const selectedCount = state.selected.size;
        const totalCount = state.visibleKeys.size;
        const hasSome = selectedCount > 0;
        const hasAll = totalCount > 0 && selectedCount === totalCount;

        const headCheckbox = table.querySelector('input[data-bulk-role="head-checkbox"]');
        if (headCheckbox) {
            headCheckbox.checked = hasAll;
            headCheckbox.indeterminate = hasSome && !hasAll;
            headCheckbox.disabled = state.busy || totalCount === 0;
        }

        const masterCheckbox = toolbar.querySelector('input[data-bulk-role="master-checkbox"]');
        if (masterCheckbox) {
            masterCheckbox.checked = hasAll;
            masterCheckbox.indeterminate = hasSome && !hasAll;
            masterCheckbox.disabled = state.busy || totalCount === 0;
        }

        const countEl = toolbar.querySelector('[data-bulk-role="selected-count"]');
        if (countEl) {
            countEl.textContent = `${selectedCount} selected`;
        }

        const selectEl = toolbar.querySelector('[data-bulk-role="action-select"]');
        const applyBtn = toolbar.querySelector('[data-bulk-role="apply-action"]');
        if (applyBtn) {
            const selectedAction = norm(selectEl && selectEl.value);
            const action = actionCatalog(table).find((item) => item.id === selectedAction);
            const needsSelection = action ? action.requiresSelection !== false : true;
            const disabledBySelection = !selectedAction || (needsSelection && selectedCount === 0);
            applyBtn.disabled = state.busy || disabledBySelection;
        }
    }

    function scheduleSync(table) {
        if (!table) return;
        const state = getState(table);
        if (state.syncQueued) return;
        state.syncQueued = true;
        window.requestAnimationFrame(() => {
            state.syncQueued = false;
            syncTable(table);
        });
    }

    function syncTable(table) {
        if (!shouldHandleTable(table)) return;
        const state = getState(table);
        const rows = getBodyRows(table);
        const visibleKeys = new Set();
        const usedKeys = new Set();

        ensureHeaderCell(table);
        ensureToolbar(table);

        rows.forEach((row, index) => {
            if (!isDataRow(row)) {
                ensurePlaceholderColspan(table, row);
                row.classList.remove('bulk-row-selected');
                return;
            }

            const key = resolveRowKey(table, row, index, usedKeys);
            row.dataset.bulkResolvedKey = key;
            visibleKeys.add(key);

            const checkbox = ensureRowCell(row);
            const checked = state.selected.has(key);
            if (checkbox) {
                checkbox.checked = checked;
                checkbox.disabled = state.busy;
                checkbox.dataset.bulkKey = key;
            }
            row.classList.toggle('bulk-row-selected', checked);
        });

        Array.from(state.selected).forEach((key) => {
            if (!visibleKeys.has(key)) state.selected.delete(key);
        });
        state.visibleKeys = visibleKeys;

        updateToolbarAndHeader(table);
    }

    function setAllVisible(table, checked) {
        const state = getState(table);
        if (state.busy) return;
        const target = !!checked;
        if (!target) {
            state.selected.clear();
        } else {
            state.visibleKeys.forEach((key) => state.selected.add(key));
        }
        syncTable(table);
    }

    function clearSelection(table) {
        const state = getState(table);
        state.selected.clear();
        syncTable(table);
    }

    function setBusy(table, busy) {
        const state = getState(table);
        state.busy = !!busy;
        syncTable(table);
    }

    async function runAction(table, actionId) {
        const action = actionCatalog(table).find((item) => item.id === norm(actionId));
        if (!action) return;

        const state = getState(table);
        const selectedKeys = Array.from(state.selected);

        if (action.requiresSelection !== false && !selectedKeys.length) {
            notify('warning', 'Select at least one row.');
            return;
        }

        const confirmMessage = action.confirmMessage;
        if (confirmMessage) {
            const question = typeof confirmMessage === 'function'
                ? String(confirmMessage(selectedKeys) || '')
                : String(confirmMessage || '');
            if (question && !window.confirm(question)) return;
        }

        if (action.id === 'select-visible') {
            setAllVisible(table, true);
            return;
        }
        if (action.id === 'clear-selection') {
            clearSelection(table);
            return;
        }
        if (action.id === 'copy-selected') {
            const rowsByKey = selectedRowsMap(table);
            const lines = selectedKeys
                .map((key) => rowsByKey.get(key))
                .filter(Boolean)
                .map((row) => getRowDisplayText(row))
                .filter(Boolean);
            if (!lines.length) {
                notify('warning', 'No selected rows to copy.');
                return;
            }
            try {
                await copyTextToClipboard(lines.join('\n'));
                notify('success', `${lines.length} row(s) copied.`);
            } catch (error) {
                notify('error', 'Copy failed.');
            }
            return;
        }

        const config = getTableConfig(table);
        if (typeof config.onAction !== 'function') {
            notify('warning', 'This table has no custom bulk action handler.');
            return;
        }

        setBusy(table, true);
        try {
            await config.onAction({
                tableId: table.id,
                table,
                actionId: action.id,
                selectedKeys,
                clearSelection: () => clearSelection(table),
                setBusy: (busy) => setBusy(table, busy),
                notify,
            });
        } catch (error) {
            notify('error', error && error.message ? error.message : 'Bulk action failed.');
        } finally {
            setBusy(table, false);
        }
    }

    function bindToolbarEvents(table) {
        const state = getState(table);
        const toolbar = ensureToolbar(table);
        if (!toolbar || state.toolbarBound) return;

        toolbar.addEventListener('change', (event) => {
            const target = event && event.target;
            if (!(target instanceof HTMLElement)) return;

            if (target.matches('input[data-bulk-role="master-checkbox"]')) {
                setAllVisible(table, target.checked);
                return;
            }
            if (target.matches('select[data-bulk-role="action-select"]')) {
                updateToolbarAndHeader(table);
            }
        });

        toolbar.addEventListener('click', (event) => {
            const actionEl = event && event.target && event.target.closest
                ? event.target.closest('[data-bulk-role="apply-action"]')
                : null;
            if (!actionEl) return;
            event.preventDefault();
            const selectEl = toolbar.querySelector('select[data-bulk-role="action-select"]');
            const actionId = norm(selectEl && selectEl.value);
            if (!actionId) return;
            runAction(table, actionId).catch((error) => {
                console.error('TableBulk apply action failed:', error);
            });
        });

        state.toolbarBound = true;
    }

    function bindTableEvents(table) {
        const state = getState(table);
        if (state.bound) return;

        table.addEventListener('change', (event) => {
            const target = event && event.target;
            if (!(target instanceof HTMLElement)) return;
            const checkbox = target.closest('input[type="checkbox"][data-bulk-role]');
            if (!checkbox) return;

            const role = norm(checkbox.dataset.bulkRole);
            if (role === 'head-checkbox') {
                setAllVisible(table, checkbox.checked);
                return;
            }
            if (role === 'row-checkbox') {
                const key = norm(checkbox.dataset.bulkKey);
                if (!key) return;
                if (checkbox.checked) {
                    state.selected.add(key);
                } else {
                    state.selected.delete(key);
                }
                syncTable(table);
            }
        });

        state.bound = true;
    }

    function ensureObserver(table) {
        const state = getState(table);
        const tbody = table.tBodies && table.tBodies[0];
        if (!tbody) return;
        if (state.observer && state.observerTarget === tbody) return;

        if (state.observer) state.observer.disconnect();
        state.observer = new MutationObserver(() => {
            scheduleSync(table);
        });
        state.observer.observe(tbody, { childList: true, subtree: true });
        state.observerTarget = tbody;
    }

    function setupTable(table) {
        if (!shouldHandleTable(table)) return;
        bindTableEvents(table);
        bindToolbarEvents(table);
        ensureObserver(table);
        syncTable(table);
    }

    function scanTables() {
        const tables = Array.from(document.querySelectorAll(TABLE_SELECTOR));
        tables.forEach((table) => setupTable(table));
    }

    function scheduleGlobalScan() {
        if (globalScanQueued) return;
        globalScanQueued = true;
        window.requestAnimationFrame(() => {
            globalScanQueued = false;
            scanTables();
        });
    }

    function register(config) {
        if (!config || !norm(config.tableId)) return;
        tableConfigs.set(norm(config.tableId), { ...config });
        const table = resolveTable(config.tableId);
        if (table) setupTable(table);
    }

    function getSelection(tableId) {
        const table = resolveTable(tableId);
        if (!table) return [];
        const state = getState(table);
        return Array.from(state.selected);
    }

    const api = {
        register,
        refresh(tableId = '') {
            if (norm(tableId)) {
                const table = resolveTable(tableId);
                if (table) setupTable(table);
                return;
            }
            scanTables();
        },
        clearSelection(tableId) {
            const table = resolveTable(tableId);
            if (!table) return;
            clearSelection(table);
        },
        getSelection,
    };

    if (window.TableBulk && typeof window.TableBulk === 'object') {
        Object.assign(window.TableBulk, api);
    } else {
        window.TableBulk = api;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            scheduleGlobalScan();
        }, { once: true });
    } else {
        scheduleGlobalScan();
    }

    window.addEventListener('load', () => scheduleGlobalScan());
    if (window.AppEvents && typeof window.AppEvents.on === 'function') {
        window.AppEvents.on('view:loaded', () => scheduleGlobalScan());
        window.AppEvents.on('view:activated', () => scheduleGlobalScan());
    }
})();
