from __future__ import annotations

import csv
from html import escape as html_escape
from io import BytesIO, StringIO
import os
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.dependencies import (
    User,
    apply_organization_query_filters,
    apply_scope_query_filters,
    enforce_organization_access,
    enforce_scope_access,
    get_db,
    get_current_user,
    has_permission_for_user,
    require_permission,
)
from app.core.organizations import OrganizationType
from app.db.models import (
    CommItem,
    Discipline,
    Organization,
    OrganizationContract,
    PermitQcPermit,
    Project,
    SiteLog,
    SiteLogActivityCatalog,
    SiteLogActivityPmsMapping,
    SiteLogActivityPmsStep,
    SiteLogActivityRow,
    SiteLogAttachment,
    SiteLogAttachmentRow,
    SiteLogAttachmentTypeCatalog,
    SiteLogComment,
    SiteLogEquipmentCatalog,
    SiteLogEquipmentRow,
    SiteLogEquipmentStatusCatalog,
    SiteLogIssueTypeCatalog,
    SiteLogIssueRow,
    SiteLogManpowerRow,
    SiteLogMaterialCatalog,
    SiteLogMaterialRow,
    SiteLogRoleCatalog,
    SiteLogSequence,
    SiteLogShiftCatalog,
    SiteLogStatusLog,
    SiteLogWeatherCatalog,
    SiteLogWorkSectionCatalog,
    SiteLogWorkflowStatus,
    TechDetail,
    User as DbUser,
)
from app.services.access_control import resolve_effective_access
from app.services.folder_service import safe_name
from app.services.nextcloud_adapter import NextcloudAdapter
from app.services.power_bi_tokens import (
    POWER_BI_SITE_LOG_SCOPE,
    PowerBiReportAccess,
    is_power_bi_token_value,
    resolve_power_bi_report_access,
)
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import resolve_nextcloud_runtime


router = APIRouter(prefix="/site-logs", tags=["Site Logs"])

LOG_TYPES = {"DAILY", "WEEKLY", "SAFETY_INCIDENT"}
STATUSES = {"DRAFT", "SUBMITTED", "RETURNED", "VERIFIED"}
WORK_STATUSES = {"ACTIVE", "HOLIDAY", "INACTIVE"}
SECTIONS = {"GENERAL", "MANPOWER", "EQUIPMENT", "ACTIVITY", "MATERIAL", "ISSUE", "REPORT_ATTACHMENT"}
FILE_KINDS = {"pdf", "native", "attachment"}
LOG_TYPE_LABELS = {"DAILY": "روزانه", "WEEKLY": "هفتگی", "SAFETY_INCIDENT": "حادثه ایمنی"}
STATUS_LABELS = {"DRAFT": "پیش‌نویس", "SUBMITTED": "ارسال‌شده", "RETURNED": "برگشت‌شده", "VERIFIED": "تاییدشده"}
WORK_STATUS_LABELS = {"ACTIVE": "فعال", "HOLIDAY": "تعطیل", "INACTIVE": "غیرفعال"}
SITE_LOG_REPORT_SECTIONS = {"general", "manpower", "equipment", "material", "activity"}
SITE_LOG_REPORT_SECTION_LABELS = {
    "general": "عمومی",
    "manpower": "نفرات",
    "equipment": "تجهیزات",
    "material": "مصالح",
    "activity": "فعالیت",
}


def _extract_bearer_token(request: Request) -> str:
    auth_header = str(request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return ""


def _request_client_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "").strip()


def _site_log_csv_report_reader(
    request: Request,
    db: Session = Depends(get_db),
) -> User | PowerBiReportAccess:
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwt_error: HTTPException | None = None
    try:
        user = get_current_user(
            request,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            db,
        )
        if not has_permission_for_user(db, user, POWER_BI_SITE_LOG_SCOPE):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Missing permission: {POWER_BI_SITE_LOG_SCOPE}",
            )
        return user
    except HTTPException as exc:
        jwt_error = exc

    if is_power_bi_token_value(token):
        _, access = resolve_power_bi_report_access(
            db,
            token_value=token,
            client_ip=_request_client_ip(request),
            required_scope=POWER_BI_SITE_LOG_SCOPE,
        )
        return access

    raise jwt_error or HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


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


def _parse_query_day(value: str | None, field_name: str) -> datetime | None:
    raw = _norm(value)
    if not raw:
        return None
    try:
        if "T" in raw:
            return _to_day_start(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        return _to_day_start(date.fromisoformat(raw[:10]))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}. Use YYYY-MM-DD.")


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


def _compose_summary_text(
    current_work_summary: str | None,
    next_plan_summary: str | None,
    legacy_summary: str | None = None,
) -> str | None:
    current = _norm(current_work_summary)
    next_plan = _norm(next_plan_summary)
    if current or next_plan:
        parts: list[str] = []
        if current:
            parts.append(f"کارهای در حال انجام: {current}")
        if next_plan:
            parts.append(f"برنامه بعدی: {next_plan}")
        return "\n".join(parts)
    return _norm(legacy_summary) or None


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


def _normalize_work_status(value: str | None, default: str = "ACTIVE") -> str:
    code = _upper(value) or _upper(default)
    if code not in WORK_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unsupported work_status: {value}")
    return code


def _safe_work_status(value: str | None, default: str = "ACTIVE") -> str:
    try:
        return _normalize_work_status(value, default)
    except HTTPException:
        return _upper(default) if _upper(default) in WORK_STATUSES else "ACTIVE"


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


def _normalize_report_section(value: str | None) -> str:
    section = _norm(value).lower() or "general"
    if section not in SITE_LOG_REPORT_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported report_section: {value}")
    return section


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
    if status not in {"DRAFT", "RETURNED"}:
        raise HTTPException(status_code=409, detail="Only DRAFT or RETURNED site logs can be edited.")


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
            joinedload(SiteLog.organization_contract).joinedload(OrganizationContract.block),
            joinedload(SiteLog.created_by),
            joinedload(SiteLog.submitted_by),
            joinedload(SiteLog.verified_by),
            joinedload(SiteLog.manpower_rows),
            joinedload(SiteLog.equipment_rows),
            joinedload(SiteLog.activity_rows),
            joinedload(SiteLog.material_rows),
            joinedload(SiteLog.issue_rows),
            joinedload(SiteLog.attachment_rows).joinedload(SiteLogAttachmentRow.linked_attachment),
            joinedload(SiteLog.attachments).joinedload(SiteLogAttachment.uploaded_by),
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
    )
    enforce_organization_access(db, user, organization_id=row.organization_id)


def _check_project_exists(db: Session, project_code: str) -> None:
    if not db.query(Project.code).filter(Project.code == _upper(project_code)).first():
        raise HTTPException(status_code=404, detail="Project not found")


def _check_optional_discipline(db: Session, discipline_code: str | None) -> None:
    code = _upper(discipline_code)
    if not code:
        return
    if not db.query(Discipline.code).filter(Discipline.code == code).first():
        raise HTTPException(status_code=404, detail="Discipline not found")


def _check_optional_org(db: Session, org_id: int | None) -> None:
    if not org_id:
        return
    if not db.query(Organization.id).filter(Organization.id == int(org_id)).first():
        raise HTTPException(status_code=404, detail=f"Organization not found: {org_id}")


