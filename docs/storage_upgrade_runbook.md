# Storage Upgrade Runbook (Hybrid + Data Safety)

## What Changed
- Local filesystem remains the primary storage backend.
- Upload pipeline now computes `sha256`, detects MIME by content/signature, and stores validation status.
- Async storage job system added for:
  - Google Drive mirror (`google_drive_mirror`)
  - OpenProject sync (`openproject_sync`)
- Local cache manifest APIs added for pin/unpin workflows.
- Upload APIs support optional `openproject_work_package_id` to chain mirror -> OpenProject sync.

## New/Updated APIs
- `GET /api/v1/settings/storage-policy`
- `POST /api/v1/settings/storage-policy`
- `GET /api/v1/settings/storage-integrations`
- `POST /api/v1/settings/storage-integrations`
- `POST /api/v1/storage/sync/google-drive/run`
- `POST /api/v1/storage/sync/openproject/run`
- `POST /api/v1/storage/local-cache/pin`
- `POST /api/v1/storage/local-cache/unpin`
- `GET /api/v1/storage/local-cache/manifest`
- `GET /api/v1/archive/files/{id}/integrity`

## Worker
- New worker entrypoint: `python -m app.workers.storage_worker`
- Docker service: `worker` in `docker-compose.yml`.

## Desktop Local Sync Agent
- Script: `tools/mdr_sync_agent.py`
- Example:

```bash
python tools/mdr_sync_agent.py \
  --base-url https://your-domain.com \
  --token <JWT_TOKEN> \
  --out-dir ~/MDRSyncCache
```

- Behavior:
  - Pull pinned manifest from API.
  - Download only missing/changed files.
  - Verify downloaded file hash (`sha256`).

## Required Migration
Run:

```bash
alembic upgrade head
```

## Optional Backfill (Legacy Files)

Dry run:

```bash
python tools/backfill_file_integrity.py
```

Execute:

```bash
python tools/backfill_file_integrity.py --execute
```

## New Env Vars
- `GDRIVE_SERVICE_ACCOUNT_JSON`
- `GDRIVE_SHARED_DRIVE_ID`
- `OPENPROJECT_BASE_URL`
- `OPENPROJECT_API_TOKEN`
- `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- legacy alias: `OPENPROJECT_DEFAULT_PROJECT_ID` (optional, backward compatible)
- `STORAGE_ALLOWED_ROOTS` (CSV of absolute roots, example: `/app/archive_storage,/app/data_store`)
- `STORAGE_REQUIRE_ABSOLUTE_PATHS` (`true` recommended for staging/production)
- `STORAGE_VALIDATE_WRITABLE_ON_SAVE` (`true` recommended for staging/production)

## Storage Path Hardening (Production Gate)

- Mount network storage on host OS first (CIFS/NFS).
- Bind mount into container with stable absolute paths.
- Ensure mount ownership aligns with `APP_UID:APP_GID`.
- Save storage paths only as absolute paths under `STORAGE_ALLOWED_ROOTS`.
- Save is rejected (`422`) if path is relative, خارج از root مجاز, or not writable by service account.
