from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    User,
    apply_scope_query_filters,
    enforce_scope_access,
    get_db,
    get_user_scope_filters,
    require_permission,
)
from app.db.models import (
    ArchiveFile,
    Block,
    Discipline,
    DocumentActivity,
    DocumentComment,
    DocumentRelation,
    DocumentRevision,
    DocumentTag,
    DocumentTagAssignment,
    Level,
    LocalSyncManifest,
    MdrCategory,
    MdrDocument,
    Package,
    Phase,
    Project,
)
from app.services import archive_service, docnum_service, mdr_service
from app.services.nextcloud_adapter import NextcloudAdapter
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import resolve_nextcloud_runtime
from app.services.openproject_status import (
    ENTITY_ARCHIVE_FILE,
    default_openproject_sync_status,
    get_openproject_status_map,
    is_openproject_integration_enabled,
)
from app.services.site_cache import (
    build_archive_relative_path,
    normalize_site_code,
    site_manifest_policy_scope,
)

router = APIRouter(prefix="/archive", tags=["Archive"])


def _archive_openproject_status_map(db: Session, file_ids: list[int]) -> tuple[dict[tuple[str, int], dict], str]:
    clean_ids = [int(file_id) for file_id in file_ids if int(file_id or 0) > 0]
    if not clean_ids:
        return {}, default_openproject_sync_status(integration_enabled=is_openproject_integration_enabled(db))
    integration_enabled = is_openproject_integration_enabled(db)
    fallback_status = default_openproject_sync_status(integration_enabled=integration_enabled)
    status_map = get_openproject_status_map(
        db,
        [(ENTITY_ARCHIVE_FILE, file_id) for file_id in clean_ids],
        integration_enabled=integration_enabled,
    )
    return status_map, fallback_status


def _archive_openproject_payload(status_map: dict[tuple[str, int], dict], fallback_status: str, file_id: int) -> dict:
    row = status_map.get((ENTITY_ARCHIVE_FILE, int(file_id or 0)), {})
    return {
        "openproject_sync_status": str(row.get("sync_status") or fallback_status),
        "openproject_work_package_id": row.get("work_package_id"),
        "openproject_attachment_id": row.get("openproject_attachment_id"),
        "openproject_last_synced_at": row.get("last_synced_at"),
    }


def _file_kind(value: str | None) -> str:
    kind = str(value or "").strip().lower()
    return kind if kind in {"pdf", "native"} else "pdf"


def _revision_file_meta(
    revision: DocumentRevision | None,
) -> tuple[int | None, str | None, int | None, str | None]:
    if not revision:
        return None, None, None, None
    pdf_id: int | None = None
    pdf_name: str | None = None
    native_id: int | None = None
    native_name: str | None = None
    for item in revision.archive_files or []:
        kind = _file_kind(item.file_kind)
        if kind == "native":
            if native_id is None:
                native_id = item.id
                native_name = item.original_name
        elif pdf_id is None:
            pdf_id = item.id
            pdf_name = item.original_name
    return pdf_id, pdf_name, native_id, native_name


