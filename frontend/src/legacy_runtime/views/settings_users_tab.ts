// @ts-nocheck
import { formatShamsiDate } from "../../lib/persian_datetime";
let currentDeleteUserId = null;
let usersCache = new Map();

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const ACCESS_SCOPE_ENDPOINT = '/api/v1/settings/permissions/scope';
const ACCESS_USER_SCOPE_ENDPOINT = '/api/v1/settings/permissions/user-scope';
const ACCESS_USER_SCOPE_UPSERT_ENDPOINT = '/api/v1/settings/permissions/user-scope/upsert';
const ACCESS_USER_ACCESS_ENDPOINT = '/api/v1/settings/permissions/user-access';
const ACCESS_SCOPE_CACHE_TTL_MS = 45 * 1000;
const ACCESS_SUGGESTION_LIMIT = 0; // 0 = unlimited
const accessState = {
  loaded: false,
  loadedAt: 0,
  loadedCategory: '',
  loading: false,
  loadingPromise: null,
  loadError: null,
  roleScope: {},
  currentRoleScope: { projects: [], disciplines: [] },
  projects: [],
  disciplines: [],
  projectMap: new Map(),
  disciplineMap: new Map(),
  userScope: {},
  currentUserId: null,
  currentUserRole: '',
  currentCategory: 'consultant',
};
const accessTags = {
  projects: new Set(),
  disciplines: new Set(),
};
let accessInputsInitialized = false;
const USERS_PAGE_ENDPOINT = '/api/v1/users/paged';
const USERS_ORGS_ENDPOINT = '/api/v1/users/organizations/catalog';
const USERS_DEFAULT_PAGE_SIZE = 10;
const USERS_TABLE_COLSPAN = 10;
const USERS_PAGE_REQUEST_TIMEOUT_MS = 20000;
const USERS_ORGS_REQUEST_TIMEOUT_MS = 8000;
const USERS_BULK_ACTION_ACTIVATE = 'users-bulk-activate';
const USERS_BULK_ACTION_DEACTIVATE = 'users-bulk-deactivate';
const USERS_BULK_ACTION_DELETE = 'users-bulk-delete';
const organizationsState = {
  loaded: false,
  loadingPromise: null,
  items: [],
};
const usersState = {
  initialized: false,
  actionsBound: false,
  bulkRegistered: false,
  loading: false,
  requestId: 0,
  page: 1,
  pageSize: USERS_DEFAULT_PAGE_SIZE,
  total: 0,
  totalPages: 1,
  count: 0,
  search: '',
  role: '',
  status: '',
  organizationType: '',
  organizationId: '',
  searchTimer: null,
  menuBound: false,
};
const USERS_MODAL_IDS = ['userModal', 'deleteModal', 'userAccessModal'];
let usersModalEventsBound = false;
let usersModalLastActiveEl = null;

function usersNotify(type, message) {
  if (window.UI && typeof window.UI[type] === 'function') {
    window.UI[type](message);
    return;
  }
  if (typeof showToast === 'function') {
    const tone = type === 'error'
      ? 'error'
      : type === 'warning'
        ? 'warning'
        : type === 'info'
          ? 'info'
          : 'success';
    showToast(message, tone);
    return;
  }
  alert(message);
}

function usersBulkBridge() {
  if (!window.TableBulk || typeof window.TableBulk !== 'object') return null;
  if (typeof window.TableBulk.register !== 'function') return null;
  return window.TableBulk;
}

function parseBulkUserIds(selectedKeys = []) {
  return (selectedKeys || [])
    .map((key) => Number(key))
    .filter((id) => Number.isFinite(id) && id > 0)
    .map((id) => Math.trunc(id));
}

function summarizeBulkErrors(items, fallback = 'Operation failed') {
  if (!items || !items.length) return '';
  const joined = items.slice(0, 3).join(' | ');
  if (items.length > 3) {
    return `${joined} | +${items.length - 3} more`;
  }
  return joined || fallback;
}

async function updateUserActiveStateBulk(userId, isActive) {
  const user = usersCache.get(String(userId));
  if (!user) {
    throw new Error(`User #${userId} is not available in current page cache`);
  }
  const payload = {
    full_name: user.full_name || null,
    role: String(user.role || 'user').toLowerCase(),
    organization_id: user.organization_id ? Number(user.organization_id) : null,
    organization_role: String(user.organization_role || 'viewer').toLowerCase(),
    is_active: !!isActive,
  };
  const response = await window.fetchWithAuth(`/api/v1/users/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  if (!response || !response.ok) {
    const body = response && typeof response.json === 'function'
      ? await response.json().catch(() => ({}))
      : {};
    throw new Error(body.detail || `Update failed (${response ? response.status : 'network'})`);
  }
}

async function deleteUserBulk(userId) {
  const response = await window.fetchWithAuth(`/api/v1/users/${userId}`, { method: 'DELETE' });
  if (!response || !response.ok) {
    const body = response && typeof response.json === 'function'
      ? await response.json().catch(() => ({}))
      : {};
    throw new Error(body.detail || `Delete failed (${response ? response.status : 'network'})`);
  }
}

async function runUsersBulkAction(actionId, selectedKeys) {
  const ids = parseBulkUserIds(selectedKeys);
  if (!ids.length) {
    usersNotify('warning', 'No user selected.');
    return;
  }

  let operationName = '';
  let confirmMessage = '';
  let task = null;

  if (actionId === USERS_BULK_ACTION_ACTIVATE) {
    operationName = 'activate';
    confirmMessage = `Activate ${ids.length} selected user(s)?`;
    task = (id) => updateUserActiveStateBulk(id, true);
  } else if (actionId === USERS_BULK_ACTION_DEACTIVATE) {
    operationName = 'deactivate';
    confirmMessage = `Deactivate ${ids.length} selected user(s)?`;
    task = (id) => updateUserActiveStateBulk(id, false);
  } else if (actionId === USERS_BULK_ACTION_DELETE) {
    operationName = 'delete';
    confirmMessage = `Delete ${ids.length} selected user(s)? This cannot be undone.`;
    task = (id) => deleteUserBulk(id);
  }

  if (!task) {
    usersNotify('warning', 'Unknown bulk action.');
    return;
  }
  if (!window.confirm(confirmMessage)) return;

  const failures = [];
  let success = 0;

  for (const id of ids) {
    try {
      await task(id);
      success += 1;
    } catch (error) {
      const message = error && error.message ? error.message : 'Request failed';
      failures.push(`#${id}: ${message}`);
    }
  }

  if (success > 0) {
    usersNotify('success', `${success} user(s) ${operationName}d.`);
  }
  if (failures.length > 0) {
    usersNotify('warning', `${failures.length} operation(s) failed. ${summarizeBulkErrors(failures)}`);
  }

  const bulk = usersBulkBridge();
  if (bulk && typeof bulk.clearSelection === 'function') {
    bulk.clearSelection('usersTable');
  }
  await loadUsers({ resetPage: false, reloadScope: true });
}

function registerUsersBulkActions() {
  if (usersState.bulkRegistered) return;
  const bulk = usersBulkBridge();
  if (!bulk) return;

  bulk.register({
    tableId: 'usersTable',
    actions: [
      { id: USERS_BULK_ACTION_ACTIVATE, label: 'Activate selected users' },
      { id: USERS_BULK_ACTION_DEACTIVATE, label: 'Deactivate selected users' },
      { id: USERS_BULK_ACTION_DELETE, label: 'Delete selected users' },
    ],
    getRowKey(row) {
      return row && row.dataset ? row.dataset.bulkKey : '';
    },
    onAction({ actionId, selectedKeys }) {
      return runUsersBulkAction(actionId, selectedKeys);
    },
  });

  usersState.bulkRegistered = true;
}

function getUsersModal(modalId) {
  return document.getElementById(modalId);
}

function isUsersModalVisible(modalEl) {
  if (!modalEl) return false;
  if (modalEl.style.display && modalEl.style.display !== 'none') return true;
  return window.getComputedStyle(modalEl).display !== 'none';
}

function hasOpenUsersModal() {
  return USERS_MODAL_IDS.some((modalId) => isUsersModalVisible(getUsersModal(modalId)));
}

function syncUsersModalScrollLock() {
  if (!document || !document.body) return;
  document.body.classList.toggle('users-modal-open', hasOpenUsersModal());
}

function openUsersModal(modalId, focusSelector = '') {
  const modal = getUsersModal(modalId);
  if (!modal) return;
  const active = document.activeElement;
  if (active && typeof active.focus === 'function') {
    usersModalLastActiveEl = active;
  }
  modal.style.display = 'flex';
  modal.setAttribute('aria-hidden', 'false');
  syncUsersModalScrollLock();
  if (!focusSelector) return;
  window.requestAnimationFrame(() => {
    const focusEl = modal.querySelector(focusSelector);
    if (focusEl && typeof focusEl.focus === 'function') {
      focusEl.focus();
      if (focusEl.select && typeof focusEl.select === 'function') focusEl.select();
    }
  });
}