def _load_contract_or_404(db: Session, contract_id: int) -> OrganizationContract:
    row = (
        db.query(OrganizationContract)
        .options(joinedload(OrganizationContract.block))
        .filter(OrganizationContract.id == int(contract_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Organization contract not found: {contract_id}")
    return row


def _check_optional_org_contract(db: Session, contract_id: int | None, organization_id: int | None = None) -> OrganizationContract | None:
    if not contract_id:
        return None
    contract = _load_contract_or_404(db, int(contract_id))
    if organization_id and int(contract.organization_id or 0) != int(organization_id):
        raise HTTPException(status_code=400, detail="Selected contract does not belong to the organization.")
    return contract


def _check_optional_user(db: Session, user_id: int | None) -> None:
    if not user_id:
        return
    if not db.query(DbUser.id).filter(DbUser.id == int(user_id)).first():
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")


def _choice_label_map(db: Session, model: Any) -> dict[str, str]:
    rows = db.query(model).all()
    return {_upper(getattr(row, "code", None)): _norm(getattr(row, "label", None)) for row in rows if _upper(getattr(row, "code", None))}


def _site_log_choice_labels(db: Session) -> dict[str, dict[str, str]]:
    return {
        "shift": _choice_label_map(db, SiteLogShiftCatalog),
        "weather": _choice_label_map(db, SiteLogWeatherCatalog),
        "issue_type": _choice_label_map(db, SiteLogIssueTypeCatalog),
    }


def _choice_label(labels: dict[str, dict[str, str]] | None, catalog_type: str, code: Any) -> str | None:
    value = _upper(code)
    if not value:
        return None
    return (labels or {}).get(catalog_type, {}).get(value) or value


def _validate_active_choice_code(
    db: Session,
    model: Any,
    value: Any,
    field_name: str,
    *,
    previous_value: Any = None,
    allow_unchanged_legacy: bool = False,
) -> str | None:
    code = _upper(value)
    if not code:
        return None
    previous_code = _upper(previous_value)
    if allow_unchanged_legacy and previous_code and code == previous_code:
        return code
    exists = (
        db.query(model.id)
        .filter(func.upper(model.code) == code, model.is_active == True)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}: {code}")
    return code


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
    storage_manager = StorageManager(db)
    base = storage_manager.get_site_log_base_path()
    section = {
        "GENERAL": "General",
        "MANPOWER": "Manpower",
        "EQUIPMENT": "Equipment",
        "ACTIVITY": "Activity",
        "MATERIAL": "Materials",
        "ISSUE": "Issues",
        "REPORT_ATTACHMENT": "ReportAttachments",
    }.get(_upper(section_code), "General")
    kind = {"pdf": "PDF", "native": "Native", "attachment": "Attachment"}.get(file_kind, "Attachment")
    slug = safe_name(row.log_no or f"SLOG-{row.id}")
    path = base / "site_logs" / slug / section / kind
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


def _download_webdav_attachment(
    db: Session,
    row: SiteLogAttachment,
    content_disposition_type: str = "attachment",
    media_type_override: str | None = None,
) -> StreamingResponse:
    stored_path = str(row.stored_path or "").strip()
    remote_path = stored_path.replace("webdav://", "", 1)
    adapter = _nextcloud_adapter_for_webdav(db)
    if not adapter.file_exists(remote_path):
        raise HTTPException(status_code=404, detail="Attachment file not found")
    filename = safe_name(row.file_name or f"attachment-{row.id}") or f"attachment-{row.id}"
    media_type = media_type_override or _norm(row.detected_mime or row.mime_type) or "application/octet-stream"
    return StreamingResponse(
        adapter.download_file_stream(remote_path),
        media_type=media_type,
        headers={"Content-Disposition": f'{content_disposition_type}; filename="{filename}"'},
    )


def _serve_attachment_file(
    db: Session,
    row: SiteLogAttachment,
    content_disposition_type: str = "attachment",
    media_type_override: str | None = None,
):
    if str(row.stored_path or "").strip().startswith("webdav://"):
        return _download_webdav_attachment(db, row, content_disposition_type, media_type_override)
    path = Path(row.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(
        path=str(path),
        filename=row.file_name,
        media_type=media_type_override or row.detected_mime or row.mime_type,
        content_disposition_type=content_disposition_type,
    )


def _attachment_preview_media_type(row: SiteLogAttachment) -> str | None:
    raw_mimes = [
        str(row.detected_mime or "").split(";", 1)[0].strip().lower(),
        str(row.mime_type or "").split(";", 1)[0].strip().lower(),
    ]
    for mime in raw_mimes:
        if mime in {"application/pdf", "application/x-pdf"}:
            return "application/pdf"
        if mime.startswith("image/"):
            return mime
    ext = Path(str(row.file_name or "")).suffix.lower()
    if ext == ".pdf":
        return "application/pdf"
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext)


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

    path = Path(raw_path)
    try:
        if path.exists():
            os.remove(path)
    except Exception:
        pass


def _has_verified_payload(manpower: list[dict[str, Any]], equipment: list[dict[str, Any]], activity: list[dict[str, Any]]) -> bool:
    return any(
        (row.get("verified_count") is not None or row.get("verified_hours") is not None) for row in manpower
    ) or any(
        (row.get("verified_count") is not None or row.get("verified_status") or row.get("verified_hours") is not None)
        for row in equipment
    ) or any(
        (row.get("verified_progress_pct") is not None) for row in activity
    )


def _has_rows(row: SiteLog) -> bool:
    return bool(
        row.manpower_rows
        or row.equipment_rows
        or row.activity_rows
        or row.material_rows
        or row.issue_rows
        or row.attachment_rows
    )


def _has_verified_values(row: SiteLog) -> bool:
    return any((x.verified_count is not None or x.verified_hours is not None) for x in row.manpower_rows) or any(
        (x.verified_count is not None or _norm(x.verified_status) or x.verified_hours is not None) for x in row.equipment_rows
    ) or any((x.verified_progress_pct is not None) for x in row.activity_rows)


def _serialize(row: SiteLog, include_rows: bool = False, catalog_labels: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "log_no": row.log_no,
        "log_type": row.log_type,
        "project_code": row.project_code,
        "discipline_code": row.discipline_code,
        "organization_id": row.organization_id,
        "organization_name": row.organization.name if row.organization else None,
        "organization_contract_id": row.organization_contract_id,
        "log_date": _to_iso(row.log_date),
        "work_status": _safe_work_status(row.work_status),
        "work_status_label": WORK_STATUS_LABELS.get(_safe_work_status(row.work_status), row.work_status),
        "shift": row.shift,
        "shift_label": _choice_label(catalog_labels, "shift", row.shift),
        "contract_number": row.contract_number,
        "contract_subject": row.contract_subject,
        "contract_block": row.contract_block,
        "qc_test_count": row.qc_test_count,
        "qc_inspection_count": row.qc_inspection_count,
        "qc_open_ncr_count": row.qc_open_ncr_count,
        "qc_open_punch_count": row.qc_open_punch_count,
        "qc_summary_note": row.qc_summary_note,
        "qc_snapshot_at": _to_iso(row.qc_snapshot_at),
        "weather": row.weather,
        "weather_label": _choice_label(catalog_labels, "weather", row.weather),
        "summary": row.summary,
        "current_work_summary": row.current_work_summary,
        "next_plan_summary": row.next_plan_summary,
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
        "material_count": len(row.material_rows or []),
        "issue_count": len(row.issue_rows or []),
        "attachment_row_count": len(row.attachment_rows or []),
    }
    if include_rows:
        attachments_by_section_row_id: dict[tuple[str, int], list[SiteLogAttachment]] = {}
        for attachment in sorted(row.attachments or [], key=lambda v: (v.uploaded_at or datetime.min, v.id or 0)):
            section_code = _upper(attachment.section_code)
            row_id = _to_int(attachment.row_id)
            if not row_id:
                continue
            attachments_by_section_row_id.setdefault((section_code, row_id), []).append(attachment)

        payload["manpower_rows"] = [
            {
                "id": x.id,
                "role_code": x.role_code,
                "role_label": x.role_label,
                "work_section_label": x.work_section_label,
                "claimed_count": x.claimed_count,
                "claimed_hours": x.claimed_hours,
                "verified_count": x.verified_count,
                "verified_hours": x.verified_hours,
                "note": x.note,
                "sort_order": x.sort_order,
                "attachment_files": _row_attachment_payload(attachments_by_section_row_id, "MANPOWER", x.sort_order, x.id),
            }
            for x in sorted(row.manpower_rows, key=lambda v: (v.sort_order or 0, v.id or 0))
        ]
        payload["equipment_rows"] = [
            {
                "id": x.id,
                "equipment_code": x.equipment_code,
                "equipment_label": x.equipment_label,
                "work_location": x.work_location,
                "claimed_count": x.claimed_count,
                "claimed_status": x.claimed_status,
                "claimed_hours": x.claimed_hours,
                "verified_count": x.verified_count,
                "verified_status": x.verified_status,
                "verified_hours": x.verified_hours,
                "note": x.note,
                "sort_order": x.sort_order,
                "attachment_files": _row_attachment_payload(attachments_by_section_row_id, "EQUIPMENT", x.sort_order, x.id),
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
                "location": x.location,
                "unit": x.unit,
                "personnel_count": x.personnel_count,
                "pms_mapping_id": x.pms_mapping_id,
                "pms_template_code": x.pms_template_code,
                "pms_template_title": x.pms_template_title,
                "pms_template_version": x.pms_template_version,
                "pms_step_code": x.pms_step_code,
                "pms_step_title": x.pms_step_title,
                "pms_step_weight_pct": x.pms_step_weight_pct,
                "today_quantity": x.today_quantity,
                "cumulative_quantity": x.cumulative_quantity,
                "supervisor_today_quantity": getattr(x, "supervisor_today_quantity", None),
                "supervisor_cumulative_quantity": getattr(x, "supervisor_cumulative_quantity", None),
                "supervisor_unit": getattr(x, "supervisor_unit", None),
                "qc_status": getattr(x, "qc_status", None),
                "qc_at": _to_iso(getattr(x, "qc_at", None)),
                "qc_by_user_id": getattr(x, "qc_by_user_id", None),
                "qc_note": getattr(x, "qc_note", None),
                "measurement_status": getattr(x, "measurement_status", None),
                "measurement_updated_at": _to_iso(getattr(x, "measurement_updated_at", None)),
                "measurement_updated_by_user_id": getattr(x, "measurement_updated_by_user_id", None),
                "activity_status": x.activity_status,
                "stop_reason": x.stop_reason,
                "note": x.note,
                "sort_order": x.sort_order,
                "attachment_files": _row_attachment_payload(attachments_by_section_row_id, "ACTIVITY", x.sort_order, x.id),
            }
            for x in sorted(row.activity_rows, key=lambda v: (v.sort_order or 0, v.id or 0))
        ]
        payload["material_rows"] = [
            {
                "id": x.id,
                "material_code": x.material_code,
                "title": x.title,
                "consumption_location": x.consumption_location,
                "unit": x.unit,
                "incoming_quantity": x.incoming_quantity,
                "consumed_quantity": x.consumed_quantity,
                "cumulative_quantity": x.cumulative_quantity,
                "note": x.note,
                "sort_order": x.sort_order,
                "attachment_files": _row_attachment_payload(attachments_by_section_row_id, "MATERIAL", x.sort_order, x.id),
            }
            for x in sorted(row.material_rows, key=lambda v: (v.sort_order or 0, v.id or 0))
        ]
        payload["issue_rows"] = [
            {
                "id": x.id,
                "issue_type": x.issue_type,
                "issue_type_label": _choice_label(catalog_labels, "issue_type", x.issue_type),
                "description": x.description,
                "responsible_party": x.responsible_party,
                "due_date": _to_iso(x.due_date),
                "status": x.status,
                "note": x.note,
                "sort_order": x.sort_order,
                "attachment_files": _row_attachment_payload(attachments_by_section_row_id, "ISSUE", x.sort_order, x.id),
            }
            for x in sorted(row.issue_rows, key=lambda v: (v.sort_order or 0, v.id or 0))
        ]
        payload["attachment_rows"] = [
            _serialize_attachment_row(
                x,
                attachments_by_section_row_id.get(("REPORT_ATTACHMENT", int(_to_int(x.sort_order) or 0) + 1), []),
            )
            for x in sorted(row.attachment_rows, key=lambda v: (v.sort_order or 0, v.id or 0))
        ]
    return payload


def _site_log_pdf_font_name() -> str:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        candidates = [
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "tahoma.ttf",
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        for path in candidates:
            if not path.exists():
                continue
            font_name = f"SiteLogPdf-{path.stem}"
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
            return font_name
    except Exception:
        pass
    return "Helvetica"


def _site_log_pdf_text(value: Any, default: str = "-") -> str:
    text = _norm(value)
    return text or default


def _site_log_pdf_date(value: Any) -> str:
    text = _norm(value)
    if not text:
        return "-"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return text.split("T", 1)[0] or text


def _site_log_pdf_number(value: Any, digits: int = 0) -> str:
    if value is None or value == "":
        return "-"
    try:
        number = float(value)
    except Exception:
        return _site_log_pdf_text(value)
    if digits <= 0:
        return str(int(round(number)))
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _build_site_log_pdf(payload: dict[str, Any]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise HTTPException(status_code=500, detail="PDF generation dependency is unavailable.") from exc

    font_name = _site_log_pdf_font_name()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.1 * cm,
        leftMargin=1.1 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )
    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SiteLogTitle",
        parent=base_styles["Title"],
        fontName=font_name,
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "SiteLogHeading",
        parent=base_styles["Heading2"],
        fontName=font_name,
        fontSize=11,
        leading=14,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=5,
    )
    cell_style = ParagraphStyle(
        "SiteLogCell",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=7.6,
        leading=10,
        alignment=TA_RIGHT,
        wordWrap="CJK",
    )
    label_style = ParagraphStyle(
        "SiteLogLabel",
        parent=cell_style,
        textColor=colors.HexColor("#475569"),
    )

    def cell(value: Any, *, label: bool = False):
        return Paragraph(html_escape(_site_log_pdf_text(value)), label_style if label else cell_style)

    def table_style(header: bool = False) -> TableStyle:
        commands: list[tuple[Any, ...]] = [
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 7.6),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header:
            commands.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ]
            )
        return TableStyle(commands)

    elements: list[Any] = [
        Paragraph("Site Log Report", title_style),
        Paragraph(html_escape(_site_log_pdf_text(payload.get("log_no"))), title_style),
        Spacer(1, 0.15 * cm),
    ]

    header_rows = [
        [cell("Log No", label=True), cell(payload.get("log_no")), cell("Status", label=True), cell(payload.get("status_code"))],
        [cell("Project", label=True), cell(payload.get("project_code")), cell("Date", label=True), cell(_site_log_pdf_date(payload.get("log_date")))],
        [cell("Organization", label=True), cell(payload.get("organization_name")), cell("Log Type", label=True), cell(payload.get("log_type"))],
        [cell("Contract No", label=True), cell(payload.get("contract_number")), cell("Contract Subject", label=True), cell(payload.get("contract_subject"))],
        [cell("Shift", label=True), cell(payload.get("shift_label") or payload.get("shift")), cell("Weather", label=True), cell(payload.get("weather_label") or payload.get("weather"))],
    ]
    info_table = Table(header_rows, colWidths=[2.2 * cm, 6.5 * cm, 2.4 * cm, 6.5 * cm])
    info_table.setStyle(table_style())
    elements.append(info_table)

    elements.append(Paragraph("Management Summary", heading_style))
    summary_rows = [
        [cell("Current Work", label=True), cell(payload.get("current_work_summary") or payload.get("summary"))],
        [cell("Next Plan", label=True), cell(payload.get("next_plan_summary"))],
        [cell("QC Summary", label=True), cell(payload.get("qc_summary_note"))],
    ]
    summary_table = Table(summary_rows, colWidths=[3.2 * cm, 14.4 * cm])
    summary_table.setStyle(table_style())
    elements.append(summary_table)

    elements.append(Paragraph("Counts", heading_style))
    count_rows = [
        [cell("Manpower", label=True), cell(payload.get("manpower_count")), cell("Equipment", label=True), cell(payload.get("equipment_count"))],
        [cell("Activities", label=True), cell(payload.get("activity_count")), cell("Materials", label=True), cell(payload.get("material_count"))],
        [cell("Issues", label=True), cell(payload.get("issue_count")), cell("Attachments", label=True), cell(payload.get("attachment_row_count"))],
        [cell("QC Tests", label=True), cell(payload.get("qc_test_count")), cell("Open NCR", label=True), cell(payload.get("qc_open_ncr_count"))],
    ]
    counts_table = Table(count_rows, colWidths=[3.2 * cm, 5.6 * cm, 3.2 * cm, 5.6 * cm])
    counts_table.setStyle(table_style())
    elements.append(counts_table)

    def add_section(title: str, rows: list[Any], headers: list[str], mapper, widths: list[float]) -> None:
        elements.append(Paragraph(title, heading_style))
        if not rows:
            empty_table = Table([[cell("No rows registered.")]], colWidths=[17.6 * cm])
            empty_table.setStyle(table_style())
            elements.append(empty_table)
            return
        data = [[cell(item) for item in headers]]
        for index, row in enumerate(rows[:60], 1):
            data.append([cell(item) for item in mapper(row, index)])
        if len(rows) > 60:
            data.append([cell(f"{len(rows) - 60} more rows omitted.")] + [cell("") for _ in headers[1:]])
        table = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
        table.setStyle(table_style(header=True))
        elements.append(table)

    add_section(
        "Manpower",
        list(payload.get("manpower_rows") or []),
        ["#", "Role", "Work Section", "Claimed Count", "Claimed Hours", "Verified Count", "Verified Hours", "Note"],
        lambda row, index: [
            index,
            row.get("role_label") or row.get("role_code"),
            row.get("work_section_label"),
            _site_log_pdf_number(row.get("claimed_count")),
            _site_log_pdf_number(row.get("claimed_hours"), 1),
            _site_log_pdf_number(row.get("verified_count")),
            _site_log_pdf_number(row.get("verified_hours"), 1),
            row.get("note"),
        ],
        [0.8, 3.0, 3.0, 1.8, 1.8, 1.8, 1.8, 3.6],
    )

    add_section(
        "Equipment",
        list(payload.get("equipment_rows") or []),
        ["#", "Equipment", "Work Location", "Claimed Count", "Claimed Status", "Claimed Hours", "Verified Count", "Verified Status", "Verified Hours"],
        lambda row, index: [
            index,
            row.get("equipment_label") or row.get("equipment_code"),
            row.get("work_location"),
            _site_log_pdf_number(row.get("claimed_count")),
            row.get("claimed_status"),
            _site_log_pdf_number(row.get("claimed_hours"), 1),
            _site_log_pdf_number(row.get("verified_count")),
            row.get("verified_status"),
            _site_log_pdf_number(row.get("verified_hours"), 1),
        ],
        [0.8, 3.3, 2.3, 1.6, 1.8, 1.6, 1.6, 1.8, 1.6],
    )

    add_section(
        "Activities",
        list(payload.get("activity_rows") or []),
        ["#", "Code", "Title", "Location", "Unit", "Today", "Cumulative", "Status"],
        lambda row, index: [
            index,
            row.get("activity_code"),
            row.get("activity_title"),
            row.get("location"),
            row.get("unit"),
            _site_log_pdf_number(row.get("today_quantity"), 2),
            _site_log_pdf_number(row.get("cumulative_quantity"), 2),
            row.get("activity_status"),
        ],
        [0.8, 2.1, 5.6, 2.1, 1.4, 1.6, 1.8, 2.2],
    )

    add_section(
        "Materials",
        list(payload.get("material_rows") or []),
        ["#", "Code", "Title", "Consumption Location", "Unit", "Incoming", "Consumed", "Cumulative", "Note"],
        lambda row, index: [
            index,
            row.get("material_code"),
            row.get("title"),
            row.get("consumption_location"),
            row.get("unit"),
            _site_log_pdf_number(row.get("incoming_quantity"), 2),
            _site_log_pdf_number(row.get("consumed_quantity"), 2),
            _site_log_pdf_number(row.get("cumulative_quantity"), 2),
            row.get("note"),
        ],
        [0.8, 1.8, 3.4, 2.3, 1.3, 1.6, 1.6, 1.7, 3.0],
    )

    add_section(
        "Issues / Risks",
        list(payload.get("issue_rows") or []),
        ["#", "Type", "Description", "Responsible", "Due", "Status"],
        lambda row, index: [
            index,
            row.get("issue_type_label") or row.get("issue_type"),
            row.get("description"),
            row.get("responsible_party"),
            _site_log_pdf_date(row.get("due_date")),
            row.get("status"),
        ],
        [0.8, 3.0, 5.8, 3.0, 2.2, 2.8],
    )

    attachment_rows = list(payload.get("attachment_rows") or [])
    if attachment_rows:
        add_section(
            "Report Attachments",
            attachment_rows,
            ["#", "Type", "Title", "Reference", "File"],
            lambda row, index: [
                index,
                row.get("attachment_type_label") or row.get("attachment_type"),
                row.get("title"),
                row.get("reference_no"),
                row.get("linked_attachment_file_name"),
            ],
            [0.8, 3.0, 6.2, 3.2, 4.4],
        )

    elements.append(PageBreak())
    footer_table = Table(
        [
            [cell("Created By", label=True), cell(payload.get("created_by_name")), cell("Created At", label=True), cell(_site_log_pdf_date(payload.get("created_at")))],
            [cell("Submitted By", label=True), cell(payload.get("submitted_by_name")), cell("Submitted At", label=True), cell(_site_log_pdf_date(payload.get("submitted_at")))],
            [cell("Verified By", label=True), cell(payload.get("verified_by_name")), cell("Verified At", label=True), cell(_site_log_pdf_date(payload.get("verified_at")))],
        ],
        colWidths=[2.8 * cm, 6.0 * cm, 2.8 * cm, 6.0 * cm],
    )
    footer_table.setStyle(table_style())
    elements.append(Paragraph("Workflow", heading_style))
    elements.append(footer_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


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
    attachment_id = int(row.id or 0)
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
        "preview_url": f"/api/v1/site-logs/attachments/{attachment_id}/preview" if attachment_id > 0 else None,
        "download_url": f"/api/v1/site-logs/attachments/{attachment_id}/download" if attachment_id > 0 else None,
    }


def _row_attachment_payload(
    attachments_by_section_row_id: dict[tuple[str, int], list[SiteLogAttachment]],
    section_code: str,
    sort_order: Any,
    db_row_id: Any = None,
) -> list[dict[str, Any]]:
    section = _upper(section_code)
    target_row_ids: list[int] = []
    stable_row_id = _to_int(db_row_id)
    if stable_row_id:
        target_row_ids.append(int(stable_row_id))
    ordinal_row_id = int(_to_int(sort_order) or 0) + 1
    if ordinal_row_id not in target_row_ids:
        target_row_ids.append(ordinal_row_id)

    seen_ids: set[int] = set()
    files: list[dict[str, Any]] = []
    for row_id in target_row_ids:
        for attachment in attachments_by_section_row_id.get((section, row_id), []):
            attachment_id = int(attachment.id or 0)
            if attachment_id in seen_ids:
                continue
            seen_ids.add(attachment_id)
            files.append(_serialize_attachment(attachment))
    return files


def _serialize_attachment_row(row: SiteLogAttachmentRow, attachment_files: list[SiteLogAttachment] | None = None) -> dict[str, Any]:
    attachment = row.linked_attachment
    attachment_id = int(row.linked_attachment_id or 0) if row.linked_attachment_id else None
    files = [_serialize_attachment(x) for x in (attachment_files or [])]
    if attachment and not any(int(item.get("id") or 0) == attachment_id for item in files):
        files.insert(0, _serialize_attachment(attachment))
    return {
        "id": row.id,
        "attachment_type": row.attachment_type,
        "title": row.title,
        "reference_no": row.reference_no,
        "note": row.note,
        "linked_attachment_id": attachment_id,
        "linked_attachment_file_name": attachment.file_name if attachment else None,
        "linked_attachment_file_kind": attachment.file_kind if attachment else None,
        "linked_attachment_download_url": (
            f"/api/v1/site-logs/attachments/{attachment_id}/download" if attachment_id else None
        ),
        "attachment_files": files,
        "linked_attachment_ids": [int(item.get("id") or 0) for item in files if int(item.get("id") or 0) > 0],
        "sort_order": row.sort_order,
    }


def _day_bounds(value: date | datetime | None) -> tuple[datetime | None, datetime | None]:
    start = _to_day_start(value)
    if not start:
        return None, None
    return start, start.replace(hour=23, minute=59, second=59, microsecond=999999)


def _comm_item_org_clause(organization_id: int | None):
    oid = int(organization_id or 0)
    if oid <= 0:
        return None
    return or_(
        CommItem.organization_id == oid,
        CommItem.contractor_org_id == oid,
        CommItem.recipient_org_id == oid,
    )


def _permit_org_clause(organization_id: int | None):
    oid = int(organization_id or 0)
    if oid <= 0:
        return None
    return or_(
        PermitQcPermit.organization_id == oid,
        PermitQcPermit.contractor_org_id == oid,
    )


def _build_qc_snapshot(
    db: Session,
    *,
    project_code: str | None,
    organization_id: int | None,
    log_date: date | datetime | None,
) -> dict[str, Any]:
    project_value = _upper(project_code)
    oid = int(organization_id or 0) or None
    day_start, day_end = _day_bounds(log_date)
    if not project_value or not oid or not day_start or not day_end:
        return {
            "qc_test_count": 0,
            "qc_inspection_count": 0,
            "qc_open_ncr_count": 0,
            "qc_snapshot_at": _to_iso(datetime.utcnow()),
        }

    permit_query = db.query(PermitQcPermit.id).filter(PermitQcPermit.project_code == project_value)
    permit_org_clause = _permit_org_clause(oid)
    if permit_org_clause is not None:
        permit_query = permit_query.filter(permit_org_clause)
    permit_query = permit_query.filter(
        PermitQcPermit.permit_date.is_not(None),
        PermitQcPermit.permit_date >= day_start,
        PermitQcPermit.permit_date <= day_end,
    )

    inspection_query = (
        db.query(CommItem.id)
        .join(TechDetail, TechDetail.comm_item_id == CommItem.id)
        .filter(
            CommItem.project_code == project_value,
            CommItem.item_type == "TECH",
            TechDetail.tech_subtype_code == "IR",
            CommItem.created_at >= day_start,
            CommItem.created_at <= day_end,
        )
    )
    comm_org_clause = _comm_item_org_clause(oid)
    if comm_org_clause is not None:
        inspection_query = inspection_query.filter(comm_org_clause)

    ncr_query = db.query(CommItem.id).filter(
        CommItem.project_code == project_value,
        CommItem.item_type == "NCR",
        CommItem.status_code != "CLOSED",
    )
    if comm_org_clause is not None:
        ncr_query = ncr_query.filter(comm_org_clause)

    return {
        "qc_test_count": int(permit_query.count()),
        "qc_inspection_count": int(inspection_query.count()),
        "qc_open_ncr_count": int(ncr_query.count()),
        "qc_snapshot_at": _to_iso(datetime.utcnow()),
    }


def _resolve_contract_snapshot(
    db: Session,
    *,
    organization_id: int | None,
    organization_contract_id: int | None,
    contract_number: str | None,
    contract_subject: str | None,
    contract_block: str | None,
) -> tuple[int | None, str | None, str | None, str | None]:
    contract = _check_optional_org_contract(db, organization_contract_id, organization_id)
    if contract:
        block_name = None
        if contract.block:
            block_name = contract.block.name_e or contract.block.name_p or contract.block.code
        return (
            int(contract.id),
            _norm(contract.contract_number) or None,
            _norm(contract.subject) or None,
            _norm(block_name) or None,
        )
    return (
        None,
        _norm(contract_number) or None,
        _norm(contract_subject) or None,
        _norm(contract_block) or None,
    )


def _serialize_activity_catalog_item(row: SiteLogActivityCatalog) -> dict[str, Any]:
    contract = row.organization_contract
    contract_number = _norm(getattr(contract, "contract_number", None))
    contract_subject = _norm(getattr(contract, "subject", None))
    scope = "project"
    if row.organization_contract_id:
        scope = "contract"
    elif row.organization_id:
        scope = "organization"
    pms_payload = _serialize_activity_catalog_pms_payload(getattr(row, "pms_mapping", None))
    return {
        "id": int(row.id or 0),
        "project_code": row.project_code,
        "organization_id": row.organization_id,
        "organization_name": getattr(getattr(row, "organization", None), "name", None),
        "organization_contract_id": row.organization_contract_id,
        "contract_number": contract_number or None,
        "contract_subject": contract_subject or None,
        "activity_code": row.activity_code,
        "activity_title": row.activity_title,
        "default_location": row.default_location,
        "default_unit": row.default_unit,
        "sort_order": int(row.sort_order or 0),
        "is_active": bool(row.is_active),
        "scope_code": scope,
        "scope_label": (
            "سطح قرارداد"
            if scope == "contract"
            else "سطح سازمان" if scope == "organization" else "سطح پروژه"
        ),
        **pms_payload,
    }


def _serialize_activity_catalog_pms_payload(mapping: SiteLogActivityPmsMapping | None) -> dict[str, Any]:
    if not mapping:
        return {
            "pms_mapping_id": None,
            "pms_template_id": None,
            "pms_template_code": None,
            "pms_template_title": None,
            "pms_snapshot_version": None,
            "pms_template_version": None,
            "pms_status": "none",
            "pms_steps": [],
        }
    template_version = int(getattr(getattr(mapping, "template", None), "version", None) or mapping.snapshot_version or 1)
    snapshot_version = int(mapping.snapshot_version or 1)
    return {
        "pms_mapping_id": int(mapping.id or 0),
        "pms_template_id": int(mapping.template_id or 0),
        "pms_template_code": _upper(mapping.template_code),
        "pms_template_title": _norm(mapping.template_title),
        "pms_snapshot_version": snapshot_version,
        "pms_template_version": template_version,
        "pms_status": "stale" if template_version != snapshot_version else "mapped",
        "pms_steps": [
            {
                "id": int(step.id or 0),
                "step_code": _upper(step.step_code),
                "step_title": _norm(step.step_title),
                "weight_pct": float(step.weight_pct or 0),
                "sort_order": int(step.sort_order or 0),
                "is_active": bool(step.is_active),
            }
            for step in sorted(mapping.steps or [], key=lambda item: (int(item.sort_order or 0), int(item.id or 0)))
            if bool(step.is_active)
        ],
    }


def _load_activity_option_rows(
    db: Session,
    *,
    project_code: str,
    organization_id: int | None,
    organization_contract_id: int | None,
) -> list[dict[str, Any]]:
    project_value = _upper(project_code)
    org_id = int(organization_id or 0) or None
    contract_id = int(organization_contract_id or 0) or None
    query = (
        db.query(SiteLogActivityCatalog)
        .options(
            joinedload(SiteLogActivityCatalog.organization),
            joinedload(SiteLogActivityCatalog.organization_contract).joinedload(OrganizationContract.block),
            joinedload(SiteLogActivityCatalog.pms_mapping).joinedload(SiteLogActivityPmsMapping.template),
            joinedload(SiteLogActivityCatalog.pms_mapping).selectinload(SiteLogActivityPmsMapping.steps),
        )
        .filter(
            SiteLogActivityCatalog.project_code == project_value,
            SiteLogActivityCatalog.is_active == True,
        )
    )
    rows = query.order_by(
        SiteLogActivityCatalog.sort_order.asc(),
        SiteLogActivityCatalog.activity_code.asc(),
        SiteLogActivityCatalog.id.asc(),
    ).all()

    selected: list[SiteLogActivityCatalog] = []
    seen_codes: set[str] = set()

    def append_matches(matches: list[SiteLogActivityCatalog]) -> None:
        for item in matches:
            code = _upper(item.activity_code)
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            selected.append(item)

    if contract_id:
        append_matches(
            [item for item in rows if int(item.organization_contract_id or 0) == contract_id]
        )
    if org_id:
        append_matches(
            [
                item
                for item in rows
                if int(item.organization_id or 0) == org_id and not item.organization_contract_id
            ]
        )
    append_matches(
        [item for item in rows if item.organization_id is None and item.organization_contract_id is None]
    )
    return [_serialize_activity_catalog_item(item) for item in selected]

class ManpowerIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    role_code: Optional[str] = Field(default=None, max_length=64)
    role_label: Optional[str] = Field(default=None, max_length=255)
    work_section_label: Optional[str] = Field(default=None, max_length=255)
    claimed_count: Optional[int] = Field(default=None, ge=0)
    claimed_hours: Optional[float] = Field(default=None, ge=0)
    verified_count: Optional[int] = Field(default=None, ge=0)
    verified_hours: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    sort_order: Optional[int] = 0


class EquipmentIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    equipment_code: Optional[str] = Field(default=None, max_length=64)
    equipment_label: Optional[str] = Field(default=None, max_length=255)
    work_location: Optional[str] = Field(default=None, max_length=255)
    claimed_count: Optional[int] = Field(default=None, ge=0)
    claimed_status: Optional[str] = Field(default=None, max_length=32)
    claimed_hours: Optional[float] = Field(default=None, ge=0)
    verified_count: Optional[int] = Field(default=None, ge=0)
    verified_status: Optional[str] = Field(default=None, max_length=32)
    verified_hours: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    sort_order: Optional[int] = 0


class ActivityIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    activity_code: Optional[str] = Field(default=None, max_length=64)
    activity_title: Optional[str] = Field(default=None, max_length=255)
    source_system: Optional[str] = Field(default="MANUAL", max_length=32)
    external_ref: Optional[str] = Field(default=None, max_length=128)
    claimed_progress_pct: Optional[float] = Field(default=None, ge=0, le=100)
    verified_progress_pct: Optional[float] = Field(default=None, ge=0, le=100)
    location: Optional[str] = Field(default=None, max_length=255)
    unit: Optional[str] = Field(default=None, max_length=64)
    personnel_count: Optional[int] = Field(default=None, ge=0)
    pms_mapping_id: Optional[int] = Field(default=None, ge=1)
    pms_template_code: Optional[str] = Field(default=None, max_length=64)
    pms_template_title: Optional[str] = Field(default=None, max_length=255)
    pms_template_version: Optional[int] = Field(default=None, ge=1)
    pms_step_code: Optional[str] = Field(default=None, max_length=64)
    pms_step_title: Optional[str] = Field(default=None, max_length=255)
    pms_step_weight_pct: Optional[float] = Field(default=None, ge=0, le=100)
    today_quantity: Optional[float] = Field(default=None, ge=0)
    cumulative_quantity: Optional[float] = Field(default=None, ge=0)
    activity_status: Optional[str] = Field(default=None, max_length=64)
    stop_reason: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = None
    sort_order: Optional[int] = 0


class MaterialIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    material_code: Optional[str] = Field(default=None, max_length=64)
    title: Optional[str] = Field(default=None, max_length=255)
    consumption_location: Optional[str] = Field(default=None, max_length=255)
    unit: Optional[str] = Field(default=None, max_length=64)
    incoming_quantity: Optional[float] = Field(default=None, ge=0)
    consumed_quantity: Optional[float] = Field(default=None, ge=0)
    cumulative_quantity: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    sort_order: Optional[int] = 0


class IssueIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    issue_type: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    responsible_party: Optional[str] = Field(default=None, max_length=255)
    due_date: Optional[datetime | date] = None
    status: Optional[str] = Field(default=None, max_length=64)
    note: Optional[str] = None
    sort_order: Optional[int] = 0


class AttachmentRowIn(BaseModel):
    id: Optional[int] = Field(default=None, ge=1)
    attachment_type: Optional[str] = Field(default=None, max_length=64)
    title: Optional[str] = Field(default=None, max_length=255)
    reference_no: Optional[str] = Field(default=None, max_length=128)
    note: Optional[str] = None
    linked_attachment_id: Optional[int] = Field(default=None, ge=1)
    sort_order: Optional[int] = 0


class SiteLogCreateIn(BaseModel):
    log_type: str = Field(..., max_length=32)
    project_code: str = Field(..., max_length=50)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    organization_id: Optional[int] = Field(default=None, ge=1)
    organization_contract_id: Optional[int] = Field(default=None, ge=1)
    log_date: datetime | date
    work_status: Optional[str] = Field(default="ACTIVE", max_length=32)
    shift: Optional[str] = Field(default=None, max_length=64)
    contract_number: Optional[str] = Field(default=None, max_length=128)
    contract_subject: Optional[str] = Field(default=None, max_length=500)
    contract_block: Optional[str] = Field(default=None, max_length=255)
    qc_open_punch_count: Optional[int] = Field(default=None, ge=0)
    qc_summary_note: Optional[str] = None
    weather: Optional[str] = Field(default=None, max_length=64)
    summary: Optional[str] = None
    current_work_summary: Optional[str] = None
    next_plan_summary: Optional[str] = None
    status_code: Optional[str] = Field(default="DRAFT", max_length=32)
    manpower_rows: list[ManpowerIn] = Field(default_factory=list)
    equipment_rows: list[EquipmentIn] = Field(default_factory=list)
    activity_rows: list[ActivityIn] = Field(default_factory=list)
    material_rows: list[MaterialIn] = Field(default_factory=list)
    issue_rows: list[IssueIn] = Field(default_factory=list)
    attachment_rows: list[AttachmentRowIn] = Field(default_factory=list)


class SiteLogUpdateIn(BaseModel):
    log_type: Optional[str] = Field(default=None, max_length=32)
    project_code: Optional[str] = Field(default=None, max_length=50)
    discipline_code: Optional[str] = Field(default=None, max_length=20)
    organization_id: Optional[int] = Field(default=None, ge=1)
    organization_contract_id: Optional[int] = Field(default=None, ge=1)
    log_date: Optional[datetime | date] = None
    work_status: Optional[str] = Field(default=None, max_length=32)
    shift: Optional[str] = Field(default=None, max_length=64)
    contract_number: Optional[str] = Field(default=None, max_length=128)
    contract_subject: Optional[str] = Field(default=None, max_length=500)
    contract_block: Optional[str] = Field(default=None, max_length=255)
    qc_open_punch_count: Optional[int] = Field(default=None, ge=0)
    qc_summary_note: Optional[str] = None
    weather: Optional[str] = Field(default=None, max_length=64)
    summary: Optional[str] = None
    current_work_summary: Optional[str] = None
    next_plan_summary: Optional[str] = None
    manpower_rows: Optional[list[ManpowerIn]] = None
    equipment_rows: Optional[list[EquipmentIn]] = None
    activity_rows: Optional[list[ActivityIn]] = None
    material_rows: Optional[list[MaterialIn]] = None
    issue_rows: Optional[list[IssueIn]] = None
    attachment_rows: Optional[list[AttachmentRowIn]] = None


class SubmitIn(BaseModel):
    note: Optional[str] = None


class ReturnIn(BaseModel):
    note: str = Field(..., min_length=1)


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
            "id": _to_int(r.id),
            "role_code": _upper(r.role_code) or None,
            "role_label": _norm(r.role_label) or None,
            "work_section_label": _norm(r.work_section_label) or None,
            "claimed_count": _to_int(r.claimed_count),
            "claimed_hours": _to_float(r.claimed_hours),
            "verified_count": _to_int(r.verified_count),
            "verified_hours": _to_float(r.verified_hours),
            "note": _norm(r.note) or None,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any([row["role_code"], row["role_label"], row["work_section_label"], row["claimed_count"] is not None, row["claimed_hours"] is not None, row["verified_count"] is not None, row["verified_hours"] is not None, row["note"]]):
            out.append(row)
    return out


def _sanitize_equipment(rows: list[EquipmentIn] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows or []):
        row = {
            "id": _to_int(r.id),
            "equipment_code": _upper(r.equipment_code) or None,
            "equipment_label": _norm(r.equipment_label) or None,
            "work_location": _norm(r.work_location) or None,
            "claimed_count": _to_int(r.claimed_count),
            "claimed_status": _upper(r.claimed_status) or None,
            "claimed_hours": _to_float(r.claimed_hours),
            "verified_count": _to_int(r.verified_count),
            "verified_status": _upper(r.verified_status) or None,
            "verified_hours": _to_float(r.verified_hours),
            "note": _norm(r.note) or None,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any([
            row["equipment_code"],
            row["equipment_label"],
            row["work_location"],
            row["claimed_count"] is not None,
            row["claimed_status"],
            row["claimed_hours"] is not None,
            row["verified_count"] is not None,
            row["verified_status"],
            row["verified_hours"] is not None,
            row["note"],
        ]):
            out.append(row)
    return out


def _sanitize_activity(rows: list[ActivityIn] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows or []):
        row = {
            "id": _to_int(r.id),
            "activity_code": _upper(r.activity_code) or None,
            "activity_title": _norm(r.activity_title) or None,
            "source_system": _upper(r.source_system) or "MANUAL",
            "external_ref": _norm(r.external_ref) or None,
            "claimed_progress_pct": _to_float(r.claimed_progress_pct),
            "verified_progress_pct": _to_float(r.verified_progress_pct),
            "location": _norm(r.location) or None,
            "unit": _norm(r.unit) or None,
            "personnel_count": _to_int(r.personnel_count),
            "pms_mapping_id": _to_int(r.pms_mapping_id),
            "pms_template_code": _upper(r.pms_template_code) or None,
            "pms_template_title": _norm(r.pms_template_title) or None,
            "pms_template_version": _to_int(r.pms_template_version),
            "pms_step_code": _upper(r.pms_step_code) or None,
            "pms_step_title": _norm(r.pms_step_title) or None,
            "pms_step_weight_pct": _to_float(r.pms_step_weight_pct),
            "today_quantity": _to_float(r.today_quantity),
            "cumulative_quantity": _to_float(r.cumulative_quantity),
            "activity_status": _norm(r.activity_status) or None,
            "stop_reason": _norm(r.stop_reason) or None,
            "note": _norm(r.note) or None,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any(
            [
                row["activity_code"],
                row["activity_title"],
                row["external_ref"],
                row["claimed_progress_pct"] is not None,
                row["verified_progress_pct"] is not None,
                row["location"],
                row["unit"],
                row["personnel_count"] is not None,
                row["pms_mapping_id"],
                row["pms_step_code"],
                row["today_quantity"] is not None,
                row["cumulative_quantity"] is not None,
                row["activity_status"],
                row["stop_reason"],
                row["note"],
            ]
        ):
            out.append(row)
    return out


def _apply_activity_pms_snapshots(db: Session, rows: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if rows is None:
        return None
    mapping_ids = sorted({int(row.get("pms_mapping_id") or 0) for row in rows if int(row.get("pms_mapping_id") or 0) > 0})
    mappings: dict[int, SiteLogActivityPmsMapping] = {}
    if mapping_ids:
        loaded = (
            db.query(SiteLogActivityPmsMapping)
            .options(
                joinedload(SiteLogActivityPmsMapping.template),
                selectinload(SiteLogActivityPmsMapping.steps),
            )
            .filter(SiteLogActivityPmsMapping.id.in_(mapping_ids))
            .all()
        )
        mappings = {int(row.id or 0): row for row in loaded}
    for row in rows:
        mapping_id = int(row.get("pms_mapping_id") or 0)
        step_code = _upper(row.get("pms_step_code"))
        if mapping_id <= 0:
            row["pms_mapping_id"] = None
            row["pms_template_code"] = None
            row["pms_template_title"] = None
            row["pms_template_version"] = None
            row["pms_step_code"] = None
            row["pms_step_title"] = None
            row["pms_step_weight_pct"] = None
            continue
        mapping = mappings.get(mapping_id)
        if not mapping:
            raise HTTPException(status_code=404, detail=f"PMS mapping not found: {mapping_id}")
        row["pms_template_code"] = _upper(mapping.template_code)
        row["pms_template_title"] = _norm(mapping.template_title) or None
        row["pms_template_version"] = int(mapping.snapshot_version or 1)
        if not step_code:
            row["pms_step_code"] = None
            row["pms_step_title"] = None
            row["pms_step_weight_pct"] = None
            continue
        step = next((item for item in mapping.steps or [] if bool(item.is_active) and _upper(item.step_code) == step_code), None)
        if not step:
            raise HTTPException(status_code=400, detail=f"PMS step is not valid for the selected activity: {step_code}")
        row["pms_step_code"] = _upper(step.step_code)
        row["pms_step_title"] = _norm(step.step_title) or None
        row["pms_step_weight_pct"] = float(step.weight_pct or 0)
    return rows


def _sanitize_material(rows: list[MaterialIn] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows or []):
        row = {
            "id": _to_int(r.id),
            "material_code": _upper(r.material_code) or None,
            "title": _norm(r.title) or None,
            "consumption_location": _norm(r.consumption_location) or None,
            "unit": _norm(r.unit) or None,
            "incoming_quantity": _to_float(r.incoming_quantity),
            "consumed_quantity": _to_float(r.consumed_quantity),
            "cumulative_quantity": _to_float(r.cumulative_quantity),
            "note": _norm(r.note) or None,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any(
            [
                row["material_code"],
                row["title"],
                row["consumption_location"],
                row["unit"],
                row["incoming_quantity"] is not None,
                row["consumed_quantity"] is not None,
                row["cumulative_quantity"] is not None,
                row["note"],
            ]
        ):
            out.append(row)
    return out


def _sanitize_issue(rows: list[IssueIn] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows or []):
        row = {
            "id": _to_int(r.id),
            "issue_type": _upper(r.issue_type) or None,
            "description": _norm(r.description) or None,
            "responsible_party": _norm(r.responsible_party) or None,
            "due_date": _to_day_start(r.due_date),
            "status": _norm(r.status) or None,
            "note": _norm(r.note) or None,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any(
            [
                row["issue_type"],
                row["description"],
                row["responsible_party"],
                row["due_date"] is not None,
                row["status"],
                row["note"],
            ]
        ):
            out.append(row)
    return out


def _validate_issue_rows(
    db: Session,
    rows: list[dict[str, Any]] | None,
    *,
    existing_rows: list[SiteLogIssueRow] | None = None,
) -> list[dict[str, Any]] | None:
    if rows is None:
        return None
    valid_codes = {
        _upper(code)
        for (code,) in db.query(SiteLogIssueTypeCatalog.code)
        .filter(SiteLogIssueTypeCatalog.is_active == True)
        .all()
    }
    existing_by_id = {int(item.id or 0): _upper(item.issue_type) for item in existing_rows or [] if int(item.id or 0) > 0}
    existing_by_sort = {int(item.sort_order or 0): _upper(item.issue_type) for item in existing_rows or []}
    for row in rows:
        code = _upper(row.get("issue_type"))
        if not code:
            row["issue_type"] = None
            continue
        if code in valid_codes:
            row["issue_type"] = code
            continue
        row_id = _to_int(row.get("id"))
        sort_order = int(_to_int(row.get("sort_order")) or 0)
        unchanged_legacy = (row_id and existing_by_id.get(row_id) == code) or existing_by_sort.get(sort_order) == code
        if unchanged_legacy:
            row["issue_type"] = code
            continue
        raise HTTPException(status_code=400, detail=f"Invalid issue_type: {code}")
    return rows


def _sanitize_attachment_rows(db: Session, rows: list[AttachmentRowIn] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    valid_attachment_ids = {
        int(row.id or 0): True
        for row in db.query(SiteLogAttachment.id).all()
    }
    for i, r in enumerate(rows or []):
        linked_attachment_id = _to_int(r.linked_attachment_id)
        if linked_attachment_id and linked_attachment_id not in valid_attachment_ids:
            raise HTTPException(status_code=404, detail=f"Linked attachment not found: {linked_attachment_id}")
        row = {
            "id": _to_int(r.id),
            "attachment_type": _norm(r.attachment_type) or None,
            "title": _norm(r.title) or None,
            "reference_no": _norm(r.reference_no) or None,
            "note": _norm(r.note) or None,
            "linked_attachment_id": linked_attachment_id,
            "sort_order": int(r.sort_order if r.sort_order is not None else i),
        }
        if any([row["attachment_type"], row["title"], row["reference_no"], row["note"], row["linked_attachment_id"]]):
            out.append(row)
    return out


def _ensure_attachment_links_for_log(
    db: Session,
    log_id: int | None,
    attachment_rows: list[dict[str, Any]] | None,
) -> None:
    if not attachment_rows:
        return
    if not log_id:
        if any(item.get("linked_attachment_id") for item in attachment_rows):
            raise HTTPException(status_code=400, detail="Linked attachments are available only after the site log is saved.")
        return
    for item in attachment_rows:
        linked_attachment_id = _to_int(item.get("linked_attachment_id"))
        if not linked_attachment_id:
            continue
        linked_log_id = _to_int(db.query(SiteLogAttachment.site_log_id).filter(SiteLogAttachment.id == linked_attachment_id).scalar())
        if linked_log_id != int(log_id):
            raise HTTPException(status_code=400, detail="Linked attachment must belong to the same site log.")


def _apply_qc_snapshot_to_row(
    row: SiteLog,
    *,
    db: Session,
    project_code: str | None,
    organization_id: int | None,
    log_date: date | datetime | None,
    qc_open_punch_count: int | None,
    qc_summary_note: str | None,
) -> None:
    snapshot = _build_qc_snapshot(
        db,
        project_code=project_code,
        organization_id=organization_id,
        log_date=log_date,
    )
    row.qc_test_count = int(snapshot.get("qc_test_count") or 0)
    row.qc_inspection_count = int(snapshot.get("qc_inspection_count") or 0)
    row.qc_open_ncr_count = int(snapshot.get("qc_open_ncr_count") or 0)
    row.qc_snapshot_at = datetime.utcnow()
    row.qc_open_punch_count = _to_int(qc_open_punch_count)
    row.qc_summary_note = _norm(qc_summary_note) or None


def _replace_rows(
    row: SiteLog,
    manpower: list[dict[str, Any]] | None,
    equipment: list[dict[str, Any]] | None,
    activity: list[dict[str, Any]] | None,
    material: list[dict[str, Any]] | None = None,
    issue: list[dict[str, Any]] | None = None,
    attachment_rows: list[dict[str, Any]] | None = None,
) -> None:
    def sync_collection(attr_name: str, model: Any, payload_rows: list[dict[str, Any]] | None) -> None:
        if payload_rows is None:
            return
        collection = getattr(row, attr_name)
        existing_rows = list(collection or [])
        by_id = {int(item.id or 0): item for item in existing_rows if int(item.id or 0) > 0}
        by_sort_order = {int(item.sort_order or 0): item for item in existing_rows}
        used_ids: set[int] = set()
        next_rows = []
        for payload in payload_rows:
            values = dict(payload)
            payload_id = _to_int(values.pop("id", None))
            target = by_id.get(int(payload_id or 0)) if payload_id else None
            if target is None:
                sort_order = int(_to_int(values.get("sort_order")) or 0)
                candidate = by_sort_order.get(sort_order)
                candidate_id = int(candidate.id or 0) if candidate is not None else 0
                if candidate is not None and candidate_id not in used_ids:
                    target = candidate
            if target is None:
                target = model()
            for field_name, field_value in values.items():
                setattr(target, field_name, field_value)
            target_id = int(target.id or 0)
            if target_id > 0:
                used_ids.add(target_id)
            next_rows.append(target)
        collection[:] = next_rows

    sync_collection("manpower_rows", SiteLogManpowerRow, manpower)
    sync_collection("equipment_rows", SiteLogEquipmentRow, equipment)
    sync_collection("activity_rows", SiteLogActivityRow, activity)
    sync_collection("material_rows", SiteLogMaterialRow, material)
    sync_collection("issue_rows", SiteLogIssueRow, issue)
    sync_collection("attachment_rows", SiteLogAttachmentRow, attachment_rows)


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
            if p.get("verified_count") is not None:
                target.verified_count = p.get("verified_count")
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
    orgs = (
        apply_organization_query_filters(
            db.query(Organization)
            .options(joinedload(Organization.contracts).joinedload(OrganizationContract.block))
            .filter(Organization.is_active == True),
            db,
            user,
            organization_column=Organization.id,
        )
        .order_by(Organization.name.asc())
        .all()
    )
    statuses = db.query(SiteLogWorkflowStatus).filter(SiteLogWorkflowStatus.is_active == True).order_by(SiteLogWorkflowStatus.sort_order.asc(), SiteLogWorkflowStatus.code.asc()).all()
    role_catalog = db.query(SiteLogRoleCatalog).filter(SiteLogRoleCatalog.is_active == True).order_by(SiteLogRoleCatalog.sort_order.asc(), SiteLogRoleCatalog.code.asc()).all()
    work_section_catalog = db.query(SiteLogWorkSectionCatalog).filter(SiteLogWorkSectionCatalog.is_active == True).order_by(SiteLogWorkSectionCatalog.sort_order.asc(), SiteLogWorkSectionCatalog.code.asc()).all()
    equipment_catalog = db.query(SiteLogEquipmentCatalog).filter(SiteLogEquipmentCatalog.is_active == True).order_by(SiteLogEquipmentCatalog.sort_order.asc(), SiteLogEquipmentCatalog.code.asc()).all()
    material_catalog_rows = db.query(SiteLogMaterialCatalog).filter(SiteLogMaterialCatalog.is_active == True).order_by(SiteLogMaterialCatalog.sort_order.asc(), SiteLogMaterialCatalog.code.asc()).all()
    equipment_status_catalog = db.query(SiteLogEquipmentStatusCatalog).filter(SiteLogEquipmentStatusCatalog.is_active == True).order_by(SiteLogEquipmentStatusCatalog.sort_order.asc(), SiteLogEquipmentStatusCatalog.code.asc()).all()
    attachment_type_catalog = db.query(SiteLogAttachmentTypeCatalog).filter(SiteLogAttachmentTypeCatalog.is_active == True).order_by(SiteLogAttachmentTypeCatalog.sort_order.asc(), SiteLogAttachmentTypeCatalog.code.asc()).all()
    issue_type_catalog = db.query(SiteLogIssueTypeCatalog).filter(SiteLogIssueTypeCatalog.is_active == True).order_by(SiteLogIssueTypeCatalog.sort_order.asc(), SiteLogIssueTypeCatalog.code.asc()).all()
    shift_catalog = db.query(SiteLogShiftCatalog).filter(SiteLogShiftCatalog.is_active == True).order_by(SiteLogShiftCatalog.sort_order.asc(), SiteLogShiftCatalog.code.asc()).all()
    weather_catalog = db.query(SiteLogWeatherCatalog).filter(SiteLogWeatherCatalog.is_active == True).order_by(SiteLogWeatherCatalog.sort_order.asc(), SiteLogWeatherCatalog.code.asc()).all()
    material_query = (
        db.query(SiteLogMaterialRow.material_code, SiteLogMaterialRow.title, SiteLogMaterialRow.unit)
        .join(SiteLog, SiteLog.id == SiteLogMaterialRow.site_log_id)
        .filter(or_(SiteLogMaterialRow.material_code.isnot(None), SiteLogMaterialRow.title.isnot(None)))
    )
    material_query = apply_scope_query_filters(material_query, db, user, project_column=SiteLog.project_code, discipline_column=None)
    material_query = apply_organization_query_filters(material_query, db, user, organization_column=SiteLog.organization_id)
    material_rows = material_query.order_by(SiteLogMaterialRow.title.asc(), SiteLogMaterialRow.material_code.asc()).limit(500).all()
    material_catalog: list[dict[str, str | None]] = [
        {"code": x.code, "label": x.label, "unit": None}
        for x in material_catalog_rows
    ]
    seen_materials: set[tuple[str, str]] = {
        (_upper(x.code), _norm(x.label)) for x in material_catalog_rows
    }
    for material_code, title, unit in material_rows:
        code = _upper(material_code)
        label = _norm(title)
        if not code and not label:
            continue
        key = (code, label)
        if key in seen_materials:
            continue
        seen_materials.add(key)
        material_catalog.append({"code": code, "label": label or code, "unit": _norm(unit) or None})
    return {
        "ok": True,
        "log_types": [{"code": "DAILY", "label": "Daily Report"}, {"code": "WEEKLY", "label": "Weekly Report"}, {"code": "SAFETY_INCIDENT", "label": "Safety Incident"}],
        "work_statuses": [
            {"code": "ACTIVE", "label": WORK_STATUS_LABELS["ACTIVE"], "sort_order": 10},
            {"code": "HOLIDAY", "label": WORK_STATUS_LABELS["HOLIDAY"], "sort_order": 20},
            {"code": "INACTIVE", "label": WORK_STATUS_LABELS["INACTIVE"], "sort_order": 30},
        ],
        "workflow_statuses": [{"code": x.code, "label": x.label, "sort_order": x.sort_order} for x in statuses],
        "section_codes": sorted(list(SECTIONS)),
        "projects": [{"code": x.code, "name": x.name_e or x.name_p or x.code} for x in projects],
        "disciplines": [{"code": x.code, "name": x.name_e or x.name_p or x.code} for x in disciplines],
        "organizations": [
            {
                "id": x.id,
                "name": x.name,
                "org_type": x.org_type,
                "contracts": [
                    {
                        "id": c.id,
                        "organization_id": c.organization_id,
                        "contract_number": c.contract_number,
                        "subject": c.subject,
                        "block_id": c.block_id,
                        "block_name": (c.block.name_e or c.block.name_p or c.block.code) if c.block else None,
                    }
                    for c in x.contracts
                ],
            }
            for x in orgs
        ],
        "role_catalog": [{"code": x.code, "label": x.label} for x in role_catalog],
        "work_section_catalog": [{"code": x.code, "label": x.label} for x in work_section_catalog],
        "equipment_catalog": [{"code": x.code, "label": x.label} for x in equipment_catalog],
        "material_catalog": material_catalog,
        "equipment_status_catalog": [{"code": x.code, "label": x.label} for x in equipment_status_catalog],
        "attachment_type_catalog": [{"code": x.code, "label": x.label} for x in attachment_type_catalog],
        "issue_type_catalog": [{"code": x.code, "label": x.label} for x in issue_type_catalog],
        "shift_catalog": [{"code": x.code, "label": x.label} for x in shift_catalog],
        "weather_catalog": [{"code": x.code, "label": x.label} for x in weather_catalog],
    }


@router.get("/activity-options")
def activity_options(
    project_code: str = Query(..., min_length=1),
    organization_id: Optional[int] = Query(default=None, ge=1),
    organization_contract_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:read")),
):
    project_value = _upper(project_code)
    _check_project_exists(db, project_value)
    enforce_scope_access(db, user, project_code=project_value)
    _check_optional_org(db, organization_id)
    if organization_id:
        enforce_organization_access(db, user, organization_id=organization_id)
    contract = _check_optional_org_contract(db, organization_contract_id, organization_id)
    items = _load_activity_option_rows(
        db,
        project_code=project_value,
        organization_id=organization_id or getattr(contract, "organization_id", None),
        organization_contract_id=organization_contract_id,
    )
    return {
        "ok": True,
        "project_code": project_value,
        "organization_id": organization_id or getattr(contract, "organization_id", None),
        "organization_contract_id": organization_contract_id,
        "data": items,
    }


@router.get("/qc-snapshot")
def qc_snapshot(
    project_code: str = Query(..., min_length=1),
    organization_id: Optional[int] = Query(default=None, ge=1),
    log_date: datetime | date = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:read")),
):
    project_value = _upper(project_code)
    _check_project_exists(db, project_value)
    enforce_scope_access(db, user, project_code=project_value)
    _check_optional_org(db, organization_id)
    if organization_id:
        enforce_organization_access(db, user, organization_id=organization_id)
    snapshot = _build_qc_snapshot(
        db,
        project_code=project_value,
        organization_id=organization_id,
        log_date=log_date,
    )
    snapshot["ok"] = True
    snapshot["project_code"] = project_value
    snapshot["organization_id"] = organization_id
    snapshot["log_date"] = _to_iso(_to_day_start(log_date))
    return snapshot


@router.get("/list")
def list_logs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    module_key: Optional[str] = Query(default=None),
    tab_key: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    organization_id: Optional[int] = Query(default=None, ge=1),
    organization_contract_id: Optional[int] = Query(default=None, ge=1),
    log_type: Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    work_status: Optional[str] = Query(default=None),
    log_date_from: Optional[str] = Query(default=None),
    log_date_to: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:read")),
):
    q = db.query(SiteLog).options(joinedload(SiteLog.organization))
    q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=None)
    q = apply_organization_query_filters(q, db, user, organization_column=SiteLog.organization_id)
    selected_contract = _check_optional_org_contract(db, organization_contract_id, organization_id)
    if organization_id:
        _check_optional_org(db, organization_id)
        enforce_organization_access(db, user, organization_id=organization_id)
        q = q.filter(SiteLog.organization_id == organization_id)
    if selected_contract and getattr(selected_contract, "organization_id", None):
        enforce_organization_access(db, user, organization_id=int(selected_contract.organization_id))
    if organization_contract_id:
        q = q.filter(SiteLog.organization_contract_id == organization_contract_id)
    if project_code:
        q = q.filter(SiteLog.project_code == _upper(project_code))
    if discipline_code:
        q = q.filter(SiteLog.discipline_code == _upper(discipline_code))
    if log_type:
        q = q.filter(SiteLog.log_type == _normalize_log_type(log_type))
    if status_code:
        q = q.filter(SiteLog.status_code == _normalize_status(status_code))
    if work_status:
        q = q.filter(SiteLog.work_status == _normalize_work_status(work_status))
    if log_date_from:
        q = q.filter(SiteLog.log_date >= _parse_query_day(log_date_from, "log_date_from"))
    if log_date_to:
        d = _parse_query_day(log_date_to, "log_date_to")
        if d:
            q = q.filter(SiteLog.log_date <= d.replace(hour=23, minute=59, second=59))
    if _norm(module_key).lower() == "consultant" and _norm(tab_key).lower() == "inspection" and not status_code:
        q = q.filter(SiteLog.status_code == "SUBMITTED")
    if _norm(search):
        pattern = f"%{_norm(search)}%"
        q = q.filter(
            or_(
                SiteLog.log_no.ilike(pattern),
                SiteLog.summary.ilike(pattern),
                SiteLog.current_work_summary.ilike(pattern),
                SiteLog.next_plan_summary.ilike(pattern),
                SiteLog.contract_number.ilike(pattern),
                SiteLog.contract_subject.ilike(pattern),
                SiteLog.contract_block.ilike(pattern),
                SiteLog.qc_summary_note.ilike(pattern),
                SiteLog.weather.ilike(pattern),
                SiteLog.organization.has(Organization.name.ilike(pattern)),
            )
        )
    total = q.count()
    rows = q.order_by(SiteLog.log_date.desc(), SiteLog.id.desc()).offset(skip).limit(limit).all()
    labels = _site_log_choice_labels(db)
    return {"ok": True, "total": total, "count": len(rows), "data": [_serialize(x, include_rows=False, catalog_labels=labels) for x in rows]}


@router.post("/create")
def create_log(payload: SiteLogCreateIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:create"))):
    _require_contractor_flow(user)
    pcode = _upper(payload.project_code)
    dcode = _upper(payload.discipline_code)
    ltype = _normalize_log_type(payload.log_type)
    work_status = _normalize_work_status(payload.work_status)
    status = _normalize_status(payload.status_code, "DRAFT")
    if not _is_admin(user) and status != "DRAFT":
        raise HTTPException(status_code=400, detail="Contractor users can only create DRAFT site logs.")
    ldate = _to_day_start(payload.log_date)
    if not ldate:
        raise HTTPException(status_code=400, detail="log_date is required")
    _check_project_exists(db, pcode)
    _check_optional_discipline(db, dcode)
    enforce_scope_access(db, user, project_code=pcode)
    selected_contract = _check_optional_org_contract(db, payload.organization_contract_id, payload.organization_id)
    organization_id = payload.organization_id or getattr(selected_contract, "organization_id", None)
    _check_optional_org(db, organization_id)
    if organization_id:
        enforce_organization_access(db, user, organization_id=organization_id)
    organization_contract_id, contract_number, contract_subject, contract_block = _resolve_contract_snapshot(
        db,
        organization_id=organization_id,
        organization_contract_id=payload.organization_contract_id,
        contract_number=payload.contract_number,
        contract_subject=payload.contract_subject,
        contract_block=payload.contract_block,
    )
    manpower = _sanitize_manpower(payload.manpower_rows)
    equipment = _sanitize_equipment(payload.equipment_rows)
    activity = _sanitize_activity(payload.activity_rows)
    activity = _apply_activity_pms_snapshots(db, activity) or []
    material = _sanitize_material(payload.material_rows)
    issue = _sanitize_issue(payload.issue_rows)
    issue = _validate_issue_rows(db, issue) or []
    attachment_rows = _sanitize_attachment_rows(db, payload.attachment_rows)
    shift_code = _validate_active_choice_code(db, SiteLogShiftCatalog, payload.shift, "shift")
    weather_code = _validate_active_choice_code(db, SiteLogWeatherCatalog, payload.weather, "weather")
    if not _is_admin(user) and _has_verified_payload(manpower, equipment, activity):
        raise HTTPException(status_code=403, detail="Contractor users cannot write verified values.")
    row = SiteLog(
        log_no=_next_log_no(db, project_code=pcode, log_type=ltype, log_date=ldate),
        log_type=ltype,
        project_code=pcode,
        discipline_code=dcode or None,
        organization_id=organization_id,
        organization_contract_id=organization_contract_id,
        log_date=ldate,
        work_status=work_status,
        shift=shift_code,
        contract_number=contract_number,
        contract_subject=contract_subject,
        contract_block=contract_block,
        weather=weather_code,
        summary=_compose_summary_text(payload.current_work_summary, payload.next_plan_summary, payload.summary),
        current_work_summary=_norm(payload.current_work_summary) or None,
        next_plan_summary=_norm(payload.next_plan_summary) or None,
        status_code=status,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    _ensure_attachment_links_for_log(db, int(row.id), attachment_rows)
    _replace_rows(row, manpower, equipment, activity, material, issue, attachment_rows)
    _apply_qc_snapshot_to_row(
        row,
        db=db,
        project_code=pcode,
        organization_id=organization_id,
        log_date=ldate,
        qc_open_punch_count=payload.qc_open_punch_count,
        qc_summary_note=payload.qc_summary_note,
    )
    _record_status(db, site_log_id=int(row.id), from_status=None, to_status=status, user_id=getattr(user, "id", None))
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, int(row.id)), include_rows=True, catalog_labels=_site_log_choice_labels(db))}

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
    q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=None)
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
    q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=None)
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
    totals = {
        "manpower_count_delta": 0.0,
        "manpower_hours_delta": 0.0,
        "equipment_count_delta": 0.0,
        "equipment_hours_delta": 0.0,
        "activity_progress_delta": 0.0,
    }
    for x in rows:
        mc = sum(float(v.claimed_count or 0) for v in x.manpower_rows)
        mv = sum(float(v.verified_count or 0) for v in x.manpower_rows)
        mhc = sum(float(v.claimed_hours or 0) for v in x.manpower_rows)
        mhv = sum(float(v.verified_hours or 0) for v in x.manpower_rows)
        ec = sum(float(v.claimed_count or 0) for v in x.equipment_rows)
        ev = sum(float(v.verified_count or 0) for v in x.equipment_rows)
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
            "equipment_count_delta": round(ev - ec, 2),
            "equipment_hours_delta": round(ehv - ehc, 2),
            "activity_progress_delta": round(apv - apc, 2),
        }
        data.append(row)
        totals["manpower_count_delta"] += row["manpower_count_delta"]
        totals["manpower_hours_delta"] += row["manpower_hours_delta"]
        totals["equipment_count_delta"] += row["equipment_count_delta"]
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
    q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=None)
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


