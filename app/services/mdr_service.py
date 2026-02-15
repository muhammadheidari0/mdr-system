# app/services/mdr_service.py
from __future__ import annotations

import re
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import DocumentRevision, MdrDocument, Package


def get_document_by_number(db: Session, doc_number: str) -> Optional[MdrDocument]:
    code = str(doc_number or "").strip().upper()
    if not code:
        return None
    return db.query(MdrDocument).filter(MdrDocument.doc_number == code).first()


def _normalize_subject_for_key(value: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]", "", str(value or "")).lower()


def _package_code_candidates(discipline_code: str | None, package_code: str | None) -> list[str]:
    disc = str(discipline_code or "").strip().upper()
    raw_pkg = str(package_code or "").strip().upper()
    if not raw_pkg:
        return []

    candidates: list[str] = []
    if disc and raw_pkg.startswith(disc) and len(raw_pkg) > len(disc):
        stripped = raw_pkg[len(disc) :].strip()
        if stripped:
            candidates.append(stripped)
    candidates.append(raw_pkg)

    if disc and not raw_pkg.startswith(disc):
        prefixed = f"{disc}{raw_pkg}"
        candidates.append(prefixed)

    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        if not item or item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _resolve_package_row(
    db: Session,
    discipline_code: str | None,
    package_code: str | None,
) -> tuple[Package | None, str]:
    disc = str(discipline_code or "").strip().upper()
    candidates = _package_code_candidates(disc, package_code)
    default_pkg = candidates[0] if candidates else (str(package_code or "").strip().upper() or "00")

    if not disc or not candidates:
        return None, default_pkg

    rows = (
        db.query(Package)
        .filter(Package.discipline_code == disc)
        .filter(Package.package_code.in_(candidates))
        .all()
    )
    by_code = {str(row.package_code or "").strip().upper(): row for row in rows}
    for code in candidates:
        row = by_code.get(code)
        if row:
            return row, code
    return None, default_pkg


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

    package_candidates = _package_code_candidates(discipline_code, package_code)
    if not package_candidates:
        package_candidates = [str(package_code or "").strip().upper() or "00"]

    candidates = (
        db.query(MdrDocument)
        .filter(MdrDocument.project_code == str(project_code or "").strip().upper())
        .filter(MdrDocument.mdr_code == str(mdr_code or "").strip().upper())
        .filter(MdrDocument.phase_code == str(phase_code or "").strip().upper())
        .filter(MdrDocument.discipline_code == str(discipline_code or "").strip().upper())
        .filter(MdrDocument.package_code.in_(package_candidates))
        .filter(MdrDocument.block == str(block or "").strip().upper())
        .filter(MdrDocument.level_code == str(level_code or "").strip().upper())
        .all()
    )
    for doc in candidates:
        if _normalize_subject_for_key(doc.subject) == target_subject:
            return doc
    return None


def find_subjectless_document_by_scope(
    db: Session,
    *,
    project_code: str,
    mdr_code: str,
    phase_code: str,
    discipline_code: str,
    package_code: str,
    block: str,
    level_code: str,
) -> Optional[MdrDocument]:
    package_candidates = _package_code_candidates(discipline_code, package_code)
    if not package_candidates:
        package_candidates = [str(package_code or "").strip().upper() or "00"]

    rows = (
        db.query(MdrDocument)
        .filter(MdrDocument.project_code == str(project_code or "").strip().upper())
        .filter(MdrDocument.mdr_code == str(mdr_code or "").strip().upper())
        .filter(MdrDocument.phase_code == str(phase_code or "").strip().upper())
        .filter(MdrDocument.discipline_code == str(discipline_code or "").strip().upper())
        .filter(MdrDocument.package_code.in_(package_candidates))
        .filter(MdrDocument.block == str(block or "").strip().upper())
        .filter(MdrDocument.level_code == str(level_code or "").strip().upper())
        .filter(or_(MdrDocument.subject.is_(None), MdrDocument.subject == ""))
        .order_by(MdrDocument.id.asc())
        .all()
    )
    for doc in rows:
        if not _normalize_subject_for_key(doc.subject):
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
) -> Tuple[str, str, str]:
    """
    Title convention aligned with MDR coding sheet:
    - title_e: PackageE[-BlockLevel][ - SubjectE]
    - title_p: PackageP (GEN) or Block+LevelCode-PackageP (non-GEN), then [-SubjectP]
    """
    pkg_name_e = str(package_code or "").strip() or "00"
    pkg_name_p = pkg_name_e
    pkg, resolved_pkg_code = _resolve_package_row(db, discipline_code, package_code)
    pkg_name_e = resolved_pkg_code
    pkg_name_p = resolved_pkg_code

    if pkg:
        pkg_name_e_db = str(pkg.name_e or "").strip()
        pkg_name_p_db = str(pkg.name_p or "").strip()

        if pkg_name_e_db:
            pkg_name_e = pkg_name_e_db

        # Prefer Persian package name; if missing, fallback to English package name.
        if pkg_name_p_db:
            pkg_name_p = pkg_name_p_db
        elif pkg_name_e_db:
            pkg_name_p = pkg_name_e_db

    block_str = str(block_code or "").strip().upper() or "G"
    level_str = str(level_code or "").strip().upper() or "GEN"
    is_general = level_str == "GEN"

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
        title_p = f"{block_str}{level_str}-{pkg_name_p}"
    if sub_p:
        title_p = f"{title_p}-{sub_p}"

    return title_e, title_p, resolved_pkg_code


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
    title_e, title_p, _ = _generate_full_titles(
        db,
        discipline_code,
        package_code,
        block_code,
        level_code,
        subject_e,
        subject_p,
    )
    return title_e, title_p


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
    full_title_e, full_title_p, resolved_package_code = _generate_full_titles(
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
        package_code=resolved_package_code,
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
