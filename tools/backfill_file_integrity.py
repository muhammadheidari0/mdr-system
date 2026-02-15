from __future__ import annotations

import argparse
import hashlib
import mimetypes
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import ArchiveFile, CorrespondenceAttachment


def _sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _backfill_archive(db: Session, *, dry_run: bool = True) -> int:
    rows = db.query(ArchiveFile).filter(ArchiveFile.sha256.is_(None)).all()
    changed = 0
    for row in rows:
        path = Path(str(row.stored_path or "").strip())
        if not path.exists():
            continue
        row.sha256 = _sha256_for_file(path)
        if not str(row.detected_mime or "").strip():
            guessed, _ = mimetypes.guess_type(path.name)
            row.detected_mime = str(guessed or row.mime_type or "").strip() or None
        if not str(row.validation_status or "").strip():
            row.validation_status = "legacy"
        if not str(row.storage_backend or "").strip():
            row.storage_backend = "local"
        if not str(row.mirror_status or "").strip():
            row.mirror_status = "pending"
        changed += 1
    return changed


def _backfill_corr(db: Session, *, dry_run: bool = True) -> int:
    rows = db.query(CorrespondenceAttachment).filter(CorrespondenceAttachment.sha256.is_(None)).all()
    changed = 0
    for row in rows:
        path = Path(str(row.stored_path or "").strip())
        if not path.exists():
            continue
        row.sha256 = _sha256_for_file(path)
        if not str(row.detected_mime or "").strip():
            guessed, _ = mimetypes.guess_type(path.name)
            row.detected_mime = str(guessed or row.mime_type or "").strip() or None
        if not str(row.validation_status or "").strip():
            row.validation_status = "legacy"
        if not str(row.storage_backend or "").strip():
            row.storage_backend = "local"
        if not str(row.mirror_status or "").strip():
            row.mirror_status = "pending"
        changed += 1
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill file sha256/detected mime for legacy files.")
    parser.add_argument("--database-url", default=str(settings.DATABASE_URL))
    parser.add_argument("--execute", action="store_true", help="Apply changes. Default is dry-run.")
    args = parser.parse_args()

    engine = create_engine(str(args.database_url))
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        archive_count = _backfill_archive(db, dry_run=not args.execute)
        corr_count = _backfill_corr(db, dry_run=not args.execute)
        if args.execute:
            db.commit()
        else:
            db.rollback()

    mode = "EXECUTED" if args.execute else "DRY-RUN"
    print(f"[{mode}] archive_files updated: {archive_count}")
    print(f"[{mode}] correspondence_attachments updated: {corr_count}")


if __name__ == "__main__":
    main()
