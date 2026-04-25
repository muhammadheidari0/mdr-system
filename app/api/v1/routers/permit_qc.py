from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
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
    has_permission_for_user,
    require_permission,
)
from app.db.models import (
    Discipline,
    Organization,
    PermitQcPermit,
    PermitQcPermitAttachment,
    PermitQcPermitCheck,
    PermitQcPermitEvent,
    PermitQcPermitStation,
    PermitQcTemplate,
    PermitQcTemplateCheck,
    PermitQcTemplateStation,
    Project,
)
from app.services.access_control import resolve_effective_access
from app.services.folder_service import safe_name
from app.services.nextcloud_adapter import NextcloudAdapter
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import resolve_nextcloud_runtime

router = APIRouter(prefix="/permit-qc", tags=["Permit QC"])

PERMIT_STATUSES = (
    "DRAFT",
    "SUBMITTED",
    "UNDER_REVIEW",
    "RETURNED",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
)
PERMIT_STATUS_SET = set(PERMIT_STATUSES)
CONTRACTOR_MUTABLE_STATUSES = {"DRAFT", "RETURNED"}
CONTRACTOR_SUBMIT_STATUSES = {"DRAFT", "RETURNED"}
CONTRACTOR_CANCEL_STATUSES = {"DRAFT", "SUBMITTED", "RETURNED"}
CONSULTANT_REVIEWABLE_STATUSES = {"SUBMITTED", "UNDER_REVIEW"}

STATION_ACTIONS = {"APPROVE", "RETURN", "REJECT"}
STATION_STATUS_MAP = {
    "APPROVE": "APPROVED",
    "RETURN": "RETURNED",
    "REJECT": "REJECTED",
}
CHECK_TYPES = {"BOOLEAN", "TEXT", "NUMBER", "DATE"}

MODULE_KEYS = {"contractor", "consultant"}
CONSULTANT_CATEGORIES = {"consultant", "employer"}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _json_dumps(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False)


def _effective_role(user: User) -> str:
    return str(resolve_effective_access(user).effective_role or "").strip().lower()


def _permission_category(user: User) -> str:
    return str(resolve_effective_access(user).permission_category or "").strip().lower()


def _is_system_admin(user: User) -> bool:
    return bool(resolve_effective_access(user).is_system_admin)


def _module_key_or_400(value: str) -> str:
    module = _lower(value)
    if module not in MODULE_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid module_key: {value}")
    return module


def _status_or_400(value: str) -> str:
    status = _upper(value)
    if status not in PERMIT_STATUS_SET:
        raise HTTPException(status_code=400, detail=f"Invalid status: {value}")
    return status


def _check_type_or_default(value: str | None) -> str:
    normalized = _upper(value) or "BOOLEAN"
    if normalized not in CHECK_TYPES:
        return "TEXT"
    return normalized


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raw = _lower(value)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def _ensure_module_access(user: User, module_key: str) -> str:
    module = _module_key_or_400(module_key)
    if _is_system_admin(user):
        return module
    category = _permission_category(user)
    if module == "contractor" and category != "contractor":
        raise HTTPException(status_code=403, detail="Contractor module access denied.")
    if module == "consultant" and category not in CONSULTANT_CATEGORIES:
        raise HTTPException(status_code=403, detail="Consultant module access denied.")
    return module


def _ensure_consultant_template_access(user: User) -> None:
    if _is_system_admin(user):
        return
    category = _permission_category(user)
    if category not in CONSULTANT_CATEGORIES:
        raise HTTPException(
            status_code=403,
            detail="Template management is available only for consultant module access.",
        )


def _effective_read_module_key(user: User, requested: str | None) -> str:
    if requested:
        return _ensure_module_access(user, requested)
    category = _permission_category(user)
    fallback = "contractor" if category == "contractor" else "consultant"
    return _ensure_module_access(user, fallback)


def _record_event(
    db: Session,
    *,
    permit_id: int,
    event_type: str,
    created_by_id: int | None,
    station_id: int | None = None,
    from_status_code: str | None = None,
    to_status_code: str | None = None,
    note: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        PermitQcPermitEvent(
            permit_id=permit_id,
            station_id=station_id,
            event_type=_upper(event_type) or "EVENT",
            from_status_code=_upper(from_status_code) or None,
            to_status_code=_upper(to_status_code) or None,
            note=_norm(note) or None,
            payload_json=_json_dumps(payload),
            created_by_id=created_by_id,
            created_at=datetime.utcnow(),
        )
    )


def _require_project_and_discipline(db: Session, project_code: str, discipline_code: str) -> tuple[str, str]:
    project_value = _upper(project_code)
    discipline_value = _upper(discipline_code)
    if not project_value:
        raise HTTPException(status_code=400, detail="project_code is required")
    if not discipline_value:
        raise HTTPException(status_code=400, detail="discipline_code is required")

    project = db.query(Project.code).filter(Project.code == project_value).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    discipline = db.query(Discipline.code).filter(Discipline.code == discipline_value).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")
    return project_value, discipline_value


def _ensure_organization_exists(db: Session, organization_id: int | None, *, field_name: str) -> int | None:
    if not organization_id:
        return None
    org = db.query(Organization.id).filter(Organization.id == int(organization_id)).first()
    if not org:
        raise HTTPException(status_code=404, detail=f"{field_name} organization not found")
    return int(organization_id)


