from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.db.models import ArchiveFile, DocumentRevision, MdrDocument


def serialize_archive_manifest_row(row: ArchiveFile) -> dict[str, Any]:
    revision = row.document_revision
    document = revision.document if revision else None
    return {
        "legacy_document_id": int(getattr(document, "id", 0) or 0),
        "legacy_revision_id": int(getattr(revision, "id", 0) or 0),
        "legacy_archive_file_id": int(getattr(row, "id", 0) or 0),
        "doc_number": str(getattr(document, "doc_number", "") or ""),
        "project_code": str(getattr(document, "project_code", "") or ""),
        "discipline_code": str(getattr(document, "discipline_code", "") or ""),
        "package_code": str(getattr(document, "package_code", "") or ""),
        "block_code": str(getattr(document, "block", "") or ""),
        "level_code": str(getattr(document, "level_code", "") or ""),
        "phase_code": str(getattr(document, "phase_code", "") or ""),
        "mdr_code": str(getattr(document, "mdr_code", "") or ""),
        "subject": str(getattr(document, "subject", "") or ""),
        "revision": str(getattr(revision, "revision", "") or getattr(row, "revision", "") or ""),
        "status": str(getattr(revision, "status", "") or getattr(row, "status", "") or ""),
        "file_kind": str(getattr(row, "file_kind", "") or "pdf"),
        "source_path": str(getattr(row, "stored_path", "") or ""),
        "original_name": str(getattr(row, "original_name", "") or ""),
        "mime_type": str(getattr(row, "mime_type", "") or getattr(row, "detected_mime", "") or ""),
        "size_bytes": int(getattr(row, "size_bytes", 0) or 0),
        "sha256": str(getattr(row, "sha256", "") or ""),
        "uploaded_by_email": str(getattr(row, "uploaded_by", "") or ""),
        "uploaded_at": getattr(row, "uploaded_at", None).isoformat() if getattr(row, "uploaded_at", None) else None,
    }


def export_archive_manifest_rows(
    db: Session,
    *,
    project_code: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    query = (
        db.query(ArchiveFile)
        .options(joinedload(ArchiveFile.document_revision).joinedload(DocumentRevision.document))
        .join(ArchiveFile.document_revision)
        .join(DocumentRevision.document)
        .filter(ArchiveFile.deleted_at.is_(None), MdrDocument.deleted_at.is_(None))
        .order_by(MdrDocument.doc_number.asc(), DocumentRevision.revision.asc(), ArchiveFile.id.asc())
    )
    project = str(project_code or "").strip().upper()
    if project:
        query = query.filter(MdrDocument.project_code == project)
    if limit and int(limit) > 0:
        query = query.limit(int(limit))
    return [serialize_archive_manifest_row(row) for row in query.all()]
