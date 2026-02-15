from __future__ import annotations

import time

from app.db.session import SessionLocal
from app.services.storage_sync import run_storage_jobs

POLL_SECONDS = 5
JOB_BATCH_SIZE = 25
RETRY_LIMIT = 8


def run_forever() -> None:
    while True:
        with SessionLocal() as db:
            result = run_storage_jobs(
                db,
                limit=JOB_BATCH_SIZE,
                retry_limit=RETRY_LIMIT,
            )
            processed = int(result.get("processed", 0))
        if processed <= 0:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
