# app/services/smart_import_service.py
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

from sqlalchemy.orm import Session
from app.db.models import MdrDocument, Project, Phase

# ایمپورت سرویس‌های کمکی (جهت جلوگیری از تکرار کد)
from app.services import docnum_service, mdr_service, folder_service

# ---------------------------------------------------------
# Helper Classes
# ---------------------------------------------------------
@dataclass
class ParsedDoc:
    project: str
    mdr: str
    phase: str
    pkg: str
    serial: str
    block: str
    level: str
    original_filename: str

    @property
    def doc_number(self) -> str:
        # نام فایل بدون پسوند به عنوان شماره سند
        return Path(self.original_filename).stem

def _disc_from_pkg(pkg_code: str) -> str:
    """استخراج دیسیپلین از کد پکیج (مثلاً AR01 -> AR)"""
    if not pkg_code: return "GN"
    m = re.match(r"^([A-Z]+)", pkg_code, re.IGNORECASE)
    return m.group(1).upper() if m else pkg_code[:2].upper()

def _get_sheet_name(mdr_char: str) -> str:
    """تبدیل کد MDR به نام شیت (Engineering, Procurement, ...)"""
    return {'E': 'Engineering', 'P': 'Procurement', 'C': 'Construction'}.get(mdr_char.upper(), 'General')

# ---------------------------------------------------------
# 1. Parsing Logic (استخراج اطلاعات از نام فایل)
# ---------------------------------------------------------
def parse_filename(filename: str) -> Optional[ParsedDoc]:
    """
    تلاش برای تجزیه نام فایل به اجزای استاندارد سند.
    فرمت‌های پشتیبانی شده:
    1. 4-Part: PROJ-MID-SERIAL-TAIL (Construction style)
    2. 3-Part: PROJ-MID-TAIL (Engineering style)
    """
    stem = Path(filename).stem.upper().strip()
    
    # Pattern 1: 4 Parts -> T202-C-001-AB
    m4 = re.match(r"^([A-Z0-9]+)-([A-Z0-9]+)-(\d+)-([A-Z0-9]+)$", stem)
    if m4:
        proj, mid, serial, tail = m4.groups()
        # فرض: mid شامل MDR+Phase است، tail شامل Block+Level
        if len(mid) < 2 or len(tail) < 2: return None
        return ParsedDoc(
            project=proj, 
            mdr=mid[0], 
            phase=mid[1], 
            pkg="GEN", # پکیج عمومی در این حالت فرض می‌شود
            serial=serial, 
            block=tail[0], 
            level=tail[1:], 
            original_filename=filename
        )

    # Pattern 2: 3 Parts -> T202-EAR01-GENL01
    # ساختار معمول: PROJ - (MDR+Phase+Pkg) - (Block+Level) (+Serial گاهی اوقات)
    m3 = re.match(r"^([A-Z0-9]+)-([A-Z0-9]+)-([A-Z0-9]+)$", stem)
    if m3:
        proj, mid, tail = m3.groups()
        
        # تحلیل بخش میانی (MID): مثلا EAR01 -> E (MDR), A (Phase - typo?), R01 (Pkg?)
        # استاندارد دقیق پروژه: MDR(1) + Phase(1) + Pkg(Code)
        if len(mid) < 4: return None # حداقل باید MDR, Phase, Pkg(2 char) داشته باشد
        
        mdr_code = mid[0]
        phase_code = mid[1]
        pkg_code = mid[2:] # باقی‌مانده پکیج است
        
        # استخراج سریال از پکیج (اگر چسبیده باشد)
        # برخی مواقع سریال در انتهای پکیج است، برخی مواقع جداست.
        # اینجا فرض می‌کنیم سریال در نام فایل نیست و از دیتابیس باید چک شود، 
        # یا اینکه نام فایل شماره سند است.
        
        # تحلیل بخش انتهایی (TAIL): Block(1+) + Level
        # فرض ساده: حرف اول بلوک است
        block_code = tail[0]
        level_code = tail[1:]

        return ParsedDoc(
            project=proj, 
            mdr=mdr_code, 
            phase=phase_code, 
            pkg=pkg_code, 
            serial="0000", # سریال نامشخص از روی فرمت 3 بخشی (مگر اینکه در DB باشد)
            block=block_code, 
            level=level_code, 
            original_filename=filename
        )

    return None

