# tools/create_seed_excel.py
import pandas as pd
import os
import csv
import re

# ------------------------------------------------------------
# 1. تنظیم مسیرها (دقیقاً طبق ساختار شما)
# ------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# فرض: فایل در tools/ است و data_sources در روت پروژه قرار دارد
DATA_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "data_sources"))

# اگر پوشه وجود نداشت بساز
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

BASE_FILENAME = "master_data.xlsx"
CSV_INPUT = os.path.join(DATA_DIR, "packages.csv")

# ------------------------------------------------------------
# 2. تابع تولید نام فایل جدید (جلوگیری از Overwrite)
# ------------------------------------------------------------
def get_next_filename(directory, filename):
    """
    بررسی می‌کند اگر فایل وجود دارد، یک شماره به انتهای نام اضافه می‌کند.
    مثال: master_data.xlsx -> master_data (1).xlsx -> master_data (2).xlsx
    """
    name, ext = os.path.splitext(filename)
    full_path = os.path.join(directory, filename)
    
    # اگر فایل اصلی وجود ندارد، همان را برگردان
    if not os.path.exists(full_path):
        return full_path, filename
    
    counter = 1
    while True:
        new_name = f"{name} ({counter}){ext}"
        new_path = os.path.join(directory, new_name)
        if not os.path.exists(new_path):
            return new_path, new_name
        counter += 1

# محاسبه مسیر نهایی
OUTPUT_PATH, FINAL_FILENAME = get_next_filename(DATA_DIR, BASE_FILENAME)
print(f"📍 Target Path: {OUTPUT_PATH}")

# ------------------------------------------------------------
# 3. داده‌های ثابت (شیت‌های ضروری)
# ------------------------------------------------------------

# 1. Projects
df_projects = pd.DataFrame([
    {"code": "T202", "name_e": "Tehran Diamond", "name_p": "الماس تهران", "root_path": "C:/MDR/T202", "is_active": True},
    {"code": "P102", "name_e": "Beta Complex", "name_p": "مجتمع بتا", "root_path": "C:/MDR/P102", "is_active": True},
])

# 2. MDR Categories
df_mdr = pd.DataFrame([
    {"code": "E", "name_e": "Engineering", "name_p": "مهندسی", "folder_name": "Engineering", "sort_order": 1},
    {"code": "P", "name_e": "Procurement", "name_p": "تدارکات", "folder_name": "Procurement", "sort_order": 2},
    {"code": "C", "name_e": "Construction", "name_p": "اجرا", "folder_name": "Construction", "sort_order": 3},
    {"code": "T", "name_e": "Transmittal", "name_p": "ترنسمیتال", "folder_name": "Transmittals", "sort_order": 99},
])

# 3. Phases
df_phases = pd.DataFrame([
    {"ph_code": "P", "name_e": "Pre-Design", "name_p": "مقدماتی"},
    {"ph_code": "S", "name_e": "Schematic", "name_p": "شماتیک"},
    {"ph_code": "D", "name_e": "Design Development", "name_p": "توسعه طرح"},
    {"ph_code": "C", "name_e": "Construction Doc", "name_p": "نقشه‌های اجرایی"},
])

# 4. Levels
df_levels = pd.DataFrame([
    {"code": "GEN", "name_e": "General", "name_p": "عمومی", "sort_order": 0},
    {"code": "B01", "name_e": "Basement -1", "name_p": "زیرزمین ۱", "sort_order": 1},
    {"code": "GF", "name_e": "Ground Floor", "name_p": "همکف", "sort_order": 2},
    {"code": "L01", "name_e": "Level 01", "name_p": "طبقه اول", "sort_order": 3},
])

# 5. Blocks
df_blocks = pd.DataFrame([
    {"project_code": "T202", "code": "GEN", "name_e": "General", "name_p": "عمومی", "sort_order": 0},
    {"project_code": "T202", "code": "A", "name_e": "Block A", "name_p": "بلوک شمالی", "sort_order": 1},
    {"project_code": "T202", "code": "B", "name_e": "Block B", "name_p": "بلوک جنوبی", "sort_order": 2},
])

