// @ts-nocheck
(() => {
  const MATRIX_ENDPOINT = '/api/v1/settings/permissions/matrix';
  const SCOPE_ENDPOINT = '/api/v1/settings/permissions/scope';
  const USERS_SEARCH_ENDPOINT = '/api/v1/users/paged';
  const USER_ACCESS_ENDPOINT = '/api/v1/settings/permissions/user-access';
  const DEFAULT_CATEGORY = 'consultant';
  const DEFAULT_SUBTAB = 'overview';
  const SEARCH_DEBOUNCE_MS = 180;
  const STORAGE_KEYS = {
    category: 'settings.permissions.activeCategory',
    subtab: 'settings.permissions.activeSubtab',
  };

  const CATEGORY_ORDER = ['consultant', 'contractor', 'employer', 'dcc'];
  const ROLE_ORDER = ['manager', 'dcc', 'project_control', 'user', 'viewer'];
  const DEFAULT_ROLE_LABELS = {
    manager: 'سرپرست',
    dcc: 'کنترل مدارک (DCC)',
    project_control: 'کنترل پروژه',
    user: 'کاربر عادی',
    viewer: 'مشاهده‌گر',
  };
  const DEFAULT_CATEGORY_LABELS = {
    consultant: 'مشاور',
    contractor: 'پیمانکار',
    employer: 'کارفرما',
    dcc: 'DCC',
  };
  const PERMISSION_TYPE_LABELS = {
    hub: 'هاب',
    module: 'ماژول',
    domain: 'دامنه',
    action: 'عملیات',
  };
  const GUIDED_SECTION_ORDER = {
    hubs: 1,
    edms: 2,
    contractor: 3,
    consultant: 4,
    reports_dash: 5,
    admin: 6,
    infra: 7,
  };
  const EXPERT_BUCKETS = {
    hubs: { key: 'hubs', label: 'هاب‌ها', order: 1 },
    modules_edms: { key: 'modules_edms', label: 'ماژول‌های EDMS', order: 2 },
    modules_contractor: { key: 'modules_contractor', label: 'ماژول‌های پیمانکار', order: 3 },
    modules_consultant: { key: 'modules_consultant', label: 'ماژول‌های مشاور', order: 4 },
    domains: { key: 'domains', label: 'دسترسی دامنه‌ها', order: 5 },
    actions: { key: 'actions', label: 'عملیات', order: 6 },
    reports_dash: { key: 'reports_dash', label: 'گزارش و داشبورد', order: 7 },
    admin: { key: 'admin', label: 'تنظیمات و مدیریت', order: 8 },
    infra: { key: 'infra', label: 'زیرساخت و یکپارچه‌سازی', order: 9 },
  };
  const VALID_SUBTABS = ['overview', 'expert', 'scope', 'effective'];

  const state = {
    initialized: false,
    actionsBound: false,
    activeCategory: loadStoredValue(STORAGE_KEYS.category, DEFAULT_CATEGORY),
    activeSubtab: DEFAULT_SUBTAB,
    categories: CATEGORY_ORDER.slice(),
    categoryLabels: { ...DEFAULT_CATEGORY_LABELS },
    roleLabels: { ...DEFAULT_ROLE_LABELS },
    footerStatus: '',
    matrixByCategory: {},
    scopeByCategory: {},
    effective: {
      query: '',
      searchTimer: null,
      results: [],
      selectedUserId: null,
      selectedUserLabel: '',
      payload: null,
      loading: false,
    },
  };
  state.activeSubtab = normalizeSubtab(loadStoredValue(STORAGE_KEYS.subtab, DEFAULT_SUBTAB));

  function loadStoredValue(key, fallback) {
    try {
      return window.localStorage.getItem(key) || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function storeValue(key, value) {
    try {
      window.localStorage.setItem(key, String(value || ''));
    } catch (_) {}
  }

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function cloneDeep(value) {
    return JSON.parse(JSON.stringify(value == null ? null : value));
  }

  function normalizeCategory(value) {
    const key = String(value || '').trim().toLowerCase();
    return CATEGORY_ORDER.includes(key) ? key : DEFAULT_CATEGORY;
  }

  function normalizeRole(value) {
    const key = String(value || '').trim().toLowerCase();
    return ROLE_ORDER.includes(key) ? key : 'user';
  }

  function normalizeSubtab(value) {
    const key = String(value || '').trim().toLowerCase();
    return VALID_SUBTABS.includes(key) ? key : DEFAULT_SUBTAB;
  }

  function categoryLabel(value) {
    const key = normalizeCategory(value);
    return state.categoryLabels[key] || DEFAULT_CATEGORY_LABELS[key] || value || '-';
  }

  function roleLabel(value) {
    const key = normalizeRole(value);
    return state.roleLabels[key] || DEFAULT_ROLE_LABELS[key] || value || '-';
  }

  function permissionTypeLabel(value) {
    const key = String(value || '').trim().toLowerCase();
    return PERMISSION_TYPE_LABELS[key] || key || '-';
  }

  function permissionDependencyHint(meta) {
    const dependsOn = Array.isArray(meta && meta.depends_on) ? meta.depends_on.filter(Boolean) : [];
    if (dependsOn.length) return `نیازمند ${dependsOn.join(' + ')}`;
    if (String(meta && meta.type || '') === 'module') return 'به‌تنهایی برای visible شدن کافی نیست';
    return '';
  }

  function notify(type, message) {
    if (window.UI && typeof window.UI[type] === 'function') {
      window.UI[type](message);
      return;
    }
    if (typeof window.showToast === 'function') {
      window.showToast(message, type === 'error' ? 'error' : type === 'warning' ? 'warning' : 'success');
      return;
    }
    window.alert(message);
  }

  async function request(url, options = {}) {
    const requester = typeof window.fetchWithAuth === 'function' ? window.fetchWithAuth : window.fetch.bind(window);
    const headers = { ...(options.headers || {}) };
    let body = options.body;
    if (body && typeof body === 'object' && !(body instanceof window.FormData) && !(body instanceof window.Blob)) {
      body = JSON.stringify(body);
      if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';
    }
    const response = await requester(url, { ...options, headers, body });
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try {
        const payload = await response.clone().json();
        message = payload.detail || payload.message || message;
      } catch (_) {}
      throw new Error(message);
    }
    return response.json();
  }

  function defaultRoleScope() {
    return ROLE_ORDER.reduce((acc, role) => {
      acc[role] = { projects: [], disciplines: [] };
      return acc;
    }, {});
  }

  function createEmptyMatrixState() {
    return {
      loaded: false,
      readOnly: false,
      roles: ROLE_ORDER.slice(),
      permissions: [],
      permissionsMeta: [],
      metaIndex: {},
      featureCatalog: [],
      featureIndex: {},
      matrix: {},
      originalMatrix: {},
      baselineMatrix: {},
      roleLabels: { ...DEFAULT_ROLE_LABELS },
      categoryLabel: '',
      lastSavedAt: '',
      dirty: false,
      filters: {
        query: '',
        type: '',
        section: '',
        changedOnly: false,
        activeOnly: false,
      },
      collapsedSections: new Set(),
      collapsedPages: new Set(),
    };
  }

  function createEmptyScopeState() {
    return {
      loaded: false,
      readOnly: false,
      roles: ROLE_ORDER.slice(),
      roleLabels: { ...DEFAULT_ROLE_LABELS },
      categoryLabel: '',
      scope: defaultRoleScope(),
      originalScope: defaultRoleScope(),
      projects: [],
      disciplines: [],
      projectMap: new Map(),
      disciplineMap: new Map(),
      dirty: false,
      lastSavedAt: '',
    };
  }

  function matrixState(category = state.activeCategory) {
    const key = normalizeCategory(category);
    if (!state.matrixByCategory[key]) state.matrixByCategory[key] = createEmptyMatrixState();
    return state.matrixByCategory[key];
  }

  function scopeState(category = state.activeCategory) {
    const key = normalizeCategory(category);
    if (!state.scopeByCategory[key]) state.scopeByCategory[key] = createEmptyScopeState();
    return state.scopeByCategory[key];
  }

  function buildMetaIndex(items) {
    const index = {};
    (items || []).forEach((item) => {
      if (item && item.key) index[String(item.key)] = item;
    });
    return index;
  }

  function buildFeatureIndex(items) {
    const index = {};
    (items || []).forEach((item) => {
      if (item && item.key) index[String(item.key)] = item;
    });
    return index;
  }

  function normalizeScopeValues(values) {
    return Array.from(new Set((values || []).map((item) => String(item || '').trim().toUpperCase()).filter(Boolean))).sort();
  }

  function normalizeScopePayload(scope) {
    const normalized = defaultRoleScope();
    ROLE_ORDER.forEach((role) => {
      const roleData = scope && typeof scope === 'object' ? scope[role] : null;
      normalized[role] = {
        projects: normalizeScopeValues(roleData && roleData.projects),
        disciplines: normalizeScopeValues(roleData && roleData.disciplines),
      };
    });
    return normalized;
  }

  function formatNow() {
    try {
      return new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date());
    } catch (_) {
      return new Date().toLocaleTimeString();
    }
  }

  function ensureMatrixDefaults(current) {
    current.roles.forEach((role) => {
      if (!current.matrix[role]) current.matrix[role] = {};
      if (!current.originalMatrix[role]) current.originalMatrix[role] = {};
      if (!current.baselineMatrix[role]) current.baselineMatrix[role] = {};
      current.permissions.forEach((permission) => {
        if (!(permission in current.matrix[role])) current.matrix[role][permission] = false;
        if (!(permission in current.originalMatrix[role])) current.originalMatrix[role][permission] = false;
        if (!(permission in current.baselineMatrix[role])) current.baselineMatrix[role][permission] = false;
      });
    });
  }

  function computeMatrixDirty(category = state.activeCategory) {
    const current = matrixState(category);
    current.dirty = JSON.stringify(current.matrix || {}) !== JSON.stringify(current.originalMatrix || {});
    return current.dirty;
  }

  function computeScopeDirty(category = state.activeCategory) {
    const current = scopeState(category);
    current.dirty = JSON.stringify(current.scope || {}) !== JSON.stringify(current.originalScope || {});
    return current.dirty;
  }

  function hasAnyDirtyCategory() {
    return CATEGORY_ORDER.some((category) => computeMatrixDirty(category) || computeScopeDirty(category));
  }

  async function loadPermissionsMatrix(category, force = false) {
    const target = normalizeCategory(category);
    const current = matrixState(target);
    if (current.loaded && !force) return current;
    const payload = await request(`${MATRIX_ENDPOINT}?category=${encodeURIComponent(target)}`);
    current.loaded = true;
    current.readOnly = Boolean(payload.read_only);
    current.roles = Array.isArray(payload.roles) ? payload.roles.map(normalizeRole) : ROLE_ORDER.slice();
    current.permissions = Array.isArray(payload.permissions) ? payload.permissions.slice() : [];
    current.permissionsMeta = Array.isArray(payload.permissions_meta) ? payload.permissions_meta.slice() : [];
    current.metaIndex = buildMetaIndex(current.permissionsMeta);
    current.featureCatalog = Array.isArray(payload.feature_catalog)
      ? payload.feature_catalog.filter((item) => Array.isArray(item.category_relevance) ? item.category_relevance.includes(target) : true)
      : [];
    current.featureIndex = buildFeatureIndex(current.featureCatalog);
    current.matrix = cloneDeep(payload.matrix || {});
    current.originalMatrix = cloneDeep(payload.matrix || {});
    current.baselineMatrix = cloneDeep(payload.baseline_matrix || payload.matrix || {});
    current.categoryLabel = String(payload.category_label || categoryLabel(target));
    current.roleLabels = { ...DEFAULT_ROLE_LABELS, ...(payload.role_labels || {}) };
    current.lastSavedAt = current.lastSavedAt || '';
    state.categories = Array.isArray(payload.categories) && payload.categories.length ? payload.categories.map(normalizeCategory) : CATEGORY_ORDER.slice();
    state.roleLabels = { ...DEFAULT_ROLE_LABELS, ...(payload.role_labels || {}) };
    state.categoryLabels[target] = current.categoryLabel;
    ensureMatrixDefaults(current);
    computeMatrixDirty(target);
    return current;
  }

  async function loadPermissionsScope(category, force = false) {
    const target = normalizeCategory(category);
    const current = scopeState(target);
    if (current.loaded && !force) return current;
    const payload = await request(`${SCOPE_ENDPOINT}?category=${encodeURIComponent(target)}`);
    current.loaded = true;
    current.readOnly = Boolean(payload.scope_read_only);
    current.roles = Array.isArray(payload.roles) ? payload.roles.map(normalizeRole) : ROLE_ORDER.slice();
    current.roleLabels = { ...DEFAULT_ROLE_LABELS, ...(payload.role_labels || {}) };
    current.categoryLabel = String(payload.category_label || categoryLabel(target));
    current.scope = normalizeScopePayload(payload.scope || {});
    current.originalScope = cloneDeep(current.scope);
    current.projects = Array.isArray(payload.projects) ? payload.projects.slice() : [];
    current.disciplines = Array.isArray(payload.disciplines) ? payload.disciplines.slice() : [];
    current.projectMap = new Map(current.projects.map((item) => [String(item.code || '').toUpperCase(), String(item.name || item.code || '')]));
    current.disciplineMap = new Map(current.disciplines.map((item) => [String(item.code || '').toUpperCase(), String(item.name || item.code || '')]));
    state.roleLabels = { ...DEFAULT_ROLE_LABELS, ...(payload.role_labels || {}) };
    state.categoryLabels[target] = current.categoryLabel;
    computeScopeDirty(target);
    return current;
  }

  async function ensureCategoryLoaded(category = state.activeCategory, force = false) {
    const target = normalizeCategory(category);
    await Promise.all([loadPermissionsMatrix(target, force), loadPermissionsScope(target, force)]);
    return { matrix: matrixState(target), scope: scopeState(target) };
  }

  function persistWorkspaceState() {
    storeValue(STORAGE_KEYS.category, state.activeCategory);
    storeValue(STORAGE_KEYS.subtab, state.activeSubtab);
  }

  function currentDirtyMessage() {
    const matrixDirty = computeMatrixDirty(state.activeCategory);
    const scopeDirty = computeScopeDirty(state.activeCategory);
    if (state.activeSubtab === 'scope') return scopeDirty ? 'تغییرات ذخیره‌نشده در Scope' : 'بدون تغییر';
    if (state.activeSubtab === 'effective') return 'نمای دسترسی مؤثر فقط خواندنی است';
    if (matrixDirty) return 'تغییرات ذخیره‌نشده در ماتریس';
    if (scopeDirty) return 'Scope این دسته تغییر ذخیره‌نشده دارد';
    return 'بدون تغییر';
  }

  function setFooterStatus(message) {
    state.footerStatus = String(message || currentDirtyMessage());
    const footer = document.getElementById('permissionsFooterStatus');
    if (footer) footer.textContent = state.footerStatus;
  }

  function updateHeaderState() {
    const categoryBadge = document.getElementById('permissionsCurrentCategoryBadge');
    const dirtyBadge = document.getElementById('permissionsDirtyBadge');
    const lastSavedBadge = document.getElementById('permissionsLastSavedBadge');
    const saveBtn = document.querySelector('[data-permissions-action="save-current"]');
    const resetBtn = document.querySelector('[data-permissions-action="reset-current"]');
    const currentMatrix = matrixState(state.activeCategory);
    const currentScope = scopeState(state.activeCategory);
    const readOnly = state.activeSubtab === 'scope' ? currentScope.readOnly : currentMatrix.readOnly;
    const dirtyText = currentDirtyMessage();
    const matrixDirty = computeMatrixDirty(state.activeCategory);
    const scopeDirty = computeScopeDirty(state.activeCategory);

    if (categoryBadge) categoryBadge.textContent = `دسته فعال: ${categoryLabel(state.activeCategory)}`;
    if (dirtyBadge) {
      dirtyBadge.textContent = dirtyText;
      dirtyBadge.classList.toggle('is-dirty', hasAnyDirtyCategory());
      dirtyBadge.classList.toggle('is-muted', !hasAnyDirtyCategory());
    }
    if (lastSavedBadge) {
      const lastSaved = state.activeSubtab === 'scope' ? currentScope.lastSavedAt : currentMatrix.lastSavedAt;
      lastSavedBadge.textContent = `آخرین ذخیره: ${lastSaved || '-'}`;
    }
    if (saveBtn) {
      const disabled = state.activeSubtab === 'effective' || readOnly || (state.activeSubtab === 'scope' ? !scopeDirty : !matrixDirty);
      saveBtn.disabled = Boolean(disabled);
    }
    if (resetBtn) {
      const disabled = state.activeSubtab === 'effective' || readOnly || (state.activeSubtab === 'scope' ? !scopeDirty : !matrixDirty);
      resetBtn.disabled = Boolean(disabled);
    }
    setFooterStatus(dirtyText);
  }

  function renderCategorySwitcher() {
    const root = document.getElementById('permissionsCategoryTabs');
    if (!root) return;
    const buttons = root.querySelectorAll('[data-permissions-category]');
    buttons.forEach((button) => {
      const category = normalizeCategory(button.getAttribute('data-permissions-category') || '');
      const isActive = category === state.activeCategory;
      const hasDirty = computeMatrixDirty(category) || computeScopeDirty(category);
      button.classList.toggle('active', isActive);
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      button.innerHTML = `${esc(categoryLabel(category))}${hasDirty ? '<span class="permissions-tab-dirty-dot"></span>' : ''}`;
    });
  }

  function renderSubtabs() {
    const tabs = document.querySelectorAll('#permissionsSubtabs [data-subtab]');
    tabs.forEach((tab) => {
      const subtab = String(tab.getAttribute('data-subtab') || '');
      const isActive = subtab === state.activeSubtab;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
      tab.setAttribute('tabindex', isActive ? '0' : '-1');
    });
    const panelMap = {
      overview: document.getElementById('permissionsPanelOverview'),
      expert: document.getElementById('permissionsPanelExpert'),
      scope: document.getElementById('permissionsPanelScope'),
      effective: document.getElementById('permissionsPanelEffective'),
    };
    Object.entries(panelMap).forEach(([key, panel]) => {
      if (!panel) return;
      const isActive = key === state.activeSubtab;
      panel.classList.toggle('active', isActive);
      panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
    });
  }

  function featureState(roleKey, feature, current) {
    const row = current.matrix[roleKey] || {};
    const basePermissions = Array.isArray(feature.base_permissions) ? feature.base_permissions : [];
    const actionPermissions = Array.isArray(feature.action_permissions) ? feature.action_permissions : [];
    const enabledCount = basePermissions.filter((permission) => Boolean(row[permission])).length;
    const baseEnabled = enabledCount === basePermissions.length && basePermissions.length > 0;
    const hasAnyBase = enabledCount > 0;
    const activeActions = actionPermissions.filter((permission) => Boolean(row[permission]));
    let status = 'غیرفعال';
    let statusKey = 'off';
    if (baseEnabled) {
      status = 'فعال';
      statusKey = 'on';
    } else if (hasAnyBase || activeActions.length > 0) {
      status = 'وابسته';
      statusKey = 'partial';
    }
    return {
      baseEnabled,
      hasAnyBase,
      activeActions,
      status,
      statusKey,
      warning: !baseEnabled && activeActions.length > 0,
    };
  }

  function groupFeaturesBySection(items) {
    const grouped = new Map();
    (items || []).forEach((item) => {
      const key = String(item.section_key || 'misc');
      if (!grouped.has(key)) {
        grouped.set(key, {
          key,
          label: String(item.section_label || key),
          order: GUIDED_SECTION_ORDER[key] || 100,
          items: [],
        });
      }
      grouped.get(key).items.push(item);
    });
    return Array.from(grouped.values()).sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'fa'));
  }

  function renderPermissionToggle(roleKey, permission, current, dependencyLocked) {
    const meta = current.metaIndex[permission] || {};
    const disabled = Boolean(current.readOnly || dependencyLocked);
    const dependencyHint = permissionDependencyHint(meta);
    return `
      <label class="permissions-inline-toggle ${disabled ? 'is-disabled' : ''}" title="${esc(permission)}">
        <input
          type="checkbox"
          data-permissions-action="toggle-permission"
          data-role="${esc(roleKey)}"
          data-permission="${encodeURIComponent(permission)}"
          ${Boolean(current.matrix[roleKey] && current.matrix[roleKey][permission]) ? 'checked' : ''}
          ${disabled ? 'disabled' : ''}
        >
        <span class="permissions-inline-toggle-copy">
          <span class="permissions-inline-toggle-title">
            <span>${esc(meta.label_fa || permission)}</span>
            <span class="permissions-inline-toggle-badges">
              <span class="permissions-meta-badge is-type">${esc(permissionTypeLabel(meta.type))}</span>
              ${dependencyHint ? '<span class="permissions-meta-badge is-dependency">وابستگی</span>' : ''}
            </span>
          </span>
          <code>${esc(permission)}</code>
          ${dependencyHint ? `<small class="permissions-inline-toggle-hint">${esc(dependencyHint)}</small>` : ''}
        </span>
      </label>
    `;
  }

  function renderFeatureRow(roleKey, feature, current) {
    const status = featureState(roleKey, feature, current);
    const actionPermissions = Array.isArray(feature.action_permissions) ? feature.action_permissions : [];
    const basePermissions = Array.isArray(feature.base_permissions) ? feature.base_permissions : [];
    return `
      <details class="permissions-feature-row is-${esc(status.statusKey)}">
        <summary>
          <div class="permissions-feature-main">
            <div class="permissions-feature-copy">
              <strong>${esc(feature.label_fa || feature.key)}</strong>
              <p>${esc(feature.description || '')}</p>
              <div class="permissions-feature-badges">
                <span class="permissions-meta-badge is-section">${esc(feature.section_label || 'بخش')}</span>
                <span class="permissions-meta-badge is-page">${esc(feature.page_label || feature.page_key || 'صفحه')}</span>
                <span class="permissions-meta-badge is-base">${esc(String(basePermissions.length))} مجوز پایه</span>
                ${actionPermissions.length ? `<span class="permissions-meta-badge is-action">${esc(String(actionPermissions.length))} عملیات</span>` : ''}
              </div>
            </div>
            <div class="permissions-feature-controls">
              <span class="permissions-feature-status is-${esc(status.statusKey)}">${esc(status.status)}</span>
              <label class="toggle-switch ${current.readOnly ? 'is-disabled' : ''}">
                <input
                  type="checkbox"
                  data-permissions-action="toggle-feature-bundle"
                  data-role="${esc(roleKey)}"
                  data-feature-key="${esc(feature.key)}"
                  ${status.baseEnabled ? 'checked' : ''}
                  ${current.readOnly ? 'disabled' : ''}
                >
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>
        </summary>
        <div class="permissions-feature-details">
          <div class="permissions-feature-bundle">
            <div class="permissions-feature-subtitle">Bundle پایه</div>
            <div class="permissions-code-list">
              ${basePermissions.map((permission) => renderPermissionToggle(roleKey, permission, current, false)).join('')}
            </div>
          </div>
          <div class="permissions-feature-bundle">
            <div class="permissions-feature-subtitle">عملیات وابسته</div>
            <div class="permissions-code-list">
              ${actionPermissions.length
                ? actionPermissions.map((permission) => renderPermissionToggle(roleKey, permission, current, !status.baseEnabled)).join('')
                : '<span class="permissions-empty-inline">عملیات اضافی برای این feature تعریف نشده است.</span>'}
            </div>
            ${status.warning ? '<div class="permissions-inline-hint">Bundle پایه خاموش است اما عملیات وابسته فعال مانده. برای تغییر عملیات، ابتدا نمایش feature را روشن کنید.</div>' : ''}
          </div>
        </div>
      </details>
    `;
  }

  function renderRoleCard(roleKey, current, sections) {
    const features = current.featureCatalog || [];
    const enabledCount = features.filter((feature) => featureState(roleKey, feature, current).baseEnabled).length;
    const partialCount = features.filter((feature) => featureState(roleKey, feature, current).statusKey === 'partial').length;
    const statusLabel = current.readOnly ? 'readonly' : enabledCount === 0 ? 'غیرفعال' : enabledCount === features.length ? 'فعال' : 'محدود';
    const statusClass = current.readOnly ? 'readonly' : enabledCount === 0 ? 'off' : enabledCount === features.length ? 'on' : 'partial';
    const copyOptions = current.roles
      .filter((candidate) => candidate !== roleKey)
      .map((candidate) => `<option value="${esc(candidate)}">${esc(roleLabel(candidate))}</option>`)
      .join('');
    return `
      <article class="permissions-role-card">
        <header class="permissions-role-card-header">
          <div>
            <h4>${esc(roleLabel(roleKey))}</h4>
            <div class="permissions-role-card-meta">
              <span class="permissions-role-badge is-${statusClass}">${esc(statusLabel)}</span>
              <span class="muted">${enabledCount} feature فعال / ${Math.max(0, features.length - enabledCount)} feature غیرفعال</span>
            </div>
            <div class="permissions-role-card-stats">
              <span class="permissions-role-stat is-on">فعال: ${enabledCount}</span>
              <span class="permissions-role-stat is-partial">وابسته: ${partialCount}</span>
              <span class="permissions-role-stat is-muted">بخش‌ها: ${sections.length}</span>
            </div>
          </div>
          <div class="permissions-role-card-actions">
            <div class="permissions-copy-inline">
              <select class="form-input permissions-copy-select" data-copy-source-for="${esc(roleKey)}" ${current.readOnly ? 'disabled' : ''}>
                <option value="">کپی از نقش دیگر</option>
                ${copyOptions}
              </select>
              <button type="button" class="btn-secondary btn-sm" data-permissions-action="copy-role-from" data-role="${esc(roleKey)}" ${current.readOnly ? 'disabled' : ''}>اعمال</button>
            </div>
            <div class="permissions-role-card-quick">
              <button type="button" class="btn-secondary btn-sm" data-permissions-action="reset-role-baseline" data-role="${esc(roleKey)}" ${current.readOnly ? 'disabled' : ''}>Baseline</button>
              <button type="button" class="btn-secondary btn-sm" data-permissions-action="clear-role" data-role="${esc(roleKey)}" ${current.readOnly ? 'disabled' : ''}>خاموش کردن همه</button>
              <button type="button" class="btn-secondary btn-sm" data-permissions-action="set-role-viewer" data-role="${esc(roleKey)}" ${current.readOnly ? 'disabled' : ''}>فقط خواندن</button>
            </div>
          </div>
        </header>
        <div class="permissions-role-card-body">
          ${sections.map((section) => `
            <details class="permissions-guided-section" open>
              <summary>${esc(section.label)}</summary>
              <div class="permissions-guided-section-body">
                ${section.items.map((feature) => renderFeatureRow(roleKey, feature, current)).join('')}
              </div>
            </details>
          `).join('')}
        </div>
      </article>
    `;
  }

  function renderOverviewTab() {
    const current = matrixState(state.activeCategory);
    const container = document.getElementById('permissionsOverviewContent');
    if (!container) return;
    if (!current.loaded) {
      container.innerHTML = '<div class="permissions-empty-inline">در حال بارگذاری خلاصه نقش‌ها...</div>';
      return;
    }
    const sections = groupFeaturesBySection(current.featureCatalog);
    container.innerHTML = `
      <div class="permissions-guided-grid">
        ${current.roles.map((role) => renderRoleCard(role, current, sections)).join('')}
      </div>
    `;
  }

  function expertBucketFor(meta) {
    if (!meta) return EXPERT_BUCKETS.actions;
    const pageKey = String(meta.page_key || '');
    if (meta.type === 'hub') return EXPERT_BUCKETS.hubs;
    if (meta.type === 'module') {
      if (['archive', 'transmittal', 'correspondence'].includes(pageKey)) return EXPERT_BUCKETS.modules_edms;
      if (pageKey.includes('contractor') || pageKey === 'workboard') return EXPERT_BUCKETS.modules_contractor;
      if (pageKey.includes('consultant') || pageKey === 'bim') return EXPERT_BUCKETS.modules_consultant;
      if (['reports', 'dashboard'].includes(pageKey)) return EXPERT_BUCKETS.reports_dash;
      if (['storage', 'site_cache', 'integrations'].includes(pageKey)) return EXPERT_BUCKETS.infra;
      return EXPERT_BUCKETS.admin;
    }
    if (['dashboard', 'reports'].includes(pageKey)) return EXPERT_BUCKETS.reports_dash;
    if (['settings', 'permissions', 'users', 'organizations', 'lookup'].includes(pageKey)) return EXPERT_BUCKETS.admin;
    if (['storage', 'site_cache', 'integrations'].includes(pageKey)) return EXPERT_BUCKETS.infra;
    return meta.type === 'domain' ? EXPERT_BUCKETS.domains : EXPERT_BUCKETS.actions;
  }

  function permissionMatchesExpertFilters(meta, current) {
    const filters = current.filters || {};
    const query = String(filters.query || '').trim().toLowerCase();
    if (filters.type && String(meta.type || '') !== String(filters.type)) return false;
    if (filters.section && expertBucketFor(meta).key !== filters.section) return false;
    if (query) {
      const text = [meta.label_fa, meta.key, meta.page_label, meta.section_label, meta.type].join(' ').toLowerCase();
      if (!text.includes(query)) return false;
    }
    if (filters.activeOnly) {
      const anyActive = current.roles.some((role) => Boolean(current.matrix[role] && current.matrix[role][meta.key]));
      if (!anyActive) return false;
    }
    if (filters.changedOnly) {
      const anyChanged = current.roles.some((role) => Boolean(current.matrix[role] && current.matrix[role][meta.key]) !== Boolean(current.baselineMatrix[role] && current.baselineMatrix[role][meta.key]));
      if (!anyChanged) return false;
    }
    return true;
  }

  function expertSectionOptions(current) {
    const map = new Map();
    current.permissionsMeta.forEach((meta) => {
      const bucket = expertBucketFor(meta);
      if (!map.has(bucket.key)) map.set(bucket.key, bucket);
    });
    return Array.from(map.values()).sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'fa'));
  }

  function renderExpertSectionFilterOptions() {
    const select = document.getElementById('permissionsSectionFilter');
    const current = matrixState(state.activeCategory);
    if (!select || !current.loaded) return;
    const selected = String(current.filters.section || '');
    select.innerHTML = `<option value="">همه</option>${expertSectionOptions(current).map((item) => `<option value="${esc(item.key)}" ${selected === item.key ? 'selected' : ''}>${esc(item.label)}</option>`).join('')}`;
  }

  function resolveExpertScopeItems(scopeType, scopeKey, current) {
    if (scopeType === 'section') {
      return current.permissionsMeta.filter((meta) => expertBucketFor(meta).key === scopeKey && permissionMatchesExpertFilters(meta, current));
    }
    if (scopeType === 'page') {
      return current.permissionsMeta.filter((meta) => String(meta.page_key || '') === scopeKey && permissionMatchesExpertFilters(meta, current));
    }
    return [];
  }

  function renderAggregateRoleCell(role, items, scopeKey, scopeType, current) {
    const values = items.map((meta) => Boolean(current.matrix[role] && current.matrix[role][meta.key]));
    const checked = values.length > 0 && values.every(Boolean);
    return `
      <td class="center-text matrix-role-cell">
        <label class="toggle-switch ${current.readOnly ? 'is-disabled' : ''}">
          <input
            type="checkbox"
            data-permissions-action="toggle-expert-aggregate"
            data-role="${esc(role)}"
            data-scope-type="${esc(scopeType)}"
            data-scope-key="${esc(scopeKey)}"
            ${checked ? 'checked' : ''}
            ${current.readOnly ? 'disabled' : ''}
          >
          <span class="toggle-slider"></span>
        </label>
      </td>
    `;
  }

  function renderExpertPermissionRow(section, page, meta, current, hidden) {
    const dependencyText = permissionDependencyHint(meta);
    return `
      <tr class="matrix-tree-child-row ${hidden ? 'is-collapsed' : ''}" data-page-parent="${esc(page.key)}" data-section-parent="${esc(section.key)}">
        <td class="matrix-permission-name sticky-col">
          <div class="permissions-expert-row">
            <div class="permissions-expert-copy">
              <span class="permissions-expert-label">${esc(meta.label_fa || meta.key)}</span>
              <div class="permissions-expert-meta">
                <span class="permissions-expert-type">${esc(permissionTypeLabel(meta.type))}</span>
                ${dependencyText ? '<span class="permissions-meta-badge is-dependency">وابستگی</span>' : ''}
                <code>${esc(meta.key)}</code>
              </div>
              ${dependencyText ? `<div class="permissions-expert-hint">${esc(dependencyText)}</div>` : ''}
            </div>
          </div>
        </td>
        ${current.roles.map((role) => `
          <td class="center-text matrix-role-cell">
            <label class="toggle-switch ${current.readOnly ? 'is-disabled' : ''}">
              <input
                type="checkbox"
                data-permissions-action="toggle-permission"
                data-role="${esc(role)}"
                data-permission="${encodeURIComponent(meta.key)}"
                ${Boolean(current.matrix[role] && current.matrix[role][meta.key]) ? 'checked' : ''}
                ${current.readOnly ? 'disabled' : ''}
              >
              <span class="toggle-slider"></span>
            </label>
          </td>
        `).join('')}
      </tr>
    `;
  }

  function renderExpertPage(section, page, current, sectionCollapsed) {
    const pageCollapsed = current.collapsedPages.has(page.key);
    return `
      <tr class="matrix-tree-group-row ${sectionCollapsed ? 'is-collapsed' : ''} ${pageCollapsed ? 'is-page-collapsed' : ''}" data-page-key="${esc(page.key)}" data-section-parent="${esc(section.key)}">
        <td class="matrix-permission-name sticky-col matrix-tree-group-cell">
          <button type="button" class="matrix-tree-group-toggle" data-permissions-action="toggle-expert-page" data-page-key="${esc(page.key)}">
            <span class="material-icons-round">expand_more</span>
            <span class="matrix-tree-group-name">${esc(page.label || page.key)}</span>
          </button>
          <span class="matrix-group-count">${page.items.length}</span>
        </td>
        ${current.roles.map((role) => renderAggregateRoleCell(role, page.items, page.key, 'page', current)).join('')}
      </tr>
      ${page.items.map((meta) => renderExpertPermissionRow(section, page, meta, current, sectionCollapsed || pageCollapsed)).join('')}
    `;
  }

  function renderExpertMatrix() {
    const current = matrixState(state.activeCategory);
    const head = document.getElementById('permissionsMatrixHead');
    const body = document.getElementById('permissionsMatrixBody');
    const queryInput = document.getElementById('permissionsSearchInput');
    const typeFilter = document.getElementById('permissionsTypeFilter');
    const sectionFilter = document.getElementById('permissionsSectionFilter');
    const changedOnly = document.getElementById('permissionsShowChangedOnly');
    const activeOnly = document.getElementById('permissionsShowActiveOnly');
    if (!head || !body) return;
    if (!current.loaded) {
      head.innerHTML = '';
      body.innerHTML = '<tr><td class="center-text muted" colspan="6" style="padding: 36px;">در حال بارگذاری ماتریس حرفه‌ای...</td></tr>';
      return;
    }
    if (queryInput && queryInput.value !== String(current.filters.query || '')) queryInput.value = String(current.filters.query || '');
    if (typeFilter && typeFilter.value !== String(current.filters.type || '')) typeFilter.value = String(current.filters.type || '');
    if (changedOnly) changedOnly.checked = Boolean(current.filters.changedOnly);
    if (activeOnly) activeOnly.checked = Boolean(current.filters.activeOnly);
    renderExpertSectionFilterOptions();
    if (sectionFilter && sectionFilter.value !== String(current.filters.section || '')) sectionFilter.value = String(current.filters.section || '');
    head.innerHTML = `
      <tr>
        <th class="sticky-col">مجوز (درختی)</th>
        ${current.roles.map((role) => `<th>${esc(roleLabel(role))}</th>`).join('')}
      </tr>
    `;
    const visibleMeta = current.permissionsMeta
      .filter((meta) => permissionMatchesExpertFilters(meta, current))
      .sort((a, b) => {
        const bucketCompare = expertBucketFor(a).order - expertBucketFor(b).order;
        if (bucketCompare !== 0) return bucketCompare;
        const pageCompare = String(a.page_label || '').localeCompare(String(b.page_label || ''), 'fa');
        if (pageCompare !== 0) return pageCompare;
        return String(a.label_fa || a.key || '').localeCompare(String(b.label_fa || b.key || ''), 'fa');
      });
    if (!visibleMeta.length) {
      body.innerHTML = `<tr><td class="center-text muted" colspan="${current.roles.length + 1}" style="padding: 36px;">نتیجه‌ای مطابق فیلتر فعلی پیدا نشد.</td></tr>`;
      return;
    }
    const grouped = [];
    const sectionMap = new Map();
    visibleMeta.forEach((meta) => {
      const bucket = expertBucketFor(meta);
      if (!sectionMap.has(bucket.key)) {
        const section = { ...bucket, pages: new Map() };
        sectionMap.set(bucket.key, section);
        grouped.push(section);
      }
      const section = sectionMap.get(bucket.key);
      if (!section.pages.has(meta.page_key)) section.pages.set(meta.page_key, { key: meta.page_key, label: meta.page_label, items: [] });
      section.pages.get(meta.page_key).items.push(meta);
    });
    body.innerHTML = grouped.map((section) => {
      const sectionCollapsed = current.collapsedSections.has(section.key);
      const sectionItems = Array.from(section.pages.values()).flatMap((page) => page.items);
      return `
        <tr class="matrix-tree-section-row ${sectionCollapsed ? 'is-collapsed' : ''}" data-section-key="${esc(section.key)}">
          <td class="matrix-permission-name sticky-col matrix-tree-section-cell">
            <button type="button" class="matrix-tree-section-toggle" data-permissions-action="toggle-expert-section" data-section-key="${esc(section.key)}">
              <span class="material-icons-round">expand_more</span>
              <span class="matrix-tree-section-name">${esc(section.label)}</span>
            </button>
            <span class="matrix-group-count">${sectionItems.length}</span>
          </td>
          ${current.roles.map((role) => renderAggregateRoleCell(role, sectionItems, section.key, 'section', current)).join('')}
        </tr>
        ${Array.from(section.pages.values()).map((page) => renderExpertPage(section, page, current, sectionCollapsed)).join('')}
      `;
    }).join('');
  }

  function renderScopeTag(role, type, code, nameMap, readOnly) {
    const title = nameMap.get(code) && nameMap.get(code) !== code ? `${code} - ${nameMap.get(code)}` : code;
    return `
      <span class="tag-item" title="${esc(title)}">
        <span class="tag-text">${esc(code)}</span>
        ${readOnly ? '' : `<button type="button" class="tag-remove" data-permissions-action="remove-scope-tag" data-role="${esc(role)}" data-scope-type="${esc(type)}" data-code="${esc(code)}" aria-label="حذف">&times;</button>`}
      </span>
    `;
  }

  function renderScopeInput(role, type, label, values, nameMap, readOnly) {
    return `
      <div class="permissions-scope-input-group">
        <label class="form-label-sm">${esc(label)}</label>
        <div class="tags-input ${readOnly ? 'disabled' : ''}">
          <div class="permissions-scope-tags">
            ${(values || []).map((code) => renderScopeTag(role, type, code, nameMap, readOnly)).join('')}
          </div>
          <input
            type="text"
            class="tags-input-field"
            data-permissions-action="scope-input"
            data-role="${esc(role)}"
            data-scope-type="${esc(type)}"
            placeholder="کد را وارد کنید"
            ${readOnly ? 'disabled' : ''}
          >
        </div>
        <div class="tag-suggestions" id="scope-suggestions-${esc(role)}-${esc(type)}"></div>
        <div class="permissions-scope-preview">
          ${(values || []).length
            ? (values || []).map((code) => `<span class="permissions-scope-pill"><strong>${esc(code)}</strong><small>${esc(nameMap.get(code) || code)}</small></span>`).join('')
            : '<span class="permissions-empty-inline">بدون محدودیت</span>'}
        </div>
      </div>
    `;
  }

  function renderScopeRoleCard(role, current) {
    const roleScope = current.scope[role] || { projects: [], disciplines: [] };
    const projectCount = roleScope.projects.length;
    const disciplineCount = roleScope.disciplines.length;
    const copyOptions = current.roles
      .filter((candidate) => candidate !== role)
      .map((candidate) => `<option value="${esc(candidate)}">${esc(roleLabel(candidate))}</option>`)
      .join('');
    const summary = projectCount || disciplineCount
      ? `محدود به ${projectCount || 0} پروژه و ${disciplineCount || 0} دیسیپلین`
      : 'بدون محدودیت';
    return `
      <article class="permissions-scope-role-card">
        <header class="permissions-role-card-header">
          <div>
            <h4>${esc(roleLabel(role))}</h4>
            <div class="permissions-role-card-meta">
              <span class="permissions-role-badge ${projectCount || disciplineCount ? 'is-partial' : 'is-on'}">${esc(summary)}</span>
            </div>
          </div>
          <div class="permissions-role-card-actions">
            <div class="permissions-copy-inline">
              <select class="form-input permissions-copy-select" data-scope-copy-source-for="${esc(role)}" ${current.readOnly ? 'disabled' : ''}>
                <option value="">کپی از نقش دیگر</option>
                ${copyOptions}
              </select>
              <button type="button" class="btn-secondary btn-sm" data-permissions-action="scope-copy-role" data-role="${esc(role)}" ${current.readOnly ? 'disabled' : ''}>اعمال</button>
            </div>
            <div class="permissions-role-card-quick">
              <button type="button" class="btn-secondary btn-sm" data-permissions-action="scope-unrestricted-role" data-role="${esc(role)}" ${current.readOnly ? 'disabled' : ''}>بدون محدودیت</button>
              <button type="button" class="btn-secondary btn-sm" data-permissions-action="scope-clear-role" data-role="${esc(role)}" ${current.readOnly ? 'disabled' : ''}>پاک‌سازی</button>
            </div>
          </div>
        </header>
        <div class="permissions-scope-role-body">
          ${renderScopeInput(role, 'projects', 'پروژه‌ها', roleScope.projects, current.projectMap, current.readOnly)}
          ${renderScopeInput(role, 'disciplines', 'دیسیپلین‌ها', roleScope.disciplines, current.disciplineMap, current.readOnly)}
        </div>
      </article>
    `;
  }

  function renderScopeTab() {
    const current = scopeState(state.activeCategory);
    const container = document.getElementById('permissionsScopeContent');
    if (!container) return;
    if (!current.loaded) {
      container.innerHTML = '<div class="permissions-empty-inline">در حال بارگذاری Scope نقش‌ها...</div>';
      return;
    }
    container.innerHTML = `<div class="permissions-scope-grid permissions-scope-role-grid">${current.roles.map((role) => renderScopeRoleCard(role, current)).join('')}</div>`;
  }

  function permissionSourceLabel(value) {
    const map = {
      full_access: 'دسترسی کامل',
      category_matrix: 'ماتریس دسته‌بندی',
      role_matrix: 'ماتریس نقش',
      static_fallback: 'fallback ثابت',
    };
    const key = String(value || '').trim().toLowerCase();
    return map[key] || (value || '-');
  }

  function navigationItemLabel(group, key) {
    const labels = {
      hubs: {
        dashboard: 'کارتابل',
        edms: 'مدیریت مدارک مهندسی',
        reports: 'گزارش‌ها',
        contractor: 'فرم‌ها و اجرا',
        consultant: 'نظارت و کنترل پروژه',
      },
      edms_tabs: {
        archive: 'آرشیو مدارک',
        transmittal: 'ترنسمیتال',
        correspondence: 'مکاتبات',
      },
      contractor_tabs: {
        execution: 'گزارش کارگاهی',
        requests: 'درخواست‌ها',
        permit_qc: 'Permit + QC',
      },
      consultant_tabs: {
        inspection: 'بازدید و چک‌لیست',
        defects: 'لیست نواقص',
        instructions: 'دستورکار / صورتجلسه',
        control: 'کنترل پروژه',
        permit_qc: 'Permit + QC',
      },
    };
    return (labels[group] && labels[group][key]) || key;
  }

  function renderScopeSummaryCard(title, values, restricted, catalog) {
    if (!restricted) {
      return `<div class="permissions-scope-card"><strong>${esc(title)}</strong><span class="permissions-empty-inline">بدون محدودیت</span></div>`;
    }
    if (!values.length) {
      return `<div class="permissions-scope-card"><strong>${esc(title)}</strong><span class="permissions-empty-inline">بدون دسترسی مؤثر</span></div>`;
    }
    return `
      <div class="permissions-scope-card">
        <strong>${esc(title)}</strong>
        <div class="permissions-scope-preview">
          ${values.map((code) => `<span class="permissions-scope-pill"><strong>${esc(code)}</strong><small>${esc(catalog[code] || code)}</small></span>`).join('')}
        </div>
      </div>
    `;
  }

  function renderEffectiveAccess(payload) {
    const panel = document.getElementById('permissionsEffectiveAccessPanel');
    if (!panel) return;
    if (!payload || !payload.user) {
      panel.innerHTML = `
        <div class="permissions-effective-empty">
          <span class="material-icons-round">shield</span>
          <strong>هنوز کاربری انتخاب نشده است</strong>
          <p>پس از انتخاب کاربر، خلاصه دسترسی مؤثر و وضعیت نهایی UI در همین بخش نمایش داده می‌شود.</p>
        </div>
      `;
      return;
    }

    const user = payload.user || {};
    const navigation = payload.navigation || {};
    const diagnostics = payload.navigation_diagnostics || {};
    const visibleHubs = Object.entries(navigation.hubs || {}).filter(([, value]) => Boolean(value)).map(([key]) => key);
    const visibleEdms = Object.entries(navigation.edms_tabs || {}).filter(([, value]) => Boolean(value)).map(([key]) => key);
    const visibleContractor = Object.entries(navigation.contractor_tabs || {}).filter(([, value]) => Boolean(value)).map(([key]) => key);
    const visibleConsultant = Object.entries(navigation.consultant_tabs || {}).filter(([, value]) => Boolean(value)).map(([key]) => key);
    const projectCatalog = {};
    const disciplineCatalog = {};
    ((payload.effective_scope_catalog && payload.effective_scope_catalog.projects) || []).forEach((item) => {
      projectCatalog[item.code] = item.name || item.code;
    });
    ((payload.effective_scope_catalog && payload.effective_scope_catalog.disciplines) || []).forEach((item) => {
      disciplineCatalog[item.code] = item.name || item.code;
    });

    panel.innerHTML = `
      <div class="permissions-effective-grid">
        <div class="permissions-effective-card"><strong>کاربر</strong><small>${esc(user.full_name || '-')}</small></div>
        <div class="permissions-effective-card"><strong>ایمیل</strong><small>${esc(user.email || '-')}</small></div>
        <div class="permissions-effective-card"><strong>Category</strong><small>${esc(categoryLabel(user.category || payload.category))}</small></div>
        <div class="permissions-effective-card"><strong>Effective Role</strong><small>${esc(roleLabel(user.effective_role || user.role))}</small></div>
        <div class="permissions-effective-card"><strong>منبع مجوز</strong><small>${esc(permissionSourceLabel(user.permission_source))}</small></div>
        <div class="permissions-effective-card"><strong>System Admin</strong><small>${user.is_system_admin ? 'بله' : 'خیر'}</small></div>
      </div>
      <div class="permissions-effective-actions">
        <button type="button" class="btn-secondary" data-permissions-action="open-user-scope-modal" data-user-id="${esc(user.id)}">ویرایش Scope کاربر</button>
        <button type="button" class="btn-secondary" data-permissions-action="goto-users">رفتن به مدیریت کاربران</button>
        <button type="button" class="btn-secondary" data-permissions-action="copy-effective-report">کپی گزارش</button>
      </div>
      <div class="permissions-effective-sections">
        <section class="permissions-effective-section">
          <div class="permissions-effective-section-title">هاب‌های visible</div>
          <div class="permissions-flag-list">
            ${visibleHubs.length ? visibleHubs.map((key) => `<span class="permissions-flag-pill is-allowed">${esc(navigationItemLabel('hubs', key))}</span>`).join('') : '<span class="permissions-empty-inline">موردی برای نمایش وجود ندارد</span>'}
          </div>
        </section>
        <section class="permissions-effective-section">
          <div class="permissions-effective-section-title">تب‌های EDMS</div>
          <div class="permissions-flag-list">
            ${visibleEdms.length ? visibleEdms.map((key) => `<span class="permissions-flag-pill is-allowed">${esc(navigationItemLabel('edms_tabs', key))}</span>`).join('') : '<span class="permissions-empty-inline">موردی برای نمایش وجود ندارد</span>'}
          </div>
        </section>
        <section class="permissions-effective-section">
          <div class="permissions-effective-section-title">تب‌های پیمانکار</div>
          <div class="permissions-flag-list">
            ${visibleContractor.length ? visibleContractor.map((key) => `<span class="permissions-flag-pill is-allowed">${esc(navigationItemLabel('contractor_tabs', key))}</span>`).join('') : '<span class="permissions-empty-inline">موردی برای نمایش وجود ندارد</span>'}
          </div>
        </section>
        <section class="permissions-effective-section">
          <div class="permissions-effective-section-title">تب‌های مشاور</div>
          <div class="permissions-flag-list">
            ${visibleConsultant.length ? visibleConsultant.map((key) => `<span class="permissions-flag-pill is-allowed">${esc(navigationItemLabel('consultant_tabs', key))}</span>`).join('') : '<span class="permissions-empty-inline">موردی برای نمایش وجود ندارد</span>'}
          </div>
        </section>
      </div>
      <div class="permissions-scope-grid">
        ${renderScopeSummaryCard('Role Scope / پروژه', (payload.role_scope && payload.role_scope.projects) || [], Boolean(payload.role_scope && payload.role_scope.projects && payload.role_scope.projects.length), projectCatalog)}
        ${renderScopeSummaryCard('Role Scope / دیسیپلین', (payload.role_scope && payload.role_scope.disciplines) || [], Boolean(payload.role_scope && payload.role_scope.disciplines && payload.role_scope.disciplines.length), disciplineCatalog)}
        ${renderScopeSummaryCard('User Scope / پروژه', (payload.user_scope && payload.user_scope.projects) || [], Boolean(payload.user_scope && payload.user_scope.projects && payload.user_scope.projects.length), projectCatalog)}
        ${renderScopeSummaryCard('User Scope / دیسیپلین', (payload.user_scope && payload.user_scope.disciplines) || [], Boolean(payload.user_scope && payload.user_scope.disciplines && payload.user_scope.disciplines.length), disciplineCatalog)}
        ${renderScopeSummaryCard('Effective Scope / پروژه', (payload.effective_scope && payload.effective_scope.projects) || [], Boolean(payload.effective_scope && payload.effective_scope.projects_restricted), projectCatalog)}
        ${renderScopeSummaryCard('Effective Scope / دیسیپلین', (payload.effective_scope && payload.effective_scope.disciplines) || [], Boolean(payload.effective_scope && payload.effective_scope.disciplines_restricted), disciplineCatalog)}
      </div>
      <section class="permissions-effective-section">
        <div class="permissions-effective-section-title">هشدارهای ناوبری</div>
        <div class="permissions-code-list">
          ${(diagnostics.warnings || []).length ? diagnostics.warnings.map((item) => `<code>${esc(item)}</code>`).join('') : '<span class="permissions-empty-inline">هشدار ناوبری ثبت نشده است.</span>'}
        </div>
      </section>
      <details class="permissions-effective-section">
        <summary class="permissions-effective-section-title">نمونه مجوزهای denied</summary>
        <div class="permissions-code-list">
          ${(payload.denied_permissions_sample || []).length ? payload.denied_permissions_sample.map((item) => `<code>${esc(item)}</code>`).join('') : '<span class="permissions-empty-inline">نمونه denied وجود ندارد.</span>'}
        </div>
      </details>
      <details class="permissions-effective-section">
        <summary class="permissions-effective-section-title">Raw Granted Permissions</summary>
        <div class="permissions-code-list">
          ${(payload.granted_permissions || []).length ? payload.granted_permissions.map((item) => `<code>${esc(item)}</code>`).join('') : '<span class="permissions-empty-inline">مجوز فعالی وجود ندارد.</span>'}
        </div>
      </details>
    `;
  }

  async function searchEffectiveAccessUsers(query) {
    const text = String(query || '').trim();
    const container = document.getElementById('permissionsAuditUserResults');
    if (!container) return;
    if (!text) {
      state.effective.results = [];
      container.classList.remove('is-open');
      container.innerHTML = '';
      return;
    }
    const payload = await request(`${USERS_SEARCH_ENDPOINT}?page=1&page_size=8&q=${encodeURIComponent(text)}`);
    state.effective.results = Array.isArray(payload.items) ? payload.items : [];
    renderAuditUserResults();
  }

  function renderAuditUserResults() {
    const container = document.getElementById('permissionsAuditUserResults');
    if (!container) return;
    const items = state.effective.results || [];
    if (!items.length) {
      container.classList.remove('is-open');
      container.innerHTML = '';
      return;
    }
    container.innerHTML = items.map((item) => `
      <button type="button" class="permissions-audit-result" data-permissions-action="select-effective-user" data-user-id="${esc(item.id)}" data-user-label="${esc(item.full_name || item.email || '')}">
        <strong>${esc(item.full_name || item.email || '-')}</strong>
        <span>${esc(item.email || '-')}</span>
        <small>${esc(categoryLabel(item.organization_type || item.permission_category))} / ${esc(roleLabel(item.effective_role || item.role))}</small>
      </button>
    `).join('');
    container.classList.add('is-open');
  }

  async function loadEffectiveAccess(userId, userLabel = '') {
    if (!userId) return;
    state.effective.selectedUserId = Number(userId);
    state.effective.selectedUserLabel = String(userLabel || '');
    state.effective.loading = true;
    const input = document.getElementById('permissionsAuditUserSearch');
    if (input && userLabel) input.value = userLabel;
    const payload = await request(`${USER_ACCESS_ENDPOINT}/${encodeURIComponent(userId)}`);
    state.effective.loading = false;
    state.effective.payload = payload;
    renderEffectiveAccess(payload);
  }

  function renderAll() {
    renderCategorySwitcher();
    renderSubtabs();
    renderOverviewTab();
    renderExpertMatrix();
    renderScopeTab();
    if (state.activeSubtab === 'effective') renderEffectiveAccess(state.effective.payload);
    updateHeaderState();
  }

  function addScopeTag(role, type, rawValue) {
    const current = scopeState(state.activeCategory);
    const code = String(rawValue || '').trim().toUpperCase();
    if (!code) return;
    const catalog = type === 'projects' ? current.projects : current.disciplines;
    const exists = (catalog || []).some((item) => String(item.code || '').trim().toUpperCase() === code);
    if (!exists) {
      notify('warning', 'کد وارد شده در فهرست موجود نیست.');
      return;
    }
    current.scope[role][type] = normalizeScopeValues([...(current.scope[role][type] || []), code]);
    computeScopeDirty(state.activeCategory);
    renderScopeTab();
    updateHeaderState();
  }

  function removeScopeTag(role, type, rawValue) {
    const current = scopeState(state.activeCategory);
    const code = String(rawValue || '').trim().toUpperCase();
    current.scope[role][type] = normalizeScopeValues((current.scope[role][type] || []).filter((item) => item !== code));
    computeScopeDirty(state.activeCategory);
    renderScopeTab();
    updateHeaderState();
  }

  function renderScopeSuggestions(role, type, query = '') {
    const current = scopeState(state.activeCategory);
    const container = document.getElementById(`scope-suggestions-${role}-${type}`);
    if (!container) return;
    const catalog = type === 'projects' ? current.projects : current.disciplines;
    const selected = new Set((current.scope[role] && current.scope[role][type]) || []);
    const text = String(query || '').trim().toUpperCase();
    const items = (catalog || []).filter((item) => {
      const code = String(item.code || '').toUpperCase();
      const name = String(item.name || '').toUpperCase();
      if (selected.has(code)) return false;
      if (!text) return true;
      return code.includes(text) || name.includes(text);
    }).slice(0, 8);
    if (!items.length) {
      container.classList.remove('show');
      container.innerHTML = '';
      return;
    }
    container.innerHTML = items.map((item) => `
      <button type="button" class="tag-suggestion-item" data-permissions-action="select-scope-suggestion" data-role="${esc(role)}" data-scope-type="${esc(type)}" data-code="${esc(String(item.code || '').toUpperCase())}">
        <span class="tag-suggestion-code">${esc(String(item.code || '').toUpperCase())}</span>
        <span class="tag-suggestion-name">${esc(String(item.name || item.code || ''))}</span>
      </button>
    `).join('');
    container.classList.add('show');
  }

  function handleToggleFeature(role, featureKey, checked) {
    const current = matrixState(state.activeCategory);
    const feature = current.featureIndex[featureKey];
    if (!feature) return;
    (feature.base_permissions || []).forEach((permission) => {
      current.matrix[role][permission] = Boolean(checked);
    });
    computeMatrixDirty(state.activeCategory);
    renderOverviewTab();
    renderExpertMatrix();
    updateHeaderState();
  }

  function handleTogglePermission(role, permission, checked) {
    const current = matrixState(state.activeCategory);
    current.matrix[role][permission] = Boolean(checked);
    if (checked) {
      const feature = (current.featureCatalog || []).find((item) => Array.isArray(item.action_permissions) && item.action_permissions.includes(permission));
      if (feature) {
        const missingBase = (feature.base_permissions || []).some((key) => !current.matrix[role][key]);
        (feature.base_permissions || []).forEach((basePermission) => {
          current.matrix[role][basePermission] = true;
        });
        if (missingBase) setFooterStatus(`برای فعال شدن این عملیات، Bundle پایه ${feature.label_fa} هم فعال شد.`);
      }
    }
    computeMatrixDirty(state.activeCategory);
    renderOverviewTab();
    renderExpertMatrix();
    updateHeaderState();
  }

  function copyRoleFrom(role, sourceRole) {
    const current = matrixState(state.activeCategory);
    if (!sourceRole || !current.matrix[sourceRole]) return;
    current.matrix[role] = cloneDeep(current.matrix[sourceRole]);
    computeMatrixDirty(state.activeCategory);
    renderOverviewTab();
    renderExpertMatrix();
    updateHeaderState();
    setFooterStatus(`مجوزهای ${roleLabel(sourceRole)} به ${roleLabel(role)} کپی شد.`);
  }

  function resetRoleToBaseline(role) {
    const current = matrixState(state.activeCategory);
    current.matrix[role] = cloneDeep(current.baselineMatrix[role] || {});
    ensureMatrixDefaults(current);
    computeMatrixDirty(state.activeCategory);
    renderOverviewTab();
    renderExpertMatrix();
    updateHeaderState();
  }

  function clearRole(role) {
    const current = matrixState(state.activeCategory);
    current.permissions.forEach((permission) => {
      current.matrix[role][permission] = false;
    });
    computeMatrixDirty(state.activeCategory);
    renderOverviewTab();
    renderExpertMatrix();
    updateHeaderState();
  }

  function setRoleViewer(role) {
    copyRoleFrom(role, 'viewer');
  }

  function handleToggleExpertAggregate(role, scopeType, scopeKey, checked) {
    const current = matrixState(state.activeCategory);
    resolveExpertScopeItems(scopeType, scopeKey, current).forEach((meta) => {
      current.matrix[role][meta.key] = Boolean(checked);
    });
    computeMatrixDirty(state.activeCategory);
    renderOverviewTab();
    renderExpertMatrix();
    updateHeaderState();
  }

  function resetCurrentDraft() {
    if (state.activeSubtab === 'effective') return;
    if (state.activeSubtab === 'scope') {
      const current = scopeState(state.activeCategory);
      current.scope = cloneDeep(current.originalScope);
      computeScopeDirty(state.activeCategory);
      renderScopeTab();
      updateHeaderState();
      return;
    }
    const current = matrixState(state.activeCategory);
    current.matrix = cloneDeep(current.originalMatrix);
    ensureMatrixDefaults(current);
    computeMatrixDirty(state.activeCategory);
    renderOverviewTab();
    renderExpertMatrix();
    updateHeaderState();
  }

  async function reloadCurrentCategory() {
    await ensureCategoryLoaded(state.activeCategory, true);
    if (state.effective.selectedUserId) {
      try {
        await loadEffectiveAccess(state.effective.selectedUserId, state.effective.selectedUserLabel);
      } catch (_) {}
    }
    renderAll();
  }

  async function saveCurrentSubtab() {
    if (state.activeSubtab === 'effective') return;
    if (state.activeSubtab === 'scope') {
      const current = scopeState(state.activeCategory);
      if (current.readOnly) {
        notify('warning', 'Scope این دسته فقط خواندنی است.');
        return;
      }
      await request(`${SCOPE_ENDPOINT}?category=${encodeURIComponent(state.activeCategory)}`, {
        method: 'POST',
        body: { scope: current.scope },
      });
      current.originalScope = cloneDeep(current.scope);
      current.lastSavedAt = formatNow();
      computeScopeDirty(state.activeCategory);
      notify('success', `Scope دسته ${categoryLabel(state.activeCategory)} ذخیره شد.`);
    } else {
      const current = matrixState(state.activeCategory);
      if (current.readOnly) {
        notify('warning', 'ماتریس این دسته فقط خواندنی است.');
        return;
      }
      await request(`${MATRIX_ENDPOINT}?category=${encodeURIComponent(state.activeCategory)}`, {
        method: 'POST',
        body: { matrix: current.matrix },
      });
      current.originalMatrix = cloneDeep(current.matrix);
      current.lastSavedAt = formatNow();
      computeMatrixDirty(state.activeCategory);
      notify('success', `ماتریس دسته ${categoryLabel(state.activeCategory)} ذخیره شد.`);
    }
    if (state.effective.selectedUserId) {
      try {
        await loadEffectiveAccess(state.effective.selectedUserId, state.effective.selectedUserLabel);
      } catch (_) {}
    }
    renderAll();
  }

  async function copyEffectiveReportToClipboard() {
    const payload = state.effective.payload;
    if (!payload || !payload.user) return;
    const user = payload.user;
    const lines = [
      `کاربر: ${user.full_name || '-'}`,
      `ایمیل: ${user.email || '-'}`,
      `Category: ${categoryLabel(user.category || payload.category)}`,
      `Effective Role: ${roleLabel(user.effective_role || user.role)}`,
      `Permission Source: ${permissionSourceLabel(user.permission_source)}`,
    ];
    await navigator.clipboard.writeText(lines.join('\n'));
    notify('success', 'گزارش دسترسی مؤثر کپی شد.');
  }

  function bindActions() {
    if (state.actionsBound) return;
    const root = document.getElementById('settingsPermissionsTabRoot');
    if (!root) return;

    root.addEventListener('click', async (event) => {
      const actionEl = event.target && event.target.closest ? event.target.closest('[data-permissions-action]') : null;
      if (!actionEl || !root.contains(actionEl)) return;
      const action = String(actionEl.getAttribute('data-permissions-action') || '');
      try {
        switch (action) {
          case 'switch-category':
            state.activeCategory = normalizeCategory(actionEl.getAttribute('data-permissions-category') || '');
            persistWorkspaceState();
            await ensureCategoryLoaded(state.activeCategory, false);
            renderAll();
            if (state.activeSubtab === 'effective' && state.effective.selectedUserId) {
              await loadEffectiveAccess(state.effective.selectedUserId, state.effective.selectedUserLabel);
            }
            break;
          case 'switch-subtab':
            state.activeSubtab = String(actionEl.getAttribute('data-subtab') || DEFAULT_SUBTAB);
            persistWorkspaceState();
            renderAll();
            if (state.activeSubtab === 'effective' && state.effective.selectedUserId) await loadEffectiveAccess(state.effective.selectedUserId, state.effective.selectedUserLabel);
            break;
          case 'reload-current':
            await reloadCurrentCategory();
            break;
          case 'reset-current':
            resetCurrentDraft();
            break;
          case 'save-current':
            await saveCurrentSubtab();
            break;
          case 'toggle-feature-bundle':
            handleToggleFeature(normalizeRole(actionEl.getAttribute('data-role') || ''), String(actionEl.getAttribute('data-feature-key') || ''), Boolean(actionEl.checked));
            break;
          case 'copy-role-from': {
            const role = normalizeRole(actionEl.getAttribute('data-role') || '');
            const select = root.querySelector(`[data-copy-source-for="${role}"]`);
            copyRoleFrom(role, select ? normalizeRole(select.value) : '');
            break;
          }
          case 'reset-role-baseline':
            resetRoleToBaseline(normalizeRole(actionEl.getAttribute('data-role') || ''));
            break;
          case 'clear-role':
            clearRole(normalizeRole(actionEl.getAttribute('data-role') || ''));
            break;
          case 'set-role-viewer':
            setRoleViewer(normalizeRole(actionEl.getAttribute('data-role') || ''));
            break;
          case 'toggle-expert-section': {
            const current = matrixState(state.activeCategory);
            const key = String(actionEl.getAttribute('data-section-key') || '');
            if (current.collapsedSections.has(key)) current.collapsedSections.delete(key); else current.collapsedSections.add(key);
            renderExpertMatrix();
            break;
          }
          case 'toggle-expert-page': {
            const current = matrixState(state.activeCategory);
            const key = String(actionEl.getAttribute('data-page-key') || '');
            if (current.collapsedPages.has(key)) current.collapsedPages.delete(key); else current.collapsedPages.add(key);
            renderExpertMatrix();
            break;
          }
          case 'expand-expert':
            matrixState(state.activeCategory).collapsedSections.clear();
            matrixState(state.activeCategory).collapsedPages.clear();
            renderExpertMatrix();
            break;
          case 'collapse-expert': {
            const current = matrixState(state.activeCategory);
            current.permissionsMeta.forEach((meta) => {
              current.collapsedSections.add(expertBucketFor(meta).key);
              current.collapsedPages.add(String(meta.page_key || ''));
            });
            renderExpertMatrix();
            break;
          }
          case 'clear-expert-filters': {
            const current = matrixState(state.activeCategory);
            current.filters = { query: '', type: '', section: '', changedOnly: false, activeOnly: false };
            const searchInput = document.getElementById('permissionsSearchInput');
            const typeFilter = document.getElementById('permissionsTypeFilter');
            const sectionFilter = document.getElementById('permissionsSectionFilter');
            const changedOnly = document.getElementById('permissionsShowChangedOnly');
            const activeOnly = document.getElementById('permissionsShowActiveOnly');
            if (searchInput) searchInput.value = '';
            if (typeFilter) typeFilter.value = '';
            if (sectionFilter) sectionFilter.value = '';
            if (changedOnly) changedOnly.checked = false;
            if (activeOnly) activeOnly.checked = false;
            renderExpertMatrix();
            break;
          }
          case 'toggle-expert-aggregate':
            handleToggleExpertAggregate(normalizeRole(actionEl.getAttribute('data-role') || ''), String(actionEl.getAttribute('data-scope-type') || ''), String(actionEl.getAttribute('data-scope-key') || ''), Boolean(actionEl.checked));
            break;
          case 'scope-copy-role': {
            const role = normalizeRole(actionEl.getAttribute('data-role') || '');
            const select = root.querySelector(`[data-scope-copy-source-for="${role}"]`);
            const sourceRole = select ? normalizeRole(select.value) : '';
            if (sourceRole) {
              scopeState(state.activeCategory).scope[role] = cloneDeep(scopeState(state.activeCategory).scope[sourceRole] || { projects: [], disciplines: [] });
              computeScopeDirty(state.activeCategory);
              renderScopeTab();
              updateHeaderState();
            }
            break;
          }
          case 'scope-unrestricted-role':
          case 'scope-clear-role':
            scopeState(state.activeCategory).scope[normalizeRole(actionEl.getAttribute('data-role') || '')] = { projects: [], disciplines: [] };
            computeScopeDirty(state.activeCategory);
            renderScopeTab();
            updateHeaderState();
            break;
          case 'remove-scope-tag':
            removeScopeTag(normalizeRole(actionEl.getAttribute('data-role') || ''), String(actionEl.getAttribute('data-scope-type') || ''), String(actionEl.getAttribute('data-code') || ''));
            break;
          case 'select-scope-suggestion':
            addScopeTag(normalizeRole(actionEl.getAttribute('data-role') || ''), String(actionEl.getAttribute('data-scope-type') || ''), String(actionEl.getAttribute('data-code') || ''));
            break;
          case 'select-effective-user':
            state.effective.results = [];
            renderAuditUserResults();
            await loadEffectiveAccess(Number(actionEl.getAttribute('data-user-id') || 0), String(actionEl.getAttribute('data-user-label') || ''));
            break;
          case 'open-user-scope-modal':
            if (window.openSettingsTab) window.openSettingsTab('users');
            if (window.openSettingsUserAccessModal) window.openSettingsUserAccessModal(Number(actionEl.getAttribute('data-user-id') || 0));
            break;
          case 'goto-users':
            if (window.openSettingsTab) window.openSettingsTab('users');
            if (window.loadUsers) window.loadUsers({ resetPage: false, reloadScope: true });
            break;
          case 'copy-effective-report':
            await copyEffectiveReportToClipboard();
            break;
          default:
            break;
        }
      } catch (error) {
        notify('error', error.message || 'عملیات مدیریت دسترسی ناموفق بود.');
      }
    });

    root.addEventListener('change', (event) => {
      const actionEl = event.target && event.target.closest ? event.target.closest('[data-permissions-action]') : null;
      if (!actionEl || !root.contains(actionEl)) return;
      if (String(actionEl.getAttribute('data-permissions-action') || '') !== 'toggle-permission') return;
      handleTogglePermission(normalizeRole(actionEl.getAttribute('data-role') || ''), decodeURIComponent(String(actionEl.getAttribute('data-permission') || '')), Boolean(actionEl.checked));
    });

    root.addEventListener('input', (event) => {
      const target = event.target;
      if (!target) return;
      if (target.id === 'permissionsSearchInput') {
        matrixState(state.activeCategory).filters.query = target.value || '';
        renderExpertMatrix();
      } else if (target.id === 'permissionsAuditUserSearch') {
        state.effective.query = target.value || '';
        if (state.effective.searchTimer) window.clearTimeout(state.effective.searchTimer);
        state.effective.searchTimer = window.setTimeout(async () => {
          try {
            await searchEffectiveAccessUsers(state.effective.query);
          } catch (error) {
            notify('error', error.message || 'جست‌وجوی کاربر ناموفق بود.');
          }
        }, SEARCH_DEBOUNCE_MS);
      } else if (target.getAttribute('data-permissions-action') === 'scope-input') {
        renderScopeSuggestions(normalizeRole(target.getAttribute('data-role') || ''), String(target.getAttribute('data-scope-type') || ''), target.value || '');
      }
    });

    root.addEventListener('focusin', (event) => {
      const target = event.target;
      if (target && target.getAttribute && target.getAttribute('data-permissions-action') === 'scope-input') {
        renderScopeSuggestions(normalizeRole(target.getAttribute('data-role') || ''), String(target.getAttribute('data-scope-type') || ''), target.value || '');
      }
    });

    root.addEventListener('keydown', (event) => {
      const target = event.target;
      if (!target || target.getAttribute('data-permissions-action') !== 'scope-input') return;
      const role = normalizeRole(target.getAttribute('data-role') || '');
      const type = String(target.getAttribute('data-scope-type') || '');
      if (event.key === 'Enter' || event.key === ',') {
        event.preventDefault();
        addScopeTag(role, type, target.value || '');
      } else if (event.key === 'Backspace' && !target.value) {
        const values = scopeState(state.activeCategory).scope[role][type] || [];
        const last = values[values.length - 1];
        if (last) removeScopeTag(role, type, last);
      }
    });

    const typeFilter = document.getElementById('permissionsTypeFilter');
    const sectionFilter = document.getElementById('permissionsSectionFilter');
    const changedOnly = document.getElementById('permissionsShowChangedOnly');
    const activeOnly = document.getElementById('permissionsShowActiveOnly');
    if (typeFilter) typeFilter.addEventListener('change', () => { matrixState(state.activeCategory).filters.type = typeFilter.value || ''; renderExpertMatrix(); });
    if (sectionFilter) sectionFilter.addEventListener('change', () => { matrixState(state.activeCategory).filters.section = sectionFilter.value || ''; renderExpertMatrix(); });
    if (changedOnly) changedOnly.addEventListener('change', () => { matrixState(state.activeCategory).filters.changedOnly = Boolean(changedOnly.checked); renderExpertMatrix(); });
    if (activeOnly) activeOnly.addEventListener('change', () => { matrixState(state.activeCategory).filters.activeOnly = Boolean(activeOnly.checked); renderExpertMatrix(); });

    state.actionsBound = true;
  }

  async function init(forceReload = false) {
    bindActions();
    await ensureCategoryLoaded(state.activeCategory, forceReload);
    renderAll();
    if (state.effective.selectedUserId) {
      try {
        await loadEffectiveAccess(state.effective.selectedUserId, state.effective.selectedUserLabel);
      } catch (error) {
        notify('warning', error.message || 'بارگذاری دسترسی مؤثر ناموفق بود.');
      }
    }
    state.initialized = true;
  }

  window.openPermissionsEffectiveAccessUser = async function openPermissionsEffectiveAccessUser(userId, userLabel = '') {
    state.activeSubtab = 'effective';
    state.effective.selectedUserId = Number(userId || 0) || null;
    state.effective.selectedUserLabel = String(userLabel || '');
    persistWorkspaceState();
    if (window.openSettingsTab) window.openSettingsTab('permissions');
    await init(false);
    if (state.effective.selectedUserId) await loadEffectiveAccess(state.effective.selectedUserId, state.effective.selectedUserLabel);
    renderAll();
  };

  window.initPermissionsSettings = async function initPermissionsSettings(force = false) {
    try {
      await init(Boolean(force));
    } catch (error) {
      notify('error', error.message || 'بارگذاری workspace مدیریت دسترسی ناموفق بود.');
    }
  };
})();
