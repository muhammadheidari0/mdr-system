from __future__ import annotations

import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    User,
    allow_admin,
    allow_editor,
    allow_viewer,
    apply_scope_query_filters,
    enforce_scope_access,
    get_db,
)
from app.db.models import (
    ArchiveFile,
    Correspondence,
    CorrespondenceAttachment,
    DocumentRevision,
    LocalSyncManifest,
    MdrDocument,
    OpenProjectImportRow,
    OpenProjectImportRun,
    OpenProjectLink,
    SiteCacheAgentToken,
    SiteCacheProfile,
)
from app.core.config import settings
from app.services.openproject_status import (
    ENTITY_ARCHIVE_FILE,
    ENTITY_CORRESPONDENCE_ATTACHMENT,
    default_openproject_sync_status,
    get_openproject_status_map,
    is_openproject_integration_enabled,
    is_valid_entity_type,
    normalize_entity_type,
)
from app.services.storage_sync import (
    JOB_GOOGLE_DRIVE_MIRROR,
    JOB_OPENPROJECT_SYNC,
    resolve_openproject_runtime,
    run_storage_jobs,
)
from app.services.openproject_adapter import OpenProjectAdapter
from app.services.openproject_import import (
    build_work_package_create_payload,
    parse_summary_json,
    parse_task_table_from_bytes,
)
from app.services.storage_policy import get_storage_integrations
from app.services.site_cache import (
    build_site_manifest,
    detect_matching_profile_by_cidr,
    extract_client_ip,
    normalize_site_code,
    resolve_site_profile_by_token,
    serialize_profile,
    site_manifest_policy_scope,
    site_scope_value,
)

router = APIRouter(prefix="/storage", tags=["Storage"])


def _scope_value(user: User, policy_scope: Optional[str]) -> str:
    raw = str(policy_scope or "").strip()
    if raw:
        return raw
    user_id = int(getattr(user, "id", 0) or 0)
    return f"user:{user_id}" if user_id > 0 else "global"


def _manifest_scope_for_entity(entity_type: str, scope: str) -> str:
    normalized_entity = normalize_entity_type(entity_type)
    raw_scope = str(scope or "").strip()
    return f"{normalized_entity}:{raw_scope}"


def _manifest_scope_candidates(entity_type: str, scope: str) -> list[str]:
    normalized_entity = normalize_entity_type(entity_type)
    raw_scope = str(scope or "").strip()
    scopes = [_manifest_scope_for_entity(normalized_entity, raw_scope)]
    # Backward compatibility for rows that were saved before entity_type was encoded.
    if normalized_entity == ENTITY_ARCHIVE_FILE:
        scopes.append(raw_scope)
    return scopes


def _parse_manifest_scope(value: str | None) -> tuple[str, str]:
    raw = str(value or "").strip()
    for entity_type in (ENTITY_ARCHIVE_FILE, ENTITY_CORRESPONDENCE_ATTACHMENT):
        prefix = f"{entity_type}:"
        if raw.startswith(prefix):
            return entity_type, raw[len(prefix) :]
    return ENTITY_ARCHIVE_FILE, raw


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


def _extract_site_token(request: Request) -> str:
    auth_header = str(request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        value = auth_header.split(" ", 1)[1].strip()
        if value:
            return value
    return str(request.headers.get("x-site-token") or "").strip()


def _authenticate_site_agent(
    db: Session,
    *,
    request: Request,
    site_code: str,
) -> tuple[SiteCacheProfile, SiteCacheAgentToken]:
    token_value = _extract_site_token(request)
    if not token_value:
        raise HTTPException(status_code=401, detail="Missing site token")
    profile, token_row = resolve_site_profile_by_token(
        db,
        site_code=site_code,
        token_value=token_value,
    )
    if not profile or not token_row:
        raise HTTPException(status_code=401, detail="Invalid site token or site_code")
    token_row.last_used_at = datetime.utcnow()
    db.flush()
    return profile, token_row


def _upsert_manifest(
    db: Session,
    *,
    file_id: int,
    entity_type: str,
    scope: str,
    version_hash: str,
    is_pinned: bool,
) -> LocalSyncManifest:
    scopes = _manifest_scope_candidates(entity_type, scope)
    row = (
        db.query(LocalSyncManifest)
        .filter(LocalSyncManifest.file_id == int(file_id))
        .filter(LocalSyncManifest.policy_scope.in_(scopes))
        .first()
    )
    manifest_scope = _manifest_scope_for_entity(entity_type, scope)
    if not row:
        row = LocalSyncManifest(
            file_id=int(file_id),
            policy_scope=manifest_scope,
            version_hash=version_hash,
            is_pinned=bool(is_pinned),
        )
        db.add(row)
        db.flush()
        return row
    row.policy_scope = manifest_scope
    row.version_hash = version_hash
    row.is_pinned = bool(is_pinned)
    row.last_modified_at = datetime.utcnow()
    db.flush()
    return row


def _resolve_archive_for_pin(db: Session, file_id: int) -> ArchiveFile | None:
    return (
        db.query(ArchiveFile)
        .options(joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.document))
        .filter(ArchiveFile.id == int(file_id))
        .first()
    )


