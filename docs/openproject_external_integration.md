# OpenProject External Integration (API Key)

## Terminology
- Correct term in this project: `OpenProject API Key (Access Token)`.
- Do not use `Provider token` for OpenProject API authentication.

## Base URLs
- Base URL example: `https://open-project.htico.ir`
- API base is always: `<base_url>/api/v3`
- The app normalizes these inputs automatically:
  - `https://host`
  - `https://host/`
  - `https://host/openproject`
  - `https://host/openproject/api/v3`

## Authentication
- Auth mode: Basic Auth (official OpenProject API v3 style)
  - username: `apikey`
  - password: `<OpenProject API Key>`

## Required env/settings
- `OPENPROJECT_BASE_URL`
- `OPENPROJECT_API_TOKEN`
- `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- optional legacy alias: `OPENPROJECT_DEFAULT_PROJECT_ID`

## Security recommendations
- Create a dedicated integration user in OpenProject.
- Generate API key for that integration user only.
- Do not reuse personal user API keys for production integrations.

## UI (Settings > Integrations)
- OpenProject area is tabbed:
  - `Connection Settings`
  - `Excel Import`
  - `Data & Logs`
- Excel import in MVP:
  - Uses only `Task_Table1` sheet from `openproject template.xlsx`
  - Two-step flow: `Validate (Dry-run)` then `Start Processing`
  - Creates flat work packages under `default_work_package_id`
  - `Predecessors` and resource assignment are logged but not executed in MVP

## Import API endpoints (Admin only)
- `GET /api/v1/storage/openproject/import/template`
- `POST /api/v1/storage/openproject/import/validate`
- `POST /api/v1/storage/openproject/import/runs/{run_id}/execute`
- `GET /api/v1/storage/openproject/import/runs`
- `GET /api/v1/storage/openproject/import/runs/{run_id}`
- `GET /api/v1/storage/openproject/import/runs/{run_id}/rows`
- `GET /api/v1/storage/openproject/activity`
