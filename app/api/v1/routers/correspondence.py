from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
    Discipline,
    IssuingEntity,
    Project,
)
from app.services.folder_service import safe_name
from app.services.openproject_status import (
    ENTITY_CORRESPONDENCE_ATTACHMENT,
    default_openproject_sync_status,
    get_openproject_status_map,
    is_openproject_integration_enabled,
)
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import enqueue_correspondence_mirror_job, resolve_mirror_enqueue_plan

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


def _attachment_kind(value: Optional[str]) -> str:
    kind = _norm(value).lower()
    if kind in {"letter", "original", "attachment"}:
        return kind
    return "attachment"


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


def _load_action_or_404(db: Session, action_id: int) -> CorrespondenceAction:
    row = db.query(CorrespondenceAction).filter(CorrespondenceAction.id == action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    return row


def _load_attachment_or_404(db: Session, attachment_id: int) -> CorrespondenceAttachment:
    row = db.query(CorrespondenceAttachment).filter(CorrespondenceAttachment.id == attachment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return row


def _enforce_corr_scope(db: Session, user: User, row: Correspondence) -> None:
    enforce_scope_access(
        db,
        user,
        project_code=row.project_code,
        discipline_code=row.discipline_code,
    )


def _corr_storage_dir(db: Session, row: Correspondence, file_kind: str) -> Path:
    base = StorageManager(db).get_correspondence_base_path()
    issuing = safe_name(row.issuing_code or "GENERAL")
    ref = safe_name(row.reference_no or f"CORR-{row.id}")
    kind_folder = {
        "letter": "Letter",
        "original": "Original",
        "attachment": "Attachment",
    }.get(file_kind, "Attachment")
    path = base / issuing / ref / kind_folder
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
            .filter(CorrespondenceAttachment.correspondence_id.in_(correspondence_ids))
            .group_by(CorrespondenceAttachment.correspondence_id)
            .all()
        )
    }
    return action_counts, open_action_counts, attachment_counts


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
        "actions_count": int(action_counts.get(int(row.id), 0)),
        "open_actions_count": int(open_action_counts.get(int(row.id), 0)),
        "attachments_count": int(attachment_counts.get(int(row.id), 0)),
    }


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
        discipline_column=Correspondence.discipline_code,
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
        discipline_column=Correspondence.discipline_code,
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
        discipline_column=Correspondence.discipline_code,
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

    enforce_scope_access(
        db,
        user,
        project_code=project_code,
        discipline_code=discipline_code,
    )

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
                db.commit()
                db.refresh(row)
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
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_reference_unique_violation(exc):
            raise HTTPException(status_code=409, detail="reference_no already exists") from exc
        raise
    db.refresh(row)
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

    enforce_scope_access(
        db,
        user,
        project_code=row.project_code,
        discipline_code=row.discipline_code,
    )

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

    enforce_scope_access(
        db,
        user,
        project_code=row.project_code,
        discipline_code=row.discipline_code,
    )
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_correspondence(row)}


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

    now = datetime.utcnow()
    original_name = safe_name(file.filename)
    unique_name = safe_name(f"{now.strftime('%Y%m%d%H%M%S%f')}_{original_name}")
    folder = _corr_storage_dir(db, corr, normalized_kind)
    storage_manager = StorageManager(db)
    saved = storage_manager.save_upload_secure(
        file=file,
        destination_folder=str(folder),
        new_name=unique_name,
        file_kind="attachment",
    )
    path_obj = Path(saved.stored_path)

    integrations = get_storage_integrations(db)
    mirror_plan = resolve_mirror_enqueue_plan(integrations)
    mirror_provider = str(mirror_plan.get("provider") or "")
    mirror_status = str(mirror_plan.get("status") or "disabled")

    row = CorrespondenceAttachment(
        correspondence_id=correspondence_id,
        action_id=linked_action_id,
        file_name=original_name,
        stored_path=str(path_obj),
        file_kind=normalized_kind,
        mime_type=saved.declared_mime or _norm(file.content_type) or None,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        storage_backend="local",
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

    file_path = Path(row.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path=str(file_path), filename=row.file_name, media_type=row.mime_type)


@router.delete("/attachments/{attachment_id}")
def delete_correspondence_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("correspondence:delete")),
):
    row = _load_attachment_or_404(db, attachment_id)
    corr = _load_correspondence_or_404(db, row.correspondence_id)
    _enforce_corr_scope(db, user, corr)

    file_path = Path(row.stored_path)
    db.delete(row)
    db.commit()

    try:
        if file_path.exists():
            os.remove(file_path)
    except Exception:
        pass
    return {"ok": True}
