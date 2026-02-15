# MDR App

FastAPI + SQLAlchemy + Jinja application with incremental migration path to:

- PostgreSQL as primary database
- Alembic for schema versioning
- TypeScript + Vite frontend build pipeline

## Quick Start (Local)

1. Create and activate virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Copy env template and adjust values:

```powershell
copy .env.example .env
```

4. Create/update admin:

```powershell
python create_admin.py
```

5. Run app:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Database Migration Policy

- Runtime DB initialization is disabled.
- Staging/Production schema changes must be applied by Alembic:

```powershell
alembic upgrade head
```

- `DATABASE_URL` must point to PostgreSQL in runtime/deployment.
- SQLite is supported only as cutover source input for ETL/reconciliation tools.
- Runtime startup rejects SQLite `DATABASE_URL` values by policy.

## API Prefix Normalization

- Public API is served under `/api/v1/*`.
- `API_PREFIX` can be configured as `/api` or `/api/v1`; app startup normalizes both to the same public v1 paths.

## Docker (PostgreSQL local)

```powershell
docker compose up -d --build
```

The web service runs `alembic upgrade head` before starting Uvicorn.

## Ubuntu Server Production (Docker + Caddy, Recommended)

For direct Ubuntu Server deployment with Docker Engine and Caddy TLS proxy, use:

- `docker-compose.windows.prod.yml` (production hardening override; name is historical)
- `docker/Caddyfile`
- `.env.production.example`
- `docs/ubuntu_server_docker_caddy_runbook.md`
- `docs/storage_upgrade_runbook.md`

Current stable release anchor:

- Tag: `v3.2.0`
- Commit: `d106bddddc3b34bd1d46fc8ed7ad20d641c1ee5b`

Production deploy model:

- push version tag from desktop
- pull/checkout tag on server (`git fetch --tags`, `git checkout --detach vX.Y.Z`)
- deploy with Docker compose build

Start stack in production mode:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build
```

The override binds app/database ports to localhost and exposes only `80/443` via Caddy.
Frontend assets are built inside Docker (multi-stage Dockerfile), so deploy does not require committing `static/dist`.
Production override maps persistent data to `${MDR_DATA_ROOT:-/opt/mdr_data}` for DB/files/logs durability.
Default compose port bindings are localhost-only (`WEB_PORT_BIND` / `POSTGRES_PORT_BIND`) unless explicitly changed.

Important env contract for production:

- set both `DATABASE_URL` and `COMPOSE_DATABASE_URL` to the same PostgreSQL DSN

## Windows Server Production (Docker + Caddy)

For Windows Server deployment with WSL2, Docker Engine, and Caddy TLS proxy, use:

- `docker-compose.windows.prod.yml`
- `docker/Caddyfile`
- `.env.production.example`
- `docs/windows_server_docker_caddy_runbook.md`
- `docs/storage_upgrade_runbook.md`

## TypeScript Pipeline

Frontend source tree is under `frontend/src`.

```powershell
npm install
npm run gen:api
npm run typecheck
npm run build
```

Build output is generated under `static/dist` (local development workflow).
For production Docker deployments, frontend build is executed inside Docker image build.
Minimum recommended Node runtime is `20.x`.
`npm run gen:api` now prefers project `.venv` Python automatically (with fallback to `python`/`python3`).

## DB Baseline / Reconciliation Tools

```powershell
# 1) Baseline report from current DB
python tools/db_baseline_report.py --database-url sqlite:///./database/mdr_project.db

# 2) Schema drift report (model vs DB)
python tools/schema_drift_report.py --database-url sqlite:///./database/mdr_project.db

# 3) Dry-run ETL analysis
python tools/sqlite_to_postgres_etl.py --dry-run --postgres-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app

# 4) Execute ETL
python tools/sqlite_to_postgres_etl.py --execute --truncate-target --postgres-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app

# 5) Post-load parity report
python tools/data_parity_report.py --source-url sqlite:///./database/mdr_project.db --target-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app
```

## Staging Rehearsal / Cutover Runbook

```powershell
# 1) Apply schema on target
alembic upgrade head

# 2) Dry-run ETL
python tools/sqlite_to_postgres_etl.py --dry-run --postgres-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app

# 3) Execute ETL
python tools/sqlite_to_postgres_etl.py --execute --truncate-target --postgres-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app

# 4) Generate parity report
python tools/data_parity_report.py --source-url sqlite:///./database/mdr_project.db --target-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app --report reports/data_parity_report_cutover.json

# 5) Enforce mandatory parity gate (all tables)
python tools/parity_gate.py --report reports/data_parity_report_cutover.json --max-count-mismatches 0 --max-unique-issues 0 --max-fk-violations 0

# 6) Drift gate (target + source)
python tools/schema_drift_report.py --database-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app --out reports/schema_drift_report_post_cutover.json --fail-on-warning
python tools/schema_drift_report.py --database-url sqlite:///./database/mdr_project.db --out reports/schema_drift_report_source_post_cutover.json --fail-on-warning
```

Or run phases 1-5 with one command:

```powershell
python tools/cutover_readiness.py --e2e-system-chrome
```

## Test Lanes

- PostgreSQL primary lane:

```powershell
$env:TEST_PROFILE="postgres_main"
alembic upgrade head
python create_admin.py
pytest -q test_api.py tests/test_endpoint_fixes.py tests/test_regressions.py tests/test_services.py tests/test_schema_sanity.py tests/test_db_runtime_policy.py tests/test_ui_smoke.py tests/test_no_legacy_fallbacks.py
```

## Local E2E In Restricted Networks

If Playwright browser download is blocked, run with system Chrome:

```powershell
$env:PW_USE_SYSTEM_CHROME="1"
npm run e2e:critical
```

Optional custom executable path:

```powershell
$env:PW_CHROME_EXECUTABLE_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
npm run e2e:critical
```

## Rehearsal / Production Checklist

See `docs/cutover_runbook.md` for:
- staging rehearsal sequence and evidence checklist
- rollback drill documentation template
- production cutover order with read-only window

## Useful Scripts

- `tools/db_baseline_report.py`: snapshot of tables, columns, indexes, and row counts
- `tools/schema_drift_report.py`: compares model vs live DB schema
- `tools/sqlite_to_postgres_etl.py`: repeatable ETL from SQLite to PostgreSQL
- `tools/data_parity_report.py`: row-count / key parity checks between source & target
- `tools/export_openapi.py`: exports OpenAPI schema for TS type generation
