# گزارش DevOps قبل از Publish

این سند برای DevOps/Infra نوشته شده تا قبل از deploy یا publish، تصویر دقیقی از ساختار سیستم، وابستگی ها، runtime topology، مسیر build/deploy و gateهای الزامی پروژه داشته باشد.

## 1. خلاصه اجرایی

این پروژه یک سامانه وب مبتنی بر:

- Backend: FastAPI + SQLAlchemy + Alembic
- Frontend: TypeScript + Vite
- Database: PostgreSQL
- Reverse Proxy / TLS: Caddy
- Background Processing: Python worker
- Deploy Model: Docker Compose
- Release Model: هم آنلاین از repo و هم offline package

اپلیکیشن در production باید روی PostgreSQL اجرا شود. SQLite فقط به عنوان source برای ETL/cutover tooling نگه داشته شده و runtime production روی SQLite طراحی نشده است.

## 2. معماری اجرایی

مسیر اصلی runtime:

1. کاربر از طریق browser به `Caddy` وصل می شود.
2. `Caddy` درخواست را به سرویس `web` روی FastAPI پاس می دهد.
3. سرویس `web` به `PostgreSQL` متصل می شود.
4. سرویس `worker` به صورت background jobهای storage/integration را اجرا می کند.

توپولوژی containerها:

- `postgres`
- `web`
- `worker`
- `caddy`

پورت ها:

- Public:
  - `80/tcp`
  - `443/tcp`
- Local-only:
  - `127.0.0.1:8000` برای web
  - `127.0.0.1:5432` برای postgres

health endpoint اصلی:

- `GET /api/v1/health`

## 3. فناوری ها و سیستم های استفاده شده

### Backend

- `fastapi`
- `uvicorn[standard]`
- `sqlalchemy`
- `pydantic`
- `pydantic-settings`
- `alembic`
- `psycopg`
- `jinja2`
- `python-jose`
- `bcrypt`
- `python-multipart`

### Frontend

- `vite`
- `typescript`
- `date-fns`
- `date-fns-jalali`

### گزارش/فایل/اکسل

- `reportlab`
- `openpyxl`
- `pandas`
- `python-magic`
- `file` و `libmagic1` در runtime image

### Integrationها

- Google Drive
- OpenProject
- Nextcloud
- Native EDMS sync endpoint/shared secret

### Infra / Deploy

- Docker Engine
- Docker Compose
- Caddy
- GitHub Actions CI

## 4. ساختار مهم پروژه

مسیرهای مهم:

- `app/`
  - backend application
- `app/api/v1/routers/`
  - API routers
- `app/services/`
  - integration/service logic
- `app/workers/`
  - background worker entrypoints
- `alembic/`
  - database migrations
- `docker/`
  - runtime start scripts
- `frontend/`
  - TypeScript/Vite source
- `templates/`
  - server-rendered HTML templates
- `static/`
  - built frontend assets and static files
- `tools/`
  - operational scripts, ETL, parity, cutover, bootstrap
- `docs/`
  - runbookها و operational documentation
- `.github/workflows/ci.yml`
  - CI pipeline

## 5. نحوه build

### Frontend build

در Dockerfile ابتدا stage فرانت اجرا می شود:

- base image: `node:20-alpine`
- `npm ci`
- `npm run build`

خروجی در:

- `static/dist`

### Backend image

stage دوم:

- base image: `python:3.10-slim`
- نصب packageهای Python از `requirements.txt`
- نصب packageهای apt:
  - `gcc`
  - `libpq-dev`
  - `libmagic1`
  - `file`

سپس frontend build output داخل image نهایی کپی می شود.

runtime user:

- `mdr`

entrypoint اصلی image:

- `/app/docker/start.sh`

## 6. رفتار startup سرویس ها

### web

فایل:

- `docker/start.sh`

رفتار:

- اعتبار `SECRET_KEY` را چک می کند.
- migration bootstrap را اجرا می کند.
- اگر DB خالی باشد:
  - baseline migration و سپس stamp
- اگر schema legacy بدون `alembic_version` باشد:
  - `alembic stamp head`
- در حالت عادی:
  - `alembic upgrade head`
