# app/services/archive_service.py
from __future__ import annotations

import os
import re
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import UploadFile, HTTPException

from app.db.models import ArchiveFile, DocumentRevision, MdrDocument
from app.services import folder_service, docnum_service, mdr_service
from app.services.storage import StorageManager

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
        pkg_full = core[:-2] if serial_match else core
        pkg_full = pkg_full or core or "00"

        disc_c = pkg_full[:2] if len(pkg_full) >= 2 else "GN"
        block_c = suffix[0]
        level_c = suffix[1:] or "GEN"

        return {
            "project_code": project_code,
            "mdr_code": mdr_c,
            "phase_code": phase_c,
            "discipline_code": disc_c,
            "package_code": pkg_full,
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

# ---------------------------------------------------------
# 3. Get Document Info (Main Logic Updated)
# ---------------------------------------------------------
def get_document_status_info(db: Session, doc_number: str, subject_e: str = "", subject_p: str = ""):
    """
    اطلاعات سند را برمی‌گرداند.
    اگر سند وجود نداشته باشد، سعی می‌کند آن را بسازد (Auto Create).
    """
    doc_number = doc_number.strip().upper()
    
    # 1. جستجو در دیتابیس
    doc = db.query(MdrDocument).filter(MdrDocument.doc_number == doc_number).first()
    
    is_newly_created = False
    
    # 2. اگر نبود، تلاش برای ساختن (Auto Create)
    if not doc:
        parts = _parse_doc_code(doc_number)
        if parts:
            try:
                # برای اطمینان، شماره سند را دوباره محاسبه نمی‌کنیم چون کاربر دقیقاً همین کد را خواسته
                # اما چک می‌کنیم فرمت معتبر باشد
                
                title_e = subject_e or f"Document {doc_number}"
                title_p = subject_p or f"سند {doc_number}"
                
                doc = mdr_service.create_mdr_document(
                    db, 
                    doc_number=doc_number, 
                    project_code=parts['project_code'],
                    mdr_code=parts['mdr_code'], 
                    phase_code=parts['phase_code'],
                    discipline_code=parts['discipline_code'], 
                    package_code=parts['package_code'],
                    block=parts['block'], 
                    level_code=parts['level_code'],
                    title_e=title_e, 
                    title_p=title_p
                )
                is_newly_created = True
                
            except Exception as e:
                print(f"Error creating document with MDR services: {e}")
    
    # 3. اگر باز هم نبود (یعنی فرمت کد اشتباه بوده و پارس نشده)
    if not doc:
        return {
            "exists": False, 
            "msg": "سند یافت نشد و کد نامعتبر است."
        }

    # 4. دریافت آخرین وضعیت
    last_rev = db.query(DocumentRevision).filter(
        DocumentRevision.document_id == doc.id
    ).order_by(desc(DocumentRevision.created_at)).first()

    current_rev_code = last_rev.revision if last_rev else "N/A"
    current_status = last_rev.status if last_rev else "Registered"
    
    suggested = "00"
    if last_rev:
        suggested = _calculate_next_revision(last_rev.revision)

    msg = None
    if is_newly_created:
        msg = "سند جدید با موفقیت ایجاد شد."
        if not subject_e and not subject_p:
            msg += " (عناوین پیش‌فرض)"

    return {
        "exists": True,
        "document_id": doc.id,
        "doc_number": doc.doc_number,
        "title": doc.doc_title_e or doc.subject or "بدون عنوان",
        "last_revision": current_rev_code,
        "last_status": current_status,
        "next_revision_suggestion": suggested,
        "msg_success": msg,
        "is_new_document": is_newly_created
    }

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
    commit: bool = True,
    is_admin: bool = False
) -> ArchiveFile:
    storage = StorageManager(db)

    doc = db.query(MdrDocument).filter(MdrDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # مدیریت ریویژن (ساخت یا آپدیت)
    rev = db.query(DocumentRevision).filter(
        DocumentRevision.document_id == document_id,
        DocumentRevision.revision == revision_code
    ).first()

    if rev:
        rev.status = status_code
        rev.created_at = datetime.utcnow()
    else:
        rev = DocumentRevision(
            document_id=document_id,
            revision=revision_code,
            status=status_code,
            notes="Created via Upload"
        )
        db.add(rev)
        db.flush() 

    # --- ساخت مسیر ذخیره‌سازی ---
    proj_name = doc.project.name_e if doc.project else doc.project_code
    mdr_folder = folder_service.get_mdr_folder_name(db, doc.mdr_code)
    
    phase_name = doc.phase_code
    if doc.phase: phase_name = doc.phase.name_e or doc.phase_code
    
    disc_name = "General"
    disc_code = doc.discipline_code or "GN"
    if doc.discipline: disc_name = doc.discipline.name_e
    
    pkg_name = "General"
    pkg_code = doc.package_code or "00"
    if doc.package: pkg_name = doc.package.name_e

    target_folder = storage.get_mdr_path(
        project_code=doc.project_code,
        project_name=proj_name,
        mdr_folder_name=mdr_folder,
        phase_name=phase_name,
        disc_name=disc_name, disc_code=disc_code,
        pkg_name=pkg_name, pkg_code=pkg_code,
    )

    # --- استانداردسازی نام فایل ---
    # فرمت: [DocNumber]_[EnglishTitle]_Rev[XX].[ext]
    
    _, file_extension = os.path.splitext(file.filename)
    
    # عنوان انگلیسی را تمیز می‌کنیم (حذف کاراکترهای غیرمجاز)
    raw_title = doc.doc_title_e or doc.subject or "Untitled"
    safe_title = folder_service.safe_name(raw_title) # حذف / \ : * ? " < > |
    
    # اگر عنوان خیلی طولانی بود، کوتاه می‌کنیم (اختیاری)
    if len(safe_title) > 100:
        safe_title = safe_title[:100]

    # ساخت نام نهایی
    clean_name = f"{doc.doc_number}_{safe_title}_Rev{revision_code}{file_extension}"
    
    # ذخیره فایل فیزیکی
    saved_path = storage.save_upload(
        file=file, 
        destination_folder=target_folder, 
        new_name=clean_name
    )
    
    file_size = 0
    if os.path.exists(saved_path):
        file_size = os.path.getsize(saved_path)

    # بروزرسانی دیتابیس
    rev.file_path = saved_path
    rev.file_name = clean_name

    archive_entry = ArchiveFile(
        revision_id=rev.id,
        original_name=clean_name, 
        stored_path=saved_path,
        mime_type=file.content_type,
        size_bytes=file_size,
        file_kind=_normalize_archive_file_kind(file_kind),
        is_primary=bool(is_primary),
        companion_file_id=companion_file_id,
        revision=revision_code,
        status=status_code,
        uploaded_by="User",
        uploaded_at=datetime.utcnow()
    )
    
    db.add(archive_entry)
    if commit:
        db.commit()
        db.refresh(archive_entry)
    else:
        db.flush()
    
    return archive_entry


def save_dual_upload_files(
    db: Session,
    *,
    pdf_file: UploadFile,
    native_file: UploadFile,
    document_id: int,
    revision_code: str,
    status_code: str = "Uploaded",
    is_admin: bool = False,
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
            commit=False,
            is_admin=is_admin,
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
            commit=False,
            is_admin=is_admin,
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
    is_admin: bool = False
) -> ArchiveFile:
    """
    ثبت کامل مدرک (Master) و آپلود فایل در یک مرحله.
    """
    
    # 1. ابتدا سند را در جدول MDR ثبت می‌کنیم
    existing = db.query(MdrDocument).filter(MdrDocument.doc_number == meta_data['doc_number']).first()
    
    if existing:
        # اگر کد وجود دارد، از همان استفاده کن
        doc = existing
        # اختیاری: می‌توانیم عنوان‌ها را آپدیت کنیم
        if meta_data.get('subject_e'): doc.doc_title_e = meta_data['subject_e']
        if meta_data.get('subject_p'): doc.doc_title_p = meta_data['subject_p']
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
            title_e=meta_data['subject_e'],
            title_p=meta_data['subject_p'],
            subject=meta_data['subject_e']
        )
    
    db.flush() # برای گرفتن ID سند

    # 2. آپلود فایل
    archive_entry = save_upload_file(
        db=db,
        file=file,
        document_id=doc.id,
        revision_code=revision_code,
        status_code=status_code,
        file_kind=file_kind,
        is_admin=is_admin
    )
    
    return archive_entry


def register_and_upload_dual_document(
    db: Session,
    *,
    pdf_file: UploadFile,
    native_file: UploadFile,
    meta_data: dict,
    revision_code: str,
    status_code: str,
    is_admin: bool = False,
) -> tuple[ArchiveFile, ArchiveFile]:
    """
    Register document metadata (if needed) and upload PDF + Native together.
    """
    existing = db.query(MdrDocument).filter(MdrDocument.doc_number == meta_data["doc_number"]).first()

    if existing:
        doc = existing
        if meta_data.get("subject_e"):
            doc.doc_title_e = meta_data["subject_e"]
        if meta_data.get("subject_p"):
            doc.doc_title_p = meta_data["subject_p"]
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
            title_e=meta_data["subject_e"],
            title_p=meta_data["subject_p"],
            subject=meta_data["subject_e"],
        )

    db.flush()

    return save_dual_upload_files(
        db=db,
        pdf_file=pdf_file,
        native_file=native_file,
        document_id=doc.id,
        revision_code=revision_code,
        status_code=status_code,
        is_admin=is_admin,
    )

