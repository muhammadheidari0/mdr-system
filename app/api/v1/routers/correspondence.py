from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import (
    User,
    apply_scope_query_filters,
    enforce_scope_access,
    get_db,
    require_permission,
)
from app.db.models import (
    Correspondence,
    CorrespondenceAction,
    CorrespondenceAttachment,
    CorrespondenceCategory,
    CorrespondenceExternalRelation,
    CorrespondenceTagAssignment,
    Discipline,
    DocumentExternalRelation,
    DocumentRevision,
    DocumentTag,
    IssuingEntity,
    MdrDocument,
    MeetingMinute,
    OpenProjectLink,
    Project,
    Transmittal,
    TransmittalDoc,
)
from app.services.folder_service import safe_name
from app.services.nextcloud_adapter import NextcloudAdapter
from app.services.openproject_status import (
    ENTITY_CORRESPONDENCE_ATTACHMENT,
    default_openproject_sync_status,
    get_openproject_status_map,
    is_openproject_integration_enabled,
)
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import (
    enqueue_correspondence_mirror_job,
    resolve_mirror_enqueue_plan,
    resolve_nextcloud_runtime,
)
from app.services import tag_service

router = APIRouter(prefix="/correspondence", tags=["Correspondence"])
AUTO_REFERENCE_MAX_RETRIES = 8
AUTO_REFERENCE_SERIAL_WIDTH = 3


def _attachment_openproject_status_map(db: Session, attachment_ids: list[int]) -> tuple[dict[tuple[str, int], dict], str]:
    clean_ids = [int(attachment_id) for attachment_id in attachment_ids if int(attachment_id or 0) > 0]
    integration_enabled = is_openproject_integration_enabled(db)
    fallback_status = default_openproject_sync_status(integration_enabled=integration_enabled)
    if not clean_ids:
        return {}, fallback_status
    status_map = get_openproject_status_map(
        db,
        [(ENTITY_CORRESPONDENCE_ATTACHMENT, attachment_id) for attachment_id in clean_ids],
        integration_enabled=integration_enabled,
    )
    return status_map, fallback_status


def _attachment_openproject_payload(status_map: dict[tuple[str, int], dict], fallback_status: str, attachment_id: int) -> dict:
    row = status_map.get((ENTITY_CORRESPONDENCE_ATTACHMENT, int(attachment_id or 0)), {})
    return {
        "openproject_sync_status": str(row.get("sync_status") or fallback_status),
        "openproject_work_package_id": row.get("work_package_id"),
        "openproject_attachment_id": row.get("openproject_attachment_id"),
        "openproject_last_synced_at": row.get("last_synced_at"),
    }


def _norm(value: Optional[str]) -> str:
    return str(value or "").strip()


def _norm_upper(value: Optional[str]) -> str:
    return _norm(value).upper()


def _parse_filter_date(value: Optional[str], field_name: str) -> Optional[datetime]:
    raw = _norm(value)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid `{field_name}` format (YYYY-MM-DD expected).",
        ) from exc


def _category_code(value: Optional[str]) -> str:
    raw = _norm_upper(value)
    mapping = {
        "LETTER": "CO",
        "CORRESPONDENCE": "CO",
        "MOM": "M",
        "MEETING": "M",
        "EMAIL": "I",
        "MAIL": "I",
        "PERSONNEL": "S",
        "FINANCE": "F",
        "LEGAL": "L",
        "CONFIDENTIAL": "C",
        "INVOICE": "V",
        "PROFORMA": "P",
    }
    if raw in mapping:
        return mapping[raw]
    alnum = "".join(ch for ch in raw if ch.isalnum())
    if not alnum:
        return "CO"
    return alnum[:2]


def _direction_code(value: Optional[str]) -> str:
    raw = _norm_upper(value)
    if raw in {"IN", "I", "INBOUND"}:
        return "I"
    if raw in {"OUT", "O", "OUTBOUND"}:
        return "O"
    return "O"


def _reference_period(value: Optional[datetime]) -> str:
    dt = value or datetime.utcnow()
    return dt.strftime("%y%m")


def _reference_prefix(
    *,
    issuing_code: str,
    category_code: str,
    direction: str,
    corr_date: Optional[datetime],
) -> str:
    issuing = _norm_upper(issuing_code)
    category = _norm_upper(category_code)
    dcode = _direction_code(direction)
    period = _reference_period(corr_date)
    return f"{issuing}-{category}-{dcode}-{period}"


def _extract_serial(reference_no: str, prefix: str) -> Optional[int]:
    value = _norm(reference_no)
    if not value.startswith(prefix):
        return None
    suffix = value[len(prefix):]
    if not suffix.isdigit():
        return None
    try:
        return int(suffix)
    except Exception:
        return None


def _next_reference_serial(
    db: Session,
    *,
    issuing_code: str,
    category_code: str,
    direction: str,
    corr_date: Optional[datetime],
) -> int:
    prefix = _reference_prefix(
        issuing_code=issuing_code,
        category_code=category_code,
        direction=direction,
        corr_date=corr_date,
    )
    rows = (
        db.query(Correspondence.reference_no)
        .filter(
            Correspondence.reference_no.is_not(None),
            Correspondence.reference_no.like(f"{prefix}%"),
        )
        .all()
    )
    max_serial = 0
    for (reference_no,) in rows:
        serial = _extract_serial(str(reference_no or ""), prefix)
        if serial is not None and serial > max_serial:
            max_serial = serial
    return max_serial + 1


def _build_reference_no(
    *,
    issuing_code: str,
    category_code: str,
    direction: str,
    corr_date: Optional[datetime],
    serial: int,
) -> str:
    prefix = _reference_prefix(
        issuing_code=issuing_code,
        category_code=category_code,
        direction=direction,
        corr_date=corr_date,
    )
    return f"{prefix}{serial:0{AUTO_REFERENCE_SERIAL_WIDTH}d}"


def _is_reference_unique_violation(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "unique constraint failed" in text and "correspondences.reference_no" in text
    ) or ("uq_correspondences_reference_no" in text)


def _should_auto_reference(
    *,
    issuing_code: str,
    category_code: str,
    direction: str,
    manual_reference: Optional[str],
) -> bool:
    if _norm(manual_reference):
        return False
    return bool(_norm_upper(issuing_code)) and bool(_norm_upper(category_code)) and bool(_direction_code(direction))


def _resolve_category_code(category_code: Optional[str], doc_type: Optional[str]) -> str:
    category = _norm_upper(category_code)
    if category:
        return category
    return _category_code(doc_type)


def _resolve_issuing_code(issuing_code: Optional[str], project_code: Optional[str]) -> str:
    issuing = _norm_upper(issuing_code)
    if issuing:
        return issuing
    project = _norm_upper(project_code)
    if project:
        return project
    return "G"


def _resolve_project_for_issuing(
    db: Session,
    *,
    project_code: Optional[str],
    issuing: Optional[IssuingEntity],
) -> Optional[str]:
    normalized_project = _norm_upper(project_code)
    if normalized_project:
        return normalized_project
    if issuing and issuing.project_code:
        return _norm_upper(issuing.project_code)
    return None


def _get_or_create_issuing_entity(
    db: Session,
    *,
    issuing_code: str,
    project_code_hint: Optional[str] = None,
) -> IssuingEntity:
    code = _norm_upper(issuing_code)
    row = db.query(IssuingEntity).filter(IssuingEntity.code == code).first()
    if row:
        return row

    project_code = _norm_upper(project_code_hint) or code
    project = db.query(Project).filter(Project.code == project_code).first()
    if project:
        row = IssuingEntity(
            code=code,
            name_e=str(project.name_e or project.name_p or project.code),
            project_code=project.code,
            is_active=bool(project.is_active),
            sort_order=100,
        )
    else:
        row = IssuingEntity(
            code=code,
            name_e=code,
            project_code=None,
            is_active=True,
            sort_order=999,
        )
    db.add(row)
    db.flush()
    return row


def _get_or_create_category(
    db: Session,
    *,
    category_code: str,
) -> CorrespondenceCategory:
    code = _norm_upper(category_code)
    row = db.query(CorrespondenceCategory).filter(CorrespondenceCategory.code == code).first()
    if row:
        return row
    row = CorrespondenceCategory(
        code=code,
        name_e=code,
        is_active=True,
        sort_order=999,
    )
    db.add(row)
    db.flush()
    return row


class CorrespondenceCreateIn(BaseModel):
    project_code: Optional[str] = Field(default=None, max_length=50)
    issuing_code: Optional[str] = Field(default=None, max_length=20)
    category_code: Optional[str] = Field(default=None, max_length=20)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    tag_id: Optional[int] = Field(default=None, ge=1)
    doc_type: str = Field(default="Letter", min_length=1, max_length=20)
    direction: str = Field(default="IN", min_length=1, max_length=10)
    reference_no: Optional[str] = Field(default=None, max_length=120)
    subject: str = Field(..., min_length=1)
    sender: Optional[str] = Field(default=None, max_length=255)
    recipient: Optional[str] = Field(default=None)
    corr_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    status: str = Field(default="Open", min_length=1, max_length=20)
    priority: str = Field(default="Normal", min_length=1, max_length=20)
    notes: Optional[str] = None


