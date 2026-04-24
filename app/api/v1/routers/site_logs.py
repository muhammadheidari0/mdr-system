from __future__ import annotations

import os
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    User,
    apply_organization_query_filters,
    apply_scope_query_filters,
    enforce_organization_access,
    enforce_scope_access,
    get_db,
    require_permission,
)
from app.core.organizations import OrganizationType
from app.db.models import (
    Discipline,
    Organization,
    Project,
    SiteLog,
    SiteLogActivityRow,
    SiteLogAttachment,
    SiteLogComment,
    SiteLogEquipmentCatalog,
    SiteLogEquipmentRow,
    SiteLogEquipmentStatusCatalog,
    SiteLogManpowerRow,
    SiteLogRoleCatalog,
    SiteLogSequence,
    SiteLogStatusLog,
    SiteLogWorkflowStatus,
    User as DbUser,
)
from app.services.access_control import resolve_effective_access
from app.services.folder_service import safe_name
from app.services.storage import StorageManager


router = APIRouter(prefix="/site-logs", tags=["Site Logs"])

LOG_TYPES = {"DAILY", "WEEKLY", "SAFETY_INCIDENT"}
STATUSES = {"DRAFT", "SUBMITTED", "VERIFIED"}
SECTIONS = {"GENERAL", "MANPOWER", "EQUIPMENT", "ACTIVITY"}
FILE_KINDS = {"pdf", "native", "attachment"}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _to_day_start(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        row = value
    else:
        row = datetime.combine(value, dt_time.min)
    return row.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _normalize_log_type(value: str | None) -> str:
    code = _upper(value)
    if code not in LOG_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported log_type: {value}")
    return code


def _normalize_status(value: str | None, default: str = "DRAFT") -> str:
    code = _upper(value) or _upper(default)
    if code not in STATUSES:
        raise HTTPException(status_code=400, detail=f"Unsupported status_code: {value}")
    return code


def _normalize_section(value: str | None) -> str:
    code = _upper(value) or "GENERAL"
    if code not in SECTIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported section_code: {value}")
    return code


def _normalize_file_kind(value: str | None) -> str:
    code = _norm(value).lower() or "attachment"
    if code not in FILE_KINDS:
        raise HTTPException(status_code=400, detail=f"Unsupported file_kind: {value}")
    return code


def _is_admin(user: User) -> bool:
    return bool(resolve_effective_access(user).is_system_admin)


def _category(user: User) -> str:
    return str(resolve_effective_access(user).permission_category or "").strip().lower()


def _require_contractor_flow(user: User) -> None:
    if _is_admin(user):
        return
    if _category(user) == OrganizationType.CONSULTANT.value:
        raise HTTPException(status_code=403, detail="Consultant users cannot create or submit site logs.")


def _require_consultant_flow(user: User) -> None:
    if _is_admin(user):
        return
    if _category(user) != OrganizationType.CONSULTANT.value:
        raise HTTPException(status_code=403, detail="Only consultant users can verify site logs.")


def _enforce_editable_draft(row: SiteLog, user: User) -> None:
    if _is_admin(user):
        return
    status = _upper(row.status_code)
    if status == "VERIFIED":
        raise HTTPException(status_code=409, detail="Verified site logs are read-only.")
    if status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only DRAFT site logs can be edited.")


def _enforce_not_verified_for_write(row: SiteLog, user: User) -> None:
    if _is_admin(user):
        return
    if _upper(row.status_code) == "VERIFIED":
        raise HTTPException(status_code=409, detail="Verified site logs are read-only.")


def _load_log_or_404(db: Session, log_id: int) -> SiteLog:
    row = (
        db.query(SiteLog)
        .options(
            joinedload(SiteLog.organization),
            joinedload(SiteLog.created_by),
            joinedload(SiteLog.submitted_by),
            joinedload(SiteLog.verified_by),
            joinedload(SiteLog.manpower_rows),
            joinedload(SiteLog.equipment_rows),
            joinedload(SiteLog.activity_rows),
        )
        .filter(SiteLog.id == log_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site log not found")
    return row


def _load_attachment_or_404(db: Session, attachment_id: int) -> SiteLogAttachment:
    row = (
        db.query(SiteLogAttachment)
        .options(joinedload(SiteLogAttachment.uploaded_by))
        .filter(SiteLogAttachment.id == attachment_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return row

def _enforce_log_scope(db: Session, user: User, row: SiteLog) -> None:
    enforce_scope_access(
        db,
        user,
        project_code=row.project_code,
        discipline_code=row.discipline_code,
    )
    enforce_organization_access(db, user, organization_id=row.organization_id)


def _check_project_and_discipline(db: Session, project_code: str, discipline_code: str) -> None:
    if not db.query(Project.code).filter(Project.code == _upper(project_code)).first():
        raise HTTPException(status_code=404, detail="Project not found")
    if not db.query(Discipline.code).filter(Discipline.code == _upper(discipline_code)).first():
        raise HTTPException(status_code=404, detail="Discipline not found")


def _check_optional_org(db: Session, org_id: int | None) -> None:
    if not org_id:
        return
    if not db.query(Organization.id).filter(Organization.id == int(org_id)).first():
        raise HTTPException(status_code=404, detail=f"Organization not found: {org_id}")


def _check_optional_user(db: Session, user_id: int | None) -> None:
    if not user_id:
        return
    if not db.query(DbUser.id).filter(DbUser.id == int(user_id)).first():
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")


def _next_log_no(db: Session, *, project_code: str, log_type: str, log_date: datetime) -> str:
    pcode = _upper(project_code)
    ltype = _upper(log_type)
    day = _to_day_start(log_date)
    if not day:
        raise HTTPException(status_code=400, detail="log_date is required")
    seq = (
        db.query(SiteLogSequence)
        .filter(
            SiteLogSequence.project_code == pcode,
            SiteLogSequence.log_type == ltype,
            SiteLogSequence.log_date == day,
        )
        .with_for_update()
        .first()
    )
    if seq:
        value = int(seq.next_value or 1)
        seq.next_value = value + 1
        seq.updated_at = datetime.utcnow()
        return f"{pcode}-SLOG-{ltype}-{day.strftime('%Y%m%d')}-{value:04d}"
    db.add(
        SiteLogSequence(
            project_code=pcode,
            log_type=ltype,
            log_date=day,
            next_value=2,
            updated_at=datetime.utcnow(),
        )
    )
    return f"{pcode}-SLOG-{ltype}-{day.strftime('%Y%m%d')}-0001"


def _record_status(db: Session, *, site_log_id: int, from_status: str | None, to_status: str, user_id: int | None, note: str | None = None) -> None:
    db.add(
        SiteLogStatusLog(
            site_log_id=site_log_id,
            from_status=_upper(from_status) or None,
            to_status=_upper(to_status),
            changed_by_id=user_id,
            changed_at=datetime.utcnow(),
            note=_norm(note) or None,
        )
    )


def _storage_dir(db: Session, row: SiteLog, section_code: str, file_kind: str) -> Path:
    base = StorageManager(db).get_correspondence_base_path()
    section = {
        "GENERAL": "General",
        "MANPOWER": "Manpower",
        "EQUIPMENT": "Equipment",
        "ACTIVITY": "Activity",
    }.get(_upper(section_code), "General")
    kind = {"pdf": "PDF", "native": "Native", "attachment": "Attachment"}.get(file_kind, "Attachment")
    slug = safe_name(row.log_no or f"SLOG-{row.id}")
    path = base / "site_logs" / slug / section / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def _has_verified_payload(manpower: list[dict[str, Any]], equipment: list[dict[str, Any]], activity: list[dict[str, Any]]) -> bool:
    return any(
        (row.get("verified_count") is not None or row.get("verified_hours") is not None) for row in manpower
    ) or any((row.get("verified_status") or row.get("verified_hours") is not None) for row in equipment) or any(
        (row.get("verified_progress_pct") is not None) for row in activity
    )


def _has_rows(row: SiteLog) -> bool:
    return bool(row.manpower_rows or row.equipment_rows or row.activity_rows)


def _has_verified_values(row: SiteLog) -> bool:
    return any((x.verified_count is not None or x.verified_hours is not None) for x in row.manpower_rows) or any(
        (_norm(x.verified_status) or x.verified_hours is not None) for x in row.equipment_rows
    ) or any((x.verified_progress_pct is not None) for x in row.activity_rows)


def _serialize(row: SiteLog, include_rows: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "log_no": row.log_no,
        "log_type": row.log_type,
        "project_code": row.project_code,
        "discipline_code": row.discipline_code,
        "organization_id": row.organization_id,
        "organization_name": row.organization.name if row.organization else None,
        "log_date": _to_iso(row.log_date),
        "weather": row.weather,
        "summary": row.summary,
        "status_code": row.status_code,
        "created_by_id": row.created_by_id,
        "created_by_name": row.created_by.full_name if row.created_by else None,
        "submitted_by_id": row.submitted_by_id,
        "submitted_by_name": row.submitted_by.full_name if row.submitted_by else None,
        "submitted_at": _to_iso(row.submitted_at),
        "verified_by_id": row.verified_by_id,
        "verified_by_name": row.verified_by.full_name if row.verified_by else None,
        "verified_at": _to_iso(row.verified_at),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
        "manpower_count": len(row.manpower_rows or []),
        "equipment_count": len(row.equipment_rows or []),
        "activity_count": len(row.activity_rows or []),
    }
    if include_rows:
        payload["manpower_rows"] = [
            {
                "id": x.id,
                "role_code": x.role_code,
                "role_label": x.role_label,
                "claimed_count": x.claimed_count,
                "claimed_hours": x.claimed_hours,
                "verified_count": x.verified_count,
                "verified_hours": x.verified_hours,
                "note": x.note,
                "sort_order": x.sort_order,
            }
            for x in sorted(row.manpower_rows, key=lambda v: (v.sort_order or 0, v.id or 0))
        ]
        payload["equipment_rows"] = [
            {
                "id": x.id,
                "equipment_code": x.equipment_code,
                "equipment_label": x.equipment_label,
                "claimed_status": x.claimed_status,
                "claimed_hours": x.claimed_hours,
                "verified_status": x.verified_status,
                "verified_hours": x.verified_hours,
                "note": x.note,
                "sort_order": x.sort_order,
            }
            for x in sorted(row.equipment_rows, key=lambda v: (v.sort_order or 0, v.id or 0))
        ]
        payload["activity_rows"] = [
            {
                "id": x.id,
                "activity_code": x.activity_code,
                "activity_title": x.activity_title,
                "source_system": x.source_system,
                "external_ref": x.external_ref,
                "claimed_progress_pct": x.claimed_progress_pct,
                "verified_progress_pct": x.verified_progress_pct,
                "note": x.note,
                "sort_order": x.sort_order,
            }
            for x in sorted(row.activity_rows, key=lambda v: (v.sort_order or 0, v.id or 0))
        ]
    return payload


def _serialize_status(row: SiteLogStatusLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "site_log_id": row.site_log_id,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "changed_by_id": row.changed_by_id,
        "changed_by_name": row.changed_by.full_name if row.changed_by else None,
        "changed_at": _to_iso(row.changed_at),
        "note": row.note,
    }


def _serialize_comment(row: SiteLogComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "site_log_id": row.site_log_id,
        "comment_text": row.comment_text,
        "comment_type": row.comment_type,
        "created_by_id": row.created_by_id,
        "created_by_name": row.created_by.full_name if row.created_by else None,
        "created_at": _to_iso(row.created_at),
    }


def _serialize_attachment(row: SiteLogAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "site_log_id": row.site_log_id,
        "section_code": row.section_code,
        "row_id": row.row_id,
        "file_name": row.file_name,
        "stored_path": row.stored_path,
        "file_kind": row.file_kind,
        "note": row.note,
        "mime_type": row.mime_type,
        "detected_mime": row.detected_mime,
        "validation_status": row.validation_status,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "uploaded_by_id": row.uploaded_by_id,
        "uploaded_by_name": row.uploaded_by.full_name if row.uploaded_by else None,
        "uploaded_at": _to_iso(row.uploaded_at),
    }

class ManpowerIn(BaseModel):
    role_code: Optional[str] = Field(default=None, max_length=64)
    role_label: Optional[str] = Field(default=None, max_length=255)
    claimed_count: Optional[int] = Field(default=None, ge=0)
    claimed_hours: Optional[float] = Field(default=None, ge=0)
    verified_count: Optional[int] = Field(default=None, ge=0)
    verified_hours: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    sort_order: Optional[int] = 0


class EquipmentIn(BaseModel):
    equipment_code: Optional[str] = Field(default=None, max_length=64)
    equipment_label: Optional[str] = Field(default=None, max_length=255)
    claimed_status: Optional[str] = Field(default=None, max_length=32)
    claimed_hours: Optional[float] = Field(default=None, ge=0)
    verified_status: Optional[str] = Field(default=None, max_length=32)
    verified_hours: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    sort_order: Optional[int] = 0


class ActivityIn(BaseModel):
    activity_code: Optional[str] = Field(default=None, max_length=64)
    activity_title: Optional[str] = Field(default=None, max_length=255)
    source_system: Optional[str] = Field(default="MANUAL", max_length=32)
    external_ref: Optional[str] = Field(default=None, max_length=128)
    claimed_progress_pct: Optional[float] = Field(default=None, ge=0, le=100)
    verified_progress_pct: Optional[float] = Field(default=None, ge=0, le=100)
    note: Optional[str] = None
    sort_order: Optional[int] = 0


class SiteLogCreateIn(BaseModel):
    log_type: str = Field(..., max_length=32)
    project_code: str = Field(..., max_length=50)
    discipline_code: str = Field(..., max_length=20)
    organization_id: Optional[int] = Field(default=None, ge=1)
    log_date: datetime | date
    weather: Optional[str] = Field(default=None, max_length=64)
    summary: Optional[str] = None
    status_code: Optional[str] = Field(default="DRAFT", max_length=32)
    manpower_rows: list[ManpowerIn] = Field(default_factory=list)
    equipment_rows: list[EquipmentIn] = Field(default_factory=list)
    activity_rows: list[ActivityIn] = Field(default_factory=list)


class SiteLogUpdateIn(BaseModel):
    log_type: Optional[str] = Field(default=None, max_length=32)
    project_code: Optional[str] = Field(default=None, max_length=50)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    organization_id: Optional[int] = Field(default=None, ge=1)
    log_date: Optional[datetime | date] = None
    weather: Optional[str] = Field(default=None, max_length=64)
    summary: Optional[str] = None
    manpower_rows: Optional[list[ManpowerIn]] = None
    equipment_rows: Optional[list[EquipmentIn]] = None
    activity_rows: Optional[list[ActivityIn]] = None


class SubmitIn(BaseModel):
    note: Optional[str] = None


class VerifyIn(BaseModel):
    note: Optional[str] = None
    manpower_rows: list[ManpowerIn] = Field(default_factory=list)
    equipment_rows: list[EquipmentIn] = Field(default_factory=list)
    activity_rows: list[ActivityIn] = Field(default_factory=list)


class CommentIn(BaseModel):
    comment_text: str = Field(..., min_length=1)
    comment_type: Optional[str] = Field(default="comment", max_length=32)


def _sanitize_manpower(rows: list[ManpowerIn] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows or []):
        row = {
            "role_code": _upper(r.role_code) or None,
            "role_label": _norm(r.role_label) or None,
            "claimed_count": _to_int(r.claimed_count),
            "claimed_hours": _to_float(r.claimed_hours),
            "verified_count": _to_int(r.verified_count),
            "verified_hours": _to_float(r.verified_hours),
            "note": _norm(r.note) or None,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any([row["role_code"], row["role_label"], row["claimed_count"] is not None, row["claimed_hours"] is not None, row["verified_count"] is not None, row["verified_hours"] is not None, row["note"]]):
            out.append(row)
    return out


def _sanitize_equipment(rows: list[EquipmentIn] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows or []):
        row = {
            "equipment_code": _upper(r.equipment_code) or None,
            "equipment_label": _norm(r.equipment_label) or None,
            "claimed_status": _upper(r.claimed_status) or None,
            "claimed_hours": _to_float(r.claimed_hours),
            "verified_status": _upper(r.verified_status) or None,
            "verified_hours": _to_float(r.verified_hours),
            "note": _norm(r.note) or None,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any([row["equipment_code"], row["equipment_label"], row["claimed_status"], row["claimed_hours"] is not None, row["verified_status"], row["verified_hours"] is not None, row["note"]]):
            out.append(row)
    return out


def _sanitize_activity(rows: list[ActivityIn] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows or []):
        row = {
            "activity_code": _upper(r.activity_code) or None,
            "activity_title": _norm(r.activity_title) or None,
            "source_system": _upper(r.source_system) or "MANUAL",
            "external_ref": _norm(r.external_ref) or None,
            "claimed_progress_pct": _to_float(r.claimed_progress_pct),
            "verified_progress_pct": _to_float(r.verified_progress_pct),
            "note": _norm(r.note) or None,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any([row["activity_code"], row["activity_title"], row["external_ref"], row["claimed_progress_pct"] is not None, row["verified_progress_pct"] is not None, row["note"]]):
            out.append(row)
    return out


def _replace_rows(row: SiteLog, manpower: list[dict[str, Any]] | None, equipment: list[dict[str, Any]] | None, activity: list[dict[str, Any]] | None) -> None:
    if manpower is not None:
        row.manpower_rows.clear()
        for p in manpower:
            row.manpower_rows.append(SiteLogManpowerRow(**p))
    if equipment is not None:
        row.equipment_rows.clear()
        for p in equipment:
            row.equipment_rows.append(SiteLogEquipmentRow(**p))
    if activity is not None:
        row.activity_rows.clear()
        for p in activity:
            row.activity_rows.append(SiteLogActivityRow(**p))


def _verify_update_rows(row: SiteLog, manpower: list[dict[str, Any]], equipment: list[dict[str, Any]], activity: list[dict[str, Any]]) -> None:
    if manpower:
        current = {int(x.sort_order or 0): x for x in row.manpower_rows}
        for p in manpower:
            key = int(p.get("sort_order") or 0)
            target = current.get(key) or SiteLogManpowerRow(sort_order=key)
            if target not in row.manpower_rows:
                row.manpower_rows.append(target)
            if p.get("verified_count") is not None:
                target.verified_count = p.get("verified_count")
            if p.get("verified_hours") is not None:
                target.verified_hours = p.get("verified_hours")
            if p.get("note") is not None:
                target.note = p.get("note")
    if equipment:
        current = {int(x.sort_order or 0): x for x in row.equipment_rows}
        for p in equipment:
            key = int(p.get("sort_order") or 0)
            target = current.get(key) or SiteLogEquipmentRow(sort_order=key)
            if target not in row.equipment_rows:
                row.equipment_rows.append(target)
            if p.get("verified_status") is not None:
                target.verified_status = p.get("verified_status")
            if p.get("verified_hours") is not None:
                target.verified_hours = p.get("verified_hours")
            if p.get("note") is not None:
                target.note = p.get("note")
    if activity:
        current = {int(x.sort_order or 0): x for x in row.activity_rows}
        for p in activity:
            key = int(p.get("sort_order") or 0)
            target = current.get(key) or SiteLogActivityRow(sort_order=key, source_system="MANUAL")
            if target not in row.activity_rows:
                row.activity_rows.append(target)
            if p.get("verified_progress_pct") is not None:
                target.verified_progress_pct = p.get("verified_progress_pct")
            if p.get("note") is not None:
                target.note = p.get("note")

@router.get("/catalog")
def catalog(db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:read"))):
    projects = apply_scope_query_filters(db.query(Project), db, user, project_column=Project.code, discipline_column=None).order_by(Project.code.asc()).all()
    disciplines = apply_scope_query_filters(db.query(Discipline), db, user, project_column=None, discipline_column=Discipline.code).order_by(Discipline.code.asc()).all()
    orgs = apply_organization_query_filters(db.query(Organization).filter(Organization.is_active == True), db, user, organization_column=Organization.id).order_by(Organization.name.asc()).all()
    statuses = db.query(SiteLogWorkflowStatus).filter(SiteLogWorkflowStatus.is_active == True).order_by(SiteLogWorkflowStatus.sort_order.asc(), SiteLogWorkflowStatus.code.asc()).all()
    role_catalog = db.query(SiteLogRoleCatalog).filter(SiteLogRoleCatalog.is_active == True).order_by(SiteLogRoleCatalog.sort_order.asc(), SiteLogRoleCatalog.code.asc()).all()
    equipment_catalog = db.query(SiteLogEquipmentCatalog).filter(SiteLogEquipmentCatalog.is_active == True).order_by(SiteLogEquipmentCatalog.sort_order.asc(), SiteLogEquipmentCatalog.code.asc()).all()
    equipment_status_catalog = db.query(SiteLogEquipmentStatusCatalog).filter(SiteLogEquipmentStatusCatalog.is_active == True).order_by(SiteLogEquipmentStatusCatalog.sort_order.asc(), SiteLogEquipmentStatusCatalog.code.asc()).all()
    return {
        "ok": True,
        "log_types": [{"code": "DAILY", "label": "Daily Report"}, {"code": "WEEKLY", "label": "Weekly Report"}, {"code": "SAFETY_INCIDENT", "label": "Safety Incident"}],
        "workflow_statuses": [{"code": x.code, "label": x.label, "sort_order": x.sort_order} for x in statuses],
        "section_codes": sorted(list(SECTIONS)),
        "projects": [{"code": x.code, "name": x.name_e or x.name_p or x.code} for x in projects],
        "disciplines": [{"code": x.code, "name": x.name_e or x.name_p or x.code} for x in disciplines],
        "organizations": [{"id": x.id, "name": x.name, "org_type": x.org_type} for x in orgs],
        "role_catalog": [{"code": x.code, "label": x.label} for x in role_catalog],
        "equipment_catalog": [{"code": x.code, "label": x.label} for x in equipment_catalog],
        "equipment_status_catalog": [{"code": x.code, "label": x.label} for x in equipment_status_catalog],
    }


@router.get("/list")
def list_logs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    module_key: Optional[str] = Query(default=None),
    tab_key: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    log_type: Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    log_date_from: Optional[datetime] = Query(default=None),
    log_date_to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:read")),
):
    q = db.query(SiteLog).options(joinedload(SiteLog.organization))
    q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=SiteLog.discipline_code)
    q = apply_organization_query_filters(q, db, user, organization_column=SiteLog.organization_id)
    if project_code:
        q = q.filter(SiteLog.project_code == _upper(project_code))
    if discipline_code:
        q = q.filter(SiteLog.discipline_code == _upper(discipline_code))
    if log_type:
        q = q.filter(SiteLog.log_type == _normalize_log_type(log_type))
    if status_code:
        q = q.filter(SiteLog.status_code == _normalize_status(status_code))
    if log_date_from:
        q = q.filter(SiteLog.log_date >= _to_day_start(log_date_from))
    if log_date_to:
        d = _to_day_start(log_date_to)
        if d:
            q = q.filter(SiteLog.log_date <= d.replace(hour=23, minute=59, second=59))
    if _norm(module_key).lower() == "consultant" and _norm(tab_key).lower() == "inspection" and not status_code:
        q = q.filter(SiteLog.status_code == "SUBMITTED")
    if _norm(search):
        pattern = f"%{_norm(search)}%"
        q = q.filter(or_(SiteLog.log_no.ilike(pattern), SiteLog.summary.ilike(pattern), SiteLog.weather.ilike(pattern)))
    total = q.count()
    rows = q.order_by(SiteLog.log_date.desc(), SiteLog.id.desc()).offset(skip).limit(limit).all()
    return {"ok": True, "total": total, "count": len(rows), "data": [_serialize(x, include_rows=False) for x in rows]}


@router.post("/create")
def create_log(payload: SiteLogCreateIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:create"))):
    _require_contractor_flow(user)
    pcode = _upper(payload.project_code)
    dcode = _upper(payload.discipline_code)
    ltype = _normalize_log_type(payload.log_type)
    status = _normalize_status(payload.status_code, "DRAFT")
    if not _is_admin(user) and status != "DRAFT":
        raise HTTPException(status_code=400, detail="Contractor users can only create DRAFT site logs.")
    ldate = _to_day_start(payload.log_date)
    if not ldate:
        raise HTTPException(status_code=400, detail="log_date is required")
    _check_project_and_discipline(db, pcode, dcode)
    enforce_scope_access(db, user, project_code=pcode, discipline_code=dcode)
    _check_optional_org(db, payload.organization_id)
    if payload.organization_id:
        enforce_organization_access(db, user, organization_id=payload.organization_id)
    manpower = _sanitize_manpower(payload.manpower_rows)
    equipment = _sanitize_equipment(payload.equipment_rows)
    activity = _sanitize_activity(payload.activity_rows)
    if not _is_admin(user) and _has_verified_payload(manpower, equipment, activity):
        raise HTTPException(status_code=403, detail="Contractor users cannot write verified values.")
    row = SiteLog(
        log_no=_next_log_no(db, project_code=pcode, log_type=ltype, log_date=ldate),
        log_type=ltype,
        project_code=pcode,
        discipline_code=dcode,
        organization_id=payload.organization_id,
        log_date=ldate,
        weather=_upper(payload.weather) or None,
        summary=_norm(payload.summary) or None,
        status_code=status,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    _replace_rows(row, manpower, equipment, activity)
    db.flush()
    _record_status(db, site_log_id=int(row.id), from_status=None, to_status=status, user_id=getattr(user, "id", None))
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, int(row.id)), include_rows=True)}

@router.get("/reports/volume")
def report_volume(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    log_type: Optional[str] = Query(default=None),
    log_date_from: Optional[datetime] = Query(default=None),
    log_date_to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:report_read")),
):
    q = db.query(SiteLog)
    q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=SiteLog.discipline_code)
    q = apply_organization_query_filters(q, db, user, organization_column=SiteLog.organization_id)
    if project_code:
        q = q.filter(SiteLog.project_code == _upper(project_code))
    if discipline_code:
        q = q.filter(SiteLog.discipline_code == _upper(discipline_code))
    if log_type:
        q = q.filter(SiteLog.log_type == _normalize_log_type(log_type))
    if log_date_from:
        q = q.filter(SiteLog.log_date >= _to_day_start(log_date_from))
    if log_date_to:
        d = _to_day_start(log_date_to)
        if d:
            q = q.filter(SiteLog.log_date <= d.replace(hour=23, minute=59, second=59))
    rows = q.all()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for x in rows:
        by_type[x.log_type] = by_type.get(x.log_type, 0) + 1
        by_status[x.status_code] = by_status.get(x.status_code, 0) + 1
    return {"ok": True, "count": len(rows), "summary": {"total": len(rows), "by_type": by_type, "by_status": by_status}}


@router.get("/reports/variance")
def report_variance(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    log_type: Optional[str] = Query(default=None),
    log_date_from: Optional[datetime] = Query(default=None),
    log_date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:report_read")),
):
    q = db.query(SiteLog).options(joinedload(SiteLog.manpower_rows), joinedload(SiteLog.equipment_rows), joinedload(SiteLog.activity_rows))
    q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=SiteLog.discipline_code)
    q = apply_organization_query_filters(q, db, user, organization_column=SiteLog.organization_id)
    if project_code:
        q = q.filter(SiteLog.project_code == _upper(project_code))
    if discipline_code:
        q = q.filter(SiteLog.discipline_code == _upper(discipline_code))
    if log_type:
        q = q.filter(SiteLog.log_type == _normalize_log_type(log_type))
    if log_date_from:
        q = q.filter(SiteLog.log_date >= _to_day_start(log_date_from))
    if log_date_to:
        d = _to_day_start(log_date_to)
        if d:
            q = q.filter(SiteLog.log_date <= d.replace(hour=23, minute=59, second=59))
    rows = q.order_by(SiteLog.log_date.desc(), SiteLog.id.desc()).limit(limit).all()
    data: list[dict[str, Any]] = []
    totals = {"manpower_count_delta": 0.0, "manpower_hours_delta": 0.0, "equipment_hours_delta": 0.0, "activity_progress_delta": 0.0}
    for x in rows:
        mc = sum(float(v.claimed_count or 0) for v in x.manpower_rows)
        mv = sum(float(v.verified_count or 0) for v in x.manpower_rows)
        mhc = sum(float(v.claimed_hours or 0) for v in x.manpower_rows)
        mhv = sum(float(v.verified_hours or 0) for v in x.manpower_rows)
        ehc = sum(float(v.claimed_hours or 0) for v in x.equipment_rows)
        ehv = sum(float(v.verified_hours or 0) for v in x.equipment_rows)
        apc = sum(float(v.claimed_progress_pct or 0) for v in x.activity_rows)
        apv = sum(float(v.verified_progress_pct or 0) for v in x.activity_rows)
        row = {
            "id": x.id,
            "log_no": x.log_no,
            "log_type": x.log_type,
            "log_date": _to_iso(x.log_date),
            "status_code": x.status_code,
            "manpower_count_delta": round(mv - mc, 2),
            "manpower_hours_delta": round(mhv - mhc, 2),
            "equipment_hours_delta": round(ehv - ehc, 2),
            "activity_progress_delta": round(apv - apc, 2),
        }
        data.append(row)
        totals["manpower_count_delta"] += row["manpower_count_delta"]
        totals["manpower_hours_delta"] += row["manpower_hours_delta"]
        totals["equipment_hours_delta"] += row["equipment_hours_delta"]
        totals["activity_progress_delta"] += row["activity_progress_delta"]
    for k in list(totals.keys()):
        totals[k] = round(float(totals[k]), 2)
    return {"ok": True, "count": len(data), "summary": totals, "data": data}


@router.get("/reports/progress")
def report_progress(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    log_type: Optional[str] = Query(default=None),
    log_date_from: Optional[datetime] = Query(default=None),
    log_date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:report_read")),
):
    q = db.query(SiteLog).options(joinedload(SiteLog.activity_rows))
    q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=SiteLog.discipline_code)
    q = apply_organization_query_filters(q, db, user, organization_column=SiteLog.organization_id)
    if project_code:
        q = q.filter(SiteLog.project_code == _upper(project_code))
    if discipline_code:
        q = q.filter(SiteLog.discipline_code == _upper(discipline_code))
    if log_type:
        q = q.filter(SiteLog.log_type == _normalize_log_type(log_type))
    if log_date_from:
        q = q.filter(SiteLog.log_date >= _to_day_start(log_date_from))
    if log_date_to:
        d = _to_day_start(log_date_to)
        if d:
            q = q.filter(SiteLog.log_date <= d.replace(hour=23, minute=59, second=59))
    rows = q.order_by(SiteLog.log_date.desc(), SiteLog.id.desc()).limit(limit).all()
    all_claimed: list[float] = []
    all_verified: list[float] = []
    data: list[dict[str, Any]] = []
    for x in rows:
        c = [float(v.claimed_progress_pct) for v in x.activity_rows if v.claimed_progress_pct is not None]
        v = [float(v.verified_progress_pct) for v in x.activity_rows if v.verified_progress_pct is not None]
        all_claimed.extend(c)
        all_verified.extend(v)
        data.append(
            {
                "id": x.id,
                "log_no": x.log_no,
                "log_type": x.log_type,
                "log_date": _to_iso(x.log_date),
                "status_code": x.status_code,
                "claimed_avg_progress_pct": round(sum(c) / len(c), 2) if c else None,
                "verified_avg_progress_pct": round(sum(v) / len(v), 2) if v else None,
            }
        )
    claimed = round(sum(all_claimed) / len(all_claimed), 2) if all_claimed else None
    verified = round(sum(all_verified) / len(all_verified), 2) if all_verified else None
    variance = round((verified or 0.0) - (claimed or 0.0), 2) if claimed is not None or verified is not None else None
    return {"ok": True, "count": len(data), "summary": {"claimed_avg_progress_pct": claimed, "verified_avg_progress_pct": verified, "variance_pct": variance}, "data": data}

@router.get("/{log_id}")
def get_log(log_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:read"))):
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    return {"ok": True, "data": _serialize(row, include_rows=True)}


@router.put("/{log_id}")
def update_log(log_id: int, payload: SiteLogUpdateIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:update"))):
    _require_contractor_flow(user)
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    _enforce_editable_draft(row, user)
    fields = set(payload.model_fields_set or set())
    if "project_code" in fields and payload.project_code is not None:
        _check_project_and_discipline(db, payload.project_code, row.discipline_code)
        enforce_scope_access(db, user, project_code=_upper(payload.project_code), discipline_code=row.discipline_code)
        row.project_code = _upper(payload.project_code)
    if "discipline_code" in fields and payload.discipline_code is not None:
        _check_project_and_discipline(db, row.project_code, payload.discipline_code)
        enforce_scope_access(db, user, project_code=row.project_code, discipline_code=_upper(payload.discipline_code))
        row.discipline_code = _upper(payload.discipline_code)
    if "organization_id" in fields:
        _check_optional_org(db, payload.organization_id)
        if payload.organization_id:
            enforce_organization_access(db, user, organization_id=payload.organization_id)
        row.organization_id = payload.organization_id
    if "log_type" in fields and payload.log_type is not None:
        row.log_type = _normalize_log_type(payload.log_type)
    if "log_date" in fields and payload.log_date is not None:
        ldate = _to_day_start(payload.log_date)
        if not ldate:
            raise HTTPException(status_code=400, detail="log_date is invalid")
        row.log_date = ldate
    if "weather" in fields:
        row.weather = _upper(payload.weather) or None
    if "summary" in fields:
        row.summary = _norm(payload.summary) or None
    manpower = _sanitize_manpower(payload.manpower_rows) if payload.manpower_rows is not None else None
    equipment = _sanitize_equipment(payload.equipment_rows) if payload.equipment_rows is not None else None
    activity = _sanitize_activity(payload.activity_rows) if payload.activity_rows is not None else None
    if not _is_admin(user) and _has_verified_payload(manpower or [], equipment or [], activity or []):
        raise HTTPException(status_code=403, detail="Contractor users cannot write verified values.")
    _replace_rows(row, manpower, equipment, activity)
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, log_id), include_rows=True)}


@router.post("/{log_id}/submit")
def submit_log(log_id: int, payload: SubmitIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:submit"))):
    _require_contractor_flow(user)
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    _enforce_editable_draft(row, user)
    if not row.project_code or not row.discipline_code or not row.log_date:
        raise HTTPException(status_code=400, detail="project_code, discipline_code and log_date are required.")
    if not _has_rows(row):
        raise HTTPException(status_code=400, detail="At least one row is required before submit.")
    prev = row.status_code
    row.status_code = "SUBMITTED"
    row.submitted_by_id = getattr(user, "id", None)
    row.submitted_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    _record_status(db, site_log_id=log_id, from_status=prev, to_status="SUBMITTED", user_id=getattr(user, "id", None), note=payload.note)
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, log_id), include_rows=True)}