function closeUsersModal(modalId, restoreFocus = true) {
  const modal = getUsersModal(modalId);
  if (!modal) return;
  modal.style.display = 'none';
  modal.setAttribute('aria-hidden', 'true');
  syncUsersModalScrollLock();
  if (!restoreFocus) return;
  if (usersModalLastActiveEl && document.contains(usersModalLastActiveEl)) {
    usersModalLastActiveEl.focus();
  }
  usersModalLastActiveEl = null;
}

function closeTopUsersModal() {
  if (isUsersModalVisible(getUsersModal('userAccessModal'))) {
    closeUserAccessModal();
    return true;
  }
  if (isUsersModalVisible(getUsersModal('deleteModal'))) {
    closeDeleteModal();
    return true;
  }
  if (isUsersModalVisible(getUsersModal('userModal'))) {
    closeUserModal();
    return true;
  }
  return false;
}

function bindUsersModalEvents() {
  if (usersModalEventsBound) return;

  document.addEventListener('keydown', (event) => {
    if (!event || event.key !== 'Escape') return;
    const closed = closeTopUsersModal();
    if (!closed) return;
    event.preventDefault();
  });

  USERS_MODAL_IDS.forEach((modalId) => {
    const modal = getUsersModal(modalId);
    if (!modal || modal.dataset.usersOverlayBound === 'true') return;
    modal.addEventListener('click', (event) => {
      if (event.target !== modal) return;
      if (modalId === 'userModal') {
        closeUserModal();
      } else if (modalId === 'deleteModal') {
        closeDeleteModal();
      } else if (modalId === 'userAccessModal') {
        closeUserAccessModal();
      }
    });
    modal.dataset.usersOverlayBound = 'true';
  });

  usersModalEventsBound = true;
}

async function fetchUsersWithTimeout(url, options = {}, timeoutMs = USERS_PAGE_REQUEST_TIMEOUT_MS) {
  const canAbort = typeof window.AbortController === 'function';
  const controller = canAbort ? new window.AbortController() : null;
  const timeoutHandle = controller
    ? window.setTimeout(() => controller.abort(), Number(timeoutMs || USERS_PAGE_REQUEST_TIMEOUT_MS))
    : null;

  try {
    const requestOptions = controller
      ? { ...options, signal: controller.signal }
      : options;
    return await window.fetchWithAuth(url, requestOptions);
  } catch (error) {
    const isAbort = !!(
      error
      && (
        error.name === 'AbortError'
        || String(error.message || '').toLowerCase().includes('aborted')
      )
    );
    if (isAbort) {
      throw new Error('Request timeout');
    }
    throw error;
  } finally {
    if (timeoutHandle !== null) window.clearTimeout(timeoutHandle);
  }
}

function roleLabel(role) {
  const map = {
    admin: 'Ù…Ø¯ÛŒØ± Ø³ÛŒØ³ØªÙ…',
    manager: 'Ø³Ø±Ù¾Ø±Ø³Øª',
    dcc: 'Ú©Ù†ØªØ±Ù„ Ù…Ø¯Ø§Ø±Ú© (DCC)',
    user: 'Ú©Ø§Ø±Ø¨Ø± Ø¹Ø§Ø¯ÛŒ',
    viewer: 'Ù…Ø´Ø§Ù‡Ø¯Ù‡â€ŒÚ¯Ø±',
  };
  return map[String(role || '').toLowerCase()] || 'Ù†Ø§Ù…Ø´Ø®Øµ';
}

function roleClass(role) {
  const key = String(role || '').toLowerCase();
  return ['admin', 'manager', 'dcc', 'user', 'viewer'].includes(key) ? key : 'user';
}

function organizationTypeLabel(value) {
  const map = {
    system: 'Ø³ÛŒØ³ØªÙ…',
    employer: 'Ú©Ø§Ø±ÙØ±Ù…Ø§',
    consultant: 'Ù…Ø´Ø§ÙˆØ±',
    contractor: 'Ù¾ÛŒÙ…Ø§Ù†Ú©Ø§Ø±',
    subcontractor: 'Ù¾ÛŒÙ…Ø§Ù†Ú©Ø§Ø± Ø¬Ø²Ø¡',
  };
  const key = String(value || '').trim().toLowerCase();
  return map[key] || 'Ù†Ø§Ù…Ø´Ø®Øµ';
}

function normalizePermissionCategory(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (raw === 'contractor' || raw === 'subcontractor') return 'contractor';
  if (raw === 'employer') return 'employer';
  return 'consultant';
}

function organizationRoleLabel(value) {
  const map = {
    admin: 'Ù…Ø¯ÛŒØ± Ø³Ø§Ø²Ù…Ø§Ù†',
    dcc: 'Ú©Ù†ØªØ±Ù„ Ù…Ø¯Ø§Ø±Ú©',
    viewer: 'Ù…Ø´Ø§Ù‡Ø¯Ù‡â€ŒÚ¯Ø±',
  };
  const key = String(value || '').trim().toLowerCase();
  return map[key] || 'Ù…Ø´Ø§Ù‡Ø¯Ù‡â€ŒÚ¯Ø±';
}

function organizationRoleClass(value) {
  const key = String(value || '').trim().toLowerCase();
  return ['admin', 'dcc', 'viewer'].includes(key) ? key : 'viewer';
}

function normalizeOrgId(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num) || num <= 0) return '';
  return String(num);
}

function filteredOrganizationsByType(typeValue = '') {
  const key = String(typeValue || '').trim().toLowerCase();
  const list = Array.isArray(organizationsState.items) ? organizationsState.items : [];
  if (!key) return list;
  return list.filter((item) => String(item && item.org_type || '').trim().toLowerCase() === key);
}

