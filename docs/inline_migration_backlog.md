# Inline Script Migration Backlog

This backlog is the route-level scope for Phase 8 (inline scripts and inline handlers extraction).

## Current Inventory

- Inline `<script>` in templates: 0 files
- Inline event handlers (`onclick`, `onchange`, etc.): 0 files

## Priority A (active route-level pages)

- `templates/views/archive.html`
- `templates/views/partials/settings_users_tab.html`
- `templates/views/profile_settings.html`
- `templates/components/doc_search.html`
- `templates/views/transmittal.html`
- `templates/views/correspondence.html`
- `templates/views/edms.html`
- `templates/base.html`

## Priority B (login and standalone pages)

- `templates/login_standalone.html`
- `templates/views/login.html`
- `templates/views/login_simple.html`
- `templates/views/login_working.html`
- `templates/views/debug_login.html`

## Priority C (settings partials)

- `templates/views/partials/settings_bulk_tab.html`
- `templates/views/partials/settings_general_tab.html`
- `templates/views/partials/settings_organizations_tab.html`
- `templates/views/partials/settings_permissions_tab.html`
- `templates/views/partials/settings_reports_tab.html`

## Priority D (legacy / utility)

- `templates/components/scripts.html`
- `templates/views/reports.html`
- `templates/views/settings.html`
- `templates/mdr/bulk_register.html`
- `templates/views/contractor_hub.html`
- `templates/views/consultant_hub.html`

## Completed in this step

- Extracted inline header bootstrap logic from `templates/components/header.html` to:
  - `static/js/views/header.js`
- Extracted inline handlers from `templates/base.html` to:
  - `static/js/views/base_interactions.js`
- Extracted inline archive script from `templates/views/archive.html` to:
  - `static/js/views/archive.js`
- Extracted inline settings users tab script from `templates/views/partials/settings_users_tab.html` to:
  - `static/js/views/settings_users_tab.js`
- Extracted inline profile settings script and removed inline handlers from `templates/views/profile_settings.html`:
  - `static/js/views/profile_settings.js`
- Extracted inline global doc search script from `templates/components/doc_search.html` to:
  - `static/js/views/doc_search.js`
- Removed inline handlers from `templates/views/edms.html` and bound actions in:
  - `static/js/views/edms.js`
- Removed inline handlers from `templates/views/transmittal.html` and bound actions in:
  - `static/js/transmittal_v2.js`
- Removed inline handlers from module tabs in:
  - `templates/views/contractor_hub.html`
  - `templates/views/consultant_hub.html`
  - Bound tab clicks in `static/js/views/contractor.js` and `static/js/views/consultant.js`
- Extracted inline frame-resize script from `templates/views/partials/settings_bulk_tab.html` to:
  - `static/js/views/settings_bulk_tab.js`
- Extracted inline scripts from route-level login pages:
  - `templates/login_standalone.html` -> `static/js/views/login_standalone.js`
  - `templates/views/debug_login.html` -> `static/js/views/debug_login.js`
- Extracted remaining inline scripts/handlers from legacy login templates:
  - `templates/views/login.html` -> `static/js/views/login_legacy_view.js`
  - `templates/views/login_simple.html` -> `static/js/views/login_legacy_view.js`
  - `templates/views/login_working.html` -> `static/js/views/login_legacy_view.js`
- Extracted bulk register page script from `templates/mdr/bulk_register.html` to:
  - `static/js/views/mdr_bulk_register.js`
- Replaced bulk register inline handlers with delegated bindings:
  - tabs / upload / toolbar actions / row clone-delete now handled in `static/js/views/mdr_bulk_register.js`
- TS bridge hardening for gradual `app.js` migration:
  - `frontend/src/lib/legacy.ts` now registers `ViewBoot` hooks as `{ init() {} }` objects compatible with `runViewInitializer`
  - TS entry keys normalized to route-level IDs (`view-dashboard`, `view-edms`, ...)
  - `frontend/src/globals.d.ts` updated with typed `ViewBoot`/`registerViewBoot`
- Navigation/App-Shell first slice extracted to TS:
  - new `frontend/src/lib/app_shell.ts` (public-page guard, delegated nav listeners, sidebar/menu toggles, sidebar active-state mapping)
  - `frontend/src/entries/app.ts` now installs `window.__TS_APP_SHELL__`
  - `static/js/app.js` delegates shell functions to TS bridge with legacy fallback retained