def _parse_filter_date(value: str | None, field_name: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid `{field_name}` format (YYYY-MM-DD expected).") from exc


def _extract_serial_from_doc_number(doc_number: str, prefix: str, suffix: str) -> str | None:
    try:
        value = str(doc_number or "").strip().upper()
        pfx = str(prefix or "").strip().upper()
        sfx = str(suffix or "").strip().upper()
        if not value.startswith(pfx):
            return None
        middle = value[len(pfx):]
        if sfx and middle.endswith(sfx):
            middle = middle[: -len(sfx)]
        middle = str(middle or "").strip()
        if not middle.isdigit():
            return None
        return middle
    except Exception:
        return None


def _resolve_single_subject(subject_e: str | None, subject_p: str | None) -> str:
    p = str(subject_p or "").strip()
    if p:
        return p
    return str(subject_e or "").strip()


def _subject_key_for_coding(subject_e: str | None, subject_p: str | None) -> str:
    # Single-subject policy: if subject_p is empty, fallback to subject_e.
    return _resolve_single_subject(subject_e, subject_p)


class DocumentMetadataUpdateIn(BaseModel):
    doc_title_e: Optional[str] = None
    doc_title_p: Optional[str] = None
    subject: Optional[str] = None
    phase_code: Optional[str] = None
    package_code: Optional[str] = None
    block: Optional[str] = None
    level_code: Optional[str] = None
    notes: Optional[str] = None


class DocumentCommentCreateIn(BaseModel):
    body: str
    parent_id: Optional[int] = None


class DocumentCommentUpdateIn(BaseModel):
    body: str


class DocumentRelationCreateIn(BaseModel):
    target_document_id: int
    relation_type: Optional[str] = "related"
    notes: Optional[str] = None


class DocumentTagCreateIn(BaseModel):
    name: str
    color: Optional[str] = None


class DocumentTagAssignIn(BaseModel):
    tag_id: Optional[int] = None
    tag_name: Optional[str] = None
    color: Optional[str] = None


def _parse_json_text(raw: str | None) -> Any:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return text


def _user_display_name(user_obj: Any) -> str | None:
    if not user_obj:
        return None
    return str(getattr(user_obj, "full_name", None) or getattr(user_obj, "email", None) or "").strip() or None


def _serialize_document_payload(document: MdrDocument) -> dict[str, Any]:
    return {
        "id": int(document.id or 0),
        "doc_number": document.doc_number,
        "doc_title_e": document.doc_title_e,
        "doc_title_p": document.doc_title_p,
        "subject": document.subject,
        "project_code": document.project_code,
        "phase_code": document.phase_code,
        "discipline_code": document.discipline_code,
        "package_code": document.package_code,
        "block": document.block,
        "level_code": document.level_code,
        "mdr_code": document.mdr_code,
        "notes": document.notes,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
        "deleted_at": document.deleted_at.isoformat() if document.deleted_at else None,
        "updated_by_id": document.updated_by_id,
        "updated_by_name": _user_display_name(getattr(document, "updated_by", None)),
        "deleted_by_id": document.deleted_by_id,
        "deleted_by_name": _user_display_name(getattr(document, "deleted_by", None)),
    }


def _serialize_archive_file(row: ArchiveFile | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": int(row.id or 0),
        "name": row.original_name,
        "mime_type": row.mime_type,
        "detected_mime": row.detected_mime,
        "size_bytes": row.size_bytes,
        "file_kind": row.file_kind,
        "status": row.status,
        "is_primary": bool(row.is_primary) if row.is_primary is not None else True,
        "revision": row.revision,
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
    }


def _serialize_revision_payload(row: DocumentRevision | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "revision_id": int(row.id or 0),
        "revision": row.revision,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_activity_payload(row: DocumentActivity) -> dict[str, Any]:
    return {
        "id": int(row.id or 0),
        "document_id": int(row.document_id or 0),
        "action": row.action,
        "detail": row.detail,
        "before_data": _parse_json_text(row.before_json),
        "after_data": _parse_json_text(row.after_json),
        "actor_user_id": row.actor_user_id,
        "actor_name": row.actor_name,
        "actor_email": row.actor_email,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_comment_payload(row: DocumentComment) -> dict[str, Any]:
    return {
        "id": int(row.id or 0),
        "document_id": int(row.document_id or 0),
        "parent_id": int(row.parent_id or 0) or None,
        "author_id": int(row.author_id or 0) or None,
        "author_name": row.author_name,
        "author_email": row.author_email,
        "body": None if row.deleted_at else row.body,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        "is_deleted": bool(row.deleted_at),
        "children": [],
    }


def _build_comment_tree(rows: list[DocumentComment]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            row.created_at.isoformat() if row.created_at else "",
            int(row.id or 0),
        ),
    )
    by_id: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in ordered:
        payload = _serialize_comment_payload(row)
        by_id[payload["id"]] = payload
        parent_id = payload["parent_id"]
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(payload)
        else:
            roots.append(payload)
    return roots


def _serialize_relation_payload(row: DocumentRelation, *, direction: str) -> dict[str, Any]:
    counterpart = row.target_document if direction == "outgoing" else row.source_document
    return {
        "id": int(row.id or 0),
        "source_document_id": int(row.source_document_id or 0),
        "target_document_id": int(row.target_document_id or 0),
        "relation_type": row.relation_type,
        "notes": row.notes,
        "created_by_id": row.created_by_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "direction": direction,
        "counterpart": {
            "id": int(getattr(counterpart, "id", 0) or 0),
            "doc_number": getattr(counterpart, "doc_number", None),
            "doc_title_e": getattr(counterpart, "doc_title_e", None),
            "doc_title_p": getattr(counterpart, "doc_title_p", None),
            "subject": getattr(counterpart, "subject", None),
            "project_code": getattr(counterpart, "project_code", None),
            "discipline_code": getattr(counterpart, "discipline_code", None),
            "deleted_at": (
                getattr(counterpart, "deleted_at", None).isoformat()
                if getattr(counterpart, "deleted_at", None)
                else None
            ),
        },
    }


def _serialize_tag_payload(row: DocumentTag) -> dict[str, Any]:
    return {
        "id": int(row.id or 0),
        "name": row.name,
        "color": row.color,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_tag_assignment_payload(row: DocumentTagAssignment) -> dict[str, Any]:
    tag = getattr(row, "tag", None)
    return {
        "id": int(row.id or 0),
        "document_id": int(row.document_id or 0),
        "tag_id": int(row.tag_id or 0),
        "assigned_by_id": row.assigned_by_id,
        "assigned_at": row.assigned_at.isoformat() if row.assigned_at else None,
        "tag": {
            "id": int(getattr(tag, "id", 0) or 0),
            "name": getattr(tag, "name", None),
            "color": getattr(tag, "color", None),
        },
    }


@router.get("/check-status")
async def check_document_status(
    doc_code: str = Query(..., min_length=3),
    subject_e: Optional[str] = Query(None),
    subject_p: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    """????? ????? ??? ? ??????? ?????? ????"""
    payload = archive_service.get_document_status_info(db, doc_code, subject_e, subject_p)
    parsed_payload = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else None
    if payload.get("exists") and payload.get("document_id"):
        doc = db.query(MdrDocument).filter(MdrDocument.id == payload["document_id"]).first()
        if doc:
            enforce_scope_access(
                db,
                user,
                project_code=doc.project_code,
                discipline_code=doc.discipline_code,
            )
            payload["project_code"] = doc.project_code
            payload["discipline_code"] = doc.discipline_code
    elif parsed_payload:
        enforce_scope_access(
            db,
            user,
            project_code=parsed_payload.get("project_code"),
            discipline_code=parsed_payload.get("discipline_code"),
        )
    return payload


@router.get("/doc-suggestions")
def get_doc_suggestions(
    q: Optional[str] = Query(None),
    project_code: Optional[str] = Query(None),
    limit: int = Query(default=15, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    query = db.query(MdrDocument).filter(MdrDocument.deleted_at.is_(None))
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=MdrDocument.project_code,
        discipline_column=MdrDocument.discipline_code,
    )

    project = str(project_code or "").strip().upper()
    if project:
        enforce_scope_access(db, user, project_code=project)
        query = query.filter(MdrDocument.project_code == project)

    term = str(q or "").strip()
    if term:
        like_term = f"%{term.replace(' ', '%')}%"
        query = query.filter(
            or_(
                MdrDocument.doc_number.ilike(like_term),
                MdrDocument.doc_title_e.ilike(like_term),
                MdrDocument.doc_title_p.ilike(like_term),
                MdrDocument.subject.ilike(like_term),
            )
        )

    rows = query.order_by(MdrDocument.doc_number.asc()).limit(limit).all()
    items = [
        {
            "id": row.id,
            "doc_number": row.doc_number,
            "title_e": row.doc_title_e or "",
            "title_p": row.doc_title_p or "",
        }
        for row in rows
    ]
    return {"ok": True, "items": items}


@router.post("/register-document")
async def register_document_only(
    doc_number: str = Form(...),
    project_code: str = Form(...),
    mdr_code: Optional[str] = Form(None),
    phase: Optional[str] = Form(None),
    discipline: Optional[str] = Form(None),
    package: Optional[str] = Form(None),
    block: Optional[str] = Form(None),
    level: Optional[str] = Form(None),
    subject_e: Optional[str] = Form(None),
    subject_p: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:create")),
):
    if not doc_number or not project_code or not package or not block:
        raise HTTPException(
            status_code=400,
            detail="Required fields missing (doc_number, project_code, package, block).",
        )

    enforce_scope_access(
        db,
        user,
        project_code=project_code,
        discipline_code=discipline,
    )

    normalized_doc_number = str(doc_number or "").strip().upper()
    subject_value = _resolve_single_subject(subject_e, subject_p)
    subject_key = _subject_key_for_coding(subject_e, subject_p)
    existing_meta_doc = None
    if subject_key:
        existing_meta_doc = mdr_service.find_document_by_metadata_key(
            db,
            project_code=str(project_code or "").strip().upper(),
            mdr_code=str(mdr_code or "X").strip().upper() or "X",
            phase_code=str(phase or "X").strip().upper() or "X",
            discipline_code=str(discipline or "XX").strip().upper() or "XX",
            package_code=str(package or "").strip().upper(),
            block=str(block or "").strip().upper(),
            level_code=str(level or "GEN").strip().upper() or "GEN",
            subject=subject_key,
        )
    if existing_meta_doc:
        status_info = archive_service.get_document_status_info(db, existing_meta_doc.doc_number)
        return {
            "ok": True,
            "created": False,
            "document_id": existing_meta_doc.id,
            "doc_number": existing_meta_doc.doc_number,
            "title": existing_meta_doc.doc_title_e or existing_meta_doc.subject or "",
            "last_revision": status_info.get("last_revision", "N/A"),
            "last_status": status_info.get("last_status", "Registered"),
            "next_revision_suggestion": status_info.get("next_revision_suggestion", "00"),
            "duplicate_meta": True,
        }

    meta_data = {
        "doc_number": normalized_doc_number,
        "project_code": str(project_code or "").strip().upper(),
        "mdr_code": str(mdr_code or "X").strip().upper() or "X",
        "phase": str(phase or "X").strip().upper() or "X",
        "discipline": str(discipline or "XX").strip().upper() or "XX",
        "package": str(package or "").strip().upper(),
        "block": str(block or "").strip().upper(),
        "level": str(level or "GEN").strip().upper() or "GEN",
        "subject_e": subject_value,
        "subject_p": subject_value,
    }

    try:
        doc, created = archive_service.register_document_metadata(
            db=db,
            meta_data=meta_data,
            actor=user,
        )
        status_info = archive_service.get_document_status_info(db, doc.doc_number)
        return {
            "ok": True,
            "created": bool(created),
            "document_id": doc.id,
            "doc_number": doc.doc_number,
            "title": doc.doc_title_e or doc.subject or "",
            "last_revision": status_info.get("last_revision", "N/A"),
            "last_status": status_info.get("last_status", "Registered"),
            "next_revision_suggestion": status_info.get("next_revision_suggestion", "00"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload")
async def upload_file(
    document_id: int = Form(...),
    revision: str = Form(...),
    status: str = Form("IFA"),
    file_kind: str = Form("pdf"),
    openproject_work_package_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:update")),
):
    """????? ???? ???? ???? ?? ????? ???? ????"""
    document = db.query(MdrDocument).filter(MdrDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    try:
        result = archive_service.save_upload_file(
            db=db,
            file=file,
            document_id=document_id,
            revision_code=revision,
            status_code=status,
            file_kind=file_kind,
            openproject_work_package_id=openproject_work_package_id,
            is_admin=user.role == "admin",
            actor=user,
        )
        status_map, fallback_status = _archive_openproject_status_map(db, [int(result.id or 0)])
        return {
            "ok": True,
            "message": "???? ?? ?????? ????? ??.",
            "file_id": result.id,
            "new_name": result.original_name,
            "revision": result.revision,
            "sha256": result.sha256,
            "detected_mime": result.detected_mime,
            "validation_status": result.validation_status,
            "mirror_status": result.mirror_status,
            **_archive_openproject_payload(status_map, fallback_status, int(result.id or 0)),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload-dual")
async def upload_dual_files(
    document_id: int = Form(...),
    revision: str = Form(...),
    status: str = Form("IFA"),
    openproject_work_package_id: Optional[int] = Form(None),
    pdf_file: UploadFile = File(...),
    native_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:update")),
):
    """Upload both PDF and Native files and link them as companion files."""
    document = db.query(MdrDocument).filter(MdrDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    try:
        pdf_entry, native_entry = archive_service.save_dual_upload_files(
            db=db,
            pdf_file=pdf_file,
            native_file=native_file,
            document_id=document_id,
            revision_code=revision,
            status_code=status,
            openproject_work_package_id=openproject_work_package_id,
            is_admin=user.role == "admin",
            actor=user,
        )
        status_map, fallback_status = _archive_openproject_status_map(
            db, [int(pdf_entry.id or 0), int(native_entry.id or 0)]
        )
        return {
            "ok": True,
            "message": "Dual files uploaded successfully.",
            "document_id": document_id,
            "revision": revision,
            "pdf_file_id": pdf_entry.id,
            "native_file_id": native_entry.id,
            "pdf_name": pdf_entry.original_name,
            "native_name": native_entry.original_name,
            "pdf_sha256": pdf_entry.sha256,
            "native_sha256": native_entry.sha256,
            "pdf_validation_status": pdf_entry.validation_status,
            "native_validation_status": native_entry.validation_status,
            "mirror_status": {
                "pdf": pdf_entry.mirror_status,
                "native": native_entry.mirror_status,
            },
            "openproject_sync_status": {
                "pdf": _archive_openproject_payload(status_map, fallback_status, int(pdf_entry.id or 0))[
                    "openproject_sync_status"
                ],
                "native": _archive_openproject_payload(
                    status_map, fallback_status, int(native_entry.id or 0)
                )["openproject_sync_status"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Dual Upload Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/register-and-upload")
async def register_and_upload(
    file: UploadFile = File(...),
    revision: str = Form(...),
    status: str = Form("IFA"),
    file_kind: str = Form("pdf"),
    openproject_work_package_id: Optional[int] = Form(None),
    doc_number: Optional[str] = Form(None),
    project_code: Optional[str] = Form(None),
    mdr_code: Optional[str] = Form(None),
    phase: Optional[str] = Form(None),
    discipline: Optional[str] = Form(None),
    package: Optional[str] = Form(None),
    block: Optional[str] = Form(None),
    level: Optional[str] = Form(None),
    subject_e: Optional[str] = Form(None),
    subject_p: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:update")),
):
    """??? ?????? ???? + ????? ????"""
    if not doc_number or not project_code or not package or not block:
        raise HTTPException(
            status_code=400,
            detail="??????? ???? ??? (?????? ?????? ????? ????) ???? ???.",
        )
    enforce_scope_access(
        db,
        user,
        project_code=project_code,
        discipline_code=discipline,
    )

    try:
        meta_data = {
            "doc_number": doc_number,
            "project_code": project_code,
            "mdr_code": mdr_code or "X",
            "phase": phase or "X",
            "discipline": discipline or "XX",
            "package": package,
            "block": block,
            "level": level or "XX",
            "subject_e": _resolve_single_subject(subject_e, subject_p),
            "subject_p": _resolve_single_subject(subject_e, subject_p),
        }

        result = archive_service.register_and_upload_document(
            db=db,
            file=file,
            meta_data=meta_data,
            revision_code=revision,
            status_code=status,
            file_kind=file_kind,
            openproject_work_package_id=openproject_work_package_id,
            is_admin=user.role == "admin",
            actor=user,
        )
        status_map, fallback_status = _archive_openproject_status_map(db, [int(result.id or 0)])

        return {
            "ok": True,
            "message": "???? ?? ?????? ??? ? ???? ????? ??.",
            "file_id": result.id,
            "doc_number": meta_data["doc_number"],
            "sha256": result.sha256,
            "detected_mime": result.detected_mime,
            "validation_status": result.validation_status,
            "mirror_status": result.mirror_status,
            **_archive_openproject_payload(status_map, fallback_status, int(result.id or 0)),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Full Register Error: {e}")
        raise HTTPException(status_code=400, detail=f"??? ?? ??? ???: {str(e)}")


@router.post("/register-and-upload-dual")
async def register_and_upload_dual(
    pdf_file: UploadFile = File(...),
    native_file: UploadFile = File(...),
    revision: str = Form(...),
    status: str = Form("IFA"),
    openproject_work_package_id: Optional[int] = Form(None),
    doc_number: Optional[str] = Form(None),
    project_code: Optional[str] = Form(None),
    mdr_code: Optional[str] = Form(None),
    phase: Optional[str] = Form(None),
    discipline: Optional[str] = Form(None),
    package: Optional[str] = Form(None),
    block: Optional[str] = Form(None),
    level: Optional[str] = Form(None),
    subject_e: Optional[str] = Form(None),
    subject_p: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:update")),
):
    if not doc_number or not project_code or not package or not block:
        raise HTTPException(
            status_code=400,
            detail="??????? ???? ??? (?????? ?????? ????? ????) ???? ???.",
        )
    enforce_scope_access(
        db,
        user,
        project_code=project_code,
        discipline_code=discipline,
    )
    try:
        meta_data = {
            "doc_number": doc_number,
            "project_code": project_code,
            "mdr_code": mdr_code or "X",
            "phase": phase or "X",
            "discipline": discipline or "XX",
            "package": package,
            "block": block,
            "level": level or "XX",
            "subject_e": _resolve_single_subject(subject_e, subject_p),
            "subject_p": _resolve_single_subject(subject_e, subject_p),
        }

        pdf_entry, native_entry = archive_service.register_and_upload_dual_document(
            db=db,
            pdf_file=pdf_file,
            native_file=native_file,
            meta_data=meta_data,
            revision_code=revision,
            status_code=status,
            openproject_work_package_id=openproject_work_package_id,
            is_admin=user.role == "admin",
            actor=user,
        )
        status_map, fallback_status = _archive_openproject_status_map(
            db, [int(pdf_entry.id or 0), int(native_entry.id or 0)]
        )

        return {
            "ok": True,
            "message": "Dual files uploaded successfully.",
            "doc_number": meta_data["doc_number"],
            "revision": revision,
            "pdf_file_id": pdf_entry.id,
            "native_file_id": native_entry.id,
            "pdf_sha256": pdf_entry.sha256,
            "native_sha256": native_entry.sha256,
            "pdf_validation_status": pdf_entry.validation_status,
            "native_validation_status": native_entry.validation_status,
            "mirror_status": {
                "pdf": pdf_entry.mirror_status,
                "native": native_entry.mirror_status,
            },
            "openproject_sync_status": {
                "pdf": _archive_openproject_payload(status_map, fallback_status, int(pdf_entry.id or 0))[
                    "openproject_sync_status"
                ],
                "native": _archive_openproject_payload(
                    status_map, fallback_status, int(native_entry.id or 0)
                )["openproject_sync_status"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Full Dual Register Error: {e}")
        raise HTTPException(status_code=400, detail=f"??? ?? ??? ???: {str(e)}")


@router.get("/list")
async def list_archives(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    project_code: Optional[str] = None,
    discipline_code: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    site_code: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    query = (
        db.query(ArchiveFile)
        .options(
            joinedload(ArchiveFile.document_revision)
            .joinedload(DocumentRevision.document)
            .joinedload(MdrDocument.project),
            joinedload(ArchiveFile.document_revision)
            .joinedload(DocumentRevision.document)
            .joinedload(MdrDocument.discipline),
            joinedload(ArchiveFile.document_revision)
            .joinedload(DocumentRevision.document)
            .joinedload(MdrDocument.package),
            joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.archive_files),
        )
        .join(DocumentRevision)
        .join(MdrDocument)
        .filter(ArchiveFile.deleted_at.is_(None), MdrDocument.deleted_at.is_(None))
    )
    query = apply_scope_query_filters(
        query,
        db,
        user,
        project_column=MdrDocument.project_code,
        discipline_column=MdrDocument.discipline_code,
    )
    # Keep list rows focused on one row per revision/document.
    # Native companion files are still reachable via `native_file_id`.
    query = query.filter(
        or_(ArchiveFile.is_primary.is_(True), ArchiveFile.is_primary.is_(None))
    )
    query = query.filter(
        or_(ArchiveFile.file_kind.is_(None), ArchiveFile.file_kind != "native")
    )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                ArchiveFile.original_name.ilike(search_term),
                MdrDocument.doc_number.ilike(search_term),
                DocumentRevision.status.ilike(search_term),
                MdrDocument.doc_title_e.ilike(search_term),
                MdrDocument.doc_title_p.ilike(search_term),
            )
        )

    project_code = str(project_code or "").strip()
    if project_code:
        query = query.filter(MdrDocument.project_code == project_code)

    discipline_code = str(discipline_code or "").strip()
    if discipline_code:
        query = query.filter(MdrDocument.discipline_code == discipline_code)

    status = str(status or "").strip()
    if status:
        query = query.filter(ArchiveFile.status.ilike(status))

    from_dt = _parse_filter_date(date_from, "date_from")
    to_dt = _parse_filter_date(date_to, "date_to")
    if from_dt and to_dt and from_dt > to_dt:
        raise HTTPException(status_code=400, detail="`date_from` must be earlier than or equal to `date_to`.")
    if from_dt:
        query = query.filter(ArchiveFile.uploaded_at >= from_dt)
    if to_dt:
        query = query.filter(ArchiveFile.uploaded_at < (to_dt + timedelta(days=1)))

    total = query.count()
    files = query.order_by(ArchiveFile.uploaded_at.desc()).offset(skip).limit(limit).all()
    status_map, fallback_status = _archive_openproject_status_map(
        db, [int(row.id or 0) for row in files]
    )
    normalized_site_code = normalize_site_code(site_code)
    site_scope = site_manifest_policy_scope(normalized_site_code) if normalized_site_code else ""
    pinned_ids: set[int] = set()
    if site_scope:
        file_ids = [int(row.id or 0) for row in files if int(row.id or 0) > 0]
        if file_ids:
            pinned_rows = (
                db.query(LocalSyncManifest.file_id)
                .filter(
                    LocalSyncManifest.file_id.in_(file_ids),
                    LocalSyncManifest.policy_scope == site_scope,
                    LocalSyncManifest.is_pinned.is_(True),
                )
                .all()
            )
            pinned_ids = {int(row.file_id) for row in pinned_rows}

    data = []
    for f in files:
        revision_row = f.document_revision
        document_row = revision_row.document if revision_row else None
        doc_num = document_row.doc_number if document_row else "Unknown"
        pdf_file_id, pdf_file_name, native_file_id, native_file_name = _revision_file_meta(revision_row)
        pdf_relative_path = None
        native_relative_path = None
        if revision_row:
            for item in revision_row.archive_files or []:
                kind = _file_kind(item.file_kind)
                rel_path = build_archive_relative_path(item)
                if kind == "native":
                    if native_relative_path is None:
                        native_relative_path = rel_path
                elif pdf_relative_path is None:
                    pdf_relative_path = rel_path
        op_payload = _archive_openproject_payload(status_map, fallback_status, int(f.id or 0))
        project_name = None
        discipline_name = None
        package_name = None
        if document_row:
            if document_row.project:
                project_name = document_row.project.name_p or document_row.project.name_e
            if document_row.discipline:
                discipline_name = document_row.discipline.name_p or document_row.discipline.name_e
            if document_row.package:
                package_name = document_row.package.name_p or document_row.package.name_e
        data.append(
            {
                "id": f.id,
                "name": f.original_name,
                "doc_number": doc_num,
                "document_id": document_row.id if document_row else None,
                "doc_title_e": document_row.doc_title_e if document_row else None,
                "doc_title_p": document_row.doc_title_p if document_row else None,
                "project_code": document_row.project_code if document_row else None,
                "project_name": project_name,
                "discipline_code": document_row.discipline_code if document_row else None,
                "discipline_name": discipline_name,
                "package_code": document_row.package_code if document_row else None,
                "package_name": package_name,
                "revision_id": revision_row.id if revision_row else None,
                "revision": f.revision,
                "size": f.size_bytes,
                "status": f.status,
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
                "type": f.mime_type,
                "detected_mime": f.detected_mime,
                "validation_status": f.validation_status,
                "sha256": f.sha256,
                "storage_backend": f.storage_backend,
                "gdrive_file_id": f.gdrive_file_id,
                "mirror_provider": getattr(f, "mirror_provider", None),
                "mirror_remote_id": getattr(f, "mirror_remote_id", None),
                "mirror_remote_url": getattr(f, "mirror_remote_url", None),
                "mirror_status": f.mirror_status,
                "mirror_updated_at": f.mirror_updated_at.isoformat() if f.mirror_updated_at else None,
                "file_kind": f.file_kind or "pdf",
                "is_primary": True if f.is_primary is None else bool(f.is_primary),
                "companion_file_id": f.companion_file_id,
                "pdf_file_id": pdf_file_id,
                "pdf_file_name": pdf_file_name,
                "pdf_relative_path": pdf_relative_path,
                "native_file_id": native_file_id,
                "native_file_name": native_file_name,
                "native_relative_path": native_relative_path,
                "site_relative_path": build_archive_relative_path(f),
                "site_pinned": bool(int(f.id or 0) in pinned_ids) if site_scope else None,
                "site_scope": site_scope or None,
                **op_payload,
            }
        )

    return {"ok": True, "total": total, "data": data}


@router.get("/revision-history/{document_id}")
async def revision_history(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    document = (
        db.query(MdrDocument)
        .options(joinedload(MdrDocument.revisions).joinedload(DocumentRevision.archive_files))
        .filter(MdrDocument.id == document_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    all_file_ids: list[int] = []
    for rev in document.revisions or []:
        for af in rev.archive_files or []:
            if af.deleted_at is not None:
                continue
            all_file_ids.append(int(af.id or 0))
    status_map, fallback_status = _archive_openproject_status_map(db, all_file_ids)

    revisions_payload = []
    for rev in sorted(
        document.revisions or [],
        key=lambda r: (r.created_at is not None, r.created_at or ""),
        reverse=True,
    ):
        files_payload = []
        for af in sorted(
            rev.archive_files or [],
            key=lambda r: (r.uploaded_at is not None, r.uploaded_at or ""),
            reverse=True,
        ):
            if af.deleted_at is not None:
                continue
            op_payload = _archive_openproject_payload(status_map, fallback_status, int(af.id or 0))
            files_payload.append(
                {
                    "id": af.id,
                    "name": af.original_name,
                    "file_kind": _file_kind(af.file_kind),
                    "size": af.size_bytes,
                    "mime_type": af.mime_type,
                    "detected_mime": af.detected_mime,
                    "validation_status": af.validation_status,
                    "sha256": af.sha256,
                    "storage_backend": af.storage_backend,
                    "gdrive_file_id": af.gdrive_file_id,
                    "mirror_provider": getattr(af, "mirror_provider", None),
                    "mirror_remote_id": getattr(af, "mirror_remote_id", None),
                    "mirror_remote_url": getattr(af, "mirror_remote_url", None),
                    "mirror_status": af.mirror_status,
                    "mirror_updated_at": af.mirror_updated_at.isoformat() if af.mirror_updated_at else None,
                    "status": af.status,
                    "is_primary": True if af.is_primary is None else bool(af.is_primary),
                    "companion_file_id": af.companion_file_id,
                    "uploaded_at": af.uploaded_at.isoformat() if af.uploaded_at else None,
                    **op_payload,
                }
            )

        revisions_payload.append(
            {
                "revision_id": rev.id,
                "revision": rev.revision,
                "status": rev.status,
                "created_at": rev.created_at.isoformat() if rev.created_at else None,
                "files": files_payload,
            }
        )

    return {
        "ok": True,
        "document": {
            "id": document.id,
            "doc_number": document.doc_number,
            "title_e": document.doc_title_e,
            "title_p": document.doc_title_p,
            "project_code": document.project_code,
            "discipline_code": document.discipline_code,
        },
        "revisions": revisions_payload,
    }


def _download_from_webdav(db: Session, file_record: ArchiveFile, stored_path: str) -> StreamingResponse:
    """Stream file from Nextcloud WebDAV."""
    integrations = get_storage_integrations(db)
    runtime = resolve_nextcloud_runtime(integrations)

    if not runtime.get("enabled") or runtime.get("mode") != "webdav":
        raise HTTPException(status_code=503, detail="WebDAV storage not configured.")

    adapter = NextcloudAdapter(
        base_url=str(runtime.get("base_url") or ""),
        username=str(runtime.get("username") or ""),
        app_password=str(runtime.get("app_password") or ""),
        root_path=str(runtime.get("root_path") or ""),
        connect_timeout=float(runtime.get("connect_timeout") or 5),
        read_timeout=float(runtime.get("read_timeout") or 10),
        tls_verify=bool(runtime.get("tls_verify")),
    )

    # Strip "webdav://" prefix
    remote_path = stored_path.replace("webdav://", "")

    # Check if file exists
    if not adapter.file_exists(remote_path):
        raise HTTPException(status_code=404, detail="File not found on Nextcloud.")

    # Stream response
    return StreamingResponse(
        adapter.download_file_stream(remote_path),
        media_type=file_record.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{file_record.original_name}"'
        },
    )


@router.get("/download/{file_id}")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    file_record = db.query(ArchiveFile).filter(ArchiveFile.id == file_id, ArchiveFile.deleted_at.is_(None)).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found.")

    # Access control
    if file_record.document_revision and file_record.document_revision.document:
        doc = file_record.document_revision.document
        enforce_scope_access(
            db,
            user,
            project_code=doc.project_code,
            discipline_code=doc.discipline_code,
        )

    stored_path = str(file_record.stored_path or "").strip()

    # WebDAV download
    if stored_path.startswith("webdav://"):
        return _download_from_webdav(db, file_record, stored_path)

    # Local filesystem download
    if not os.path.exists(stored_path):
        raise HTTPException(status_code=404, detail="File not found on disk.")

    return FileResponse(
        path=stored_path,
        filename=file_record.original_name,
        media_type=file_record.mime_type,
    )


@router.get("/files/{file_id}/integrity")
async def get_file_integrity(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    file_record = db.query(ArchiveFile).filter(ArchiveFile.id == file_id, ArchiveFile.deleted_at.is_(None)).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    if file_record.document_revision and file_record.document_revision.document:
        doc = file_record.document_revision.document
        enforce_scope_access(
            db,
            user,
            project_code=doc.project_code,
            discipline_code=doc.discipline_code,
        )
    status_map, fallback_status = _archive_openproject_status_map(db, [int(file_record.id or 0)])
    op_payload = _archive_openproject_payload(status_map, fallback_status, int(file_record.id or 0))
    return {
        "ok": True,
        "file_id": file_record.id,
        "sha256": file_record.sha256,
        "declared_mime": file_record.mime_type,
        "detected_mime": file_record.detected_mime,
        "validation_status": file_record.validation_status,
        "storage_backend": file_record.storage_backend,
        "gdrive_file_id": file_record.gdrive_file_id,
        "mirror_provider": getattr(file_record, "mirror_provider", None),
        "mirror_remote_id": getattr(file_record, "mirror_remote_id", None),
        "mirror_remote_url": getattr(file_record, "mirror_remote_url", None),
        "mirror_status": file_record.mirror_status,
        "mirror_updated_at": file_record.mirror_updated_at.isoformat()
        if file_record.mirror_updated_at
        else None,
        **op_payload,
    }


@router.get("/documents/{document_id}")
async def get_document_detail(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    payload = archive_service.get_document_detail(db, int(document_id), user)
    document = payload.get("document")
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    is_deleted = bool(payload.get("is_deleted"))
    capabilities = dict(payload.get("capabilities") or {})
    if is_deleted:
        capabilities.update(
            {
                "can_edit": False,
                "can_delete": False,
                "can_comment": False,
                "can_manage_relations": False,
                "can_manage_tags": False,
            }
        )

    return {
        "ok": True,
        "document": _serialize_document_payload(document),
        "latest_revision": _serialize_revision_payload(payload.get("latest_revision")),
        "latest_files": {
            "preview": _serialize_archive_file((payload.get("latest_files") or {}).get("preview")),
            "latest": _serialize_archive_file((payload.get("latest_files") or {}).get("latest")),
        },
        "preview_meta": payload.get("preview_meta") or {},
        "counts": payload.get("counts") or {},
        "capabilities": capabilities,
        "is_deleted": is_deleted,
        "revisions": payload.get("revisions") or [],
        "comments": payload.get("comments") or [],
        "activities": [_serialize_activity_payload(row) for row in payload.get("activities") or []],
        "relations": {
            "outgoing": [
                _serialize_relation_payload(row, direction="outgoing")
                for row in (payload.get("relations") or {}).get("outgoing", [])
            ],
            "incoming": [
                _serialize_relation_payload(row, direction="incoming")
                for row in (payload.get("relations") or {}).get("incoming", [])
            ],
        },
        "tags": [_serialize_tag_assignment_payload(row) for row in payload.get("tags") or []],
        "transmittals": payload.get("transmittals") or [],
    }


@router.put("/documents/{document_id}")
async def update_document_metadata(
    document_id: int,
    body: DocumentMetadataUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:update")),
):
    updates = body.model_dump(exclude_none=True)
    updated = archive_service.update_document_metadata(db, int(document_id), updates, user)
    detail = archive_service.get_document_detail(db, int(updated.id or 0), user)
    return {
        "ok": True,
        "document": _serialize_document_payload(updated),
        "capabilities": detail.get("capabilities") or {},
        "is_deleted": bool(updated.deleted_at),
    }


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:delete")),
):
    deleted = archive_service.soft_delete_document(db, int(document_id), user)
    return {
        "ok": True,
        "document_id": int(deleted.id or 0),
        "deleted_at": deleted.deleted_at.isoformat() if deleted.deleted_at else None,
        "deleted_by_id": deleted.deleted_by_id,
    }


@router.get("/documents/{document_id}/preview")
async def stream_document_preview(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    payload = archive_service.get_document_detail(db, int(document_id), user)
    preview_file = (payload.get("latest_files") or {}).get("preview")
    if not preview_file:
        raise HTTPException(status_code=404, detail="Preview file not found")
    if preview_file.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Preview file not found")
    file_path = str(preview_file.stored_path or "").strip()
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Preview file not found")
    media_type = str(preview_file.mime_type or preview_file.detected_mime or "application/octet-stream")
    filename = str(preview_file.original_name or f"document_{document_id}").replace('"', "")
    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/documents/{document_id}/activity")
async def list_document_activity(
    document_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    payload = archive_service.list_document_activity(db, int(document_id), user, skip=skip, limit=limit)
    return {
        "ok": True,
        "total": int(payload.get("total") or 0),
        "data": [_serialize_activity_payload(row) for row in payload.get("data") or []],
    }


@router.get("/documents/{document_id}/comments")
async def list_document_comments(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    rows = archive_service.list_document_comments(db, int(document_id), user)
    return {"ok": True, "items": _build_comment_tree(rows)}


@router.post("/documents/{document_id}/comments")
async def create_document_comment(
    document_id: int,
    body: DocumentCommentCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:comment_create")),
):
    row = archive_service.create_document_comment(
        db,
        int(document_id),
        body=str(body.body or "").strip(),
        user=user,
        parent_id=body.parent_id,
    )
    return {"ok": True, "item": _serialize_comment_payload(row)}


@router.put("/documents/{document_id}/comments/{comment_id}")
async def update_document_comment(
    document_id: int,
    comment_id: int,
    body: DocumentCommentUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:comment_update")),
):
    row = archive_service.update_document_comment(
        db,
        int(document_id),
        int(comment_id),
        body=str(body.body or "").strip(),
        user=user,
    )
    return {"ok": True, "item": _serialize_comment_payload(row)}


@router.delete("/documents/{document_id}/comments/{comment_id}")
async def delete_document_comment(
    document_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:comment_delete")),
):
    row = archive_service.delete_document_comment(db, int(document_id), int(comment_id), user)
    return {"ok": True, "item": _serialize_comment_payload(row)}


@router.get("/documents/{document_id}/transmittals")
async def list_document_transmittals(
    document_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    payload = archive_service.list_document_transmittals(
        db,
        int(document_id),
        user=user,
        skip=skip,
        limit=limit,
    )
    return payload


@router.get("/documents/{document_id}/relations")
async def list_document_relations(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    payload = archive_service.list_document_relations(db, int(document_id), user)
    return {
        "ok": True,
        "outgoing": [_serialize_relation_payload(row, direction="outgoing") for row in payload.get("outgoing") or []],
        "incoming": [_serialize_relation_payload(row, direction="incoming") for row in payload.get("incoming") or []],
    }


@router.post("/documents/{document_id}/relations")
async def create_document_relation(
    document_id: int,
    body: DocumentRelationCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:relation_manage")),
):
    row = archive_service.create_document_relation(
        db,
        int(document_id),
        int(body.target_document_id),
        relation_type=str(body.relation_type or "related"),
        notes=body.notes,
        user=user,
    )
    return {"ok": True, "relation": _serialize_relation_payload(row, direction="outgoing")}


@router.delete("/documents/{document_id}/relations/{relation_id}")
async def delete_document_relation(
    document_id: int,
    relation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:relation_manage")),
):
    archive_service.delete_document_relation(db, int(document_id), int(relation_id), user)
    return {"ok": True, "document_id": int(document_id), "relation_id": int(relation_id)}


@router.get("/tags")
async def list_tags(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    del user
    rows = archive_service.list_tags(db)
    return {"ok": True, "items": [_serialize_tag_payload(row) for row in rows]}


@router.post("/tags")
async def create_tag(
    body: DocumentTagCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:tag_manage")),
):
    row = archive_service.create_tag(db, name=body.name, color=body.color, user=user)
    return {"ok": True, "tag": _serialize_tag_payload(row)}


@router.get("/documents/{document_id}/tags")
async def list_document_tags(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    rows = archive_service.list_document_tags(db, int(document_id), user)
    return {"ok": True, "items": [_serialize_tag_assignment_payload(row) for row in rows]}


@router.post("/documents/{document_id}/tags")
async def assign_document_tag(
    document_id: int,
    body: DocumentTagAssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:tag_manage")),
):
    row = archive_service.assign_tag_to_document(
        db,
        int(document_id),
        tag_name=body.tag_name,
        tag_id=body.tag_id,
        color=body.color,
        user=user,
    )
    return {"ok": True, "item": _serialize_tag_assignment_payload(row)}


@router.delete("/documents/{document_id}/tags/{tag_id}")
async def remove_document_tag(
    document_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents:tag_manage")),
):
    archive_service.remove_tag_from_document(db, int(document_id), int(tag_id), user)
    return {"ok": True, "document_id": int(document_id), "tag_id": int(tag_id)}


@router.get("/form-data")
def get_archive_form_data(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    """??????? ???? ???? ???????????? ???? ?? ? ???"""
    scope_filters = get_user_scope_filters(db, user)
    allowed_projects = set(scope_filters["projects"])
    allowed_disciplines = set(scope_filters["disciplines"])
    projects_restricted = bool(scope_filters.get("projects_restricted"))
    disciplines_restricted = bool(scope_filters.get("disciplines_restricted"))

    data = {
        "projects": [
            {"code": p.code, "name": p.name_e or p.name_p or ""}
            for p in db.query(Project).order_by(Project.code).all()
            if (not projects_restricted) or p.code in allowed_projects
        ],
        "disciplines": [
            {"code": d.code, "name": d.name_e or d.name_p or ""}
            for d in db.query(Discipline).order_by(Discipline.code).all()
            if (not disciplines_restricted) or d.code in allowed_disciplines
        ],
        "mdr_categories": [
            {"code": c.code, "name": c.name_e or c.name_p or ""}
            for c in db.query(MdrCategory).order_by(MdrCategory.code).all()
        ],
        "phases": [
            {"code": p.ph_code, "name": p.name_e or p.name_p or ""}
            for p in db.query(Phase).order_by(Phase.ph_code).all()
        ],
        "packages": [
            {
                "code": p.package_code,
                "name": p.name_e or p.name_p or "",
                "name_e": p.name_e or p.name_p or "",
                "name_p": p.name_p or p.name_e or "",
                "discipline_code": p.discipline_code,
            }
            for p in db.query(Package).all()
            if (not disciplines_restricted) or p.discipline_code in allowed_disciplines
        ],
        "blocks": [
            {"code": b.code, "name": b.name_e or "", "project_code": b.project_code}
            for b in db.query(Block).all()
            if (not projects_restricted) or b.project_code in allowed_projects
        ],
        "levels": [l.code for l in db.query(Level.code).order_by(Level.code).all()],
    }
    return data


@router.get("/next-serial")
def get_next_serial_preview(
    project_code: str,
    mdr_code: str,
    phase: str,
    discipline: str,
    pkg: str,
    block: str,
    level: str,
    subject_e: Optional[str] = None,
    subject_p: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    """?????? ????? ???? ?? ?? ??? ????? ????? ?????"""
    enforce_scope_access(
        db,
        user,
        project_code=project_code,
        discipline_code=discipline,
    )
    try:
        subject_key = _subject_key_for_coding(subject_e, subject_p)
        if not subject_key:
            subjectless_doc = mdr_service.find_subjectless_document_by_scope(
                db,
                project_code=str(project_code or "").strip().upper(),
                mdr_code=str(mdr_code or "").strip().upper(),
                phase_code=str(phase or "").strip().upper(),
                discipline_code=str(discipline or "").strip().upper(),
                package_code=str(pkg or "").strip().upper(),
                block=str(block or "").strip().upper(),
                level_code=str(level or "").strip().upper(),
            )
            if subjectless_doc:
                prefix, suffix = docnum_service.build_doc_number_parts(
                    project_code=project_code,
                    mdr_code=mdr_code,
                    phase_code=phase,
                    discipline_code=discipline,
                    pkg_code=pkg,
                    block=block,
                    level=level,
                )
                serial = _extract_serial_from_doc_number(subjectless_doc.doc_number, prefix, suffix) or "01"
                return {
                    "serial": serial,
                    "full_doc": subjectless_doc.doc_number,
                    "existing": True,
                    "existing_document_id": subjectless_doc.id,
                }

            doc_num, serial = docnum_service.generate_subjectless_doc_number(
                db,
                project_code=project_code,
                mdr_code=mdr_code,
                phase_code=phase,
                discipline_code=discipline,
                pkg_code=pkg,
                block=block,
                level=level,
                start_serial=1,
            )
            return {
                "serial": serial,
                "full_doc": doc_num,
                "existing": False,
                "existing_document_id": None,
            }

        existing_meta_doc = None
        if subject_key:
            existing_meta_doc = mdr_service.find_document_by_metadata_key(
                db,
                project_code=str(project_code or "").strip().upper(),
                mdr_code=str(mdr_code or "").strip().upper(),
                phase_code=str(phase or "").strip().upper(),
                discipline_code=str(discipline or "").strip().upper(),
                package_code=str(pkg or "").strip().upper(),
                block=str(block or "").strip().upper(),
                level_code=str(level or "").strip().upper(),
                subject=subject_key,
            )
        if existing_meta_doc:
            prefix, suffix = docnum_service.build_doc_number_parts(
                project_code=project_code,
                mdr_code=mdr_code,
                phase_code=phase,
                discipline_code=discipline,
                pkg_code=pkg,
                block=block,
                level=level,
            )
            serial = _extract_serial_from_doc_number(existing_meta_doc.doc_number, prefix, suffix) or ""
            return {
                "serial": serial,
                "full_doc": existing_meta_doc.doc_number,
                "existing": True,
                "existing_document_id": existing_meta_doc.id,
            }

        doc_num, serial = docnum_service.generate_next_doc_number(
            db,
            project_code=project_code,
            mdr_code=mdr_code,
            phase_code=phase,
            discipline_code=discipline,
            pkg_code=pkg,
            block=block,
            level=level,
            subject_p=subject_key,
        )
        return {
            "serial": serial,
            "full_doc": doc_num,
            "existing": False,
            "existing_document_id": None,
        }
    except Exception as e:
        print(f"Serial Error: {e}")
        return {"serial": "01", "full_doc": "", "existing": False, "existing_document_id": None}