function renderUsersOrganizationFilterOptions(preserveValue = true) {
  const orgTypeEl = document.getElementById('usersOrgTypeFilter');
  const orgFilterEl = document.getElementById('usersOrganizationFilter');
  if (!orgFilterEl) return;
  const selectedType = String(orgTypeEl ? orgTypeEl.value : usersState.organizationType || '').trim().toLowerCase();
  const previous = preserveValue ? normalizeOrgId(orgFilterEl.value || usersState.organizationId) : '';
  const items = filteredOrganizationsByType(selectedType);

  orgFilterEl.innerHTML = `
    <option value="">Ù‡Ù…Ù‡ Ø³Ø§Ø²Ù…Ø§Ù†â€ŒÙ‡Ø§</option>
    ${items.map((org) => {
      const id = normalizeOrgId(org && org.id);
      const code = String(org && org.code || '').trim();
      const name = String(org && org.name || '').trim();
      const typeLabel = organizationTypeLabel(org && org.org_type);
      const label = [name || code || `#${id}`, code ? `(${code})` : '', `- ${typeLabel}`].filter(Boolean).join(' ');
      return `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`;
    }).join('')}
  `;

  const hasPrevious = previous && items.some((org) => normalizeOrgId(org && org.id) === previous);
  orgFilterEl.value = hasPrevious ? previous : '';
}

function renderUserOrganizationOptions(selectedId = '') {
  const selectEl = document.getElementById('userOrganization');
  if (!selectEl) return;
  const normalizedSelected = normalizeOrgId(selectedId);
  const items = Array.isArray(organizationsState.items) ? organizationsState.items : [];

  selectEl.innerHTML = `
    <option value="">-</option>
    ${items.map((org) => {
      const id = normalizeOrgId(org && org.id);
      const code = String(org && org.code || '').trim();
      const name = String(org && org.name || '').trim();
      const typeLabel = organizationTypeLabel(org && org.org_type);
      const label = [name || code || `#${id}`, code ? `(${code})` : '', `- ${typeLabel}`].filter(Boolean).join(' ');
      return `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`;
    }).join('')}
  `;

  if (normalizedSelected && items.some((org) => normalizeOrgId(org && org.id) === normalizedSelected)) {
    selectEl.value = normalizedSelected;
  } else {
    selectEl.value = '';
  }
}

async function ensureOrganizationsCatalogLoaded(force = false) {
  if (organizationsState.loaded && !force) {
    renderUsersOrganizationFilterOptions(true);
    return;
  }
  if (organizationsState.loadingPromise) {
    await organizationsState.loadingPromise;
    return;
  }

  organizationsState.loadingPromise = (async () => {
    const response = await fetchUsersWithTimeout(USERS_ORGS_ENDPOINT, {}, USERS_ORGS_REQUEST_TIMEOUT_MS);
    if (!response || !response.ok) {
      const body = response && typeof response.json === 'function'
        ? await response.json().catch(() => ({}))
        : {};
      throw new Error(body.detail || 'Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª ÙÙ‡Ø±Ø³Øª Ø³Ø§Ø²Ù…Ø§Ù†â€ŒÙ‡Ø§');
    }
    const payload = await response.json().catch(() => ({}));
    const items = Array.isArray(payload && payload.items) ? payload.items : [];
    organizationsState.items = items
      .filter((org) => org && org.id && org.is_active !== false)
      .map((org) => ({
        id: Number(org.id),
        code: String(org.code || '').trim(),
        name: String(org.name || '').trim(),
        org_type: String(org.org_type || '').trim().toLowerCase(),
      }));
    organizationsState.loaded = true;
    renderUsersOrganizationFilterOptions(true);
  })();

  try {
    await organizationsState.loadingPromise;
  } finally {
    organizationsState.loadingPromise = null;
  }
}

function closeAllUserActionMenus() {
  document.querySelectorAll('.users-kebab-menu.show').forEach((menu) => menu.classList.remove('show'));
  document.querySelectorAll('.users-kebab-btn[aria-expanded="true"]').forEach((btn) => btn.setAttribute('aria-expanded', 'false'));
}

function toggleUserActionMenu(event, userId) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }

  const id = String(userId || '').trim();
  if (!id) return;
  const menu = document.getElementById(`usersActionMenu-${id}`);
  if (!menu) return;

  const shouldOpen = !menu.classList.contains('show');
  closeAllUserActionMenus();

  if (!shouldOpen) return;
  menu.classList.add('show');
  if (event && event.currentTarget) {
    event.currentTarget.setAttribute('aria-expanded', 'true');
  }
}

function getUserScopeStatus(user, fallbackScope = { projects: [], disciplines: [] }) {
  const role = String((user && user.role) || '').toLowerCase();
  const summary = user && typeof user.scope_summary === 'object' && user.scope_summary
    ? user.scope_summary
    : null;

  const fallbackProjects = Array.isArray(fallbackScope.projects) ? fallbackScope.projects.length : 0;
  const fallbackDisciplines = Array.isArray(fallbackScope.disciplines) ? fallbackScope.disciplines.length : 0;

  const projectsCount = summary ? Number(summary.projects_count || 0) : fallbackProjects;
  const disciplinesCount = summary ? Number(summary.disciplines_count || 0) : fallbackDisciplines;
  const hasCustomScope = summary
    ? Boolean(summary.has_custom_scope || projectsCount > 0 || disciplinesCount > 0)
    : Boolean(fallbackProjects > 0 || fallbackDisciplines > 0);

  let status = summary ? String(summary.status || '').toLowerCase() : '';
  if (!status) status = role === 'admin' ? 'admin' : (hasCustomScope ? 'restricted' : 'full');

  if (status === 'admin') {
    return {
      key: 'admin',
      badge: 'Ø§Ø¯Ù…ÛŒÙ† Ú©Ø§Ù…Ù„',
      detail: 'Ø¯Ø³ØªØ±Ø³ÛŒ Ú©Ø§Ù…Ù„ Ø³ÛŒØ³ØªÙ…ÛŒ',
    };
  }
  if (status === 'restricted') {
    return {
      key: 'restricted',
      badge: 'Ù…Ø­Ø¯ÙˆØ¯',
      detail: `${projectsCount} Ù¾Ø±ÙˆÚ˜Ù‡ØŒ ${disciplinesCount} Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†`,
    };
  }
  return {
    key: 'full',
    badge: 'Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª',
    detail: 'Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª Ù¾Ø±ÙˆÚ˜Ù‡/Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†',
  };
}

function setUsersTableState(message, tone = 'muted') {
  const tbody = document.getElementById('usersTableBody');
  if (!tbody) return;
  closeAllUserActionMenus();
  const klass = tone === 'danger' ? 'text-danger' : 'muted';
  tbody.innerHTML = `<tr><td colspan="${USERS_TABLE_COLSPAN}" class="center-text ${klass}" style="padding: 40px;">${escapeHtml(message)}</td></tr>`;
}

function setUsersTableMeta(message) {
  const el = document.getElementById('usersTableMeta');
  if (!el) return;
  el.textContent = message || '';
}

function setUsersControlsDisabled(disabled) {
  ['usersSearchInput', 'usersRoleFilter', 'usersStatusFilter', 'usersOrgTypeFilter', 'usersOrganizationFilter', 'usersPageSize', 'usersPrevPageBtn', 'usersNextPageBtn']
    .forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.disabled = !!disabled;
    });
}

function syncUsersFiltersFromControls({ resetPage = false } = {}) {
  const searchInput = document.getElementById('usersSearchInput');
  const roleFilter = document.getElementById('usersRoleFilter');
  const statusFilter = document.getElementById('usersStatusFilter');
  const orgTypeFilter = document.getElementById('usersOrgTypeFilter');
  const orgFilter = document.getElementById('usersOrganizationFilter');
  const pageSizeEl = document.getElementById('usersPageSize');

  usersState.search = String((searchInput ? searchInput.value : '') || '').trim();
  usersState.role = String((roleFilter ? roleFilter.value : '') || '').trim().toLowerCase();
  usersState.status = String((statusFilter ? statusFilter.value : '') || '').trim().toLowerCase();
  usersState.organizationType = String((orgTypeFilter ? orgTypeFilter.value : '') || '').trim().toLowerCase();
  usersState.organizationId = normalizeOrgId(orgFilter ? orgFilter.value : '');

  const parsedPageSize = Number((pageSizeEl ? pageSizeEl.value : '') || usersState.pageSize || USERS_DEFAULT_PAGE_SIZE);
  usersState.pageSize = Number.isFinite(parsedPageSize) && parsedPageSize > 0 ? parsedPageSize : USERS_DEFAULT_PAGE_SIZE;
  if (resetPage) usersState.page = 1;
}

function buildUsersQueryString() {
  const params = new URLSearchParams();
  params.set('page', String(usersState.page));
  params.set('page_size', String(usersState.pageSize));
  if (usersState.search) params.set('q', usersState.search);
  if (usersState.role) params.set('role', usersState.role);
  if (usersState.status === 'active') params.set('is_active', 'true');
  if (usersState.status === 'inactive') params.set('is_active', 'false');
  if (usersState.organizationType) params.set('organization_type', usersState.organizationType);
  if (usersState.organizationId) params.set('organization_id', usersState.organizationId);
  return params.toString();
}

function usersPageModel() {
  const page = Number(usersState.page || 1);
  const total = Number(usersState.totalPages || 1);
  if (total <= 7) return Array.from({ length: total }, (_, idx) => idx + 1);

  const pages = [1];
  const left = Math.max(2, page - 1);
  const right = Math.min(total - 1, page + 1);
  if (left > 2) pages.push('...');
  for (let i = left; i <= right; i += 1) pages.push(i);
  if (right < total - 1) pages.push('...');
  pages.push(total);
  return pages;
}

function renderUsersPagination() {
  const prevBtn = document.getElementById('usersPrevPageBtn');
  const nextBtn = document.getElementById('usersNextPageBtn');
  const pagesWrap = document.getElementById('usersPageButtons');

  if (prevBtn) prevBtn.disabled = usersState.loading || usersState.page <= 1;
  if (nextBtn) nextBtn.disabled = usersState.loading || usersState.page >= usersState.totalPages;
  if (!pagesWrap) return;

  if (usersState.totalPages <= 1) {
    pagesWrap.innerHTML = '';
    return;
  }

  const model = usersPageModel();
  pagesWrap.innerHTML = model.map((item) => {
    if (item === '...') return '<span class="users-page-ellipsis">...</span>';
    const num = Number(item);
    const active = num === usersState.page ? 'active' : '';
    return `<button type="button" class="users-page-btn ${active}" data-users-action="go-users-page" data-page="${num}">${num}</button>`;
  }).join('');
}

function updateUsersMetaText() {
  const total = Number(usersState.total || 0);
  if (!total) {
    setUsersTableMeta('Ú©Ø§Ø±Ø¨Ø±ÛŒ Ù…Ø·Ø§Ø¨Ù‚ ÙÛŒÙ„ØªØ± Ø§Ù†ØªØ®Ø§Ø¨ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯.');
    return;
  }
  const from = ((usersState.page - 1) * usersState.pageSize) + 1;
  const to = Math.min(total, from + usersState.count - 1);
  setUsersTableMeta(`Ù†Ù…Ø§ÛŒØ´ ${from} ØªØ§ ${to} Ø§Ø² ${total} Ú©Ø§Ø±Ø¨Ø±`);
}

function bindUsersToolbar() {
  if (usersState.initialized) return;
  const root = document.getElementById('settingsUsersTabRoot');
  const searchInput = document.getElementById('usersSearchInput');
  const roleFilter = document.getElementById('usersRoleFilter');
  const statusFilter = document.getElementById('usersStatusFilter');
  const orgTypeFilter = document.getElementById('usersOrgTypeFilter');
  const orgFilter = document.getElementById('usersOrganizationFilter');
  const pageSizeEl = document.getElementById('usersPageSize');
  registerUsersBulkActions();

  if (searchInput) {
    searchInput.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      if (usersState.searchTimer) window.clearTimeout(usersState.searchTimer);
      loadUsers({ resetPage: true });
    });
    searchInput.addEventListener('input', () => {
      if (usersState.searchTimer) window.clearTimeout(usersState.searchTimer);
      usersState.searchTimer = window.setTimeout(() => {
        loadUsers({ resetPage: true });
      }, 220);
    });
  }

  if (roleFilter) roleFilter.addEventListener('change', () => loadUsers({ resetPage: true }));
  if (statusFilter) statusFilter.addEventListener('change', () => loadUsers({ resetPage: true }));
  if (orgTypeFilter) {
    orgTypeFilter.addEventListener('change', () => {
      renderUsersOrganizationFilterOptions(false);
      loadUsers({ resetPage: true });
    });
  }
  if (orgFilter) orgFilter.addEventListener('change', () => loadUsers({ resetPage: true }));
  if (pageSizeEl) pageSizeEl.addEventListener('change', () => loadUsers({ resetPage: true }));
  bindUsersModalEvents();

  if (!usersState.actionsBound) {
    document.addEventListener('click', (event) => {
      const actionEl = event && event.target && event.target.closest
        ? event.target.closest('[data-users-action]')
        : null;
      if (!actionEl) return;
      const isInUsersRoot = !!(root && root.contains(actionEl));
      const isInUsersModal = !!(actionEl.closest && actionEl.closest('#userModal, #deleteModal, #userAccessModal'));
      if (!isInUsersRoot && !isInUsersModal) return;

      const action = String(actionEl.dataset.usersAction || '').trim();
      if (!action) return;

      switch (action) {
        case 'open-create-user-modal':
          openCreateUserModal();
          break;
        case 'refresh-users-table':
          refreshUsersTable();
          break;
        case 'change-users-page':
          changeUsersPage(Number(actionEl.dataset.step || 0));
          break;
        case 'go-users-page':
          goToUsersPage(Number(actionEl.dataset.page || 0));
          break;
        case 'close-user-modal':
          closeUserModal();
          break;
        case 'save-user':
          saveUser();
          break;
        case 'close-delete-modal':
          closeDeleteModal();
          break;
        case 'confirm-delete-user':
          confirmDelete();
          break;
        case 'close-user-access-modal':
          closeUserAccessModal();
          break;
        case 'clear-user-access-scope':
          clearUserAccessScope();
          break;
        case 'save-user-access-scope':
          saveUserAccessScope();
          break;
        case 'toggle-user-action-menu':
          toggleUserActionMenu(event, Number(actionEl.dataset.userId || 0));
          break;
        case 'open-user-access-modal':
          closeAllUserActionMenus();
          openUserAccessModal(Number(actionEl.dataset.userId || 0));
          break;
        case 'edit-user':
          closeAllUserActionMenus();
          editUser(Number(actionEl.dataset.userId || 0));
          break;
        case 'delete-user':
          closeAllUserActionMenus();
          deleteUser(Number(actionEl.dataset.userId || 0));
          break;
        case 'remove-access-tag':
          removeAccessTag(actionEl.dataset.tagType || '', actionEl.dataset.tagCode || '');
          break;
        default:
          break;
      }
    });
    usersState.actionsBound = true;
  }

  if (!usersState.menuBound) {
    document.addEventListener('click', (event) => {
      const target = event && event.target;
      if (target && target.closest && target.closest('.users-kebab')) return;
      closeAllUserActionMenus();
    });
    document.addEventListener('keydown', (event) => {
      if (event && event.key === 'Escape' && !hasOpenUsersModal()) closeAllUserActionMenus();
    });
    usersState.menuBound = true;
  }

  usersState.initialized = true;
}

function goToUsersPage(page) {
  const target = Number(page);
  if (!Number.isFinite(target)) return;
  if (target < 1 || target > usersState.totalPages || target === usersState.page) return;
  usersState.page = target;
  loadUsers();
}

function changeUsersPage(step) {
  const delta = Number(step || 0);
  if (!Number.isFinite(delta) || !delta) return;
  goToUsersPage(usersState.page + delta);
}

function refreshUsersTable() {
  loadUsers({ resetPage: false, reloadScope: true });
}

async function loadUsers(options = {}) {
  const tbody = document.getElementById('usersTableBody');
  if (!tbody) return;

  const requestId = ++usersState.requestId;
  bindUsersToolbar();
  void ensureOrganizationsCatalogLoaded(false).catch((orgError) => {
    console.warn('Load organization catalog failed:', orgError);
  });
  syncUsersFiltersFromControls({ resetPage: !!options.resetPage });
  usersState.loading = true;
  setUsersControlsDisabled(true);
  setUsersTableState('Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ú©Ø§Ø±Ø¨Ø±Ø§Ù†...');
  setUsersTableMeta('Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø±ÙˆØ²Ø±Ø³Ø§Ù†ÛŒ Ù„ÛŒØ³Øª Ú©Ø§Ø±Ø¨Ø±Ø§Ù†...');

  try {
    const query = buildUsersQueryString();
    let data = null;

    const response = await fetchUsersWithTimeout(`${USERS_PAGE_ENDPOINT}?${query}`, {}, USERS_PAGE_REQUEST_TIMEOUT_MS);
    if (response && response.ok) {
      data = await response.json();
    } else {
      const status = response ? response.status : 0;
      if (status === 404 || status === 405) {
        const skip = Math.max(0, (usersState.page - 1) * usersState.pageSize);
        const legacyQuery = new URLSearchParams();
        legacyQuery.set('skip', String(skip));
        legacyQuery.set('limit', String(usersState.pageSize));
        if (usersState.search) legacyQuery.set('q', usersState.search);
        if (usersState.role) legacyQuery.set('role', usersState.role);
        if (usersState.status === 'active') legacyQuery.set('is_active', 'true');
        if (usersState.status === 'inactive') legacyQuery.set('is_active', 'false');
        if (usersState.organizationType) legacyQuery.set('organization_type', usersState.organizationType);
        if (usersState.organizationId) legacyQuery.set('organization_id', usersState.organizationId);

        const legacyResponse = await fetchUsersWithTimeout(`/api/v1/users/?${legacyQuery.toString()}`, {}, USERS_PAGE_REQUEST_TIMEOUT_MS);
        if (!legacyResponse || !legacyResponse.ok) {
          let legacyErr = {};
          if (legacyResponse && typeof legacyResponse.json === 'function') {
            legacyErr = await legacyResponse.json().catch(() => ({}));
          }
          throw new Error(legacyErr.detail || 'Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª Ù„ÛŒØ³Øª Ú©Ø§Ø±Ø¨Ø±Ø§Ù†');
        }

        const legacyItems = await legacyResponse.json();
        const items = Array.isArray(legacyItems) ? legacyItems : [];
        data = {
          items,
          pagination: {
            total: items.length,
            page: 1,
            page_size: usersState.pageSize,
            total_pages: 1,
            count: items.length,
          },
        };
      } else {
        let errData = {};
        if (response && typeof response.json === 'function') {
          errData = await response.json().catch(() => ({}));
        }
        throw new Error(errData.detail || 'Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª Ù„ÛŒØ³Øª Ú©Ø§Ø±Ø¨Ø±Ø§Ù†');
      }
    }

    if (requestId !== usersState.requestId) return;
    if (data && data.detail) throw new Error(data.detail);

    const pagination = (data && data.pagination) || {};
    const users = Array.isArray(data && data.items) ? data.items : [];
    usersState.total = Number(pagination.total || 0);
    usersState.page = Number(pagination.page || usersState.page || 1);
    usersState.pageSize = Number(pagination.page_size || usersState.pageSize || USERS_DEFAULT_PAGE_SIZE);
    usersState.totalPages = Math.max(1, Number(pagination.total_pages || 1));
    usersState.count = Number(pagination.count || users.length || 0);

    const pageSizeEl = document.getElementById('usersPageSize');
    if (pageSizeEl && String(pageSizeEl.value) !== String(usersState.pageSize)) {
      pageSizeEl.value = String(usersState.pageSize);
    }

    usersCache = new Map(users.map((u) => [String(u.id), u]));

    const hasScopeSummary = users.every((u) => u && typeof u.scope_summary === 'object' && u.scope_summary !== null);
    let scopeMap = accessState.userScope || {};
    const scopeMapIsEmpty = !scopeMap || Object.keys(scopeMap).length === 0;
    if ((!hasScopeSummary && scopeMapIsEmpty) || (!hasScopeSummary && options.reloadScope)) {
      try {
        const scopePayload = await accessRequest(ACCESS_USER_SCOPE_ENDPOINT);
        scopeMap = (scopePayload && scopePayload.scope) || {};
        accessState.userScope = scopeMap;
      } catch (scopeError) {
        console.warn('Load user scope map failed:', scopeError);
      }
    }

    if (!users.length) {
      setUsersTableState('Ú©Ø§Ø±Ø¨Ø±ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯');
      renderUsersPagination();
      updateUsersMetaText();
      return;
    }

    closeAllUserActionMenus();
    tbody.innerHTML = users.map((user) => {
      const isAdmin = String(user.role || '').toLowerCase() === 'admin';
      const organization = user && typeof user.organization === 'object' ? user.organization : null;
      const organizationName = organization ? (organization.name || organization.code || '-') : '-';
      const organizationMeta = organization
        ? [organization.code || '-', organizationTypeLabel(organization.org_type)].filter(Boolean).join(' - ')
        : '-';
      const organizationRole = organizationRoleLabel(user.organization_role);
      const userScope = scopeMap[String(user.id)] || { projects: [], disciplines: [] };
      const scopeStatus = getUserScopeStatus(user, userScope);
      const actionMenuId = `usersActionMenu-${user.id}`;
      return `
        <tr data-bulk-key="${user.id}" data-user-id="${user.id}">
          <td>${user.id}</td>
          <td>${escapeHtml(user.email)}</td>
          <td>${escapeHtml(user.full_name || '-')}</td>
          <td><span class="role-badge ${roleClass(user.role)}">${roleLabel(user.role)}</span></td>
          <td>
            <div class="scope-status-cell">
              <span class="scope-badge full">${escapeHtml(organizationName)}</span>
              <span class="scope-detail">${escapeHtml(organizationMeta)}</span>
            </div>
          </td>
          <td><span class="role-badge ${organizationRoleClass(user.organization_role)}">${escapeHtml(organizationRole)}</span></td>
          <td><span class="status-badge ${user.is_active ? 'active' : 'inactive'}">${user.is_active ? 'ÙØ¹Ø§Ù„' : 'ØºÛŒØ±ÙØ¹Ø§Ù„'}</span></td>
          <td>
            <div class="scope-status-cell">
              <span class="scope-badge ${scopeStatus.key}">${escapeHtml(scopeStatus.badge)}</span>
              <span class="scope-detail">${escapeHtml(scopeStatus.detail)}</span>
            </div>
          </td>
          <td>${formatShamsiDate(user.created_at)}</td>
          <td>
            <div class="users-kebab">
              <button
                type="button"
                class="users-kebab-btn"
                data-users-action="toggle-user-action-menu" data-user-id="${user.id}"
                aria-label="Ø¹Ù…Ù„ÛŒØ§Øª"
                aria-haspopup="true"
                aria-expanded="false"
                aria-controls="${actionMenuId}"
              >
                <span class="material-icons-round">more_vert</span>
              </button>
              <div class="users-kebab-menu" id="${actionMenuId}" role="menu">
                <button type="button" class="users-kebab-item" data-users-action="open-user-access-modal" data-user-id="${user.id}" ${isAdmin ? 'disabled' : ''}>
                  <span class="material-icons-round">vpn_key</span>
                  Ù…Ø¯ÛŒØ±ÛŒØª Ø¯Ø³ØªØ±Ø³ÛŒ
                </button>
                <button type="button" class="users-kebab-item" data-users-action="edit-user" data-user-id="${user.id}">
                  <span class="material-icons-round">edit</span>
                  ÙˆÛŒØ±Ø§ÛŒØ´ Ú©Ø§Ø±Ø¨Ø±
                </button>
                <button type="button" class="users-kebab-item danger" data-users-action="delete-user" data-user-id="${user.id}">
                  <span class="material-icons-round">delete</span>
                  Ø­Ø°Ù Ú©Ø§Ø±Ø¨Ø±
                </button>
              </div>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    renderUsersPagination();
    updateUsersMetaText();
  } catch (error) {
    if (requestId !== usersState.requestId) return;
    console.error('Load users error:', error);
    setUsersTableState('Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ú©Ø§Ø±Ø¨Ø±Ø§Ù†', 'danger');
    setUsersTableMeta('Ø¯Ø±ÛŒØ§ÙØª Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯.');
    usersCache = new Map();
  } finally {
    if (requestId !== usersState.requestId) return;
    usersState.loading = false;
    setUsersControlsDisabled(false);
    renderUsersPagination();
  }
}