def _resolve_attachment_for_pin(db: Session, file_id: int) -> CorrespondenceAttachment | None:
    return (
        db.query(CorrespondenceAttachment)
        .options(joinedload(CorrespondenceAttachment.correspondence))
        .filter(CorrespondenceAttachment.id == int(file_id))
        .first()
    )


def _enforce_archive_scope(db: Session, user: User, row: ArchiveFile) -> None:
    revision = row.document_revision
    document = revision.document if revision else None
    if not document:
        return
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )


def _enforce_attachment_scope(db: Session, user: User, row: CorrespondenceAttachment) -> None:
    corr = row.correspondence
    if not corr:
        return
    enforce_scope_access(
        db,
        user,
        project_code=corr.project_code,
        discipline_code=corr.discipline_code,
    )


class LocalCachePinIn(BaseModel):
    file_id: int = Field(..., ge=1)
    policy_scope: Optional[str] = Field(default=None, max_length=64)
    entity_type: Optional[str] = Field(default=ENTITY_ARCHIVE_FILE, max_length=64)


class LocalCacheUnpinIn(BaseModel):
    file_id: int = Field(..., ge=1)
    policy_scope: Optional[str] = Field(default=None, max_length=64)
    entity_type: Optional[str] = Field(default=ENTITY_ARCHIVE_FILE, max_length=64)


class OpenProjectStatusItemIn(BaseModel):
    entity_type: str = Field(default=ENTITY_ARCHIVE_FILE, max_length=64)
    entity_id: int = Field(..., ge=1)


class OpenProjectStatusIn(BaseModel):
    items: list[OpenProjectStatusItemIn] = Field(default_factory=list, max_length=500)


class SiteAgentHeartbeatIn(BaseModel):
    site_code: str = Field(..., min_length=2, max_length=64)
    hostname: Optional[str] = Field(default=None, max_length=255)
    app_version: Optional[str] = Field(default=None, max_length=64)
    summary: dict = Field(default_factory=dict)


class OpenProjectImportExecuteIn(BaseModel):
    target_parent_work_package_id: Optional[int] = Field(default=None, ge=1)