- Boot + Router first extraction to TS:
  - new `frontend/src/lib/app_boot.ts` for `window.onload` orchestration (dictionary, EDMS nav, first route, listeners)
  - new `frontend/src/lib/app_router.ts` for `navigateTo`/route switch orchestration
  - `static/js/app.js` delegates `window.onload` and `navigateTo` to TS bridges with legacy fallback retained
- EDMS state + tab-flow extraction to TS:
  - new `frontend/src/lib/edms_state.ts` (pending/default/visibility state, nav mapping, last-tab persistence, header-stats throttle state)
  - `frontend/src/entries/app.ts` now installs `window.__TS_EDMS_STATE__`
  - `static/js/app.js` delegates EDMS stateful functions (`mapToRoutedView`, `loadEdmsNavigation`, `openEdmsTab` state writes, last-tab helpers, header-stats guard) with legacy fallback retained
- ModuleBoard helper + orchestration extraction to TS:
  - new `frontend/src/lib/module_board.ts` (key/canEdit/format/status/priority + summary refresh + tab-open orchestration)
  - `frontend/src/entries/app.ts` now installs `window.__TS_MODULE_BOARD__`
  - `static/js/app.js` delegates `moduleBoardKey`, `moduleBoardCanEdit`, format/class helpers, `moduleBoardRefreshSummary`, and `moduleBoardOnTabOpened` with legacy fallback retained
- ModuleBoard action binding + debounce extraction to TS:
  - `frontend/src/lib/module_board.ts` provides `bindActions` and `debouncedLoad`
  - `static/js/app.js` now delegates `moduleBoardBindActions` and `moduleBoardDebouncedLoad` to TS bridge first, with legacy fallback retained
- ModuleBoard load orchestration extraction to TS:
  - `frontend/src/lib/module_board.ts` now provides `load` (query params, fetch, cache update, empty/error/loading state)
  - `static/js/app.js` delegates `moduleBoardLoad` to TS bridge first and keeps full legacy fallback path
- ModuleBoard save/delete extraction to TS:
  - `frontend/src/lib/module_board.ts` now provides `save` and `delete` mutation orchestration
  - `static/js/app.js` delegates `moduleBoardSave` and `moduleBoardDelete` to TS bridge first with legacy fallback retained
- ModuleBoard form/edit extraction to TS:
  - `frontend/src/lib/module_board.ts` now provides `resetForm`, `openForm`, `closeForm`, and `edit`
  - `static/js/app.js` delegates `moduleBoardResetForm`, `moduleBoardOpenForm`, `moduleBoardCloseForm`, and `moduleBoardEdit` to TS bridge first with legacy fallback retained
- Navigation helpers extraction to TS router bridge:
  - `frontend/src/lib/app_router.ts` now provides `runViewInitializer` and `activateView`
  - `static/js/app.js` delegates `runViewInitializer` and `activateViewSection` to TS router bridge first with legacy fallback retained
- View partial loader extraction to TS:
  - new `frontend/src/lib/view_loader.ts` provides `executeScriptsInElement` and `loadViewPartial`
  - `frontend/src/entries/app.ts` now installs `window.__TS_VIEW_LOADER__`
  - `static/js/app.js` delegates `executeScriptsInElement` and `loadViewPartial` to TS bridge first with legacy fallback retained
- App data/bootstrap extraction to TS:
  - new `frontend/src/lib/app_data.ts` provides `ensureXlsxLoaded` and `loadDictionary`
  - `frontend/src/entries/app.ts` now installs `window.__TS_APP_DATA__`
  - `static/js/app.js` delegates `ensureXlsxLoaded` and `loadDictionary` to TS bridge first with legacy fallback retained
- EDMS header stats orchestration extraction to TS:
  - `frontend/src/lib/edms_state.ts` now provides `loadHeaderStats` (cache gate + loading state + fetch/apply flow)
  - `static/js/app.js` delegates `loadEdmsHeaderStats` to TS bridge first with legacy fallback retained