async function openCreateUserModal() {
  try {
    await ensureOrganizationsCatalogLoaded(false);
  } catch (error) {
    console.warn('Organization catalog unavailable in create modal:', error);
  }
  document.getElementById('userModalTitle').textContent = 'Ø§ÛŒØ¬Ø§Ø¯ Ú©Ø§Ø±Ø¨Ø± Ø¬Ø¯ÛŒØ¯';
  document.getElementById('userForm').reset();
  document.getElementById('userId').value = '';
  document.getElementById('userEmail').disabled = false;
  document.getElementById('userPassword').required = true;
  document.getElementById('passwordLabel').textContent = 'Ø±Ù…Ø² Ø¹Ø¨ÙˆØ± *';
  document.getElementById('passwordHelp').textContent = 'Ø¨Ø±Ø§ÛŒ Ú©Ø§Ø±Ø¨Ø± Ø¬Ø¯ÛŒØ¯ Ø±Ù…Ø² Ø¹Ø¨ÙˆØ± Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª';
  renderUserOrganizationOptions('');
  document.getElementById('userOrganizationRole').value = 'viewer';
  document.getElementById('userActive').checked = true;
  openUsersModal('userModal', '#userEmail');
}

async function editUser(userId) {
  const user = usersCache.get(String(userId));
  if (!user) {
    UI.error('Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ú©Ø§Ø±Ø¨Ø± Ø¨Ø±Ø§ÛŒ ÙˆÛŒØ±Ø§ÛŒØ´ ÛŒØ§ÙØª Ù†Ø´Ø¯. Ù„Ø·ÙØ§Ù‹ Ù„ÛŒØ³Øª Ø±Ø§ Ø¨Ø±ÙˆØ²Ø±Ø³Ø§Ù†ÛŒ Ú©Ù†ÛŒØ¯.');
    return;
  }

  try {
    await ensureOrganizationsCatalogLoaded(false);
  } catch (error) {
    console.warn('Organization catalog unavailable in edit modal:', error);
  }

  document.getElementById('userModalTitle').textContent = 'ÙˆÛŒØ±Ø§ÛŒØ´ Ú©Ø§Ø±Ø¨Ø±';
  document.getElementById('userId').value = userId;
  document.getElementById('userEmail').value = user.email || '';
  document.getElementById('userEmail').disabled = true;
  document.getElementById('userFullName').value = user.full_name || '';
  document.getElementById('userRole').value = user.role || 'user';
  renderUserOrganizationOptions(user.organization_id);
  const orgRoleEl = document.getElementById('userOrganizationRole');
  const orgRoleValue = String(user.organization_role || 'viewer').toLowerCase();
  orgRoleEl.value = ['admin', 'dcc', 'viewer'].includes(orgRoleValue) ? orgRoleValue : 'viewer';
  document.getElementById('userActive').checked = !!user.is_active;
  document.getElementById('userPassword').value = '';
  document.getElementById('userPassword').required = false;
  document.getElementById('passwordLabel').textContent = 'Ø±Ù…Ø² Ø¹Ø¨ÙˆØ±';
  document.getElementById('passwordHelp').textContent = 'ØªØºÛŒÛŒØ± Ø±Ù…Ø² Ø§Ø² Ù…Ù†ÙˆÛŒ Ú©Ø§Ø±Ø¨Ø± Ø§Ù†Ø¬Ø§Ù… Ù…ÛŒâ€ŒØ´ÙˆØ¯';
  openUsersModal('userModal', '#userFullName');
}

