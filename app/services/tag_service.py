from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import enforce_scope_access
from app.db.models import (
    Correspondence,
    CorrespondenceTagAssignment,
    DocumentTag,
    DocumentTagAssignment,
    MdrDocument,
)
from app.services.document_activity_service import log_document_activity


def normalize_tag_name(name: str | None) -> str:
    return " ".join(str(name or "").strip().split())


def normalize_tag_color(color: str | None) -> str | None:
    value = str(color or "").strip()
    if not value:
        return None
    return value


def list_tags(db: Session) -> list[DocumentTag]:
    return db.query(DocumentTag).order_by(DocumentTag.name.asc(), DocumentTag.id.asc()).all()


def get_tag_or_404(db: Session, tag_id: int) -> DocumentTag:
    row = db.query(DocumentTag).filter(DocumentTag.id == int(tag_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Tag not found")
    return row


def create_tag(db: Session, name: str, color: str | None, user: Any | None = None) -> DocumentTag:
    del user
    normalized_name = normalize_tag_name(name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Tag name is required")
    for row in db.query(DocumentTag).order_by(DocumentTag.id.asc()).all():
        if normalize_tag_name(row.name).lower() == normalized_name.lower():
            if color is not None and not str(row.color or "").strip():
                row.color = normalize_tag_color(color)
                db.commit()
                db.refresh(row)
            return row
    row = DocumentTag(
        name=normalized_name,
        color=normalize_tag_color(color),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_tag(
    db: Session,
    tag_id: int,
    *,
    name: str,
    color: str | None,
) -> DocumentTag:
    row = get_tag_or_404(db, tag_id)
    normalized_name = normalize_tag_name(name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Tag name is required")
    for other in db.query(DocumentTag).order_by(DocumentTag.id.asc()).all():
        if int(other.id or 0) == int(row.id or 0):
            continue
        if normalize_tag_name(other.name).lower() == normalized_name.lower():
            raise HTTPException(status_code=409, detail="Tag name already exists")
    row.name = normalized_name
    row.color = normalize_tag_color(color)
    db.commit()
    db.refresh(row)
    return row


def delete_tag(db: Session, tag_id: int) -> None:
    row = get_tag_or_404(db, tag_id)
    db.delete(row)
    db.commit()


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


def resolve_tag(
    db: Session,
    *,
    tag_id: int | None = None,
    tag_name: str | None = None,
    color: str | None = None,
    user: Any | None = None,
) -> DocumentTag:
    if tag_id:
        return get_tag_or_404(db, int(tag_id))
    return create_tag(db, str(tag_name or ""), color, user)


def assign_tag_to_document(
    db: Session,
    document_id: int,
    *,
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
    target_tag = resolve_tag(db, tag_id=tag_id, tag_name=tag_name, color=color, user=user)
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


def list_correspondence_tags(
    db: Session,
    correspondence_id: int,
    user: Any,
) -> list[CorrespondenceTagAssignment]:
    correspondence = (
        db.query(Correspondence)
        .options(
            joinedload(Correspondence.tag_assignments).joinedload(CorrespondenceTagAssignment.tag)
        )
        .filter(Correspondence.id == int(correspondence_id))
        .first()
    )
    if not correspondence:
        raise HTTPException(status_code=404, detail="Correspondence not found")
    enforce_scope_access(db, user, project_code=correspondence.project_code)
    return list(correspondence.tag_assignments or [])


def replace_correspondence_tags(
    db: Session,
    correspondence: Correspondence,
    *,
    tag_ids: list[int] | None,
    user: Any,
) -> list[CorrespondenceTagAssignment]:
    enforce_scope_access(db, user, project_code=correspondence.project_code)
    desired_ids = sorted(
        {
            int(value)
            for value in (tag_ids or [])
            if isinstance(value, int) or str(value or "").strip().isdigit()
            if int(value) > 0
        }
    )
    if desired_ids:
        tags = db.query(DocumentTag).filter(DocumentTag.id.in_(desired_ids)).all()
        found_ids = sorted({int(row.id or 0) for row in tags})
        if found_ids != desired_ids:
            raise HTTPException(status_code=404, detail="One or more selected tags were not found")

    existing_rows = list(correspondence.tag_assignments or [])
    existing_ids = {int(row.tag_id or 0): row for row in existing_rows}

    for row in existing_rows:
        if int(row.tag_id or 0) not in desired_ids:
            db.delete(row)

    for tag_id in desired_ids:
        if tag_id in existing_ids:
            continue
        db.add(
            CorrespondenceTagAssignment(
                correspondence_id=int(correspondence.id or 0),
                tag_id=int(tag_id),
                assigned_by_id=getattr(user, "id", None),
                assigned_at=datetime.utcnow(),
            )
        )

    db.flush()
    db.refresh(correspondence)
    return list(correspondence.tag_assignments or [])
