from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import StorageJob

DEFAULT_RETRY_LIMIT = 8


def _utcnow() -> datetime:
    return datetime.utcnow()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(value: str | None) -> dict[str, Any]:
    raw = str(value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def enqueue_storage_job(
    db: Session,
    *,
    job_type: str,
    file_id: int | None,
    payload: dict[str, Any] | None = None,
    status: str = "pending",
) -> StorageJob:
    row = StorageJob(
        job_type=str(job_type or "").strip(),
        file_id=file_id,
        payload_json=_json_dumps(payload or {}),
        status=str(status or "pending").strip() or "pending",
        retry_count=0,
        next_retry_at=None,
        last_error=None,
    )
    db.add(row)
    db.flush()
    return row


def claim_pending_jobs(
    db: Session,
    *,
    job_types: list[str] | None = None,
    limit: int = 20,
) -> list[StorageJob]:
    now = _utcnow()
    query = db.query(StorageJob).filter(
        StorageJob.status.in_(["pending", "retry"]),
        or_(StorageJob.next_retry_at.is_(None), StorageJob.next_retry_at <= now),
    )
    if job_types:
        query = query.filter(StorageJob.job_type.in_([str(j).strip() for j in job_types if str(j).strip()]))
    rows = (
        query.order_by(StorageJob.created_at.asc(), StorageJob.id.asc())
        .limit(max(1, min(int(limit), 200)))
        .all()
    )
    for row in rows:
        row.status = "running"
        row.last_error = None
        row.updated_at = now
    db.flush()
    return rows


def mark_job_success(db: Session, row: StorageJob, payload: dict[str, Any] | None = None) -> None:
    row.status = "success"
    row.retry_count = int(row.retry_count or 0)
    row.next_retry_at = None
    row.last_error = None
    if payload is not None:
        row.payload_json = _json_dumps(payload)
    row.updated_at = _utcnow()
    db.flush()


def mark_job_retry(
    db: Session,
    row: StorageJob,
    *,
    error_message: str,
    retry_limit: int = DEFAULT_RETRY_LIMIT,
) -> None:
    current_retry = int(row.retry_count or 0) + 1
    row.retry_count = current_retry
    row.last_error = str(error_message or "").strip()[:4000]
    if current_retry >= int(retry_limit):
        row.status = "dead"
        row.next_retry_at = None
    else:
        # Exponential-ish backoff with upper bound
        delay_seconds = min(300, max(5, 2 ** min(current_retry, 7)))
        row.status = "retry"
        row.next_retry_at = _utcnow() + timedelta(seconds=delay_seconds)
    row.updated_at = _utcnow()
    db.flush()


def job_payload(row: StorageJob) -> dict[str, Any]:
    return _json_loads(row.payload_json)