function closeUserModal() {
  const form = document.getElementById('userForm');
  if (form && typeof form.reset === 'function') form.reset();
  const errorInputs = form && form.querySelectorAll ? form.querySelectorAll('.form-input-error') : [];
  if (errorInputs && typeof errorInputs.forEach === 'function') {
    errorInputs.forEach((input) => input.classList.remove('form-input-error'));
  }
  closeUsersModal('userModal');
}

async function saveUser() {
  const userId = document.getElementById('userId').value;
  const email = document.getElementById('userEmail').value;
  const fullName = document.getElementById('userFullName').value;
  const password = document.getElementById('userPassword').value;
  const role = document.getElementById('userRole').value;
  const organizationId = normalizeOrgId(document.getElementById('userOrganization').value);
  const organizationRole = String(document.getElementById('userOrganizationRole').value || 'viewer').trim().toLowerCase();
  const isActive = document.getElementById('userActive').checked;

  if (!userId && !email) { UI.error('Ø§ÛŒÙ…ÛŒÙ„ Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª'); return; }
  if (!userId && !password) { UI.error('Ø±Ù…Ø² Ø¹Ø¨ÙˆØ± Ø¨Ø±Ø§ÛŒ Ú©Ø§Ø±Ø¨Ø± Ø¬Ø¯ÛŒØ¯ Ø§Ù„Ø²Ø§Ù…ÛŒ Ø§Ø³Øª'); return; }

  const btn = document.querySelector('#userModal .btn-primary');
  UI.setBtnLoading(btn, true);

  try {
    const url = userId ? `/api/v1/users/${userId}` : '/api/v1/users/';
    const method = userId ? 'PUT' : 'POST';
    const body = userId
      ? {
        full_name: fullName,
        role: role,
        organization_id: organizationId ? Number(organizationId) : null,
        organization_role: organizationRole || 'viewer',
        is_active: isActive,
      }
      : {
        email: email,
        password: password,
        full_name: fullName,
        role: role,
        organization_id: organizationId ? Number(organizationId) : null,
        organization_role: organizationRole || 'viewer',
        is_active: isActive,
      };

    const response = await window.fetchWithAuth(url, { method, body: JSON.stringify(body) });
    if (response && response.ok) {
      UI.success(userId ? 'Ú©Ø§Ø±Ø¨Ø± Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª ÙˆÛŒØ±Ø§ÛŒØ´ Ø´Ø¯' : 'Ú©Ø§Ø±Ø¨Ø± Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø§ÛŒØ¬Ø§Ø¯ Ø´Ø¯');
      closeUserModal();
      loadUsers({ resetPage: !userId });
    } else {
      const data = await response.json().catch(() => ({}));
      UI.error(data.detail || 'Ø®Ø·Ø§ Ø¯Ø± Ø°Ø®ÛŒØ±Ù‡ Ø§Ø·Ù„Ø§Ø¹Ø§Øª');
    }
  } catch (error) {
    console.error('Save user error:', error);
  } finally {
    UI.setBtnLoading(btn, false);
  }
}