- در صورت فعال بودن:
  - `SYNC_ADMIN_ON_START=true`
  - اجرای `create_admin.py`
- سپس Uvicorn را با `WEB_CONCURRENCY` بالا می آورد.

### worker

فایل:

- `docker/start_worker.sh`

رفتار:

- صبر می کند DB و schema آماده شوند.
- وجود جدول `settings_kv` را بررسی می کند.
- سپس:
  - `python -m app.workers.storage_worker`

### caddy

وظیفه:

- reverse proxy
- termination TLS
- public ingress

حالت های TLS:

- `http`
- `internal`
- `custom`
- `public`

## 7. فایل های compose و تفاوت آنها

### `docker-compose.yml`

compose اصلی توسعه/استقرار استاندارد.

### `docker-compose.offline.yml`

برای offline deployment package استفاده می شود و bind mountهای production-style دارد:

- `${MDR_DATA_ROOT}/postgres`
- `${MDR_DATA_ROOT}/database`
- `${MDR_DATA_ROOT}/data_store`
- `${MDR_DATA_ROOT}/archive_storage`
- `${MDR_DATA_ROOT}/logs`

### `docker-compose.windows.prod.yml`

overlay مربوط به سناریوهای Windows/server deployment.

## 8. تنظیمات محیطی مهم

فایل مبنا:

- `.env.production.example`

کلیدهای حیاتی:

- `APP_ENV=production`
- `DEBUG=false`
- `API_PREFIX=/api/v1`
- `MDR_DOMAIN`
- `MDR_DATA_ROOT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `COMPOSE_DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `ADMIN_FULL_NAME`
- `APP_UID`
- `APP_GID`
- `WEB_CONCURRENCY`
- `POSTGRES_PORT_BIND`
- `WEB_PORT_BIND`
- `CADDY_HTTP_PORT_BIND`
- `CADDY_HTTPS_PORT_BIND`

feature/storage controls:

- `READ_ONLY_MODE`
- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_MAX_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`
- `STORAGE_ALLOWED_ROOTS`
- `STORAGE_REQUIRE_ABSOLUTE_PATHS`
- `STORAGE_VALIDATE_WRITABLE_ON_SAVE`

integration envها:

- `GDRIVE_SERVICE_ACCOUNT_JSON`
- `GDRIVE_SHARED_DRIVE_ID`
- `OPENPROJECT_BASE_URL`
- `OPENPROJECT_API_TOKEN`
- `OPENPROJECT_CONNECT_TIMEOUT_SECONDS`
- `OPENPROJECT_READ_TIMEOUT_SECONDS`
- `OPENPROJECT_TLS_VERIFY`
- `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- `NEXTCLOUD_BASE_URL`
- `NEXTCLOUD_USERNAME`
- `NEXTCLOUD_APP_PASSWORD`
- `NEXTCLOUD_ROOT_PATH`
- `NEXTCLOUD_LOCAL_MOUNT_ROOT`
- `NATIVE_EDMS_SYNC_SHARED_SECRET`
- `NATIVE_EDMS_SYNC_TARGET_URL`

نکته مهم:

- `DATABASE_URL` و `COMPOSE_DATABASE_URL` باید یکسان باشند.
- اگر پسورد PostgreSQL شامل کاراکترهای خاص مثل `@` یا `#` باشد، در URL باید URL-encoded شود.

## 9. persistence و storage

مسیرهای داده host-side در production/offline:

- `/opt/mdr_data/postgres`
- `/opt/mdr_data/database`
- `/opt/mdr_data/data_store`
- `/opt/mdr_data/archive_storage`
- `/opt/mdr_data/logs`
- `/opt/mdr_data/backups`

قاعده مهم برای storage pathها:

- فقط absolute path
- باید داخل `STORAGE_ALLOWED_ROOTS` باشند
- writable بودن path موقع save بررسی می شود

قاعده عملیاتی:

- برای SMB/NFS/CIFS mount، mount باید روی host انجام شود.
- مسیرهای `smb://` یا remote URI مستقیم داخل app ذخیره نشوند.

## 10. health checks و readiness

### Compose-level

- `postgres`: `pg_isready`
- `web`: درخواست به `http://127.0.0.1:8000/api/v1/health`
- `worker`: dependency روی healthy بودن `postgres` و `web`

