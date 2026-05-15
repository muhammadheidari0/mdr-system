from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    User,
    apply_organization_query_filters,
    apply_scope_query_filters,
    enforce_scope_access,
    get_current_user,
    get_db,
    has_permission_for_user,
)
from app.core.config import settings
from app.core.roles import Role
from app.db.models import (
    BimEquipmentItem,
    BimMtoItem,
    BimPublishItem,
    BimPublishRun,
    BimRevitClientState,
    BimRevitSyncItem,
    BimRevitSyncRun,
    BimScheduleRow,
    BimScheduleRun,
    SettingsKV,
    SiteLog,
)
from app.services import archive_service, docnum_service
from app.services.access_control import resolve_effective_access
from app.services.bim_revit_security import (
    build_signature_canonical,
    compute_body_sha256,
    compute_plugin_signature,
    decrypt_plugin_secret,
)
from app.services.storage_policy import get_bim_revit_integration, get_storage_policy


router = APIRouter(prefix="/bim", tags=["BIM"])

ERROR_VALIDATION = "validation_error"
ERROR_PERMISSION = "permission_denied"
ERROR_CONFLICT = "conflict_revision_content"
ERROR_FILE_POLICY = "file_policy_rejected"
ERROR_INTERNAL = "internal_error"
ERROR_SIGNATURE = "signature_invalid"
ERROR_REPLAY = "signature_replay"

PUBLISH_COMPLETED = "completed"
PUBLISH_COMPLETED_WITH_ERRORS = "completed_with_errors"
PUBLISH_FAILED = "failed"

SCHEDULE_PROFILE_MTO = "MTO"
SCHEDULE_PROFILE_EQUIPMENT = "EQUIPMENT"

SCHEDULE_STAGING = "STAGING"
SCHEDULE_VALIDATED = "VALIDATED"
SCHEDULE_APPROVED = "APPROVED"
SCHEDULE_REJECTED = "REJECTED"

SYNC_UPSERT = "upsert"
SYNC_DELETE = "delete"

SYNC_SECTION_MANPOWER = "MANPOWER"
SYNC_SECTION_EQUIPMENT = "EQUIPMENT"
SYNC_SECTION_ACTIVITY = "ACTIVITY"

MAPPING_SETTINGS_KEY = "custom.bim.mapping.v1"
BIM_REPLAY_NONCE_PREFIX = "bimn"
INBOX_RETENTION_DAYS = 30

INBOX_STAGED = "staged"
INBOX_STAGED_WITH_ERRORS = "staged_with_errors"
INBOX_APPROVED = "approved"
INBOX_REJECTED = "rejected"
INBOX_EXPIRED = "expired"


class PublishItemIn(BaseModel):
    item_index: int = 0
    sheet_unique_id: str
    sheet_number: Optional[str] = None
    sheet_name: Optional[str] = None
    doc_number: Optional[str] = None
    requested_revision: str
    status_code: Optional[str] = None
    include_native: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    file_sha256: Optional[str] = None


class PublishBatchJsonIn(BaseModel):
    run_client_id: Optional[str] = None
    project_code: str
    model_guid: Optional[str] = None
    model_title: Optional[str] = None
    revit_version: Optional[str] = None
    plugin_version: Optional[str] = None
    items: list[PublishItemIn] = Field(default_factory=list)
    files_manifest: list[dict[str, Any]] = Field(default_factory=list)


class ScheduleRowIn(BaseModel):
    row_no: Optional[int] = None
    element_key: Optional[str] = None
    equipment_key: Optional[str] = None
    values: dict[str, Any] = Field(default_factory=dict)


class ScheduleIngestIn(BaseModel):
    project_code: str
    profile_code: str
    model_guid: str
    view_name: Optional[str] = None
    schema_version: str
    rows: list[ScheduleRowIn] = Field(default_factory=list)


class SiteLogPullIn(BaseModel):
    project_code: Optional[str] = None
    client_model_guid: str
    log_ids: list[int] = Field(default_factory=list)


class SiteLogAckErrorIn(BaseModel):
    sync_key: str
    message: str


class SiteLogAckIn(BaseModel):
    run_id: str
    applied_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    errors: list[SiteLogAckErrorIn] = Field(default_factory=list)


class ScheduleRejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class PublishRejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class _BimItemError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class _LocalUploadFile:
    def __init__(self, *, file_path: str, file_name: str, content_type: str):
        self.filename = file_name
        self.content_type = content_type
        self.file = open(file_path, "rb")

    def close(self) -> None:
        try:
            self.file.close()
        except Exception:
            pass


def _utcnow() -> datetime:
    return datetime.utcnow()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(value: Any, *, expected: type) -> Any:
    raw = _norm(value)
    if not raw:
        return expected()
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise _BimItemError(ERROR_VALIDATION, "Invalid JSON payload.") from exc
    if not isinstance(parsed, expected):
        raise _BimItemError(ERROR_VALIDATION, "JSON payload has invalid type.")
    return parsed


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _sha256_upload(upload: UploadFile) -> str:
    data = await upload.read()
    digest = hashlib.sha256(data).hexdigest()
    try:
        await upload.seek(0)
    except Exception:
        upload.file.seek(0)
    return digest


def _http_error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message": message,
        },
    )