function deleteUser(userId) {
  const user = usersCache.get(String(userId));
  currentDeleteUserId = userId;
  document.getElementById('deleteUserName').textContent = (user && user.email) || `#${userId}`;
  openUsersModal('deleteModal');
}

function closeDeleteModal() {
  closeUsersModal('deleteModal');
  currentDeleteUserId = null;
}

async function confirmDelete() {
  if (!currentDeleteUserId) return;
  try {
    const response = await window.fetchWithAuth(`/api/v1/users/${currentDeleteUserId}`, { method: 'DELETE' });
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      showToast('Ú©Ø§Ø±Ø¨Ø± Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø­Ø°Ù Ø´Ø¯', 'success');
      closeDeleteModal();
      loadUsers();
    } else {
      showToast(data.detail || 'Ø®Ø·Ø§ Ø¯Ø± Ø­Ø°Ù Ú©Ø§Ø±Ø¨Ø±', 'error');
    }
  } catch (error) {
    console.error('Delete user error:', error);
    showToast('Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±ØªØ¨Ø§Ø· Ø¨Ø§ Ø³Ø±ÙˆØ±', 'error');
  }
}

function accessNotify(type, message) {
  if (window.UI && typeof window.UI[type] === 'function') {
    window.UI[type](message);
    return;
  }
  if (typeof showToast === 'function') {
    const toastType = type === 'error' ? 'error' : type === 'warning' ? 'warning' : type === 'info' ? 'info' : 'success';
    showToast(message, toastType);
    return;
  }
  alert(message);
}

function setAccessSourceStatus(message, tone = 'info') {
  const el = document.getElementById('accessSourceStatus');
  if (!el) return;
  el.textContent = message || '';
  el.dataset.tone = tone || 'info';
}

function normalizeTagValue(value) {
  return String(value || '').trim().toUpperCase();
}

function buildOptionMap(list) {
  const map = new Map();
  (list || []).forEach((item) => {
    const code = normalizeTagValue(item.code);
    if (code) map.set(code, item.name || code);
  });
  return map;
}

function normalizeList(values) {
  return (values || []).map((value) => normalizeTagValue(value)).filter(Boolean);
}

function computeEffectiveScope(roleValues, userValues) {
  const roleSet = new Set(normalizeList(roleValues));
  const userSet = new Set(normalizeList(userValues));
  if (roleSet.size && userSet.size) {
    const intersection = Array.from(roleSet).filter((value) => userSet.has(value)).sort();
    return { values: intersection, restricted: true };
  }
  if (roleSet.size) return { values: Array.from(roleSet).sort(), restricted: true };
  if (userSet.size) return { values: Array.from(userSet).sort(), restricted: true };
  return { values: [], restricted: false };
}

function getRoleScopeForUser(role) {
  const roleKey = String(role || '').toLowerCase();
  const scope = accessState.roleScope && accessState.roleScope[roleKey];
  if (scope && typeof scope === 'object') {
    return {
      projects: normalizeList(scope.projects),
      disciplines: normalizeList(scope.disciplines),
    };
  }
  return { projects: [], disciplines: [] };
}

async function accessRequest(url, options = {}) {
  const fn = typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : fetch;
  const res = await fn(url, options);
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.clone().json();
      message = body.detail || body.message || message;
    } catch (_) {}
    throw new Error(message);
  }
  return res.json();
}

function setAccessLoading(isLoading) {
  const loader = document.getElementById('userAccessLoading');
  const content = document.getElementById('userAccessContent');
  if (loader) loader.classList.toggle('active', !!isLoading);
  if (content) content.style.opacity = isLoading ? '0.6' : '1';
}

function setAccessInputsDisabled(disabled) {
  const projectsInput = document.getElementById('accessProjectsInput');
  const disciplinesInput = document.getElementById('accessDisciplinesInput');
  const projectsWrap = document.getElementById('accessProjectsTagsInput');
  const disciplinesWrap = document.getElementById('accessDisciplinesTagsInput');
  if (projectsInput) projectsInput.disabled = !!disabled;
  if (disciplinesInput) disciplinesInput.disabled = !!disabled;
  if (projectsWrap) projectsWrap.classList.toggle('disabled', !!disabled);
  if (disciplinesWrap) disciplinesWrap.classList.toggle('disabled', !!disabled);
  const saveBtn = document.getElementById('userAccessSaveBtn');
  const clearBtn = document.getElementById('userAccessClearBtn');
  if (saveBtn) saveBtn.disabled = !!disabled;
  if (clearBtn) clearBtn.disabled = !!disabled;
}

async function loadAccessScopeData(force = false, category = 'consultant') {
  const categoryKey = normalizePermissionCategory(category);
  const cacheFresh = accessState.loaded
    && accessState.loadedCategory === categoryKey
    && (Date.now() - Number(accessState.loadedAt || 0) < ACCESS_SCOPE_CACHE_TTL_MS);
  if (cacheFresh && !force) {
    const projectsCount = accessState.projects.length;
    const disciplinesCount = accessState.disciplines.length;
    if (projectsCount || disciplinesCount) {
      setAccessSourceStatus(`Ù…Ù†Ø§Ø¨Ø¹ ${organizationTypeLabel(categoryKey)} Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ø´Ø¯: ${projectsCount} Ù¾Ø±ÙˆÚ˜Ù‡ØŒ ${disciplinesCount} Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†`, 'info');
    } else {
      setAccessSourceStatus('ÙÙ‡Ø±Ø³Øª Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§ Ùˆ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†â€ŒÙ‡Ø§ Ø®Ø§Ù„ÛŒ Ø§Ø³Øª. Ø§Ø¨ØªØ¯Ø§ Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ù¾Ø§ÛŒÙ‡ Ø±Ø§ Ø«Ø¨Øª Ú©Ù†ÛŒØ¯.', 'warning');
    }
    return;
  }
  if (accessState.loadingPromise) {
    await accessState.loadingPromise;
    return;
  }
  accessState.loading = true;
  accessState.loadError = null;
  accessState.loadingPromise = (async () => {
  try {
    const scopeUrl = `${ACCESS_SCOPE_ENDPOINT}?category=${encodeURIComponent(categoryKey)}`;
    const [scopePayload, userScopePayload] = await Promise.all([
      accessRequest(scopeUrl),
      accessRequest(ACCESS_USER_SCOPE_ENDPOINT),
    ]);

    accessState.roleScope = (scopePayload && scopePayload.scope) || {};
    accessState.projects = Array.isArray(scopePayload && scopePayload.projects) ? scopePayload.projects : [];
    accessState.disciplines = Array.isArray(scopePayload && scopePayload.disciplines) ? scopePayload.disciplines : [];
    accessState.projectMap = buildOptionMap(accessState.projects);
    accessState.disciplineMap = buildOptionMap(accessState.disciplines);
    accessState.userScope = (userScopePayload && userScopePayload.scope) || {};
    accessState.loadedCategory = categoryKey;
    accessState.loaded = true;
    accessState.loadedAt = Date.now();
    const projectsCount = accessState.projects.length;
    const disciplinesCount = accessState.disciplines.length;
    if (projectsCount || disciplinesCount) {
      setAccessSourceStatus(`Ù…Ù†Ø§Ø¨Ø¹ ${organizationTypeLabel(categoryKey)} Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ø´Ø¯: ${projectsCount} Ù¾Ø±ÙˆÚ˜Ù‡ØŒ ${disciplinesCount} Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†`, 'info');
    } else {
      setAccessSourceStatus('ÙÙ‡Ø±Ø³Øª Ù¾Ø±ÙˆÚ˜Ù‡â€ŒÙ‡Ø§ Ùˆ Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†â€ŒÙ‡Ø§ Ø®Ø§Ù„ÛŒ Ø§Ø³Øª. Ø§Ø¨ØªØ¯Ø§ Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ù¾Ø§ÛŒÙ‡ Ø±Ø§ Ø«Ø¨Øª Ú©Ù†ÛŒØ¯.', 'warning');
    }
  } catch (error) {
    accessState.loaded = false;
    accessState.loadError = error;
    setAccessSourceStatus('Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ÛŒ Ù¾Ø§ÛŒÙ‡ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯. Ø¯Ø³ØªØ±Ø³ÛŒ Ø§Ø¯Ù…ÛŒÙ† Ø±Ø§ Ø¨Ø±Ø±Ø³ÛŒ Ú©Ù†ÛŒØ¯.', 'error');
    throw error;
  } finally {
    accessState.loading = false;
    accessState.loadingPromise = null;
  }
  })();
  await accessState.loadingPromise;
}

async function loadUserAccessEffective(userId) {
  if (!userId) return null;
  return accessRequest(`${ACCESS_USER_ACCESS_ENDPOINT}/${encodeURIComponent(userId)}`);
}