### Application-level

- `GET /api/v1/health` باید `{"ok": true, "status": "healthy"}` برگرداند.

### Offline installer

bootstrap script بعد از deploy:

- local health check
- public health check

را اجرا می کند.

## 11. CI/CD و quality gates

فایل:

- `.github/workflows/ci.yml`

laneهای CI:

### backend-postgres

- PostgreSQL service
- `alembic upgrade head`
- schema drift gate
- SQLite -> PostgreSQL ETL
- admin seed
- pytest suite
- parity report
- parity gate

### frontend

- install node deps
- generate OpenAPI + TS types
- typecheck
- frontend build

### e2e-browser

- Playwright critical e2e
- PostgreSQL service
- migrations
- ETL
- admin seed

publish بدون pass شدن این laneها نباید انجام شود.

## 12. ابزارهای operational مهم

در `tools/` چند دسته ابزار مهم وجود دارد:

### deploy/bootstrap

- `tools/bootstrap_ubuntu2404.sh`
- `tools/bootstrap_offline.sh`
- `tools/build_offline_installer.sh`
- `tools/render_caddyfile.sh`

### DB migration / cutover / readiness

- `tools/sqlite_to_postgres_etl.py`
- `tools/data_parity_report.py`
- `tools/parity_gate.py`
- `tools/schema_drift_report.py`
- `tools/cutover_readiness.py`
- `tools/production_cutover.py`
- `tools/db_baseline_report.py`

### sync / repair / operational utilities

- `tools/mdr_sync_agent.py`
- `tools/backfill_file_integrity.py`
- `tools/repair_mdr_documents_from_doc_number.py`
- `tools/push_edms_sync_events.py`

## 13. مسیرهای deploy پشتیبانی شده

### A. Deploy از repo روی Ubuntu

مرجع:

- `docs/ubuntu_server_docker_caddy_runbook.md`

مدل:

- clone/fetch tag
- ساخت `.env`
- render Caddyfile
- `docker compose up -d --build`

### B. Offline package deploy

مرجع:

- `docs/offline_ubuntu_install_runbook.md`

مدل:

- build package روی ماشین connected
- انتقال `tar.gz` به سرور target
- extract
- اجرای `install.sh`
- load image tarها
- deploy و health check

## 14. مواردی که DevOps باید قبل از publish چک کند

### 14.1 کد و artifact

- branch/tag release مشخص باشد.
- worktree dirty نباشد.
- artifactها داخل git commit نشده باشند.
- frontend build تازه باشد و `static/dist` با source همخوانی داشته باشد.
- cache-busting templateها در صورت تغییر frontend کنترل شود.

### 14.2 config و secrets

- `.env` از `.env.production.example` ساخته شده باشد.
- secretهای placeholder حذف شده باشند.
- `SECRET_KEY` واقعی و بلند باشد.
- `ADMIN_PASSWORD` و `POSTGRES_PASSWORD` قوی باشند.
- DSNها URL-safe باشند.
- `MDR_DOMAIN` با mode استقرار سازگار باشد.

### 14.3 دیتابیس

- migrationها روی DB target تست شده باشند.
- اگر cutover از SQLite داریم:
  - ETL اجرا شده باشد.
  - parity report صفر mismatch داشته باشد.
  - schema drift report fail نشده باشد.
- backup یا snapshot قبل از cutover موجود باشد.

### 14.4 runtime و infra

- Docker Engine و Compose plugin نصب و سالم باشند.
- دسترسی پورت 80/443 درست باشد.
- 8000 و 5432 public نباشند.
- mount pathهای storage writable باشند.
- UID/GID روی مسیرهای bind شده درست باشد.
- Caddyfile نهایی با mode انتخابی همخوانی داشته باشد.

### 14.5 integrationها

- اگر Google Drive فعال است:
  - service account معتبر باشد.
  - shared drive ID تنظیم شده باشد.
- اگر OpenProject فعال است:
  - base URL و token معتبر باشد.
  - TLS verification policy معلوم باشد.
- اگر Nextcloud فعال است:
  - mount/local root با path policy سازگار باشد.

