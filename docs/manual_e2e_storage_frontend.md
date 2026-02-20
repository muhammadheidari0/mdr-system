# Manual E2E - Storage and Integrations UX

## Scope
- `Settings > Storage`
  - Paths
  - Policy
  - Site Cache
- `Settings > Integrations`
  - Provider tabs: `OpenProject`, `Google`, `Nextcloud`
  - Mirror selector: `none | google_drive | nextcloud`
  - OpenProject sub-tabs: `Connection Settings`, `Project Import`, `Excel Import`, `Data & Logs`

## Preconditions
- Admin user is available.
- `/api/v1/health` is healthy.
- Browser cache cleared.

## 1) Storage page
1. Open `Settings`.
2. Open `Storage` tab.
3. Confirm stepper sections are visible: `Paths`, `Policy`, `Site Cache`.

Expected:
- No OpenProject/Google provider fields are shown in Storage page.

## 2) Paths save
1. Fill `MDR path` and `Correspondence path` with different valid paths.
2. Click `Save Paths`.

Expected:
- Save succeeds.
- Last saved time updates.

## 3) Integrations provider tabs
1. Open `Settings > Integrations`.
2. Verify provider tabs exist:
  - `OpenProject`
  - `Google`
  - `Nextcloud`
3. Verify mirror selector exists with values:
  - `None`
  - `Google Drive`
  - `Nextcloud`
3. Verify Local Cache controls are not present here.

## 4) OpenProject connection
1. In OpenProject provider, open `Connection Settings`.
2. Set:
  - enabled
  - base URL
  - default parent work package id
  - api key
3. (Optional) toggle `Ignore SSL errors (internal/test only)`.
4. Click `Save OpenProject Settings`.
5. Click `Test Connection`.

Expected:
- Save succeeds.
- Ping summary is shown in result box.
- If SSL is disabled, warning note is visible.

## 5) OpenProject project import (snapshot)
1. Open sub-tab `Project Import`.
2. Fill `Project ID / Identifier`.
3. Click `Preview Work Packages`.

Expected:
- Preview table shows live rows from OpenProject.

4. Click `Import Snapshot`.
5. Open `Data & Logs`.

Expected:
- New run exists with `OPP-` prefix.
- Row logs are visible for the run.

## 6) OpenProject excel import
1. Open sub-tab `Excel Import`.
2. Upload `openproject template.xlsx`.
3. Click `Validate (Dry-run)`.
4. Click `Start Processing`.

Expected:
- Run appears in `Data & Logs` with `OPI-` prefix.
- Progress and final status are visible.
- Summary includes pass counters:
  - `Pass1 created/failed`
  - `Pass2 relations created/failed`
- In `Row Logs`, selecting a row shows mapping/relation/custom-field summary.

## 7) Google integration
1. Switch to provider tab `Google`.
2. Fill OAuth fields:
  - `OAuth Client ID`
  - `OAuth Client Secret`
  - `OAuth Refresh Token`
3. Toggle services as needed:
  - Drive / Gmail / Calendar
4. Fill service-specific fields (`shared_drive_id`, `sender_email`, `calendar_id`).
5. Click `Save Google Settings`.
6. Click `Test Drive`, `Test Gmail`, `Test Calendar`.

Expected:
- Save succeeds.
- Ping result is shown for each service.

## 8) Regression check
- Navigate away and back to Integrations.
- Confirm saved non-secret fields are loaded.
- Confirm secret fields are not returned in plain text.

## 9) Nextcloud integration
1. Switch provider tab to `Nextcloud`.
2. Set:
  - enabled
  - base URL
  - username
  - app password
  - root path
3. (Optional) toggle `Ignore SSL errors (internal/test only)`.
4. Set mirror provider to `nextcloud`.
5. Click `Save Nextcloud Settings`.
6. Click `Test Nextcloud Connection`.
7. Click `Run Nextcloud Sync`.

Expected:
- Save succeeds.
- Ping summary is shown in result box with `tls_verify_effective` and `ssl_source`.
- Sync run action returns processed/success/failed counters.