function updateAccessSummary(user) {
  const summary = document.getElementById('userAccessSummary');
  if (!summary || !user) return;
  const org = user && typeof user.organization === 'object' ? user.organization : null;
  const category = normalizePermissionCategory(org ? org.org_type : null);
  summary.innerHTML = `
    <div><strong>Ú©Ø§Ø±Ø¨Ø±:</strong> ${escapeHtml(user.full_name || user.email || '-')}</div>
    <div><strong>Ø§ÛŒÙ…ÛŒÙ„:</strong> ${escapeHtml(user.email || '-')}</div>
    <div><strong>Ù†Ù‚Ø´:</strong> ${escapeHtml(roleLabel(user.role))}</div>
    <div><strong>Ø¯Ø³ØªÙ‡ Ø¯Ø³ØªØ±Ø³ÛŒ:</strong> ${escapeHtml(organizationTypeLabel(category))}</div>
    <div><strong>ÙˆØ¶Ø¹ÛŒØª:</strong> ${user.is_active ? 'ÙØ¹Ø§Ù„' : 'ØºÛŒØ±ÙØ¹Ø§Ù„'}</div>
  `;
}

function getTagMap(type) {
  return type === 'projects' ? accessState.projectMap : accessState.disciplineMap;
}

function formatPreviewValues(values, restricted, map) {
  if (!restricted) {
    return '<span class="preview-empty">Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª</span>';
  }
  if (!values.length) {
    return '<span class="preview-empty is-denied">ÙØ§Ù‚Ø¯ Ø¯Ø³ØªØ±Ø³ÛŒ</span>';
  }

  const max = 6;
  const sliced = values.slice(0, max);
  const chips = sliced.map((code) => {
    const name = (map ? map.get(code) : undefined);
    const title = name && name !== code ? `${code} - ${name}` : code;
    if (name && name !== code) {
      return `<span class="preview-chip" title="${escapeHtml(title)}">${escapeHtml(code)}<span class="preview-chip-name">${escapeHtml(name)}</span></span>`;
    }
    return `<span class="preview-chip" title="${escapeHtml(title)}">${escapeHtml(code)}</span>`;
  });

  if (values.length > max) {
    chips.push(`<span class="preview-chip preview-more">+${values.length - max}</span>`);
  }

  return chips.join('');
}

function updateAccessPreview() {
  const roleProjectsEl = document.getElementById('accessPreviewRoleProjects');
  if (!roleProjectsEl) return;

  const roleScope = accessState.currentRoleScope || getRoleScopeForUser(accessState.currentUserRole);
  const roleProjects = normalizeList(roleScope.projects);
  const roleDisciplines = normalizeList(roleScope.disciplines);
  const userProjects = Array.from(accessTags.projects || []);
  const userDisciplines = Array.from(accessTags.disciplines || []);

  const effectiveProjects = computeEffectiveScope(roleProjects, userProjects);
  const effectiveDisciplines = computeEffectiveScope(roleDisciplines, userDisciplines);

  const projectsMap = getTagMap('projects');
  const disciplinesMap = getTagMap('disciplines');

  roleProjectsEl.innerHTML = formatPreviewValues(roleProjects, roleProjects.length > 0, projectsMap);
  const roleDisciplinesEl = document.getElementById('accessPreviewRoleDisciplines');
  if (roleDisciplinesEl) {
    roleDisciplinesEl.innerHTML = formatPreviewValues(roleDisciplines, roleDisciplines.length > 0, disciplinesMap);
  }

  const userProjectsEl = document.getElementById('accessPreviewUserProjects');
  if (userProjectsEl) {
    userProjectsEl.innerHTML = formatPreviewValues(userProjects, userProjects.length > 0, projectsMap);
  }
  const userDisciplinesEl = document.getElementById('accessPreviewUserDisciplines');
  if (userDisciplinesEl) {
    userDisciplinesEl.innerHTML = formatPreviewValues(userDisciplines, userDisciplines.length > 0, disciplinesMap);
  }

  const effectiveProjectsEl = document.getElementById('accessPreviewEffectiveProjects');
  if (effectiveProjectsEl) {
    effectiveProjectsEl.innerHTML = formatPreviewValues(effectiveProjects.values, effectiveProjects.restricted, projectsMap);
  }
  const effectiveDisciplinesEl = document.getElementById('accessPreviewEffectiveDisciplines');
  if (effectiveDisciplinesEl) {
    effectiveDisciplinesEl.innerHTML = formatPreviewValues(effectiveDisciplines.values, effectiveDisciplines.restricted, disciplinesMap);
  }

  const warningEl = document.getElementById('accessPreviewWarning');
  if (warningEl) {
    const hasEmptyRestricted =
      (effectiveProjects.restricted && effectiveProjects.values.length === 0) ||
      (effectiveDisciplines.restricted && effectiveDisciplines.values.length === 0);
    warningEl.style.display = hasEmptyRestricted ? 'block' : 'none';
  }
}

async function refreshAccessPreviewFromServer(userId, syncTags = false) {
  try {
    const payload = await loadUserAccessEffective(userId);
    if (payload && payload.role_scope) {
      accessState.currentRoleScope = {
        projects: normalizeList(payload.role_scope.projects),
        disciplines: normalizeList(payload.role_scope.disciplines),
      };
    }
    if (syncTags && payload && payload.user_scope) {
      setAccessTags('projects', payload.user_scope.projects || []);
      setAccessTags('disciplines', payload.user_scope.disciplines || []);
    } else {
      updateAccessPreview();
    }
  } catch (error) {
    console.warn('Refresh access preview failed:', error);
  }
}

function renderAccessTags(type) {
  const listEl = document.getElementById(type === 'projects' ? 'accessProjectsTags' : 'accessDisciplinesTags');
  if (!listEl) return;

  const values = Array.from(accessTags[type] || []).sort();
  const map = getTagMap(type);
  listEl.innerHTML = values.map((code) => {
    const name = map.get(code);
    const title = name && name !== code ? `${code} - ${name}` : code;
    return `
      <span class="tag-item" title="${escapeHtml(title)}">
        <span class="tag-text">${escapeHtml(code)}</span>
        <button type="button" class="tag-remove" data-users-action="remove-access-tag" data-tag-type="${type}" data-tag-code="${escapeHtml(code)}" aria-label="Ø­Ø°Ù">&times;</button>
      </span>
    `;
  }).join('');
}

function setAccessTags(type, values) {
  const normalized = (values || [])
    .map((v) => normalizeTagValue(v))
    .filter(Boolean);
  accessTags[type] = new Set(normalized);
  renderAccessTags(type);
  updateAccessPreview();
}

function addAccessTag(type, value) {
  const code = normalizeTagValue(value);
  if (!code) return;
  const list = type === 'projects' ? accessState.projects : accessState.disciplines;
  if (Array.isArray(list) && list.length) {
    const exists = list.some((item) => normalizeTagValue(item.code) === code);
    if (!exists) {
      accessNotify('error', 'Ú©Ø¯ ÙˆØ§Ø±Ø¯ Ø´Ø¯Ù‡ Ø¯Ø± Ù„ÛŒØ³Øª Ù…ÙˆØ¬ÙˆØ¯ Ù†ÛŒØ³Øª');
      return;
    }
  }
  accessTags[type].add(code);
  renderAccessTags(type);
  updateAccessPreview();
}

function removeAccessTag(type, value) {
  const code = normalizeTagValue(value);
  if (!code) return;
  accessTags[type].delete(code);
  renderAccessTags(type);
  updateAccessPreview();
}

function renderAccessSuggestions(type, items) {
  const container = document.getElementById(type === 'projects' ? 'accessProjectsSuggestions' : 'accessDisciplinesSuggestions');
  if (!container) return;
  if (!items.length) {
    container.classList.remove('show');
    container.innerHTML = '';
    return;
  }

  container.innerHTML = items.map((item) => {
    const code = normalizeTagValue(item.code);
    const name = item.name || '';
    return `
      <div class="tag-suggestion-item" data-type="${type}" data-code="${escapeHtml(code)}">
        <span class="tag-suggestion-code">${escapeHtml(code)}</span>
        <span class="tag-suggestion-name">${escapeHtml(name)}</span>
      </div>
    `;
  }).join('');
  container.classList.add('show');
}

function updateAccessSuggestions(type, query = '') {
  const list = type === 'projects' ? accessState.projects : accessState.disciplines;
  const q = String(query || '').trim().toUpperCase();
  const selected = accessTags[type] || new Set();
  const matched = (list || []).filter((item) => {
    const code = normalizeTagValue(item.code);
    const name = String(item.name || '').toUpperCase();
    if (selected.has(code)) return false;
    if (!q) return true;
    return code.includes(q) || name.includes(q);
  });
  const limit = Number(ACCESS_SUGGESTION_LIMIT || 0);
  const items = limit > 0 ? matched.slice(0, limit) : matched;
  renderAccessSuggestions(type, items);
}

function selectAccessSuggestion(type, code) {
  addAccessTag(type, code);
  const input = document.getElementById(type === 'projects' ? 'accessProjectsInput' : 'accessDisciplinesInput');
  if (input) {
    input.value = '';
    input.focus();
  }
  updateAccessSuggestions(type, '');
}

