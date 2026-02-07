from __future__ import annotations

from datetime import datetime, timedelta
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
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
    DocumentRevision,
    Level,
    MdrCategory,
    MdrDocument,
    Package,
    Phase,
    Project,
)
from app.services import archive_service, docnum_service

router = APIRouter(prefix="/archive", tags=["Archive"])


def _file_kind(value: str | None) -> str:
    kind = str(value or "").strip().lower()
    return kind if kind in {"pdf", "native"} else "pdf"


def _revision_file_ids(revision: DocumentRevision | None) -> tuple[int | None, int | None]:
    if not revision:
        return None, None
    pdf_id: int | None = None
    native_id: int | None = None
    for item in revision.archive_files or []:
        if _file_kind(item.file_kind) == "native":
            if native_id is None:
                native_id = item.id
        elif pdf_id is None:
            pdf_id = item.id
    return pdf_id, native_id


def _parse_filter_date(value: str | None, field_name: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid `{field_name}` format (YYYY-MM-DD expected).") from exc


@router.get("/check-status")
async def check_document_status(
    doc_code: str = Query(..., min_length=3),
    subject_e: Optional[str] = Query(None),
    subject_p: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    """????? ????? ??? ? ??????? ?????? ????"""
    return archive_service.get_document_status_info(db, doc_code, subject_e, subject_p)


@router.post("/upload")
async def upload_file(
    document_id: int = Form(...),
    revision: str = Form(...),
    status: str = Form("IFA"),
    file_kind: str = Form("pdf"),
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
            is_admin=user.role == "admin",
        )
        return {
            "ok": True,
            "message": "???? ?? ?????? ????? ??.",
            "file_id": result.id,
            "new_name": result.original_name,
            "revision": result.revision,
        }
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload-dual")
async def upload_dual_files(
    document_id: int = Form(...),
    revision: str = Form(...),
    status: str = Form("IFA"),
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
            is_admin=user.role == "admin",
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
        }
    except Exception as e:
        print(f"Dual Upload Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/register-and-upload")
async def register_and_upload(
    file: UploadFile = File(...),
    revision: str = Form(...),
    status: str = Form("IFA"),
    file_kind: str = Form("pdf"),
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
            "subject_e": subject_e or "",
            "subject_p": subject_p or "",
        }

        result = archive_service.register_and_upload_document(
            db=db,
            file=file,
            meta_data=meta_data,
            revision_code=revision,
            status_code=status,
            file_kind=file_kind,
            is_admin=user.role == "admin",
        )

        return {
            "ok": True,
            "message": "???? ?? ?????? ??? ? ???? ????? ??.",
            "file_id": result.id,
            "doc_number": meta_data["doc_number"],
        }
    except Exception as e:
        print(f"Full Register Error: {e}")
        raise HTTPException(status_code=400, detail=f"??? ?? ??? ???: {str(e)}")


@router.post("/register-and-upload-dual")
async def register_and_upload_dual(
    pdf_file: UploadFile = File(...),
    native_file: UploadFile = File(...),
    revision: str = Form(...),
    status: str = Form("IFA"),
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
            "subject_e": subject_e or "",
            "subject_p": subject_p or "",
        }

        pdf_entry, native_entry = archive_service.register_and_upload_dual_document(
            db=db,
            pdf_file=pdf_file,
            native_file=native_file,
            meta_data=meta_data,
            revision_code=revision,
            status_code=status,
            is_admin=user.role == "admin",
        )

        return {
            "ok": True,
            "message": "Dual files uploaded successfully.",
            "doc_number": meta_data["doc_number"],
            "revision": revision,
            "pdf_file_id": pdf_entry.id,
            "native_file_id": native_entry.id,
        }
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
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    query = (
        db.query(ArchiveFile)
        .options(
            joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.document),
            joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.archive_files),
        )
        .join(DocumentRevision)
        .join(MdrDocument)
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

    data = []
    for f in files:
        revision_row = f.document_revision
        document_row = revision_row.document if revision_row else None
        doc_num = document_row.doc_number if document_row else "Unknown"
        pdf_file_id, native_file_id = _revision_file_ids(revision_row)
        data.append(
            {
                "id": f.id,
                "name": f.original_name,
                "doc_number": doc_num,
                "document_id": document_row.id if document_row else None,
                "project_code": document_row.project_code if document_row else None,
                "discipline_code": document_row.discipline_code if document_row else None,
                "revision_id": revision_row.id if revision_row else None,
                "revision": f.revision,
                "size": f.size_bytes,
                "status": f.status,
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
                "type": f.mime_type,
                "file_kind": f.file_kind or "pdf",
                "is_primary": True if f.is_primary is None else bool(f.is_primary),
                "companion_file_id": f.companion_file_id,
                "pdf_file_id": pdf_file_id,
                "native_file_id": native_file_id,
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
            files_payload.append(
                {
                    "id": af.id,
                    "name": af.original_name,
                    "file_kind": _file_kind(af.file_kind),
                    "size": af.size_bytes,
                    "mime_type": af.mime_type,
                    "status": af.status,
                    "is_primary": True if af.is_primary is None else bool(af.is_primary),
                    "companion_file_id": af.companion_file_id,
                    "uploaded_at": af.uploaded_at.isoformat() if af.uploaded_at else None,
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


@router.get("/download/{file_id}")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("archive:read")),
):
    file_record = db.query(ArchiveFile).filter(ArchiveFile.id == file_id).first()
    if not file_record or not os.path.exists(file_record.stored_path):
        raise HTTPException(status_code=404, detail="???? ???? ???.")
    if file_record.document_revision and file_record.document_revision.document:
        doc = file_record.document_revision.document
        enforce_scope_access(
            db,
            user,
            project_code=doc.project_code,
            discipline_code=doc.discipline_code,
        )

    return FileResponse(
        path=file_record.stored_path,
        filename=file_record.original_name,
        media_type=file_record.mime_type,
    )


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
        doc_num, serial = docnum_service.generate_next_doc_number(
            db,
            project_code=project_code,
            mdr_code=mdr_code,
            phase_code=phase,
            discipline_code=discipline,
            pkg_code=pkg,
            block=block,
            level=level,
            subject_p=subject_p,
        )
        return {"serial": serial, "full_doc": doc_num}
    except Exception as e:
        print(f"Serial Error: {e}")
        return {"serial": "01", "full_doc": ""}
