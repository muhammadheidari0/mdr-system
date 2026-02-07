from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.api.dependencies import (
    User,
    apply_scope_query_filters,
    enforce_scope_access,
    get_db,
    require_permission,
)
from app.db.models import ArchiveFile, DocumentRevision, MdrDocument

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:read")),
):
    """???? ??????? ?? ???? ???????? ??????"""
    base_query = db.query(ArchiveFile).join(DocumentRevision)
    total_files = base_query.count()

    stats = (
        db.query(
            func.count(case((DocumentRevision.status == "IFA", 1))).label("review"),
            func.count(case((DocumentRevision.status == "IFC", 1))).label("approved"),
            func.count(case((DocumentRevision.status == "AB", 1))).label("as_built"),
        )
        .select_from(ArchiveFile)
        .join(DocumentRevision, ArchiveFile.revision_id == DocumentRevision.id)
        .first()
    )

    return {
        "total": total_files,
        "review": stats.review or 0,
        "approved": stats.approved or 0,
        "transmittal": stats.as_built or 0,
        "user_role": current_user.role,
    }


@router.get("/table")
def get_dashboard_table(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(default=None),
    project_code: Optional[str] = Query(default=None),
    discipline_code: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    sort_by: str = Query(default="uploaded_at"),
    sort_desc: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:read")),
):
    """???? ??????? ?? ????? ? ?????????"""
    query = (
        db.query(ArchiveFile, DocumentRevision, MdrDocument)
        .join(DocumentRevision, ArchiveFile.revision_id == DocumentRevision.id)
        .join(MdrDocument, DocumentRevision.document_id == MdrDocument.id)
    )
    query = apply_scope_query_filters(
        query,
        db,
        current_user,
        project_column=MdrDocument.project_code,
        discipline_column=MdrDocument.discipline_code,
    )

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ArchiveFile.original_name.ilike(term),
                MdrDocument.doc_number.ilike(term),
                MdrDocument.doc_title_e.ilike(term),
                MdrDocument.doc_title_p.ilike(term),
                MdrDocument.subject.ilike(term),
            )
        )

    if project_code:
        enforce_scope_access(db, current_user, project_code=project_code)
        query = query.filter(MdrDocument.project_code == project_code)
    if discipline_code:
        enforce_scope_access(db, current_user, discipline_code=discipline_code)
        query = query.filter(MdrDocument.discipline_code == discipline_code)

    if status:
        query = query.filter(DocumentRevision.status.ilike(f"%{status}%"))

    sort_map = {
        "uploaded_at": ArchiveFile.uploaded_at,
        "created_at": ArchiveFile.uploaded_at,
        "doc_number": MdrDocument.doc_number,
        "status": DocumentRevision.status,
        "revision": DocumentRevision.revision,
    }
    sort_col = sort_map.get(sort_by, ArchiveFile.uploaded_at)
    query = query.order_by(sort_col.desc() if sort_desc else sort_col.asc())

    total = query.count()
    rows = query.offset(skip).limit(limit).all()

    items = []
    for archive_file, revision, document in rows:
        title = document.doc_title_p or document.doc_title_e or document.subject or ""
        items.append(
            {
                "id": archive_file.id,
                "filename": archive_file.original_name,
                "doc_number": document.doc_number,
                "doc_title_p": title,
                "title": title,
                "status": revision.status,
                "revision": revision.revision,
                "created_at": archive_file.uploaded_at.isoformat() if archive_file.uploaded_at else None,
                "file_size": archive_file.size_bytes,
            }
        )

    return {"items": items, "total": total, "skip": skip, "limit": limit}