function setupAccessTagInput(type) {
  const input = document.getElementById(type === 'projects' ? 'accessProjectsInput' : 'accessDisciplinesInput');
  const wrapper = document.getElementById(type === 'projects' ? 'accessProjectsTagsInput' : 'accessDisciplinesTagsInput');
  const suggestions = document.getElementById(type === 'projects' ? 'accessProjectsSuggestions' : 'accessDisciplinesSuggestions');
  if (!input || !wrapper) return;

  wrapper.addEventListener('click', () => input.focus());
  if (suggestions && !suggestions.dataset.bound) {
    suggestions.addEventListener('pointerdown', (event) => {
      const item = event.target.closest('.tag-suggestion-item');
      if (!item) return;
      event.preventDefault();
      const code = item.dataset.code || '';
      const itemType = item.dataset.type || type;
      selectAccessSuggestion(itemType, code);
    });
    suggestions.dataset.bound = 'true';
  }
  input.addEventListener('input', (e) => updateAccessSuggestions(type, e.target.value));
  input.addEventListener('focus', (e) => updateAccessSuggestions(type, e.target.value));
  input.addEventListener('blur', () => {
    setTimeout(() => {
      if (suggestions) suggestions.classList.remove('show');
    }, 120);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addAccessTag(type, input.value);
      input.value = '';
      updateAccessSuggestions(type, '');
    } else if (e.key === 'Backspace' && !input.value) {
      const values = Array.from(accessTags[type] || []);
      const last = values[values.length - 1];
      if (last) removeAccessTag(type, last);
    }
  });
}

function initAccessTagInputs() {
  if (accessInputsInitialized) return;
  setupAccessTagInput('projects');
  setupAccessTagInput('disciplines');
  accessInputsInitialized = true;
}

async function openUserAccessModal(userId) {
  const user = usersCache.get(String(userId));
  if (!user) {
    accessNotify('error', 'Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ú©Ø§Ø±Ø¨Ø± Ø¨Ø±Ø§ÛŒ ØªÙ†Ø¸ÛŒÙ… Ø¯Ø³ØªØ±Ø³ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯.');
    return;
  }

  accessState.currentUserId = String(userId);
  accessState.currentUserRole = String(user.role || '');
  accessState.currentCategory = normalizePermissionCategory(
    user && user.organization ? user.organization.org_type : null,
  );
  updateAccessSummary(user);
  initAccessTagInputs();
  setAccessTags('projects', []);
  setAccessTags('disciplines', []);
  setAccessSourceStatus('Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ù…Ù†Ø§Ø¨Ø¹...', 'info');

  const modal = document.getElementById('userAccessModal');
  if (modal) openUsersModal('userAccessModal', '#accessProjectsInput');

  const adminNote = document.getElementById('accessAdminNote');
  const isAdmin = String(user.role || '').toLowerCase() === 'admin';
  if (adminNote) adminNote.style.display = isAdmin ? 'block' : 'none';
  setAccessInputsDisabled(isAdmin);

  try {
    setAccessLoading(true);
    await loadAccessScopeData(false, accessState.currentCategory);
    let effectivePayload = null;
    try {
      effectivePayload = await loadUserAccessEffective(userId);
    } catch (error) {
      console.warn('User access effective load failed:', error);
    }

    if (effectivePayload && effectivePayload.role_scope) {
      accessState.currentRoleScope = {
        projects: normalizeList(effectivePayload.role_scope.projects),
        disciplines: normalizeList(effectivePayload.role_scope.disciplines),
      };
    } else {
      accessState.currentRoleScope = getRoleScopeForUser(accessState.currentUserRole);
    }

    const scope = (effectivePayload && effectivePayload.user_scope) || accessState.userScope[String(userId)] || { projects: [], disciplines: [] };
    setAccessTags('projects', scope.projects || []);
    setAccessTags('disciplines', scope.disciplines || []);
  } catch (error) {
    setAccessInputsDisabled(true);
    const message = (error && error.message === 'Forbidden')
      ? 'ÙÙ‚Ø· Ø§Ø¯Ù…ÛŒÙ† Ù…ÛŒâ€ŒØªÙˆØ§Ù†Ø¯ Ø¯Ø³ØªØ±Ø³ÛŒâ€ŒÙ‡Ø§ Ø±Ø§ Ù…Ø¯ÛŒØ±ÛŒØª Ú©Ù†Ø¯.'
      : ((error && error.message) || 'Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
    accessNotify('error', message);
  } finally {
    setAccessLoading(false);
  }
}

function closeUserAccessModal() {
  const modal = document.getElementById('userAccessModal');
  if (modal) closeUsersModal('userAccessModal');
  const sug1 = document.getElementById('accessProjectsSuggestions');
  const sug2 = document.getElementById('accessDisciplinesSuggestions');
  if (sug1) sug1.classList.remove('show');
  if (sug2) sug2.classList.remove('show');
}

async function saveUserAccessScope() {
  const userId = String(accessState.currentUserId || '').trim();
  if (!userId) {
    accessNotify('error', 'Ø§Ø¨ØªØ¯Ø§ ÛŒÚ© Ú©Ø§Ø±Ø¨Ø± Ø±Ø§ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯');
    return;
  }
  if (accessState.loadError) {
    accessNotify('error', 'Ø§Ø¨ØªØ¯Ø§ Ø®Ø·Ø§ÛŒ Ø¨Ø§Ø±Ú¯Ø°Ø§Ø±ÛŒ Ù…Ù†Ø§Ø¨Ø¹ Ø±Ø§ Ø¨Ø±Ø·Ø±Ù Ú©Ù†ÛŒØ¯.');
    return;
  }
  if (String(accessState.currentUserRole || '').toLowerCase() === 'admin') {
    accessNotify('info', 'Ø§Ø¯Ù…ÛŒÙ† Ø¯Ø³ØªØ±Ø³ÛŒ Ú©Ø§Ù…Ù„ Ø¯Ø§Ø±Ø¯ Ùˆ Ù…Ø­Ø¯ÙˆØ¯ÛŒØª Ø¨Ø±Ø§ÛŒ Ø§Ùˆ Ø°Ø®ÛŒØ±Ù‡ Ù†Ù…ÛŒâ€ŒØ´ÙˆØ¯');
    return;
  }

  const payload = {
    user_id: Number(userId),
    projects: Array.from(accessTags.projects || []),
    disciplines: Array.from(accessTags.disciplines || []),
  };

  const btn = document.getElementById('userAccessSaveBtn');
  if (btn && window.UI && window.UI.setBtnLoading) window.UI.setBtnLoading(btn, true);

  try {
    const saved = await accessRequest(ACCESS_USER_SCOPE_UPSERT_ENDPOINT, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const savedScope = (saved && saved.scope) || {
      projects: payload.projects,
      disciplines: payload.disciplines,
    };
    accessNotify('success', `Ø¯Ø³ØªØ±Ø³ÛŒ Ú©Ø§Ø±Ø¨Ø± Ø°Ø®ÛŒØ±Ù‡ Ø´Ø¯ (${(savedScope.projects || []).length} Ù¾Ø±ÙˆÚ˜Ù‡ØŒ ${(savedScope.disciplines || []).length} Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†)`);
    const requestedProjects = payload.projects || [];
    const requestedDisciplines = payload.disciplines || [];
    const savedProjects = savedScope.projects || [];
    const savedDisciplines = savedScope.disciplines || [];
    const missingProjects = requestedProjects.filter((code) => !savedProjects.includes(code));
    const missingDisciplines = requestedDisciplines.filter((code) => !savedDisciplines.includes(code));
    if (missingProjects.length || missingDisciplines.length) {
      const parts = [];
      if (missingProjects.length) parts.push(`Ù¾Ø±ÙˆÚ˜Ù‡: ${missingProjects.slice(0, 6).join(', ')}`);
      if (missingDisciplines.length) parts.push(`Ø¯ÛŒØ³ÛŒÙ¾Ù„ÛŒÙ†: ${missingDisciplines.slice(0, 6).join(', ')}`);
      accessNotify('warning', `Ø¨Ø±Ø®ÛŒ Ú©Ø¯Ù‡Ø§ Ø°Ø®ÛŒØ±Ù‡ Ù†Ø´Ø¯Ù†Ø¯. ${parts.join(' | ')}`);
    }
    accessState.userScope[userId] = {
      projects: Array.isArray(savedScope.projects) ? savedScope.projects : [],
      disciplines: Array.isArray(savedScope.disciplines) ? savedScope.disciplines : [],
    };
    loadUsers({ reloadScope: true });
    await refreshAccessPreviewFromServer(userId);
  } catch (error) {
    accessNotify('error', error.message || 'Ø°Ø®ÛŒØ±Ù‡ Ø¯Ø³ØªØ±Ø³ÛŒ Ù†Ø§Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯');
  } finally {
    if (btn && window.UI && window.UI.setBtnLoading) window.UI.setBtnLoading(btn, false);
  }
}

async function clearUserAccessScope() {
  setAccessTags('projects', []);
  setAccessTags('disciplines', []);
  await saveUserAccessScope();
}

function initSettingsUsers(forceReload = false) {
  bindUsersToolbar();
  if (forceReload) {
    loadUsers({ resetPage: false, reloadScope: true });
    return;
  }
  loadUsers();
}

window.loadUsers = loadUsers;
window.initSettingsUsers = initSettingsUsers;