# 6. Statuses (جدید و ضروری)
df_statuses = pd.DataFrame([
    {"code": "IFA", "name": "Issued for Approval", "description": "جهت تایید", "order": 1},
    {"code": "IFI", "name": "Issued for Information", "description": "جهت اطلاع", "order": 2},
    {"code": "IFC", "name": "Issued for Construction", "description": "جهت ساخت", "order": 3},
    {"code": "ASB", "name": "As Built", "description": "چون ساخت", "order": 4},
    {"code": "APP", "name": "Approved", "description": "تایید شده", "order": 5},
    {"code": "REJ", "name": "Rejected", "description": "رد شده", "order": 6},
])

# ------------------------------------------------------------
# 4. خواندن Disciplines و Packages از CSV (در صورت وجود)
# ------------------------------------------------------------
disciplines_list = []
packages_list = []
seen_disciplines = set()

# ستون‌های پیش‌فرض
df_disciplines = pd.DataFrame(columns=["code", "name_e", "name_p"])
df_packages = pd.DataFrame(columns=["discipline_code", "package_code", "name_e", "name_p"])

if os.path.exists(CSV_INPUT):
    print(f"Reading CSV from: {CSV_INPUT}")
    try:
        with open(CSV_INPUT, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                r = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                
                d_code = r.get("Discipline_Code") or r.get("discipline_code")
                d_name_e = r.get("Discipline_Name_E") or r.get("discipline_name_e")
                d_name_p = r.get("Discipline_Name_P") or r.get("discipline_name_p")
                
                p_code = r.get("Package_Code") or r.get("package_code")
                p_name_e = r.get("Package_Name_E") or r.get("package_name_e")
                p_name_p = r.get("Package_Name_P") or r.get("package_name_p")

                if d_code and d_code not in seen_disciplines:
                    disciplines_list.append({"code": d_code, "name_e": d_name_e or d_code, "name_p": d_name_p})
                    seen_disciplines.add(d_code)
                
                if d_code and p_code:
                    packages_list.append({
                        "discipline_code": d_code, 
                        "package_code": p_code, 
                        "name_e": p_name_e or p_code, 
                        "name_p": p_name_p
                    })
        
        if disciplines_list: df_disciplines = pd.DataFrame(disciplines_list)
        if packages_list: df_packages = pd.DataFrame(packages_list)
            
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
else:
    print("⚠️ Warning: packages.csv not found. Creating default empty sheets.")

# ------------------------------------------------------------
# 5. ذخیره نهایی در فایل جدید
# ------------------------------------------------------------
try:
    with pd.ExcelWriter(OUTPUT_PATH, engine='openpyxl') as writer:
        df_projects.to_excel(writer, sheet_name="Projects", index=False)
        df_mdr.to_excel(writer, sheet_name="MdrCategories", index=False)
        df_phases.to_excel(writer, sheet_name="Phases", index=False)
        df_levels.to_excel(writer, sheet_name="Levels", index=False)
        df_blocks.to_excel(writer, sheet_name="Blocks", index=False)
        df_statuses.to_excel(writer, sheet_name="Statuses", index=False)
        df_disciplines.to_excel(writer, sheet_name="Disciplines", index=False)
        df_packages.to_excel(writer, sheet_name="Packages", index=False)

    print("\n" + "="*60)
    print(f"✅ فایل اکسل جدید با موفقیت ساخته شد: {FINAL_FILENAME}")
    print(f"📂 مسیر: {DATA_DIR}")
    print("="*60)
    print("نکته: برای اعمال در سیستم، نام این فایل را به 'master_data.xlsx' تغییر دهید")
    print("یا سیستم را طوری تنظیم کنید که این فایل را بخواند.")

except Exception as e:
    print(f"❌ خطا در ساخت فایل اکسل: {e}")