### 14.6 آزمون ها

قبل از publish حداقل این gateها باید پاس شوند:

- backend PostgreSQL tests
- frontend typecheck/build
- Playwright critical e2e
- health endpoint
- smoke login/admin flow
- storage write/read smoke

## 15. ریسک ها و نکات مهم عملیاتی

### 15.1 SQLite runtime policy

SQLite در runtime production policy اصلی نیست. اگر کسی بخواهد production را روی SQLite بالا بیاورد، این با جهت معماری فعلی سازگار نیست.

### 15.2 Migration bootstrap

startup script برای چند سناریوی DB logic دارد. DevOps باید بداند که:

- DB کاملا خالی
- DB legacy بدون `alembic_version`
- DB با migration normal

سه رفتار متفاوت دارند. این موضوع روی restore/redeploy مهم است.

### 15.3 Asset cache

وقتی frontend تغییر می کند ولی query/version asset در templateها ثابت بماند، client ممکن است JS قدیمی بگیرد و deploy ظاهرا خراب شود.

### 15.4 Password در DSN

کاراکتر `%`، `@`، `#` و موارد مشابه می توانند هم در URL parsing و هم در Alembic/config interpolation مشکل ایجاد کنند. DSN باید با همین فرض بررسی شود.

### 15.5 Offline release quality

برای offline release فقط build موفق کافی نیست. این موارد باید روی package validate شوند:

- `install.sh`
- `checksums.txt`
- `release_manifest.env`
- image tar archives
- line ending صحیح در scriptها
- generated `.env` logic
- migration bootstrap در container startup

## 16. چک لیست پیشنهادی publish gate

پیشنهاد عملی قبل از sign-off:

1. `git status` تمیز باشد.
2. CI روی commit/tag release سبز باشد.
3. `npm run build` و `npm run typecheck` پاس باشد.
4. `alembic upgrade head` روی PostgreSQL staging پاس باشد.
5. `pytest` و `npm run e2e:critical` پاس باشند.
6. اگر cutover داریم:
   - ETL
   - parity report
   - parity gate
   - schema drift gate
7. `.env` production review شود.
8. secretها placeholder نباشند.
9. health endpoint داخلی و public پاس باشد.
10. rollback plan و snapshot ID ثبت شده باشد.

## 17. دستورات سریع برای DevOps

### health

```bash
curl -f http://127.0.0.1:8000/api/v1/health
curl -f http://<domain-or-ip>/api/v1/health
```

### compose status

```bash
docker compose -f docker-compose.offline.yml ps
docker compose -f docker-compose.offline.yml logs --tail=200 web
docker compose -f docker-compose.offline.yml logs --tail=200 worker
docker compose -f docker-compose.offline.yml logs --tail=200 caddy
docker compose -f docker-compose.offline.yml logs --tail=200 postgres
```

### migrations

```bash
alembic upgrade head
```

### ETL/parity

```bash
python tools/sqlite_to_postgres_etl.py --execute --truncate-target --postgres-url "$DATABASE_URL"
python tools/data_parity_report.py --source-url sqlite:///./database/mdr_project.db --target-url "$DATABASE_URL" --report reports/data_parity_report.json
python tools/parity_gate.py --report reports/data_parity_report.json --max-count-mismatches 0 --max-unique-issues 0 --max-fk-violations 0
python tools/schema_drift_report.py --database-url "$DATABASE_URL" --out reports/schema_drift_report.json --fail-on-warning
```

## 18. جمع بندی برای DevOps

اگر DevOps فقط سه چیز را بداند، این سه مورد مهم ترین هستند:

1. این سیستم production-first روی PostgreSQL + Docker Compose + Caddy طراحی شده است.
2. publish بدون migration/parity/health gates ریسک بالا دارد.
3. storage pathها، secrets، DSN encoding و asset cache-busting جزو failure pointهای واقعی این پروژه هستند.

برای runbookهای جزئی تر از این سند به این فایل ها رجوع شود:

- `docs/ubuntu_server_docker_caddy_runbook.md`
- `docs/offline_ubuntu_install_runbook.md`
- `docs/cutover_runbook.md`
- `docs/env_staging_production_required_checklist.md`
