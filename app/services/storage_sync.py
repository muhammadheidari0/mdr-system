from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import ArchiveFile, CorrespondenceAttachment, OpenProjectLink, StorageJob
from app.services.google_drive_adapter import GoogleDriveAdapter
from app.services.openproject_adapter import OpenProjectAdapter
from app.services.storage_jobs import (
    claim_pending_jobs,
    enqueue_storage_job,
    job_payload,
    mark_job_retry,
    mark_job_success,
)
from app.services.storage_policy import get_storage_integrations

JOB_GOOGLE_DRIVE_MIRROR = "google_drive_mirror"
JOB_OPENPROJECT_SYNC = "openproject_sync"


def enqueue_archive_mirror_job(
    db: Session,
    *,
    archive_file_id: int,
    work_package_id: int | None = None,
) -> StorageJob:
    payload = {
        "entity_type": "archive_file",
        "entity_id": int(archive_file_id),
    }
    if work_package_id:
        payload["work_package_id"] = int(work_package_id)
    return enqueue_storage_job(
        db,
        job_type=JOB_GOOGLE_DRIVE_MIRROR,
        file_id=int(archive_file_id),
        payload=payload,
    )


def enqueue_correspondence_mirror_job(
    db: Session,
    *,
    attachment_id: int,
    work_package_id: int | None = None,
) -> StorageJob:
    payload = {
        "entity_type": "correspondence_attachment",
        "entity_id": int(attachment_id),
    }
    if work_package_id:
        payload["work_package_id"] = int(work_package_id)
    return enqueue_storage_job(
        db,
        job_type=JOB_GOOGLE_DRIVE_MIRROR,
        file_id=int(attachment_id),
        payload=payload,
    )


def enqueue_openproject_job(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    work_package_id: int,
    file_url: str,
    title: str,
) -> StorageJob:
    payload = {
        "entity_type": str(entity_type or "").strip(),
        "entity_id": int(entity_id),
        "work_package_id": int(work_package_id),
        "file_url": str(file_url or "").strip(),
        "title": str(title or "").strip(),
    }
    return enqueue_storage_job(
        db,
        job_type=JOB_OPENPROJECT_SYNC,
        file_id=int(entity_id),
        payload=payload,
    )


def _resolve_entity_file(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
) -> tuple[str, str, str, Any]:
    key = str(entity_type or "").strip().lower()
    if key == "archive_file":
        row = db.query(ArchiveFile).filter(ArchiveFile.id == int(entity_id)).first()
        if not row:
            raise RuntimeError(f"Archive file not found: {entity_id}")
        return (row.stored_path, row.original_name, row.mime_type or "application/octet-stream", row)
    if key == "correspondence_attachment":
        row = db.query(CorrespondenceAttachment).filter(CorrespondenceAttachment.id == int(entity_id)).first()
        if not row:
            raise RuntimeError(f"Correspondence attachment not found: {entity_id}")
        return (row.stored_path, row.file_name, row.mime_type or "application/octet-stream", row)
    raise RuntimeError(f"Unsupported entity type for storage sync: {entity_type}")


def _set_mirror_result(
    *,
    row: Any,
    gdrive_file_id: str | None,
    status: str,
) -> None:
    row.gdrive_file_id = str(gdrive_file_id or "").strip() or None
    row.mirror_status = str(status or "").strip() or "pending"
    row.mirror_updated_at = datetime.utcnow()


