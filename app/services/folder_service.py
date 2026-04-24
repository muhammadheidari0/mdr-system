# app/services/folder_service.py
import re
import os
import shutil
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import UploadFile

from app.core.config import settings
from app.db.models import MdrCategory

def safe_name(s: str | None) -> str:
    """تبدیل رشته به نام فایل/فولدر ایمن (حذف کاراکترهای غیرمجاز)"""
    if not s: return ""
    s = str(s).strip()
    # حذف کاراکترهای ممنوعه ویندوز/لینوکس: < > : " / \ | ? *
    s = re.sub(r'[<>:"/\\|?*]', "-", s)
    # تبدیل فاصله‌های چندگانه به یکی
    s = re.sub(r"\s+", " ", s).strip()
    return s

def get_mdr_folder_name(db: Session, mdr_code: str) -> str:
    """دریافت نام پوشه MDR (مثلاً Engineering به جای E)"""
    m = db.query(MdrCategory).filter(MdrCategory.code == mdr_code).first()
    return (m.folder_name or m.name_e or mdr_code) if m else mdr_code

def ensure_storage_folder(
    root_path: str | None,
    project_code: str,
    project_name: str | None,
    mdr_folder_name: str,
    phase_name: str,
    disc_name: str, disc_code: str,
    pkg_name: str, pkg_code: str,
    phase_code: str | None = None,
    package_name: str | None = None,
    file_kind: str | None = None,
) -> str:
    """
    ساخت ساختار سلسله‌مراتب پوشه‌ها و بازگرداندن مسیر کامل.
    Path: Root / Project / MDR / PhaseCode / DisciplineCode / PackageName / FileKind
    """
    # مسیر پایه: اگر root_path پروژه تنظیم شده باشد از آن استفاده می‌کند، وگرنه پوشه پیش‌فرض data_store
    base = Path(root_path) if root_path else Path(settings.BASE_DIR) / "data_store"
    
    # 1. Project Folder
    p_name = safe_name(project_name)
    # اگر نام پروژه "unk" یا خالی بود، فقط کد را بگذار
    proj_folder = f"{project_code} - {p_name}" if p_name and p_name.lower() != "unk" else safe_name(project_code)

    phase_folder = safe_name(phase_code or phase_name) or "Phase"
    disc_folder = safe_name(disc_code) or "GN"
    pkg_folder = safe_name(package_name or pkg_name) or safe_name(pkg_code)

    # ساخت مسیر نهایی
    full_path = (
        base 
        / safe_name(proj_folder)
        / safe_name(mdr_folder_name) 
        / phase_folder
        / disc_folder  
        / pkg_folder   
    )
    if file_kind:
        full_path = full_path / safe_name(file_kind)
    
    # ایجاد دایرکتوری (بازگشتی) اگر وجود ندارد
    try:
        full_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[ERROR] Could not create directory {full_path}: {e}")
        # اگر نتوانست بسازد (مثلاً پرمیشن)، مسیر را برمی‌گرداند تا شاید در آینده ساخته شود یا خطا جای دیگری هندل شود
    
    return str(full_path)

def save_upload_file(file: UploadFile, destination_folder: str, new_name: str = None) -> str:
    """
    ذخیره فایل آپلود شده در مسیر مشخص شده.
    - اگر مسیر وجود نداشته باشد، می‌سازد.
    - فایل را با نام جدید (اگر داده شود) یا نام اصلی ذخیره می‌کند.
    """
    dest_path = Path(destination_folder)
    dest_path.mkdir(parents=True, exist_ok=True)
        
    filename = safe_name(new_name) if new_name else safe_name(file.filename)
    file_path = dest_path / filename
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        # پاکسازی فایل ناقص در صورت بروز خطا
        if file_path.exists():
            os.remove(file_path)
        raise e
        
    return str(file_path)