def _site_log_common_report_columns() -> list[dict[str, Any]]:
    return [
        {"key": "log_no", "label": "شماره گزارش", "type": "text"},
        {"key": "log_date", "label": "تاریخ", "type": "date"},
        {"key": "project_code", "label": "پروژه", "type": "text"},
        {"key": "discipline_code", "label": "دیسپلین", "type": "text"},
        {"key": "organization_name", "label": "سازمان", "type": "text"},
        {"key": "contract_number", "label": "قرارداد", "type": "text"},
        {"key": "contract_subject", "label": "موضوع قرارداد", "type": "text"},
        {"key": "contract_block", "label": "بلوک", "type": "text"},
        {"key": "log_type_label", "label": "نوع گزارش", "type": "text"},
        {"key": "work_status_label", "label": "وضعیت کارگاه", "type": "text"},
        {"key": "shift_label", "label": "شیفت", "type": "text"},
        {"key": "status_label", "label": "وضعیت", "type": "text"},
    ]


def _site_log_report_columns(report_section: str = "general") -> list[dict[str, Any]]:
    common = _site_log_common_report_columns()
    section = _normalize_report_section(report_section)
    if section == "manpower":
        return common + [
            {"key": "work_section_label", "label": "واحد / بخش کاری", "type": "text"},
            {"key": "role_code", "label": "کد نقش", "type": "text"},
            {"key": "role_label", "label": "عنوان نقش", "type": "text"},
            {"key": "claimed_count", "label": "تعداد اعلامی", "type": "number"},
            {"key": "verified_count", "label": "تعداد تاییدی", "type": "number"},
            {"key": "count_delta", "label": "اختلاف تعداد", "type": "number"},
            {"key": "claimed_hours", "label": "ساعت اعلامی", "type": "number"},
            {"key": "verified_hours", "label": "ساعت تاییدی", "type": "number"},
            {"key": "hours_delta", "label": "اختلاف ساعت", "type": "number"},
            {"key": "note", "label": "توضیحات", "type": "text"},
            {"key": "row_attachment_count", "label": "پیوست ردیف", "type": "number"},
            {"key": "log_id", "label": "شناسه گزارش", "type": "number"},
            {"key": "row_id", "label": "شناسه ردیف", "type": "number"},
        ]
    if section == "equipment":
        return common + [
            {"key": "equipment_code", "label": "کد تجهیز", "type": "text"},
            {"key": "equipment_label", "label": "عنوان تجهیز", "type": "text"},
            {"key": "work_location", "label": "محل کارکرد", "type": "text"},
            {"key": "claimed_count", "label": "تعداد اعلامی", "type": "number"},
            {"key": "verified_count", "label": "تعداد تاییدی", "type": "number"},
            {"key": "count_delta", "label": "اختلاف تعداد", "type": "number"},
            {"key": "claimed_status", "label": "وضعیت اعلامی", "type": "text"},
            {"key": "verified_status", "label": "وضعیت تاییدی", "type": "text"},
            {"key": "claimed_hours", "label": "ساعت اعلامی", "type": "number"},
            {"key": "verified_hours", "label": "ساعت تاییدی", "type": "number"},
            {"key": "hours_delta", "label": "اختلاف ساعت", "type": "number"},
            {"key": "note", "label": "توضیحات", "type": "text"},
            {"key": "row_attachment_count", "label": "پیوست ردیف", "type": "number"},
            {"key": "log_id", "label": "شناسه گزارش", "type": "number"},
            {"key": "row_id", "label": "شناسه ردیف", "type": "number"},
        ]
    if section == "material":
        return common + [
            {"key": "material_code", "label": "کد مصالح", "type": "text"},
            {"key": "material_title", "label": "عنوان مصالح", "type": "text"},
            {"key": "consumption_location", "label": "محل مصرف", "type": "text"},
            {"key": "unit", "label": "واحد", "type": "text"},
            {"key": "incoming_quantity", "label": "ورودی", "type": "number"},
            {"key": "consumed_quantity", "label": "مصرفی", "type": "number"},
            {"key": "cumulative_quantity", "label": "تجمعی", "type": "number"},
            {"key": "note", "label": "توضیحات", "type": "text"},
            {"key": "row_attachment_count", "label": "پیوست ردیف", "type": "number"},
            {"key": "log_id", "label": "شناسه گزارش", "type": "number"},
            {"key": "row_id", "label": "شناسه ردیف", "type": "number"},
        ]
    if section == "activity":
        return common + [
            {"key": "activity_code", "label": "کد فعالیت", "type": "text"},
            {"key": "activity_title", "label": "عنوان فعالیت", "type": "text"},
            {"key": "pms_step_title", "label": "مرحله PMS", "type": "text"},
            {"key": "location", "label": "محل", "type": "text"},
            {"key": "unit", "label": "واحد", "type": "text"},
            {"key": "today_quantity", "label": "امروز", "type": "number"},
            {"key": "cumulative_quantity", "label": "تجمعی", "type": "number"},
            {"key": "personnel_count", "label": "تعداد نفرات", "type": "number"},
            {"key": "claimed_progress_pct", "label": "پیشرفت اعلامی", "type": "percent"},
            {"key": "verified_progress_pct", "label": "پیشرفت تاییدی", "type": "percent"},
            {"key": "progress_delta_pct", "label": "اختلاف پیشرفت", "type": "percent"},
            {"key": "activity_status", "label": "وضعیت", "type": "text"},
            {"key": "stop_reason", "label": "دلیل توقف", "type": "text"},
            {"key": "note", "label": "توضیحات", "type": "text"},
            {"key": "row_attachment_count", "label": "پیوست ردیف", "type": "number"},
            {"key": "log_id", "label": "شناسه گزارش", "type": "number"},
            {"key": "row_id", "label": "شناسه ردیف", "type": "number"},
        ]
    return common + [
        {"key": "claimed_manpower_count", "label": "نفرات اعلامی", "type": "number"},
        {"key": "verified_manpower_count", "label": "نفرات تاییدی", "type": "number"},
        {"key": "manpower_count_delta", "label": "اختلاف نفرات", "type": "number"},
        {"key": "claimed_manpower_hours", "label": "ساعت نفرات اعلامی", "type": "number"},
        {"key": "verified_manpower_hours", "label": "ساعت نفرات تاییدی", "type": "number"},
        {"key": "manpower_hours_delta", "label": "اختلاف ساعت نفرات", "type": "number"},
        {"key": "claimed_equipment_count", "label": "تجهیزات اعلامی", "type": "number"},
        {"key": "verified_equipment_count", "label": "تجهیزات تاییدی", "type": "number"},
        {"key": "equipment_count_delta", "label": "اختلاف تجهیزات", "type": "number"},
        {"key": "claimed_equipment_hours", "label": "ساعت تجهیزات اعلامی", "type": "number"},
        {"key": "verified_equipment_hours", "label": "ساعت تجهیزات تاییدی", "type": "number"},
        {"key": "equipment_hours_delta", "label": "اختلاف ساعت تجهیزات", "type": "number"},
        {"key": "activity_count", "label": "تعداد فعالیت", "type": "number"},
        {"key": "claimed_avg_progress_pct", "label": "پیشرفت اعلامی", "type": "percent"},
        {"key": "verified_avg_progress_pct", "label": "پیشرفت تاییدی", "type": "percent"},
        {"key": "progress_delta_pct", "label": "اختلاف پیشرفت", "type": "percent"},
        {"key": "qc_test_count", "label": "QC Test", "type": "number"},
        {"key": "qc_inspection_count", "label": "Inspection", "type": "number"},
        {"key": "qc_open_ncr_count", "label": "NCR باز", "type": "number"},
        {"key": "qc_open_punch_count", "label": "Punch باز", "type": "number"},
        {"key": "issue_count", "label": "موانع", "type": "number"},
        {"key": "attachment_count", "label": "پیوست", "type": "number"},
        {"key": "log_id", "label": "شناسه", "type": "number"},
    ]


