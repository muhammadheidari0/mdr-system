# Staging/Production .env Required Checklist

Use this checklist before running `docker compose up -d --build` on staging or production.

## Required Keys

- [ ] `APP_ENV=staging` or `APP_ENV=production`
- [ ] `DEBUG=false`
- [ ] `API_PREFIX=/api/v1`
- [ ] `MDR_DOMAIN=<public-domain>`
- [ ] `MDR_DATA_ROOT=<server-data-root>` (example: `/opt/mdr_data`)
- [ ] `STORAGE_ALLOWED_ROOTS=<absolute-roots-csv>` (example: `/app/archive_storage,/app/data_store`)
- [ ] `STORAGE_REQUIRE_ABSOLUTE_PATHS=true`
- [ ] `STORAGE_VALIDATE_WRITABLE_ON_SAVE=true`
- [ ] `POSTGRES_PORT_BIND=127.0.0.1:5432:5432`
- [ ] `WEB_PORT_BIND=127.0.0.1:8000:8000`
- [ ] `POSTGRES_DB=<db-name>`
- [ ] `POSTGRES_USER=<db-user>`
- [ ] `POSTGRES_PASSWORD=<strong-password>`
- [ ] `DATABASE_URL=postgresql+psycopg://<user>:<password>@postgres:5432/<db-name>`
- [ ] `COMPOSE_DATABASE_URL` exactly equal to `DATABASE_URL`
- [ ] `SECRET_KEY=<long-random-secret>` (minimum 32 chars)
- [ ] `ADMIN_EMAIL=<admin-email>`
- [ ] `ADMIN_PASSWORD=<strong-admin-password>`
- [ ] `ADMIN_FULL_NAME=<admin-full-name>`
- [ ] `APP_UID=1000`
- [ ] `APP_GID=1000`
- [ ] `WEB_CONCURRENCY=2` (or higher based on host capacity)

## Optional Integrations (set only if used)

- [ ] `GDRIVE_SERVICE_ACCOUNT_JSON`
- [ ] `GDRIVE_SHARED_DRIVE_ID`
- [ ] `OPENPROJECT_BASE_URL`
- [ ] `OPENPROJECT_API_TOKEN`
- [ ] `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- [ ] (optional legacy) `OPENPROJECT_DEFAULT_PROJECT_ID`

## Storage Mount Gate

- [ ] Network storage is mounted on host OS (CIFS/NFS) before container start.
- [ ] Mount is bound into container as a stable absolute path (for example `/app/archive_storage`).
- [ ] Mount ownership/permissions are aligned with `APP_UID:APP_GID`.
- [ ] Storage paths saved in UI are absolute and under `STORAGE_ALLOWED_ROOTS`.

## Quick Validation

1. `docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml config`
2. `docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build`
