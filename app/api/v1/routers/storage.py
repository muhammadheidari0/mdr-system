from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import User, allow_admin, allow_editor, allow_viewer, get_db
from app.db.models import ArchiveFile, LocalSyncManifest
from app.services.storage_sync import JOB_GOOGLE_DRIVE_MIRROR, JOB_OPENPROJECT_SYNC, run_storage_jobs

router = APIRouter(prefix="/storage", tags=["Storage"])


def _scope_value(user: User, policy_scope: Optional[str]) -> str:
    raw = str(policy_scope or "").strip()
    if raw:
        return raw
    user_id = int(getattr(user, "id", 0) or 0)
    return f"user:{user_id}" if user_id > 0 else "global"


def _sha256_for_path(path_value: str) -> str:
    path = Path(str(path_value or "").strip())
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _upsert_manifest(
    db: Session,
    *,
    file_id: int,
    scope: str,
    version_hash: str,
    is_pinned: bool,
) -> LocalSyncManifest:
    row = (
        db.query(LocalSyncManifest)
        .filter(LocalSyncManifest.file_id == int(file_id))
        .filter(LocalSyncManifest.policy_scope == scope)
        .first()
    )
    if not row:
        row = LocalSyncManifest(
            file_id=int(file_id),
            policy_scope=scope,
            version_hash=version_hash,
            is_pinned=bool(is_pinned),
        )
        db.add(row)
        db.flush()
        return row
    row.version_hash = version_hash
    row.is_pinned = bool(is_pinned)
    row.last_modified_at = datetime.utcnow()
    db.flush()
    return row


class LocalCachePinIn(BaseModel):
    file_id: int = Field(..., ge=1)
    policy_scope: Optional[str] = Field(default=None, max_length=64)


class LocalCacheUnpinIn(BaseModel):
    file_id: int = Field(..., ge=1)
    policy_scope: Optional[str] = Field(default=None, max_length=64)


@router.post("/sync/google-drive/run")
def run_google_drive_jobs(
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    del user
    result = run_storage_jobs(db, limit=limit, job_types=[JOB_GOOGLE_DRIVE_MIRROR])
    return {"ok": True, **result}


@router.post("/sync/openproject/run")
def run_openproject_jobs(
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    del user
    result = run_storage_jobs(db, limit=limit, job_types=[JOB_OPENPROJECT_SYNC])
    return {"ok": True, **result}


@router.post("/local-cache/pin")
def pin_local_cache_file(
    payload: LocalCachePinIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    scope = _scope_value(user, payload.policy_scope)
    archive = db.query(ArchiveFile).filter(ArchiveFile.id == int(payload.file_id)).first()
    if not archive:
        raise HTTPException(status_code=404, detail="File not found")

    version_hash = str(archive.sha256 or "").strip() or _sha256_for_path(archive.stored_path)
    if not version_hash:
        raise HTTPException(status_code=400, detail="File hash is not available for pin operation.")

    row = _upsert_manifest(
        db,
        file_id=int(payload.file_id),
        scope=scope,
        version_hash=version_hash,
        is_pinned=True,
    )
    db.commit()
    return {
        "ok": True,
        "data": {
            "id": row.id,
            "file_id": row.file_id,
            "version_hash": row.version_hash,
            "is_pinned": bool(row.is_pinned),
            "policy_scope": row.policy_scope,
            "last_modified_at": row.last_modified_at.isoformat() if row.last_modified_at else None,
        },
    }


@router.post("/local-cache/unpin")
def unpin_local_cache_file(
    payload: LocalCacheUnpinIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    scope = _scope_value(user, payload.policy_scope)
    row = (
        db.query(LocalSyncManifest)
        .filter(LocalSyncManifest.file_id == int(payload.file_id))
        .filter(LocalSyncManifest.policy_scope == scope)
        .first()
    )
    if not row:
        return {"ok": True, "message": "Already unpinned"}
    row.is_pinned = False
    db.commit()
    return {"ok": True}


@router.get("/local-cache/manifest")
def get_local_cache_manifest(
    policy_scope: Optional[str] = Query(default=None),
    only_pinned: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    scope = _scope_value(user, policy_scope)
    query = db.query(LocalSyncManifest).filter(LocalSyncManifest.policy_scope == scope)
    if only_pinned:
        query = query.filter(LocalSyncManifest.is_pinned.is_(True))
    rows = query.order_by(LocalSyncManifest.last_modified_at.desc(), LocalSyncManifest.id.desc()).all()

    items: list[dict] = []
    for row in rows:
        archive = db.query(ArchiveFile).filter(ArchiveFile.id == int(row.file_id)).first()
        if not archive:
            continue

        items.append(
            {
                "file_id": row.file_id,
                "entity_type": "archive_file",
                "file_name": archive.original_name,
                "version_hash": row.version_hash,
                "sha256": archive.sha256,
                "is_pinned": bool(row.is_pinned),
                "policy_scope": row.policy_scope,
                "mirror_status": archive.mirror_status,
                "last_modified_at": row.last_modified_at.isoformat() if row.last_modified_at else None,
            }
        )
    return {"ok": True, "scope": scope, "items": items}