def _load_permit_or_404(db: Session, permit_id: int) -> PermitQcPermit:
    row = (
        db.query(PermitQcPermit)
        .options(
            joinedload(PermitQcPermit.project),
            joinedload(PermitQcPermit.discipline),
            joinedload(PermitQcPermit.organization),
            joinedload(PermitQcPermit.contractor_org),
            joinedload(PermitQcPermit.consultant_org),
            joinedload(PermitQcPermit.created_by),
            joinedload(PermitQcPermit.updated_by),
            joinedload(PermitQcPermit.stations).joinedload(PermitQcPermitStation.checks),
            joinedload(PermitQcPermit.attachments).joinedload(PermitQcPermitAttachment.uploaded_by),
            joinedload(PermitQcPermit.events).joinedload(PermitQcPermitEvent.created_by),
        )
        .filter(PermitQcPermit.id == int(permit_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Permit not found")
    return row


def _load_template_or_404(db: Session, template_id: int) -> PermitQcTemplate:
    row = (
        db.query(PermitQcTemplate)
        .options(
            joinedload(PermitQcTemplate.stations).joinedload(PermitQcTemplateStation.checks),
            joinedload(PermitQcTemplate.created_by),
            joinedload(PermitQcTemplate.updated_by),
        )
        .filter(PermitQcTemplate.id == int(template_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return row


def _resolve_template_for_permit(
    db: Session,
    *,
    template_id: int | None,
    project_code: str,
    discipline_code: str,
) -> PermitQcTemplate | None:
    if template_id:
        row = (
            db.query(PermitQcTemplate)
            .filter(
                PermitQcTemplate.id == int(template_id),
                PermitQcTemplate.is_active.is_(True),
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Active template not found")
        return row

    rows = (
        db.query(PermitQcTemplate)
        .filter(
            PermitQcTemplate.is_active.is_(True),
            or_(PermitQcTemplate.project_code == project_code, PermitQcTemplate.project_code.is_(None)),
            or_(
                PermitQcTemplate.discipline_code == discipline_code,
                PermitQcTemplate.discipline_code.is_(None),
            ),
        )
        .all()
    )
    if not rows:
        return None

    def _score(row: PermitQcTemplate) -> tuple[int, int]:
        score = 0
        if _upper(row.project_code) == project_code:
            score += 4
        if _upper(row.discipline_code) == discipline_code:
            score += 2
        if bool(row.is_default):
            score += 1
        return score, int(row.id or 0)

    rows.sort(key=_score, reverse=True)
    return rows[0]


def _build_station_snapshot(
    db: Session,
    *,
    permit: PermitQcPermit,
    template: PermitQcTemplate,
) -> None:
    template_stations = (
        db.query(PermitQcTemplateStation)
        .filter(
            PermitQcTemplateStation.template_id == int(template.id),
            PermitQcTemplateStation.is_active.is_(True),
        )
        .order_by(PermitQcTemplateStation.sort_order.asc(), PermitQcTemplateStation.id.asc())
        .all()
    )
    if not template_stations:
        raise HTTPException(status_code=400, detail="Template has no active stations.")

    station_map: dict[int, PermitQcPermitStation] = {}
    for src in template_stations:
        target = PermitQcPermitStation(
            permit_id=int(permit.id),
            template_station_id=int(src.id),
            station_key=_norm(src.station_key),
            station_label=_norm(src.station_label),
            organization_id=src.organization_id,
            is_required=bool(src.is_required),
            sort_order=int(src.sort_order or 0),
            status_code="PENDING",
        )
        db.add(target)
        db.flush()
        station_map[int(src.id)] = target

    template_station_ids = [int(row.id) for row in template_stations]
    template_checks = (
        db.query(PermitQcTemplateCheck)
        .filter(
            PermitQcTemplateCheck.station_id.in_(template_station_ids),
            PermitQcTemplateCheck.is_active.is_(True),
        )
        .order_by(PermitQcTemplateCheck.sort_order.asc(), PermitQcTemplateCheck.id.asc())
        .all()
    )
    for src in template_checks:
        permit_station = station_map.get(int(src.station_id))
        if not permit_station:
            continue
        db.add(
            PermitQcPermitCheck(
                permit_station_id=int(permit_station.id),
                template_check_id=int(src.id),
                check_code=_norm(src.check_code),
                check_label=_norm(src.check_label),
                check_type=_check_type_or_default(src.check_type),
                is_required=bool(src.is_required),
                sort_order=int(src.sort_order or 0),
            )
        )
    db.flush()


def _normalize_review_status(statuses: list[str], required_flags: list[bool]) -> str:
    normalized = [_upper(value) for value in statuses]
    if any(value == "REJECTED" for value in normalized):
        return "REJECTED"
    if any(value == "RETURNED" for value in normalized):
        return "RETURNED"

    required_indices = [idx for idx, required in enumerate(required_flags) if bool(required)]
    if required_indices:
        if all(normalized[idx] == "APPROVED" for idx in required_indices):
            return "APPROVED"
    elif normalized and all(value == "APPROVED" for value in normalized):
        return "APPROVED"
    return "UNDER_REVIEW"


def _recompute_permit_status(db: Session, permit: PermitQcPermit) -> str:
    rows = (
        db.query(PermitQcPermitStation.status_code, PermitQcPermitStation.is_required)
        .filter(PermitQcPermitStation.permit_id == int(permit.id))
        .all()
    )
    if not rows:
        return "SUBMITTED"
    statuses = [str(status or "") for status, _ in rows]
    required_flags = [bool(required) for _, required in rows]
    return _normalize_review_status(statuses, required_flags)


def _set_status_fields(permit: PermitQcPermit, status_code: str) -> None:
    now = datetime.utcnow()
    status = _status_or_400(status_code)
    permit.status_code = status
    if status == "SUBMITTED":
        permit.submitted_at = now
    if status == "APPROVED":
        permit.approved_at = now
    if status == "REJECTED":
        permit.rejected_at = now
    if status == "CANCELLED":
        permit.cancelled_at = now


def _permit_attachment_dir(db: Session, permit: PermitQcPermit) -> Path:
    storage_manager = StorageManager(db)
    base = storage_manager.get_correspondence_base_path()
    permit_code = safe_name(permit.permit_no or f"permit-{permit.id}")
    project_code = safe_name(permit.project_code or "project")
    path = base / "permit_qc" / project_code / permit_code / "attachments"
    if not storage_manager._is_webdav_primary_mode():
        path.mkdir(parents=True, exist_ok=True)
    return path


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


def _download_webdav_attachment(db: Session, row: PermitQcPermitAttachment) -> StreamingResponse:
    stored_path = str(row.stored_path or "").strip()
    remote_path = stored_path.replace("webdav://", "", 1)
    adapter = _nextcloud_adapter_for_webdav(db)
    if not adapter.file_exists(remote_path):
        raise HTTPException(status_code=404, detail="Attachment file not found")
    filename = safe_name(row.file_name or f"attachment-{row.id}") or f"attachment-{row.id}"
    media_type = _norm(row.mime_type or row.detected_mime) or "application/octet-stream"
    return StreamingResponse(
        adapter.download_file_stream(remote_path),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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


def _serialize_template_check(row: PermitQcTemplateCheck) -> dict[str, Any]:
    return {
        "id": row.id,
        "station_id": row.station_id,
        "check_code": row.check_code,
        "check_label": row.check_label,
        "check_type": row.check_type,
        "is_required": bool(row.is_required),
        "is_active": bool(row.is_active),
        "sort_order": int(row.sort_order or 0),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _serialize_template_station(row: PermitQcTemplateStation) -> dict[str, Any]:
    checks = sorted(
        list(row.checks or []),
        key=lambda item: (int(item.sort_order or 0), int(item.id or 0)),
    )
    return {
        "id": row.id,
        "template_id": row.template_id,
        "station_key": row.station_key,
        "station_label": row.station_label,
        "organization_id": row.organization_id,
        "organization_name": getattr(getattr(row, "organization", None), "name", None),
        "is_required": bool(row.is_required),
        "is_active": bool(row.is_active),
        "sort_order": int(row.sort_order or 0),
        "checks": [_serialize_template_check(check) for check in checks],
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _serialize_template(row: PermitQcTemplate) -> dict[str, Any]:
    stations = sorted(
        list(row.stations or []),
        key=lambda item: (int(item.sort_order or 0), int(item.id or 0)),
    )
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "project_code": row.project_code,
        "discipline_code": row.discipline_code,
        "is_active": bool(row.is_active),
        "is_default": bool(row.is_default),
        "station_count": len(stations),
        "check_count": sum(len(station.checks or []) for station in stations),
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "updated_by_id": row.updated_by_id,
        "updated_by_name": getattr(getattr(row, "updated_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
        "stations": [_serialize_template_station(station) for station in stations],
    }


def _serialize_permit_check(row: PermitQcPermitCheck) -> dict[str, Any]:
    return {
        "id": row.id,
        "permit_station_id": row.permit_station_id,
        "template_check_id": row.template_check_id,
        "check_code": row.check_code,
        "check_label": row.check_label,
        "check_type": row.check_type,
        "is_required": bool(row.is_required),
        "sort_order": int(row.sort_order or 0),
        "value_text": row.value_text,
        "value_bool": row.value_bool,
        "value_number": row.value_number,
        "value_date": _to_iso(row.value_date),
        "note": row.note,
    }


def _serialize_permit_station(row: PermitQcPermitStation) -> dict[str, Any]:
    checks = sorted(
        list(row.checks or []),
        key=lambda item: (int(item.sort_order or 0), int(item.id or 0)),
    )
    return {
        "id": row.id,
        "permit_id": row.permit_id,
        "template_station_id": row.template_station_id,
        "station_key": row.station_key,
        "station_label": row.station_label,
        "organization_id": row.organization_id,
        "organization_name": getattr(getattr(row, "organization", None), "name", None),
        "is_required": bool(row.is_required),
        "sort_order": int(row.sort_order or 0),
        "status_code": row.status_code,
        "reviewed_by_id": row.reviewed_by_id,
        "reviewed_by_name": getattr(getattr(row, "reviewed_by", None), "full_name", None),
        "reviewed_at": _to_iso(row.reviewed_at),
        "review_note": row.review_note,
        "checks": [_serialize_permit_check(check) for check in checks],
    }


def _serialize_attachment(row: PermitQcPermitAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "permit_id": row.permit_id,
        "file_name": row.file_name,
        "stored_path": row.stored_path,
        "file_kind": row.file_kind,
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


def _serialize_event(row: PermitQcPermitEvent) -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    raw_payload = _norm(row.payload_json)
    if raw_payload:
        try:
            parsed = json.loads(raw_payload)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            payload = None
    return {
        "id": row.id,
        "permit_id": row.permit_id,
        "station_id": row.station_id,
        "event_type": row.event_type,
        "from_status_code": row.from_status_code,
        "to_status_code": row.to_status_code,
        "note": row.note,
        "payload": payload,
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
    }


def _allowed_actions(db: Session, user: User, permit: PermitQcPermit | None, *, module_key: str) -> dict[str, bool]:
    module = _module_key_or_400(module_key)
    can_read = has_permission_for_user(db, user, "permit_qc:read")
    can_create = has_permission_for_user(db, user, "permit_qc:create")
    can_update = has_permission_for_user(db, user, "permit_qc:update")
    can_submit = has_permission_for_user(db, user, "permit_qc:submit")
    can_review = has_permission_for_user(db, user, "permit_qc:review")
    can_upload = has_permission_for_user(db, user, "permit_qc:attachment_upload")
    can_delete = has_permission_for_user(db, user, "permit_qc:attachment_delete")
    can_template = has_permission_for_user(db, user, "permit_qc:template_manage")

    actions = {
        "read": can_read,
        "create": False,
        "update": False,
        "submit": False,
        "resubmit": False,
        "cancel": False,
        "review": False,
        "attachment_upload": False,
        "attachment_delete": False,
        "template_manage": False,
    }

    if module == "contractor":
        actions["create"] = can_create
        actions["attachment_upload"] = can_upload
        actions["attachment_delete"] = can_delete
        if permit:
            status = _upper(permit.status_code)
            actions["update"] = can_update and status in CONTRACTOR_MUTABLE_STATUSES
            actions["submit"] = can_submit and status == "DRAFT"
            actions["resubmit"] = can_submit and status == "RETURNED"
            actions["cancel"] = can_submit and status in CONTRACTOR_CANCEL_STATUSES
        return actions

    actions["review"] = can_review
    actions["attachment_upload"] = can_upload
    actions["attachment_delete"] = can_delete
    actions["template_manage"] = can_template
    if permit:
        status = _upper(permit.status_code)
        actions["review"] = can_review and status in CONSULTANT_REVIEWABLE_STATUSES
    return actions


def _serialize_permit_summary(db: Session, user: User, row: PermitQcPermit, *, module_key: str) -> dict[str, Any]:
    stations = list(row.stations or [])
    required_total = sum(1 for station in stations if bool(station.is_required))
    required_approved = sum(
        1 for station in stations if bool(station.is_required) and _upper(station.status_code) == "APPROVED"
    )
    return {
        "id": row.id,
        "permit_no": row.permit_no,
        "permit_date": _to_iso(row.permit_date),
        "title": row.title,
        "description": row.description,
        "wall_name": row.wall_name,
        "floor_label": row.floor_label,
        "elevation_start": row.elevation_start,
        "elevation_end": row.elevation_end,
        "status_code": row.status_code,
        "project_code": row.project_code,
        "discipline_code": row.discipline_code,
        "template_id": row.template_id,
        "organization_id": row.organization_id,
        "contractor_org_id": row.contractor_org_id,
        "consultant_org_id": row.consultant_org_id,
        "contractor_org_name": getattr(getattr(row, "contractor_org", None), "name", None),
        "consultant_org_name": getattr(getattr(row, "consultant_org", None), "name", None),
        "submitted_at": _to_iso(row.submitted_at),
        "approved_at": _to_iso(row.approved_at),
        "rejected_at": _to_iso(row.rejected_at),
        "cancelled_at": _to_iso(row.cancelled_at),
        "created_by_id": row.created_by_id,
        "created_by_name": getattr(getattr(row, "created_by", None), "full_name", None),
        "updated_by_id": row.updated_by_id,
        "updated_by_name": getattr(getattr(row, "updated_by", None), "full_name", None),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
        "station_total": len(stations),
        "required_station_total": required_total,
        "required_station_approved": required_approved,
        "allowed_actions": _allowed_actions(db, user, row, module_key=module_key),
    }


def _serialize_permit_detail(db: Session, user: User, row: PermitQcPermit, *, module_key: str) -> dict[str, Any]:
    stations = sorted(
        list(row.stations or []),
        key=lambda item: (int(item.sort_order or 0), int(item.id or 0)),
    )
    attachments = sorted(
        list(row.attachments or []),
        key=lambda item: (item.uploaded_at or datetime.min, int(item.id or 0)),
        reverse=True,
    )
    events = sorted(
        list(row.events or []),
        key=lambda item: (item.created_at or datetime.min, int(item.id or 0)),
        reverse=True,
    )
    payload = _serialize_permit_summary(db, user, row, module_key=module_key)
    payload["stations"] = [_serialize_permit_station(station) for station in stations]
    payload["attachments"] = [_serialize_attachment(attachment) for attachment in attachments]
    payload["timeline"] = [_serialize_event(event) for event in events]
    return payload


def _enforce_permit_module_access(db: Session, user: User, permit: PermitQcPermit, *, module_key: str) -> str:
    module = _ensure_module_access(user, module_key)
    enforce_scope_access(
        db,
        user,
        project_code=permit.project_code,
        discipline_code=permit.discipline_code,
    )
    if _is_system_admin(user):
        return module

    if module == "contractor":
        target_org_id = int(permit.contractor_org_id or permit.organization_id or 0) or None
        enforce_organization_access(db, user, organization_id=target_org_id)
        return module

    user_org_id = int(getattr(user, "organization_id", 0) or 0)
    permit_org_id = int(permit.consultant_org_id or 0)
    if permit_org_id > 0 and user_org_id > 0 and permit_org_id != user_org_id:
        raise HTTPException(status_code=403, detail="Consultant organization access denied.")
    return module


class PermitQcCreateIn(BaseModel):
    module_key: str = Field(default="contractor", max_length=32)
    permit_no: str = Field(..., min_length=1, max_length=128)
    permit_date: Optional[datetime] = None
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    wall_name: Optional[str] = Field(default=None, max_length=255)
    floor_label: Optional[str] = Field(default=None, max_length=64)
    elevation_start: Optional[str] = Field(default=None, max_length=64)
    elevation_end: Optional[str] = Field(default=None, max_length=64)
    project_code: str = Field(..., min_length=1, max_length=50)
    discipline_code: str = Field(..., min_length=1, max_length=20)
    template_id: Optional[int] = Field(default=None, ge=1)
    consultant_org_id: Optional[int] = Field(default=None, ge=1)


class PermitQcUpdateIn(BaseModel):
    permit_no: Optional[str] = Field(default=None, min_length=1, max_length=128)
    permit_date: Optional[datetime] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    wall_name: Optional[str] = Field(default=None, max_length=255)
    floor_label: Optional[str] = Field(default=None, max_length=64)
    elevation_start: Optional[str] = Field(default=None, max_length=64)
    elevation_end: Optional[str] = Field(default=None, max_length=64)
    project_code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    discipline_code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    template_id: Optional[int] = Field(default=None, ge=1)
    consultant_org_id: Optional[int] = Field(default=None, ge=1)


class PermitQcReviewCheckIn(BaseModel):
    check_id: int = Field(..., ge=1)
    value_text: Optional[str] = None
    value_bool: Optional[bool] = None
    value_number: Optional[float] = None
    value_date: Optional[datetime] = None
    note: Optional[str] = None


class PermitQcReviewIn(BaseModel):
    station_id: int = Field(..., ge=1)
    action: str = Field(..., min_length=1, max_length=16)
    note: Optional[str] = None
    checks: list[PermitQcReviewCheckIn] = Field(default_factory=list)


class PermitQcTemplateUpsertIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    code: Optional[str] = Field(default=None, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    project_code: Optional[str] = Field(default=None, max_length=50)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    is_active: bool = True
    is_default: bool = False


class PermitQcTemplateStationUpsertIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    station_key: str = Field(..., min_length=1, max_length=64)
    station_label: str = Field(..., min_length=1, max_length=255)
    organization_id: Optional[int] = Field(default=None, ge=1)
    is_required: bool = True
    is_active: bool = True
    sort_order: int = 0


class PermitQcTemplateCheckUpsertIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    station_id: int = Field(..., ge=1)
    check_code: str = Field(..., min_length=1, max_length=64)
    check_label: str = Field(..., min_length=1, max_length=255)
    check_type: str = Field(default="BOOLEAN", max_length=32)
    is_required: bool = True
    is_active: bool = True
    sort_order: int = 0


class PermitQcTemplateActivateIn(BaseModel):
    is_active: bool = True
    is_default: Optional[bool] = None


@router.get("/catalog")
def permit_qc_catalog(
    module_key: str = Query(..., min_length=1),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:read")),
):
    module = _ensure_module_access(user, module_key)

    query = db.query(PermitQcPermit)
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=PermitQcPermit.project_code,
        discipline_column=PermitQcPermit.discipline_code,
    )
    if module == "contractor":
        query = apply_organization_query_filters(
            query,
            db,
            user,
            organization_column=PermitQcPermit.contractor_org_id,
        )
    else:
        user_org_id = int(getattr(user, "organization_id", 0) or 0)
        if not _is_system_admin(user) and user_org_id > 0:
            query = query.filter(
                or_(
                    PermitQcPermit.consultant_org_id == user_org_id,
                    PermitQcPermit.consultant_org_id.is_(None),
                )
            )

    project_value = _upper(project_code)
    discipline_value = _upper(discipline_code)
    if project_value:
        query = query.filter(PermitQcPermit.project_code == project_value)
    if discipline_value:
        query = query.filter(PermitQcPermit.discipline_code == discipline_value)

    rows = query.all()
    counters = {status: 0 for status in PERMIT_STATUSES}
    for row in rows:
        status = _upper(row.status_code)
        if status in counters:
            counters[status] += 1

    template_query = db.query(PermitQcTemplate).filter(PermitQcTemplate.is_active.is_(True))
    if project_value:
        template_query = template_query.filter(
            or_(PermitQcTemplate.project_code == project_value, PermitQcTemplate.project_code.is_(None))
        )
    if discipline_value:
        template_query = template_query.filter(
            or_(PermitQcTemplate.discipline_code == discipline_value, PermitQcTemplate.discipline_code.is_(None))
        )
    templates = template_query.all()
    default_template = next((row for row in templates if bool(row.is_default)), None)

    return {
        "ok": True,
        "module_key": module,
        "statuses": list(PERMIT_STATUSES),
        "actions": _allowed_actions(db, user, None, module_key=module),
        "badge_counters": {
            "total": len(rows),
            **{key.lower(): value for key, value in counters.items()},
        },
        "template_summary": {
            "active_count": len(templates),
            "default_template_id": getattr(default_template, "id", None),
            "default_template_name": getattr(default_template, "name", None),
        },
    }


@router.get("/list")
def permit_qc_list(
    module_key: str = Query(..., min_length=1),
    status_code: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    permit_no: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:read")),
):
    module = _ensure_module_access(user, module_key)
    query = db.query(PermitQcPermit).options(joinedload(PermitQcPermit.stations))
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=PermitQcPermit.project_code,
        discipline_column=PermitQcPermit.discipline_code,
    )

    if module == "contractor":
        query = apply_organization_query_filters(
            query,
            db,
            user,
            organization_column=PermitQcPermit.contractor_org_id,
        )
    else:
        user_org_id = int(getattr(user, "organization_id", 0) or 0)
        if not _is_system_admin(user) and user_org_id > 0:
            query = query.filter(
                or_(
                    PermitQcPermit.consultant_org_id == user_org_id,
                    PermitQcPermit.consultant_org_id.is_(None),
                )
            )

    status_value = _upper(status_code)
    if status_value:
        query = query.filter(PermitQcPermit.status_code == _status_or_400(status_value))
    project_value = _upper(project_code)
    if project_value:
        enforce_scope_access(db, user, project_code=project_value)
        query = query.filter(PermitQcPermit.project_code == project_value)
    discipline_value = _upper(discipline_code)
    if discipline_value:
        enforce_scope_access(db, user, discipline_code=discipline_value)
        query = query.filter(PermitQcPermit.discipline_code == discipline_value)
    permit_no_value = _norm(permit_no)
    if permit_no_value:
        query = query.filter(PermitQcPermit.permit_no.ilike(f"%{permit_no_value}%"))
    if date_from:
        query = query.filter(PermitQcPermit.permit_date >= date_from)
    if date_to:
        query = query.filter(PermitQcPermit.permit_date <= date_to)

    total = query.count()
    rows = (
        query.order_by(PermitQcPermit.created_at.desc(), PermitQcPermit.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "ok": True,
        "total": total,
        "data": [
            _serialize_permit_summary(db, user, row, module_key=module)
            for row in rows
        ],
    }


@router.post("/create")
def permit_qc_create(
    payload: PermitQcCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:create")),
):
    _ensure_module_access(user, payload.module_key or "contractor")
    _ensure_module_access(user, "contractor")

    project_value, discipline_value = _require_project_and_discipline(
        db,
        payload.project_code,
        payload.discipline_code,
    )
    enforce_scope_access(
        db,
        user,
        project_code=project_value,
        discipline_code=discipline_value,
    )

    contractor_org_id = int(getattr(user, "organization_id", 0) or 0) or None
    enforce_organization_access(db, user, organization_id=contractor_org_id)
    consultant_org_id = _ensure_organization_exists(
        db,
        payload.consultant_org_id,
        field_name="consultant_org_id",
    )

    permit_no_value = _norm(payload.permit_no)
    if not permit_no_value:
        raise HTTPException(status_code=400, detail="permit_no is required")
    exists = (
        db.query(PermitQcPermit.id)
        .filter(
            PermitQcPermit.project_code == project_value,
            PermitQcPermit.permit_no == permit_no_value,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Permit number already exists for this project.")

    template = _resolve_template_for_permit(
        db,
        template_id=payload.template_id,
        project_code=project_value,
        discipline_code=discipline_value,
    )
    row = PermitQcPermit(
        permit_no=permit_no_value,
        permit_date=payload.permit_date,
        title=_norm(payload.title),
        description=_norm(payload.description) or None,
        wall_name=_norm(payload.wall_name) or None,
        floor_label=_norm(payload.floor_label) or None,
        elevation_start=_norm(payload.elevation_start) or None,
        elevation_end=_norm(payload.elevation_end) or None,
        status_code="DRAFT",
        project_code=project_value,
        discipline_code=discipline_value,
        template_id=getattr(template, "id", None),
        organization_id=contractor_org_id,
        contractor_org_id=contractor_org_id,
        consultant_org_id=consultant_org_id,
        created_by_id=getattr(user, "id", None),
        updated_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    _record_event(
        db,
        permit_id=int(row.id),
        event_type="CREATE",
        created_by_id=getattr(user, "id", None),
        to_status_code="DRAFT",
    )
    db.commit()
    row = _load_permit_or_404(db, int(row.id))
    return {
        "ok": True,
        "data": _serialize_permit_detail(db, user, row, module_key="contractor"),
    }


@router.get("/{permit_id:int}")
def permit_qc_get(
    permit_id: int,
    module_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:read")),
):
    row = _load_permit_or_404(db, permit_id)
    module = _enforce_permit_module_access(db, user, row, module_key=_effective_read_module_key(user, module_key))
    return {"ok": True, "data": _serialize_permit_detail(db, user, row, module_key=module)}


@router.put("/{permit_id:int}")
def permit_qc_update(
    permit_id: int,
    payload: PermitQcUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:update")),
):
    row = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, row, module_key="contractor")
    status = _upper(row.status_code)
    if status not in CONTRACTOR_MUTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Update is allowed only in DRAFT or RETURNED.")

    provided = set(payload.model_fields_set)
    if "permit_no" in provided:
        permit_no_value = _norm(payload.permit_no)
        if not permit_no_value:
            raise HTTPException(status_code=400, detail="permit_no cannot be empty")
        duplicate = (
            db.query(PermitQcPermit.id)
            .filter(
                PermitQcPermit.id != int(row.id),
                PermitQcPermit.project_code == row.project_code,
                PermitQcPermit.permit_no == permit_no_value,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Permit number already exists for this project.")
        row.permit_no = permit_no_value

    if "permit_date" in provided:
        row.permit_date = payload.permit_date
    if "title" in provided:
        title_value = _norm(payload.title)
        if not title_value:
            raise HTTPException(status_code=400, detail="title cannot be empty")
        row.title = title_value
    if "description" in provided:
        row.description = _norm(payload.description) or None
    if "wall_name" in provided:
        row.wall_name = _norm(payload.wall_name) or None
    if "floor_label" in provided:
        row.floor_label = _norm(payload.floor_label) or None
    if "elevation_start" in provided:
        row.elevation_start = _norm(payload.elevation_start) or None
    if "elevation_end" in provided:
        row.elevation_end = _norm(payload.elevation_end) or None

    project_value = _upper(payload.project_code) if "project_code" in provided else _upper(row.project_code)
    discipline_value = (
        _upper(payload.discipline_code) if "discipline_code" in provided else _upper(row.discipline_code)
    )
    if "project_code" in provided or "discipline_code" in provided:
        project_value, discipline_value = _require_project_and_discipline(
            db,
            project_value,
            discipline_value,
        )
        enforce_scope_access(
            db,
            user,
            project_code=project_value,
            discipline_code=discipline_value,
        )
        row.project_code = project_value
        row.discipline_code = discipline_value

    if "consultant_org_id" in provided:
        row.consultant_org_id = _ensure_organization_exists(
            db,
            payload.consultant_org_id,
            field_name="consultant_org_id",
        )

    if "template_id" in provided:
        if payload.template_id:
            template = _resolve_template_for_permit(
                db,
                template_id=payload.template_id,
                project_code=_upper(row.project_code),
                discipline_code=_upper(row.discipline_code),
            )
            row.template_id = getattr(template, "id", None)
        else:
            row.template_id = None

    row.updated_by_id = getattr(user, "id", None)
    row.updated_at = datetime.utcnow()
    _record_event(
        db,
        permit_id=int(row.id),
        event_type="UPDATE",
        created_by_id=getattr(user, "id", None),
        from_status_code=row.status_code,
        to_status_code=row.status_code,
    )
    db.commit()
    row = _load_permit_or_404(db, int(row.id))
    return {"ok": True, "data": _serialize_permit_detail(db, user, row, module_key="contractor")}


@router.post("/{permit_id:int}/submit")
def permit_qc_submit(
    permit_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:submit")),
):
    row = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, row, module_key="contractor")
    current = _upper(row.status_code)
    if current not in CONTRACTOR_SUBMIT_STATUSES:
        raise HTTPException(status_code=409, detail="Submit is allowed only from DRAFT or RETURNED.")

    if not list(row.stations or []):
        template = _resolve_template_for_permit(
            db,
            template_id=row.template_id,
            project_code=_upper(row.project_code),
            discipline_code=_upper(row.discipline_code),
        )
        if not template:
            raise HTTPException(status_code=400, detail="No active template found for this permit.")
        row.template_id = int(template.id)
        _build_station_snapshot(db, permit=row, template=template)
        db.refresh(row)

    if current == "RETURNED":
        for station in list(row.stations or []):
            if _upper(station.status_code) == "RETURNED":
                station.status_code = "PENDING"
                station.reviewed_by_id = None
                station.reviewed_at = None
                station.review_note = None

    previous = row.status_code
    _set_status_fields(row, "SUBMITTED")
    row.updated_by_id = getattr(user, "id", None)
    row.updated_at = datetime.utcnow()
    _record_event(
        db,
        permit_id=int(row.id),
        event_type="SUBMIT" if current == "DRAFT" else "RESUBMIT",
        created_by_id=getattr(user, "id", None),
        from_status_code=previous,
        to_status_code="SUBMITTED",
    )
    db.commit()
    row = _load_permit_or_404(db, int(row.id))
    return {"ok": True, "data": _serialize_permit_detail(db, user, row, module_key="contractor")}


@router.post("/{permit_id:int}/resubmit")
def permit_qc_resubmit(
    permit_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:submit")),
):
    row = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, row, module_key="contractor")
    if _upper(row.status_code) != "RETURNED":
        raise HTTPException(status_code=409, detail="Resubmit is allowed only from RETURNED.")
    return permit_qc_submit(permit_id=permit_id, db=db, user=user)


@router.post("/{permit_id:int}/cancel")
def permit_qc_cancel(
    permit_id: int,
    note: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:submit")),
):
    row = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, row, module_key="contractor")
    current = _upper(row.status_code)
    if current not in CONTRACTOR_CANCEL_STATUSES:
        raise HTTPException(status_code=409, detail="Cancel is not allowed for current permit status.")
    previous = row.status_code
    _set_status_fields(row, "CANCELLED")
    row.updated_by_id = getattr(user, "id", None)
    row.updated_at = datetime.utcnow()
    _record_event(
        db,
        permit_id=int(row.id),
        event_type="CANCEL",
        created_by_id=getattr(user, "id", None),
        from_status_code=previous,
        to_status_code="CANCELLED",
        note=note,
    )
    db.commit()
    row = _load_permit_or_404(db, int(row.id))
    return {"ok": True, "data": _serialize_permit_detail(db, user, row, module_key="contractor")}


@router.post("/{permit_id:int}/review")
def permit_qc_review(
    permit_id: int,
    payload: PermitQcReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:review")),
):
    row = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, row, module_key="consultant")
    current = _upper(row.status_code)
    if current not in CONSULTANT_REVIEWABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Review is allowed only on SUBMITTED or UNDER_REVIEW.")

    station = (
        db.query(PermitQcPermitStation)
        .options(joinedload(PermitQcPermitStation.checks))
        .filter(
            PermitQcPermitStation.id == int(payload.station_id),
            PermitQcPermitStation.permit_id == int(row.id),
        )
        .first()
    )
    if not station:
        raise HTTPException(status_code=404, detail="Station not found for this permit.")

    action = _upper(payload.action)
    if action not in STATION_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid review action: {payload.action}")
    if action in {"RETURN", "REJECT"} and not _norm(payload.note):
        raise HTTPException(status_code=400, detail="Review note is required for RETURN/REJECT.")

    user_org_id = int(getattr(user, "organization_id", 0) or 0)
    station_org_id = int(station.organization_id or 0)
    if (
        not _is_system_admin(user)
        and station_org_id > 0
        and user_org_id > 0
        and station_org_id != user_org_id
    ):
        raise HTTPException(status_code=403, detail="Review access denied for target station organization.")

    checks_by_id = {int(check.id): check for check in list(station.checks or [])}
    for item in payload.checks:
        check = checks_by_id.get(int(item.check_id))
        if not check:
            raise HTTPException(status_code=404, detail=f"Check not found in this station: {item.check_id}")
        check_type = _check_type_or_default(check.check_type)
        if check_type == "BOOLEAN":
            parsed = _coerce_bool(item.value_bool)
            if parsed is None and check.is_required:
                raise HTTPException(
                    status_code=400,
                    detail=f"value_bool is required for BOOLEAN check `{check.check_code}`",
                )
            check.value_bool = parsed
            check.value_text = None
            check.value_number = None
            check.value_date = None
        elif check_type == "NUMBER":
            if item.value_number is None and check.is_required:
                raise HTTPException(
                    status_code=400,
                    detail=f"value_number is required for NUMBER check `{check.check_code}`",
                )
            check.value_number = item.value_number
            check.value_text = None
            check.value_bool = None
            check.value_date = None
        elif check_type == "DATE":
            if item.value_date is None and check.is_required:
                raise HTTPException(
                    status_code=400,
                    detail=f"value_date is required for DATE check `{check.check_code}`",
                )
            check.value_date = item.value_date
            check.value_text = None
            check.value_bool = None
            check.value_number = None
        else:
            text_value = _norm(item.value_text)
            if not text_value and check.is_required:
                raise HTTPException(
                    status_code=400,
                    detail=f"value_text is required for TEXT check `{check.check_code}`",
                )
            check.value_text = text_value or None
            check.value_bool = None
            check.value_number = None
            check.value_date = None
        check.note = _norm(item.note) or None

    station.status_code = STATION_STATUS_MAP[action]
    station.reviewed_by_id = getattr(user, "id", None)
    station.reviewed_at = datetime.utcnow()
    station.review_note = _norm(payload.note) or None

    previous = row.status_code
    next_status = _recompute_permit_status(db, row)
    _set_status_fields(row, next_status)
    row.updated_by_id = getattr(user, "id", None)
    row.updated_at = datetime.utcnow()
    _record_event(
        db,
        permit_id=int(row.id),
        station_id=int(station.id),
        event_type=f"REVIEW_{action}",
        created_by_id=getattr(user, "id", None),
        from_status_code=previous,
        to_status_code=next_status,
        note=payload.note,
        payload={
            "station_status": station.status_code,
            "station_key": station.station_key,
            "check_count": len(payload.checks or []),
        },
    )
    db.commit()
    row = _load_permit_or_404(db, int(row.id))
    return {"ok": True, "data": _serialize_permit_detail(db, user, row, module_key="consultant")}


@router.get("/{permit_id:int}/attachments")
def permit_qc_list_attachments(
    permit_id: int,
    module_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:read")),
):
    row = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, row, module_key=_effective_read_module_key(user, module_key))
    attachments = (
        db.query(PermitQcPermitAttachment)
        .options(joinedload(PermitQcPermitAttachment.uploaded_by))
        .filter(PermitQcPermitAttachment.permit_id == int(row.id))
        .order_by(PermitQcPermitAttachment.uploaded_at.desc(), PermitQcPermitAttachment.id.desc())
        .all()
    )
    return {"ok": True, "data": [_serialize_attachment(item) for item in attachments]}


@router.post("/{permit_id:int}/attachments")
def permit_qc_upload_attachment(
    permit_id: int,
    module_key: str = Form("contractor"),
    file: UploadFile = File(...),
    file_kind: str = Form("attachment"),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:attachment_upload")),
):
    row = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, row, module_key=module_key)
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    now = datetime.utcnow()
    original_name = safe_name(file.filename)
    unique_name = safe_name(f"{now.strftime('%Y%m%d%H%M%S%f')}_{original_name}")
    storage_manager = StorageManager(db)
    normalized_kind = _lower(file_kind) or "attachment"

    if storage_manager._is_webdav_primary_mode():
        # WebDAV mode: use correspondence_storage_path as base and relativize to root
        integrations = get_storage_integrations(db)
        runtime = resolve_nextcloud_runtime(integrations)
        root_path = str(runtime.get("root_path") or "")

        # Get correspondence base from settings (permits stored under correspondence)
        corr_base = storage_manager.get_correspondence_webdav_base()

        # Build path structure (same as _permit_attachment_dir but for WebDAV)
        permit_code = safe_name(row.permit_no or f"permit-{row.id}")
        project_code = safe_name(row.project_code or "project")

        # Build complete absolute path
        absolute_path = f"{corr_base}/permit_qc/{project_code}/{permit_code}/attachments/{unique_name}"

        # Relativize to root
        relative_path = StorageManager.relativize_webdav_path(absolute_path, root_path)

        saved = storage_manager.save_upload_to_webdav(
            file=file,
            remote_relative_path=relative_path,
            file_kind=normalized_kind,
        )
        stored_path = saved.stored_path
    else:
        # Mount/local mode: use existing logic
        folder = _permit_attachment_dir(db, row)
        saved = storage_manager.save_upload_secure(
            file=file,
            destination_folder=str(folder),
            new_name=unique_name,
            file_kind=normalized_kind,
        )
        stored_path = str(Path(saved.stored_path))
    attachment = PermitQcPermitAttachment(
        permit_id=int(row.id),
        file_name=original_name,
        stored_path=stored_path,
        file_kind=normalized_kind,
        mime_type=saved.declared_mime or _norm(file.content_type) or None,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        storage_backend=storage_manager.resolve_storage_backend_for_path(saved.stored_path),
        uploaded_by_id=getattr(user, "id", None),
        uploaded_at=datetime.utcnow(),
    )
    db.add(attachment)
    db.flush()
    _record_event(
        db,
        permit_id=int(row.id),
        event_type="ATTACHMENT_UPLOAD",
        created_by_id=getattr(user, "id", None),
        from_status_code=row.status_code,
        to_status_code=row.status_code,
        note=note,
        payload={
            "attachment_id": int(attachment.id),
            "file_name": attachment.file_name,
        },
    )
    db.commit()
    db.refresh(attachment)
    return {"ok": True, "data": _serialize_attachment(attachment)}


@router.get("/attachments/{attachment_id}/download")
def permit_qc_download_attachment(
    attachment_id: int,
    module_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:read")),
):
    row = (
        db.query(PermitQcPermitAttachment)
        .filter(PermitQcPermitAttachment.id == int(attachment_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    permit = _load_permit_or_404(db, int(row.permit_id))
    _enforce_permit_module_access(db, user, permit, module_key=_effective_read_module_key(user, module_key))
    if str(row.stored_path or "").strip().startswith("webdav://"):
        return _download_webdav_attachment(db, row)
    file_path = Path(row.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path=str(file_path), filename=row.file_name, media_type=row.mime_type)


@router.delete("/{permit_id:int}/attachments")
def permit_qc_delete_attachment(
    permit_id: int,
    attachment_id: int = Query(..., ge=1),
    module_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:attachment_delete")),
):
    permit = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, permit, module_key=_effective_read_module_key(user, module_key))
    row = (
        db.query(PermitQcPermitAttachment)
        .filter(
            PermitQcPermitAttachment.id == int(attachment_id),
            PermitQcPermitAttachment.permit_id == int(permit.id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found for this permit")
    db.delete(row)
    _record_event(
        db,
        permit_id=int(permit.id),
        event_type="ATTACHMENT_DELETE",
        created_by_id=getattr(user, "id", None),
        from_status_code=permit.status_code,
        to_status_code=permit.status_code,
        payload={"attachment_id": int(attachment_id)},
    )
    db.commit()
    _delete_stored_attachment_file(db, str(row.stored_path or ""))
    return {"ok": True}


@router.get("/{permit_id:int}/timeline")
def permit_qc_timeline(
    permit_id: int,
    module_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:read")),
):
    permit = _load_permit_or_404(db, permit_id)
    _enforce_permit_module_access(db, user, permit, module_key=_effective_read_module_key(user, module_key))
    rows = (
        db.query(PermitQcPermitEvent)
        .options(joinedload(PermitQcPermitEvent.created_by))
        .filter(PermitQcPermitEvent.permit_id == int(permit.id))
        .order_by(PermitQcPermitEvent.created_at.desc(), PermitQcPermitEvent.id.desc())
        .all()
    )
    return {"ok": True, "data": [_serialize_event(row) for row in rows]}


@router.get("/templates")
def permit_qc_templates_list(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:template_manage")),
):
    _ensure_consultant_template_access(user)
    query = db.query(PermitQcTemplate).options(
        joinedload(PermitQcTemplate.stations).joinedload(PermitQcTemplateStation.checks),
        joinedload(PermitQcTemplate.created_by),
        joinedload(PermitQcTemplate.updated_by),
    )
    if not include_inactive:
        query = query.filter(PermitQcTemplate.is_active.is_(True))
    project_value = _upper(project_code)
    if project_value:
        enforce_scope_access(db, user, project_code=project_value)
        query = query.filter(
            or_(PermitQcTemplate.project_code == project_value, PermitQcTemplate.project_code.is_(None))
        )
    discipline_value = _upper(discipline_code)
    if discipline_value:
        enforce_scope_access(db, user, discipline_code=discipline_value)
        query = query.filter(
            or_(
                PermitQcTemplate.discipline_code == discipline_value,
                PermitQcTemplate.discipline_code.is_(None),
            )
        )

    rows = query.order_by(PermitQcTemplate.is_default.desc(), PermitQcTemplate.id.desc()).all()
    return {"ok": True, "data": [_serialize_template(row) for row in rows]}


@router.post("/templates/upsert")
def permit_qc_templates_upsert(
    payload: PermitQcTemplateUpsertIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:template_manage")),
):
    _ensure_consultant_template_access(user)
    project_value = _upper(payload.project_code) or None
    discipline_value = _upper(payload.discipline_code) or None
    if project_value:
        project_exists = db.query(Project.code).filter(Project.code == project_value).first()
        if not project_exists:
            raise HTTPException(status_code=404, detail="Project not found")
    if discipline_value:
        discipline_exists = db.query(Discipline.code).filter(Discipline.code == discipline_value).first()
        if not discipline_exists:
            raise HTTPException(status_code=404, detail="Discipline not found")

    code_value = _norm(payload.code) or None
    if payload.id:
        row = _load_template_or_404(db, int(payload.id))
    else:
        row = PermitQcTemplate(created_by_id=getattr(user, "id", None), created_at=datetime.utcnow())
        db.add(row)

    if code_value:
        duplicate = (
            db.query(PermitQcTemplate.id)
            .filter(
                PermitQcTemplate.code == code_value,
                PermitQcTemplate.id != int(row.id or 0),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Template code already exists.")
    row.code = code_value
    row.name = _norm(payload.name)
    row.description = _norm(payload.description) or None
    row.project_code = project_value
    row.discipline_code = discipline_value
    row.is_active = bool(payload.is_active)
    row.is_default = bool(payload.is_default)
    row.updated_by_id = getattr(user, "id", None)
    row.updated_at = datetime.utcnow()
    db.flush()

    if row.is_default:
        db.query(PermitQcTemplate).filter(
            PermitQcTemplate.id != int(row.id),
            PermitQcTemplate.project_code == row.project_code,
            PermitQcTemplate.discipline_code == row.discipline_code,
        ).update({"is_default": False}, synchronize_session=False)

    db.commit()
    row = _load_template_or_404(db, int(row.id))
    return {"ok": True, "data": _serialize_template(row)}


@router.post("/templates/{template_id}/stations/upsert")
def permit_qc_templates_station_upsert(
    template_id: int,
    payload: PermitQcTemplateStationUpsertIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:template_manage")),
):
    _ensure_consultant_template_access(user)
    template = _load_template_or_404(db, template_id)
    if payload.id:
        station = (
            db.query(PermitQcTemplateStation)
            .filter(
                PermitQcTemplateStation.id == int(payload.id),
                PermitQcTemplateStation.template_id == int(template.id),
            )
            .first()
        )
        if not station:
            raise HTTPException(status_code=404, detail="Template station not found")
    else:
        station = PermitQcTemplateStation(template_id=int(template.id), created_at=datetime.utcnow())
        db.add(station)

    organization_id = _ensure_organization_exists(db, payload.organization_id, field_name="station")
    station.station_key = _norm(payload.station_key)
    station.station_label = _norm(payload.station_label)
    station.organization_id = organization_id
    station.is_required = bool(payload.is_required)
    station.is_active = bool(payload.is_active)
    station.sort_order = int(payload.sort_order or 0)
    station.updated_at = datetime.utcnow()
    db.commit()
    template = _load_template_or_404(db, int(template.id))
    return {"ok": True, "data": _serialize_template(template)}


@router.post("/templates/{template_id}/checks/upsert")
def permit_qc_templates_check_upsert(
    template_id: int,
    payload: PermitQcTemplateCheckUpsertIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:template_manage")),
):
    _ensure_consultant_template_access(user)
    template = _load_template_or_404(db, template_id)
    station = (
        db.query(PermitQcTemplateStation)
        .filter(
            PermitQcTemplateStation.id == int(payload.station_id),
            PermitQcTemplateStation.template_id == int(template.id),
        )
        .first()
    )
    if not station:
        raise HTTPException(status_code=404, detail="Template station not found")

    if payload.id:
        check = (
            db.query(PermitQcTemplateCheck)
            .filter(
                PermitQcTemplateCheck.id == int(payload.id),
                PermitQcTemplateCheck.station_id == int(station.id),
            )
            .first()
        )
        if not check:
            raise HTTPException(status_code=404, detail="Template check not found")
    else:
        check = PermitQcTemplateCheck(station_id=int(station.id), created_at=datetime.utcnow())
        db.add(check)

    check.check_code = _norm(payload.check_code)
    check.check_label = _norm(payload.check_label)
    check.check_type = _check_type_or_default(payload.check_type)
    check.is_required = bool(payload.is_required)
    check.is_active = bool(payload.is_active)
    check.sort_order = int(payload.sort_order or 0)
    check.updated_at = datetime.utcnow()
    db.commit()
    template = _load_template_or_404(db, int(template.id))
    return {"ok": True, "data": _serialize_template(template)}


@router.post("/templates/{template_id}/activate")
def permit_qc_templates_activate(
    template_id: int,
    payload: PermitQcTemplateActivateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("permit_qc:template_manage")),
):
    _ensure_consultant_template_access(user)
    template = _load_template_or_404(db, template_id)
    template.is_active = bool(payload.is_active)
    if payload.is_default is not None:
        template.is_default = bool(payload.is_default)
    template.updated_by_id = getattr(user, "id", None)
    template.updated_at = datetime.utcnow()
    db.flush()
    if bool(template.is_default):
        db.query(PermitQcTemplate).filter(
            PermitQcTemplate.id != int(template.id),
            PermitQcTemplate.project_code == template.project_code,
            PermitQcTemplate.discipline_code == template.discipline_code,
        ).update({"is_default": False}, synchronize_session=False)
    db.commit()
    template = _load_template_or_404(db, int(template.id))
    return {"ok": True, "data": _serialize_template(template)}
