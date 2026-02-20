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
- Flow:
  1. `Validate (Dry-run)`
  2. `Start Processing`
- Run prefix: `OPI-`
- `summary.run_type`: `excel_import`

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
