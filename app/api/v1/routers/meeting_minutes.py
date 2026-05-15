from __future__ import annotations

from datetime import datetime, timedelta
from html import escape as html_escape
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_
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
    CorrespondenceExternalRelation,
    DocumentExternalRelation,
    DocumentRevision,
    MdrDocument,
    MeetingMinute,
    MeetingMinuteAttachment,
    MeetingMinuteExternalRelation,
    MeetingMinuteSequence,
    MeetingResolution,
    Organization,
    Project,
    User as DbUser,
)
from app.services.folder_service import safe_name
from app.services.nextcloud_adapter import NextcloudAdapter
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import resolve_nextcloud_runtime


router = APIRouter(prefix="/meeting-minutes", tags=["Meeting Minutes"])

MINUTE_STATUS_LABELS = {
    "draft": "Draft",
    "open": "Open",
    "closed": "Closed",
    "cancelled": "Cancelled",
}
RESOLUTION_STATUS_LABELS = {
    "open": "Open",
    "in progress": "In Progress",
    "in_progress": "In Progress",
    "done": "Done",
    "cancelled": "Cancelled",
}
RESOLUTION_TERMINAL_STATUSES = {"done", "cancelled"}
PRIORITY_LABELS = {
    "low": "Low",
    "normal": "Normal",
    "medium": "Normal",
    "high": "High",
    "critical": "Critical",
}
MEETING_NO_SERIAL_WIDTH = 4
MEETING_RELATION_TYPES = {"related", "references", "parent", "child"}
MEETING_RELATION_TARGET_LABELS = {
    "document": "مدرک",
    "correspondence": "مکاتبه",
    "meeting_minute": "صورتجلسه",
}


class MeetingMinuteCreateIn(BaseModel):
    meeting_no: Optional[str] = Field(default=None, max_length=120)
    title: str = Field(..., min_length=1)
    project_code: Optional[str] = Field(default=None, max_length=50)
    meeting_type: str = Field(default="General", min_length=1, max_length=64)
    meeting_date: Optional[datetime] = None
    location: Optional[str] = Field(default=None, max_length=255)
    chairperson: Optional[str] = Field(default=None, max_length=255)
    secretary: Optional[str] = Field(default=None, max_length=255)
    participants: Optional[str] = None
    status: str = Field(default="Open", min_length=1, max_length=20)
    summary: Optional[str] = None
    notes: Optional[str] = None


class MeetingMinuteUpdateIn(BaseModel):
    meeting_no: Optional[str] = Field(default=None, max_length=120)
    title: Optional[str] = None
    project_code: Optional[str] = Field(default=None, max_length=50)
    meeting_type: Optional[str] = Field(default=None, max_length=64)
    meeting_date: Optional[datetime] = None
    location: Optional[str] = Field(default=None, max_length=255)
    chairperson: Optional[str] = Field(default=None, max_length=255)
    secretary: Optional[str] = Field(default=None, max_length=255)
    participants: Optional[str] = None
    status: Optional[str] = Field(default=None, max_length=20)
    summary: Optional[str] = None
    notes: Optional[str] = None


class MeetingResolutionCreateIn(BaseModel):
    resolution_no: Optional[str] = Field(default=None, max_length=64)
    description: str = Field(..., min_length=1)
    responsible_user_id: Optional[int] = Field(default=None, ge=1)
    responsible_org_id: Optional[int] = Field(default=None, ge=1)
    responsible_name: Optional[str] = Field(default=None, max_length=255)
    due_date: Optional[datetime] = None
    status: str = Field(default="Open", min_length=1, max_length=20)
    priority: str = Field(default="Normal", min_length=1, max_length=20)
    sort_order: int = 0


class MeetingResolutionUpdateIn(BaseModel):
    resolution_no: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    responsible_user_id: Optional[int] = Field(default=None, ge=1)
    responsible_org_id: Optional[int] = Field(default=None, ge=1)
    responsible_name: Optional[str] = Field(default=None, max_length=255)
    due_date: Optional[datetime] = None
    status: Optional[str] = Field(default=None, max_length=20)
    priority: Optional[str] = Field(default=None, max_length=20)
    sort_order: Optional[int] = None