@router.post("/{log_id}/verify")
def verify_log(log_id: int, payload: VerifyIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:verify"))):
    _require_consultant_flow(user)
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    if _upper(row.status_code) != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Only SUBMITTED site logs can be verified.")
    _verify_update_rows(
        row,
        _sanitize_manpower(payload.manpower_rows),
        _sanitize_equipment(payload.equipment_rows),
        _sanitize_activity(payload.activity_rows),
    )
    if not _has_verified_values(row):
        raise HTTPException(status_code=400, detail="At least one verified value is required.")
    prev = row.status_code
    row.status_code = "VERIFIED"
    row.verified_by_id = getattr(user, "id", None)
    row.verified_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    _record_status(db, site_log_id=log_id, from_status=prev, to_status="VERIFIED", user_id=getattr(user, "id", None), note=payload.note)
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, log_id), include_rows=True)}


@router.get("/{log_id}/timeline")
def timeline(log_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:read"))):
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    logs = db.query(SiteLogStatusLog).options(joinedload(SiteLogStatusLog.changed_by)).filter(SiteLogStatusLog.site_log_id == log_id).order_by(SiteLogStatusLog.changed_at.desc(), SiteLogStatusLog.id.desc()).all()
    return {"ok": True, "data": [_serialize_status(x) for x in logs]}


@router.get("/{log_id}/comments")
def list_comments(log_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:read"))):
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    rows = db.query(SiteLogComment).options(joinedload(SiteLogComment.created_by)).filter(SiteLogComment.site_log_id == log_id).order_by(SiteLogComment.created_at.desc(), SiteLogComment.id.desc()).all()
    return {"ok": True, "data": [_serialize_comment(x) for x in rows]}


@router.post("/{log_id}/comments")
def create_comment(log_id: int, payload: CommentIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:comment_create"))):
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    _enforce_not_verified_for_write(row, user)
    x = SiteLogComment(site_log_id=log_id, comment_text=_norm(payload.comment_text), comment_type=_norm(payload.comment_type) or "comment", created_by_id=getattr(user, "id", None), created_at=datetime.utcnow())
    db.add(x)
    db.commit()
    x = db.query(SiteLogComment).options(joinedload(SiteLogComment.created_by)).filter(SiteLogComment.id == x.id).first()
    return {"ok": True, "data": _serialize_comment(x)}

@router.get("/{log_id}/attachments")
def list_attachments(
    log_id: int,
    section_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:read")),
):
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    q = db.query(SiteLogAttachment).options(joinedload(SiteLogAttachment.uploaded_by)).filter(SiteLogAttachment.site_log_id == log_id)
    if section_code:
        q = q.filter(SiteLogAttachment.section_code == _normalize_section(section_code))
    rows = q.order_by(SiteLogAttachment.uploaded_at.desc(), SiteLogAttachment.id.desc()).all()
    data = [_serialize_attachment(x) for x in rows]
    grouped: dict[str, list[dict[str, Any]]] = {s: [] for s in sorted(list(SECTIONS))}
    for x in data:
        grouped.setdefault(_upper(x.get("section_code")), []).append(x)
    return {"ok": True, "data": data, "grouped": grouped}


@router.post("/{log_id}/attachments")
def upload_attachment(
    log_id: int,
    file: UploadFile = File(...),
    file_kind: str = Form("attachment"),
    section_code: str = Form("GENERAL"),
    row_id: Optional[int] = Form(None),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:attachment_upload")),
):
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    _enforce_not_verified_for_write(row, user)
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")
    fk = _normalize_file_kind(file_kind)
    sec = _normalize_section(section_code)
    now = datetime.utcnow()
    original = safe_name(file.filename)
    unique = safe_name(f"{now.strftime('%Y%m%d%H%M%S%f')}_{original}")
    folder = _storage_dir(db, row, sec, fk)
    saved = StorageManager(db).save_upload_secure(file=file, destination_folder=str(folder), new_name=unique, file_kind=fk)
    x = SiteLogAttachment(
        site_log_id=log_id,
        section_code=sec,
        row_id=row_id if row_id and row_id > 0 else None,
        file_name=original,
        stored_path=str(Path(saved.stored_path)),
        file_kind=fk,
        note=_norm(note) or None,
        mime_type=saved.declared_mime or _norm(file.content_type) or None,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        uploaded_by_id=getattr(user, "id", None),
        uploaded_at=datetime.utcnow(),
    )
    db.add(x)
    db.commit()
    x = db.query(SiteLogAttachment).options(joinedload(SiteLogAttachment.uploaded_by)).filter(SiteLogAttachment.id == x.id).first()
    return {"ok": True, "data": _serialize_attachment(x)}


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:read"))):
    row = _load_attachment_or_404(db, attachment_id)
    log = _load_log_or_404(db, row.site_log_id)
    _enforce_log_scope(db, user, log)
    path = Path(row.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path=str(path), filename=row.file_name, media_type=row.mime_type)


@router.delete("/{log_id}/attachments")
def delete_attachment(
    log_id: int,
    attachment_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:attachment_delete")),
):
    log = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, log)
    _enforce_not_verified_for_write(log, user)
    row = _load_attachment_or_404(db, attachment_id)
    if int(row.site_log_id or 0) != int(log_id):
        raise HTTPException(status_code=400, detail="Attachment does not belong to this site log.")
    path = Path(row.stored_path)
    db.delete(row)
    db.commit()
    try:
        if path.exists():
            os.remove(path)
    except Exception:
        pass
    return {"ok": True}