# ---------------------------------------------------------
# 2. Main Entry Point (Process Logic)
# ---------------------------------------------------------
def process_upload_request(
    db: Session, 
    filename: str, 
    manual_data: dict = None
) -> Tuple[Optional[MdrDocument], Dict[str, Any]]:
    """
    پردازش درخواست آپلود:
    1. شناسایی سند (از نام فایل یا ورودی دستی).
    2. ساخت سند در صورت عدم وجود.
    3. تعیین مسیر ذخیره‌سازی فایل.
    """
    parsed = None
    created_new_doc = False
    logs = []
    
    # --- گام ۱: تحلیل ورودی ---
    if manual_data and manual_data.get('package'):
        # --- حالت دستی (Manual) ---
        logs.append("Processing in Manual Mode")
        
        proj_code = manual_data.get('project_code')
        if not proj_code:
            # Fallback: انتخاب اولین پروژه فعال
            proj_obj = db.query(Project).filter(Project.is_active == True).first()
            if not proj_obj: return None, {"error": "هیچ پروژه فعالی یافت نشد."}
            proj_code = proj_obj.code

        # تعیین MDR Code (ساده‌سازی)
        phase_val = str(manual_data.get('phase', '')).upper()
        mdr_char = 'C' if phase_val in ['C', 'A'] else 'E'
        if manual_data.get('mdr_code'):
            mdr_char = manual_data['mdr_code']

        # تولید شماره سند استاندارد
        doc_num, serial_str = docnum_service.generate_next_doc_number(
            db, 
            project_code=proj_code, 
            mdr_code=mdr_char, 
            phase_code=manual_data['phase'], 
            pkg_code=manual_data['package'], 
            block=manual_data['block'], 
            level=manual_data['level']
        )
        
        # نام فایل نهایی بر اساس شماره سند استاندارد
        # (نام فایل اصلی کاربر را نادیده می‌گیریم تا استاندارد حفظ شود)
        final_filename_str = f"{doc_num}{Path(filename).suffix}"
        
        parsed = ParsedDoc(
            project=proj_code, mdr=mdr_char, phase=manual_data['phase'],
            pkg=manual_data['package'], serial=serial_str,
            block=manual_data['block'], level=manual_data['level'],
            original_filename=final_filename_str
        )
        
        # برای آبجکت ParsedDoc مقدار doc_number را دستی ست می‌کنیم 
        # (چون property فقط stem نام فایل را برمی‌گرداند)
        # اما اینجا چون نام فایل را استاندارد کردیم، همان stem درست است.

    else:
        # --- حالت هوشمند (Smart Parsing) ---
        logs.append("Processing in Smart Parsing Mode")
        parsed = parse_filename(filename)

    if not parsed:
        return None, {"error": "ساختار نام فایل استاندارد نیست و اطلاعات دستی هم وارد نشده است."}

    # --- گام ۲: اطمینان از وجود پروژه ---
    proj = db.query(Project).filter(Project.code == parsed.project).first()
    if not proj:
        return None, {"error": f"پروژه با کد {parsed.project} در سیستم تعریف نشده است."}

    # --- گام ۳: ساخت یا بازیابی سند (Master Record) ---
    doc_number = parsed.doc_number
    
    try:
        # جستجوی سند
        doc = mdr_service.get_document_by_number(db, doc_number)
        
        if not doc:
            # اگر سند وجود نداشت، آن را می‌سازیم
            logs.append(f"Document {doc_number} not found. Creating new record.")
            
            # استخراج دیسیپلین از پکیج
            disc_code = manual_data.get('discipline') if manual_data else _disc_from_pkg(parsed.pkg)
            
            # عنوان سند (Subject)
            subj_e = manual_data.get('subject_e', '') if manual_data else parsed.original_filename
            subj_p = manual_data.get('subject_p', '') if manual_data else ''

            doc = mdr_service.create_mdr_document(
                db, 
                doc_number=doc_number,
                project_code=parsed.project,
                mdr_code=parsed.mdr,
                phase_code=parsed.phase,
                discipline_code=disc_code,
                package_code=parsed.pkg,
                block=parsed.block,
                level_code=parsed.level,
                title_e=subj_e,
                title_p=subj_p
            )
            created_new_doc = True
            logs.append("New Master Document created successfully.")
        else:
            logs.append("Document exists. Preparing to add revision.")

    except Exception as e:
        return None, {"error": f"خطا در ایجاد/بازیابی سند: {str(e)}"}

    # --- گام ۴: تعیین مسیر فیزیکی ذخیره‌سازی ---
    # هدف: ساخت پوشه خوانا (مثلاً: Engineering/Detailed Design/Architecture/...)
    
    # دریافت نام کامل فاز از دیتابیس (برای پوشه‌بندی زیباتر)
    phase_obj = db.query(Phase).filter(Phase.ph_code == parsed.phase).first()
    phase_folder_name = phase_obj.name_e if phase_obj else parsed.phase

    # تعیین نام دیسیپلین
    disc_code = doc.discipline_code
    # (می‌توان نام کامل را هم کوئری زد، فعلاً کد کافی است یا در ensure_storage_folder هندل می‌شود)
    # اما برای اطمینان یک دیسیپلین جنریک می‌سازیم
    disc_name = "General" 
    if doc.discipline: disc_name = doc.discipline.name_e

    # تعیین نام پکیج
    pkg_name = "General Package"
    if doc.package: pkg_name = doc.package.name_e

    # ساخت پوشه فیزیکی
    folder_path = folder_service.ensure_storage_folder(
        root_path=proj.root_path,
        project_code=proj.code, 
        project_name=proj.name_e,
        mdr_folder_name=folder_service.get_mdr_folder_name(db, parsed.mdr),
        phase_name=phase_folder_name, # ✅ استفاده از نام کامل فاز
        phase_code=parsed.phase,
        disc_name=disc_name, disc_code=disc_code,
        pkg_name=pkg_name, pkg_code=parsed.pkg,
        package_name=pkg_name,
    )

    # خروجی متادیتا برای استفاده در روتر
    meta = {
        "sheet_name": _get_sheet_name(parsed.mdr),
        "is_new": created_new_doc,
        "logs": logs,
        "final_filename": parsed.original_filename, # نام فایلی که باید ذخیره شود
        "folder_path": folder_path,
        "doc_number": doc_number
    }
    
    return doc, meta