class CorrespondenceUpdateIn(BaseModel):
    project_code: Optional[str] = Field(default=None, max_length=50)
    issuing_code: Optional[str] = Field(default=None, max_length=20)
    category_code: Optional[str] = Field(default=None, max_length=20)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    tag_id: Optional[int] = Field(default=None, ge=1)
    doc_type: Optional[str] = Field(default=None, max_length=20)
    direction: Optional[str] = Field(default=None, max_length=10)
    reference_no: Optional[str] = Field(default=None, max_length=120)
    subject: Optional[str] = None
    sender: Optional[str] = Field(default=None, max_length=255)
    recipient: Optional[str] = None
    corr_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = Field(default=None, max_length=20)
    priority: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = None


class CorrespondenceActionCreateIn(BaseModel):
    action_type: str = Field(default="task", min_length=1, max_length=32)
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    to_user_id: Optional[int] = None
    due_date: Optional[datetime] = None
    status: str = Field(default="Open", min_length=1, max_length=20)
    is_closed: bool = False


class CorrespondenceActionUpdateIn(BaseModel):
    action_type: Optional[str] = Field(default=None, max_length=32)
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    to_user_id: Optional[int] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = Field(default=None, max_length=20)
    is_closed: Optional[bool] = None


class CorrespondenceRelationCreateIn(BaseModel):
    target_entity_type: str = Field(default="document", min_length=1, max_length=32)
    target_code: Optional[str] = Field(default=None, max_length=128)
    target_entity_id: Optional[str] = Field(default=None, max_length=128)
    relation_type: Optional[str] = Field(default="related", max_length=32)
    notes: Optional[str] = None


def _attachment_kind(value: Optional[str]) -> str:
    kind = _norm(value).lower()
    aliases = {
        "main": "letter",
        "inside": "original",
        "attachments": "attachment",
    }
    if kind in aliases:
        return aliases[kind]
    if kind in {"letter", "original", "attachment"}:
        return kind
    return "attachment"


def _correspondence_bucket_for_kind(file_kind: str) -> str:
    return {
        "letter": "main",
        "original": "inside",
        "attachment": "attachments",
    }.get(_attachment_kind(file_kind), "attachments")


def _corr_category_folder(row: Correspondence) -> str:
    category = getattr(row, "category", None)
    value = (
        getattr(category, "name_e", None)
        or getattr(category, "name_p", None)
        or row.category_code
        or "GENERAL"
    )
    return safe_name(value) or "GENERAL"


def _corr_direction_folder(row: Correspondence) -> str:
    return safe_name(_norm(row.direction).upper() or "IN") or "IN"


def _corr_reference_folder(row: Correspondence) -> str:
    return safe_name(row.reference_no or f"CORR-{row.id}") or f"CORR-{row.id}"


def _unique_file_name(folder: Path, desired_name: str) -> str:
    candidate = safe_name(desired_name)
    if not candidate:
        candidate = "file"
    path = folder / candidate
    if not path.exists():
        return candidate

    suffix = Path(candidate).suffix
    stem = Path(candidate).stem or "file"
    counter = 2
    while True:
        next_name = safe_name(f"{stem}_{counter:02d}{suffix}")
        if not (folder / next_name).exists():
            return next_name
        counter += 1


def _nextcloud_adapter_for_webdav(db: Session) -> NextcloudAdapter:
    integrations = get_storage_integrations(db)
    runtime = resolve_nextcloud_runtime(integrations)
    if not runtime.get("enabled") or runtime.get("mode") != "webdav":
        raise HTTPException(status_code=503, detail="WebDAV storage not configured.")
    return NextcloudAdapter(
        base_url=str(runtime.get("base_url") or ""),
        username=str(runtime.get("username") or ""),
        app_password=str(runtime.get("app_password") or ""),
        root_path=str(runtime.get("root_path") or ""),
        connect_timeout=float(runtime.get("connect_timeout") or 5),
        read_timeout=float(runtime.get("read_timeout") or 10),
        tls_verify=bool(runtime.get("tls_verify")),
    )


def _unique_remote_file_name(db: Session, folder: str, desired_name: str) -> str:
    candidate = safe_name(desired_name) or "file"
    remote_folder = str(folder or "").strip().rstrip("/")
    remote_path = f"{remote_folder}/{candidate}" if remote_folder else candidate
    adapter = _nextcloud_adapter_for_webdav(db)
    if not adapter.file_exists(remote_path):
        return candidate

    suffix = Path(candidate).suffix
    stem = Path(candidate).stem or "file"
    counter = 2
    while True:
        next_name = safe_name(f"{stem}_{counter:02d}{suffix}")
        remote_path = f"{remote_folder}/{next_name}" if remote_folder else next_name
        if not adapter.file_exists(remote_path):
            return next_name
        counter += 1


def _next_corr_attachment_sequence(db: Session, correspondence_id: int) -> int:
    existing = (
        db.query(func.count(CorrespondenceAttachment.id))
        .filter(
            CorrespondenceAttachment.correspondence_id == int(correspondence_id),
            CorrespondenceAttachment.file_kind == "attachment",
            CorrespondenceAttachment.deleted_at.is_(None),
        )
        .scalar()
    )
    return int(existing or 0) + 1


def _corr_storage_file_name(
    db: Session,
    row: Correspondence,
    *,
    file_kind: str,
    original_name: str,
    folder: Path,
    storage_manager: StorageManager | None = None,
) -> str:
    safe_original = safe_name(original_name) or "file"
    original_path = Path(safe_original)
    suffix = original_path.suffix or ".pdf"
    stem = safe_name(original_path.stem) or "InsideLetter"
    reference_no = _corr_reference_folder(row)

    normalized_kind = _attachment_kind(file_kind)
    if normalized_kind == "letter":
        title = safe_name(row.subject or row.reference_no or "Untitled") or "Untitled"
        desired = f"{reference_no}_{title}{suffix}"
    elif normalized_kind == "original":
        desired = f"{reference_no}_{stem}{suffix}"
    else:
        desired = f"{_next_corr_attachment_sequence(db, int(row.id or 0)):02d}_{safe_original}"
    if storage_manager and storage_manager._is_webdav_primary_mode():
        remote_folder = StorageManager._normalize_remote_path(str(folder))
        return _unique_remote_file_name(db, remote_folder, desired)
    return _unique_file_name(folder, desired)


def _download_webdav_attachment(
    db: Session,
    row: CorrespondenceAttachment,
    *,
    inline: bool = False,
) -> StreamingResponse:
    stored_path = str(row.stored_path or "").strip()
    remote_path = stored_path.replace("webdav://", "", 1)
    adapter = _nextcloud_adapter_for_webdav(db)
    if not adapter.file_exists(remote_path):
        raise HTTPException(status_code=404, detail="Attachment file not found")
    filename = safe_name(row.file_name or f"attachment-{row.id}") or f"attachment-{row.id}"
    media_type = (
        _attachment_preview_media_type(row)
        if inline
        else _norm(row.mime_type or row.detected_mime)
    ) or "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    return StreamingResponse(
        adapter.download_file_stream(remote_path),
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _delete_stored_attachment_file(db: Session, stored_path: str) -> None:
    raw_path = str(stored_path or "").strip()
    if not raw_path:
        return
    if raw_path.startswith("webdav://"):
        try:
            adapter = _nextcloud_adapter_for_webdav(db)
            adapter.delete_file(raw_path.replace("webdav://", "", 1))
        except Exception:
            pass
        return

    file_path = Path(raw_path)
    try:
        if file_path.exists():
            os.remove(file_path)
    except Exception:
        pass