def _sync_google_drive(db: Session, job: StorageJob, integrations: dict[str, Any]) -> dict[str, Any]:
    payload = job_payload(job)
    entity_type = str(payload.get("entity_type") or "").strip()
    entity_id = int(payload.get("entity_id") or 0)
    if not entity_type or entity_id <= 0:
        raise RuntimeError("Invalid google drive mirror payload.")

    gdrive_cfg = integrations.get("google_drive", {})
    if not bool(gdrive_cfg.get("enabled")):
        path, _, _, row = _resolve_entity_file(db, entity_type=entity_type, entity_id=entity_id)
        _ = path
        _set_mirror_result(row=row, gdrive_file_id=None, status="disabled")
        return {"status": "disabled"}

    local_path, display_name, mime_type, row = _resolve_entity_file(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    adapter = GoogleDriveAdapter(
        service_account_json=str(settings.GDRIVE_SERVICE_ACCOUNT_JSON or "").strip(),
        shared_drive_id=str(settings.GDRIVE_SHARED_DRIVE_ID or "").strip(),
        root_folder_id=str(gdrive_cfg.get("root_folder_id") or ""),
    )
    upload_result = adapter.upload_file(
        local_path=local_path,
        display_name=display_name,
        mime_type=mime_type,
    )
    _set_mirror_result(row=row, gdrive_file_id=upload_result.get("file_id"), status="mirrored")

    work_package_id = int(payload.get("work_package_id") or 0)
    if work_package_id > 0:
        enqueue_openproject_job(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            work_package_id=work_package_id,
            file_url=str(upload_result.get("web_view_link") or ""),
            title=display_name,
        )
    return {
        "status": "mirrored",
        "gdrive_file_id": upload_result.get("file_id"),
        "web_view_link": upload_result.get("web_view_link"),
    }


def _upsert_openproject_link(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    work_package_id: int,
    sync_status: str,
    attachment_id: str | None = None,
) -> OpenProjectLink:
    row = (
        db.query(OpenProjectLink)
        .filter(OpenProjectLink.entity_type == entity_type)
        .filter(OpenProjectLink.entity_id == entity_id)
        .filter(OpenProjectLink.work_package_id == work_package_id)
        .first()
    )
    if not row:
        row = OpenProjectLink(
            entity_type=entity_type,
            entity_id=entity_id,
            work_package_id=work_package_id,
            sync_status=sync_status,
            openproject_attachment_id=str(attachment_id or "").strip() or None,
            last_synced_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        return row
    row.sync_status = sync_status
    row.openproject_attachment_id = str(attachment_id or "").strip() or row.openproject_attachment_id
    row.last_synced_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def _sync_openproject(db: Session, job: StorageJob, integrations: dict[str, Any]) -> dict[str, Any]:
    payload = job_payload(job)
    entity_type = str(payload.get("entity_type") or "").strip()
    entity_id = int(payload.get("entity_id") or 0)
    work_package_id = int(payload.get("work_package_id") or 0)
    file_url = str(payload.get("file_url") or "").strip()
    title = str(payload.get("title") or "").strip() or f"{entity_type}:{entity_id}"
    if not entity_type or entity_id <= 0 or work_package_id <= 0:
        raise RuntimeError("Invalid openproject sync payload.")

    openproject_cfg = integrations.get("openproject", {})
    if not bool(openproject_cfg.get("enabled")):
        _upsert_openproject_link(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            work_package_id=work_package_id,
            sync_status="disabled",
        )
        return {"status": "disabled"}

    adapter = OpenProjectAdapter(
        base_url=str(settings.OPENPROJECT_BASE_URL or "").strip()
        or str(openproject_cfg.get("base_url") or "").strip(),
        api_token=str(settings.OPENPROJECT_API_TOKEN or "").strip(),
    )
    response = adapter.attach_external_link(
        work_package_id=work_package_id,
        title=title,
        url=file_url,
    )
    op_id = str(response.get("id") or "")
    _upsert_openproject_link(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        work_package_id=work_package_id,
        sync_status="synced",
        attachment_id=op_id or None,
    )
    return {"status": "synced", "openproject_attachment_id": op_id or None}


def process_job(db: Session, job: StorageJob, integrations: dict[str, Any]) -> dict[str, Any]:
    if job.job_type == JOB_GOOGLE_DRIVE_MIRROR:
        return _sync_google_drive(db, job, integrations)
    if job.job_type == JOB_OPENPROJECT_SYNC:
        return _sync_openproject(db, job, integrations)
    raise RuntimeError(f"Unsupported storage job type: {job.job_type}")


def run_storage_jobs(
    db: Session,
    *,
    limit: int = 20,
    job_types: list[str] | None = None,
    retry_limit: int = 8,
) -> dict[str, Any]:
    integrations = get_storage_integrations(db)
    rows = claim_pending_jobs(db, job_types=job_types, limit=limit)
    db.commit()

    processed = 0
    success = 0
    failed = 0
    dead = 0
    details: list[dict[str, Any]] = []

    for row in rows:
        processed += 1
        try:
            result = process_job(db, row, integrations)
            mark_job_success(db, row, payload={**job_payload(row), "result": result})
            success += 1
            details.append({"id": row.id, "job_type": row.job_type, "status": "success", "result": result})
            db.commit()
        except Exception as exc:
            mark_job_retry(
                db,
                row,
                error_message=str(exc),
                retry_limit=retry_limit,
            )
            if str(row.status or "") == "dead":
                dead += 1
            else:
                failed += 1
            details.append(
                {
                    "id": row.id,
                    "job_type": row.job_type,
                    "status": str(row.status),
                    "error": str(exc),
                    "retry_count": int(row.retry_count or 0),
                }
            )
            db.commit()

    return {
        "processed": processed,
        "success": success,
        "failed": failed,
        "dead": dead,
        "details": details,
    }
