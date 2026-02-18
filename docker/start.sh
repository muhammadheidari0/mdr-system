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

echo "[startup] Running Alembic migrations..."
alembic upgrade head

if [ "${SYNC_ADMIN_ON_START:-false}" = "true" ]; then
  echo "[startup] Syncing admin account..."
  python create_admin.py || true
fi

echo "[startup] Starting API server with ${WEB_CONCURRENCY} worker(s)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY}"
