# app/services/mdr_service.py
from __future__ import annotations

import re
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import DocumentRevision, Level, MdrDocument, Package


def get_document_by_number(db: Session, doc_number: str) -> Optional[MdrDocument]:
    code = str(doc_number or "").strip().upper()
    if not code:
        return None
    return db.query(MdrDocument).filter(MdrDocument.doc_number == code).first()


def _normalize_subject_for_key(value: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]", "", str(value or "")).lower()


def find_document_by_metadata_key(
    db: Session,
    *,
    project_code: str,
    mdr_code: str,
    phase_code: str,
    discipline_code: str,
    package_code: str,
    block: str,
    level_code: str,
    subject: str | None,
) -> Optional[MdrDocument]:
    target_subject = _normalize_subject_for_key(subject)
    if not target_subject:
        # Empty subject must not act as a metadata key.
        return None

    candidates = (
        db.query(MdrDocument)
        .filter(MdrDocument.project_code == str(project_code or "").strip().upper())
        .filter(MdrDocument.mdr_code == str(mdr_code or "").strip().upper())
        .filter(MdrDocument.phase_code == str(phase_code or "").strip().upper())
        .filter(MdrDocument.discipline_code == str(discipline_code or "").strip().upper())
        .filter(MdrDocument.package_code == str(package_code or "").strip().upper())
        .filter(MdrDocument.block == str(block or "").strip().upper())
        .filter(MdrDocument.level_code == str(level_code or "").strip().upper())
        .all()
    )
    for doc in candidates:
        if _normalize_subject_for_key(doc.subject) == target_subject:
            return doc
    return None


def _generate_full_titles(
    db: Session,
    discipline_code: str,
    package_code: str,
    block_code: str,
    level_code: str,
    subject_e: str,
    subject_p: str,
) -> Tuple[str, str]:
    """
    Title convention aligned with MDR coding sheet:
    - title_e: PackageE[-BlockLevel][ - SubjectE]
    - title_p: PackageP (GEN) or LocationNameP-Block-PackageP (non-GEN), then [-SubjectP]
    """
    pkg_name_e = str(package_code or "").strip() or "00"
    pkg_name_p = pkg_name_e

    if discipline_code and package_code:
        pkg = (
            db.query(Package)
            .filter(
                Package.discipline_code == str(discipline_code or "").strip().upper(),
                Package.package_code == str(package_code or "").strip().upper(),
            )
            .first()
        )
        if pkg:
            pkg_name_e = str(pkg.name_e or pkg_name_e).strip() or pkg_name_e
            pkg_name_p = str(pkg.name_p or pkg_name_p).strip() or pkg_name_p

    block_str = str(block_code or "").strip().upper() or "G"
    level_str = str(level_code or "").strip().upper() or "GEN"
    is_general = level_str == "GEN"
    location_name_p = level_str
    if not is_general and level_str:
        level_row = db.query(Level).filter(Level.code == level_str).first()
        if level_row and level_row.name_p:
            location_name_p = str(level_row.name_p).strip() or level_str

    sub_e = str(subject_e or "").strip()
    sub_p = str(subject_p or "").strip()

    title_e = pkg_name_e
    if not is_general and level_str:
        title_e = f"{title_e}-{block_str}{level_str}"
    if sub_e:
        title_e = f"{title_e} - {sub_e}"

    if is_general:
        title_p = pkg_name_p
    else:
        title_p = f"{location_name_p}-{block_str}-{pkg_name_p}"
    if sub_p:
        title_p = f"{title_p}-{sub_p}"

    return title_e, title_p


def build_document_titles(
    db: Session,
    *,
    discipline_code: str,
    package_code: str,
    block_code: str,
    level_code: str,
    subject_e: str,
    subject_p: str,
) -> Tuple[str, str]:
    return _generate_full_titles(
        db,
        discipline_code,
        package_code,
        block_code,
        level_code,
        subject_e,
        subject_p,
    )


def create_mdr_document(
    db: Session,
    doc_number: str,
    project_code: str,
    mdr_code: str,
    phase_code: str,
    discipline_code: str,
    package_code: str,
    block: str,
    level_code: str,
    title_e: str = "",
    title_p: str = "",
    subject: str | None = None,
    estimated_price: float = 0,
    weight: float = 0,
) -> MdrDocument:
    doc_number = str(doc_number or "").strip().upper()
    if not doc_number:
        raise HTTPException(status_code=400, detail="Document number is required.")

    if get_document_by_number(db, doc_number):
        raise HTTPException(status_code=400, detail=f"Document {doc_number} already exists.")

    sub_e = str(title_e or "").strip() or str(subject or "").strip()
    sub_p = str(title_p or "").strip()
    full_title_e, full_title_p = _generate_full_titles(
        db,
        discipline_code,
        package_code,
        block,
        level_code,
        sub_e,
        sub_p,
    )

    new_doc = MdrDocument(
        doc_number=doc_number,
        project_code=project_code,
        mdr_code=mdr_code,
        phase_code=phase_code,
        discipline_code=discipline_code,
        package_code=package_code,
        block=block,
        level_code=level_code,
        doc_title_e=full_title_e,
        doc_title_p=full_title_p,
        subject=str(subject or "").strip(),
        estimated_price=estimated_price,
        weight=weight,
    )

    db.add(new_doc)
    db.flush()
    return new_doc


def get_or_create_revision(
    db: Session,
    document_id: int,
    revision_code: str,
    status: str,
    file_path: str = None,
    notes: str = None,
) -> DocumentRevision:
    rev = (
        db.query(DocumentRevision)
        .filter(
            DocumentRevision.document_id == document_id,
            DocumentRevision.revision == revision_code,
        )
        .first()
    )

    if not rev:
        rev = DocumentRevision(
            document_id=document_id,
            revision=revision_code,
            status=status,
            file_path=file_path,
            notes=notes,
        )
        db.add(rev)
        db.flush()
    else:
        if file_path:
            rev.file_path = file_path
        if notes:
            rev.notes = notes

    return rev