def _require_feature(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(status_code=404, detail="Not found")


def _require_permission(db: Session, user: User, permission: str) -> None:
    if not has_permission_for_user(db, user, permission):
        raise _http_error(403, ERROR_PERMISSION, f"Missing permission: {permission}")


def _require_schedule_approver(user: User) -> None:
    role = str(resolve_effective_access(user).effective_role or "").strip().lower()
    if role in {Role.ADMIN.value, Role.DCC.value, Role.MANAGER.value}:
        return
    raise _http_error(403, ERROR_PERMISSION, "Only admin/manager/dcc can approve or reject schedule runs.")


def _safe_mapping(db: Session) -> dict[str, Any]:
    row = db.query(SettingsKV).filter(SettingsKV.key == MAPPING_SETTINGS_KEY).first()
    raw = _norm(row.value if row else "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_iso_datetime(raw: Optional[str]) -> datetime | None:
    value = _norm(raw)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        raise _http_error(400, ERROR_VALIDATION, "Invalid datetime format. Use ISO-8601 UTC.")


def _resolve_publish_status(success: int, failed: int, duplicate: int) -> str:
    del duplicate
    if failed <= 0:
        return PUBLISH_COMPLETED
    if success > 0:
        return PUBLISH_COMPLETED_WITH_ERRORS
    return PUBLISH_FAILED


def _profile_or_400(value: str) -> str:
    code = _upper(value)
    if code in {SCHEDULE_PROFILE_MTO, SCHEDULE_PROFILE_EQUIPMENT}:
        return code
    raise _http_error(400, ERROR_VALIDATION, f"Unsupported profile_code: {value}")


def _resolve_manifest_map(rows: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_index: dict[int, dict[str, Any]] = {}
    by_sheet: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        idx = row.get("item_index")
        if isinstance(idx, int):
            by_index[idx] = row
        sheet = _norm(row.get("sheet_unique_id"))
        if sheet:
            by_sheet[sheet] = row
    return by_index, by_sheet


def _upload_map(form_files: list[Any]) -> dict[str, UploadFile]:
    uploads: dict[str, UploadFile] = {}
    for item in form_files:
        filename = _norm(getattr(item, "filename", None))
        if filename:
            uploads[filename] = item
    return uploads


def _manifest_upload_name(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _norm(row.get(key))
        if value:
            return value
    return ""


def _pick_upload(
    uploads: dict[str, UploadFile],
    *,
    preferred_name: str,
    fallback_single: bool,
) -> UploadFile | None:
    name = _norm(preferred_name)
    if name and name in uploads:
        return uploads[name]
    if fallback_single and len(uploads) == 1:
        return next(iter(uploads.values()))
    return None


def _item_metadata_value(metadata: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = _norm(metadata.get(key))
        if value:
            return value
    return default


def _build_publish_meta(
    *,
    db: Session,
    project_code: str,
    item: PublishItemIn,
) -> dict[str, Any]:
    metadata = dict(item.metadata or {})
    subject = _item_metadata_value(
        metadata,
        "subject",
        "subject_p",
        "subject_e",
        default=_norm(item.sheet_name),
    )
    meta = {
        "doc_number": _upper(item.doc_number),
        "project_code": _upper(project_code),
        "mdr_code": _upper(_item_metadata_value(metadata, "mdr_code", "mdrCode", default="X")),
        "phase": _upper(_item_metadata_value(metadata, "phase", "phase_code", default="X")),
        "discipline": _upper(
            _item_metadata_value(metadata, "discipline", "discipline_code", default="XX")
        ),
        "package": _upper(_item_metadata_value(metadata, "package", "package_code", default="00")),
        "block": _upper(_item_metadata_value(metadata, "block", "block_code", default="G")),
        "level": _upper(_item_metadata_value(metadata, "level", "level_code", default="GEN")),
        "subject_e": subject,
        "subject_p": subject,
    }

    if not meta["doc_number"]:
        generated_doc, _ = docnum_service.generate_next_doc_number(
            db=db,
            project_code=meta["project_code"],
            mdr_code=meta["mdr_code"],
            phase_code=meta["phase"],
            discipline_code=meta["discipline"],
            pkg_code=meta["package"],
            block=meta["block"],
            level=meta["level"],
            subject_p=meta["subject_p"] or None,
        )
        meta["doc_number"] = _upper(generated_doc)
    return meta


def _require_inbox_approver(user: User) -> None:
    role = str(resolve_effective_access(user).effective_role or "").strip().lower()
    if role in {Role.ADMIN.value, Role.DCC.value, Role.MANAGER.value}:
        return
    raise _http_error(403, ERROR_PERMISSION, "Only admin/manager/dcc can approve or reject BIM inbox runs.")


def _bim_revit_settings(db: Session) -> dict[str, Any]:
    return get_bim_revit_integration(db)


def _nonce_cache_key(key_id: str, nonce: str) -> str:
    key_part = _norm(key_id).lower()[:12] or "default"
    nonce_hash = _sha256_text(_norm(nonce))[:20]
    return f"{BIM_REPLAY_NONCE_PREFIX}:{key_part}:{nonce_hash}"


def _consume_plugin_nonce(db: Session, *, key_id: str, nonce: str, now_utc: datetime) -> None:
    cache_key = _nonce_cache_key(key_id, nonce)
    exists = db.query(SettingsKV).filter(SettingsKV.key == cache_key).first()
    if exists:
        raise _http_error(403, ERROR_REPLAY, "Signature nonce replay detected.")

    db.add(SettingsKV(key=cache_key, value=_iso(now_utc) or "", updated_at=now_utc))

    expire_before = now_utc - timedelta(minutes=15)
    stale_rows = (
        db.query(SettingsKV)
        .filter(SettingsKV.key.like(f"{BIM_REPLAY_NONCE_PREFIX}:%"), SettingsKV.updated_at < expire_before)
        .all()
    )
    for row in stale_rows:
        db.delete(row)

    db.flush()


async def _verify_plugin_signature_for_inbox(
    request: Request,
    *,
    db: Session,
) -> str:
    cfg = _bim_revit_settings(db)
    if not bool(cfg.get("enabled", False)):
        raise _http_error(403, ERROR_PERMISSION, "BIM/Revit integration is disabled.")

    if not bool(settings.FEATURE_BIM_PLUGIN_HMAC):
        return ""

    if not bool(cfg.get("require_plugin_signature", True)):
        return ""

    key_id = _norm(request.headers.get("X-MDR-Plugin-KeyId"))
    timestamp_raw = _norm(request.headers.get("X-MDR-Plugin-Timestamp"))
    nonce = _norm(request.headers.get("X-MDR-Plugin-Nonce"))
    signature = _norm(request.headers.get("X-MDR-Plugin-Signature")).lower()

    if not key_id or not timestamp_raw or not nonce or not signature:
        raise _http_error(403, ERROR_SIGNATURE, "Missing plugin signature headers.")

    expected_key_id = _norm(cfg.get("plugin_key_id"))
    if not expected_key_id or key_id != expected_key_id:
        raise _http_error(403, ERROR_SIGNATURE, "Plugin key id is invalid.")

    encrypted_secret = _norm(cfg.get("plugin_secret_encrypted"))
    if not encrypted_secret:
        raise _http_error(403, ERROR_SIGNATURE, "Plugin secret is not configured.")

    try:
        ts = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
    except Exception as exc:
        raise _http_error(403, ERROR_SIGNATURE, "Invalid signature timestamp.") from exc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_utc = ts.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    if abs((now_utc - ts_utc).total_seconds()) > 300:
        raise _http_error(403, ERROR_SIGNATURE, "Signature timestamp is outside allowed skew.")

    body = await request.body()
    body_sha256 = compute_body_sha256(body)
    canonical = build_signature_canonical(
        method=request.method,
        path=request.url.path,
        timestamp=timestamp_raw,
        nonce=nonce,
        body_sha256=body_sha256,
    )
    try:
        secret = decrypt_plugin_secret(encrypted_secret, secret_key=_norm(settings.SECRET_KEY))
    except Exception as exc:
        raise _http_error(403, ERROR_SIGNATURE, "Stored plugin secret is invalid.") from exc

    expected_signature = compute_plugin_signature(secret=secret, canonical=canonical).lower()
    if not expected_signature or expected_signature != signature:
        raise _http_error(403, ERROR_SIGNATURE, "Plugin signature mismatch.")

    _consume_plugin_nonce(db, key_id=key_id, nonce=nonce, now_utc=now_utc.replace(tzinfo=None))
    return key_id


def _staging_base_dir() -> Path:
    return Path(settings.BASE_DIR) / "files" / "bim_staging"


def _ensure_staging_dir(run_uid: str) -> Path:
    folder = _staging_base_dir() / _norm(run_uid)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe_file_name(value: str, *, fallback: str) -> str:
    text = _norm(value)
    if not text:
        return fallback
    safe_chars = [c if c.isalnum() or c in {".", "_", "-"} else "_" for c in text]
    normalized = "".join(safe_chars).strip("._")
    return normalized or fallback


async def _save_upload_to_staging(upload: UploadFile, destination: Path) -> tuple[str, str]:
    data = await upload.read()
    digest = hashlib.sha256(data).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    try:
        await upload.seek(0)
    except Exception:
        upload.file.seek(0)
    return str(destination), digest


def _parse_payload_json(value: Any) -> dict[str, Any]:
    raw = _norm(value)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _run_is_expired(run: BimPublishRun) -> bool:
    return bool(run.expires_at and run.expires_at <= _utcnow())


def _run_is_approvable(run: BimPublishRun) -> bool:
    if _upper(run.status) in {_upper(INBOX_APPROVED), _upper(INBOX_REJECTED), _upper(INBOX_EXPIRED)}:
        return False
    if _run_is_expired(run):
        return False
    if int(run.failed_count or 0) > 0:
        return False
    return True


def _sync_inbox_run_expiry(db: Session, run: BimPublishRun) -> None:
    if run and run.ingestion_mode == "inbox" and _run_is_expired(run):
        if _norm(run.status) not in {INBOX_APPROVED, INBOX_REJECTED, INBOX_EXPIRED}:
            run.status = INBOX_EXPIRED
            run.staging_status = INBOX_EXPIRED
            run.finished_at = _utcnow()
            db.flush()


def _expire_stale_inbox_runs(db: Session) -> None:
    now = _utcnow()
    rows = (
        db.query(BimPublishRun)
        .filter(
            BimPublishRun.ingestion_mode == "inbox",
            BimPublishRun.expires_at.isnot(None),
            BimPublishRun.expires_at <= now,
            BimPublishRun.status.notin_([INBOX_APPROVED, INBOX_REJECTED, INBOX_EXPIRED]),
        )
        .all()
    )
    for row in rows:
        row.status = INBOX_EXPIRED
        row.staging_status = INBOX_EXPIRED
        row.finished_at = now
    if rows:
        db.commit()


def _run_validation_summary(run: BimPublishRun) -> dict[str, int]:
    return {
        "requested_count": int(run.requested_count or 0),
        "valid_count": int(run.success_count or 0),
        "invalid_count": int(run.failed_count or 0),
        "duplicate_count": int(run.duplicate_count or 0),
    }


def _inbox_run_dict(run: BimPublishRun) -> dict[str, Any]:
    sender = getattr(run, "created_by", None)
    return {
        "run_id": run.run_uid,
        "project_code": run.project_code,
        "model_guid": run.model_guid,
        "model_title": run.model_title,
        "status": _norm(run.status),
        "validation_summary": _run_validation_summary(run),
        "approvable": _run_is_approvable(run),
        "expires_at": _iso(run.expires_at),
        "created_by_id": run.created_by_id,
        "sender_name": _norm(getattr(sender, "full_name", None)) or None,
        "sender_email": _norm(getattr(sender, "email", None)) or None,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }


def _remove_staging_file(path_value: str) -> None:
    raw = _norm(path_value)
    if not raw:
        return
    try:
        path = Path(raw)
    except Exception:
        return
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except Exception:
        return


def _site_log_has_verified_data(row: SiteLog) -> bool:
    if _upper(row.status_code) != "VERIFIED":
        return False
    manpower_ok = any(
        (item.verified_count is not None or item.verified_hours is not None)
        for item in (row.manpower_rows or [])
    )
    equipment_ok = any(
        (item.verified_count is not None or _norm(item.verified_status) or item.verified_hours is not None)
        for item in (row.equipment_rows or [])
    )
    activity_ok = any(
        (item.verified_progress_pct is not None)
        for item in (row.activity_rows or [])
    )
    return manpower_ok or equipment_ok or activity_ok


def _site_log_hash(row: SiteLog) -> str:
    payload = {
        "log_id": int(row.id or 0),
        "status_code": _upper(row.status_code),
        "manpower": [
            {
                "id": int(item.id or 0),
                "verified_count": item.verified_count,
                "verified_hours": item.verified_hours,
            }
            for item in sorted(row.manpower_rows or [], key=lambda x: int(x.id or 0))
            if item.verified_count is not None or item.verified_hours is not None
        ],
        "equipment": [
            {
                "id": int(item.id or 0),
                "verified_count": item.verified_count,
                "verified_status": _upper(item.verified_status),
                "verified_hours": item.verified_hours,
            }
            for item in sorted(row.equipment_rows or [], key=lambda x: int(x.id or 0))
            if item.verified_count is not None or _norm(item.verified_status) or item.verified_hours is not None
        ],
        "activity": [
            {
                "id": int(item.id or 0),
                "verified_progress_pct": item.verified_progress_pct,
            }
            for item in sorted(row.activity_rows or [], key=lambda x: int(x.id or 0))
            if item.verified_progress_pct is not None
        ],
    }
    return _sha256_text(_json_dumps(payload))


def _sync_key(log_id: int, section: str, row_id: int) -> str:
    return f"site_log:{int(log_id)}:{_upper(section)}:{int(row_id)}"


def _site_log_base_fields(row: SiteLog, section: str, row_id: int, operation: str) -> dict[str, Any]:
    return {
        "MDR_SYNC_KEY": _sync_key(int(row.id or 0), section, row_id),
        "MDR_LOG_ID": int(row.id or 0),
        "MDR_LOG_NO": _norm(row.log_no),
        "MDR_LOG_DATE_UTC": _iso(row.log_date),
        "MDR_SECTION": _upper(section),
        "MDR_ROW_ID": int(row_id),
        "MDR_OPERATION": operation,
    }


def _serialize_sync_row(
    *,
    row: SiteLog,
    section: str,
    row_id: int,
    operation: str,
    row_hash: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sync_key": _sync_key(int(row.id or 0), section, row_id),
        "log_id": int(row.id or 0),
        "log_no": _norm(row.log_no),
        "log_date_utc": _iso(row.log_date),
        "section_code": _upper(section),
        "operation": operation,
        "row_hash": row_hash,
        "fields": fields,
    }


async def _parse_publish_payload(request: Request) -> tuple[PublishBatchJsonIn, dict[str, UploadFile], bool]:
    content_type = str(request.headers.get("content-type") or "").lower()

    if "multipart/form-data" in content_type:
        form = await request.form()
        items_raw = _json_loads(form.get("items_json"), expected=list)
        files_manifest = _json_loads(form.get("files_manifest"), expected=list)

        items: list[PublishItemIn] = []
        for idx, raw in enumerate(items_raw):
            if not isinstance(raw, dict):
                raise _http_error(400, ERROR_VALIDATION, f"Invalid item payload at index {idx}.")
            try:
                item = PublishItemIn.model_validate(raw)
            except ValidationError as exc:
                raise _http_error(400, ERROR_VALIDATION, str(exc)) from exc
            items.append(item)

        payload = PublishBatchJsonIn(
            run_client_id=_norm(form.get("run_client_id")) or None,
            project_code=_upper(form.get("project_code")),
            model_guid=_norm(form.get("model_guid")) or None,
            model_title=_norm(form.get("model_title")) or None,
            revit_version=_norm(form.get("revit_version")) or None,
            plugin_version=_norm(form.get("plugin_version")) or None,
            items=items,
            files_manifest=[x for x in files_manifest if isinstance(x, dict)],
        )
        files = _upload_map(form.getlist("files"))
        return payload, files, True

    try:
        raw_json = await request.json()
    except Exception as exc:
        raise _http_error(400, ERROR_VALIDATION, "Request body must be valid JSON or multipart form-data.") from exc

    try:
        payload = PublishBatchJsonIn.model_validate(raw_json)
    except ValidationError as exc:
        raise _http_error(400, ERROR_VALIDATION, str(exc)) from exc

    return payload, {}, False


@router.post("/edms/inbox/publish-batch")
async def publish_batch_inbox(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_INBOX_GATEWAY))
    _require_permission(db, user, "bim:publish")

    plugin_key_id = await _verify_plugin_signature_for_inbox(request, db=db)

    try:
        payload, uploads, is_multipart = await _parse_publish_payload(request)
    except _BimItemError as exc:
        raise _http_error(400, exc.code, exc.message) from exc

    project_code = _upper(payload.project_code)
    if not project_code:
        raise _http_error(400, ERROR_VALIDATION, "project_code is required.")
    if not payload.items:
        raise _http_error(400, ERROR_VALIDATION, "At least one publish item is required.")

    enforce_scope_access(db, user, project_code=project_code)

    run_uid = uuid.uuid4().hex
    run = BimPublishRun(
        run_uid=run_uid,
        run_client_id=_norm(payload.run_client_id) or None,
        project_code=project_code,
        model_guid=_norm(payload.model_guid) or None,
        model_title=_norm(payload.model_title) or None,
        revit_version=_norm(payload.revit_version) or None,
        plugin_version=_norm(payload.plugin_version) or None,
        ingestion_mode="inbox",
        plugin_key_id=_norm(plugin_key_id) or None,
        status=INBOX_STAGED,
        staging_status=INBOX_STAGED,
        validation_status="running",
        created_by_id=getattr(user, "id", None),
        started_at=_utcnow(),
        expires_at=_utcnow() + timedelta(days=INBOX_RETENTION_DAYS),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    staging_dir = _ensure_staging_dir(run_uid)
    by_index, by_sheet = _resolve_manifest_map(payload.files_manifest)

    success_count = 0
    failed_count = 0
    duplicate_count = 0
    results: list[dict[str, Any]] = []

    for offset, item in enumerate(payload.items):
        item_index = int(item.item_index if item.item_index >= 0 else offset)
        sheet_unique_id = _norm(item.sheet_unique_id)
        requested_revision = _upper(item.requested_revision)
        manifest_row = by_index.get(item_index) or by_sheet.get(sheet_unique_id) or {}

        doc_number = _upper(item.doc_number)
        status_code = _upper(item.status_code) or "IFA"
        include_native = bool(item.include_native)
        state = "failed"
        error_code = ""
        error_message = ""
        applied_revision = requested_revision
        idempotency_hash = ""
        file_sha256 = ""
        pdf_staging_path = ""
        native_staging_path = ""
        validation_errors: list[dict[str, str]] = []

        try:
            if not sheet_unique_id:
                raise _BimItemError(ERROR_VALIDATION, "sheet_unique_id is required.")
            if not requested_revision:
                raise _BimItemError(ERROR_VALIDATION, "requested_revision is required.")

            pdf_name = _manifest_upload_name(manifest_row, "pdf_file_name", "pdf_name", "pdf")
            native_name = _manifest_upload_name(manifest_row, "native_file_name", "native_name", "native")
            fallback_single = is_multipart and len(payload.items) == 1
            pdf_upload = _pick_upload(uploads, preferred_name=pdf_name, fallback_single=fallback_single)
            native_upload = _pick_upload(uploads, preferred_name=native_name, fallback_single=False)

            provided_sha = _norm(item.file_sha256) or _norm(manifest_row.get("pdf_sha256")) or _norm(manifest_row.get("file_sha256"))
            if provided_sha:
                file_sha256 = provided_sha.lower()

            if pdf_upload is not None:
                safe_name = _safe_file_name(getattr(pdf_upload, "filename", "") or "", fallback=f"item_{item_index}.pdf")
                staged_path = staging_dir / f"i{item_index}_pdf_{safe_name}"
                pdf_staging_path, uploaded_sha = await _save_upload_to_staging(pdf_upload, staged_path)
                if file_sha256 and uploaded_sha != file_sha256:
                    raise _BimItemError(ERROR_VALIDATION, "Provided file_sha256 does not match uploaded PDF.")
                file_sha256 = uploaded_sha

            if include_native and native_upload is not None:
                native_safe_name = _safe_file_name(
                    getattr(native_upload, "filename", "") or "",
                    fallback=f"item_{item_index}.native",
                )
                native_staged_path = staging_dir / f"i{item_index}_native_{native_safe_name}"
                native_staging_path, _ = await _save_upload_to_staging(native_upload, native_staged_path)

            if not file_sha256:
                raise _BimItemError(ERROR_VALIDATION, "PDF hash is required. Provide file upload or file_sha256.")

            idempotency_hash = _sha256_text("|".join([project_code, sheet_unique_id, requested_revision, file_sha256]))

            duplicate_row = db.query(BimPublishItem).filter(BimPublishItem.idempotency_hash == idempotency_hash).first()
            if duplicate_row:
                state = "duplicate"
                duplicate_count += 1
                applied_revision = _upper(duplicate_row.applied_revision or requested_revision)
                tracking_hash = _sha256_text(f"{idempotency_hash}|duplicate|{run_uid}|{item_index}")
                db.add(
                    BimPublishItem(
                        run_id=run.id,
                        item_index=item_index,
                        project_code=project_code,
                        sheet_unique_id=sheet_unique_id,
                        sheet_number=_norm(item.sheet_number) or None,
                        sheet_name=_norm(item.sheet_name) or None,
                        doc_number=_upper(duplicate_row.doc_number) or doc_number or None,
                        requested_revision=requested_revision,
                        status_code=status_code,
                        include_native=include_native,
                        idempotency_hash=tracking_hash,
                        file_sha256=file_sha256,
                        state=state,
                        applied_revision=applied_revision,
                        staging_file_path=pdf_staging_path or None,
                        staging_sha256=file_sha256,
                        validation_state="DUPLICATE",
                        payload_json=_json_dumps(
                            {
                                "duplicate_of_hash": idempotency_hash,
                                "metadata": item.metadata,
                                "manifest": manifest_row,
                                "staging_native_file_path": native_staging_path,
                            }
                        ),
                        created_at=_utcnow(),
                        finished_at=_utcnow(),
                    )
                )
                db.commit()
            else:
                conflict_row = (
                    db.query(BimPublishItem)
                    .filter(
                        BimPublishItem.project_code == project_code,
                        BimPublishItem.sheet_unique_id == sheet_unique_id,
                        BimPublishItem.requested_revision == requested_revision,
                        BimPublishItem.idempotency_hash != idempotency_hash,
                    )
                    .first()
                )
                if conflict_row:
                    state = "failed"
                    failed_count += 1
                    error_code = ERROR_CONFLICT
                    error_message = "Same revision received with different content hash."
                    validation_errors.append({"code": error_code, "message": error_message})
                else:
                    state = "validated"
                    success_count += 1

                db.add(
                    BimPublishItem(
                        run_id=run.id,
                        item_index=item_index,
                        project_code=project_code,
                        sheet_unique_id=sheet_unique_id,
                        sheet_number=_norm(item.sheet_number) or None,
                        sheet_name=_norm(item.sheet_name) or None,
                        doc_number=doc_number or None,
                        requested_revision=requested_revision,
                        status_code=status_code,
                        include_native=include_native,
                        idempotency_hash=idempotency_hash,
                        file_sha256=file_sha256,
                        state=state,
                        applied_revision=applied_revision,
                        error_code=error_code or None,
                        error_message=error_message or None,
                        staging_file_path=pdf_staging_path or None,
                        staging_sha256=file_sha256,
                        validation_state="VALID" if state == "validated" else "INVALID",
                        validation_errors_json=_json_dumps(validation_errors) if validation_errors else None,
                        payload_json=_json_dumps(
                            {
                                "metadata": item.metadata,
                                "manifest": manifest_row,
                                "staging_native_file_path": native_staging_path,
                            }
                        ),
                        created_at=_utcnow(),
                        finished_at=_utcnow(),
                    )
                )
                db.commit()

        except _BimItemError as exc:
            db.rollback()
            state = "failed"
            failed_count += 1
            error_code = exc.code
            error_message = exc.message
            validation_errors = [{"code": error_code, "message": error_message}]
            fallback_hash = idempotency_hash if idempotency_hash else _sha256_text(
                f"{project_code}|{sheet_unique_id or item_index}|{requested_revision or 'NA'}|{run_uid}|{offset}"
            )
            if db.query(BimPublishItem).filter(BimPublishItem.idempotency_hash == fallback_hash).first():
                fallback_hash = _sha256_text(f"{fallback_hash}|{run_uid}|{offset}|failed")

            db.add(
                BimPublishItem(
                    run_id=run.id,
                    item_index=item_index,
                    project_code=project_code,
                    sheet_unique_id=sheet_unique_id or f"MISSING-{item_index}",
                    sheet_number=_norm(item.sheet_number) or None,
                    sheet_name=_norm(item.sheet_name) or None,
                    doc_number=doc_number or None,
                    requested_revision=requested_revision or "NA",
                    status_code=status_code,
                    include_native=include_native,
                    idempotency_hash=fallback_hash,
                    file_sha256=file_sha256 or None,
                    state=state,
                    error_code=error_code,
                    error_message=error_message,
                    staging_file_path=pdf_staging_path or None,
                    staging_sha256=file_sha256 or None,
                    validation_state="INVALID",
                    validation_errors_json=_json_dumps(validation_errors),
                    payload_json=_json_dumps(
                        {
                            "metadata": item.metadata,
                            "manifest": manifest_row,
                            "staging_native_file_path": native_staging_path,
                        }
                    ),
                    created_at=_utcnow(),
                    finished_at=_utcnow(),
                )
            )
            db.commit()

        except Exception as exc:
            db.rollback()
            state = "failed"
            failed_count += 1
            error_code = ERROR_INTERNAL
            error_message = str(exc)
            validation_errors = [{"code": error_code, "message": error_message}]
            fallback_hash = _sha256_text(
                f"{project_code}|{sheet_unique_id or item_index}|{requested_revision or 'NA'}|{run_uid}|{offset}|internal"
            )
            db.add(
                BimPublishItem(
                    run_id=run.id,
                    item_index=item_index,
                    project_code=project_code,
                    sheet_unique_id=sheet_unique_id or f"MISSING-{item_index}",
                    sheet_number=_norm(item.sheet_number) or None,
                    sheet_name=_norm(item.sheet_name) or None,
                    doc_number=doc_number or None,
                    requested_revision=requested_revision or "NA",
                    status_code=status_code,
                    include_native=include_native,
                    idempotency_hash=fallback_hash,
                    file_sha256=file_sha256 or None,
                    state=state,
                    error_code=error_code,
                    error_message=error_message,
                    staging_file_path=pdf_staging_path or None,
                    staging_sha256=file_sha256 or None,
                    validation_state="INVALID",
                    validation_errors_json=_json_dumps(validation_errors),
                    payload_json=_json_dumps(
                        {
                            "metadata": item.metadata,
                            "manifest": manifest_row,
                            "staging_native_file_path": native_staging_path,
                        }
                    ),
                    created_at=_utcnow(),
                    finished_at=_utcnow(),
                )
            )
            db.commit()

        results.append(
            {
                "item_index": item_index,
                "sheet_unique_id": sheet_unique_id,
                "state": state,
                "error_code": error_code or None,
                "error_message": error_message or None,
                "staging_file_ref": pdf_staging_path or None,
            }
        )

    run.requested_count = len(payload.items)
    run.success_count = int(success_count)
    run.failed_count = int(failed_count)
    run.duplicate_count = int(duplicate_count)
    run.validation_status = "valid" if failed_count == 0 else "has_errors"
    run.staging_status = INBOX_STAGED
    run.status = INBOX_STAGED if failed_count == 0 else INBOX_STAGED_WITH_ERRORS
    run.finished_at = _utcnow()
    db.commit()

    return {
        "run_id": run.run_uid,
        "status": run.status,
        "validation_summary": _run_validation_summary(run),
        "approvable": _run_is_approvable(run),
        "expires_at": _iso(run.expires_at),
        "items": results,
    }


@router.post("/edms/publish-batch")
async def publish_batch(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_permission(db, user, "bim:publish")

    try:
        payload, uploads, is_multipart = await _parse_publish_payload(request)
    except _BimItemError as exc:
        raise _http_error(400, exc.code, exc.message) from exc
    if not _upper(payload.project_code):
        raise _http_error(400, ERROR_VALIDATION, "project_code is required.")

    enforce_scope_access(db, user, project_code=_upper(payload.project_code))

    if not payload.items:
        raise _http_error(400, ERROR_VALIDATION, "At least one publish item is required.")

    run_uid = uuid.uuid4().hex
    run = BimPublishRun(
        run_uid=run_uid,
        run_client_id=_norm(payload.run_client_id) or None,
        project_code=_upper(payload.project_code),
        model_guid=_norm(payload.model_guid) or None,
        model_title=_norm(payload.model_title) or None,
        revit_version=_norm(payload.revit_version) or None,
        plugin_version=_norm(payload.plugin_version) or None,
        status="running",
        created_by_id=getattr(user, "id", None),
        started_at=_utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    by_index, by_sheet = _resolve_manifest_map(payload.files_manifest)
    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    duplicate_count = 0

    for offset, item in enumerate(payload.items):
        item_index = int(item.item_index if item.item_index >= 0 else offset)
        sheet_unique_id = _norm(item.sheet_unique_id)
        requested_revision = _upper(item.requested_revision)
        manifest_row = by_index.get(item_index) or by_sheet.get(sheet_unique_id) or {}

        doc_number = _upper(item.doc_number)
        status_code = _upper(item.status_code) or "IFA"
        include_native = bool(item.include_native)
        state = "failed"
        error_code = ""
        error_message = ""
        document_id: int | None = None
        pdf_file_id: int | None = None
        native_file_id: int | None = None
        applied_revision = requested_revision
        idempotency_hash = ""
        file_sha256 = ""

        try:
            if not sheet_unique_id:
                raise _BimItemError(ERROR_VALIDATION, "sheet_unique_id is required.")
            if not requested_revision:
                raise _BimItemError(ERROR_VALIDATION, "requested_revision is required.")

            pdf_name = _manifest_upload_name(manifest_row, "pdf_file_name", "pdf_name", "pdf")
            native_name = _manifest_upload_name(
                manifest_row,
                "native_file_name",
                "native_name",
                "native",
            )
            fallback_single = is_multipart and len(payload.items) == 1
            pdf_upload = _pick_upload(uploads, preferred_name=pdf_name, fallback_single=fallback_single)
            native_upload = _pick_upload(uploads, preferred_name=native_name, fallback_single=False)

            provided_sha = _norm(item.file_sha256) or _norm(manifest_row.get("pdf_sha256")) or _norm(
                manifest_row.get("file_sha256")
            )
            if provided_sha:
                file_sha256 = provided_sha.lower()
            elif pdf_upload is not None:
                file_sha256 = await _sha256_upload(pdf_upload)

            if not file_sha256:
                raise _BimItemError(ERROR_VALIDATION, "PDF hash is required. Provide file upload or file_sha256.")

            idempotency_hash = _sha256_text(
                "|".join(
                    [
                        _upper(payload.project_code),
                        sheet_unique_id,
                        requested_revision,
                        file_sha256,
                    ]
                )
            )

            duplicate_row = (
                db.query(BimPublishItem)
                .filter(BimPublishItem.idempotency_hash == idempotency_hash)
                .first()
            )
            if duplicate_row:
                state = "duplicate"
                duplicate_count += 1
                doc_number = _upper(duplicate_row.doc_number)
                document_id = duplicate_row.document_id
                pdf_file_id = duplicate_row.pdf_file_id
                native_file_id = duplicate_row.native_file_id
                applied_revision = _upper(duplicate_row.applied_revision or requested_revision)
                tracking_hash = _sha256_text(
                    f"{idempotency_hash}|duplicate|{run_uid}|{item_index}"
                )
                db.add(
                    BimPublishItem(
                        run_id=run.id,
                        item_index=item_index,
                        project_code=_upper(payload.project_code),
                        sheet_unique_id=sheet_unique_id,
                        sheet_number=_norm(item.sheet_number) or None,
                        sheet_name=_norm(item.sheet_name) or None,
                        doc_number=doc_number or None,
                        requested_revision=requested_revision,
                        status_code=status_code,
                        include_native=include_native,
                        idempotency_hash=tracking_hash,
                        file_sha256=file_sha256,
                        state=state,
                        document_id=document_id,
                        applied_revision=applied_revision,
                        pdf_file_id=pdf_file_id,
                        native_file_id=native_file_id,
                        payload_json=_json_dumps(
                            {
                                "duplicate_of_hash": idempotency_hash,
                                "metadata": item.metadata,
                                "manifest": manifest_row,
                            }
                        ),
                        created_at=_utcnow(),
                        finished_at=_utcnow(),
                    )
                )
                db.commit()
            else:
                conflict_row = (
                    db.query(BimPublishItem)
                    .filter(
                        BimPublishItem.project_code == _upper(payload.project_code),
                        BimPublishItem.sheet_unique_id == sheet_unique_id,
                        BimPublishItem.requested_revision == requested_revision,
                        BimPublishItem.idempotency_hash != idempotency_hash,
                    )
                    .first()
                )
                if conflict_row:
                    state = "failed"
                    failed_count += 1
                    error_code = ERROR_CONFLICT
                    error_message = "Same revision received with different content hash."
                else:
                    meta = _build_publish_meta(db=db, project_code=_upper(payload.project_code), item=item)
                    doc_number = _upper(meta["doc_number"])

                    try:
                        doc, _ = archive_service.register_document_metadata(db=db, meta_data=meta)
                        document_id = int(doc.id or 0) if doc else None
                    except HTTPException as exc:
                        detail = str(exc.detail)
                        if "mime" in detail.lower() or "size" in detail.lower():
                            raise _BimItemError(ERROR_FILE_POLICY, detail) from exc
                        raise _BimItemError(ERROR_VALIDATION, detail) from exc

                    if pdf_upload is not None and document_id:
                        try:
                            await pdf_upload.seek(0)
                        except Exception:
                            pdf_upload.file.seek(0)

                        if include_native and native_upload is not None:
                            try:
                                await native_upload.seek(0)
                            except Exception:
                                native_upload.file.seek(0)
                            pdf_entry, native_entry = archive_service.save_dual_upload_files(
                                db=db,
                                pdf_file=pdf_upload,
                                native_file=native_upload,
                                document_id=document_id,
                                revision_code=requested_revision,
                                status_code=status_code,
                            )
                            pdf_file_id = int(pdf_entry.id or 0)
                            native_file_id = int(native_entry.id or 0)
                        else:
                            pdf_entry = archive_service.save_upload_file(
                                db=db,
                                file=pdf_upload,
                                document_id=document_id,
                                revision_code=requested_revision,
                                status_code=status_code,
                                file_kind="pdf",
                            )
                            pdf_file_id = int(pdf_entry.id or 0)

                    state = "completed"
                    success_count += 1

                db.add(
                    BimPublishItem(
                        run_id=run.id,
                        item_index=item_index,
                        project_code=_upper(payload.project_code),
                        sheet_unique_id=sheet_unique_id,
                        sheet_number=_norm(item.sheet_number) or None,
                        sheet_name=_norm(item.sheet_name) or None,
                        doc_number=doc_number or None,
                        requested_revision=requested_revision,
                        status_code=status_code,
                        include_native=include_native,
                        idempotency_hash=idempotency_hash,
                        file_sha256=file_sha256,
                        state=state,
                        document_id=document_id,
                        applied_revision=applied_revision,
                        pdf_file_id=pdf_file_id,
                        native_file_id=native_file_id,
                        error_code=error_code or None,
                        error_message=error_message or None,
                        payload_json=_json_dumps(
                            {
                                "metadata": item.metadata,
                                "manifest": manifest_row,
                            }
                        ),
                        created_at=_utcnow(),
                        finished_at=_utcnow(),
                    )
                )
                db.commit()

        except _BimItemError as exc:
            db.rollback()
            state = "failed"
            failed_count += 1
            error_code = exc.code
            error_message = exc.message

            fallback_hash = (
                idempotency_hash
                if idempotency_hash
                else _sha256_text(
                    f"{_upper(payload.project_code)}|{sheet_unique_id or item_index}|{requested_revision or 'NA'}|{run_uid}|{offset}"
                )
            )
            if (
                db.query(BimPublishItem)
                .filter(BimPublishItem.idempotency_hash == fallback_hash)
                .first()
            ):
                fallback_hash = _sha256_text(f"{fallback_hash}|{run_uid}|{offset}|failed")

            db.add(
                BimPublishItem(
                    run_id=run.id,
                    item_index=item_index,
                    project_code=_upper(payload.project_code),
                    sheet_unique_id=sheet_unique_id or f"MISSING-{item_index}",
                    sheet_number=_norm(item.sheet_number) or None,
                    sheet_name=_norm(item.sheet_name) or None,
                    doc_number=doc_number or None,
                    requested_revision=requested_revision or "NA",
                    status_code=status_code,
                    include_native=include_native,
                    idempotency_hash=fallback_hash,
                    file_sha256=file_sha256 or None,
                    state=state,
                    error_code=error_code,
                    error_message=error_message,
                    payload_json=_json_dumps(
                        {
                            "metadata": item.metadata,
                            "manifest": manifest_row,
                        }
                    ),
                    created_at=_utcnow(),
                    finished_at=_utcnow(),
                )
            )
            db.commit()

        except Exception as exc:
            db.rollback()
            state = "failed"
            failed_count += 1
            error_code = ERROR_INTERNAL
            error_message = str(exc)
            fallback_hash = _sha256_text(
                f"{_upper(payload.project_code)}|{sheet_unique_id or item_index}|{requested_revision or 'NA'}|{run_uid}|{offset}|internal"
            )
            db.add(
                BimPublishItem(
                    run_id=run.id,
                    item_index=item_index,
                    project_code=_upper(payload.project_code),
                    sheet_unique_id=sheet_unique_id or f"MISSING-{item_index}",
                    sheet_number=_norm(item.sheet_number) or None,
                    sheet_name=_norm(item.sheet_name) or None,
                    doc_number=doc_number or None,
                    requested_revision=requested_revision or "NA",
                    status_code=status_code,
                    include_native=include_native,
                    idempotency_hash=fallback_hash,
                    file_sha256=file_sha256 or None,
                    state=state,
                    error_code=error_code,
                    error_message=error_message,
                    payload_json=_json_dumps(
                        {
                            "metadata": item.metadata,
                            "manifest": manifest_row,
                        }
                    ),
                    created_at=_utcnow(),
                    finished_at=_utcnow(),
                )
            )
            db.commit()

        results.append(
            {
                "item_index": item_index,
                "state": state,
                "document_id": document_id,
                "doc_number": doc_number or None,
                "applied_revision": applied_revision or requested_revision,
                "pdf_file_id": pdf_file_id,
                "native_file_id": native_file_id,
                "error_code": error_code or None,
                "error_message": error_message or None,
            }
        )

    run.requested_count = len(payload.items)
    run.success_count = int(success_count)
    run.failed_count = int(failed_count)
    run.duplicate_count = int(duplicate_count)
    run.status = _resolve_publish_status(success_count, failed_count, duplicate_count)
    run.finished_at = _utcnow()
    db.commit()

    return {
        "run_id": run.run_uid,
        "summary": {
            "requested_count": int(run.requested_count),
            "success_count": int(run.success_count),
            "failed_count": int(run.failed_count),
            "duplicate_count": int(run.duplicate_count),
            "status": run.status,
        },
        "items": results,
    }


@router.get("/edms/runs/{run_id}")
def get_publish_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_permission(db, user, "bim:read")

    run = db.query(BimPublishRun).filter(BimPublishRun.run_uid == _norm(run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Publish run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)

    return {
        "run_id": run.run_uid,
        "project_code": run.project_code,
        "counts": {
            "requested_count": int(run.requested_count or 0),
            "success_count": int(run.success_count or 0),
            "failed_count": int(run.failed_count or 0),
            "duplicate_count": int(run.duplicate_count or 0),
        },
        "status": _norm(run.status),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }


@router.get("/edms/runs/{run_id}/items")
def get_publish_run_items(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_permission(db, user, "bim:read")

    run = db.query(BimPublishRun).filter(BimPublishRun.run_uid == _norm(run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Publish run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)

    rows = (
        db.query(BimPublishItem)
        .filter(BimPublishItem.run_id == run.id)
        .order_by(BimPublishItem.item_index.asc(), BimPublishItem.id.asc())
        .all()
    )
    return {
        "run_id": run.run_uid,
        "items": [
            {
                "item_index": int(item.item_index),
                "sheet_unique_id": item.sheet_unique_id,
                "state": item.state,
                "error_code": item.error_code,
                "error_message": item.error_message,
                "document_id": item.document_id,
                "doc_number": item.doc_number,
                "applied_revision": item.applied_revision,
                "pdf_file_id": item.pdf_file_id,
                "native_file_id": item.native_file_id,
            }
            for item in rows
        ],
    }


@router.get("/edms/inbox/runs")
def list_inbox_runs(
    status: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    created_from: Optional[str] = Query(default=None),
    created_to: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_INBOX_GATEWAY))
    _require_permission(db, user, "bim:read")

    _expire_stale_inbox_runs(db)

    query = (
        db.query(BimPublishRun)
        .options(joinedload(BimPublishRun.created_by))
        .filter(BimPublishRun.ingestion_mode == "inbox")
    )
    query = apply_scope_query_filters(query, db, user, project_column=BimPublishRun.project_code)

    project = _upper(project_code)
    if project:
        enforce_scope_access(db, user, project_code=project)
        query = query.filter(BimPublishRun.project_code == project)

    status_filter = _norm(status).lower()
    if status_filter:
        query = query.filter(BimPublishRun.status == status_filter)

    from_dt = _parse_iso_datetime(created_from)
    to_dt = _parse_iso_datetime(created_to)
    if from_dt is not None:
        query = query.filter(BimPublishRun.started_at >= from_dt)
    if to_dt is not None:
        query = query.filter(BimPublishRun.started_at <= to_dt)

    total = query.count()
    rows = (
        query.order_by(BimPublishRun.started_at.desc(), BimPublishRun.id.desc())
        .offset(int(offset))
        .limit(int(limit))
        .all()
    )
    for row in rows:
        _sync_inbox_run_expiry(db, row)
    db.commit()

    return {
        "total": int(total),
        "count": len(rows),
        "items": [_inbox_run_dict(row) for row in rows],
    }


@router.get("/edms/inbox/runs/{run_id}")
def get_inbox_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_INBOX_GATEWAY))
    _require_permission(db, user, "bim:read")

    run = (
        db.query(BimPublishRun)
        .options(joinedload(BimPublishRun.created_by))
        .filter(BimPublishRun.run_uid == _norm(run_id), BimPublishRun.ingestion_mode == "inbox")
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Inbox run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)
    _sync_inbox_run_expiry(db, run)
    db.commit()
    return _inbox_run_dict(run)


@router.get("/edms/inbox/runs/{run_id}/items")
def get_inbox_run_items(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_INBOX_GATEWAY))
    _require_permission(db, user, "bim:read")

    run = (
        db.query(BimPublishRun)
        .filter(BimPublishRun.run_uid == _norm(run_id), BimPublishRun.ingestion_mode == "inbox")
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Inbox run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)
    _sync_inbox_run_expiry(db, run)

    rows = (
        db.query(BimPublishItem)
        .filter(BimPublishItem.run_id == run.id)
        .order_by(BimPublishItem.item_index.asc(), BimPublishItem.id.asc())
        .all()
    )
    db.commit()
    return {
        "run_id": run.run_uid,
        "status": run.status,
        "items": [
            {
                "item_index": int(item.item_index),
                "sheet_unique_id": item.sheet_unique_id,
                "sheet_number": item.sheet_number,
                "sheet_name": item.sheet_name,
                "state": item.state,
                "validation_state": item.validation_state,
                "error_code": item.error_code,
                "error_message": item.error_message,
                "staging_file_ref": item.staging_file_path,
                "archive_result": {
                    "document_id": item.document_id,
                    "pdf_file_id": item.pdf_file_id,
                    "native_file_id": item.native_file_id,
                    "archive_document_id": item.archive_document_id,
                    "archive_file_id": item.archive_file_id,
                },
            }
            for item in rows
        ],
    }


@router.post("/edms/inbox/runs/{run_id}/approve")
def approve_inbox_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_INBOX_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_INBOX_APPROVAL))
    _require_inbox_approver(user)
    _require_permission(db, user, "bim:approve")

    run = (
        db.query(BimPublishRun)
        .filter(BimPublishRun.run_uid == _norm(run_id), BimPublishRun.ingestion_mode == "inbox")
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Inbox run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)
    _sync_inbox_run_expiry(db, run)
    if run.status == INBOX_EXPIRED:
        db.commit()
        raise _http_error(409, ERROR_VALIDATION, "Run is expired and cannot be approved.")
    if run.status == INBOX_REJECTED:
        raise _http_error(409, ERROR_VALIDATION, "Rejected run cannot be approved.")
    if run.status == INBOX_APPROVED:
        raise _http_error(409, ERROR_VALIDATION, "Run is already approved.")

    rows = (
        db.query(BimPublishItem)
        .filter(BimPublishItem.run_id == run.id)
        .order_by(BimPublishItem.item_index.asc(), BimPublishItem.id.asc())
        .all()
    )
    has_invalid = any(_norm(row.state) == "failed" or _upper(row.validation_state) == "INVALID" for row in rows)
    if has_invalid:
        raise _http_error(409, ERROR_VALIDATION, "apply_aborted_validation: run contains invalid items.")

    archived = 0
    failed = 0
    duplicates = 0
    results: list[dict[str, Any]] = []

    for item in rows:
        state_key = _norm(item.state).lower()
        if state_key == "duplicate":
            duplicates += 1
            results.append(
                {
                    "item_index": int(item.item_index),
                    "state": "duplicate",
                    "document_id": item.document_id,
                    "pdf_file_id": item.pdf_file_id,
                    "native_file_id": item.native_file_id,
                }
            )
            continue

        payload_data = _parse_payload_json(item.payload_json)
        metadata = payload_data.get("metadata") if isinstance(payload_data.get("metadata"), dict) else {}
        native_staging_path = _norm(payload_data.get("staging_native_file_path"))
        source_item = PublishItemIn(
            item_index=int(item.item_index),
            sheet_unique_id=_norm(item.sheet_unique_id),
            sheet_number=_norm(item.sheet_number) or None,
            sheet_name=_norm(item.sheet_name) or None,
            doc_number=_norm(item.doc_number) or None,
            requested_revision=_norm(item.requested_revision),
            status_code=_norm(item.status_code) or None,
            include_native=bool(item.include_native),
            metadata=metadata,
            file_sha256=_norm(item.file_sha256) or None,
        )

        doc_number = _norm(item.doc_number)
        document_id: int | None = None
        pdf_file_id: int | None = None
        native_file_id: int | None = None
        error_code = ""
        error_message = ""

        try:
            meta = _build_publish_meta(db=db, project_code=run.project_code, item=source_item)
            doc_number = _upper(meta.get("doc_number"))
            doc, _ = archive_service.register_document_metadata(db=db, meta_data=meta)
            document_id = int(doc.id or 0) if doc else None

            if _norm(item.staging_file_path):
                pdf_path = _norm(item.staging_file_path)
                if not Path(pdf_path).exists():
                    raise _BimItemError(ERROR_VALIDATION, "staging file is missing.")

                pdf_upload = _LocalUploadFile(
                    file_path=pdf_path,
                    file_name=Path(pdf_path).name,
                    content_type="application/pdf",
                )
                native_upload: _LocalUploadFile | None = None
                try:
                    if bool(item.include_native) and native_staging_path:
                        if not Path(native_staging_path).exists():
                            raise _BimItemError(ERROR_VALIDATION, "native staging file is missing.")
                        native_upload = _LocalUploadFile(
                            file_path=native_staging_path,
                            file_name=Path(native_staging_path).name,
                            content_type="application/octet-stream",
                        )
                        pdf_entry, native_entry = archive_service.save_dual_upload_files(
                            db=db,
                            pdf_file=pdf_upload,
                            native_file=native_upload,
                            document_id=int(document_id or 0),
                            revision_code=_upper(item.requested_revision),
                            status_code=_upper(item.status_code) or "IFA",
                        )
                        pdf_file_id = int(pdf_entry.id or 0)
                        native_file_id = int(native_entry.id or 0)
                    else:
                        pdf_entry = archive_service.save_upload_file(
                            db=db,
                            file=pdf_upload,
                            document_id=int(document_id or 0),
                            revision_code=_upper(item.requested_revision),
                            status_code=_upper(item.status_code) or "IFA",
                            file_kind="pdf",
                        )
                        pdf_file_id = int(pdf_entry.id or 0)
                finally:
                    if native_upload is not None:
                        native_upload.close()
                    pdf_upload.close()

            item.state = "completed"
            item.validation_state = "APPLIED"
            item.error_code = None
            item.error_message = None
            item.doc_number = doc_number or None
            item.document_id = document_id
            item.archive_document_id = document_id
            item.pdf_file_id = pdf_file_id
            item.native_file_id = native_file_id
            item.archive_file_id = pdf_file_id
            item.finished_at = _utcnow()

            _remove_staging_file(item.staging_file_path or "")
            _remove_staging_file(native_staging_path)
            item.staging_file_path = None

            archived += 1
            db.commit()
            results.append(
                {
                    "item_index": int(item.item_index),
                    "state": "completed",
                    "document_id": document_id,
                    "pdf_file_id": pdf_file_id,
                    "native_file_id": native_file_id,
                }
            )
        except _BimItemError as exc:
            db.rollback()
            failed += 1
            error_code = exc.code
            error_message = exc.message
            item.error_code = error_code
            item.error_message = error_message
            item.state = "failed"
            item.validation_state = "APPLY_FAILED"
            item.finished_at = _utcnow()
            db.commit()
            results.append(
                {
                    "item_index": int(item.item_index),
                    "state": "failed",
                    "error_code": error_code,
                    "error_message": error_message,
                }
            )
        except Exception as exc:
            db.rollback()
            failed += 1
            error_code = ERROR_INTERNAL
            error_message = str(exc)
            item.error_code = error_code
            item.error_message = error_message
            item.state = "failed"
            item.validation_state = "APPLY_FAILED"
            item.finished_at = _utcnow()
            db.commit()
            results.append(
                {
                    "item_index": int(item.item_index),
                    "state": "failed",
                    "error_code": error_code,
                    "error_message": error_message,
                }
            )

    run.success_count = int(archived)
    run.failed_count = int(failed)
    run.duplicate_count = int(duplicates)
    run.validation_status = "approved" if failed == 0 else "archive_errors"
    run.staging_status = "archived" if failed == 0 else "archive_partial"
    run.status = INBOX_APPROVED if failed == 0 else INBOX_STAGED_WITH_ERRORS
    run.finished_at = _utcnow()
    if failed == 0:
        run.approved_by_id = getattr(user, "id", None)
        run.approved_at = _utcnow()
        run.rejected_by_id = None
        run.rejected_at = None
        run.reject_reason = None
    db.commit()

    return {
        "run_id": run.run_uid,
        "status": run.status,
        "approved_count": int(archived),
        "failed_count": int(failed),
        "items": results,
    }


@router.post("/edms/inbox/runs/{run_id}/reject")
def reject_inbox_run(
    run_id: str,
    payload: PublishRejectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_INBOX_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_INBOX_APPROVAL))
    _require_inbox_approver(user)
    _require_permission(db, user, "bim:reject")

    run = (
        db.query(BimPublishRun)
        .filter(BimPublishRun.run_uid == _norm(run_id), BimPublishRun.ingestion_mode == "inbox")
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Inbox run not found.")
    enforce_scope_access(db, user, project_code=run.project_code)

    _sync_inbox_run_expiry(db, run)
    if run.status == INBOX_APPROVED:
        raise _http_error(409, ERROR_VALIDATION, "Approved run cannot be rejected.")
    if run.status == INBOX_EXPIRED:
        raise _http_error(409, ERROR_VALIDATION, "Expired run cannot be rejected.")

    run.status = INBOX_REJECTED
    run.staging_status = INBOX_REJECTED
    run.validation_status = "rejected"
    run.rejected_by_id = getattr(user, "id", None)
    run.rejected_at = _utcnow()
    run.reject_reason = _norm(payload.reason)
    run.finished_at = _utcnow()
    db.commit()

    return {
        "run_id": run.run_uid,
        "status": run.status,
        "reason": run.reject_reason,
    }


@router.post("/schedules/ingest")
def ingest_schedule(
    payload: ScheduleIngestIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_permission(db, user, "bim:schedule_ingest")

    project_code = _upper(payload.project_code)
    if not project_code:
        raise _http_error(400, ERROR_VALIDATION, "project_code is required.")
    enforce_scope_access(db, user, project_code=project_code)

    profile_code = _profile_or_400(payload.profile_code)
    schema_version = _norm(payload.schema_version)
    if not schema_version:
        raise _http_error(400, ERROR_VALIDATION, "schema_version is required.")
    if not payload.rows:
        raise _http_error(400, ERROR_VALIDATION, "rows[] is required.")

    run_uid = uuid.uuid4().hex
    run = BimScheduleRun(
        run_uid=run_uid,
        project_code=project_code,
        profile_code=profile_code,
        model_guid=_norm(payload.model_guid),
        view_name=_norm(payload.view_name) or None,
        schema_version=schema_version,
        status=SCHEDULE_STAGING,
        created_by_id=getattr(user, "id", None),
        created_at=_utcnow(),
    )
    db.add(run)
    db.flush()

    row_errors: list[dict[str, Any]] = []
    total = len(payload.rows)
    valid = 0
    invalid = 0

    for offset, row in enumerate(payload.rows):
        row_no = int(row.row_no if row.row_no and row.row_no > 0 else offset + 1)
        values = row.values if isinstance(row.values, dict) else {}

        element_key = _norm(row.element_key)
        equipment_key = _norm(row.equipment_key)
        if not equipment_key:
            equipment_key = _norm(values.get("equipment_key"))
        if not element_key:
            element_key = _norm(values.get("element_key"))

        row_state = "VALID"
        error_code = None
        error_message = None

        if profile_code == SCHEDULE_PROFILE_MTO and not element_key:
            row_state = "INVALID"
            error_code = ERROR_VALIDATION
            error_message = "element_key is required for MTO profile."
        elif profile_code == SCHEDULE_PROFILE_EQUIPMENT and not equipment_key:
            row_state = "INVALID"
            error_code = ERROR_VALIDATION
            error_message = "equipment_key is required for EQUIPMENT profile."

        if row_state == "VALID":
            valid += 1
        else:
            invalid += 1
            row_errors.append(
                {
                    "row_no": row_no,
                    "error_code": error_code,
                    "message": error_message,
                }
            )

        db.add(
            BimScheduleRow(
                run_id=run.id,
                row_no=row_no,
                row_state=row_state,
                error_code=error_code,
                error_message=error_message,
                element_key=element_key or None,
                equipment_key=equipment_key or None,
                values_json=_json_dumps(values),
                created_at=_utcnow(),
            )
        )

    run.total_rows = int(total)
    run.valid_rows = int(valid)
    run.invalid_rows = int(invalid)
    run.status = SCHEDULE_VALIDATED
    db.commit()

    return {
        "run_id": run.run_uid,
        "validation_summary": {
            "total_rows": int(run.total_rows),
            "valid_rows": int(run.valid_rows),
            "invalid_rows": int(run.invalid_rows),
        },
        "row_errors": row_errors,
    }


@router.get("/schedules/runs/{run_id}")
def get_schedule_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_permission(db, user, "bim:read")

    run = db.query(BimScheduleRun).filter(BimScheduleRun.run_uid == _norm(run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Schedule run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)

    return {
        "run_id": run.run_uid,
        "project_code": run.project_code,
        "profile_code": run.profile_code,
        "status": run.status,
        "total_rows": int(run.total_rows or 0),
        "valid_rows": int(run.valid_rows or 0),
        "invalid_rows": int(run.invalid_rows or 0),
        "approved_at": _iso(run.approved_at),
        "rejected_at": _iso(run.rejected_at),
    }


@router.post("/schedules/runs/{run_id}/approve")
def approve_schedule_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_SCHEDULE_APPROVAL))
    _require_permission(db, user, "bim:schedule_approve")
    _require_schedule_approver(user)

    run = db.query(BimScheduleRun).filter(BimScheduleRun.run_uid == _norm(run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Schedule run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)

    if _upper(run.status) != SCHEDULE_VALIDATED:
        raise _http_error(409, ERROR_VALIDATION, "Only VALIDATED runs can be approved.")

    rows = (
        db.query(BimScheduleRow)
        .filter(BimScheduleRow.run_id == run.id, BimScheduleRow.row_state == "VALID")
        .all()
    )
    merged = 0
    for row in rows:
        values: dict[str, Any]
        try:
            values = json.loads(_norm(row.values_json) or "{}")
        except Exception:
            values = {}
        if not isinstance(values, dict):
            values = {}

        if _upper(run.profile_code) == SCHEDULE_PROFILE_MTO:
            key = _norm(row.element_key or values.get("element_key"))
            if not key:
                continue
            existing = (
                db.query(BimMtoItem)
                .filter(
                    BimMtoItem.project_code == run.project_code,
                    BimMtoItem.model_guid == run.model_guid,
                    BimMtoItem.element_key == key,
                )
                .first()
            )
            if existing:
                existing.values_json = _json_dumps(values)
                existing.source_run_id = run.id
                existing.updated_at = _utcnow()
            else:
                db.add(
                    BimMtoItem(
                        project_code=run.project_code,
                        model_guid=run.model_guid,
                        element_key=key,
                        values_json=_json_dumps(values),
                        source_run_id=run.id,
                        created_at=_utcnow(),
                        updated_at=_utcnow(),
                    )
                )
            merged += 1
        else:
            key = _norm(row.equipment_key or values.get("equipment_key") or row.element_key)
            if not key:
                continue
            existing = (
                db.query(BimEquipmentItem)
                .filter(
                    BimEquipmentItem.project_code == run.project_code,
                    BimEquipmentItem.model_guid == run.model_guid,
                    BimEquipmentItem.equipment_key == key,
                )
                .first()
            )
            if existing:
                existing.values_json = _json_dumps(values)
                existing.source_run_id = run.id
                existing.updated_at = _utcnow()
            else:
                db.add(
                    BimEquipmentItem(
                        project_code=run.project_code,
                        model_guid=run.model_guid,
                        equipment_key=key,
                        values_json=_json_dumps(values),
                        source_run_id=run.id,
                        created_at=_utcnow(),
                        updated_at=_utcnow(),
                    )
                )
            merged += 1

    run.status = SCHEDULE_APPROVED
    run.approved_by_id = getattr(user, "id", None)
    run.approved_at = _utcnow()
    db.commit()

    return {
        "run_id": run.run_uid,
        "merged_rows": int(merged),
        "status": run.status,
    }


@router.post("/schedules/runs/{run_id}/reject")
def reject_schedule_run(
    run_id: str,
    payload: ScheduleRejectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_SCHEDULE_APPROVAL))
    _require_permission(db, user, "bim:schedule_reject")
    _require_schedule_approver(user)

    run = db.query(BimScheduleRun).filter(BimScheduleRun.run_uid == _norm(run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Schedule run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)

    if _upper(run.status) != SCHEDULE_VALIDATED:
        raise _http_error(409, ERROR_VALIDATION, "Only VALIDATED runs can be rejected.")

    run.status = SCHEDULE_REJECTED
    run.rejected_by_id = getattr(user, "id", None)
    run.rejected_at = _utcnow()
    run.rejected_reason = _norm(payload.reason)
    db.commit()

    return {
        "run_id": run.run_uid,
        "status": run.status,
    }


@router.get("/config")
def get_bim_config(
    project_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_permission(db, user, "bim:read")

    project = _upper(project_code)
    if project:
        enforce_scope_access(db, user, project_code=project)

    mapping = _safe_mapping(db)
    storage_policy = get_storage_policy(db)
    return {
        "mapping": mapping,
        "limits": {
            "mime": storage_policy.get("allowed_mimes_by_kind", {}),
            "max_size_mb": storage_policy.get("max_size_mb", {}),
            "publish_batch_limit": 100,
            "schedule_rows_limit": 20000,
            "writeback_rows_limit": 5000,
        },
    }


@router.get("/site-logs/revit/manifest")
def get_site_log_manifest(
    project_code: str = Query(...),
    client_model_guid: str = Query(...),
    updated_after: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_REVIT_WRITEBACK_SITELOGS))
    _require_permission(db, user, "bim:site_logs_sync")

    project = _upper(project_code)
    if not project:
        raise _http_error(400, ERROR_VALIDATION, "project_code is required.")
    model_guid = _norm(client_model_guid)
    if not model_guid:
        raise _http_error(400, ERROR_VALIDATION, "client_model_guid is required.")

    enforce_scope_access(db, user, project_code=project)

    state = (
        db.query(BimRevitClientState)
        .filter(
            BimRevitClientState.project_code == project,
            BimRevitClientState.client_model_guid == model_guid,
            BimRevitClientState.user_id == int(getattr(user, "id", 0) or 0),
        )
        .first()
    )

    since = _parse_iso_datetime(updated_after)
    if since is None and state and _norm(state.last_cursor):
        since = _parse_iso_datetime(state.last_cursor)

    query = (
        db.query(SiteLog)
        .options(
            joinedload(SiteLog.manpower_rows),
            joinedload(SiteLog.equipment_rows),
            joinedload(SiteLog.activity_rows),
        )
        .filter(SiteLog.project_code == project)
    )
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=SiteLog.project_code,
        discipline_column=SiteLog.discipline_code,
    )
    query = apply_organization_query_filters(query, db, user, organization_column=SiteLog.organization_id)
    if since is not None:
        query = query.filter(SiteLog.updated_at > since)

    rows = query.order_by(SiteLog.updated_at.asc(), SiteLog.id.asc()).limit(limit).all()

    prev_log_ids = {
        int(log_id)
        for (log_id,) in (
            db.query(BimRevitSyncItem.source_log_id)
            .join(BimRevitSyncRun, BimRevitSyncRun.id == BimRevitSyncItem.run_id)
            .filter(
                BimRevitSyncRun.project_code == project,
                BimRevitSyncRun.client_model_guid == model_guid,
            )
            .distinct()
            .all()
        )
    }

    changes: list[dict[str, Any]] = []
    cursor_dt: datetime | None = since
    for row in rows:
        current_cursor = row.updated_at or row.verified_at or row.created_at
        if current_cursor and (cursor_dt is None or current_cursor > cursor_dt):
            cursor_dt = current_cursor

        has_verified = _site_log_has_verified_data(row)
        if has_verified:
            changes.append(
                {
                    "log_id": int(row.id),
                    "log_no": row.log_no,
                    "verified_at": _iso(row.verified_at),
                    "log_hash": _site_log_hash(row),
                    "operation": SYNC_UPSERT,
                }
            )
            continue

        if int(row.id) in prev_log_ids:
            changes.append(
                {
                    "log_id": int(row.id),
                    "log_no": row.log_no,
                    "verified_at": _iso(row.updated_at),
                    "log_hash": "",
                    "operation": SYNC_DELETE,
                }
            )

    run_uid = uuid.uuid4().hex
    sync_run = BimRevitSyncRun(
        run_uid=run_uid,
        project_code=project,
        client_model_guid=model_guid,
        status="manifested",
        requested_by_id=getattr(user, "id", None),
        requested_at=_utcnow(),
    )
    db.add(sync_run)

    if state is None:
        state = BimRevitClientState(
            project_code=project,
            client_model_guid=model_guid,
            user_id=int(getattr(user, "id", 0) or 0),
        )
        db.add(state)

    next_cursor = _iso(cursor_dt)
    if next_cursor:
        state.last_cursor = next_cursor
    state.last_manifest_at = _utcnow()
    state.updated_at = _utcnow()

    db.commit()

    return {
        "run_id": run_uid,
        "changes": changes,
        "next_cursor": next_cursor,
    }


@router.post("/site-logs/revit/pull")
def pull_site_log_rows(
    payload: SiteLogPullIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_REVIT_WRITEBACK_SITELOGS))
    _require_permission(db, user, "bim:site_logs_sync")

    model_guid = _norm(payload.client_model_guid)
    if not model_guid:
        raise _http_error(400, ERROR_VALIDATION, "client_model_guid is required.")

    requested_ids = sorted({int(v) for v in payload.log_ids if int(v) > 0})
    if not requested_ids:
        raise _http_error(400, ERROR_VALIDATION, "log_ids[] is required.")

    project = _upper(payload.project_code)
    if not project:
        first_row = db.query(SiteLog.project_code).filter(SiteLog.id == requested_ids[0]).first()
        project = _upper(first_row[0] if first_row else "")
    if not project:
        raise _http_error(400, ERROR_VALIDATION, "project_code is required.")

    enforce_scope_access(db, user, project_code=project)

    query = (
        db.query(SiteLog)
        .options(
            joinedload(SiteLog.manpower_rows),
            joinedload(SiteLog.equipment_rows),
            joinedload(SiteLog.activity_rows),
        )
        .filter(SiteLog.project_code == project, SiteLog.id.in_(requested_ids))
    )
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=SiteLog.project_code,
        discipline_column=SiteLog.discipline_code,
    )
    query = apply_organization_query_filters(query, db, user, organization_column=SiteLog.organization_id)
    logs = query.all()
    by_id = {int(row.id): row for row in logs}

    run_uid = uuid.uuid4().hex
    run = BimRevitSyncRun(
        run_uid=run_uid,
        project_code=project,
        client_model_guid=model_guid,
        status="pulled",
        requested_by_id=getattr(user, "id", None),
        requested_at=_utcnow(),
    )
    db.add(run)
    db.flush()

    manpower_rows: list[dict[str, Any]] = []
    equipment_rows: list[dict[str, Any]] = []
    activity_rows: list[dict[str, Any]] = []

    historical_items = (
        db.query(BimRevitSyncItem)
        .join(BimRevitSyncRun, BimRevitSyncRun.id == BimRevitSyncItem.run_id)
        .filter(
            BimRevitSyncRun.project_code == project,
            BimRevitSyncRun.client_model_guid == model_guid,
            BimRevitSyncItem.source_log_id.in_(requested_ids),
        )
        .order_by(BimRevitSyncItem.id.desc())
        .all()
    )
    historical_by_log: dict[int, dict[str, BimRevitSyncItem]] = {}
    for item in historical_items:
        historical_by_log.setdefault(int(item.source_log_id), {})
        historical_by_log[int(item.source_log_id)].setdefault(_norm(item.sync_key), item)

    for log_id in requested_ids:
        row = by_id.get(log_id)
        if not row:
            continue

        if _site_log_has_verified_data(row):
            for child in sorted(row.manpower_rows or [], key=lambda x: int(x.id or 0)):
                if child.verified_count is None and child.verified_hours is None:
                    continue
                fields = _site_log_base_fields(
                    row=row,
                    section=SYNC_SECTION_MANPOWER,
                    row_id=int(child.id or 0),
                    operation=SYNC_UPSERT,
                )
                fields.update(
                    {
                        "MDR_ROLE_CODE": child.role_code,
                        "MDR_ROLE_LABEL": child.role_label,
                        "MDR_VERIFIED_COUNT": child.verified_count,
                        "MDR_VERIFIED_HOURS": child.verified_hours,
                        "MDR_NOTE": child.note,
                    }
                )
                row_hash = _sha256_text(_json_dumps(fields))
                serialized = _serialize_sync_row(
                    row=row,
                    section=SYNC_SECTION_MANPOWER,
                    row_id=int(child.id or 0),
                    operation=SYNC_UPSERT,
                    row_hash=row_hash,
                    fields=fields,
                )
                manpower_rows.append(serialized)
                db.add(
                    BimRevitSyncItem(
                        run_id=run.id,
                        sync_key=serialized["sync_key"],
                        source_log_id=int(row.id or 0),
                        section_code=SYNC_SECTION_MANPOWER,
                        row_id=int(child.id or 0),
                        operation=SYNC_UPSERT,
                        row_hash=row_hash,
                        state="pending",
                        payload_json=_json_dumps(serialized["fields"]),
                        created_at=_utcnow(),
                    )
                )

            for child in sorted(row.equipment_rows or [], key=lambda x: int(x.id or 0)):
                if child.verified_count is None and not _norm(child.verified_status) and child.verified_hours is None:
                    continue
                fields = _site_log_base_fields(
                    row=row,
                    section=SYNC_SECTION_EQUIPMENT,
                    row_id=int(child.id or 0),
                    operation=SYNC_UPSERT,
                )
                fields.update(
                    {
                        "MDR_EQUIPMENT_CODE": child.equipment_code,
                        "MDR_EQUIPMENT_LABEL": child.equipment_label,
                        "MDR_VERIFIED_COUNT": child.verified_count,
                        "MDR_VERIFIED_STATUS": child.verified_status,
                        "MDR_VERIFIED_HOURS": child.verified_hours,
                        "MDR_NOTE": child.note,
                    }
                )
                row_hash = _sha256_text(_json_dumps(fields))
                serialized = _serialize_sync_row(
                    row=row,
                    section=SYNC_SECTION_EQUIPMENT,
                    row_id=int(child.id or 0),
                    operation=SYNC_UPSERT,
                    row_hash=row_hash,
                    fields=fields,
                )
                equipment_rows.append(serialized)
                db.add(
                    BimRevitSyncItem(
                        run_id=run.id,
                        sync_key=serialized["sync_key"],
                        source_log_id=int(row.id or 0),
                        section_code=SYNC_SECTION_EQUIPMENT,
                        row_id=int(child.id or 0),
                        operation=SYNC_UPSERT,
                        row_hash=row_hash,
                        state="pending",
                        payload_json=_json_dumps(serialized["fields"]),
                        created_at=_utcnow(),
                    )
                )

            for child in sorted(row.activity_rows or [], key=lambda x: int(x.id or 0)):
                if child.verified_progress_pct is None:
                    continue
                fields = _site_log_base_fields(
                    row=row,
                    section=SYNC_SECTION_ACTIVITY,
                    row_id=int(child.id or 0),
                    operation=SYNC_UPSERT,
                )
                fields.update(
                    {
                        "MDR_ACTIVITY_CODE": child.activity_code,
                        "MDR_ACTIVITY_TITLE": child.activity_title,
                        "MDR_EXTERNAL_REF": child.external_ref,
                        "MDR_VERIFIED_PROGRESS_PCT": child.verified_progress_pct,
                        "MDR_NOTE": child.note,
                    }
                )
                row_hash = _sha256_text(_json_dumps(fields))
                serialized = _serialize_sync_row(
                    row=row,
                    section=SYNC_SECTION_ACTIVITY,
                    row_id=int(child.id or 0),
                    operation=SYNC_UPSERT,
                    row_hash=row_hash,
                    fields=fields,
                )
                activity_rows.append(serialized)
                db.add(
                    BimRevitSyncItem(
                        run_id=run.id,
                        sync_key=serialized["sync_key"],
                        source_log_id=int(row.id or 0),
                        section_code=SYNC_SECTION_ACTIVITY,
                        row_id=int(child.id or 0),
                        operation=SYNC_UPSERT,
                        row_hash=row_hash,
                        state="pending",
                        payload_json=_json_dumps(serialized["fields"]),
                        created_at=_utcnow(),
                    )
                )
            continue

        for sync_item in historical_by_log.get(log_id, {}).values():
            section = _upper(sync_item.section_code)
            fields = {
                "MDR_SYNC_KEY": sync_item.sync_key,
                "MDR_OPERATION": SYNC_DELETE,
            }
            row_hash = _sha256_text(_json_dumps(fields))
            serialized = {
                "sync_key": sync_item.sync_key,
                "log_id": int(log_id),
                "log_no": _norm(row.log_no),
                "log_date_utc": _iso(row.log_date),
                "section_code": section,
                "operation": SYNC_DELETE,
                "row_hash": row_hash,
                "fields": fields,
            }
            if section == SYNC_SECTION_MANPOWER:
                manpower_rows.append(serialized)
            elif section == SYNC_SECTION_EQUIPMENT:
                equipment_rows.append(serialized)
            else:
                activity_rows.append(serialized)

            db.add(
                BimRevitSyncItem(
                    run_id=run.id,
                    sync_key=_norm(sync_item.sync_key),
                    source_log_id=int(log_id),
                    section_code=section,
                    row_id=int(sync_item.row_id or 0),
                    operation=SYNC_DELETE,
                    row_hash=row_hash,
                    state="pending",
                    payload_json=_json_dumps(fields),
                    created_at=_utcnow(),
                )
            )

    db.commit()

    return {
        "run_id": run.run_uid,
        "manpower_rows": manpower_rows,
        "equipment_rows": equipment_rows,
        "activity_rows": activity_rows,
    }


@router.post("/site-logs/revit/ack")
def ack_site_log_sync(
    payload: SiteLogAckIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_feature(bool(settings.FEATURE_BIM_GATEWAY))
    _require_feature(bool(settings.FEATURE_BIM_REVIT_WRITEBACK_SITELOGS))
    _require_permission(db, user, "bim:site_logs_sync")

    run = db.query(BimRevitSyncRun).filter(BimRevitSyncRun.run_uid == _norm(payload.run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Sync run not found.")

    enforce_scope_access(db, user, project_code=run.project_code)

    errors_by_key = {_norm(item.sync_key): _norm(item.message) for item in payload.errors if _norm(item.sync_key)}
    items = db.query(BimRevitSyncItem).filter(BimRevitSyncItem.run_id == run.id).all()

    for item in items:
        key = _norm(item.sync_key)
        if key in errors_by_key:
            item.state = "failed"
            item.error_code = "apply_error"
            item.error_message = errors_by_key[key]
        else:
            item.state = "applied"
            item.error_code = None
            item.error_message = None
        item.applied_at = _utcnow()

    run.applied_count = int(payload.applied_count)
    run.failed_count = int(payload.failed_count)
    run.status = "completed" if int(payload.failed_count) == 0 else "completed_with_errors"
    run.errors_json = _json_dumps(
        [{"sync_key": key, "message": msg} for key, msg in errors_by_key.items()]
    )
    run.finished_at = _utcnow()

    state = (
        db.query(BimRevitClientState)
        .filter(
            BimRevitClientState.project_code == run.project_code,
            BimRevitClientState.client_model_guid == run.client_model_guid,
            BimRevitClientState.user_id == int(getattr(user, "id", 0) or 0),
        )
        .first()
    )
    if state is None:
        state = BimRevitClientState(
            project_code=run.project_code,
            client_model_guid=run.client_model_guid,
            user_id=int(getattr(user, "id", 0) or 0),
        )
        db.add(state)
    state.last_pull_at = _utcnow()
    state.updated_at = _utcnow()

    db.commit()

    return {
        "ok": True,
        "received_at": _iso(_utcnow()),
    }
