# OpenProject External Integration (API Key)

## Terminology
- Use `OpenProject API Key (Access Token)` in UI/docs.
- Do not use `Provider token` for OpenProject API auth.

## Base URL and auth
- Base URL example: `https://open-project.htico.ir`
- API base is always `<base_url>/api/v3`
- Normalized automatically from:
  - `https://host`
  - `https://host/`
  - `https://host/openproject`
  - `https://host/openproject/api/v3`
- Auth mode: Basic Auth
  - username: `apikey`
  - password: `<OpenProject API Key>`

## Runtime config
- `OPENPROJECT_BASE_URL`
- `OPENPROJECT_API_TOKEN`
- `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- Legacy alias (read-compatible): `OPENPROJECT_DEFAULT_PROJECT_ID`
- TLS controls:
  - `OPENPROJECT_TLS_VERIFY` (secure default)
  - `OPENPROJECT_TLS_VERIFY_FORCE` (optional override)

TLS precedence:
1. `OPENPROJECT_TLS_VERIFY_FORCE` (if set)
2. UI `skip_ssl_verify`
3. `OPENPROJECT_TLS_VERIFY`

## Settings UI
Path: `Settings > Integrations > OpenProject`

Provider tabs in Integrations:
- `OpenProject`
- `Google`

OpenProject sub-tabs:
- `Connection Settings`
- `Project Import`
- `Excel Import`
- `Data & Logs`

### Connection Settings
- `OpenProject Enabled`
- `Base URL`
- `OpenProject API Key (Access Token)`
- `Default Parent Work Package ID`
- `Ignore SSL errors (internal/test only)` toggle
- Actions: `Save`, `Test Connection`, `Clear Token`, `Run Sync`

### Project Import (Snapshot)
- Input: `Project ID / Identifier`
- Actions:
  - `Preview Work Packages` (live list from OpenProject)
  - `Import Snapshot` (persist to import runs/rows tables)
- Snapshot run prefix: `OPP-`
- Snapshot `summary.run_type`: `project_snapshot`

### Excel Import (MVP)
- Input file: `openproject template.xlsx`
- Uses only sheet `Task_Table1`
- Optional runtime input: `Root Parent Work Package ID`
  - If provided in Excel Import form, it overrides default parent for that run.
  - If empty, runtime falls back to `Default Parent Work Package ID` from Connection Settings.
- Template source in repository: `data_sources/templates/openproject template.xlsx`
- Canonical `Task_Table1` header order:
  - `WBS, Subject, Duration, Start_Date, Finish_Date, Predecessors, %complete, Type`
- Flow:
  1. `Validate (Dry-run)` with parser + row persistence
  2. `Start Processing`:
     - Pass-1: create WBS hierarchy (parent resolution by WBS)
     - Pass-2: create predecessor relations
- Run prefix: `OPI-`
- `summary.run_type`: `excel_import`

Excel parser compatibility:
- Legacy template columns: `Name, Duration, Start_Date, Finish_Date, Predecessors, Resource_Names`
- New template aliases: `WBS, Subject, Duration, Start_Date, Finish_Date, Predecessors, %complete, Type`
- Optional extra columns (supported): `Resource_Names`, `Priority`
- If `WBS` column is missing (legacy), sequential WBS is auto-generated.
- `WBS` remains optional in template; hierarchy is still enforced when valid WBS values exist.
- `Predecessors` supports only `FS` with optional lag (`12`, `12FS+2`, `12FS-1`).

Execution details:
- Parent resolution precedence for `execute`:
  1. Request payload: `target_parent_work_package_id`
  2. Settings runtime: `default_work_package_id`
- If a row's `parent_wbs` cannot be resolved from already-created rows, that row falls back to root parent instead of failing.
- Type/Priority are resolved via OpenProject catalogs (`types`, `priorities`).
- Type fallback on mismatch: parent type.
- Priority fallback on mismatch: omitted with warning.
- `doneRatio` is sent first, with one fallback retry to `percentageDone` for field-compatibility.

## API endpoints (Admin)
Connection/sync:
- `POST /api/v1/storage/openproject/ping`
- `POST /api/v1/storage/sync/openproject/run`

Project snapshot:
- `GET /api/v1/storage/openproject/projects/{project_ref}/work-packages/preview`
- `POST /api/v1/storage/openproject/projects/{project_ref}/import`

Excel import:
- `GET /api/v1/storage/openproject/import/template`
- `POST /api/v1/storage/openproject/import/validate`
- `POST /api/v1/storage/openproject/import/runs/{run_id}/execute`
- `GET /api/v1/storage/openproject/import/runs`
- `GET /api/v1/storage/openproject/import/runs/{run_id}`
- `GET /api/v1/storage/openproject/import/runs/{run_id}/rows`
- `GET /api/v1/storage/openproject/activity`

## Security notes
- Use a dedicated integration user in OpenProject.
- Keep API key outside logs and audit payloads (redacted by design).