def _site_log_report_query(
    db: Session,
    user: User | None,
    *,
    bi_access: PowerBiReportAccess | None = None,
    project_code: str | None = None,
    discipline_code: str | None = None,
    log_type: str | None = None,
    status_code: str | None = None,
    organization_id: int | None = None,
    organization_contract_id: int | None = None,
    log_date_from: date | datetime | None = None,
    log_date_to: date | datetime | None = None,
    search: str | None = None,
):
    q = db.query(SiteLog).options(
        joinedload(SiteLog.organization),
        joinedload(SiteLog.organization_contract).joinedload(OrganizationContract.block),
        selectinload(SiteLog.manpower_rows),
        selectinload(SiteLog.equipment_rows),
        selectinload(SiteLog.activity_rows),
        selectinload(SiteLog.material_rows),
        selectinload(SiteLog.issue_rows),
        selectinload(SiteLog.attachment_rows),
        selectinload(SiteLog.attachments),
    )
    if user is not None:
        q = apply_scope_query_filters(q, db, user, project_column=SiteLog.project_code, discipline_column=None)
        q = apply_organization_query_filters(q, db, user, organization_column=SiteLog.organization_id)
    elif bi_access is not None and bi_access.allowed_project_codes:
        q = q.filter(SiteLog.project_code.in_(bi_access.allowed_project_codes))
    if project_code:
        q = q.filter(SiteLog.project_code == _upper(project_code))
    if discipline_code:
        q = q.filter(SiteLog.discipline_code == _upper(discipline_code))
    if log_type:
        q = q.filter(SiteLog.log_type == _normalize_log_type(log_type))
    if status_code:
        q = q.filter(SiteLog.status_code == _normalize_status(status_code))
    if organization_id:
        q = q.filter(SiteLog.organization_id == int(organization_id))
    if organization_contract_id:
        q = q.filter(SiteLog.organization_contract_id == int(organization_contract_id))
    if log_date_from:
        q = q.filter(SiteLog.log_date >= _to_day_start(log_date_from))
    if log_date_to:
        d = _to_day_start(log_date_to)
        if d:
            q = q.filter(SiteLog.log_date <= d.replace(hour=23, minute=59, second=59))
    if _norm(search):
        pattern = f"%{_norm(search)}%"
        q = q.filter(
            or_(
                SiteLog.log_no.ilike(pattern),
                SiteLog.project_code.ilike(pattern),
                SiteLog.discipline_code.ilike(pattern),
                SiteLog.summary.ilike(pattern),
                SiteLog.current_work_summary.ilike(pattern),
                SiteLog.next_plan_summary.ilike(pattern),
                SiteLog.contract_number.ilike(pattern),
                SiteLog.contract_subject.ilike(pattern),
                SiteLog.contract_block.ilike(pattern),
                SiteLog.qc_summary_note.ilike(pattern),
                SiteLog.organization.has(Organization.name.ilike(pattern)),
                SiteLog.manpower_rows.any(
                    or_(
                        SiteLogManpowerRow.role_code.ilike(pattern),
                        SiteLogManpowerRow.role_label.ilike(pattern),
                        SiteLogManpowerRow.work_section_label.ilike(pattern),
                        SiteLogManpowerRow.note.ilike(pattern),
                    )
                ),
                SiteLog.equipment_rows.any(
                    or_(
                        SiteLogEquipmentRow.equipment_code.ilike(pattern),
                        SiteLogEquipmentRow.equipment_label.ilike(pattern),
                        SiteLogEquipmentRow.work_location.ilike(pattern),
                        SiteLogEquipmentRow.claimed_status.ilike(pattern),
                        SiteLogEquipmentRow.verified_status.ilike(pattern),
                        SiteLogEquipmentRow.note.ilike(pattern),
                    )
                ),
                SiteLog.material_rows.any(
                    or_(
                        SiteLogMaterialRow.material_code.ilike(pattern),
                        SiteLogMaterialRow.title.ilike(pattern),
                        SiteLogMaterialRow.consumption_location.ilike(pattern),
                        SiteLogMaterialRow.unit.ilike(pattern),
                        SiteLogMaterialRow.note.ilike(pattern),
                    )
                ),
                SiteLog.activity_rows.any(
                    or_(
                        SiteLogActivityRow.activity_code.ilike(pattern),
                        SiteLogActivityRow.activity_title.ilike(pattern),
                        SiteLogActivityRow.pms_step_title.ilike(pattern),
                        SiteLogActivityRow.location.ilike(pattern),
                        SiteLogActivityRow.unit.ilike(pattern),
                        SiteLogActivityRow.activity_status.ilike(pattern),
                        SiteLogActivityRow.stop_reason.ilike(pattern),
                        SiteLogActivityRow.note.ilike(pattern),
                    )
                ),
            )
        )
    return q