- EDMS navigation + visibility orchestration extraction to TS:
  - `frontend/src/lib/edms_state.ts` now provides `applyTabVisibility` and `loadNavigationAndApply`
  - `static/js/app.js` delegates `applyEdmsTabVisibility` and `loadEdmsNavigation` to TS bridge first with legacy fallback retained
- EDMS tab-open orchestration extraction to TS:
  - `frontend/src/lib/edms_state.ts` now provides `openTab` (panel/button activation, pending tab, side-effect hook, last-tab persistence)
  - `static/js/app.js` delegates `openEdmsTab` to TS bridge first with legacy fallback retained
- Contractor/Consultant tab orchestration extraction to TS:
  - new `frontend/src/lib/module_tabs.ts` provides `switchTab` and `resolveInitialTab`
  - `frontend/src/entries/app.ts` now installs `window.__TS_MODULE_TABS__`
  - `static/js/app.js` delegates `switchModuleTab`, `openContractorTab`, `openConsultantTab`, `initContractorView`, and `initConsultantView` to TS bridge first with legacy fallback retained
- Browser-level smoke coverage added:
  - `playwright.config.ts`
  - `tests/e2e/app_smoke.spec.ts`
  - CI lane `e2e-browser` in `.github/workflows/ci.yml`
- Transmittal 2.0 UI orchestration extracted to TS:
  - new `frontend/src/lib/transmittal_ui.ts` (mode switching + delegated action binding + field-event binding)
  - `frontend/src/entries/app.ts` now installs `window.__TS_TRANSMITTAL_UI__`
  - `static/js/transmittal_v2.js` delegates `showCreateMode`/`showListMode` and binding functions to TS bridge first with legacy fallback retained
- Transmittal 2.0 data slice extracted to TS:
  - new `frontend/src/lib/transmittal_data.ts` (request wrapper + list/stats/next-number/eligible-docs)
  - `frontend/src/entries/app.ts` now installs `window.__TS_TRANSMITTAL_DATA__`
  - `static/js/transmittal_v2.js` delegates `request`, `loadTransmittalStats`, `loadTransmittals`, `refreshTransmittalNumber`, and `searchEligibleDocs` to TS bridge first with legacy fallback retained
- Transmittal 2.0 mutation/actions extraction to TS:
  - new `frontend/src/lib/transmittal_mutations.ts` (detail/create/update/issue/void/download-cover)
  - `frontend/src/entries/app.ts` now installs `window.__TS_TRANSMITTAL_MUTATIONS__`
  - `static/js/transmittal_v2.js` delegates detail+mutation calls to TS bridge first with legacy fallback retained
  - list/action buttons now use delegated `data-tr2-action` handlers (`download-cover`, `edit-item`, `issue-item`, `void-item`, `doc-add`, `doc-remove`) instead of dynamic inline `onclick`
- Correspondence C2 API slice extracted to TS bridges:
  - new `frontend/src/lib/correspondence_data.ts` (catalog/dashboard/list/actions/attachments reads)
  - new `frontend/src/lib/correspondence_mutations.ts` (save/upsert/toggle/delete/upload/download/delete mutations)
  - `frontend/src/entries/app.ts` now installs `window.__TS_CORRESPONDENCE_DATA__` and `window.__TS_CORRESPONDENCE_MUTATIONS__`
  - `static/js/correspondence.js` delegates API flows to TS bridges first with legacy fallback retained
- Correspondence UI orchestration extracted to TS:
  - new `frontend/src/lib/correspondence_ui.ts` (filters/form/modal/action delegated bindings)
  - `frontend/src/entries/app.ts` now installs `window.__TS_CORRESPONDENCE_UI__`
  - `static/js/correspondence.js` delegates `bindEvents` to TS bridge first with legacy fallback retained
- Correspondence state/render extraction to TS:
  - new `frontend/src/lib/correspondence_state.ts` (reference preview + select fill + pager + rows/actions/attachments renderers)
  - `frontend/src/entries/app.ts` now installs `window.__TS_CORRESPONDENCE_STATE__`
  - `static/js/correspondence.js` delegates `fillSelect`, `refPreview`, `renderPager`, `renderRows`, `fillActionOptions`, `renderActions`, and `renderAtts` to TS bridge first with legacy fallback retained
