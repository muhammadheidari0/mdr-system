# app/services/mdr_service.py
import re
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.db.models import MdrDocument, DocumentRevision, Package, Level, Block

def get_document_by_number(db: Session, doc_number: str) -> Optional[MdrDocument]:
    """جستجوی سند بر اساس شماره"""
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
    subject_p: str
) -> Tuple[str, str]:
    """
    تولید عنوان کامل انگلیسی و فارسی.
    اگر نام پکیج یا لول در دیتابیس نبود، از کد آن‌ها استفاده می‌کند.
    """
    
    # 1. یافتن نام پکیج (ایمن سازی شده)
    pkg_name_e = package_code
    pkg_name_p = package_code
    
    if discipline_code and package_code:
        pkg = db.query(Package).filter(
            Package.discipline_code == discipline_code,
            Package.package_code == package_code
        ).first()
        
        if pkg:
            if pkg.name_e: pkg_name_e = pkg.name_e
            if pkg.name_p: pkg_name_p = pkg.name_p

    # 2. نام بلوک
    block_str = block_code if block_code else "G"
    
    # 3. نام طبقه (ایمن سازی شده)
    lvl_str = level_code if level_code else "GEN"
    if level_code:
        lvl = db.query(Level).filter(Level.code == level_code).first()
        # معمولا در عنوان سند از کد لول استفاده می‌شود (L01)، اگر نام خواستید خط زیر را فعال کنید:
        # if lvl and lvl.name_e: lvl_str = lvl.name_e

    # 4. ترکیب بخش موقعیت
    location_part = f"{block_str}{lvl_str}"

    # 5. تمیزکاری سابجکت‌ها (تبدیل None به رشته خالی)
    sub_e = str(subject_e).strip() if subject_e else ""
    sub_p = str(subject_p).strip() if subject_p else sub_e

    # 6. فرمت‌دهی نهایی
    # ساختار: PackageName - Location - Subject
    
    full_title_e = f"{pkg_name_e}-{location_part}"
    if sub_e: full_title_e += f"-{sub_e}"

    full_title_p = f"{pkg_name_p}-{location_part}"
    if sub_p: full_title_p += f"-{sub_p}"

    return full_title_e, full_title_p

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
    subject: str = None,
    estimated_price: float = 0,
    weight: float = 0
) -> MdrDocument:
    doc_number = str(doc_number or "").strip().upper()
    if not doc_number:
        raise HTTPException(status_code=400, detail="Document number is required.")
    
    # چک کردن وجود سند
    if get_document_by_number(db, doc_number):
        # اینجا به جای خطا، می‌توانیم سند موجود را برگردانیم یا آپدیت کنیم
        # اما طبق درخواست فعلی خطا برمی‌گردانیم (که در ایمپورت هندل می‌شود)
        raise HTTPException(status_code=400, detail=f"Document {doc_number} already exists.")

    # تعیین سابجکت برای تولید عنوان
    subj_gen_e = title_e if title_e else (subject or "")
    subj_gen_p = title_p if title_p else (subject or "")

    # تولید عنوان کامل (با تابع ایمن شده)
    full_title_e, full_title_p = _generate_full_titles(
        db, discipline_code, package_code, block, level_code, 
        subj_gen_e, subj_gen_p
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
        subject=subject,
        
        estimated_price=estimated_price,
        weight=weight
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
    notes: str = None
) -> DocumentRevision:
    
    rev = db.query(DocumentRevision).filter(
        DocumentRevision.document_id == document_id,
        DocumentRevision.revision == revision_code
    ).first()

    if not rev:
        rev = DocumentRevision(
            document_id=document_id,
            revision=revision_code,
            status=status,
            file_path=file_path,
            notes=notes
        )
        db.add(rev)
        db.flush()
    else:
        if file_path: rev.file_path = file_path
        if notes: rev.notes = notes
    
    return rev