def _sum_number(rows: list[Any], attr: str) -> float:
    return round(sum(float(getattr(row, attr, None) or 0) for row in rows), 2)


def _avg_number(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _site_log_report_base_fields(row: SiteLog, catalog_labels: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    log_type_code = _upper(row.log_type)
    status_code = _upper(row.status_code)
    work_status_code = _safe_work_status(row.work_status)
    return {
        "log_id": row.id,
        "log_no": row.log_no,
        "log_type": log_type_code,
        "log_type_label": LOG_TYPE_LABELS.get(log_type_code, log_type_code),
        "work_status": work_status_code,
        "work_status_label": WORK_STATUS_LABELS.get(work_status_code, work_status_code),
        "project_code": row.project_code,
        "discipline_code": row.discipline_code,
        "organization_id": row.organization_id,
        "organization_name": row.organization.name if row.organization else None,
        "organization_contract_id": row.organization_contract_id,
        "contract_number": row.contract_number,
        "contract_subject": row.contract_subject,
        "contract_block": row.contract_block,
        "log_date": _to_iso(row.log_date),
        "shift": row.shift,
        "shift_label": _choice_label(catalog_labels, "shift", row.shift),
        "status_code": status_code,
        "status_label": STATUS_LABELS.get(status_code, status_code),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


def _site_log_row_attachment_count(row: SiteLog, section_code: str, sort_order: Any, db_row_id: Any = None) -> int:
    attachments_by_section_row_id: dict[tuple[str, int], int] = {}
    for attachment in row.attachments or []:
        section = _upper(attachment.section_code)
        row_id = _to_int(attachment.row_id)
        if not row_id:
            continue
        attachments_by_section_row_id[(section, row_id)] = attachments_by_section_row_id.get((section, row_id), 0) + 1

    target_ids: list[int] = []
    stable_id = _to_int(db_row_id)
    if stable_id:
        target_ids.append(int(stable_id))
    ordinal_id = int(_to_int(sort_order) or 0) + 1
    if ordinal_id not in target_ids:
        target_ids.append(ordinal_id)
    section = _upper(section_code)
    return sum(attachments_by_section_row_id.get((section, row_id), 0) for row_id in target_ids)


def _site_log_report_row(row: SiteLog, catalog_labels: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    manpower_rows = list(row.manpower_rows or [])
    equipment_rows = list(row.equipment_rows or [])
    activity_rows = list(row.activity_rows or [])
    claimed_progress_values = [float(x.claimed_progress_pct) for x in activity_rows if x.claimed_progress_pct is not None]
    verified_progress_values = [float(x.verified_progress_pct) for x in activity_rows if x.verified_progress_pct is not None]
    claimed_progress = _avg_number(claimed_progress_values)
    verified_progress = _avg_number(verified_progress_values)
    claimed_manpower_count = _sum_number(manpower_rows, "claimed_count")
    verified_manpower_count = _sum_number(manpower_rows, "verified_count")
    claimed_manpower_hours = _sum_number(manpower_rows, "claimed_hours")
    verified_manpower_hours = _sum_number(manpower_rows, "verified_hours")
    claimed_equipment_count = _sum_number(equipment_rows, "claimed_count")
    verified_equipment_count = _sum_number(equipment_rows, "verified_count")
    claimed_equipment_hours = _sum_number(equipment_rows, "claimed_hours")
    verified_equipment_hours = _sum_number(equipment_rows, "verified_hours")
    return {
        **_site_log_report_base_fields(row, catalog_labels),
        "claimed_manpower_count": claimed_manpower_count,
        "verified_manpower_count": verified_manpower_count,
        "manpower_count_delta": round(verified_manpower_count - claimed_manpower_count, 2),
        "claimed_manpower_hours": claimed_manpower_hours,
        "verified_manpower_hours": verified_manpower_hours,
        "manpower_hours_delta": round(verified_manpower_hours - claimed_manpower_hours, 2),
        "claimed_equipment_count": claimed_equipment_count,
        "verified_equipment_count": verified_equipment_count,
        "equipment_count_delta": round(verified_equipment_count - claimed_equipment_count, 2),
        "claimed_equipment_hours": claimed_equipment_hours,
        "verified_equipment_hours": verified_equipment_hours,
        "equipment_hours_delta": round(verified_equipment_hours - claimed_equipment_hours, 2),
        "activity_count": len(activity_rows),
        "claimed_avg_progress_pct": claimed_progress,
        "verified_avg_progress_pct": verified_progress,
        "progress_delta_pct": (
            round((verified_progress or 0.0) - (claimed_progress or 0.0), 2)
            if claimed_progress is not None or verified_progress is not None
            else None
        ),
        "qc_test_count": int(row.qc_test_count or 0),
        "qc_inspection_count": int(row.qc_inspection_count or 0),
        "qc_open_ncr_count": int(row.qc_open_ncr_count or 0),
        "qc_open_punch_count": int(row.qc_open_punch_count or 0),
        "issue_count": len(row.issue_rows or []),
        "attachment_row_count": len(row.attachment_rows or []),
        "attachment_count": len(row.attachments or []),
    }


def _site_log_report_section_rows(
    row: SiteLog,
    report_section: str,
    catalog_labels: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    section = _normalize_report_section(report_section)
    if section == "general":
        return [_site_log_report_row(row, catalog_labels)]

    base = _site_log_report_base_fields(row, catalog_labels)
    rows: list[dict[str, Any]] = []
    if section == "manpower":
        for item in sorted(row.manpower_rows or [], key=lambda v: (v.sort_order or 0, v.id or 0)):
            claimed_count = float(item.claimed_count or 0)
            verified_count = float(item.verified_count or 0)
            claimed_hours = float(item.claimed_hours or 0)
            verified_hours = float(item.verified_hours or 0)
            rows.append(
                {
                    **base,
                    "row_id": item.id,
                    "row_sort_order": item.sort_order,
                    "work_section_label": item.work_section_label,
                    "role_code": item.role_code,
                    "role_label": item.role_label,
                    "claimed_count": round(claimed_count, 2),
                    "verified_count": round(verified_count, 2),
                    "count_delta": round(verified_count - claimed_count, 2),
                    "claimed_hours": round(claimed_hours, 2),
                    "verified_hours": round(verified_hours, 2),
                    "hours_delta": round(verified_hours - claimed_hours, 2),
                    "note": item.note,
                    "row_attachment_count": _site_log_row_attachment_count(row, "MANPOWER", item.sort_order, item.id),
                }
            )
        return rows

    if section == "equipment":
        for item in sorted(row.equipment_rows or [], key=lambda v: (v.sort_order or 0, v.id or 0)):
            claimed_count = float(item.claimed_count or 0)
            verified_count = float(item.verified_count or 0)
            claimed_hours = float(item.claimed_hours or 0)
            verified_hours = float(item.verified_hours or 0)
            rows.append(
                {
                    **base,
                    "row_id": item.id,
                    "row_sort_order": item.sort_order,
                    "equipment_code": item.equipment_code,
                    "equipment_label": item.equipment_label,
                    "work_location": item.work_location,
                    "claimed_count": round(claimed_count, 2),
                    "verified_count": round(verified_count, 2),
                    "count_delta": round(verified_count - claimed_count, 2),
                    "claimed_status": item.claimed_status,
                    "verified_status": item.verified_status,
                    "claimed_hours": round(claimed_hours, 2),
                    "verified_hours": round(verified_hours, 2),
                    "hours_delta": round(verified_hours - claimed_hours, 2),
                    "note": item.note,
                    "row_attachment_count": _site_log_row_attachment_count(row, "EQUIPMENT", item.sort_order, item.id),
                }
            )
        return rows

    if section == "material":
        for item in sorted(row.material_rows or [], key=lambda v: (v.sort_order or 0, v.id or 0)):
            rows.append(
                {
                    **base,
                    "row_id": item.id,
                    "row_sort_order": item.sort_order,
                    "material_code": item.material_code,
                    "material_title": item.title,
                    "consumption_location": item.consumption_location,
                    "unit": item.unit,
                    "incoming_quantity": round(float(item.incoming_quantity or 0), 2),
                    "consumed_quantity": round(float(item.consumed_quantity or 0), 2),
                    "cumulative_quantity": round(float(item.cumulative_quantity or 0), 2),
                    "note": item.note,
                    "row_attachment_count": _site_log_row_attachment_count(row, "MATERIAL", item.sort_order, item.id),
                }
            )
        return rows

    if section == "activity":
        for item in sorted(row.activity_rows or [], key=lambda v: (v.sort_order or 0, v.id or 0)):
            claimed = float(item.claimed_progress_pct) if item.claimed_progress_pct is not None else None
            verified = float(item.verified_progress_pct) if item.verified_progress_pct is not None else None
            rows.append(
                {
                    **base,
                    "row_id": item.id,
                    "row_sort_order": item.sort_order,
                    "activity_code": item.activity_code,
                    "activity_title": item.activity_title,
                    "pms_step_title": item.pms_step_title,
                    "location": item.location,
                    "unit": item.unit,
                    "today_quantity": round(float(item.today_quantity or 0), 2),
                    "cumulative_quantity": round(float(item.cumulative_quantity or 0), 2),
                    "personnel_count": int(item.personnel_count or 0),
                    "claimed_progress_pct": round(claimed, 2) if claimed is not None else None,
                    "verified_progress_pct": round(verified, 2) if verified is not None else None,
                    "progress_delta_pct": (
                        round((verified or 0.0) - (claimed or 0.0), 2)
                        if claimed is not None or verified is not None
                        else None
                    ),
                    "activity_status": item.activity_status,
                    "stop_reason": item.stop_reason,
                    "note": item.note,
                    "row_attachment_count": _site_log_row_attachment_count(row, "ACTIVITY", item.sort_order, item.id),
                }
            )
        return rows
    return []


def _sort_site_log_report_rows(
    rows: list[dict[str, Any]],
    sort_by: str,
    sort_dir: str,
    report_section: str = "general",
) -> list[dict[str, Any]]:
    allowed = {col["key"] for col in _site_log_report_columns(report_section)} | {
        "log_type",
        "status_code",
        "created_at",
        "updated_at",
        "organization_id",
        "organization_contract_id",
        "row_sort_order",
    }
    key = sort_by if sort_by in allowed else "log_date"
    reverse = _norm(sort_dir).lower() == "desc"

    def value(row: dict[str, Any]) -> Any:
        current = row.get(key)
        if isinstance(current, (int, float)):
            return current
        return str(current or "").lower()

    present = [row for row in rows if row.get(key) is not None]
    missing = [row for row in rows if row.get(key) is None]
    present.sort(key=value, reverse=reverse)
    return present + missing


def _site_log_table_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    claimed_progress = [
        float(row.get("claimed_avg_progress_pct") if row.get("claimed_avg_progress_pct") is not None else row.get("claimed_progress_pct"))
        for row in rows
        if row.get("claimed_avg_progress_pct") is not None or row.get("claimed_progress_pct") is not None
    ]
    verified_progress = [
        float(row.get("verified_avg_progress_pct") if row.get("verified_avg_progress_pct") is not None else row.get("verified_progress_pct"))
        for row in rows
        if row.get("verified_avg_progress_pct") is not None or row.get("verified_progress_pct") is not None
    ]
    for row in rows:
        status = _upper(row.get("status_code"))
        log_type = _upper(row.get("log_type"))
        if status:
            by_status[status] = by_status.get(status, 0) + 1
        if log_type:
            by_type[log_type] = by_type.get(log_type, 0) + 1
    claimed_avg = _avg_number(claimed_progress)
    verified_avg = _avg_number(verified_progress)
    return {
        "total": len(rows),
        "by_status": by_status,
        "by_type": by_type,
        "draft": by_status.get("DRAFT", 0),
        "submitted": by_status.get("SUBMITTED", 0),
        "returned": by_status.get("RETURNED", 0),
        "verified": by_status.get("VERIFIED", 0),
        "claimed_manpower_count": round(sum(float(row.get("claimed_manpower_count") or 0) for row in rows), 2),
        "verified_manpower_count": round(sum(float(row.get("verified_manpower_count") or 0) for row in rows), 2),
        "claimed_manpower_hours": round(sum(float(row.get("claimed_manpower_hours") or 0) for row in rows), 2),
        "verified_manpower_hours": round(sum(float(row.get("verified_manpower_hours") or 0) for row in rows), 2),
        "claimed_equipment_count": round(sum(float(row.get("claimed_equipment_count") or 0) for row in rows), 2),
        "verified_equipment_count": round(sum(float(row.get("verified_equipment_count") or 0) for row in rows), 2),
        "claimed_equipment_hours": round(sum(float(row.get("claimed_equipment_hours") or 0) for row in rows), 2),
        "verified_equipment_hours": round(sum(float(row.get("verified_equipment_hours") or 0) for row in rows), 2),
        "claimed_count": round(sum(float(row.get("claimed_count") or 0) for row in rows), 2),
        "verified_count": round(sum(float(row.get("verified_count") or 0) for row in rows), 2),
        "count_delta": round(sum(float(row.get("count_delta") or 0) for row in rows), 2),
        "claimed_hours": round(sum(float(row.get("claimed_hours") or 0) for row in rows), 2),
        "verified_hours": round(sum(float(row.get("verified_hours") or 0) for row in rows), 2),
        "hours_delta": round(sum(float(row.get("hours_delta") or 0) for row in rows), 2),
        "incoming_quantity": round(sum(float(row.get("incoming_quantity") or 0) for row in rows), 2),
        "consumed_quantity": round(sum(float(row.get("consumed_quantity") or 0) for row in rows), 2),
        "cumulative_quantity": round(sum(float(row.get("cumulative_quantity") or 0) for row in rows), 2),
        "personnel_count": sum(int(row.get("personnel_count") or 0) for row in rows),
        "row_attachment_count": sum(int(row.get("row_attachment_count") or 0) for row in rows),
        "activity_count": sum(int(row.get("activity_count") or 0) for row in rows),
        "issue_count": sum(int(row.get("issue_count") or 0) for row in rows),
        "attachment_count": sum(int(row.get("attachment_count") or 0) for row in rows),
        "qc_open_ncr_count": sum(int(row.get("qc_open_ncr_count") or 0) for row in rows),
        "qc_open_punch_count": sum(int(row.get("qc_open_punch_count") or 0) for row in rows),
        "claimed_avg_progress_pct": claimed_avg,
        "verified_avg_progress_pct": verified_avg,
        "progress_delta_pct": (
            round((verified_avg or 0.0) - (claimed_avg or 0.0), 2)
            if claimed_avg is not None or verified_avg is not None
            else None
        ),
    }


def _site_log_table_payload(
    db: Session,
    user: User | None,
    *,
    bi_access: PowerBiReportAccess | None = None,
    project_code: str | None = None,
    discipline_code: str | None = None,
    log_type: str | None = None,
    status_code: str | None = None,
    organization_id: int | None = None,
    organization_contract_id: int | None = None,
    log_date_from: date | datetime | None = None,
    log_date_to: date | datetime | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "log_date",
    sort_dir: str = "desc",
    report_section: str = "general",
    include_all_rows: bool = False,
) -> dict[str, Any]:
    section = _normalize_report_section(report_section)
    if bi_access and bi_access.allowed_report_sections and section not in bi_access.allowed_report_sections:
        raise HTTPException(status_code=403, detail="Power BI token is not allowed for this report section.")
    labels = _site_log_choice_labels(db)
    rows: list[dict[str, Any]] = []
    for row in _site_log_report_query(
        db,
        user,
        bi_access=bi_access,
        project_code=project_code,
        discipline_code=discipline_code,
        log_type=log_type,
        status_code=status_code,
        organization_id=organization_id,
        organization_contract_id=organization_contract_id,
        log_date_from=log_date_from,
        log_date_to=log_date_to,
        search=search,
    ).all():
        rows.extend(_site_log_report_section_rows(row, section, labels))
    sorted_rows = _sort_site_log_report_rows(rows, sort_by, sort_dir, section)
    total = len(sorted_rows)
    safe_page_size = max(1, int(page_size or 50))
    safe_page = max(1, int(page or 1))
    pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    if include_all_rows:
        page_rows = sorted_rows
    else:
        offset = (safe_page - 1) * safe_page_size
        page_rows = sorted_rows[offset : offset + safe_page_size]
    return {
        "ok": True,
        "report_section": section,
        "report_section_label": SITE_LOG_REPORT_SECTION_LABELS.get(section, section),
        "summary": _site_log_table_summary(sorted_rows),
        "columns": _site_log_report_columns(section),
        "data": page_rows,
        "pagination": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "pages": pages,
            "has_prev": safe_page > 1,
            "has_next": safe_page < pages,
        },
        "sort": {"sort_by": sort_by, "sort_dir": "desc" if _norm(sort_dir).lower() == "desc" else "asc"},
    }


@router.get("/reports/table")
def report_table(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    log_type: Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    organization_id: Optional[int] = Query(default=None, ge=1),
    organization_contract_id: Optional[int] = Query(default=None, ge=1),
    log_date_from: Optional[date] = Query(default=None),
    log_date_to: Optional[date] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=5000),
    sort_by: str = Query(default="log_date"),
    sort_dir: str = Query(default="desc"),
    report_section: str = Query(default="general"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("site_logs:report_read")),
):
    return _site_log_table_payload(
        db,
        user,
        project_code=project_code,
        discipline_code=discipline_code,
        log_type=log_type,
        status_code=status_code,
        organization_id=organization_id,
        organization_contract_id=organization_contract_id,
        log_date_from=log_date_from,
        log_date_to=log_date_to,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        report_section=report_section,
    )


@router.get("/reports/table.csv")
def report_table_csv(
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    log_type: Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    organization_id: Optional[int] = Query(default=None, ge=1),
    organization_contract_id: Optional[int] = Query(default=None, ge=1),
    log_date_from: Optional[date] = Query(default=None),
    log_date_to: Optional[date] = Query(default=None),
    search: Optional[str] = Query(default=None),
    sort_by: str = Query(default="log_date"),
    sort_dir: str = Query(default="desc"),
    report_section: str = Query(default="general"),
    db: Session = Depends(get_db),
    principal: User | PowerBiReportAccess = Depends(_site_log_csv_report_reader),
):
    user = principal if isinstance(principal, User) else None
    bi_access = principal if isinstance(principal, PowerBiReportAccess) else None
    payload = _site_log_table_payload(
        db,
        user,
        bi_access=bi_access,
        project_code=project_code,
        discipline_code=discipline_code,
        log_type=log_type,
        status_code=status_code,
        organization_id=organization_id,
        organization_contract_id=organization_contract_id,
        log_date_from=log_date_from,
        log_date_to=log_date_to,
        search=search,
        page=1,
        page_size=500,
        sort_by=sort_by,
        sort_dir=sort_dir,
        report_section=report_section,
        include_all_rows=True,
    )
    fieldnames = [column["key"] for column in payload["columns"]]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in payload["data"]:
        writer.writerow({key: row.get(key) for key in fieldnames})
    section = str(payload.get("report_section") or "general")
    filename = f"site-log-report-{section}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        BytesIO(buffer.getvalue().encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


@router.get("/{log_id}/pdf")
def download_log_pdf(log_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:read"))):
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    payload = _serialize(row, include_rows=True, catalog_labels=_site_log_choice_labels(db))
    pdf_bytes = _build_site_log_pdf(payload)
    base_name = safe_name(_site_log_pdf_text(payload.get("log_no"), f"site-log-{log_id}")) or f"site-log-{log_id}"
    file_name = f"{base_name}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{file_name}\"; filename*=UTF-8''{quote(file_name)}",
            "Cache-Control": "no-store",
        },
    )


@router.get("/{log_id}")
def get_log(log_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:read"))):
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    return {"ok": True, "data": _serialize(row, include_rows=True, catalog_labels=_site_log_choice_labels(db))}


@router.put("/{log_id}")
def update_log(log_id: int, payload: SiteLogUpdateIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:update"))):
    _require_contractor_flow(user)
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    _enforce_editable_draft(row, user)
    fields = set(payload.model_fields_set or set())
    if "project_code" in fields and payload.project_code is not None:
        _check_project_exists(db, payload.project_code)
        enforce_scope_access(db, user, project_code=_upper(payload.project_code))
        row.project_code = _upper(payload.project_code)
    if "discipline_code" in fields:
        _check_optional_discipline(db, payload.discipline_code)
        row.discipline_code = _upper(payload.discipline_code) or None
    if "organization_id" in fields:
        _check_optional_org(db, payload.organization_id)
        if payload.organization_id:
            enforce_organization_access(db, user, organization_id=payload.organization_id)
        row.organization_id = payload.organization_id
    if "organization_contract_id" in fields:
        if payload.organization_contract_id:
            _check_optional_org_contract(db, payload.organization_contract_id, row.organization_id)
        row.organization_contract_id = payload.organization_contract_id
    if "log_type" in fields and payload.log_type is not None:
        row.log_type = _normalize_log_type(payload.log_type)
    if "log_date" in fields and payload.log_date is not None:
        ldate = _to_day_start(payload.log_date)
        if not ldate:
            raise HTTPException(status_code=400, detail="log_date is invalid")
        row.log_date = ldate
    if "work_status" in fields:
        row.work_status = _normalize_work_status(payload.work_status)
    if "shift" in fields:
        row.shift = _validate_active_choice_code(
            db,
            SiteLogShiftCatalog,
            payload.shift,
            "shift",
            previous_value=row.shift,
            allow_unchanged_legacy=True,
        )
    if "weather" in fields:
        row.weather = _validate_active_choice_code(
            db,
            SiteLogWeatherCatalog,
            payload.weather,
            "weather",
            previous_value=row.weather,
            allow_unchanged_legacy=True,
        )
    if "summary" in fields:
        row.summary = _norm(payload.summary) or None
    if "current_work_summary" in fields:
        row.current_work_summary = _norm(payload.current_work_summary) or None
    if "next_plan_summary" in fields:
        row.next_plan_summary = _norm(payload.next_plan_summary) or None
    if {"summary", "current_work_summary", "next_plan_summary"} & fields:
        legacy_summary = payload.summary if "summary" in fields else None
        row.summary = _compose_summary_text(row.current_work_summary, row.next_plan_summary, legacy_summary)
    manpower = _sanitize_manpower(payload.manpower_rows) if payload.manpower_rows is not None else None
    equipment = _sanitize_equipment(payload.equipment_rows) if payload.equipment_rows is not None else None
    activity = _sanitize_activity(payload.activity_rows) if payload.activity_rows is not None else None
    activity = _apply_activity_pms_snapshots(db, activity)
    material = _sanitize_material(payload.material_rows) if payload.material_rows is not None else None
    issue = _sanitize_issue(payload.issue_rows) if payload.issue_rows is not None else None
    issue = _validate_issue_rows(db, issue, existing_rows=list(row.issue_rows or []))
    attachment_rows = _sanitize_attachment_rows(db, payload.attachment_rows) if payload.attachment_rows is not None else None
    if not _is_admin(user) and _has_verified_payload(manpower or [], equipment or [], activity or []):
        raise HTTPException(status_code=403, detail="Contractor users cannot write verified values.")
    organization_contract_id, contract_number, contract_subject, contract_block = _resolve_contract_snapshot(
        db,
        organization_id=row.organization_id,
        organization_contract_id=row.organization_contract_id,
        contract_number=payload.contract_number if "contract_number" in fields else row.contract_number,
        contract_subject=payload.contract_subject if "contract_subject" in fields else row.contract_subject,
        contract_block=payload.contract_block if "contract_block" in fields else row.contract_block,
    )
    row.organization_contract_id = organization_contract_id
    row.contract_number = contract_number
    row.contract_subject = contract_subject
    row.contract_block = contract_block
    if attachment_rows is not None:
        _ensure_attachment_links_for_log(db, log_id, attachment_rows)
    _replace_rows(row, manpower, equipment, activity, material, issue, attachment_rows)
    if {"project_code", "organization_id", "organization_contract_id", "log_date", "qc_open_punch_count", "qc_summary_note"} & fields:
        _apply_qc_snapshot_to_row(
            row,
            db=db,
            project_code=row.project_code,
            organization_id=row.organization_id,
            log_date=row.log_date,
            qc_open_punch_count=payload.qc_open_punch_count if "qc_open_punch_count" in fields else row.qc_open_punch_count,
            qc_summary_note=payload.qc_summary_note if "qc_summary_note" in fields else row.qc_summary_note,
        )
    elif "qc_summary_note" in fields:
        row.qc_summary_note = _norm(payload.qc_summary_note) or None
    elif "qc_open_punch_count" in fields:
        row.qc_open_punch_count = _to_int(payload.qc_open_punch_count)
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, log_id), include_rows=True, catalog_labels=_site_log_choice_labels(db))}


@router.post("/{log_id}/submit")
def submit_log(log_id: int, payload: SubmitIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:submit"))):
    _require_contractor_flow(user)
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    _enforce_editable_draft(row, user)
    if not row.project_code or not row.log_date:
        raise HTTPException(status_code=400, detail="project_code and log_date are required.")
    if _normalize_work_status(row.work_status) == "ACTIVE" and not _has_rows(row):
        raise HTTPException(status_code=400, detail="برای گزارش فعال، حداقل یک ردیف باید ثبت شود.")
    prev = row.status_code
    row.status_code = "SUBMITTED"
    row.submitted_by_id = getattr(user, "id", None)
    row.submitted_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    _record_status(db, site_log_id=log_id, from_status=prev, to_status="SUBMITTED", user_id=getattr(user, "id", None), note=payload.note)
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, log_id), include_rows=True, catalog_labels=_site_log_choice_labels(db))}


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
    if _normalize_work_status(row.work_status) == "ACTIVE" and not _has_verified_values(row):
        raise HTTPException(status_code=400, detail="At least one verified value is required.")
    prev = row.status_code
    row.status_code = "VERIFIED"
    row.verified_by_id = getattr(user, "id", None)
    row.verified_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    _record_status(db, site_log_id=log_id, from_status=prev, to_status="VERIFIED", user_id=getattr(user, "id", None), note=payload.note)
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, log_id), include_rows=True, catalog_labels=_site_log_choice_labels(db))}