class MeetingRelationCreateIn(BaseModel):
    target_entity_type: str = Field(default="document", min_length=1, max_length=32)
    target_code: Optional[str] = Field(default=None, max_length=128)
    target_entity_id: Optional[str] = Field(default=None, max_length=128)
    relation_type: Optional[str] = Field(default="related", max_length=32)
    notes: Optional[str] = None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_filter_date(value: Optional[str], field_name: str) -> Optional[datetime]:
    raw = _norm(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(raw, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid `{field_name}` format (YYYY-MM-DD expected).",
            ) from exc


def _meeting_period(value: datetime | None) -> str:
    dt = value or datetime.utcnow()
    return dt.strftime("%y%m")


def _meeting_project_key(project_code: Optional[str]) -> str:
    return _upper(project_code) or "GEN"


def _meeting_no_prefix(project_code: Optional[str], meeting_date: datetime | None) -> str:
    return f"{_meeting_project_key(project_code)}-MOM-{_meeting_period(meeting_date)}-"


def _extract_meeting_serial(meeting_no: str, prefix: str) -> int | None:
    value = _norm(meeting_no)
    if not value.startswith(prefix):
        return None
    suffix = value[len(prefix):]
    if not suffix.isdigit():
        return None
    try:
        return int(suffix)
    except Exception:
        return None


def _existing_meeting_serial_max(db: Session, *, project_key: str, period: str) -> int:
    prefix = f"{project_key}-MOM-{period}-"
    rows = (
        db.query(MeetingMinute.meeting_no)
        .filter(
            MeetingMinute.deleted_at.is_(None),
            MeetingMinute.meeting_no.like(f"{prefix}%"),
        )
        .all()
    )
    max_value = 0
    for (meeting_no,) in rows:
        serial = _extract_meeting_serial(str(meeting_no or ""), prefix)
        if serial is not None:
            max_value = max(max_value, serial)
    return max_value


def _build_meeting_no(project_key: str, period: str, serial: int) -> str:
    return f"{project_key}-MOM-{period}-{int(serial):0{MEETING_NO_SERIAL_WIDTH}d}"


def _next_meeting_no(db: Session, *, project_code: Optional[str], meeting_date: datetime | None, consume: bool) -> dict[str, Any]:
    project_key = _meeting_project_key(project_code)
    period = _meeting_period(meeting_date)
    seq = (
        db.query(MeetingMinuteSequence)
        .filter(
            MeetingMinuteSequence.project_code == project_key,
            MeetingMinuteSequence.period == period,
        )
        .with_for_update()
        .first()
    )
    serial = int(getattr(seq, "next_value", None) or 1)
    serial = max(serial, _existing_meeting_serial_max(db, project_key=project_key, period=period) + 1)
    meeting_no = _build_meeting_no(project_key, period, serial)
    while db.query(MeetingMinute.id).filter(
        func.lower(MeetingMinute.meeting_no) == meeting_no.lower(),
        MeetingMinute.deleted_at.is_(None),
    ).first():
        serial += 1
        meeting_no = _build_meeting_no(project_key, period, serial)
    if consume:
        if seq:
            seq.next_value = serial + 1
            seq.updated_at = datetime.utcnow()
        else:
            db.add(
                MeetingMinuteSequence(
                    project_code=project_key,
                    period=period,
                    next_value=serial + 1,
                    updated_at=datetime.utcnow(),
                )
            )
    return {
        "meeting_no": meeting_no,
        "project_code": project_key,
        "period": period,
        "next_serial": serial,
    }


def _gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    gy = year - 1600
    gm = month - 1
    gd = day - 1
    g_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    for i in range(gm):
        g_day_no += g_days_in_month[i]
    if gm > 1 and ((gy + 1600) % 4 == 0 and ((gy + 1600) % 100 != 0 or (gy + 1600) % 400 == 0)):
        g_day_no += 1
    g_day_no += gd
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    jm = 0
    while jm < 11 and j_day_no >= j_days_in_month[jm]:
        j_day_no -= j_days_in_month[jm]
        jm += 1
    return jy, jm + 1, j_day_no + 1


def _format_jalali_date(value: Any) -> str:
    if not value:
        return "-"
    dt = value if isinstance(value, datetime) else None
    if dt is None:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return str(value)[:10]
    jy, jm, jd = _gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def _normalize_minute_status(value: Any) -> str:
    key = _lower(value).replace("_", " ")
    return MINUTE_STATUS_LABELS.get(key, "Open")


def _normalize_resolution_status(value: Any) -> str:
    key = _lower(value).replace("_", " ")
    return RESOLUTION_STATUS_LABELS.get(key, "Open")


def _normalize_priority(value: Any) -> str:
    key = _lower(value).replace("_", " ")
    return PRIORITY_LABELS.get(key, "Normal")


def _is_resolution_open(status_value: Any) -> bool:
    return _lower(status_value).replace("_", " ") not in RESOLUTION_TERMINAL_STATUSES


def _today_start() -> datetime:
    now = datetime.utcnow()
    return datetime(year=now.year, month=now.month, day=now.day)


def _is_resolution_overdue(row: MeetingResolution) -> bool:
    return bool(row.due_date and row.due_date < _today_start() and _is_resolution_open(row.status))


def _attachment_kind(value: Any) -> str:
    kind = _lower(value).replace("-", "_")
    if kind in {"main", "primary"}:
        return "main"
    return "attachment"


def _project_or_none(db: Session, project_code: Optional[str]) -> str | None:
    project = _upper(project_code)
    if not project:
        return None
    if not db.query(Project.code).filter(Project.code == project).first():
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _validated_user_id_or_none(db: Session, user_id: Optional[int]) -> int | None:
    if user_id is None:
        return None
    if int(user_id or 0) <= 0:
        raise HTTPException(status_code=400, detail="Invalid responsible_user_id")
    if not db.query(DbUser.id).filter(DbUser.id == int(user_id)).first():
        raise HTTPException(status_code=404, detail="Responsible user not found")
    return int(user_id)


def _validated_org_id_or_none(db: Session, org_id: Optional[int]) -> int | None:
    if org_id is None:
        return None
    if int(org_id or 0) <= 0:
        raise HTTPException(status_code=400, detail="Invalid responsible_org_id")
    if not db.query(Organization.id).filter(Organization.id == int(org_id)).first():
        raise HTTPException(status_code=404, detail="Responsible organization not found")
    return int(org_id)


def _ensure_unique_active_meeting_no(db: Session, meeting_no: str, *, exclude_id: int | None = None) -> None:
    query = db.query(MeetingMinute.id).filter(
        func.lower(MeetingMinute.meeting_no) == _lower(meeting_no),
        MeetingMinute.deleted_at.is_(None),
    )
    if exclude_id is not None:
        query = query.filter(MeetingMinute.id != int(exclude_id))
    if query.first():
        raise HTTPException(status_code=409, detail="meeting_no already exists")


def _base_minute_query(db: Session):
    return db.query(MeetingMinute).filter(MeetingMinute.deleted_at.is_(None))


def _load_minute_or_404(db: Session, minute_id: int) -> MeetingMinute:
    row = (
        db.query(MeetingMinute)
        .options(
            selectinload(MeetingMinute.resolutions),
            selectinload(MeetingMinute.attachments),
        )
        .filter(MeetingMinute.id == int(minute_id), MeetingMinute.deleted_at.is_(None))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Meeting minute not found")
    return row


def _load_resolution_or_404(db: Session, resolution_id: int) -> MeetingResolution:
    row = (
        db.query(MeetingResolution)
        .filter(
            MeetingResolution.id == int(resolution_id),
            MeetingResolution.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Resolution not found")
    return row


def _load_attachment_or_404(db: Session, attachment_id: int) -> MeetingMinuteAttachment:
    row = (
        db.query(MeetingMinuteAttachment)
        .filter(
            MeetingMinuteAttachment.id == int(attachment_id),
            MeetingMinuteAttachment.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return row


def _active_resolutions(row: MeetingMinute) -> list[MeetingResolution]:
    return [item for item in list(row.resolutions or []) if item.deleted_at is None]


def _active_attachments(row: MeetingMinute) -> list[MeetingMinuteAttachment]:
    return [item for item in list(row.attachments or []) if item.deleted_at is None]


def _serialize_resolution(row: MeetingResolution) -> dict[str, Any]:
    responsible_user = getattr(row, "responsible_user", None)
    responsible_org = getattr(row, "responsible_org", None)
    attachment_count = len(
        [item for item in list(row.attachments or []) if item.deleted_at is None]
    )
    return {
        "id": row.id,
        "meeting_minute_id": row.meeting_minute_id,
        "resolution_no": row.resolution_no,
        "description": row.description,
        "responsible_user_id": row.responsible_user_id,
        "responsible_user_name": getattr(responsible_user, "full_name", None),
        "responsible_org_id": row.responsible_org_id,
        "responsible_org_name": getattr(responsible_org, "name", None),
        "responsible_name": row.responsible_name,
        "due_date": _to_iso(row.due_date),
        "status": row.status,
        "priority": row.priority,
        "sort_order": int(row.sort_order or 0),
        "is_overdue": _is_resolution_overdue(row),
        "attachment_count": attachment_count,
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _serialize_attachment(row: MeetingMinuteAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "meeting_minute_id": row.meeting_minute_id,
        "resolution_id": row.resolution_id,
        "file_name": row.file_name,
        "file_kind": _attachment_kind(row.file_kind),
        "mime_type": row.mime_type,
        "detected_mime": row.detected_mime,
        "validation_status": row.validation_status,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "storage_backend": row.storage_backend,
        "uploaded_by_id": row.uploaded_by_id,
        "uploaded_by_name": getattr(getattr(row, "uploaded_by", None), "full_name", None),
        "uploaded_at": _to_iso(row.uploaded_at),
    }


def _latest_document_revision(db: Session, document_id: int) -> DocumentRevision | None:
    return (
        db.query(DocumentRevision)
        .filter(DocumentRevision.document_id == int(document_id))
        .order_by(DocumentRevision.created_at.desc(), DocumentRevision.id.desc())
        .first()
    )


def _normalize_relation_target_type(value: Any) -> str:
    raw = _lower(value).replace("-", "_")
    aliases = {
        "doc": "document",
        "mdr": "document",
        "mdr_document": "document",
        "document": "document",
        "corr": "correspondence",
        "correspondence": "correspondence",
        "letter": "correspondence",
        "mail": "correspondence",
    }
    normalized = aliases.get(raw)
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid relation target type")
    return normalized


def _normalize_relation_type(value: Any) -> str:
    normalized = _lower(value) or "related"
    if normalized not in MEETING_RELATION_TYPES:
        raise HTTPException(status_code=400, detail="Invalid relation type")
    return normalized


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


def _target_label(entity_type: Any) -> str:
    return MEETING_RELATION_TARGET_LABELS.get(_lower(entity_type), _norm(entity_type) or "-")


def _serialize_meeting_relation(row: MeetingMinuteExternalRelation, *, direction: str = "outgoing") -> dict[str, Any]:
    target_type = _lower(row.target_entity_type)
    return {
        "id": f"external:{int(row.id or 0)}",
        "relation_id": int(row.id or 0),
        "meeting_minute_id": int(row.meeting_minute_id or 0),
        "target_entity_type": target_type,
        "target_entity_id": row.target_entity_id,
        "target_code": row.target_code,
        "target_label": _target_label(target_type),
        "target_title": row.target_title,
        "target_project_code": row.target_project_code,
        "target_status": row.target_status,
        "relation_type": row.relation_type,
        "notes": row.notes,
        "created_at": _to_iso(row.created_at),
        "direction": direction,
    }


def _serialize_document_incoming_relation(db: Session, row: DocumentExternalRelation) -> dict[str, Any]:
    document = row.source_document
    revision = _latest_document_revision(db, int(getattr(document, "id", 0) or row.source_document_id or 0)) if document else None
    return {
        "id": f"document_external:{int(row.id or 0)}",
        "relation_id": int(row.id or 0),
        "target_entity_type": "document",
        "target_entity_id": int(getattr(document, "id", 0) or row.source_document_id or 0),
        "target_code": getattr(document, "doc_number", None),
        "target_label": _target_label("document"),
        "target_title": (
            getattr(document, "doc_title_p", None)
            or getattr(document, "doc_title_e", None)
            or getattr(document, "subject", None)
        ),
        "target_project_code": getattr(document, "project_code", None),
        "target_status": getattr(revision, "status", None),
        "relation_type": row.relation_type,
        "notes": row.notes,
        "created_at": _to_iso(row.created_at),
        "direction": "incoming",
    }


def _serialize_correspondence_incoming_relation(row: CorrespondenceExternalRelation, correspondence: Correspondence | None) -> dict[str, Any]:
    return {
        "id": f"correspondence_external:{int(row.id or 0)}",
        "relation_id": int(row.id or 0),
        "target_entity_type": "correspondence",
        "target_entity_id": int(getattr(correspondence, "id", 0) or 0),
        "target_code": getattr(correspondence, "reference_no", None) or row.target_code,
        "target_label": _target_label("correspondence"),
        "target_title": getattr(correspondence, "subject", None) or row.target_title,
        "target_project_code": getattr(correspondence, "project_code", None) or row.target_project_code,
        "target_status": getattr(correspondence, "status", None) or row.target_status,
        "relation_type": row.relation_type,
        "notes": row.notes,
        "created_at": _to_iso(row.created_at),
        "direction": "incoming",
    }


def _counts_for_minutes(db: Session, minute_ids: list[int]) -> tuple[dict[int, int], dict[int, int], dict[int, int], dict[int, int]]:
    if not minute_ids:
        return {}, {}, {}, {}
    today = _today_start()
    res_counts = {
        int(row.meeting_minute_id): int(row.count)
        for row in (
            db.query(
                MeetingResolution.meeting_minute_id.label("meeting_minute_id"),
                func.count(MeetingResolution.id).label("count"),
            )
            .filter(
                MeetingResolution.meeting_minute_id.in_(minute_ids),
                MeetingResolution.deleted_at.is_(None),
            )
            .group_by(MeetingResolution.meeting_minute_id)
            .all()
        )
    }
    open_counts = {
        int(row.meeting_minute_id): int(row.count)
        for row in (
            db.query(
                MeetingResolution.meeting_minute_id.label("meeting_minute_id"),
                func.count(MeetingResolution.id).label("count"),
            )
            .filter(
                MeetingResolution.meeting_minute_id.in_(minute_ids),
                MeetingResolution.deleted_at.is_(None),
                ~func.lower(MeetingResolution.status).in_(RESOLUTION_TERMINAL_STATUSES),
            )
            .group_by(MeetingResolution.meeting_minute_id)
            .all()
        )
    }
    overdue_counts = {
        int(row.meeting_minute_id): int(row.count)
        for row in (
            db.query(
                MeetingResolution.meeting_minute_id.label("meeting_minute_id"),
                func.count(MeetingResolution.id).label("count"),
            )
            .filter(
                MeetingResolution.meeting_minute_id.in_(minute_ids),
                MeetingResolution.deleted_at.is_(None),
                MeetingResolution.due_date.is_not(None),
                MeetingResolution.due_date < today,
                ~func.lower(MeetingResolution.status).in_(RESOLUTION_TERMINAL_STATUSES),
            )
            .group_by(MeetingResolution.meeting_minute_id)
            .all()
        )
    }
    attachment_counts = {
        int(row.meeting_minute_id): int(row.count)
        for row in (
            db.query(
                MeetingMinuteAttachment.meeting_minute_id.label("meeting_minute_id"),
                func.count(MeetingMinuteAttachment.id).label("count"),
            )
            .filter(
                MeetingMinuteAttachment.meeting_minute_id.in_(minute_ids),
                MeetingMinuteAttachment.deleted_at.is_(None),
            )
            .group_by(MeetingMinuteAttachment.meeting_minute_id)
            .all()
        )
    }
    return res_counts, open_counts, overdue_counts, attachment_counts


def _serialize_minute(
    row: MeetingMinute,
    *,
    resolution_counts: dict[int, int] | None = None,
    open_resolution_counts: dict[int, int] | None = None,
    overdue_resolution_counts: dict[int, int] | None = None,
    attachment_counts: dict[int, int] | None = None,
) -> dict[str, Any]:
    resolution_counts = resolution_counts or {}
    open_resolution_counts = open_resolution_counts or {}
    overdue_resolution_counts = overdue_resolution_counts or {}
    attachment_counts = attachment_counts or {}
    minute_id = int(row.id or 0)
    active_attachments = _active_attachments(row)
    main_file = next(
        (item for item in active_attachments if _attachment_kind(item.file_kind) == "main"),
        None,
    )
    return {
        "id": row.id,
        "meeting_no": row.meeting_no,
        "title": row.title,
        "project_code": row.project_code,
        "project_name": getattr(getattr(row, "project", None), "name_e", None)
        or getattr(getattr(row, "project", None), "name_p", None),
        "meeting_type": row.meeting_type,
        "meeting_date": _to_iso(row.meeting_date),
        "location": row.location,
        "chairperson": row.chairperson,
        "secretary": row.secretary,
        "participants": row.participants,
        "status": row.status,
        "summary": row.summary,
        "notes": row.notes,
        "resolution_count": int(resolution_counts.get(minute_id, len(_active_resolutions(row))) or 0),
        "open_resolution_count": int(open_resolution_counts.get(minute_id, 0) or 0),
        "overdue_resolution_count": int(overdue_resolution_counts.get(minute_id, 0) or 0),
        "attachment_count": int(attachment_counts.get(minute_id, len(active_attachments)) or 0),
        "has_main_file": main_file is not None,
        "main_attachment_id": getattr(main_file, "id", None),
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _apply_minute_filters(
    query,
    db: Session,
    *,
    search: Optional[str],
    project_code: Optional[str],
    meeting_type: Optional[str],
    status: Optional[str],
    responsible_user_id: Optional[int],
    responsible: Optional[str],
    open_resolutions_only: bool,
    overdue_only: bool,
    has_attachments: Optional[bool],
    relation_search: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
):
    pcode = _upper(project_code)
    if pcode:
        query = query.filter(MeetingMinute.project_code == pcode)

    mtype = _norm(meeting_type)
    if mtype:
        query = query.filter(MeetingMinute.meeting_type.ilike(mtype))

    status_value = _norm(status)
    if status_value:
        query = query.filter(MeetingMinute.status.ilike(status_value))

    from_dt = _parse_filter_date(date_from, "date_from")
    to_dt = _parse_filter_date(date_to, "date_to")
    if from_dt and to_dt and from_dt > to_dt:
        raise HTTPException(status_code=400, detail="`date_from` must be earlier than or equal to `date_to`.")
    if from_dt:
        query = query.filter(MeetingMinute.meeting_date >= from_dt)
    if to_dt:
        query = query.filter(MeetingMinute.meeting_date < (to_dt + timedelta(days=1)))

    search_value = _norm(search)
    if search_value:
        pattern = f"%{search_value}%"
        matching_resolutions = (
            db.query(MeetingResolution.meeting_minute_id)
            .filter(
                MeetingResolution.deleted_at.is_(None),
                or_(
                    MeetingResolution.resolution_no.ilike(pattern),
                    MeetingResolution.description.ilike(pattern),
                    MeetingResolution.responsible_name.ilike(pattern),
                ),
            )
            .subquery()
        )
        query = query.filter(
            or_(
                MeetingMinute.meeting_no.ilike(pattern),
                MeetingMinute.title.ilike(pattern),
                MeetingMinute.meeting_type.ilike(pattern),
                MeetingMinute.location.ilike(pattern),
                MeetingMinute.participants.ilike(pattern),
                MeetingMinute.id.in_(db.query(matching_resolutions.c.meeting_minute_id)),
            )
        )

    if has_attachments is not None:
        attachment_ids = (
            db.query(MeetingMinuteAttachment.meeting_minute_id)
            .filter(MeetingMinuteAttachment.deleted_at.is_(None))
            .distinct()
            .subquery()
        )
        if has_attachments:
            query = query.filter(MeetingMinute.id.in_(db.query(attachment_ids.c.meeting_minute_id)))
        else:
            query = query.filter(~MeetingMinute.id.in_(db.query(attachment_ids.c.meeting_minute_id)))

    relation_value = _norm(relation_search)
    if relation_value:
        pattern = f"%{relation_value}%"
        outgoing_ids = (
            db.query(MeetingMinuteExternalRelation.meeting_minute_id)
            .filter(
                or_(
                    MeetingMinuteExternalRelation.target_code.ilike(pattern),
                    MeetingMinuteExternalRelation.target_title.ilike(pattern),
                    MeetingMinuteExternalRelation.notes.ilike(pattern),
                )
            )
            .distinct()
            .subquery()
        )
        incoming_document_ids = (
            db.query(DocumentExternalRelation.target_entity_id.label("meeting_id"))
            .join(MdrDocument, MdrDocument.id == DocumentExternalRelation.source_document_id)
            .filter(
                DocumentExternalRelation.target_entity_type == "meeting_minute",
                or_(
                    DocumentExternalRelation.target_code.ilike(pattern),
                    DocumentExternalRelation.target_title.ilike(pattern),
                    DocumentExternalRelation.notes.ilike(pattern),
                    MdrDocument.doc_number.ilike(pattern),
                    MdrDocument.doc_title_e.ilike(pattern),
                    MdrDocument.doc_title_p.ilike(pattern),
                    MdrDocument.subject.ilike(pattern),
                ),
            )
            .distinct()
            .subquery()
        )
        incoming_corr_ids = (
            db.query(CorrespondenceExternalRelation.target_entity_id.label("meeting_id"))
            .join(Correspondence, Correspondence.id == CorrespondenceExternalRelation.correspondence_id)
            .filter(
                CorrespondenceExternalRelation.target_entity_type == "meeting_minute",
                or_(
                    CorrespondenceExternalRelation.target_code.ilike(pattern),
                    CorrespondenceExternalRelation.target_title.ilike(pattern),
                    CorrespondenceExternalRelation.notes.ilike(pattern),
                    Correspondence.reference_no.ilike(pattern),
                    Correspondence.subject.ilike(pattern),
                    Correspondence.sender.ilike(pattern),
                    Correspondence.recipient.ilike(pattern),
                ),
            )
            .distinct()
            .subquery()
        )
        query = query.filter(
            or_(
                MeetingMinute.id.in_(db.query(outgoing_ids.c.meeting_minute_id)),
                MeetingMinute.id.in_(db.query(incoming_document_ids.c.meeting_id)),
                cast(MeetingMinute.id, String).in_(db.query(incoming_corr_ids.c.meeting_id)),
            )
        )

    needs_resolution_join = any(
        [
            responsible_user_id is not None,
            bool(_norm(responsible)),
            bool(open_resolutions_only),
            bool(overdue_only),
        ]
    )
    if needs_resolution_join:
        query = query.join(
            MeetingResolution,
            MeetingResolution.meeting_minute_id == MeetingMinute.id,
        ).filter(MeetingResolution.deleted_at.is_(None))

    if responsible_user_id is not None:
        query = query.filter(MeetingResolution.responsible_user_id == int(responsible_user_id))

    responsible_value = _norm(responsible)
    if responsible_value:
        pattern = f"%{responsible_value}%"
        query = query.filter(MeetingResolution.responsible_name.ilike(pattern))

    if open_resolutions_only:
        query = query.filter(~func.lower(MeetingResolution.status).in_(RESOLUTION_TERMINAL_STATUSES))

    if overdue_only:
        query = query.filter(
            MeetingResolution.due_date.is_not(None),
            MeetingResolution.due_date < _today_start(),
            ~func.lower(MeetingResolution.status).in_(RESOLUTION_TERMINAL_STATUSES),
        )

    return query.distinct()


def _summary_for_query(db: Session, query) -> dict[str, int]:
    ids_subq = query.with_entities(MeetingMinute.id.label("id")).distinct().subquery()
    total = db.query(func.count(ids_subq.c.id)).scalar() or 0
    open_minutes = (
        db.query(func.count(MeetingMinute.id))
        .join(ids_subq, ids_subq.c.id == MeetingMinute.id)
        .filter(func.lower(MeetingMinute.status) == "open")
        .scalar()
        or 0
    )
    closed_minutes = (
        db.query(func.count(MeetingMinute.id))
        .join(ids_subq, ids_subq.c.id == MeetingMinute.id)
        .filter(func.lower(MeetingMinute.status) == "closed")
        .scalar()
        or 0
    )
    open_resolution_minutes = (
        db.query(func.count(func.distinct(MeetingResolution.meeting_minute_id)))
        .join(ids_subq, ids_subq.c.id == MeetingResolution.meeting_minute_id)
        .filter(
            MeetingResolution.deleted_at.is_(None),
            ~func.lower(MeetingResolution.status).in_(RESOLUTION_TERMINAL_STATUSES),
        )
        .scalar()
        or 0
    )
    overdue_resolutions = (
        db.query(func.count(MeetingResolution.id))
        .join(ids_subq, ids_subq.c.id == MeetingResolution.meeting_minute_id)
        .filter(
            MeetingResolution.deleted_at.is_(None),
            MeetingResolution.due_date.is_not(None),
            MeetingResolution.due_date < _today_start(),
            ~func.lower(MeetingResolution.status).in_(RESOLUTION_TERMINAL_STATUSES),
        )
        .scalar()
        or 0
    )
    return {
        "total": int(total),
        "open": int(open_minutes),
        "closed": int(closed_minutes),
        "open_resolution_minutes": int(open_resolution_minutes),
        "overdue_resolutions": int(overdue_resolutions),
    }


def _next_resolution_no(db: Session, minute_id: int) -> str:
    count = (
        db.query(func.count(MeetingResolution.id))
        .filter(
            MeetingResolution.meeting_minute_id == int(minute_id),
            MeetingResolution.deleted_at.is_(None),
        )
        .scalar()
        or 0
    )
    return f"R-{int(count) + 1:03d}"


def _minute_storage_parts(row: MeetingMinute, file_kind: str) -> tuple[str, str, str, str]:
    project = safe_name(row.project_code or "GENERAL") or "GENERAL"
    date_value = row.meeting_date or datetime.utcnow()
    year = str(date_value.year)
    meeting_no = safe_name(row.meeting_no or f"meeting-{row.id}") or f"meeting-{row.id}"
    kind = "main" if _attachment_kind(file_kind) == "main" else "attachments"
    return project, year, meeting_no, kind


def _minute_storage_dir(db: Session, row: MeetingMinute, file_kind: str) -> Path:
    base = StorageManager(db).get_correspondence_base_path()
    project, year, meeting_no, kind = _minute_storage_parts(row, file_kind)
    path = base / "meeting_minutes" / project / year / meeting_no / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def _storage_file_name(row: MeetingMinute, file_kind: str, original_name: str) -> str:
    safe_original = safe_name(original_name) or "file"
    suffix = Path(safe_original).suffix
    stem = safe_name(Path(safe_original).stem) or "file"
    prefix = "main" if _attachment_kind(file_kind) == "main" else "att"
    meeting_no = safe_name(row.meeting_no or f"meeting-{row.id}") or f"meeting-{row.id}"
    return safe_name(f"{prefix}_{meeting_no}_{uuid4().hex[:8]}_{stem}{suffix}") or f"{prefix}_{uuid4().hex}"


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


def _download_webdav_attachment(db: Session, row: MeetingMinuteAttachment) -> StreamingResponse:
    stored_path = str(row.stored_path or "").strip()
    remote_path = stored_path.replace("webdav://", "", 1)
    adapter = _nextcloud_adapter_for_webdav(db)
    if not adapter.file_exists(remote_path):
        raise HTTPException(status_code=404, detail="Attachment file not found")
    filename = safe_name(row.file_name or f"meeting-attachment-{row.id}") or f"meeting-attachment-{row.id}"
    media_type = _norm(row.mime_type or row.detected_mime) or "application/octet-stream"
    return StreamingResponse(
        adapter.download_file_stream(remote_path),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _render_meeting_print_html(row: MeetingMinute) -> str:
    project_name = (
        getattr(getattr(row, "project", None), "name_p", None)
        or getattr(getattr(row, "project", None), "name_e", None)
        or row.project_code
        or "-"
    )
    resolutions = sorted(_active_resolutions(row), key=lambda item: (int(item.sort_order or 0), int(item.id or 0)))
    attachments = _active_attachments(row)
    resolution_rows = []
    for idx, resolution in enumerate(resolutions, 1):
        responsible = (
            resolution.responsible_name
            or getattr(getattr(resolution, "responsible_user", None), "full_name", None)
            or getattr(getattr(resolution, "responsible_org", None), "name", None)
            or "-"
        )
        resolution_rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td class=\"ltr\">{html_escape(_norm(resolution.resolution_no) or '-')}</td>"
            f"<td class=\"desc\">{html_escape(_norm(resolution.description) or '-')}</td>"
            f"<td>{html_escape(responsible)}</td>"
            f"<td>{html_escape(_format_jalali_date(resolution.due_date))}</td>"
            f"<td>{html_escape(_norm(resolution.status) or '-')}</td>"
            f"<td>{html_escape(_norm(resolution.priority) or '-')}</td>"
            "</tr>"
        )
    if not resolution_rows:
        resolution_rows.append('<tr><td colspan="7" class="empty-row">مصوبه‌ای ثبت نشده است.</td></tr>')

    attachment_rows = []
    for idx, attachment in enumerate(attachments, 1):
        attachment_rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{html_escape('فایل اصلی' if _attachment_kind(attachment.file_kind) == 'main' else 'پیوست')}</td>"
            f"<td class=\"ltr\">{html_escape(_norm(attachment.file_name) or '-')}</td>"
            f"<td>{html_escape(str(int(attachment.size_bytes or 0)))}</td>"
            f"<td>{html_escape(_format_jalali_date(attachment.uploaded_at))}</td>"
            "</tr>"
        )
    if not attachment_rows:
        attachment_rows.append('<tr><td colspan="5" class="empty-row">پیوستی ثبت نشده است.</td></tr>')

    html = f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>صورتجلسه - {html_escape(_norm(row.meeting_no))}</title>
  <style>
    @page {{ size: A4; margin: 0; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:#edf2f7; color:#111827; font-family:Tahoma,Arial,sans-serif; direction:rtl; font-size:11px; line-height:1.65; }}
    .sheet {{ width:210mm; min-height:297mm; margin:18px auto; background:#fff; display:flex; flex-direction:column; box-shadow:0 14px 34px rgba(15,23,42,.18); }}
    .header {{ flex:0 0 auto; }}
    .content {{ flex:1 1 auto; padding:4mm 8mm 0; }}
    .footer {{ flex:0 0 auto; margin-top:auto; padding:0 8mm 8mm; }}
    table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
    td, th {{ border:1px solid #1f2937; padding:5px 6px; vertical-align:middle; }}
    th {{ background:#d9d9d9; font-weight:900; text-align:center; }}
    .head td {{ height:28px; }}
    .meta {{ width:46mm; font-size:10.5px; }}
    .meta .label {{ width:17mm; background:#f3f4f6; font-weight:900; text-align:center; }}
    .title-cell {{ text-align:center; }}
    .title-fa {{ font-size:21px; font-weight:900; }}
    .title-en {{ direction:ltr; font-weight:900; font-size:12px; }}
    .logo-box {{ height:24mm; border:1px solid #8b95a1; display:flex; align-items:center; justify-content:center; font-weight:900; background:#fafafa; }}
    .section-title {{ background:#d6d6d6; border:1px solid #1f2937; border-bottom:0; margin-top:4mm; padding:4px 6px; text-align:center; font-weight:900; }}
    .info td:nth-child(odd) {{ width:25mm; background:#f2f2f2; font-weight:900; text-align:center; }}
    .info td:nth-child(even) {{ text-align:right; }}
    .summary-box {{ border:1px solid #1f2937; min-height:22mm; padding:7px 8px; white-space:pre-wrap; }}
    .resolutions th {{ font-size:10.5px; }}
    .resolutions td {{ text-align:center; font-size:10px; }}
    .resolutions .desc {{ text-align:right; }}
    .ltr {{ direction:ltr; unicode-bidi:embed; font-family:Consolas,'Courier New',monospace; }}
    .empty-row {{ height:16mm; color:#64748b; font-weight:800; text-align:center; }}
    .signatures td {{ height:24mm; text-align:center; font-weight:900; }}
    .muted {{ color:#64748b; font-size:10px; }}
    @media print {{ body {{ background:#fff; }} .sheet {{ margin:0; box-shadow:none; }} }}
  </style>
</head>
<body>
  <main class="sheet">
    <header class="header">
      <table class="head">
        <tr>
          <td class="meta">
            <table>
              <tr><td class="label">شماره</td><td class="ltr">{html_escape(_norm(row.meeting_no) or '-')}</td></tr>
              <tr><td class="label">تاریخ</td><td>{html_escape(_format_jalali_date(row.meeting_date))}</td></tr>
              <tr><td class="label">وضعیت</td><td>{html_escape(_norm(row.status) or '-')}</td></tr>
            </table>
          </td>
          <td class="title-cell">
            <div class="title-fa">صورتجلسه</div>
            <div class="title-en">MEETING MINUTES</div>
            <div>{html_escape(_norm(row.title) or '-')}</div>
          </td>
          <td style="width:43mm;"><div class="logo-box">لوگوی شرکت</div></td>
        </tr>
      </table>
    </header>
    <section class="content">
      <div class="section-title">مشخصات جلسه</div>
      <table class="info">
        <tr><td>پروژه</td><td>{html_escape(str(project_name))}</td><td>کد پروژه</td><td class="ltr">{html_escape(_norm(row.project_code) or '-')}</td></tr>
        <tr><td>نوع جلسه</td><td>{html_escape(_norm(row.meeting_type) or '-')}</td><td>محل</td><td>{html_escape(_norm(row.location) or '-')}</td></tr>
        <tr><td>رئیس جلسه</td><td>{html_escape(_norm(row.chairperson) or '-')}</td><td>دبیر جلسه</td><td>{html_escape(_norm(row.secretary) or '-')}</td></tr>
        <tr><td>حاضرین</td><td colspan="3">{html_escape(_norm(row.participants) or '-')}</td></tr>
      </table>
      <div class="section-title">خلاصه جلسه</div>
      <div class="summary-box">{html_escape(_norm(row.summary) or _norm(row.notes) or '-')}</div>
      <div class="section-title">مصوبات</div>
      <table class="resolutions">
        <thead><tr><th style="width:8mm;">ردیف</th><th style="width:22mm;">شماره</th><th>شرح مصوبه</th><th style="width:32mm;">مسئول</th><th style="width:23mm;">سررسید</th><th style="width:20mm;">وضعیت</th><th style="width:18mm;">اولویت</th></tr></thead>
        <tbody>{''.join(resolution_rows)}</tbody>
      </table>
      <div class="section-title">پیوست‌ها</div>
      <table class="resolutions">
        <thead><tr><th style="width:8mm;">ردیف</th><th style="width:24mm;">نوع</th><th>نام فایل</th><th style="width:22mm;">حجم</th><th style="width:26mm;">تاریخ</th></tr></thead>
        <tbody>{''.join(attachment_rows)}</tbody>
      </table>
    </section>
    <footer class="footer">
      <div class="section-title">امضاها</div>
      <table class="signatures">
        <tr><td>تهیه‌کننده<br><span class="muted">نام، امضا، تاریخ</span></td><td>نماینده پیمانکار<br><span class="muted">نام، امضا، تاریخ</span></td><td>نماینده مشاور<br><span class="muted">نام، امضا، تاریخ</span></td></tr>
      </table>
    </footer>
  </main>
</body>
</html>"""
    return html


@router.get("/catalog")
def get_meeting_minutes_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    project_query = db.query(Project).order_by(Project.code.asc())
    project_query = apply_scope_query_filters(project_query, db, user, project_column=Project.code)
    project_rows = project_query.all()
    user_rows = db.query(DbUser).filter(DbUser.is_active.is_(True)).order_by(DbUser.full_name.asc(), DbUser.email.asc()).all()
    org_rows = db.query(Organization).filter(Organization.is_active.is_(True)).order_by(Organization.name.asc()).all()
    existing_types = [
        str(value or "").strip()
        for (value,) in (
            db.query(MeetingMinute.meeting_type)
            .filter(MeetingMinute.deleted_at.is_(None))
            .distinct()
            .order_by(MeetingMinute.meeting_type.asc())
            .all()
        )
        if str(value or "").strip()
    ]
    meeting_types = sorted(set(["General", "Coordination", "Technical", "Site", "Management", *existing_types]))
    return {
        "ok": True,
        "projects": [
            {
                "code": row.code,
                "name_e": row.name_e,
                "name_p": row.name_p,
                "is_active": bool(row.is_active),
            }
            for row in project_rows
        ],
        "meeting_types": meeting_types,
        "minute_statuses": list(MINUTE_STATUS_LABELS.values()),
        "resolution_statuses": ["Open", "In Progress", "Done", "Cancelled"],
        "priorities": ["Low", "Normal", "High", "Critical"],
        "users": [
            {"id": row.id, "full_name": row.full_name, "email": row.email}
            for row in user_rows
        ],
        "organizations": [
            {"id": row.id, "code": row.code, "name": row.name, "org_type": row.org_type}
            for row in org_rows
        ],
    }


@router.get("/dashboard")
def get_meeting_minutes_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    query = _base_minute_query(db)
    query = apply_scope_query_filters(query, db, user, project_column=MeetingMinute.project_code)
    return {"ok": True, "stats": _summary_for_query(db, query)}


@router.get("/list")
def list_meeting_minutes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    meeting_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    responsible_user_id: Optional[int] = Query(default=None),
    responsible: Optional[str] = Query(default=None),
    open_resolutions_only: bool = Query(default=False),
    overdue_only: bool = Query(default=False),
    has_attachments: Optional[bool] = Query(default=None),
    relation_search: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    sort_by: Optional[str] = Query(default="meeting_date"),
    sort_dir: Optional[str] = Query(default="desc"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    query = _base_minute_query(db)
    query = apply_scope_query_filters(query, db, user, project_column=MeetingMinute.project_code)
    query = _apply_minute_filters(
        query,
        db,
        search=search,
        project_code=project_code,
        meeting_type=meeting_type,
        status=status,
        responsible_user_id=responsible_user_id,
        responsible=responsible,
        open_resolutions_only=open_resolutions_only,
        overdue_only=overdue_only,
        has_attachments=has_attachments,
        relation_search=relation_search,
        date_from=date_from,
        date_to=date_to,
    )
    summary = _summary_for_query(db, query)
    total = int(summary["total"])
    sort_map = {
        "meeting_no": MeetingMinute.meeting_no,
        "title": MeetingMinute.title,
        "project_code": MeetingMinute.project_code,
        "meeting_type": MeetingMinute.meeting_type,
        "meeting_date": MeetingMinute.meeting_date,
        "status": MeetingMinute.status,
        "created_at": MeetingMinute.created_at,
        "updated_at": MeetingMinute.updated_at,
    }
    sort_column = sort_map.get(_lower(sort_by), MeetingMinute.meeting_date)
    order_expr = sort_column.asc() if _lower(sort_dir) == "asc" else sort_column.desc()
    rows = (
        query.options(
            selectinload(MeetingMinute.project),
            selectinload(MeetingMinute.created_by),
            selectinload(MeetingMinute.resolutions),
            selectinload(MeetingMinute.attachments),
        )
        .order_by(order_expr, MeetingMinute.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    minute_ids = [int(row.id) for row in rows]
    res_counts, open_counts, overdue_counts, attachment_counts = _counts_for_minutes(db, minute_ids)
    return {
        "ok": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "summary": summary,
        "data": [
            _serialize_minute(
                row,
                resolution_counts=res_counts,
                open_resolution_counts=open_counts,
                overdue_resolution_counts=overdue_counts,
                attachment_counts=attachment_counts,
            )
            for row in rows
        ],
    }


@router.get("/next-number")
def get_next_meeting_minute_number(
    project_code: Optional[str] = Query(default=None),
    meeting_date: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    parsed_date = _parse_filter_date(meeting_date, "meeting_date") if _norm(meeting_date) else datetime.utcnow()
    pcode = _project_or_none(db, project_code) if _upper(project_code) else None
    enforce_scope_access(db, user, project_code=pcode)
    payload = _next_meeting_no(db, project_code=pcode, meeting_date=parsed_date, consume=False)
    return {"ok": True, **payload}


@router.post("/create")
def create_meeting_minute(
    payload: MeetingMinuteCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:create")),
):
    title = _norm(payload.title)
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    project_code = _project_or_none(db, payload.project_code)
    enforce_scope_access(db, user, project_code=project_code)
    meeting_date = payload.meeting_date or datetime.utcnow()
    meeting_no = _norm(payload.meeting_no)
    if meeting_no:
        _ensure_unique_active_meeting_no(db, meeting_no)
    else:
        meeting_no = str(_next_meeting_no(db, project_code=project_code, meeting_date=meeting_date, consume=True)["meeting_no"])
    row = MeetingMinute(
        meeting_no=meeting_no,
        title=title,
        project_code=project_code,
        meeting_type=_norm(payload.meeting_type) or "General",
        meeting_date=meeting_date,
        location=_norm(payload.location) or None,
        chairperson=_norm(payload.chairperson) or None,
        secretary=_norm(payload.secretary) or None,
        participants=_norm(payload.participants) or None,
        status=_normalize_minute_status(payload.status),
        summary=_norm(payload.summary) or None,
        notes=_norm(payload.notes) or None,
        created_by_id=getattr(user, "id", None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_minute(row)}


@router.put("/{minute_id}")
def update_meeting_minute(
    minute_id: int,
    payload: MeetingMinuteUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:update")),
):
    row = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=row.project_code)
    fields = set(getattr(payload, "model_fields_set", set()) or set())

    if "meeting_no" in fields:
        meeting_no = _norm(payload.meeting_no)
        if not meeting_no:
            raise HTTPException(status_code=400, detail="meeting_no is required")
        _ensure_unique_active_meeting_no(db, meeting_no, exclude_id=int(row.id))
        row.meeting_no = meeting_no
    if "title" in fields:
        title = _norm(payload.title)
        if not title:
            raise HTTPException(status_code=400, detail="title is required")
        row.title = title
    if "project_code" in fields:
        project_code = _project_or_none(db, payload.project_code)
        enforce_scope_access(db, user, project_code=project_code)
        row.project_code = project_code
    if "meeting_type" in fields:
        row.meeting_type = _norm(payload.meeting_type) or "General"
    if "meeting_date" in fields and payload.meeting_date is not None:
        row.meeting_date = payload.meeting_date
    if "location" in fields:
        row.location = _norm(payload.location) or None
    if "chairperson" in fields:
        row.chairperson = _norm(payload.chairperson) or None
    if "secretary" in fields:
        row.secretary = _norm(payload.secretary) or None
    if "participants" in fields:
        row.participants = _norm(payload.participants) or None
    if "status" in fields:
        row.status = _normalize_minute_status(payload.status)
    if "summary" in fields:
        row.summary = _norm(payload.summary) or None
    if "notes" in fields:
        row.notes = _norm(payload.notes) or None

    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_minute(row)}


@router.delete("/{minute_id}")
def delete_meeting_minute(
    minute_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:delete")),
):
    row = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=row.project_code)
    now = datetime.utcnow()
    row.deleted_at = now
    row.updated_at = now
    for resolution in _active_resolutions(row):
        resolution.deleted_at = now
        resolution.updated_at = now
    for attachment in _active_attachments(row):
        attachment.deleted_at = now
    db.commit()
    return {"ok": True, "id": int(minute_id)}


@router.get("/{minute_id}/print-preview", response_class=HTMLResponse)
def meeting_minute_print_preview(
    minute_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    row = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=row.project_code)
    row = (
        db.query(MeetingMinute)
        .options(
            selectinload(MeetingMinute.project),
            selectinload(MeetingMinute.resolutions).selectinload(MeetingResolution.responsible_user),
            selectinload(MeetingMinute.resolutions).selectinload(MeetingResolution.responsible_org),
            selectinload(MeetingMinute.attachments),
        )
        .filter(MeetingMinute.id == int(minute_id), MeetingMinute.deleted_at.is_(None))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Meeting minute not found")
    return HTMLResponse(_render_meeting_print_html(row))


@router.get("/{minute_id}/relations")
def list_meeting_relations(
    minute_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    minute = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=minute.project_code)
    outgoing_rows = (
        db.query(MeetingMinuteExternalRelation)
        .filter(MeetingMinuteExternalRelation.meeting_minute_id == int(minute_id))
        .order_by(MeetingMinuteExternalRelation.created_at.desc(), MeetingMinuteExternalRelation.id.desc())
        .all()
    )

    document_query = (
        db.query(DocumentExternalRelation)
        .join(MdrDocument, MdrDocument.id == DocumentExternalRelation.source_document_id)
        .options(selectinload(DocumentExternalRelation.source_document))
        .filter(
            DocumentExternalRelation.target_entity_type == "meeting_minute",
            DocumentExternalRelation.target_entity_id == int(minute_id),
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

    correspondence_query = (
        db.query(CorrespondenceExternalRelation, Correspondence)
        .join(Correspondence, Correspondence.id == CorrespondenceExternalRelation.correspondence_id)
        .filter(
            CorrespondenceExternalRelation.target_entity_type == "meeting_minute",
            CorrespondenceExternalRelation.target_entity_id == str(int(minute_id)),
        )
    )
    correspondence_query = apply_scope_query_filters(
        correspondence_query,
        db,
        user,
        project_column=Correspondence.project_code,
    )
    correspondence_rows = correspondence_query.order_by(CorrespondenceExternalRelation.created_at.desc()).all()

    incoming = [_serialize_document_incoming_relation(db, row) for row in document_rows]
    incoming.extend(_serialize_correspondence_incoming_relation(row, corr) for row, corr in correspondence_rows)
    return {
        "ok": True,
        "outgoing": [_serialize_meeting_relation(row, direction="outgoing") for row in outgoing_rows],
        "incoming": incoming,
    }


@router.post("/{minute_id}/relations")
def create_meeting_relation(
    minute_id: int,
    payload: MeetingRelationCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:update")),
):
    minute = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=minute.project_code)
    target_type = _normalize_relation_target_type(payload.target_entity_type)
    relation_type = _normalize_relation_type(payload.relation_type)
    notes = _norm(payload.notes) or None

    if target_type == "document":
        document = _resolve_relation_document(db, target_code=payload.target_code, target_entity_id=payload.target_entity_id)
        enforce_scope_access(
            db,
            user,
            project_code=document.project_code,
            discipline_code=document.discipline_code,
        )
        revision = _latest_document_revision(db, int(document.id or 0))
        target = {
            "type": "document",
            "id": int(document.id or 0),
            "code": str(document.doc_number or f"DOC-{int(document.id or 0)}"),
            "title": document.doc_title_p or document.doc_title_e or document.subject,
            "project_code": document.project_code,
            "status": getattr(revision, "status", None),
        }
    else:
        correspondence = _resolve_relation_correspondence(
            db,
            target_code=payload.target_code,
            target_entity_id=payload.target_entity_id,
        )
        enforce_scope_access(db, user, project_code=correspondence.project_code)
        target = {
            "type": "correspondence",
            "id": int(correspondence.id or 0),
            "code": str(correspondence.reference_no or f"CORR-{int(correspondence.id or 0)}"),
            "title": correspondence.subject,
            "project_code": correspondence.project_code,
            "status": correspondence.status,
        }

    existing = (
        db.query(MeetingMinuteExternalRelation)
        .filter(
            MeetingMinuteExternalRelation.meeting_minute_id == int(minute_id),
            MeetingMinuteExternalRelation.target_entity_type == target["type"],
            MeetingMinuteExternalRelation.target_entity_id == str(target["id"]),
            MeetingMinuteExternalRelation.relation_type == relation_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Relation already exists")
    row = MeetingMinuteExternalRelation(
        meeting_minute_id=int(minute_id),
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
    minute.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_meeting_relation(row)}


@router.delete("/{minute_id}/relations/{relation_id}")
def delete_meeting_relation(
    minute_id: int,
    relation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:update")),
):
    minute = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=minute.project_code)
    key = _norm(relation_id)
    if key.lower().startswith("external:"):
        key = key.split(":", 1)[1]
    if not key.isdigit():
        raise HTTPException(status_code=400, detail="Invalid relation id")
    row = (
        db.query(MeetingMinuteExternalRelation)
        .filter(
            MeetingMinuteExternalRelation.id == int(key),
            MeetingMinuteExternalRelation.meeting_minute_id == int(minute_id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Relation not found")
    db.delete(row)
    minute.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "id": relation_id}


@router.get("/{minute_id}/resolutions")
def list_meeting_resolutions(
    minute_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    minute = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=minute.project_code)
    rows = (
        db.query(MeetingResolution)
        .options(
            selectinload(MeetingResolution.responsible_user),
            selectinload(MeetingResolution.responsible_org),
            selectinload(MeetingResolution.attachments),
        )
        .filter(
            MeetingResolution.meeting_minute_id == int(minute_id),
            MeetingResolution.deleted_at.is_(None),
        )
        .order_by(MeetingResolution.sort_order.asc(), MeetingResolution.id.asc())
        .all()
    )
    return {"ok": True, "data": [_serialize_resolution(row) for row in rows]}


@router.post("/{minute_id}/resolutions")
def create_meeting_resolution(
    minute_id: int,
    payload: MeetingResolutionCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:update")),
):
    minute = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=minute.project_code)
    description = _norm(payload.description)
    if not description:
        raise HTTPException(status_code=400, detail="description is required")
    row = MeetingResolution(
        meeting_minute_id=int(minute_id),
        resolution_no=_norm(payload.resolution_no) or _next_resolution_no(db, int(minute_id)),
        description=description,
        responsible_user_id=_validated_user_id_or_none(db, payload.responsible_user_id),
        responsible_org_id=_validated_org_id_or_none(db, payload.responsible_org_id),
        responsible_name=_norm(payload.responsible_name) or None,
        due_date=payload.due_date,
        status=_normalize_resolution_status(payload.status),
        priority=_normalize_priority(payload.priority),
        sort_order=int(payload.sort_order or 0),
        created_by_id=getattr(user, "id", None),
    )
    db.add(row)
    minute.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_resolution(row)}


@router.put("/resolutions/{resolution_id}")
def update_meeting_resolution(
    resolution_id: int,
    payload: MeetingResolutionUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:update")),
):
    row = _load_resolution_or_404(db, resolution_id)
    minute = _load_minute_or_404(db, int(row.meeting_minute_id))
    enforce_scope_access(db, user, project_code=minute.project_code)
    fields = set(getattr(payload, "model_fields_set", set()) or set())

    if "resolution_no" in fields:
        row.resolution_no = _norm(payload.resolution_no) or row.resolution_no
    if "description" in fields:
        description = _norm(payload.description)
        if not description:
            raise HTTPException(status_code=400, detail="description is required")
        row.description = description
    if "responsible_user_id" in fields:
        row.responsible_user_id = _validated_user_id_or_none(db, payload.responsible_user_id)
    if "responsible_org_id" in fields:
        row.responsible_org_id = _validated_org_id_or_none(db, payload.responsible_org_id)
    if "responsible_name" in fields:
        row.responsible_name = _norm(payload.responsible_name) or None
    if "due_date" in fields:
        row.due_date = payload.due_date
    if "status" in fields:
        row.status = _normalize_resolution_status(payload.status)
    if "priority" in fields:
        row.priority = _normalize_priority(payload.priority)
    if "sort_order" in fields and payload.sort_order is not None:
        row.sort_order = int(payload.sort_order)

    row.updated_at = datetime.utcnow()
    minute.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_resolution(row)}


@router.delete("/resolutions/{resolution_id}")
def delete_meeting_resolution(
    resolution_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:update")),
):
    row = _load_resolution_or_404(db, resolution_id)
    minute = _load_minute_or_404(db, int(row.meeting_minute_id))
    enforce_scope_access(db, user, project_code=minute.project_code)
    now = datetime.utcnow()
    row.deleted_at = now
    row.updated_at = now
    for attachment in list(row.attachments or []):
        if attachment.deleted_at is None:
            attachment.deleted_at = now
    minute.updated_at = now
    db.commit()
    return {"ok": True, "id": int(resolution_id)}


@router.get("/{minute_id}/attachments")
def list_meeting_attachments(
    minute_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    minute = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=minute.project_code)
    rows = (
        db.query(MeetingMinuteAttachment)
        .options(selectinload(MeetingMinuteAttachment.uploaded_by))
        .filter(
            MeetingMinuteAttachment.meeting_minute_id == int(minute_id),
            MeetingMinuteAttachment.deleted_at.is_(None),
        )
        .order_by(MeetingMinuteAttachment.uploaded_at.desc(), MeetingMinuteAttachment.id.desc())
        .all()
    )
    return {"ok": True, "data": [_serialize_attachment(row) for row in rows]}


@router.post("/{minute_id}/attachments/upload")
def upload_meeting_attachment(
    minute_id: int,
    file: UploadFile = File(...),
    file_kind: str = Form("attachment"),
    resolution_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:attachment")),
):
    minute = _load_minute_or_404(db, minute_id)
    enforce_scope_access(db, user, project_code=minute.project_code)
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    linked_resolution_id: int | None = None
    if resolution_id is not None:
        resolution = _load_resolution_or_404(db, int(resolution_id))
        if int(resolution.meeting_minute_id) != int(minute_id):
            raise HTTPException(status_code=400, detail="Resolution does not belong to this meeting minute")
        linked_resolution_id = int(resolution.id)

    normalized_kind = _attachment_kind(file_kind)
    original_name = safe_name(file.filename) or "file"
    stored_name = _storage_file_name(minute, normalized_kind, original_name)
    storage_manager = StorageManager(db)

    if storage_manager._is_webdav_primary_mode():
        integrations = get_storage_integrations(db)
        runtime = resolve_nextcloud_runtime(integrations)
        root_path = str(runtime.get("root_path") or "")
        base = storage_manager.get_correspondence_webdav_base()
        project, year, meeting_no, kind_folder = _minute_storage_parts(minute, normalized_kind)
        absolute_path = f"{base}/meeting_minutes/{project}/{year}/{meeting_no}/{kind_folder}/{stored_name}"
        try:
            remote_relative_path = StorageManager.relativize_webdav_path(absolute_path, root_path)
        except Exception:
            remote_relative_path = StorageManager._normalize_remote_path(absolute_path)
        saved = storage_manager.save_upload_to_webdav(
            file=file,
            remote_relative_path=remote_relative_path,
            file_kind="attachment",
        )
        stored_path = saved.stored_path
    else:
        folder = _minute_storage_dir(db, minute, normalized_kind)
        saved = storage_manager.save_upload_secure(
            file=file,
            destination_folder=str(folder),
            new_name=stored_name,
            file_kind="attachment",
        )
        stored_path = str(Path(saved.stored_path))

    now = datetime.utcnow()
    if normalized_kind == "main":
        for existing in (
            db.query(MeetingMinuteAttachment)
            .filter(
                MeetingMinuteAttachment.meeting_minute_id == int(minute_id),
                MeetingMinuteAttachment.file_kind == "main",
                MeetingMinuteAttachment.deleted_at.is_(None),
            )
            .all()
        ):
            existing.deleted_at = now

    row = MeetingMinuteAttachment(
        meeting_minute_id=int(minute_id),
        resolution_id=linked_resolution_id,
        file_name=stored_name,
        stored_path=stored_path,
        file_kind=normalized_kind,
        mime_type=saved.declared_mime or _norm(file.content_type) or None,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        storage_backend=storage_manager.resolve_storage_backend_for_path(saved.stored_path),
        mirror_provider=None,
        mirror_remote_id=None,
        mirror_remote_url=None,
        mirror_status="disabled",
        mirror_updated_at=now,
        uploaded_by_id=getattr(user, "id", None),
    )
    db.add(row)
    minute.updated_at = now
    db.commit()
    db.refresh(row)
    return {"ok": True, "data": _serialize_attachment(row)}


@router.get("/attachments/{attachment_id}/download")
def download_meeting_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:read")),
):
    row = _load_attachment_or_404(db, attachment_id)
    minute = _load_minute_or_404(db, int(row.meeting_minute_id))
    enforce_scope_access(db, user, project_code=minute.project_code)
    if str(row.stored_path or "").strip().startswith("webdav://"):
        return _download_webdav_attachment(db, row)
    file_path = Path(row.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path=str(file_path), filename=row.file_name, media_type=row.mime_type)


@router.delete("/attachments/{attachment_id}")
def delete_meeting_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("meeting_minutes:attachment")),
):
    row = _load_attachment_or_404(db, attachment_id)
    minute = _load_minute_or_404(db, int(row.meeting_minute_id))
    enforce_scope_access(db, user, project_code=minute.project_code)
    row.deleted_at = datetime.utcnow()
    minute.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "id": int(attachment_id)}