def _safe_json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse_json_object(value: str | None) -> dict[str, Any]:
    raw = str(value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _serialize_openproject_import_run(run: OpenProjectImportRun) -> dict[str, Any]:
    summary = parse_summary_json(run.summary_json)
    started_by = run.started_by.full_name if run.started_by else None
    if not started_by and run.started_by:
        started_by = run.started_by.email
    return {
        "id": int(run.id),
        "run_no": str(run.run_no or ""),
        "status_code": str(run.status_code or ""),
        "source_file_name": run.source_file_name,
        "source_sha256": run.source_sha256,
        "target_parent_work_package_id": run.target_parent_work_package_id,
        "started_by_id": run.started_by_id,
        "started_by_name": started_by,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_rows": int(run.total_rows or 0),
        "valid_rows": int(run.valid_rows or 0),
        "invalid_rows": int(run.invalid_rows or 0),
        "created_rows": int(run.created_rows or 0),
        "failed_rows": int(run.failed_rows or 0),
        "summary": summary,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _serialize_openproject_import_row(row: OpenProjectImportRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "run_id": int(row.run_id),
        "row_no": int(row.row_no or 0),
        "task_name": row.task_name,
        "duration_raw": row.duration_raw,
        "start_raw": row.start_raw,
        "finish_raw": row.finish_raw,
        "predecessors_raw": row.predecessors_raw,
        "resource_names_raw": row.resource_names_raw,
        "normalized_start_date": row.normalized_start_date,
        "normalized_finish_date": row.normalized_finish_date,
        "validation_status": str(row.validation_status or ""),
        "execution_status": str(row.execution_status or ""),
        "created_work_package_id": row.created_work_package_id,
        "openproject_href": row.openproject_href,
        "error_message": row.error_message,
        "payload": _parse_json_object(row.payload_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _load_openproject_import_run_or_404(db: Session, run_id: int) -> OpenProjectImportRun:
    row = (
        db.query(OpenProjectImportRun)
        .options(joinedload(OpenProjectImportRun.started_by))
        .filter(OpenProjectImportRun.id == int(run_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Import run not found")
    return row


def _extract_href(value: dict[str, Any], key: str) -> str:
    links = value.get("_links") if isinstance(value, dict) else None
    if not isinstance(links, dict):
        return ""
    node = links.get(key)
    if not isinstance(node, dict):
        return ""
    return str(node.get("href") or "").strip()


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


@router.post("/openproject/ping")
def ping_openproject(
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    del user
    integrations = get_storage_integrations(db)
    runtime = resolve_openproject_runtime(integrations)
    token_source = str(runtime.get("token_source") or "none")
    base_url = OpenProjectAdapter.normalize_base_url(str(runtime.get("base_url") or ""))
    if not base_url:
        return {
            "ok": True,
            "reachable": False,
            "auth_ok": False,
            "status_code": None,
            "token_source": token_source,
            "message": "OpenProject base URL is not configured.",
        }

    url = f"{base_url}/api/v3"
    auth = ("apikey", str(runtime.get("api_token") or "")) if str(runtime.get("api_token") or "").strip() else None
    try:
        response = requests.get(
            url,
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=(
                float(runtime.get("connect_timeout") or 5),
                float(runtime.get("read_timeout") or 10),
            ),
            verify=bool(runtime.get("tls_verify")),
        )
        status_code = int(response.status_code)
        reachable = True
        auth_ok = status_code < 400
        if status_code in {401, 403}:
            auth_ok = False
            message = "OpenProject API is reachable, but authentication failed."
        elif status_code == 404:
            auth_ok = False
            message = "OpenProject API path not found (check base URL/reverse proxy path)."
        elif status_code >= 400:
            auth_ok = False
            message = f"OpenProject returned HTTP {status_code}."
        else:
            message = "OpenProject API reachable and authenticated."
        return {
            "ok": True,
            "reachable": reachable,
            "auth_ok": auth_ok,
            "status_code": status_code,
            "token_source": token_source,
            "message": message,
        }
    except requests.Timeout:
        return {
            "ok": True,
            "reachable": False,
            "auth_ok": False,
            "status_code": None,
            "token_source": token_source,
            "message": "OpenProject ping timed out.",
        }
    except requests.RequestException:
        return {
            "ok": True,
            "reachable": False,
            "auth_ok": False,
            "status_code": None,
            "token_source": token_source,
            "message": "OpenProject is unreachable (network/TLS error).",
        }


@router.get("/openproject/import/template")
def download_openproject_import_template(
    user: User = Depends(allow_admin),
):
    del user
    template_path = Path(settings.BASE_DIR) / "data_sources" / "openproject template.xlsx"
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="OpenProject template file not found")
    return FileResponse(
        path=str(template_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="openproject template.xlsx",
    )


@router.post("/openproject/import/validate")
def validate_openproject_import_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    file_name = str(file.filename or "").strip() or "openproject_import.xlsx"
    if not file_name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    content = file.file.read()
    try:
        parsed = parse_task_table_from_bytes(content, source_file_name=file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = dict(parsed.get("summary") or {})
    now = datetime.utcnow()
    run = OpenProjectImportRun(
        run_no="OPENPROJECT-IMPORT-PENDING",
        status_code="VALIDATED",
        source_file_name=file_name,
        source_sha256=str(parsed.get("source_sha256") or ""),
        started_by_id=int(getattr(user, "id", 0) or 0) or None,
        started_at=now,
        total_rows=int(summary.get("total_rows") or 0),
        valid_rows=int(summary.get("valid_rows") or 0),
        invalid_rows=int(summary.get("invalid_rows") or 0),
        created_rows=0,
        failed_rows=0,
        summary_json=_safe_json_dumps(summary),
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()
    run.run_no = f"OPI-{datetime.utcnow():%Y%m%d}-{int(run.id):06d}"

    for row in parsed.get("rows") or []:
        db.add(
            OpenProjectImportRow(
                run_id=int(run.id),
                row_no=int(row.get("row_no") or 0),
                task_name=row.get("task_name"),
                duration_raw=row.get("duration_raw"),
                start_raw=row.get("start_raw"),
                finish_raw=row.get("finish_raw"),
                predecessors_raw=row.get("predecessors_raw"),
                resource_names_raw=row.get("resource_names_raw"),
                normalized_start_date=row.get("normalized_start_date"),
                normalized_finish_date=row.get("normalized_finish_date"),
                validation_status=str(row.get("validation_status") or "INVALID"),
                execution_status=str(row.get("execution_status") or "PENDING"),
                error_message=row.get("error_message"),
                payload_json=row.get("payload_json"),
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()
    return {
        "ok": True,
        "run": _serialize_openproject_import_run(run),
        "summary": parse_summary_json(run.summary_json),
    }


@router.post("/openproject/import/runs/{run_id}/execute")
def execute_openproject_import_run(
    run_id: int,
    payload: OpenProjectImportExecuteIn = Body(default={}),
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    del user
    run = _load_openproject_import_run_or_404(db, run_id)
    status_code = str(run.status_code or "").upper()
    if status_code == "COMPLETED":
        raise HTTPException(status_code=409, detail="Import run is already completed")
    if status_code == "RUNNING":
        raise HTTPException(status_code=409, detail="Import run is already running")
    if status_code not in {"VALIDATED", "FAILED"}:
        raise HTTPException(status_code=409, detail=f"Import run status `{status_code}` is not executable")

    integrations = get_storage_integrations(db)
    runtime = resolve_openproject_runtime(integrations)
    if not bool(runtime.get("enabled")):
        raise HTTPException(status_code=400, detail="OpenProject integration is disabled")

    runtime_wp = runtime.get("default_work_package_id")
    target_parent_id = (
        int(payload.target_parent_work_package_id)
        if payload and payload.target_parent_work_package_id
        else int(runtime_wp or 0)
    )
    if target_parent_id <= 0:
        raise HTTPException(status_code=400, detail="default_work_package_id is required before execute")

    base_url = str(runtime.get("base_url") or "").strip()
    token = str(runtime.get("api_token") or "").strip()
    if not base_url or not token:
        raise HTTPException(status_code=400, detail="OpenProject base URL and API token are required")

    adapter = OpenProjectAdapter(
        base_url=base_url,
        api_token=token,
        connect_timeout=float(runtime.get("connect_timeout") or 5),
        read_timeout=float(runtime.get("read_timeout") or 10),
        tls_verify=bool(runtime.get("tls_verify")),
    )

    try:
        parent_wp = adapter.get_work_package(target_parent_id)
    except RuntimeError as exc:
        message = str(exc)
        status = 400 if "HTTP 404" in message else 502
        raise HTTPException(status_code=status, detail=message) from exc

    project_href = _extract_href(parent_wp, "project")
    type_href = _extract_href(parent_wp, "type")
    if not project_href or not type_href:
        raise HTTPException(status_code=502, detail="Failed to resolve project/type from parent work package")

    now = datetime.utcnow()
    run.status_code = "RUNNING"
    run.target_parent_work_package_id = int(target_parent_id)
    run.created_rows = 0
    run.failed_rows = 0
    run.finished_at = None
    run.error_message = None
    run.updated_at = now
    db.commit()

    rows = (
        db.query(OpenProjectImportRow)
        .filter(OpenProjectImportRow.run_id == int(run.id))
        .order_by(OpenProjectImportRow.row_no.asc(), OpenProjectImportRow.id.asc())
        .all()
    )
    total_created = 0
    total_failed = 0

    for row in rows:
        if str(row.validation_status or "").upper() != "VALID":
            row.execution_status = "SKIPPED"
            row.updated_at = datetime.utcnow()
            db.commit()
            continue

        row.execution_status = "PENDING"
        row.error_message = None
        row.created_work_package_id = None
        row.openproject_href = None
        row.updated_at = datetime.utcnow()
        db.commit()

        create_payload = build_work_package_create_payload(
            row_task_name=str(row.task_name or f"Imported Task {int(row.row_no)}"),
            row_start_date=row.normalized_start_date,
            row_finish_date=row.normalized_finish_date,
            row_no=int(row.row_no or 0),
            run_no=str(run.run_no or ""),
            parent_work_package_id=target_parent_id,
            project_href=project_href,
            type_href=type_href,
        )
        try:
            created = adapter.create_work_package(create_payload)
            created_id_raw = created.get("id")
            created_id = int(created_id_raw) if str(created_id_raw or "").isdigit() else None
            row.execution_status = "CREATED"
            row.created_work_package_id = created_id
            row.openproject_href = _extract_href(created, "self") or (
                f"/api/v3/work_packages/{created_id}" if created_id else None
            )
            row.error_message = None
            total_created += 1
        except Exception as exc:
            row.execution_status = "FAILED"
            row.error_message = str(exc)[:4000]
            row.created_work_package_id = None
            row.openproject_href = None
            total_failed += 1

        row.updated_at = datetime.utcnow()
        run.created_rows = int(total_created)
        run.failed_rows = int(total_failed)
        run.updated_at = datetime.utcnow()
        db.commit()

    run = _load_openproject_import_run_or_404(db, int(run.id))
    summary = parse_summary_json(run.summary_json)
    summary["created_rows"] = int(total_created)
    summary["failed_rows"] = int(total_failed)
    summary["target_parent_work_package_id"] = int(target_parent_id)
    summary["executed_at"] = datetime.utcnow().isoformat()

    run.status_code = "COMPLETED"
    run.created_rows = int(total_created)
    run.failed_rows = int(total_failed)
    run.finished_at = datetime.utcnow()
    run.summary_json = _safe_json_dumps(summary)
    run.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "run": _serialize_openproject_import_run(run)}


@router.get("/openproject/import/runs")
def list_openproject_import_runs(
    status_code: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    del user
    query = db.query(OpenProjectImportRun).options(joinedload(OpenProjectImportRun.started_by))
    normalized_status = str(status_code or "").strip().upper()
    if normalized_status:
        query = query.filter(OpenProjectImportRun.status_code == normalized_status)
    rows = query.order_by(OpenProjectImportRun.created_at.desc(), OpenProjectImportRun.id.desc()).limit(limit).all()
    return {"ok": True, "runs": [_serialize_openproject_import_run(row) for row in rows]}


@router.get("/openproject/import/runs/{run_id}")
def get_openproject_import_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    del user
    row = _load_openproject_import_run_or_404(db, run_id)
    return {"ok": True, "run": _serialize_openproject_import_run(row)}


@router.get("/openproject/import/runs/{run_id}/rows")
def list_openproject_import_rows(
    run_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    del user
    _load_openproject_import_run_or_404(db, run_id)
    rows = (
        db.query(OpenProjectImportRow)
        .filter(OpenProjectImportRow.run_id == int(run_id))
        .order_by(OpenProjectImportRow.row_no.asc(), OpenProjectImportRow.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    total = (
        db.query(OpenProjectImportRow)
        .filter(OpenProjectImportRow.run_id == int(run_id))
        .count()
    )
    return {
        "ok": True,
        "rows": [_serialize_openproject_import_row(row) for row in rows],
        "total": int(total),
        "skip": int(skip),
        "limit": int(limit),
    }


@router.get("/openproject/activity")
def list_openproject_activity(
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(allow_admin),
):
    del user
    activity: list[dict[str, Any]] = []

    import_rows = (
        db.query(OpenProjectImportRow, OpenProjectImportRun)
        .join(OpenProjectImportRun, OpenProjectImportRun.id == OpenProjectImportRow.run_id)
        .filter(OpenProjectImportRow.execution_status.in_(["CREATED", "FAILED"]))
        .order_by(OpenProjectImportRow.updated_at.desc(), OpenProjectImportRow.id.desc())
        .limit(limit)
        .all()
    )
    for row, run in import_rows:
        event_at = row.updated_at or row.created_at or run.updated_at or run.created_at
        activity.append(
            {
                "source": "import",
                "kind": "work_package_created"
                if str(row.execution_status or "").upper() == "CREATED"
                else "work_package_failed",
                "event_at": event_at.isoformat() if event_at else None,
                "run_id": int(run.id),
                "run_no": run.run_no,
                "row_no": int(row.row_no or 0),
                "task_name": row.task_name,
                "created_work_package_id": row.created_work_package_id,
                "error_message": row.error_message,
            }
        )

    sync_rows = (
        db.query(OpenProjectLink)
        .order_by(OpenProjectLink.last_synced_at.desc(), OpenProjectLink.updated_at.desc())
        .limit(limit)
        .all()
    )
    for row in sync_rows:
        event_at = row.last_synced_at or row.updated_at or row.created_at
        activity.append(
            {
                "source": "sync",
                "kind": "external_link_sync",
                "event_at": event_at.isoformat() if event_at else None,
                "entity_type": row.entity_type,
                "entity_id": int(row.entity_id or 0),
                "work_package_id": int(row.work_package_id or 0),
                "sync_status": row.sync_status,
                "openproject_attachment_id": row.openproject_attachment_id,
            }
        )

    activity.sort(key=lambda item: str(item.get("event_at") or ""), reverse=True)
    return {"ok": True, "items": activity[: int(limit)]}


@router.post("/openproject/status")
def get_openproject_sync_status(
    payload: OpenProjectStatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    requested: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for item in payload.items:
        entity_type = normalize_entity_type(item.entity_type, default="")
        entity_id = int(item.entity_id or 0)
        if entity_type not in {ENTITY_ARCHIVE_FILE, ENTITY_CORRESPONDENCE_ATTACHMENT} or entity_id <= 0:
            continue
        key = (entity_type, entity_id)
        if key in seen:
            continue
        seen.add(key)
        requested.append(key)

    if not requested:
        return {"ok": True, "items": []}

    archive_ids = [entity_id for entity_type, entity_id in requested if entity_type == ENTITY_ARCHIVE_FILE]
    attachment_ids = [
        entity_id
        for entity_type, entity_id in requested
        if entity_type == ENTITY_CORRESPONDENCE_ATTACHMENT
    ]

    allowed_archive_ids: set[int] = set()
    if archive_ids:
        archive_query = (
            db.query(ArchiveFile.id.label("entity_id"))
            .join(DocumentRevision, ArchiveFile.revision_id == DocumentRevision.id)
            .join(MdrDocument, DocumentRevision.document_id == MdrDocument.id)
            .filter(ArchiveFile.id.in_(archive_ids))
        )
        archive_query = apply_scope_query_filters(
            archive_query,
            db,
            user,
            project_column=MdrDocument.project_code,
            discipline_column=MdrDocument.discipline_code,
        )
        allowed_archive_ids = {int(row.entity_id) for row in archive_query.all()}

    allowed_attachment_ids: set[int] = set()
    if attachment_ids:
        attachment_query = (
            db.query(CorrespondenceAttachment.id.label("entity_id"))
            .join(Correspondence, CorrespondenceAttachment.correspondence_id == Correspondence.id)
            .filter(CorrespondenceAttachment.id.in_(attachment_ids))
        )
        attachment_query = apply_scope_query_filters(
            attachment_query,
            db,
            user,
            project_column=Correspondence.project_code,
            discipline_column=Correspondence.discipline_code,
        )
        allowed_attachment_ids = {int(row.entity_id) for row in attachment_query.all()}

    allowed_items: list[tuple[str, int]] = []
    for entity_type, entity_id in requested:
        if entity_type == ENTITY_ARCHIVE_FILE and entity_id in allowed_archive_ids:
            allowed_items.append((entity_type, entity_id))
        elif entity_type == ENTITY_CORRESPONDENCE_ATTACHMENT and entity_id in allowed_attachment_ids:
            allowed_items.append((entity_type, entity_id))

    integration_enabled = is_openproject_integration_enabled(db)
    fallback_status = default_openproject_sync_status(integration_enabled=integration_enabled)
    status_map = get_openproject_status_map(
        db,
        allowed_items,
        integration_enabled=integration_enabled,
    )

    response_items: list[dict] = []
    for entity_type, entity_id in allowed_items:
        row = status_map.get((entity_type, entity_id), {})
        response_items.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "sync_status": str(row.get("sync_status") or fallback_status),
                "work_package_id": row.get("work_package_id"),
                "openproject_attachment_id": row.get("openproject_attachment_id"),
                "last_synced_at": row.get("last_synced_at"),
            }
        )
    return {"ok": True, "items": response_items}


@router.get("/site-manifest")
def get_site_manifest(
    request: Request,
    site_code: str = Query(..., min_length=2, max_length=64),
    limit: int = Query(default=5000, ge=1, le=20000),
    db: Session = Depends(get_db),
):
    normalized_site_code = normalize_site_code(site_code)
    if not normalized_site_code:
        raise HTTPException(status_code=400, detail="Invalid site_code")
    profile, token_row = _authenticate_site_agent(
        db,
        request=request,
        site_code=normalized_site_code,
    )
    items = build_site_manifest(db, profile=profile, limit=limit)
    db.commit()
    return {
        "ok": True,
        "site_code": profile.code,
        "scope": site_scope_value(profile.code),
        "profile_id": profile.id,
        "token_id": token_row.id,
        "items": items,
    }


@router.get("/site-agent/download/{file_id}")
def site_agent_download_file(
    file_id: int,
    request: Request,
    site_code: str = Query(..., min_length=2, max_length=64),
    db: Session = Depends(get_db),
):
    normalized_site_code = normalize_site_code(site_code)
    if not normalized_site_code:
        raise HTTPException(status_code=400, detail="Invalid site_code")
    profile, _ = _authenticate_site_agent(
        db,
        request=request,
        site_code=normalized_site_code,
    )

    scope = site_manifest_policy_scope(profile.code)
    pinned_row = (
        db.query(LocalSyncManifest)
        .filter(
            LocalSyncManifest.file_id == int(file_id),
            LocalSyncManifest.policy_scope == scope,
            LocalSyncManifest.is_pinned.is_(True),
        )
        .first()
    )
    if not pinned_row:
        raise HTTPException(status_code=404, detail="File is not pinned for this site")

    archive = (
        db.query(ArchiveFile)
        .filter(ArchiveFile.id == int(file_id), ArchiveFile.deleted_at.is_(None))
        .first()
    )
    if not archive or not os.path.exists(str(archive.stored_path or "")):
        raise HTTPException(status_code=404, detail="File not found")

    db.commit()
    return FileResponse(
        path=archive.stored_path,
        filename=archive.original_name,
        media_type=archive.mime_type,
    )


@router.post("/site-agent/heartbeat")
def post_site_agent_heartbeat(
    payload: SiteAgentHeartbeatIn,
    request: Request,
    db: Session = Depends(get_db),
):
    normalized_site_code = normalize_site_code(payload.site_code)
    if not normalized_site_code:
        raise HTTPException(status_code=400, detail="Invalid site_code")
    profile, token_row = _authenticate_site_agent(
        db,
        request=request,
        site_code=normalized_site_code,
    )
    profile.last_heartbeat_at = datetime.utcnow()
    profile.last_heartbeat_info = json.dumps(
        {
            "site_code": profile.code,
            "hostname": str(payload.hostname or "").strip() or None,
            "app_version": str(payload.app_version or "").strip() or None,
            "summary": payload.summary if isinstance(payload.summary, dict) else {},
            "token_id": token_row.id,
            "received_at": profile.last_heartbeat_at.isoformat(),
        },
        ensure_ascii=False,
    )
    db.commit()
    return {
        "ok": True,
        "site_code": profile.code,
        "last_heartbeat_at": profile.last_heartbeat_at.isoformat() if profile.last_heartbeat_at else None,
    }


@router.get("/site-context")
def get_site_context(
    request: Request,
    project_code: Optional[str] = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    normalized_project = str(project_code or "").strip().upper()
    if normalized_project:
        enforce_scope_access(db, user, project_code=normalized_project)

    fallback_ip = request.client.host if request.client else ""
    client_ip = extract_client_ip(dict(request.headers), fallback_ip=fallback_ip)
    profile, matched_cidr = detect_matching_profile_by_cidr(
        db,
        client_ip=client_ip,
        project_code=normalized_project or None,
    )

    if not profile:
        return {
            "ok": True,
            "client_ip": client_ip or None,
            "site_active": False,
            "profile": None,
            "matched_cidr": None,
        }

    if profile.project_code:
        enforce_scope_access(db, user, project_code=profile.project_code)

    profile_payload = serialize_profile(profile)
    profile_payload.pop("rules", None)
    profile_payload.pop("cidrs", None)
    profile_payload.pop("last_heartbeat_info", None)
    return {
        "ok": True,
        "client_ip": client_ip or None,
        "site_active": True,
        "site_scope": site_scope_value(profile.code),
        "matched_cidr": matched_cidr,
        "profile": profile_payload,
    }


@router.post("/local-cache/pin")
def pin_local_cache_file(
    payload: LocalCachePinIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    if not is_valid_entity_type(payload.entity_type):
        raise HTTPException(status_code=400, detail="Unsupported entity_type")
    scope = _scope_value(user, payload.policy_scope)
    entity_type = normalize_entity_type(payload.entity_type)

    file_id = int(payload.file_id)
    file_name = ""
    version_hash = ""
    mirror_status = None

    if entity_type == ENTITY_ARCHIVE_FILE:
        archive = _resolve_archive_for_pin(db, file_id)
        if not archive:
            raise HTTPException(status_code=404, detail="File not found")
        _enforce_archive_scope(db, user, archive)
        file_name = str(archive.original_name or "")
        mirror_status = archive.mirror_status
        version_hash = str(archive.sha256 or "").strip() or _sha256_for_path(archive.stored_path)
    elif entity_type == ENTITY_CORRESPONDENCE_ATTACHMENT:
        attachment = _resolve_attachment_for_pin(db, file_id)
        if not attachment:
            raise HTTPException(status_code=404, detail="Attachment not found")
        _enforce_attachment_scope(db, user, attachment)
        file_name = str(attachment.file_name or "")
        mirror_status = attachment.mirror_status
        version_hash = str(attachment.sha256 or "").strip() or _sha256_for_path(attachment.stored_path)
    else:
        raise HTTPException(status_code=400, detail="Unsupported entity_type")

    if not version_hash:
        raise HTTPException(status_code=400, detail="File hash is not available for pin operation.")

    row = _upsert_manifest(
        db,
        file_id=file_id,
        entity_type=entity_type,
        scope=scope,
        version_hash=version_hash,
        is_pinned=True,
    )
    db.commit()

    manifest_entity, manifest_scope = _parse_manifest_scope(row.policy_scope)
    return {
        "ok": True,
        "data": {
            "id": row.id,
            "entity_type": manifest_entity,
            "file_id": row.file_id,
            "file_name": file_name or None,
            "version_hash": row.version_hash,
            "is_pinned": bool(row.is_pinned),
            "policy_scope": manifest_scope,
            "mirror_status": mirror_status,
            "last_modified_at": row.last_modified_at.isoformat() if row.last_modified_at else None,
        },
    }


@router.post("/local-cache/unpin")
def unpin_local_cache_file(
    payload: LocalCacheUnpinIn,
    db: Session = Depends(get_db),
    user: User = Depends(allow_editor),
):
    if not is_valid_entity_type(payload.entity_type):
        raise HTTPException(status_code=400, detail="Unsupported entity_type")
    scope = _scope_value(user, payload.policy_scope)
    entity_type = normalize_entity_type(payload.entity_type)
    scopes = _manifest_scope_candidates(entity_type, scope)
    row = (
        db.query(LocalSyncManifest)
        .filter(LocalSyncManifest.file_id == int(payload.file_id))
        .filter(LocalSyncManifest.policy_scope.in_(scopes))
        .first()
    )
    if not row:
        return {"ok": True, "message": "Already unpinned"}
    row.is_pinned = False
    row.policy_scope = _manifest_scope_for_entity(entity_type, scope)
    db.commit()
    return {"ok": True}


@router.get("/local-cache/manifest")
def get_local_cache_manifest(
    policy_scope: Optional[str] = Query(default=None),
    only_pinned: bool = Query(default=True),
    entity_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(allow_viewer),
):
    scope = _scope_value(user, policy_scope)
    if entity_type is not None and not is_valid_entity_type(entity_type):
        raise HTTPException(status_code=400, detail="Unsupported entity_type")
    normalized_entity = normalize_entity_type(entity_type, default="") if entity_type is not None else ""

    query = db.query(LocalSyncManifest)
    if normalized_entity:
        query = query.filter(
            LocalSyncManifest.policy_scope.in_(_manifest_scope_candidates(normalized_entity, scope))
        )
    else:
        all_scopes = [scope]
        all_scopes.extend(_manifest_scope_candidates(ENTITY_ARCHIVE_FILE, scope))
        all_scopes.extend(_manifest_scope_candidates(ENTITY_CORRESPONDENCE_ATTACHMENT, scope))
        query = query.filter(LocalSyncManifest.policy_scope.in_(sorted(set(all_scopes))))
    if only_pinned:
        query = query.filter(LocalSyncManifest.is_pinned.is_(True))
    rows = query.order_by(LocalSyncManifest.last_modified_at.desc(), LocalSyncManifest.id.desc()).all()

    items: list[dict] = []
    for row in rows:
        row_entity_type, row_scope = _parse_manifest_scope(row.policy_scope)
        if row_scope != scope:
            continue
        if normalized_entity and row_entity_type != normalized_entity:
            continue

        if row_entity_type == ENTITY_ARCHIVE_FILE:
            archive = _resolve_archive_for_pin(db, int(row.file_id))
            if not archive:
                continue
            try:
                _enforce_archive_scope(db, user, archive)
            except HTTPException:
                continue
            file_name = archive.original_name
            sha256 = archive.sha256
            mirror_status = archive.mirror_status
        elif row_entity_type == ENTITY_CORRESPONDENCE_ATTACHMENT:
            attachment = _resolve_attachment_for_pin(db, int(row.file_id))
            if not attachment:
                continue
            try:
                _enforce_attachment_scope(db, user, attachment)
            except HTTPException:
                continue
            file_name = attachment.file_name
            sha256 = attachment.sha256
            mirror_status = attachment.mirror_status
        else:
            continue

        items.append(
            {
                "file_id": row.file_id,
                "entity_type": row_entity_type,
                "file_name": file_name,
                "version_hash": row.version_hash,
                "sha256": sha256,
                "is_pinned": bool(row.is_pinned),
                "policy_scope": row_scope,
                "mirror_status": mirror_status,
                "last_modified_at": row.last_modified_at.isoformat() if row.last_modified_at else None,
            }
        )
    return {"ok": True, "scope": scope, "items": items}