@router.post("/{log_id}/return")
def return_log(log_id: int, payload: ReturnIn, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:verify"))):
    _require_consultant_flow(user)
    note = _norm(payload.note)
    if not note:
        raise HTTPException(status_code=400, detail="یادداشت برگشت الزامی است.")
    row = _load_log_or_404(db, log_id)
    _enforce_log_scope(db, user, row)
    if _upper(row.status_code) != "SUBMITTED":
        raise HTTPException(status_code=409, detail="فقط گزارش ارسال‌شده قابل برگشت است.")
    prev = row.status_code
    row.status_code = "RETURNED"
    row.verified_by_id = None
    row.verified_at = None
    row.updated_at = datetime.utcnow()
    user_id = getattr(user, "id", None)
    db.add(SiteLogComment(site_log_id=log_id, comment_text=note, comment_type="return", created_by_id=user_id, created_at=datetime.utcnow()))
    _record_status(db, site_log_id=log_id, from_status=prev, to_status="RETURNED", user_id=user_id, note=note)
    db.commit()
    return {"ok": True, "data": _serialize(_load_log_or_404(db, log_id), include_rows=True, catalog_labels=_site_log_choice_labels(db))}


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
    storage_manager = StorageManager(db)

    if storage_manager._is_webdav_primary_mode():
        # WebDAV mode: use the explicit Site Log base path when configured,
        # otherwise keep the legacy correspondence-storage fallback.
        integrations = get_storage_integrations(db)
        runtime = resolve_nextcloud_runtime(integrations)
        root_path = str(runtime.get("root_path") or "")

        # Site logs can use an explicit storage root; otherwise they fall back to correspondence storage.
        site_log_base = storage_manager.get_site_log_webdav_base()

        # Build path structure (same as _storage_dir but for WebDAV)
        section = {
            "GENERAL": "General",
            "MANPOWER": "Manpower",
            "EQUIPMENT": "Equipment",
            "ACTIVITY": "Activity",
            "MATERIAL": "Materials",
            "ISSUE": "Issues",
            "REPORT_ATTACHMENT": "ReportAttachments",
        }.get(sec.upper(), "General")
        kind = {"pdf": "PDF", "native": "Native", "attachment": "Attachment"}.get(fk, "Attachment")
        slug = safe_name(row.log_no or f"SLOG-{row.id}")

        # Build complete absolute path
        absolute_path = f"{site_log_base}/site_logs/{slug}/{section}/{kind}/{unique}"

        # Relativize to root
        relative_path = StorageManager.relativize_webdav_path(absolute_path, root_path)

        saved = storage_manager.save_upload_to_webdav(
            file=file,
            remote_relative_path=relative_path,
            file_kind=fk,
        )
        stored_path = saved.stored_path
    else:
        # Mount/local mode: use existing logic
        folder = _storage_dir(db, row, sec, fk)
        saved = storage_manager.save_upload_secure(
            file=file,
            destination_folder=str(folder),
            new_name=unique,
            file_kind=fk,
        )
        stored_path = str(Path(saved.stored_path))
    x = SiteLogAttachment(
        site_log_id=log_id,
        section_code=sec,
        row_id=row_id if row_id and row_id > 0 else None,
        file_name=original,
        stored_path=stored_path,
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
    return _serve_attachment_file(db, row, "attachment")


@router.get("/attachments/{attachment_id}/preview")
def preview_attachment(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("site_logs:read"))):
    row = _load_attachment_or_404(db, attachment_id)
    log = _load_log_or_404(db, row.site_log_id)
    _enforce_log_scope(db, user, log)
    media_type = _attachment_preview_media_type(row)
    if not media_type:
        raise HTTPException(
            status_code=415,
            detail="پیش‌نمایش فقط برای فایل‌های PDF و تصویری پشتیبانی می‌شود. برای این فایل از دانلود استفاده کنید.",
        )
    return _serve_attachment_file(db, row, "inline", media_type)


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
    db.delete(row)
    db.commit()
    _delete_stored_attachment_file(db, str(row.stored_path or ""))
    return {"ok": True}