- Correspondence form/business slice extraction to TS:
  - new `frontend/src/lib/correspondence_form.ts` (`createDefaultValues`, `buildPayload`, `normalizeEditValues`, `resolveProjectFromIssuing`)
  - `frontend/src/entries/app.ts` now installs `window.__TS_CORRESPONDENCE_FORM__`
  - `static/js/correspondence.js` delegates `formDefaults`, `payloadForm`, `corrOpenEdit`, and `syncProjectFromIssuing` to TS bridge first with legacy fallback retained
- Correspondence action-editor extraction to TS:
  - `frontend/src/lib/correspondence_form.ts` now includes action helpers (`createActionEditorDefaults`, `buildActionPayload`, `normalizeActionEditValues`)
  - `static/js/correspondence.js` delegates action-editor defaults, edit mapping, and action payload build to TS bridge first with legacy fallback retained
- Correspondence workflow orchestration extraction to TS:
  - new `frontend/src/lib/correspondence_workflow.ts` (`loadActions`, `loadAttachments`, `openWorkflow`, `afterActionMutation`, `afterAttachmentMutation`)
  - `frontend/src/entries/app.ts` now installs `window.__TS_CORRESPONDENCE_WORKFLOW__`
  - `static/js/correspondence.js` delegates action/attachment reload orchestration and workflow open flow to TS bridge first with legacy fallback retained
- Correspondence mutation orchestration extraction to TS:
  - `frontend/src/lib/correspondence_workflow.ts` now includes mutation wrappers (`saveCorrespondence`, `upsertAction`, `toggleActionClosed`, `deleteAction`, `uploadAttachment`, `deleteAttachment`, `downloadAttachment`)
  - `static/js/correspondence.js` now routes save/submit/toggle/delete/upload/download/deleteAttachment flows through workflow bridge only
  - legacy `parseFileName` and direct runtime `fetch` fallback for download removed from `static/js/correspondence.js`
  - `TS_CORRESPONDENCE_MUTATIONS` fallback removed from all correspondence mutation paths (workflow-only)
  - `loadActions` and `loadAtts` are now workflow-only (direct runtime fetch fallback removed)
- Correspondence bridge-first hardening (state/data render path):
  - `static/js/correspondence.js` now requires TS bridges for `loadCatalog`, `loadDashboard`, `loadList`, `renderPager`, `renderRows`, `clearActionEditor`, `fillActionOptions`, `renderActions`, and `renderAtts`
  - legacy fallback blocks for these state/data render helpers were removed to keep logic centralized in `frontend/src/lib/correspondence_*`
- Correspondence form/edit fallback cleanup:
  - `static/js/correspondence.js` now requires `TS_CORRESPONDENCE_FORM` for `corrSubmitAction` payload build, `corrEditAction` value normalization, `formDefaults`, `payloadForm`, and `corrOpenEdit`
  - legacy fallback branches for those form/edit paths were removed; remaining fallback in this module is limited to `bindEvents` bridge failure handling

## Remaining Topics (Post Inline-Cleanup)

1. TypeScript migration wave (code is still mostly legacy JS):
   - `static/js/app.js`
   - `static/js/transmittal_v2.js`
   - `static/js/views/edms.js`
   - `static/js/views/settings.js`
2. Browser-level UI smoke tests are now present (Playwright baseline). Remaining work is expanding coverage depth for CRUD-heavy flows.
3. Runtime bootstrap hardening:
   - keep PostgreSQL migration-only policy (`alembic upgrade head` in deploy path)
   - keep SQLite runtime sync limited to compatibility/dev path
4. Cutover operations sign-off:
   - rehearsal log capture
   - parity gate pass artifact attachment
   - explicit rollback drill evidence

## 2026-02-13 Strict Bridge Hardening

- PostgreSQL-only runtime path enforced; SQLite runtime compatibility path removed from backend/CI.
- Legacy fallback execution removed for targeted runtime files:
  - `static/js/app.js`
  - `static/js/transmittal_v2.js`
  - `static/js/correspondence.js`
- Release gate test added to prevent fallback marker regressions:
  - `tests/test_no_legacy_fallbacks.py`
- Legacy global bridge contracts retired:
  - removed `window.__TS_*` access from runtime JS modules
  - removed `window.ViewBoot` / `registerViewBoot` path and `frontend/src/lib/legacy.ts`
  - runtime bridge surface is now centralized at `window.AppRuntime`
