#!/usr/bin/env sh
set -eu

WAIT_TIMEOUT_SECONDS="${WORKER_DB_WAIT_TIMEOUT_SECONDS:-600}"
WAIT_INTERVAL_SECONDS="${WORKER_DB_WAIT_INTERVAL_SECONDS:-3}"

echo "[worker-startup] Waiting for database/schema readiness..."

python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text


def _to_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except Exception:
        value = default
    return value if value > 0 else default


database_url = str(os.getenv("DATABASE_URL", "")).strip()
timeout_seconds = _to_int("WORKER_DB_WAIT_TIMEOUT_SECONDS", 600)
interval_seconds = _to_int("WORKER_DB_WAIT_INTERVAL_SECONDS", 3)

if not database_url:
    print("[worker-startup] DATABASE_URL is empty.", flush=True)
    sys.exit(1)

deadline = time.time() + timeout_seconds
wait_reason_printed = False

while True:
    engine = None
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            settings_kv_table = conn.execute(text("SELECT to_regclass('public.settings_kv')")).scalar()
            if settings_kv_table:
                print("[worker-startup] Database is reachable and schema is ready.", flush=True)
                break
            if not wait_reason_printed:
                print("[worker-startup] Waiting for Alembic migrations (settings_kv is missing)...", flush=True)
                wait_reason_printed = True
    except Exception as exc:  # pragma: no cover - runtime startup path
        print(f"[worker-startup] Waiting for database connection: {exc}", flush=True)
    finally:
        if engine is not None:
            engine.dispose()

    if time.time() >= deadline:
        print(
            f"[worker-startup] Timeout after {timeout_seconds}s waiting for database/schema readiness.",
            flush=True,
        )
        sys.exit(1)
    time.sleep(interval_seconds)
PY

echo "[worker-startup] Starting storage worker..."
exec python -m app.workers.storage_worker
