# app/services/archive_service.py
from __future__ import annotations

import os
import re
from typing import Any
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from fastapi import UploadFile, HTTPException

from app.api.dependencies import enforce_scope_access, has_permission_for_user
from app.db.models import (
    ArchiveFile,
    DocumentActivity,
    DocumentComment,
    DocumentRelation,
    DocumentRevision,
    DocumentTag,
    DocumentTagAssignment,
    MdrDocument,
    Transmittal,
    TransmittalDoc,
)
from app.services import docnum_service, folder_service, mdr_service
from app.services.access_control import resolve_effective_access
from app.services.document_activity_service import (
    log_document_activity,
    serialize_document_snapshot,
)
from app.services.storage import StorageManager
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import enqueue_archive_mirror_job, resolve_mirror_enqueue_plan

# ---------------------------------------------------------
# 1. Helper: Calculate Next Revision
# ---------------------------------------------------------
def _calculate_next_revision(current_rev: str) -> str:
    if not current_rev: return "00"
    if current_rev.isdigit():
        try: return f"{int(current_rev) + 1:02d}"
        except: pass
    if len(current_rev) == 1 and current_rev.isalpha():
        if ord(current_rev.upper()) < ord('Z'):
            return chr(ord(current_rev.upper()) + 1)
    return current_rev

# ---------------------------------------------------------
# 2. Helper: Parse Document Code for Components
# ---------------------------------------------------------
def _parse_doc_code(doc_number: str) -> dict | None:
    """
    تجزیه کد سند برای استخراج اجزا.
    فرمت استاندارد: PROJECT-MDR+PHASE+PKG+SERIAL-BLOCK+LEVEL
    مثال: T202-ECAR0101-TGEN
    """
    if not doc_number:
        return None

    try:
        parts = str(doc_number).strip().upper().split("-")
        if len(parts) < 3:
            return None

        project_code = parts[0].strip()
        middle = parts[1].strip()  # ECAR0101
        suffix = parts[2].strip()  # TGEN

        if not project_code or len(middle) < 3 or len(suffix) < 2:
            return None

        mdr_c = middle[0]
        phase_c = middle[1]

        # Format after MDR+Phase is usually PKG + SERIAL(2).
        core = middle[2:]
        serial_match = re.search(r"(\d{2})$", core)
        serial_c = serial_match.group(1) if serial_match else ""
        pkg_full = core[:-2] if serial_match else core
        pkg_full = pkg_full or core or "00"
        disc_match = re.match(r"^([A-Z]+?)(\d.*)$", pkg_full)
        if disc_match:
            disc_c = disc_match.group(1)
            pkg_c = disc_match.group(2)
        else:
            disc_c = pkg_full[:2] if len(pkg_full) >= 2 else "GN"
            pkg_c = pkg_full
        block_c = suffix[0]
        level_c = suffix[1:] or "GEN"

        return {
            "project_code": project_code,
            "mdr_code": mdr_c,
            "phase_code": phase_c,
            "discipline_code": disc_c,
            "package_code": pkg_c,
            "serial": serial_c,
            "block": block_c,
            "level_code": level_c,
        }
    except Exception as e:
        print(f"Error parsing doc code: {e}")
        return None


def _normalize_archive_file_kind(value: str | None) -> str:
    kind = str(value or "").strip().lower()
    if kind in {"pdf", "native"}:
        return kind
    return "pdf"


def _canonical_subject_text(subject_e: str | None, subject_p: str | None) -> str:
    p = str(subject_p or "").strip()
    if p:
        return p
    return str(subject_e or "").strip()


def _subject_pair_for_titles(subject_e: str | None, subject_p: str | None) -> tuple[str, str]:
    subject_value = _canonical_subject_text(subject_e, subject_p)
    return subject_value, subject_value


def _subject_storage(subject_e: str | None, subject_p: str | None) -> str:
    return _canonical_subject_text(subject_e, subject_p)


def _refresh_doc_titles_from_subjects(doc: MdrDocument, db: Session, subject_e: str | None, subject_p: str | None) -> None:
    title_e, title_p = _subject_pair_for_titles(subject_e, subject_p)
    if not title_e and not title_p:
        return
    full_e, full_p = mdr_service.build_document_titles(
        db,
        discipline_code=str(doc.discipline_code or "").strip().upper(),
        package_code=str(doc.package_code or "").strip().upper(),
        block_code=str(doc.block or "").strip().upper(),
        level_code=str(doc.level_code or "").strip().upper(),
        subject_e=title_e,
        subject_p=title_p,
    )
    doc.doc_title_e = full_e
    doc.doc_title_p = full_p
    doc.subject = _subject_storage(title_e, title_p)


def _scope_subjectless_existing_from_meta(db: Session, meta_data: dict) -> MdrDocument | None:
    return mdr_service.find_subjectless_document_by_scope(
        db,
        project_code=str(meta_data.get("project_code") or "").strip().upper(),
        mdr_code=str(meta_data.get("mdr_code") or "X").strip().upper() or "X",
        phase_code=str(meta_data.get("phase") or "X").strip().upper() or "X",
        discipline_code=str(meta_data.get("discipline") or "XX").strip().upper() or "XX",
        package_code=str(meta_data.get("package") or "").strip().upper(),
        block=str(meta_data.get("block") or "").strip().upper(),
        level_code=str(meta_data.get("level") or "GEN").strip().upper() or "GEN",
    )


