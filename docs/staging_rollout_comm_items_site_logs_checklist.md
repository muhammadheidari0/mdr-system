# Staging Rollout Checklist (Feature Flag: `FEATURE_COMM_ITEMS_V1`)

## 1) Pre-Deploy
- Confirm branch is up to date and CI is green.
- Confirm database backup/snapshot is taken.
- Confirm staging `.env` contains:
  - `FEATURE_COMM_ITEMS_V1=true`
  - valid `DATABASE_URL`
- Confirm admin credentials for smoke/E2E are valid (`TEST_ADMIN_EMAIL`, `TEST_ADMIN_PASSWORD`).

## 2) Migration Readiness
- Check migration chain:
  - `alembic history`
  - `alembic heads`
  - `alembic branches`
- Expected:
  - single head: `20260220_0011`
  - no branches
- Apply migration:
  - `alembic upgrade head`
- Verify current revision:
  - `alembic current` should be `20260220_0011`

## 3) App Deploy
- Deploy backend and frontend artifacts.
- Regenerate/ship OpenAPI artifacts used by frontend:
  - `frontend/openapi.json`
  - `frontend/src/types/api.generated.ts`
- Build frontend bundle:
  - `npm run build`

## 4) Feature-Flag Validation (Staging)
- Open contractor hub (`execution`):
  - Two actions visible: `ثبت مکاتبات` and `گزارش کارگاه`
  - Site Log drawer opens from left with wide layout.
- Open consultant hub (`inspection`):
  - `صف تایید گزارش کارگاه` visible
  - submitted logs visible for verify.
- Confirm forms are Persian (labels/messages/date display).

## 5) Workflow Validation (API)
- Contractor create draft site log: `200`
- Submit without rows: `400`
- Consultant verify without verified values: `400`
- Valid verify: `200`
- Contractor write to `verified_*`: `403`
- Update after verify (non-admin): `409`

## 6) Reporting Validation
- `GET /api/v1/site-logs/reports/volume`
- `GET /api/v1/site-logs/reports/variance`
- `GET /api/v1/site-logs/reports/progress`
- Confirm claimed vs verified deltas are returned correctly.

## 7) Regression Validation
- Comm-items RFI/NCR/TECH flows still functional.
- TECH report subtypes are not available in catalog.
- Existing comm-items reports (aging/cycle/impact) still work.

## 8) Rollback Plan
- If functional issue (without schema rollback):
  - set `FEATURE_COMM_ITEMS_V1=false`
  - redeploy app and clear cache.
- If migration rollback is required:
  - execute only with DB owner approval and backup confirmation.
  - `alembic downgrade 20260219_0009` (reverts site_logs tables).