def _serialize_action(row: CorrespondenceAction) -> dict:
    return {
        "id": row.id,
        "correspondence_id": row.correspondence_id,
        "action_type": row.action_type,
        "title": row.title,
        "description": row.description,
        "from_user_id": row.from_user_id,
        "from_user_name": getattr(getattr(row, "from_user", None), "full_name", None),
        "to_user_id": row.to_user_id,
        "to_user_name": getattr(getattr(row, "to_user", None), "full_name", None),
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "status": row.status,
        "is_closed": bool(row.is_closed),
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_attachment(
    row: CorrespondenceAttachment,
    *,
    openproject_payload: dict | None = None,
) -> dict:
    openproject_payload = openproject_payload or {}
    return {
        "id": row.id,
        "correspondence_id": row.correspondence_id,
        "action_id": row.action_id,
        "file_name": row.file_name,
        "file_kind": _attachment_kind(row.file_kind),
        "mime_type": row.mime_type,
        "detected_mime": row.detected_mime,
        "preview_supported": _attachment_preview_supported(row),
        "validation_status": row.validation_status,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "storage_backend": row.storage_backend,
        "gdrive_file_id": row.gdrive_file_id,
        "mirror_provider": getattr(row, "mirror_provider", None),
        "mirror_remote_id": getattr(row, "mirror_remote_id", None),
        "mirror_remote_url": getattr(row, "mirror_remote_url", None),
        "mirror_status": row.mirror_status,
        "mirror_updated_at": row.mirror_updated_at.isoformat() if row.mirror_updated_at else None,
        "uploaded_by_id": row.uploaded_by_id,
        "uploaded_by_name": getattr(getattr(row, "uploaded_by", None), "full_name", None),
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        **openproject_payload,
    }


def _load_correspondence_or_404(db: Session, correspondence_id: int) -> Correspondence:
    row = db.query(Correspondence).filter(Correspondence.id == correspondence_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Correspondence not found")
    return row


def _load_correspondence_with_tags(db: Session, correspondence_id: int) -> Correspondence:
    row = (
        db.query(Correspondence)
        .options(
            selectinload(Correspondence.issuing_entity),
            selectinload(Correspondence.category),
            selectinload(Correspondence.tag_assignments).selectinload(CorrespondenceTagAssignment.tag),
        )
        .filter(Correspondence.id == int(correspondence_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Correspondence not found")
    return row


def _load_action_or_404(db: Session, action_id: int) -> CorrespondenceAction:
    row = db.query(CorrespondenceAction).filter(CorrespondenceAction.id == action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    return row


def _load_attachment_or_404(db: Session, attachment_id: int) -> CorrespondenceAttachment:
    row = (
        db.query(CorrespondenceAttachment)
        .filter(
            CorrespondenceAttachment.id == attachment_id,
            CorrespondenceAttachment.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return row


PREVIEW_UNSUPPORTED_DETAIL = (
    "پیش‌نمایش فقط برای PDF و فایل‌های تصویری پشتیبانی می‌شود. "
    "برای این فایل از دانلود استفاده کنید."
)

_PREVIEW_EXTENSION_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _attachment_preview_media_type(row: CorrespondenceAttachment | None) -> str | None:
    if not row or row.deleted_at is not None:
        return None
    mime_type = _norm(row.detected_mime or row.mime_type).lower()
    if mime_type in {"application/pdf", "application/x-pdf"}:
        return "application/pdf"
    if mime_type.startswith("image/"):
        return mime_type

    for raw_name in (row.file_name, row.stored_path):
        suffix = Path(str(raw_name or "")).suffix.lower()
        if suffix in _PREVIEW_EXTENSION_MEDIA_TYPES:
            return _PREVIEW_EXTENSION_MEDIA_TYPES[suffix]
    return None


def _attachment_preview_supported(row: CorrespondenceAttachment | None) -> bool:
    if not row or row.deleted_at is not None:
        return False
    return bool(_attachment_preview_media_type(row))


def _attachment_sort_key(row: CorrespondenceAttachment) -> tuple[str, int]:
    return (
        row.uploaded_at.isoformat() if row.uploaded_at else "",
        int(row.id or 0),
    )


def _resolve_correspondence_preview_attachment(row: Correspondence) -> CorrespondenceAttachment | None:
    attachments = [
        attachment
        for attachment in list(row.attachments or [])
        if attachment.deleted_at is None and _attachment_preview_supported(attachment)
    ]
    if not attachments:
        return None

    kind_rank = {"letter": 0, "original": 1, "attachment": 2}
    attachments.sort(
        key=lambda item: (
            kind_rank.get(_attachment_kind(item.file_kind), 9),
            *_attachment_sort_key(item),
        ),
        reverse=False,
    )
    best_rank = kind_rank.get(_attachment_kind(attachments[0].file_kind), 9)
    same_kind = [item for item in attachments if kind_rank.get(_attachment_kind(item.file_kind), 9) == best_rank]
    same_kind.sort(key=_attachment_sort_key, reverse=True)
    return same_kind[0] if same_kind else attachments[0]


def _enforce_corr_scope(db: Session, user: User, row: Correspondence) -> None:
    enforce_scope_access(db, user, project_code=row.project_code)


def _normalize_relation_target_type(value: Optional[str]) -> str:
    raw = _norm(value).lower().replace("-", "_")
    aliases = {
        "doc": "document",
        "mdr": "document",
        "mdr_document": "document",
        "document": "document",
        "transmittal": "transmittal",
        "transmittals": "transmittal",
        "tr": "transmittal",
        "trans": "transmittal",
        "meeting": "meeting_minute",
        "meeting_minute": "meeting_minute",
        "meeting_minutes": "meeting_minute",
        "minute": "meeting_minute",
        "mom": "meeting_minute",
        "corr": "correspondence",
        "correspondence": "correspondence",
        "letter": "correspondence",
        "mail": "correspondence",
    }
    normalized = aliases.get(raw)
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid relation target type")
    return normalized


def _normalize_relation_type(value: Optional[str]) -> str:
    return _norm(value).lower() or "related"


def _resolve_relation_document(db: Session, *, target_code: Optional[str], target_entity_id: Optional[str]) -> MdrDocument:
    code = _norm(target_code)
    entity_key = _norm(target_entity_id)
    row: MdrDocument | None = None
    if entity_key.isdigit():
        row = db.query(MdrDocument).filter(MdrDocument.id == int(entity_key)).first()
    if not row and code.isdigit():
        row = db.query(MdrDocument).filter(MdrDocument.id == int(code)).first()
    if not row and code:
        row = (
            db.query(MdrDocument)
            .filter(func.lower(MdrDocument.doc_number) == code.lower(), MdrDocument.deleted_at.is_(None))
            .first()
        )
    if not row or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Target document not found")
    return row


def _resolve_relation_transmittal(
    db: Session, *, target_code: Optional[str], target_entity_id: Optional[str]
) -> Transmittal:
    code = _norm(target_code)
    entity_key = _norm(target_entity_id)
    lookup = entity_key or code
    if not lookup:
        raise HTTPException(status_code=400, detail="Target transmittal code is required")
    row = db.query(Transmittal).filter(func.lower(Transmittal.id) == lookup.lower()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Target transmittal not found")
    return row


def _resolve_relation_meeting_minute(
    db: Session, *, target_code: Optional[str], target_entity_id: Optional[str]
) -> MeetingMinute:
    code = _norm(target_code)
    entity_key = _norm(target_entity_id)
    row: MeetingMinute | None = None
    if entity_key.isdigit():
        row = (
            db.query(MeetingMinute)
            .filter(MeetingMinute.id == int(entity_key), MeetingMinute.deleted_at.is_(None))
            .first()
        )
    if not row and code.isdigit():
        row = (
            db.query(MeetingMinute)
            .filter(MeetingMinute.id == int(code), MeetingMinute.deleted_at.is_(None))
            .first()
        )
    if not row and code:
        row = (
            db.query(MeetingMinute)
            .filter(func.lower(MeetingMinute.meeting_no) == code.lower(), MeetingMinute.deleted_at.is_(None))
            .first()
        )
    if not row:
        raise HTTPException(status_code=404, detail="Target meeting minute not found")
    return row


def _resolve_relation_correspondence(
    db: Session, *, target_code: Optional[str], target_entity_id: Optional[str]
) -> Correspondence:
    code = _norm(target_code)
    entity_key = _norm(target_entity_id)
    row: Correspondence | None = None
    if entity_key.isdigit():
        row = db.query(Correspondence).filter(Correspondence.id == int(entity_key)).first()
    if not row and code.isdigit():
        row = db.query(Correspondence).filter(Correspondence.id == int(code)).first()
    if not row and code:
        row = (
            db.query(Correspondence)
            .filter(func.lower(Correspondence.reference_no) == code.lower())
            .first()
        )
    if not row:
        raise HTTPException(status_code=404, detail="Target correspondence not found")
    return row


def _latest_document_revision(db: Session, document_id: int) -> DocumentRevision | None:
    return (
        db.query(DocumentRevision)
        .filter(DocumentRevision.document_id == int(document_id))
        .order_by(DocumentRevision.created_at.desc(), DocumentRevision.id.desc())
        .first()
    )


def _serialize_document_relation(db: Session, row: DocumentExternalRelation) -> dict[str, Any]:
    document = row.source_document
    revision = _latest_document_revision(db, int(document.id or 0)) if document else None
    return {
        "id": f"document_external:{int(row.id or 0)}",
        "relation_id": int(row.id or 0),
        "target_entity_type": "document",
        "target_entity_id": int(getattr(document, "id", 0) or row.source_document_id or 0),
        "target_code": getattr(document, "doc_number", None),
        "target_title": (
            getattr(document, "doc_title_p", None)
            or getattr(document, "doc_title_e", None)
            or getattr(document, "subject", None)
        ),
        "target_project_code": getattr(document, "project_code", None),
        "target_status": getattr(revision, "status", None),
        "revision": getattr(revision, "revision", None),
        "relation_type": row.relation_type,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "inferred": False,
    }


def _serialize_external_relation(row: CorrespondenceExternalRelation) -> dict[str, Any]:
    return {
        "id": f"external:{int(row.id or 0)}",
        "relation_id": int(row.id or 0),
        "target_entity_type": row.target_entity_type,
        "target_entity_id": row.target_entity_id,
        "target_code": row.target_code,
        "target_title": row.target_title,
        "target_project_code": row.target_project_code,
        "target_status": row.target_status,
        "relation_type": row.relation_type,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "inferred": False,
    }


def _serialize_incoming_correspondence_relation(
    row: CorrespondenceExternalRelation,
    source: Correspondence,
) -> dict[str, Any]:
    return {
        "id": f"incoming_external:{int(row.id or 0)}",
        "relation_id": int(row.id or 0),
        "target_entity_type": "correspondence",
        "target_entity_id": str(int(source.id or 0)),
        "target_code": source.reference_no or row.target_code,
        "target_title": source.subject or row.target_title,
        "target_project_code": source.project_code or row.target_project_code,
        "target_status": source.status or row.target_status,
        "relation_type": row.relation_type,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "direction": "incoming",
        "inferred": False,
    }


def _serialize_inferred_transmittal(row: Transmittal, document_codes: set[str]) -> dict[str, Any]:
    matched_codes = [
        str(doc.document_code or "")
        for doc in list(row.docs or [])
        if str(doc.document_code or "") in document_codes
    ]
    state = row.lifecycle_status or ("issued" if row.send_date else "draft")
    return {
        "id": f"inferred_transmittal:{row.id}",
        "relation_id": None,
        "target_entity_type": "transmittal",
        "target_entity_id": row.id,
        "target_code": row.id,
        "target_title": _display_transmittal_title(row),
        "target_project_code": row.project_code,
        "target_status": state,
        "relation_type": "contains_document",
        "notes": ", ".join(matched_codes),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "inferred": True,
    }


def _display_transmittal_title(row: Transmittal) -> str:
    if row.docs:
        title = _norm(row.docs[0].document_title)
        if title:
            return title
    return f"{row.sender} -> {row.receiver}"


def _corr_storage_dir(db: Session, row: Correspondence, file_kind: str) -> Path:
    base = StorageManager(db).get_correspondence_base_path()
    issuing = safe_name(row.issuing_code or "GENERAL")
    category = _corr_category_folder(row)
    direction = _corr_direction_folder(row)
    ref = safe_name(row.reference_no or f"CORR-{row.id}")
    kind_folder = _correspondence_bucket_for_kind(file_kind)
    path = base / issuing / category / direction / ref / kind_folder
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validated_user_id_or_none(db: Session, user_id: Optional[int]) -> Optional[int]:
    if user_id is None:
        return None
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid user id")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")
    return user_id


def _counts_for_rows(db: Session, correspondence_ids: list[int]) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    if not correspondence_ids:
        return {}, {}, {}

    action_counts = {
        int(row.correspondence_id): int(row.count)
        for row in (
            db.query(
                CorrespondenceAction.correspondence_id.label("correspondence_id"),
                func.count(CorrespondenceAction.id).label("count"),
            )
            .filter(CorrespondenceAction.correspondence_id.in_(correspondence_ids))
            .group_by(CorrespondenceAction.correspondence_id)
            .all()
        )
    }

    open_action_counts = {
        int(row.correspondence_id): int(row.count)
        for row in (
            db.query(
                CorrespondenceAction.correspondence_id.label("correspondence_id"),
                func.count(CorrespondenceAction.id).label("count"),
            )
            .filter(
                CorrespondenceAction.correspondence_id.in_(correspondence_ids),
                CorrespondenceAction.is_closed.is_(False),
            )
            .group_by(CorrespondenceAction.correspondence_id)
            .all()
        )
    }

    attachment_counts = {
        int(row.correspondence_id): int(row.count)
        for row in (
            db.query(
                CorrespondenceAttachment.correspondence_id.label("correspondence_id"),
                func.count(CorrespondenceAttachment.id).label("count"),
            )
            .filter(
                CorrespondenceAttachment.correspondence_id.in_(correspondence_ids),
                CorrespondenceAttachment.deleted_at.is_(None),
            )
            .group_by(CorrespondenceAttachment.correspondence_id)
            .all()
        )
    }
    return action_counts, open_action_counts, attachment_counts


def _serialize_tag_payload(row: DocumentTag | None) -> dict[str, Any]:
    if not row:
        return {
            "id": 0,
            "name": None,
            "color": None,
        }
    return {
        "id": int(getattr(row, "id", 0) or 0),
        "name": getattr(row, "name", None),
        "color": getattr(row, "color", None),
    }


def _serialize_correspondence_tag_assignments(
    rows: list[CorrespondenceTagAssignment] | None,
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows or []:
        tag = getattr(row, "tag", None)
        tag_id = int(getattr(tag, "id", 0) or getattr(row, "tag_id", 0) or 0)
        if tag_id <= 0:
            continue
        payload.append(
            {
                "id": tag_id,
                "name": getattr(tag, "name", None),
                "color": getattr(tag, "color", None),
            }
        )
    return payload


def _serialize_correspondence(
    row: Correspondence,
    *,
    action_counts: Optional[dict[int, int]] = None,
    open_action_counts: Optional[dict[int, int]] = None,
    attachment_counts: Optional[dict[int, int]] = None,
    ) -> dict:
    action_counts = action_counts or {}
    open_action_counts = open_action_counts or {}
    attachment_counts = attachment_counts or {}
    tags = _serialize_correspondence_tag_assignments(
        list(getattr(row, "tag_assignments", None) or [])
    )
    return {
        "id": row.id,
        "project_code": row.project_code,
        "issuing_code": row.issuing_code,
        "issuing_name": getattr(getattr(row, "issuing_entity", None), "name_e", None),
        "category_code": row.category_code,
        "category_name": getattr(getattr(row, "category", None), "name_e", None),
        "discipline_code": row.discipline_code,
        "doc_type": row.doc_type,
        "direction": row.direction,
        "reference_no": row.reference_no,
        "subject": row.subject,
        "sender": row.sender,
        "recipient": row.recipient,
        "corr_date": row.corr_date.isoformat() if row.corr_date else None,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "status": row.status,
        "priority": row.priority,
        "notes": row.notes,
        "created_by_id": row.created_by_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "tag_id": int(tags[0]["id"]) if tags else None,
        "tag_ids": [int(item["id"]) for item in tags],
        "tags": tags,
        "actions_count": int(action_counts.get(int(row.id), 0)),
        "open_actions_count": int(open_action_counts.get(int(row.id), 0)),
        "attachments_count": int(attachment_counts.get(int(row.id), 0)),
    }


def _is_open_correspondence(row: Correspondence) -> bool:
    return _norm(row.status).lower() == "open"


def _serialize_correspondence_report_row(
    row: Correspondence,
    *,
    now: datetime,
    action_counts: Optional[dict[int, int]] = None,
    open_action_counts: Optional[dict[int, int]] = None,
    attachment_counts: Optional[dict[int, int]] = None,
) -> dict[str, Any]:
    payload = _serialize_correspondence(
        row,
        action_counts=action_counts,
        open_action_counts=open_action_counts,
        attachment_counts=attachment_counts,
    )
    due_date = row.due_date
    corr_date = row.corr_date
    is_overdue = bool(_is_open_correspondence(row) and due_date and due_date < now)
    payload.update(
        {
            "is_overdue": is_overdue,
            "aging_days": max(0, (now.date() - due_date.date()).days) if is_overdue and due_date else None,
            "response_window_days": (
                max(0, (due_date.date() - corr_date.date()).days)
                if due_date and corr_date
                else None
            ),
        }
    )
    return payload


@router.get("/catalog")
def get_correspondence_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    del user
    issuing_rows = (
        db.query(IssuingEntity)
        .filter(IssuingEntity.is_active.is_(True))
        .order_by(IssuingEntity.sort_order.asc(), IssuingEntity.code.asc())
        .all()
    )
    category_rows = (
        db.query(CorrespondenceCategory)
        .filter(CorrespondenceCategory.is_active.is_(True))
        .order_by(CorrespondenceCategory.sort_order.asc(), CorrespondenceCategory.code.asc())
        .all()
    )
    project_rows = (
        db.query(Project)
        .filter(Project.is_active.is_(True))
        .order_by(Project.code.asc())
        .all()
    )
    discipline_rows = db.query(Discipline).order_by(Discipline.code.asc()).all()
    tag_rows = tag_service.list_tags(db)

    return {
        "ok": True,
        "issuing_entities": [
            {
                "code": row.code,
                "name_e": row.name_e,
                "name_p": row.name_p,
                "project_code": row.project_code,
                "is_active": bool(row.is_active),
            }
            for row in issuing_rows
        ],
        "categories": [
            {
                "code": row.code,
                "name_e": row.name_e,
                "name_p": row.name_p,
                "is_active": bool(row.is_active),
            }
            for row in category_rows
        ],
        "projects": [
            {
                "code": row.code,
                "name_e": row.name_e,
                "name_p": row.name_p,
                "is_active": bool(row.is_active),
            }
            for row in project_rows
        ],
        "disciplines": [
            {
                "code": row.code,
                "name_e": row.name_e,
                "name_p": row.name_p,
            }
            for row in discipline_rows
        ],
        "tags": [_serialize_tag_payload(row) for row in tag_rows],
    }


@router.get("/dashboard")
def get_correspondence_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    query = db.query(Correspondence)
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=Correspondence.project_code,
    )
    now = datetime.utcnow()
    today_start = datetime(year=now.year, month=now.month, day=now.day)
    today_end = today_start + timedelta(days=1)

    total = query.count()
    open_count = query.filter(func.lower(Correspondence.status) == "open").count()
    overdue = query.filter(
        func.lower(Correspondence.status) == "open",
        Correspondence.due_date.is_not(None),
        Correspondence.due_date < now,
    ).count()
    today_count = query.filter(
        Correspondence.corr_date >= today_start,
        Correspondence.corr_date < today_end,
    ).count()

    actions_query = (
        db.query(CorrespondenceAction)
        .join(Correspondence, Correspondence.id == CorrespondenceAction.correspondence_id)
    )
    actions_query = apply_scope_query_filters(
        actions_query,
        db,
        user,
        project_column=Correspondence.project_code,
    )
    open_actions = actions_query.filter(CorrespondenceAction.is_closed.is_(False)).count()

    return {
        "ok": True,
        "stats": {
            "total": total,
            "open": open_count,
            "overdue": overdue,
            "today": today_count,
            "open_actions": open_actions,
        },
    }


@router.get("/list")
def list_correspondence(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    project_code: Optional[str] = None,
    issuing_code: Optional[str] = None,
    category_code: Optional[str] = None,
    discipline_code: Optional[str] = None,
    tag_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    query = db.query(Correspondence)
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=Correspondence.project_code,
    )
    query = query.options(
        selectinload(Correspondence.issuing_entity),
        selectinload(Correspondence.category),
        selectinload(Correspondence.tag_assignments).selectinload(CorrespondenceTagAssignment.tag),
    )

    pcode = _norm_upper(project_code)
    if pcode:
        query = query.filter(Correspondence.project_code == pcode)

    icode = _norm_upper(issuing_code)
    if icode:
        query = query.filter(Correspondence.issuing_code == icode)

    ccode = _norm_upper(category_code)
    if ccode:
        query = query.filter(Correspondence.category_code == ccode)

    dcode = _norm_upper(discipline_code)
    if dcode:
        query = query.filter(Correspondence.discipline_code == dcode)

    if tag_id is not None and int(tag_id or 0) > 0:
        query = query.join(
            CorrespondenceTagAssignment,
            CorrespondenceTagAssignment.correspondence_id == Correspondence.id,
        ).filter(CorrespondenceTagAssignment.tag_id == int(tag_id))

    dtype = _norm(doc_type)
    if dtype:
        query = query.filter(Correspondence.doc_type.ilike(dtype))

    dvalue = _norm(direction)
    if dvalue:
        query = query.filter(Correspondence.direction.ilike(dvalue))

    svalue = _norm(status)
    if svalue:
        query = query.filter(Correspondence.status.ilike(svalue))

    search_value = _norm(search)
    if search_value:
        pattern = f"%{search_value}%"
        query = query.filter(
            or_(
                Correspondence.reference_no.ilike(pattern),
                Correspondence.subject.ilike(pattern),
                Correspondence.sender.ilike(pattern),
                Correspondence.recipient.ilike(pattern),
            )
        )

    from_dt = _parse_filter_date(date_from, "date_from")
    to_dt = _parse_filter_date(date_to, "date_to")
    if from_dt and to_dt and from_dt > to_dt:
        raise HTTPException(status_code=400, detail="`date_from` must be earlier than or equal to `date_to`.")
    if from_dt:
        query = query.filter(Correspondence.corr_date >= from_dt)
    if to_dt:
        query = query.filter(Correspondence.corr_date < (to_dt + timedelta(days=1)))

    total = query.count()
    rows = (
        query.order_by(Correspondence.corr_date.desc(), Correspondence.id.desc())
        .offset(max(0, skip))
        .limit(max(1, min(limit, 200)))
        .all()
    )

    correspondence_ids = [int(row.id) for row in rows]
    action_counts, open_action_counts, attachment_counts = _counts_for_rows(db, correspondence_ids)
    data = [
        _serialize_correspondence(
            row,
            action_counts=action_counts,
            open_action_counts=open_action_counts,
            attachment_counts=attachment_counts,
        )
        for row in rows
    ]
    return {"ok": True, "total": total, "data": data}


@router.get("/reports/table")
def report_correspondence_table(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    date_start: Optional[str] = Query(default=None),
    date_end: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    query = db.query(Correspondence)
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=Correspondence.project_code,
    )
    query = query.options(
        selectinload(Correspondence.issuing_entity),
        selectinload(Correspondence.category),
        selectinload(Correspondence.tag_assignments).selectinload(CorrespondenceTagAssignment.tag),
    )

    pcode = _norm_upper(project_code)
    if pcode:
        query = query.filter(Correspondence.project_code == pcode)

    dcode = _norm_upper(discipline_code)
    if dcode:
        query = query.filter(Correspondence.discipline_code == dcode)

    svalue = _norm(status or status_code)
    if svalue:
        query = query.filter(Correspondence.status.ilike(svalue))

    search_value = _norm(search)
    if search_value:
        pattern = f"%{search_value}%"
        query = query.filter(
            or_(
                Correspondence.reference_no.ilike(pattern),
                Correspondence.subject.ilike(pattern),
                Correspondence.sender.ilike(pattern),
                Correspondence.recipient.ilike(pattern),
            )
        )

    from_dt = _parse_filter_date(date_from or date_start, "date_from")
    to_dt = _parse_filter_date(date_to or date_end, "date_to")
    if from_dt and to_dt and from_dt > to_dt:
        raise HTTPException(status_code=400, detail="`date_from` must be earlier than or equal to `date_to`.")
    if from_dt:
        query = query.filter(Correspondence.corr_date >= from_dt)
    if to_dt:
        query = query.filter(Correspondence.corr_date < (to_dt + timedelta(days=1)))

    now = datetime.utcnow()
    total = query.count()
    rows = (
        query.order_by(Correspondence.corr_date.desc(), Correspondence.id.desc())
        .limit(limit)
        .all()
    )
    row_ids = [int(row.id) for row in rows]
    action_counts, open_action_counts, attachment_counts = _counts_for_rows(db, row_ids)
    data = [
        _serialize_correspondence_report_row(
            row,
            now=now,
            action_counts=action_counts,
            open_action_counts=open_action_counts,
            attachment_counts=attachment_counts,
        )
        for row in rows
    ]
    overdue_count = sum(1 for row in rows if _is_open_correspondence(row) and row.due_date and row.due_date < now)
    open_count = sum(1 for row in rows if _is_open_correspondence(row))
    inbound_count = sum(1 for row in rows if _direction_code(row.direction) == "I")
    outbound_count = sum(1 for row in rows if _direction_code(row.direction) == "O")
    return {
        "ok": True,
        "total": total,
        "count": len(data),
        "summary": {
            "total": total,
            "returned": len(data),
            "open": open_count,
            "overdue": overdue_count,
            "inbound": inbound_count,
            "outbound": outbound_count,
            "open_actions": sum(int(open_action_counts.get(int(row.id), 0)) for row in rows),
            "attachments": sum(int(attachment_counts.get(int(row.id), 0)) for row in rows),
        },
        "data": data,
    }


@router.get("/suggestions")
def suggest_correspondence(
    q: Optional[str] = None,
    limit: int = 8,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    search_value = _norm(q)
    if len(search_value) < 2:
        return {"ok": True, "items": []}
    pattern = f"%{search_value}%"
    query = db.query(Correspondence)
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=Correspondence.project_code,
    )
    rows = (
        query.filter(
            or_(
                Correspondence.reference_no.ilike(pattern),
                Correspondence.subject.ilike(pattern),
                Correspondence.sender.ilike(pattern),
                Correspondence.recipient.ilike(pattern),
            )
        )
        .order_by(Correspondence.corr_date.desc(), Correspondence.id.desc())
        .limit(max(1, min(int(limit or 8), 20)))
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "id": int(row.id or 0),
                "reference_no": row.reference_no,
                "subject": row.subject,
                "sender": row.sender,
                "recipient": row.recipient,
                "status": row.status,
                "corr_date": row.corr_date.isoformat() if row.corr_date else None,
            }
            for row in rows
        ],
    }


@router.post("/create")
def create_correspondence(
    payload: CorrespondenceCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:create")),
):
    issuing_code = _resolve_issuing_code(payload.issuing_code, payload.project_code)
    issuing = _get_or_create_issuing_entity(
        db,
        issuing_code=issuing_code,
        project_code_hint=payload.project_code,
    )

    category_code = _resolve_category_code(payload.category_code, payload.doc_type)
    _get_or_create_category(db, category_code=category_code)

    project_code = _resolve_project_for_issuing(
        db,
        project_code=payload.project_code,
        issuing=issuing,
    )
    if project_code:
        project = db.query(Project).filter(Project.code == project_code).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    discipline_code = _norm_upper(payload.discipline_code) or None
    if discipline_code:
        discipline = db.query(Discipline).filter(Discipline.code == discipline_code).first()
        if not discipline:
            raise HTTPException(status_code=404, detail="Discipline not found")
    tag_ids = [int(payload.tag_id)] if int(payload.tag_id or 0) > 0 else []
    if tag_ids:
        tag_service.get_tag_or_404(db, tag_ids[0])

    enforce_scope_access(db, user, project_code=project_code)

    doc_type = _norm(payload.doc_type) or "Letter"
    direction = _direction_code(payload.direction)
    corr_date = payload.corr_date or datetime.utcnow()
    manual_reference = _norm(payload.reference_no) or None
    base_data = {
        "project_code": project_code,
        "issuing_code": issuing_code,
        "category_code": category_code,
        "discipline_code": discipline_code,
        "doc_type": doc_type,
        "direction": direction,
        "subject": _norm(payload.subject),
        "sender": _norm(payload.sender) or None,
        "recipient": _norm(payload.recipient) or None,
        "corr_date": corr_date,
        "due_date": payload.due_date,
        "status": _norm(payload.status) or "Open",
        "priority": _norm(payload.priority) or "Normal",
        "notes": _norm(payload.notes) or None,
        "created_by_id": getattr(user, "id", None),
    }

    if _should_auto_reference(
        issuing_code=issuing_code,
        category_code=category_code,
        direction=direction,
        manual_reference=manual_reference,
    ):
        for attempt in range(AUTO_REFERENCE_MAX_RETRIES):
            serial = _next_reference_serial(
                db,
                issuing_code=issuing_code,
                category_code=category_code,
                direction=direction,
                corr_date=corr_date,
            )
            candidate_reference = _build_reference_no(
                issuing_code=issuing_code,
                category_code=category_code,
                direction=direction,
                corr_date=corr_date,
                serial=serial,
            )
            row = Correspondence(reference_no=candidate_reference, **base_data)
            db.add(row)
            try:
                db.flush()
                tag_service.replace_correspondence_tags(
                    db,
                    row,
                    tag_ids=tag_ids,
                    user=user,
                )
                db.commit()
                row = _load_correspondence_with_tags(db, int(row.id or 0))
                return {"ok": True, "data": _serialize_correspondence(row)}
            except IntegrityError as exc:
                db.rollback()
                if _is_reference_unique_violation(exc):
                    if attempt == AUTO_REFERENCE_MAX_RETRIES - 1:
                        raise HTTPException(
                            status_code=409,
                            detail="Failed to allocate a unique reference number. Please retry.",
                        ) from exc
                    continue
                raise
        raise HTTPException(status_code=409, detail="Failed to allocate a unique reference number.")

    row = Correspondence(reference_no=manual_reference, **base_data)
    db.add(row)
    try:
        db.flush()
        tag_service.replace_correspondence_tags(
            db,
            row,
            tag_ids=tag_ids,
            user=user,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_reference_unique_violation(exc):
            raise HTTPException(status_code=409, detail="reference_no already exists") from exc
        raise
    row = _load_correspondence_with_tags(db, int(row.id or 0))
    return {"ok": True, "data": _serialize_correspondence(row)}


@router.put("/{correspondence_id}")
def update_correspondence(
    correspondence_id: int,
    payload: CorrespondenceUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:update")),
):
    row = db.query(Correspondence).filter(Correspondence.id == correspondence_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Correspondence not found")

    enforce_scope_access(db, user, project_code=row.project_code)
    payload_fields = set(getattr(payload, "model_fields_set", set()) or set())

    if payload.issuing_code is not None:
        issuing_code = _norm_upper(payload.issuing_code)
        if not issuing_code:
            raise HTTPException(status_code=400, detail="issuing_code cannot be empty")
        issuing = _get_or_create_issuing_entity(
            db,
            issuing_code=issuing_code,
            project_code_hint=payload.project_code or row.project_code,
        )
        row.issuing_code = issuing_code
        if not _norm_upper(payload.project_code):
            row.project_code = _resolve_project_for_issuing(
                db,
                project_code=row.project_code,
                issuing=issuing,
            )

    if payload.category_code is not None:
        category_code = _norm_upper(payload.category_code)
        if not category_code:
            raise HTTPException(status_code=400, detail="category_code cannot be empty")
        _get_or_create_category(db, category_code=category_code)
        row.category_code = category_code

    if payload.project_code is not None:
        project_code = _norm_upper(payload.project_code)
        if project_code:
            project = db.query(Project).filter(Project.code == project_code).first()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
        row.project_code = project_code

    if payload.discipline_code is not None:
        discipline_code = _norm_upper(payload.discipline_code)
        if discipline_code:
            discipline = db.query(Discipline).filter(Discipline.code == discipline_code).first()
            if not discipline:
                raise HTTPException(status_code=404, detail="Discipline not found")
            row.discipline_code = discipline_code
        else:
            row.discipline_code = None

    if payload.doc_type is not None:
        row.doc_type = _norm(payload.doc_type) or row.doc_type
    if payload.direction is not None:
        row.direction = _direction_code(payload.direction) or row.direction
    if payload.reference_no is not None:
        row.reference_no = _norm(payload.reference_no) or None
    if payload.subject is not None:
        subject_value = _norm(payload.subject)
        if not subject_value:
            raise HTTPException(status_code=400, detail="subject cannot be empty")
        row.subject = subject_value
    if payload.sender is not None:
        row.sender = _norm(payload.sender) or None
    if payload.recipient is not None:
        row.recipient = _norm(payload.recipient) or None
    if payload.corr_date is not None:
        row.corr_date = payload.corr_date
    if payload.due_date is not None:
        row.due_date = payload.due_date
    if payload.status is not None:
        row.status = _norm(payload.status) or row.status
    if payload.priority is not None:
        row.priority = _norm(payload.priority) or row.priority
    if payload.notes is not None:
        row.notes = _norm(payload.notes) or None

    if "tag_id" in payload_fields:
        next_tag_ids = [int(payload.tag_id)] if int(payload.tag_id or 0) > 0 else []
        if next_tag_ids:
            tag_service.get_tag_or_404(db, next_tag_ids[0])
        tag_service.replace_correspondence_tags(
            db,
            row,
            tag_ids=next_tag_ids,
            user=user,
        )

    enforce_scope_access(db, user, project_code=row.project_code)
    db.commit()
    row = _load_correspondence_with_tags(db, int(row.id or 0))
    return {"ok": True, "data": _serialize_correspondence(row)}


@router.get("/{correspondence_id}/preview")
def preview_correspondence_attachment(
    correspondence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    row = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, row)

    attachment = _resolve_correspondence_preview_attachment(row)
    if not attachment:
        raise HTTPException(status_code=404, detail=PREVIEW_UNSUPPORTED_DETAIL)

    file_path = Path(attachment.stored_path)
    if str(attachment.stored_path or "").strip().startswith("webdav://"):
        return _download_webdav_attachment(db, attachment, inline=True)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")

    filename = safe_name(attachment.file_name or f"correspondence-{correspondence_id}")
    media_type = _attachment_preview_media_type(attachment)
    if not media_type:
        raise HTTPException(status_code=415, detail=PREVIEW_UNSUPPORTED_DETAIL)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
        content_disposition_type="inline",
    )


@router.get("/{correspondence_id}/relations")
def list_correspondence_relations(
    correspondence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    corr = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, corr)

    document_query = (
        db.query(DocumentExternalRelation)
        .join(MdrDocument, MdrDocument.id == DocumentExternalRelation.source_document_id)
        .options(selectinload(DocumentExternalRelation.source_document))
        .filter(
            DocumentExternalRelation.target_entity_type == "correspondence",
            DocumentExternalRelation.target_entity_id == int(correspondence_id),
            MdrDocument.deleted_at.is_(None),
        )
    )
    document_query = apply_scope_query_filters(
        document_query,
        db,
        user,
        project_column=MdrDocument.project_code,
        discipline_column=MdrDocument.discipline_code,
    )
    document_rows = (
        document_query.order_by(DocumentExternalRelation.created_at.desc(), DocumentExternalRelation.id.desc())
        .all()
    )

    external_rows = (
        db.query(CorrespondenceExternalRelation)
        .filter(CorrespondenceExternalRelation.correspondence_id == int(correspondence_id))
        .order_by(CorrespondenceExternalRelation.created_at.desc(), CorrespondenceExternalRelation.id.desc())
        .all()
    )
    incoming_correspondence_query = (
        db.query(CorrespondenceExternalRelation, Correspondence)
        .join(Correspondence, Correspondence.id == CorrespondenceExternalRelation.correspondence_id)
        .filter(
            CorrespondenceExternalRelation.target_entity_type == "correspondence",
            CorrespondenceExternalRelation.target_entity_id == str(int(correspondence_id)),
        )
    )
    incoming_correspondence_query = apply_scope_query_filters(
        incoming_correspondence_query,
        db,
        user,
        project_column=Correspondence.project_code,
        discipline_column=Correspondence.discipline_code,
    )
    incoming_correspondence_rows = incoming_correspondence_query.order_by(
        CorrespondenceExternalRelation.created_at.desc(),
        CorrespondenceExternalRelation.id.desc(),
    ).all()

    document_items = [_serialize_document_relation(db, row) for row in document_rows]
    external_items = [_serialize_external_relation(row) for row in external_rows]
    incoming_correspondence_items = [
        _serialize_incoming_correspondence_relation(row, source)
        for row, source in incoming_correspondence_rows
    ]

    document_codes = {
        str(item.get("target_code") or "").strip()
        for item in document_items
        if str(item.get("target_code") or "").strip()
    }
    direct_transmittal_codes = {
        str(row.target_code or "").strip()
        for row in external_rows
        if str(row.target_entity_type or "").lower() == "transmittal"
    }
    inferred_items: list[dict[str, Any]] = []
    if document_codes:
        transmittal_query = (
            db.query(Transmittal)
            .join(TransmittalDoc, TransmittalDoc.transmittal_id == Transmittal.id)
            .filter(TransmittalDoc.document_code.in_(document_codes))
        )
        transmittal_query = apply_scope_query_filters(
            transmittal_query,
            db,
            user,
            project_column=Transmittal.project_code,
        )
        seen: set[str] = set()
        for row in transmittal_query.order_by(Transmittal.created_at.desc()).all():
            code = str(row.id or "").strip()
            if not code or code in seen or code in direct_transmittal_codes:
                continue
            seen.add(code)
            inferred_items.append(_serialize_inferred_transmittal(row, document_codes))

    return {"ok": True, "data": document_items + external_items + incoming_correspondence_items + inferred_items}


@router.post("/{correspondence_id}/relations")
def create_correspondence_relation(
    correspondence_id: int,
    payload: CorrespondenceRelationCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:update")),
):
    corr = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, corr)
    target_type = _normalize_relation_target_type(payload.target_entity_type)
    relation_type = _normalize_relation_type(payload.relation_type)
    notes = _norm(payload.notes) or None

    if target_type == "document":
        document = _resolve_relation_document(
            db,
            target_code=payload.target_code,
            target_entity_id=payload.target_entity_id,
        )
        enforce_scope_access(
            db,
            user,
            project_code=document.project_code,
            discipline_code=document.discipline_code,
        )
        existing = (
            db.query(DocumentExternalRelation)
            .filter(
                DocumentExternalRelation.source_document_id == int(document.id or 0),
                DocumentExternalRelation.target_entity_type == "correspondence",
                DocumentExternalRelation.target_entity_id == int(correspondence_id),
                DocumentExternalRelation.relation_type == relation_type,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Relation already exists")
        row = DocumentExternalRelation(
            source_document_id=int(document.id or 0),
            target_entity_type="correspondence",
            target_entity_id=int(correspondence_id),
            target_code=str(corr.reference_no or f"CORR-{int(corr.id or 0)}"),
            target_title=corr.subject,
            target_project_code=corr.project_code,
            target_status=corr.status,
            relation_type=relation_type,
            notes=notes,
            created_by_id=getattr(user, "id", None),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"ok": True, "data": _serialize_document_relation(db, row)}

    if target_type == "transmittal":
        transmittal = _resolve_relation_transmittal(
            db,
            target_code=payload.target_code,
            target_entity_id=payload.target_entity_id,
        )
        enforce_scope_access(db, user, project_code=transmittal.project_code)
        target = {
            "type": "transmittal",
            "id": str(transmittal.id),
            "code": str(transmittal.id),
            "title": _display_transmittal_title(transmittal),
            "project_code": transmittal.project_code,
            "status": transmittal.lifecycle_status or ("issued" if transmittal.send_date else "draft"),
        }
    elif target_type == "meeting_minute":
        meeting = _resolve_relation_meeting_minute(
            db,
            target_code=payload.target_code,
            target_entity_id=payload.target_entity_id,
        )
        enforce_scope_access(db, user, project_code=meeting.project_code)
        target = {
            "type": "meeting_minute",
            "id": str(int(meeting.id or 0)),
            "code": str(meeting.meeting_no or f"MOM-{int(meeting.id or 0)}"),
            "title": meeting.title,
            "project_code": meeting.project_code,
            "status": meeting.status,
        }
    else:
        target_correspondence = _resolve_relation_correspondence(
            db,
            target_code=payload.target_code,
            target_entity_id=payload.target_entity_id,
        )
        if int(target_correspondence.id or 0) == int(correspondence_id):
            raise HTTPException(status_code=400, detail="Cannot relate a correspondence to itself")
        enforce_scope_access(db, user, project_code=target_correspondence.project_code)
        target = {
            "type": "correspondence",
            "id": str(int(target_correspondence.id or 0)),
            "code": str(target_correspondence.reference_no or f"CORR-{int(target_correspondence.id or 0)}"),
            "title": target_correspondence.subject,
            "project_code": target_correspondence.project_code,
            "status": target_correspondence.status,
        }
    existing_external = (
        db.query(CorrespondenceExternalRelation)
        .filter(
            CorrespondenceExternalRelation.correspondence_id == int(correspondence_id),
            CorrespondenceExternalRelation.target_entity_type == target["type"],
            CorrespondenceExternalRelation.target_entity_id == str(target["id"]),
            CorrespondenceExternalRelation.relation_type == relation_type,
        )
        .first()
    )
    if existing_external:
        raise HTTPException(status_code=409, detail="Relation already exists")
    row = CorrespondenceExternalRelation(
        correspondence_id=int(correspondence_id),
        target_entity_type=str(target["type"]),
        target_entity_id=str(target["id"]),
        target_code=str(target["code"]),
        target_title=target.get("title"),
        target_project_code=target.get("project_code"),
        target_status=target.get("status"),
        relation_type=relation_type,
        notes=notes,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_external_relation(row)}


@router.delete("/{correspondence_id}/relations/{relation_id}")
def delete_correspondence_relation(
    correspondence_id: int,
    relation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:update")),
):
    corr = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, corr)
    key = _norm(relation_id)
    if key.lower().startswith("document_external:"):
        try:
            row_id = int(key.split(":", 1)[1])
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid relation id") from exc
        row = (
            db.query(DocumentExternalRelation)
            .options(selectinload(DocumentExternalRelation.source_document))
            .filter(
                DocumentExternalRelation.id == row_id,
                DocumentExternalRelation.target_entity_type == "correspondence",
                DocumentExternalRelation.target_entity_id == int(correspondence_id),
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Relation not found")
        document = row.source_document
        if document:
            enforce_scope_access(
                db,
                user,
                project_code=document.project_code,
                discipline_code=document.discipline_code,
            )
        db.delete(row)
        db.commit()
        return {"ok": True, "id": key}

    if key.lower().startswith("external:"):
        try:
            row_id = int(key.split(":", 1)[1])
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid relation id") from exc
        row = (
            db.query(CorrespondenceExternalRelation)
            .filter(
                CorrespondenceExternalRelation.id == row_id,
                CorrespondenceExternalRelation.correspondence_id == int(correspondence_id),
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Relation not found")
        db.delete(row)
        db.commit()
        return {"ok": True, "id": key}

    raise HTTPException(status_code=400, detail="Invalid relation id")


@router.delete("/{correspondence_id}")
def delete_correspondence(
    correspondence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:delete")),
):
    row = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, row)

    stored_paths = [
        str(attachment.stored_path)
        for attachment in list(row.attachments or [])
        if _norm(attachment.stored_path)
    ]
    attachment_ids = [int(attachment.id or 0) for attachment in list(row.attachments or []) if int(attachment.id or 0) > 0]
    if attachment_ids:
        db.query(OpenProjectLink).filter(
            OpenProjectLink.entity_type == ENTITY_CORRESPONDENCE_ATTACHMENT,
            OpenProjectLink.entity_id.in_(attachment_ids),
        ).delete(synchronize_session=False)
    db.delete(row)
    db.commit()

    for stored_path in stored_paths:
        _delete_stored_attachment_file(db, stored_path)

    return {"ok": True, "id": correspondence_id}


@router.get("/{correspondence_id}/actions")
def list_correspondence_actions(
    correspondence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    corr = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, corr)
    rows = (
        db.query(CorrespondenceAction)
        .filter(CorrespondenceAction.correspondence_id == correspondence_id)
        .order_by(CorrespondenceAction.created_at.desc(), CorrespondenceAction.id.desc())
        .all()
    )
    return {"ok": True, "data": [_serialize_action(row) for row in rows]}


@router.post("/{correspondence_id}/actions")
def create_correspondence_action(
    correspondence_id: int,
    payload: CorrespondenceActionCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:create")),
):
    corr = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, corr)

    actor_id = getattr(user, "id", None)
    to_user_id = _validated_user_id_or_none(db, payload.to_user_id)
    is_closed = bool(payload.is_closed)
    row = CorrespondenceAction(
        correspondence_id=correspondence_id,
        action_type=_norm(payload.action_type) or "task",
        title=_norm(payload.title) or None,
        description=_norm(payload.description) or None,
        from_user_id=actor_id,
        to_user_id=to_user_id,
        due_date=payload.due_date,
        status=_norm(payload.status) or "Open",
        is_closed=is_closed,
        closed_at=(datetime.utcnow() if is_closed else None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_action(row)}


@router.put("/actions/{action_id}")
def update_correspondence_action(
    action_id: int,
    payload: CorrespondenceActionUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:update")),
):
    row = _load_action_or_404(db, action_id)
    corr = _load_correspondence_or_404(db, row.correspondence_id)
    _enforce_corr_scope(db, user, corr)

    if payload.action_type is not None:
        row.action_type = _norm(payload.action_type) or row.action_type
    if payload.title is not None:
        row.title = _norm(payload.title) or None
    if payload.description is not None:
        row.description = _norm(payload.description) or None
    if payload.to_user_id is not None:
        row.to_user_id = _validated_user_id_or_none(db, payload.to_user_id)
    if payload.due_date is not None:
        row.due_date = payload.due_date
    if payload.status is not None:
        row.status = _norm(payload.status) or row.status
    if payload.is_closed is not None:
        row.is_closed = bool(payload.is_closed)
        row.closed_at = datetime.utcnow() if row.is_closed else None

    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_action(row)}


@router.delete("/actions/{action_id}")
def delete_correspondence_action(
    action_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:delete")),
):
    row = _load_action_or_404(db, action_id)
    corr = _load_correspondence_or_404(db, row.correspondence_id)
    _enforce_corr_scope(db, user, corr)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/{correspondence_id}/attachments")
def list_correspondence_attachments(
    correspondence_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    corr = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, corr)
    rows = (
        db.query(CorrespondenceAttachment)
        .filter(CorrespondenceAttachment.correspondence_id == correspondence_id)
        .filter(CorrespondenceAttachment.deleted_at.is_(None))
        .order_by(CorrespondenceAttachment.uploaded_at.desc(), CorrespondenceAttachment.id.desc())
        .all()
    )
    status_map, fallback_status = _attachment_openproject_status_map(
        db, [int(row.id or 0) for row in rows]
    )
    return {
        "ok": True,
        "data": [
            _serialize_attachment(
                row,
                openproject_payload=_attachment_openproject_payload(
                    status_map, fallback_status, int(row.id or 0)
                ),
            )
            for row in rows
        ],
    }


@router.post("/{correspondence_id}/attachments/upload")
def upload_correspondence_attachment(
    correspondence_id: int,
    file: UploadFile = File(...),
    file_kind: str = Form("attachment"),
    openproject_work_package_id: Optional[int] = Form(default=None),
    action_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:create")),
):
    corr = _load_correspondence_or_404(db, correspondence_id)
    _enforce_corr_scope(db, user, corr)

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")
    normalized_kind = _attachment_kind(file_kind)

    linked_action_id: int | None = None
    if action_id is not None:
        action = _load_action_or_404(db, action_id)
        if int(action.correspondence_id) != int(correspondence_id):
            raise HTTPException(status_code=400, detail="Action does not belong to this correspondence")
        linked_action_id = action.id

    original_name = safe_name(file.filename)
    storage_manager = StorageManager(db)

    if storage_manager._is_webdav_primary_mode():
        # WebDAV mode: use correspondence_storage_path as base and relativize to root
        integrations = get_storage_integrations(db)
        runtime = resolve_nextcloud_runtime(integrations)
        root_path = str(runtime.get("root_path") or "")

        # Get correspondence base from settings (e.g., "/ARCA-NTN/Correspondence")
        corr_base = storage_manager.get_correspondence_webdav_base()

        # Build path structure (same as _corr_storage_dir but for WebDAV)
        issuing = safe_name(corr.issuing_code or "GENERAL")
        category = _corr_category_folder(corr)
        direction = _corr_direction_folder(corr)
        ref = safe_name(corr.reference_no or f"CORR-{corr.id}")
        kind_folder = _correspondence_bucket_for_kind(normalized_kind)

        # Generate unique filename for WebDAV
        remote_folder = f"{corr_base}/{issuing}/{category}/{direction}/{ref}/{kind_folder}"
        stored_name = _corr_storage_file_name(
            db,
            corr,
            file_kind=normalized_kind,
            original_name=original_name,
            folder=Path(remote_folder),  # dummy Path for compatibility
            storage_manager=storage_manager,
        )

        # Build complete absolute path
        absolute_path = f"{remote_folder}/{stored_name}"

        # Relativize to root (e.g., "/ARCA-NTN/Correspondence/..." → "/Correspondence/...")
        relative_path = StorageManager.relativize_webdav_path(absolute_path, root_path)

        saved = storage_manager.save_upload_to_webdav(
            file=file,
            remote_relative_path=relative_path,
            file_kind="attachment",
        )
        stored_path = saved.stored_path
    else:
        # Mount/local mode: use existing logic
        folder = _corr_storage_dir(db, corr, normalized_kind)
        stored_name = _corr_storage_file_name(
            db,
            corr,
            file_kind=normalized_kind,
            original_name=original_name,
            folder=folder,
            storage_manager=storage_manager,
        )
        saved = storage_manager.save_upload_secure(
            file=file,
            destination_folder=str(folder),
            new_name=stored_name,
            file_kind="attachment",
        )
        stored_path = str(Path(saved.stored_path))

    integrations = get_storage_integrations(db)
    mirror_plan = resolve_mirror_enqueue_plan(integrations)
    mirror_provider = str(mirror_plan.get("provider") or "")
    mirror_status = str(mirror_plan.get("status") or "disabled")

    row = CorrespondenceAttachment(
        correspondence_id=correspondence_id,
        action_id=linked_action_id,
        file_name=stored_name,
        stored_path=stored_path,
        file_kind=normalized_kind,
        mime_type=saved.declared_mime or _norm(file.content_type) or None,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        storage_backend=storage_manager.resolve_storage_backend_for_path(saved.stored_path),
        gdrive_file_id=None,
        mirror_provider=mirror_provider or None,
        mirror_remote_id=None,
        mirror_remote_url=None,
        mirror_status=mirror_status,
        mirror_updated_at=datetime.utcnow(),
        uploaded_by_id=getattr(user, "id", None),
    )
    db.add(row)
    db.flush()
    if bool(mirror_plan.get("enqueue")):
        enqueue_correspondence_mirror_job(
            db,
            attachment_id=row.id,
            work_package_id=openproject_work_package_id,
        )
    db.commit()
    db.refresh(row)
    status_map, fallback_status = _attachment_openproject_status_map(db, [int(row.id or 0)])
    return {
        "ok": True,
        "data": _serialize_attachment(
            row,
            openproject_payload=_attachment_openproject_payload(
                status_map, fallback_status, int(row.id or 0)
            ),
        ),
    }


@router.get("/attachments/{attachment_id}/download")
def download_correspondence_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    row = _load_attachment_or_404(db, attachment_id)
    corr = _load_correspondence_or_404(db, row.correspondence_id)
    _enforce_corr_scope(db, user, corr)

    if str(row.stored_path or "").strip().startswith("webdav://"):
        return _download_webdav_attachment(db, row)
    file_path = Path(row.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path=str(file_path), filename=row.file_name, media_type=row.mime_type)


@router.get("/attachments/{attachment_id}/preview")
def preview_correspondence_attachment_by_id(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:read")),
):
    row = _load_attachment_or_404(db, attachment_id)
    corr = _load_correspondence_or_404(db, row.correspondence_id)
    _enforce_corr_scope(db, user, corr)
    if not _attachment_preview_supported(row):
        raise HTTPException(status_code=415, detail=PREVIEW_UNSUPPORTED_DETAIL)
    if str(row.stored_path or "").strip().startswith("webdav://"):
        return _download_webdav_attachment(db, row, inline=True)
    file_path = Path(row.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    filename = safe_name(row.file_name or f"attachment-{attachment_id}") or f"attachment-{attachment_id}"
    media_type = _attachment_preview_media_type(row)
    if not media_type:
        raise HTTPException(status_code=415, detail=PREVIEW_UNSUPPORTED_DETAIL)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
        content_disposition_type="inline",
    )


@router.delete("/attachments/{attachment_id}")
def delete_correspondence_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:delete")),
):
    row = _load_attachment_or_404(db, attachment_id)
    corr = _load_correspondence_or_404(db, row.correspondence_id)
    _enforce_corr_scope(db, user, corr)

    db.delete(row)
    db.commit()
    _delete_stored_attachment_file(db, str(row.stored_path or ""))
    return {"ok": True}
