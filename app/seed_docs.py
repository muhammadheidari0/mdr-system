# seed_docs.py
# این فایل را کنار app/main.py بسازید و اجرا کنید
import sys
from pathlib import Path

# افزودن مسیر جاری
sys.path.append(str(Path(__file__).resolve().parent))

from app.db.session import SessionLocal
from app.db.models import MdrDocument, Project, MdrCategory

def create_dummy_doc():
    db = SessionLocal()
    try:
        proj = db.query(Project).first()
        cat = db.query(MdrCategory).first()

        if not proj:
            print("❌ خطا: پروژه‌ای یافت نشد. ابتدا دکمه 'Seed اولیه' را در تنظیمات بزنید.")
            return

        doc_num = f"{proj.code}-{(cat.code if cat else 'E')}-TEST-001"
        
        # چک کردن تکراری
        if db.query(MdrDocument).filter(MdrDocument.doc_number == doc_num).first():
            print("⚠️ مدرک قبلاً وجود دارد.")
            return

        doc = MdrDocument(
            project_code=proj.code,
            mdr_code=cat.code if cat else "E",
            doc_number=doc_num,
            doc_title_e="First Test Document",
            doc_title_p="اولین مدرک تستی",
            status="IFA",
            revision="00",
            phase_code="E",
            discipline_code="AR",
            block="GEN",
            level_code="L01"
        )
        db.add(doc)
        db.commit()
        print(f"✅ مدرک تستی ساخته شد: {doc_num}")
        print("حالا صفحه مرورگر را رفرش کنید (Ctrl+F5).")
        
    except Exception as e:
        print(f"❌ خطا: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_dummy_doc()