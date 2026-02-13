#!/usr/bin/env sh
set -eu

echo "[startup] Running Alembic migrations..."
alembic upgrade head

if [ "${SYNC_ADMIN_ON_START:-false}" = "true" ]; then
  echo "[startup] Syncing admin account..."
  python create_admin.py || true
fi

echo "[startup] Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
