# Storage Upgrade Runbook (Hybrid + Data Safety)

## What changed
- Local filesystem remains the primary storage backend.
- Upload pipeline computes `sha256`, detects MIME by content/signature, and stores validation status.
- Async storage jobs exist for:
  - Google Drive mirror (`google_drive_mirror`)
  - Nextcloud mirror (`nextcloud_mirror`)
  - OpenProject sync (`openproject_sync`)
- Local cache manifest APIs are available for pin/unpin workflows.

## Required migration
Run:

```bash
alembic upgrade head
```

## Deployment update flow (v2)
Use the production update helper instead of manual git/compose steps:

```bash
cd /opt/mdr_app
./update.sh --latest
```

Key behavior in `update.sh v2`:
- pre-flight checks (docker permission, disk guard, env contract)
- auto-stash + force checkout
- mandatory DB backup before deploy
- smart Caddyfile render before compose up
- auto rollback on local health failure

## New/updated APIs
Settings:
- `GET /api/v1/settings/storage-policy`
- `POST /api/v1/settings/storage-policy`
- `GET /api/v1/settings/storage-integrations`
- `POST /api/v1/settings/storage-integrations`

Storage jobs:
- `POST /api/v1/storage/sync/google-drive/run`
- `POST /api/v1/storage/sync/nextcloud/run`
- `POST /api/v1/storage/sync/openproject/run`

OpenProject:
- `POST /api/v1/storage/openproject/ping`
- `GET /api/v1/storage/openproject/projects/{project_ref}/work-packages/preview`
- `POST /api/v1/storage/openproject/projects/{project_ref}/import`
- `GET /api/v1/storage/openproject/import/template`
- `POST /api/v1/storage/openproject/import/validate`
- `POST /api/v1/storage/openproject/import/runs/{run_id}/execute`
- `GET /api/v1/storage/openproject/import/runs`
- `GET /api/v1/storage/openproject/import/runs/{run_id}`
- `GET /api/v1/storage/openproject/import/runs/{run_id}/rows`
- `GET /api/v1/storage/openproject/activity`

Google:
- `POST /api/v1/storage/google/ping`

Nextcloud:
- `POST /api/v1/storage/nextcloud/ping`
- `POST /api/v1/storage/nextcloud/folders`

Local cache:
- `POST /api/v1/storage/local-cache/pin`
- `POST /api/v1/storage/local-cache/unpin`
- `GET /api/v1/storage/local-cache/manifest`

Integrity:
- `GET /api/v1/archive/files/{id}/integrity`

## Settings UI split
- `Settings > Storage`
  - Paths
  - Policy
  - Site Cache
- `Settings > Integrations`
  - Provider tab `OpenProject`
  - Provider tab `Google`
  - Provider tab `Nextcloud`
  - Mirror provider selector (`none|google_drive|nextcloud`)
  - Local Cache is not configured in Integrations anymore.

## OpenProject UX
- Sub-tabs:
  - `Connection Settings`
  - `Project Import`
  - `Excel Import`
  - `Data & Logs`
- Project import supports project `ID` or `identifier`.
- Snapshot import is persisted in existing import tables:
  - project snapshot run prefix: `OPP-`
  - excel import run prefix: `OPI-`
- Excel import execution is two-pass:
  - Pass-1: create WBS hierarchy
  - Pass-2: create predecessor relations
- Parser supports dual template headers (legacy + new aliases).
- `Predecessors` support in this phase: `FS` with optional lag only.

## Env vars
- `GDRIVE_SERVICE_ACCOUNT_JSON`
- `GDRIVE_SHARED_DRIVE_ID`
- `OPENPROJECT_BASE_URL`
- `OPENPROJECT_API_TOKEN`
- `OPENPROJECT_TLS_VERIFY` (secure default: `true`)
- `OPENPROJECT_TLS_VERIFY_FORCE` (optional override: `true|false|1|0|yes|no|on|off`)
- `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- legacy alias: `OPENPROJECT_DEFAULT_PROJECT_ID`
- `NEXTCLOUD_BASE_URL`
- `NEXTCLOUD_USERNAME`
- `NEXTCLOUD_APP_PASSWORD`
- `NEXTCLOUD_ROOT_PATH`
- `NEXTCLOUD_LOCAL_MOUNT_ROOT`
- `NEXTCLOUD_TLS_VERIFY` (secure default: `true`)
- `NEXTCLOUD_TLS_VERIFY_FORCE` (optional override: `true|false|1|0|yes|no|on|off`)
- `STORAGE_ALLOWED_ROOTS` (CSV absolute roots, e.g. `/app/archive_storage,/app/data_store`)
- `STORAGE_REQUIRE_ABSOLUTE_PATHS=true` (recommended for staging/prod)
- `STORAGE_VALIDATE_WRITABLE_ON_SAVE=true` (recommended for staging/prod)

TLS precedence:
1. `OPENPROJECT_TLS_VERIFY_FORCE` (if set)
2. UI `skip_ssl_verify`
3. `OPENPROJECT_TLS_VERIFY`

Nextcloud TLS precedence:
1. `NEXTCLOUD_TLS_VERIFY_FORCE` (if set)
2. UI `nextcloud.skip_ssl_verify`
3. `NEXTCLOUD_TLS_VERIFY`

## Production path hardening
- Mount network storage on host OS first (CIFS/NFS).
- Bind-mount into container with stable absolute paths.
- Ensure ownership aligns with `APP_UID:APP_GID`.
- Save storage paths only under `STORAGE_ALLOWED_ROOTS`.
- Save is rejected (`422`) if path is relative, outside allowed roots, or not writable.
- `Storage Paths` remains Local/UNC only; Nextcloud folder picker maps remote folders to Local/UNC by `local_mount_root`.

## Optional legacy backfill
Dry-run:

```bash
python tools/backfill_file_integrity.py
```

Execute:

```bash
python tools/backfill_file_integrity.py --execute
```
