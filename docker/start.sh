#!/usr/bin/env sh
set -eu

APP_ENV_LOWER="$(printf '%s' "${APP_ENV:-development}" | tr '[:upper:]' '[:lower:]')"

if [ -z "${SECRET_KEY:-}" ]; then
  echo "[startup] ERROR: SECRET_KEY is not set."
  echo "[startup] Set SECRET_KEY in your .env before starting the stack."
  exit 1
fi

case "${APP_ENV_LOWER}" in
  production|prod|staging)
    if [ "${#SECRET_KEY}" -lt 32 ]; then
      echo "[startup] ERROR: SECRET_KEY must be at least 32 characters in ${APP_ENV_LOWER}."
      exit 1
    fi
    ;;
esac

if [ -z "${WEB_CONCURRENCY:-}" ]; then
  case "${APP_ENV_LOWER}" in
    production|prod|staging) WEB_CONCURRENCY=2 ;;
    *) WEB_CONCURRENCY=1 ;;
  esac
fi

bootstrap_migrations() {
  python - <<'PY'
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, inspect

database_url = os.getenv("DATABASE_URL", "").strip()
if not database_url:
    print("[startup] ERROR: DATABASE_URL is not set.", flush=True)
    sys.exit(1)

engine = create_engine(database_url, future=True)
with engine.connect() as conn:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables:
        print("[startup] Existing alembic_version detected; running upgrade head.", flush=True)
        sys.exit(10)

    user_tables = {name for name in tables if name != "alembic_version"}
    if not user_tables:
        print("[startup] Fresh database detected; applying baseline schema and stamping head.", flush=True)
        sys.exit(20)

    if "users" in user_tables:
        print("[startup] Legacy schema without alembic_version detected; stamping head.", flush=True)
        sys.exit(30)

    print("[startup] Partial schema without alembic_version detected; using upgrade head.", flush=True)
    sys.exit(10)
PY
}

echo "[startup] Running Alembic migrations..."
set +e
bootstrap_migrations
migration_mode=$?
set -e

case "$migration_mode" in
  10)
    alembic upgrade head
    ;;
  20)
    alembic upgrade 20260210_0001
    alembic stamp head
    ;;
  30)
    alembic stamp head
    ;;
  *)
    echo "[startup] ERROR: migration bootstrap probe failed with code ${migration_mode}."
    exit "$migration_mode"
    ;;
esac

if [ "${SYNC_ADMIN_ON_START:-false}" = "true" ]; then
  echo "[startup] Syncing admin account..."
  python create_admin.py || true
fi

echo "[startup] Starting API server with ${WEB_CONCURRENCY} worker(s)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY}"