def _subjectless_expected_doc_number_from_meta(db: Session, meta_data: dict) -> str:
    doc_number, _ = docnum_service.generate_subjectless_doc_number(
        db,
        project_code=str(meta_data.get("project_code") or "").strip().upper(),
        mdr_code=str(meta_data.get("mdr_code") or "X").strip().upper() or "X",
        phase_code=str(meta_data.get("phase") or "X").strip().upper() or "X",
        discipline_code=str(meta_data.get("discipline") or "XX").strip().upper() or "XX",
        pkg_code=str(meta_data.get("package") or "").strip().upper(),
        block=str(meta_data.get("block") or "").strip().upper(),
        level=str(meta_data.get("level") or "GEN").strip().upper() or "GEN",
        start_serial=1,
    )
    return str(doc_number or "").strip().upper()

# ---------------------------------------------------------
# 3. Get Document Info (Main Logic Updated)
# ---------------------------------------------------------
def get_document_status_info(db: Session, doc_number: str, subject_e: str = "", subject_p: str = ""):
    """
    Return document status only (no auto-create side effect).
    """
    doc_number = str(doc_number or "").strip().upper()
    parsed_doc = _parse_doc_code(doc_number)
    if not doc_number:
        return {
            "exists": False,
            "can_register": False,
            "msg": "Document number is empty.",
            "parsed": None,
        }

    doc = (
        db.query(MdrDocument)
        .filter(
            MdrDocument.doc_number == doc_number,
            MdrDocument.deleted_at.is_(None),
        )
        .first()
    )
    if not doc:
        return {
            "exists": False,
            "can_register": bool(parsed_doc),
            "msg": "Document not found in MDR registry.",
            "parsed": parsed_doc,
        }

    last_rev = (
        db.query(DocumentRevision)
        .filter(DocumentRevision.document_id == doc.id)
        .order_by(desc(DocumentRevision.created_at))
        .first()
    )

    current_rev_code = last_rev.revision if last_rev else "N/A"
    current_status = last_rev.status if last_rev else "Registered"
    suggested = _calculate_next_revision(last_rev.revision) if last_rev else "00"

    return {
        "exists": True,
        "document_id": doc.id,
        "doc_number": doc.doc_number,
        "title": doc.doc_title_e or doc.subject or "Untitled",
        "last_revision": current_rev_code,
        "last_status": current_status,
        "next_revision_suggestion": suggested,
        "msg_success": None,
        "is_new_document": False,
        "can_register": False,
        "parsed": {
            "project_code": doc.project_code,
            "mdr_code": doc.mdr_code,
            "phase_code": doc.phase_code,
            "discipline_code": doc.discipline_code,
            "package_code": doc.package_code,
            "serial": (parsed_doc or {}).get("serial", ""),
            "block": doc.block,
            "level_code": doc.level_code,
        },
    }


def _archive_file_sort_key(row: ArchiveFile | None) -> tuple[str, str, int]:
    if not row:
        return ("", "", 0)
    return (
        row.uploaded_at.isoformat() if row.uploaded_at else "",
        row.revision or "",
        int(row.id or 0),
    )


def _normalize_tag_name(name: str | None) -> str:
    return " ".join(str(name or "").strip().split())


def _preview_supported(row: ArchiveFile | None) -> bool:
    if not row or row.deleted_at is not None:
        return False
    mime_type = str(row.mime_type or row.detected_mime or "").strip().lower()
    return mime_type.startswith("image/") or mime_type in {"application/pdf", "application/x-pdf"} or str(
        row.file_kind or ""
    ).strip().lower() == "pdf"


def normalize_user_role(user: Any) -> str:
    try:
        return str(resolve_effective_access(user).effective_role or "").strip().lower()
    except Exception:
        return str(getattr(user, "role", "") or "").strip().lower()


def resolve_document_latest_revision(document: MdrDocument | None) -> DocumentRevision | None:
    if not document:
        return None
    revisions = list(document.revisions or [])
    if not revisions:
        return None
    revisions.sort(
        key=lambda row: (
            row.created_at.isoformat() if row.created_at else "",
            int(row.id or 0),
        ),
        reverse=True,
    )
    return revisions[0]


def resolve_document_preview_file(document: MdrDocument | None) -> ArchiveFile | None:
    if not document:
        return None
    files: list[ArchiveFile] = []
    for revision in document.revisions or []:
        for archive_file in revision.archive_files or []:
            if archive_file.deleted_at is None:
                files.append(archive_file)
    if not files:
        return None
    pdf_candidates = [
        row
        for row in files
        if str(row.mime_type or row.detected_mime or "").strip().lower() in {"application/pdf", "application/x-pdf"}
        or str(row.file_kind or "").strip().lower() == "pdf"
    ]
    image_candidates = [
        row for row in files if str(row.mime_type or row.detected_mime or "").strip().lower().startswith("image/")
    ]
    if pdf_candidates:
        pdf_candidates.sort(key=_archive_file_sort_key, reverse=True)
        return pdf_candidates[0]
    if image_candidates:
        image_candidates.sort(key=_archive_file_sort_key, reverse=True)
        return image_candidates[0]
    return None


def _latest_live_file(document: MdrDocument | None) -> ArchiveFile | None:
    if not document:
        return None
    files: list[ArchiveFile] = []
    for revision in document.revisions or []:
        for archive_file in revision.archive_files or []:
            if archive_file.deleted_at is None:
                files.append(archive_file)
    if not files:
        return None
    files.sort(key=_archive_file_sort_key, reverse=True)
    return files[0]


def _comment_payload_tree(rows: list[DocumentComment]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            row.created_at.isoformat() if row.created_at else "",
            int(row.id or 0),
        ),
    )
    items: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in ordered:
        payload = {
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
        items[payload["id"]] = payload
        parent_id = payload["parent_id"]
        if parent_id and parent_id in items:
            items[parent_id]["children"].append(payload)
        else:
            roots.append(payload)
    return roots


def _document_capabilities(db: Session, document: MdrDocument, user: Any) -> dict[str, bool]:
    is_deleted = bool(document.deleted_at)
    return {
        "can_edit": bool(has_permission_for_user(db, user, "documents:update") and not is_deleted),
        "can_delete": bool(has_permission_for_user(db, user, "documents:delete") and not is_deleted),
        "can_comment": bool(has_permission_for_user(db, user, "documents:comment_create") and not is_deleted),
        "can_manage_relations": bool(
            has_permission_for_user(db, user, "documents:relation_manage") and not is_deleted
        ),
        "can_manage_tags": bool(has_permission_for_user(db, user, "documents:tag_manage") and not is_deleted),
    }


def get_document_detail(db: Session, document_id: int, user: Any) -> dict[str, Any]:
    document = (
        db.query(MdrDocument)
        .options(
            joinedload(MdrDocument.project),
            joinedload(MdrDocument.phase),
            joinedload(MdrDocument.discipline),
            joinedload(MdrDocument.package),
            joinedload(MdrDocument.level),
            joinedload(MdrDocument.updated_by),
            joinedload(MdrDocument.deleted_by),
            joinedload(MdrDocument.revisions).joinedload(DocumentRevision.archive_files),
            joinedload(MdrDocument.comments),
            joinedload(MdrDocument.activities),
            joinedload(MdrDocument.outgoing_relations).joinedload(DocumentRelation.target_document),
            joinedload(MdrDocument.incoming_relations).joinedload(DocumentRelation.source_document),
            joinedload(MdrDocument.tag_assignments).joinedload(DocumentTagAssignment.tag),
        )
        .filter(MdrDocument.id == int(document_id))
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
    latest_revision = resolve_document_latest_revision(document)
    preview_file = resolve_document_preview_file(document)
    latest_file = _latest_live_file(document)
    revisions = sorted(
        list(document.revisions or []),
        key=lambda row: (
            row.created_at.isoformat() if row.created_at else "",
            int(row.id or 0),
        ),
        reverse=True,
    )
    revision_payload = []
    for revision in revisions:
        files = [
            row
            for row in sorted(revision.archive_files or [], key=_archive_file_sort_key, reverse=True)
            if row.deleted_at is None
        ]
        revision_payload.append(
            {
                "revision_id": int(revision.id or 0),
                "revision": revision.revision,
                "status": revision.status,
                "created_at": revision.created_at.isoformat() if revision.created_at else None,
                "files": [
                    {
                        "id": int(row.id or 0),
                        "name": row.original_name,
                        "mime_type": row.mime_type,
                        "detected_mime": row.detected_mime,
                        "size_bytes": row.size_bytes,
                        "file_kind": row.file_kind,
                        "status": row.status,
                        "is_primary": bool(row.is_primary),
                        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
                    }
                    for row in files
                ],
            }
        )
    return {
        "document": document,
        "latest_revision": latest_revision,
        "latest_files": {
            "preview": preview_file,
            "latest": latest_file,
        },
        "preview_meta": {
            "has_preview": bool(preview_file),
            "supported": _preview_supported(preview_file),
            "file_id": int(preview_file.id or 0) if preview_file else None,
            "mime_type": preview_file.mime_type if preview_file else None,
            "detected_mime": preview_file.detected_mime if preview_file else None,
            "name": preview_file.original_name if preview_file else None,
        },
        "counts": {
            "revisions": len(revisions),
            "comments": len(document.comments or []),
            "activities": len(document.activities or []),
            "relations": len(document.outgoing_relations or []) + len(document.incoming_relations or []),
            "tags": len(document.tag_assignments or []),
        },
        "capabilities": _document_capabilities(db, document, user),
        "is_deleted": bool(document.deleted_at),
        "revisions": revision_payload,
        "comments": _comment_payload_tree(list(document.comments or [])),
        "activities": sorted(
            list(document.activities or []),
            key=lambda row: (
                row.created_at.isoformat() if row.created_at else "",
                int(row.id or 0),
            ),
            reverse=True,
        ),
        "relations": {
            "outgoing": [
                row for row in document.outgoing_relations or [] if getattr(row.target_document, "deleted_at", None) is None
            ],
            "incoming": [
                row for row in document.incoming_relations or [] if getattr(row.source_document, "deleted_at", None) is None
            ],
        },
        "tags": [row for row in document.tag_assignments or [] if getattr(row.tag, "id", None)],
        "transmittals": list_document_transmittals(db, int(document.id or 0), user=user, skip=0, limit=20)["data"],
    }


def update_document_metadata(db: Session, document_id: int, updates: dict[str, Any], user: Any) -> MdrDocument:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    allowed_fields = {
        "doc_title_e",
        "doc_title_p",
        "subject",
        "phase_code",
        "package_code",
        "block",
        "level_code",
        "notes",
    }
    before = serialize_document_snapshot(document)
    for key, value in (updates or {}).items():
        if key not in allowed_fields:
            continue
        setattr(document, key, str(value).strip() if isinstance(value, str) else value)
    document.updated_at = datetime.utcnow()
    document.updated_by_id = getattr(user, "id", None)
    after = serialize_document_snapshot(document)
    log_document_activity(
        db,
        int(document.id or 0),
        "metadata_updated",
        user,
        before_data=before,
        after_data=after,
    )
    db.commit()
    db.refresh(document)
    return document


def soft_delete_document(db: Session, document_id: int, user: Any) -> MdrDocument:
    document = (
        db.query(MdrDocument)
        .options(joinedload(MdrDocument.revisions).joinedload(DocumentRevision.archive_files))
        .filter(MdrDocument.id == int(document_id))
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
    if document.deleted_at:
        return document
    before = serialize_document_snapshot(document)
    now = datetime.utcnow()
    document.deleted_at = now
    document.deleted_by_id = getattr(user, "id", None)
    document.updated_at = now
    document.updated_by_id = getattr(user, "id", None)
    for revision in document.revisions or []:
        for archive_file in revision.archive_files or []:
            if archive_file.deleted_at is None:
                archive_file.deleted_at = now
    log_document_activity(
        db,
        int(document.id or 0),
        "deleted",
        user,
        before_data=before,
        after_data=serialize_document_snapshot(document),
    )
    db.commit()
    db.refresh(document)
    return document


def apply_transmittal_scope_filters(query: Any, user: Any, db: Session) -> Any:
    from app.api.dependencies import apply_scope_query_filters

    return apply_scope_query_filters(
        query,
        db,
        user,
        project_column=Transmittal.project_code,
    )


def list_document_transmittals(
    db: Session,
    document_id: int,
    *,
    user: Any | None = None,
    skip: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if user is not None:
        enforce_scope_access(
            db,
            user,
            project_code=document.project_code,
            discipline_code=document.discipline_code,
        )
    query = (
        db.query(Transmittal)
        .join(TransmittalDoc, TransmittalDoc.transmittal_id == Transmittal.id)
        .filter(TransmittalDoc.document_code == document.doc_number)
        .order_by(Transmittal.created_at.desc())
    )
    if user is not None:
        query = apply_transmittal_scope_filters(query, user, db)
    total = query.count()
    rows = query.offset(max(0, int(skip or 0))).limit(max(1, int(limit or 20))).all()
    return {
        "ok": True,
        "total": total,
        "data": [
            {
                "id": row.id,
                "transmittal_no": row.id,
                "project_code": row.project_code,
                "status": str(getattr(row, "lifecycle_status", None) or ("issued" if row.send_date else "draft")).lower(),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "sender": row.sender,
                "receiver": row.receiver,
            }
            for row in rows
        ],
    }


def list_document_activity(db: Session, document_id: int, user: Any, skip: int = 0, limit: int = 50) -> dict[str, Any]:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    query = db.query(DocumentActivity).filter(DocumentActivity.document_id == int(document_id))
    total = query.count()
    rows = (
        query.order_by(DocumentActivity.created_at.desc(), DocumentActivity.id.desc())
        .offset(max(0, int(skip or 0)))
        .limit(max(1, int(limit or 50)))
        .all()
    )
    return {"ok": True, "total": total, "data": rows}


def list_document_comments(db: Session, document_id: int, user: Any) -> list[DocumentComment]:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    return (
        db.query(DocumentComment)
        .filter(DocumentComment.document_id == int(document_id))
        .order_by(DocumentComment.created_at.asc(), DocumentComment.id.asc())
        .all()
    )


def create_document_comment(
    db: Session,
    document_id: int,
    body: str,
    user: Any,
    parent_id: int | None = None,
) -> DocumentComment:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    body_text = str(body or "").strip()
    if not body_text:
        raise HTTPException(status_code=400, detail="Comment body is required")
    parent = None
    if parent_id:
        parent = (
            db.query(DocumentComment)
            .filter(
                DocumentComment.id == int(parent_id),
                DocumentComment.document_id == int(document_id),
            )
            .first()
        )
        if not parent:
            raise HTTPException(status_code=404, detail="Parent comment not found")
    row = DocumentComment(
        document_id=int(document_id),
        parent_id=int(parent_id) if parent else None,
        author_id=getattr(user, "id", None),
        author_name=getattr(user, "full_name", None) or getattr(user, "email", None),
        author_email=getattr(user, "email", None),
        body=body_text,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "comment_added",
        user,
        detail=f"comment:{int(row.id or 0)}",
        after_data={"comment_id": int(row.id or 0), "parent_id": int(row.parent_id or 0) or None},
    )
    db.commit()
    db.refresh(row)
    return row


def update_document_comment(db: Session, document_id: int, comment_id: int, body: str, user: Any) -> DocumentComment:
    row = (
        db.query(DocumentComment)
        .filter(DocumentComment.id == int(comment_id), DocumentComment.document_id == int(document_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    if row.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted comment cannot be updated")
    body_text = str(body or "").strip()
    if not body_text:
        raise HTTPException(status_code=400, detail="Comment body is required")
    user_id = int(getattr(user, "id", 0) or 0)
    if normalize_user_role(user) != "admin" and user_id != int(row.author_id or 0):
        raise HTTPException(status_code=403, detail="Only the author can update this comment")
    before = {"body": row.body, "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None}
    row.body = body_text
    row.updated_at = datetime.utcnow()
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "comment_updated",
        user,
        detail=f"comment:{int(row.id or 0)}",
        before_data=before,
        after_data={"body": row.body},
    )
    db.commit()
    db.refresh(row)
    return row


def delete_document_comment(db: Session, document_id: int, comment_id: int, user: Any) -> DocumentComment:
    row = (
        db.query(DocumentComment)
        .filter(DocumentComment.id == int(comment_id), DocumentComment.document_id == int(document_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    user_id = int(getattr(user, "id", 0) or 0)
    if normalize_user_role(user) != "admin" and user_id != int(row.author_id or 0):
        raise HTTPException(status_code=403, detail="Only the author can delete this comment")
    row.deleted_at = datetime.utcnow()
    row.updated_at = row.deleted_at
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "comment_deleted",
        user,
        detail=f"comment:{int(row.id or 0)}",
        after_data={"comment_id": int(row.id or 0)},
    )
    db.commit()
    db.refresh(row)
    return row


def list_document_relations(db: Session, document_id: int, user: Any) -> dict[str, list[DocumentRelation]]:
    document = (
        db.query(MdrDocument)
        .options(
            joinedload(MdrDocument.outgoing_relations).joinedload(DocumentRelation.target_document),
            joinedload(MdrDocument.incoming_relations).joinedload(DocumentRelation.source_document),
        )
        .filter(MdrDocument.id == int(document_id))
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
    return {
        "outgoing": [
            row for row in document.outgoing_relations or [] if getattr(row.target_document, "deleted_at", None) is None
        ],
        "incoming": [
            row for row in document.incoming_relations or [] if getattr(row.source_document, "deleted_at", None) is None
        ],
    }


def create_document_relation(
    db: Session,
    document_id: int,
    target_document_id: int,
    relation_type: str,
    notes: str | None,
    user: Any,
) -> DocumentRelation:
    source_document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not source_document:
        raise HTTPException(status_code=404, detail="Document not found")
    target_document = db.query(MdrDocument).filter(MdrDocument.id == int(target_document_id)).first()
    if not target_document or target_document.deleted_at:
        raise HTTPException(status_code=404, detail="Target document not found")
    enforce_scope_access(
        db,
        user,
        project_code=source_document.project_code,
        discipline_code=source_document.discipline_code,
    )
    enforce_scope_access(
        db,
        user,
        project_code=target_document.project_code,
        discipline_code=target_document.discipline_code,
    )
    if source_document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    if int(document_id) == int(target_document_id):
        raise HTTPException(status_code=400, detail="Cannot relate a document to itself")
    normalized_type = str(relation_type or "").strip().lower() or "related"
    existing = (
        db.query(DocumentRelation)
        .filter(
            DocumentRelation.source_document_id == int(document_id),
            DocumentRelation.target_document_id == int(target_document_id),
            DocumentRelation.relation_type == normalized_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Relation already exists")
    row = DocumentRelation(
        source_document_id=int(document_id),
        target_document_id=int(target_document_id),
        relation_type=normalized_type,
        notes=str(notes or "").strip() or None,
        created_by_id=getattr(user, "id", None),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "relation_added",
        user,
        detail=f"relation:{int(row.id or 0)}",
        after_data={"target_document_id": int(target_document_id), "relation_type": normalized_type},
    )
    db.commit()
    db.refresh(row)
    return row


def delete_document_relation(db: Session, document_id: int, relation_id: int, user: Any) -> None:
    row = (
        db.query(DocumentRelation)
        .filter(DocumentRelation.id == int(relation_id), DocumentRelation.source_document_id == int(document_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Relation not found")
    source_document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not source_document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=source_document.project_code,
        discipline_code=source_document.discipline_code,
    )
    if source_document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    db.delete(row)
    log_document_activity(
        db,
        int(document_id),
        "relation_removed",
        user,
        detail=f"relation:{int(relation_id)}",
    )
    db.commit()


def list_tags(db: Session) -> list[DocumentTag]:
    return db.query(DocumentTag).order_by(DocumentTag.name.asc(), DocumentTag.id.asc()).all()


def create_tag(db: Session, name: str, color: str | None, user: Any) -> DocumentTag:
    normalized_name = _normalize_tag_name(name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Tag name is required")
    for row in db.query(DocumentTag).order_by(DocumentTag.id.asc()).all():
        if _normalize_tag_name(row.name).lower() == normalized_name.lower():
            return row
    row = DocumentTag(name=normalized_name, color=str(color or "").strip() or None, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_document_tags(db: Session, document_id: int, user: Any) -> list[DocumentTagAssignment]:
    document = (
        db.query(MdrDocument)
        .options(joinedload(MdrDocument.tag_assignments).joinedload(DocumentTagAssignment.tag))
        .filter(MdrDocument.id == int(document_id))
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
    return list(document.tag_assignments or [])


def assign_tag_to_document(
    db: Session,
    document_id: int,
    tag_name: str | None,
    tag_id: int | None,
    color: str | None,
    user: Any,
) -> DocumentTagAssignment:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    target_tag: DocumentTag | None = None
    if tag_id:
        target_tag = db.query(DocumentTag).filter(DocumentTag.id == int(tag_id)).first()
    if not target_tag:
        target_tag = create_tag(db, str(tag_name or ""), color, user)
    existing = (
        db.query(DocumentTagAssignment)
        .filter(
            DocumentTagAssignment.document_id == int(document_id),
            DocumentTagAssignment.tag_id == int(target_tag.id or 0),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Tag already assigned")
    row = DocumentTagAssignment(
        document_id=int(document_id),
        tag_id=int(target_tag.id or 0),
        assigned_by_id=getattr(user, "id", None),
        assigned_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    log_document_activity(
        db,
        int(document_id),
        "tag_added",
        user,
        detail=f"tag:{int(target_tag.id or 0)}",
        after_data={"tag_id": int(target_tag.id or 0), "tag_name": target_tag.name},
    )
    db.commit()
    db.refresh(row)
    return row


def remove_tag_from_document(db: Session, document_id: int, tag_id: int, user: Any) -> None:
    document = db.query(MdrDocument).filter(MdrDocument.id == int(document_id)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_scope_access(
        db,
        user,
        project_code=document.project_code,
        discipline_code=document.discipline_code,
    )
    if document.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted document is read-only")
    row = (
        db.query(DocumentTagAssignment)
        .filter(
            DocumentTagAssignment.document_id == int(document_id),
            DocumentTagAssignment.tag_id == int(tag_id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tag assignment not found")
    db.delete(row)
    log_document_activity(
        db,
        int(document_id),
        "tag_removed",
        user,
        detail=f"tag:{int(tag_id)}",
    )
    db.commit()
# ---------------------------------------------------------
# 4. Main Upload Logic
# ---------------------------------------------------------
def save_upload_file(
    db: Session,
    file: UploadFile,
    document_id: int,
    revision_code: str,
    status_code: str = "Uploaded",
    file_kind: str = "pdf",
    is_primary: bool = True,
    companion_file_id: int | None = None,
    openproject_work_package_id: int | None = None,
    commit: bool = True,
    is_admin: bool = False,
    actor: Any | None = None,
    log_revision: bool = True,
) -> ArchiveFile:
    del is_admin
    storage = StorageManager(db)

    doc = db.query(MdrDocument).filter(MdrDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    rev = db.query(DocumentRevision).filter(
        DocumentRevision.document_id == document_id,
        DocumentRevision.revision == revision_code,
    ).first()
    if rev:
        rev.status = status_code
        rev.created_at = datetime.utcnow()
    else:
        rev = DocumentRevision(
            document_id=document_id,
            revision=revision_code,
            status=status_code,
            notes="Created via Upload",
        )
        db.add(rev)
        db.flush()

    normalized_kind = _normalize_archive_file_kind(file_kind)

    proj_name = doc.project.name_e if doc.project else doc.project_code
    mdr_folder = folder_service.get_mdr_folder_name(db, doc.mdr_code)

    phase_name = doc.phase_code
    if doc.phase:
        phase_name = doc.phase.name_e or doc.phase_code

    disc_name = "General"
    disc_code = doc.discipline_code or "GN"
    if doc.discipline:
        disc_name = doc.discipline.name_e

    pkg_name = "General"
    pkg_code = doc.package_code or "00"
    if doc.package:
        pkg_name = doc.package.name_e or doc.package.name_p or doc.package_code

    _, file_extension = os.path.splitext(file.filename)
    raw_title = doc.doc_title_e or doc.subject or "Untitled"
    safe_title = folder_service.safe_name(raw_title)
    if len(safe_title) > 100:
        safe_title = safe_title[:100]

    clean_name = f"{doc.doc_number}_{safe_title}_Rev{revision_code}{file_extension}"

    # Check if WebDAV mode
    if storage._is_webdav_primary_mode():
        # WebDAV mode: build remote path and upload directly
        pkg_folder = f"{pkg_code} - {pkg_name}"
        remote_path = f"/{proj_name}/{mdr_folder}/{phase_name}/{disc_code}/{pkg_folder}/{normalized_kind}/{clean_name}"
        saved = storage.save_upload_to_webdav(
            file=file,
            remote_relative_path=remote_path,
            file_kind=normalized_kind,
        )
    else:
        # Mount/local mode: use existing logic
        target_folder = storage.get_mdr_path(
            project_code=doc.project_code,
            project_name=proj_name,
            mdr_folder_name=mdr_folder,
            phase_name=phase_name,
            phase_code=doc.phase_code or phase_name,
            disc_name=disc_name,
            disc_code=disc_code,
            pkg_name=pkg_name,
            pkg_code=pkg_code,
            package_name=pkg_name,
            file_kind=normalized_kind,
        )
        saved = storage.save_upload_secure(
            file=file,
            destination_folder=target_folder,
            new_name=clean_name,
            file_kind=normalized_kind,
        )

    rev.file_path = saved.stored_path
    rev.file_name = clean_name

    integrations = get_storage_integrations(db)
    mirror_plan = resolve_mirror_enqueue_plan(integrations)
    mirror_provider = str(mirror_plan.get("provider") or "")
    mirror_status = str(mirror_plan.get("status") or "disabled")

    archive_entry = ArchiveFile(
        revision_id=rev.id,
        original_name=clean_name,
        stored_path=saved.stored_path,
        mime_type=saved.declared_mime or file.content_type,
        detected_mime=saved.detected_mime,
        validation_status=saved.validation_status,
        sha256=saved.sha256,
        size_bytes=saved.size_bytes,
        storage_backend="nextcloud" if saved.stored_path.startswith("webdav://") else storage.resolve_storage_backend_for_path(saved.stored_path),
        gdrive_file_id=None,
        mirror_provider=mirror_provider or None,
        mirror_remote_id=None,
        mirror_remote_url=None,
        mirror_status=mirror_status,
        mirror_updated_at=datetime.utcnow(),
        file_kind=normalized_kind,
        is_primary=bool(is_primary),
        companion_file_id=companion_file_id,
        revision=revision_code,
        status=status_code,
        uploaded_by=getattr(actor, "email", None) or "User",
        uploaded_at=datetime.utcnow(),
    )

    db.add(archive_entry)
    db.flush()
    if log_revision:
        log_document_activity(
            db,
            int(document_id),
            "revision_uploaded",
            actor,
            detail=f"revision:{revision_code}",
            after_data={
                "revision": revision_code,
                "file_id": int(archive_entry.id or 0),
                "file_kind": normalized_kind,
                "status": status_code,
            },
        )
    if bool(mirror_plan.get("enqueue")):
        enqueue_archive_mirror_job(
            db,
            archive_file_id=archive_entry.id,
            work_package_id=openproject_work_package_id,
        )

    if commit:
        db.commit()
        db.refresh(archive_entry)

    return archive_entry

def save_dual_upload_files(
    db: Session,
    *,
    pdf_file: UploadFile,
    native_file: UploadFile,
    document_id: int,
    revision_code: str,
    status_code: str = "Uploaded",
    openproject_work_package_id: int | None = None,
    is_admin: bool = False,
    actor: Any | None = None,
) -> tuple[ArchiveFile, ArchiveFile]:
    """
    Save PDF + Native files on the same revision and cross-link them as companions.
    """
    pdf_entry: ArchiveFile | None = None
    native_entry: ArchiveFile | None = None
    saved_paths: list[str] = []
    try:
        pdf_entry = save_upload_file(
            db=db,
            file=pdf_file,
            document_id=document_id,
            revision_code=revision_code,
            status_code=status_code,
            file_kind="pdf",
            is_primary=True,
            openproject_work_package_id=openproject_work_package_id,
            commit=False,
            is_admin=is_admin,
            actor=actor,
            log_revision=False,
        )
        saved_paths.append(pdf_entry.stored_path)

        native_entry = save_upload_file(
            db=db,
            file=native_file,
            document_id=document_id,
            revision_code=revision_code,
            status_code=status_code,
            file_kind="native",
            is_primary=False,
            openproject_work_package_id=openproject_work_package_id,
            commit=False,
            is_admin=is_admin,
            actor=actor,
            log_revision=False,
        )
        saved_paths.append(native_entry.stored_path)

        pdf_entry.companion_file_id = native_entry.id
        native_entry.companion_file_id = pdf_entry.id

        # Keep revision file pointer on the primary (PDF) file.
        revision_row = db.query(DocumentRevision).filter(DocumentRevision.id == pdf_entry.revision_id).first()
        if revision_row:
            revision_row.file_path = pdf_entry.stored_path
            revision_row.file_name = pdf_entry.original_name

        db.commit()
        db.refresh(pdf_entry)
        db.refresh(native_entry)
        log_document_activity(
            db,
            int(document_id),
            "revision_uploaded",
            actor,
            detail=f"revision:{revision_code}",
            after_data={
                "revision": revision_code,
                "pdf_file_id": int(pdf_entry.id or 0),
                "native_file_id": int(native_entry.id or 0),
                "status": status_code,
            },
        )
        db.commit()
        db.refresh(pdf_entry)
        db.refresh(native_entry)
        return pdf_entry, native_entry
    except Exception:
        db.rollback()
        for path in saved_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        raise
# ---------------------------------------------------------
# 5. Full Register & Upload (New Feature)
# ---------------------------------------------------------
def register_and_upload_document(
    db: Session,
    file: UploadFile,
    meta_data: dict, 
    revision_code: str,
    status_code: str,
    file_kind: str = "pdf",
    openproject_work_package_id: int | None = None,
    is_admin: bool = False,
    actor: Any | None = None,
) -> ArchiveFile:
    """
    ثبت کامل مدرک (Master) و آپلود فایل در یک مرحله.
    """
    
    subject_e, subject_p = _subject_pair_for_titles(
        meta_data.get("subject_e"),
        meta_data.get("subject_p"),
    )

    # 1. ابتدا سند را در جدول MDR ثبت می‌کنیم
    existing = db.query(MdrDocument).filter(MdrDocument.doc_number == meta_data['doc_number']).first()
    created_new_document = False
    if not existing and not (subject_e or subject_p):
        subjectless_existing = _scope_subjectless_existing_from_meta(db, meta_data)
        if subjectless_existing:
            doc = subjectless_existing
            db.flush()
            archive_entry = save_upload_file(
                db=db,
                file=file,
                document_id=doc.id,
                revision_code=revision_code,
                status_code=status_code,
                file_kind=file_kind,
                openproject_work_package_id=openproject_work_package_id,
                is_admin=is_admin,
                actor=actor,
            )
            return archive_entry

        normalized_doc_number = str(meta_data.get("doc_number") or "").strip().upper()
        expected_doc_number = _subjectless_expected_doc_number_from_meta(db, meta_data)
        if normalized_doc_number != expected_doc_number:
            raise HTTPException(
                status_code=422,
                detail=f"برای مدرک بدون Subject سریال باید از 01 شروع شود. کد صحیح: {expected_doc_number}",
            )
    
    if existing:
        # اگر کد وجود دارد، از همان استفاده کن
        doc = existing
        # اختیاری: می‌توانیم عنوان‌ها را آپدیت کنیم
        _refresh_doc_titles_from_subjects(
            doc,
            db,
            subject_e,
            subject_p,
        )
    else:
        # ساخت سند جدید
        doc = mdr_service.create_mdr_document(
            db,
            doc_number=meta_data['doc_number'],
            project_code=meta_data['project_code'],
            mdr_code=meta_data['mdr_code'],
            phase_code=meta_data['phase'],
            discipline_code=meta_data['discipline'],
            package_code=meta_data['package'],
            block=meta_data['block'],
            level_code=meta_data['level'],
            title_e=subject_e,
            title_p=subject_p,
            subject=_subject_storage(subject_e, subject_p)
        )
        created_new_document = True
    
    db.flush() # برای گرفتن ID سند
    if created_new_document:
        log_document_activity(
            db,
            int(doc.id or 0),
            "created",
            actor,
            after_data=serialize_document_snapshot(doc),
        )

    # 2. آپلود فایل
    archive_entry = save_upload_file(
        db=db,
        file=file,
        document_id=doc.id,
        revision_code=revision_code,
        status_code=status_code,
        file_kind=file_kind,
        openproject_work_package_id=openproject_work_package_id,
        is_admin=is_admin,
        actor=actor,
    )
    
    return archive_entry


def register_document_metadata(
    db: Session,
    *,
    meta_data: dict,
    actor: Any | None = None,
) -> tuple[MdrDocument, bool]:
    """
    Register only MDR document metadata (no archive upload).
    Returns: (document, created_flag)
    """
    doc_number = str(meta_data.get("doc_number") or "").strip().upper()
    if not doc_number:
        raise HTTPException(status_code=400, detail="Document number is required.")

    existing = db.query(MdrDocument).filter(MdrDocument.doc_number == doc_number).first()
    if existing:
        return existing, False

    subject_e, subject_p = _subject_pair_for_titles(
        meta_data.get("subject_e"),
        meta_data.get("subject_p"),
    )
    if not (subject_e or subject_p):
        subjectless_existing = _scope_subjectless_existing_from_meta(db, meta_data)
        if subjectless_existing:
            return subjectless_existing, False
        expected_doc_number = _subjectless_expected_doc_number_from_meta(db, meta_data)
        if doc_number != expected_doc_number:
            raise HTTPException(
                status_code=422,
                detail=f"برای مدرک بدون Subject سریال باید از 01 شروع شود. کد صحیح: {expected_doc_number}",
            )

    doc = mdr_service.create_mdr_document(
        db,
        doc_number=doc_number,
        project_code=str(meta_data.get("project_code") or "").strip().upper(),
        mdr_code=str(meta_data.get("mdr_code") or "X").strip().upper() or "X",
        phase_code=str(meta_data.get("phase") or "X").strip().upper() or "X",
        discipline_code=str(meta_data.get("discipline") or "XX").strip().upper() or "XX",
        package_code=str(meta_data.get("package") or "").strip().upper(),
        block=str(meta_data.get("block") or "").strip().upper(),
        level_code=str(meta_data.get("level") or "GEN").strip().upper() or "GEN",
        title_e=subject_e,
        title_p=subject_p,
        subject=_subject_storage(subject_e, subject_p),
    )
    db.commit()
    db.refresh(doc)
    log_document_activity(
        db,
        int(doc.id or 0),
        "created",
        actor,
        after_data=serialize_document_snapshot(doc),
    )
    db.commit()
    db.refresh(doc)
    return doc, True


def register_and_upload_dual_document(
    db: Session,
    *,
    pdf_file: UploadFile,
    native_file: UploadFile,
    meta_data: dict,
    revision_code: str,
    status_code: str,
    openproject_work_package_id: int | None = None,
    is_admin: bool = False,
    actor: Any | None = None,
) -> tuple[ArchiveFile, ArchiveFile]:
    """
    Register document metadata (if needed) and upload PDF + Native together.
    """
    subject_e, subject_p = _subject_pair_for_titles(
        meta_data.get("subject_e"),
        meta_data.get("subject_p"),
    )

    existing = db.query(MdrDocument).filter(MdrDocument.doc_number == meta_data["doc_number"]).first()
    created_new_document = False
    if not existing and not (subject_e or subject_p):
        subjectless_existing = _scope_subjectless_existing_from_meta(db, meta_data)
        if subjectless_existing:
            doc = subjectless_existing
            db.flush()
            return save_dual_upload_files(
                db=db,
                pdf_file=pdf_file,
                native_file=native_file,
                document_id=doc.id,
                revision_code=revision_code,
                status_code=status_code,
                openproject_work_package_id=openproject_work_package_id,
                is_admin=is_admin,
                actor=actor,
            )
        normalized_doc_number = str(meta_data.get("doc_number") or "").strip().upper()
        expected_doc_number = _subjectless_expected_doc_number_from_meta(db, meta_data)
        if normalized_doc_number != expected_doc_number:
            raise HTTPException(
                status_code=422,
                detail=f"برای مدرک بدون Subject سریال باید از 01 شروع شود. کد صحیح: {expected_doc_number}",
            )

    if existing:
        doc = existing
        _refresh_doc_titles_from_subjects(
            doc,
            db,
            subject_e,
            subject_p,
        )
    else:
        doc = mdr_service.create_mdr_document(
            db,
            doc_number=meta_data["doc_number"],
            project_code=meta_data["project_code"],
            mdr_code=meta_data["mdr_code"],
            phase_code=meta_data["phase"],
            discipline_code=meta_data["discipline"],
            package_code=meta_data["package"],
            block=meta_data["block"],
            level_code=meta_data["level"],
            title_e=subject_e,
            title_p=subject_p,
            subject=_subject_storage(subject_e, subject_p),
        )
        created_new_document = True

    db.flush()
    if created_new_document:
        log_document_activity(
            db,
            int(doc.id or 0),
            "created",
            actor,
            after_data=serialize_document_snapshot(doc),
        )

    return save_dual_upload_files(
        db=db,
        pdf_file=pdf_file,
        native_file=native_file,
        document_id=doc.id,
        revision_code=revision_code,
        status_code=status_code,
        openproject_work_package_id=openproject_work_package_id,
        is_admin=is_admin,
        actor=actor,
    )


