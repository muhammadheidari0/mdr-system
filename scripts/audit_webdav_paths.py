"""
Audit WebDAV file paths to detect potential issues from before the path duplication fix.

This script finds:
1. Files with duplicate path segments (e.g., /ARCA-NTN/ARCA-NTN/...)
2. Files that may not be downloadable due to incorrect paths
3. Files with absolute paths instead of root-relative paths

Usage:
    python scripts/audit_webdav_paths.py
    python scripts/audit_webdav_paths.py --fix-dry-run
    python scripts/audit_webdav_paths.py --fix (DANGEROUS - applies fixes)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import (
    ArchiveFile,
    CorrespondenceAttachment,
    ItemAttachment,
    PermitQcPermitAttachment,
    SiteLogAttachment,
)
from app.services.nextcloud_adapter import NextcloudAdapter
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import resolve_nextcloud_runtime


def get_db() -> Session:
    """Create database session."""
    engine = create_engine(str(settings.DATABASE_URL))
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def detect_path_duplication(remote_path: str) -> tuple[bool, list[str]]:
    """
    Detect if a path has duplicate consecutive segments.

    Returns:
        (has_duplication, duplicate_segments)
    """
    segments = [s for s in remote_path.split("/") if s]
    duplicates = []

    for i in range(len(segments) - 1):
        if segments[i] == segments[i + 1]:
            duplicates.append(segments[i])

    return bool(duplicates), duplicates


def audit_table(
    db: Session,
    model,
    table_name: str,
    root_path: str,
    adapter: NextcloudAdapter | None = None,
) -> dict:
    """
    Audit a single table for WebDAV path issues.

    Returns dict with:
        - total: total WebDAV records
        - duplicates: records with path duplication
        - not_found: records where file doesn't exist on Nextcloud
        - absolute_paths: records with absolute paths instead of relative
    """
    print(f"\n{'='*60}")
    print(f"Auditing: {table_name}")
    print(f"{'='*60}")

    webdav_records = (
        db.query(model)
        .filter(model.stored_path.like("webdav://%"))
        .all()
    )

    total = len(webdav_records)
    print(f"Total WebDAV records: {total}")

    if total == 0:
        return {
            "total": 0,
            "duplicates": [],
            "not_found": [],
            "absolute_paths": [],
        }

    duplicates = []
    not_found = []
    absolute_paths = []

    root_name = root_path.strip("/").split("/")[-1] if root_path != "/" else None

    for record in webdav_records:
        stored_path = str(record.stored_path or "").strip()
        remote_path = stored_path.replace("webdav://", "", 1)

        # Check 1: Path duplication
        has_dup, dup_segments = detect_path_duplication(remote_path)
        if has_dup:
            duplicates.append({
                "id": record.id,
                "stored_path": stored_path,
                "remote_path": remote_path,
                "duplicates": dup_segments,
                "file_name": getattr(record, "file_name", None) or getattr(record, "original_name", None),
            })

        # Check 2: Absolute path (not relativized)
        # If root is /ARCA-NTN and path starts with /ARCA-NTN/ARCA-NTN/
        if root_name and remote_path.startswith(f"/{root_name}/{root_name}/"):
            absolute_paths.append({
                "id": record.id,
                "stored_path": stored_path,
                "remote_path": remote_path,
                "expected_start": f"/{root_name}/",
                "actual_start": f"/{root_name}/{root_name}/",
            })

        # Check 3: File existence (if adapter provided)
        if adapter:
            try:
                exists = adapter.file_exists(remote_path)
                if not exists:
                    not_found.append({
                        "id": record.id,
                        "stored_path": stored_path,
                        "remote_path": remote_path,
                        "file_name": getattr(record, "file_name", None) or getattr(record, "original_name", None),
                    })
            except Exception as e:
                print(f"   ⚠️  Error checking file {record.id}: {e}")

    # Print results
    print(f"\n📊 Results:")
    print(f"   Total: {total}")
    print(f"   ✅ OK: {total - len(duplicates) - len(not_found)}")
    print(f"   🔄 Duplicates: {len(duplicates)}")
    print(f"   📁 Absolute paths: {len(absolute_paths)}")
    if adapter:
        print(f"   ❌ Not found on Nextcloud: {len(not_found)}")

    if duplicates:
        print(f"\n🔄 Duplicate path segments found:")
        for item in duplicates[:5]:  # Show first 5
            print(f"   ID {item['id']}: {item['remote_path']}")
            print(f"      Duplicates: {item['duplicates']}")

        if len(duplicates) > 5:
            print(f"   ... and {len(duplicates) - 5} more")

    if absolute_paths:
        print(f"\n📁 Absolute paths (not relativized):")
        for item in absolute_paths[:5]:
            print(f"   ID {item['id']}: {item['remote_path']}")
            print(f"      Expected to start with: {item['expected_start']}")
            print(f"      Actually starts with: {item['actual_start']}")

        if len(absolute_paths) > 5:
            print(f"   ... and {len(absolute_paths) - 5} more")

    if adapter and not_found:
        print(f"\n❌ Files not found on Nextcloud:")
        for item in not_found[:5]:
            print(f"   ID {item['id']}: {item['remote_path']}")
            print(f"      File: {item['file_name']}")

        if len(not_found) > 5:
            print(f"   ... and {len(not_found) - 5} more")

    return {
        "total": total,
        "duplicates": duplicates,
        "not_found": not_found,
        "absolute_paths": absolute_paths,
    }


def propose_fix(stored_path: str, root_path: str) -> str:
    """
    Propose a fixed path for a problematic stored_path.

    Example:
        stored_path: webdav:///ARCA-NTN/ARCA-NTN/MDR/file.pdf
        root_path: /ARCA-NTN
        fixed: webdav:///MDR/file.pdf
    """
    remote_path = stored_path.replace("webdav://", "", 1)

    # Remove duplicate segments
    segments = remote_path.split("/")
    deduplicated = []
    for seg in segments:
        if not seg:
            continue
        if not deduplicated or deduplicated[-1] != seg:
            deduplicated.append(seg)

    fixed_remote = "/" + "/".join(deduplicated) if deduplicated else "/"

    # Relativize to root if needed
    if root_path and root_path != "/":
        root_norm = root_path.rstrip("/")
        if fixed_remote.startswith(f"{root_norm}/"):
            fixed_remote = fixed_remote[len(root_norm):]
        elif fixed_remote == root_norm:
            fixed_remote = "/"

    return f"webdav://{fixed_remote}"


def main():
    parser = argparse.ArgumentParser(description="Audit WebDAV file paths")
    parser.add_argument(
        "--check-existence",
        action="store_true",
        help="Check if files exist on Nextcloud (slower)",
    )
    parser.add_argument(
        "--fix-dry-run",
        action="store_true",
        help="Show what would be fixed without applying changes",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply fixes to database (DANGEROUS - backup first!)",
    )

    args = parser.parse_args()

    print("🔍 WebDAV Path Audit Tool")
    print("=" * 60)

    db = get_db()

    # Get Nextcloud settings
    integrations = get_storage_integrations(db)
    runtime = resolve_nextcloud_runtime(integrations)

    if not runtime.get("enabled"):
        print("❌ Nextcloud is not enabled. Exiting.")
        return

    if runtime.get("mode") != "webdav":
        print("⚠️  Nextcloud is not in WebDAV mode. Some checks may not apply.")

    root_path = str(runtime.get("root_path") or "").strip()
    print(f"\n📂 Nextcloud Root Path: {root_path or '(not set)'}")

    # Create adapter if checking existence
    adapter = None
    if args.check_existence:
        print("🔌 Creating Nextcloud adapter for file existence checks...")
        try:
            adapter = NextcloudAdapter(
                base_url=str(runtime.get("base_url") or ""),
                username=str(runtime.get("username") or ""),
                app_password=str(runtime.get("app_password") or ""),
                root_path=root_path,
                connect_timeout=float(runtime.get("connect_timeout") or 5),
                read_timeout=float(runtime.get("read_timeout") or 10),
                tls_verify=bool(runtime.get("tls_verify")),
            )
            ping = adapter.ping()
            if not ping["ok"]:
                print(f"❌ Nextcloud ping failed: {ping}")
                adapter = None
        except Exception as e:
            print(f"❌ Failed to create adapter: {e}")
            adapter = None

    # Audit all tables
    tables = [
        (ArchiveFile, "ArchiveFile (MDR Documents)"),
        (CorrespondenceAttachment, "CorrespondenceAttachment"),
        (ItemAttachment, "ItemAttachment (Comm Items)"),
        (PermitQcPermitAttachment, "PermitQcPermitAttachment"),
        (SiteLogAttachment, "SiteLogAttachment"),
    ]

    all_results = {}
    for model, name in tables:
        results = audit_table(db, model, name, root_path, adapter)
        all_results[name] = results

    # Summary
    print(f"\n\n{'='*60}")
    print("📊 SUMMARY")
    print(f"{'='*60}")

    total_records = sum(r["total"] for r in all_results.values())
    total_duplicates = sum(len(r["duplicates"]) for r in all_results.values())
    total_absolute = sum(len(r["absolute_paths"]) for r in all_results.values())
    total_not_found = sum(len(r["not_found"]) for r in all_results.values())

    print(f"Total WebDAV records: {total_records}")
    print(f"Records with issues: {total_duplicates + total_absolute + total_not_found}")
    print(f"  - Duplicate segments: {total_duplicates}")
    print(f"  - Absolute paths: {total_absolute}")
    if adapter:
        print(f"  - Not found on NC: {total_not_found}")

    # Fix dry-run or apply
    if args.fix_dry_run or args.fix:
        print(f"\n\n{'='*60}")
        print(f"{'🔧 FIX DRY-RUN' if args.fix_dry_run else '⚠️  APPLYING FIXES'}")
        print(f"{'='*60}")

        if args.fix:
            confirm = input("\n⚠️  This will modify the database. Continue? (yes/no): ")
            if confirm.lower() != "yes":
                print("Aborted.")
                return

        for model, name in tables:
            results = all_results[name]
            issues = results["duplicates"] + results["absolute_paths"]

            if not issues:
                continue

            print(f"\n{name}: {len(issues)} issues")

            for item in issues:
                original = item["stored_path"]
                fixed = propose_fix(original, root_path)

                if original != fixed:
                    print(f"  ID {item['id']}:")
                    print(f"    Old: {original}")
                    print(f"    New: {fixed}")

                    if args.fix:
                        record = db.query(model).filter(model.id == item["id"]).first()
                        if record:
                            record.stored_path = fixed
                            db.commit()
                            print(f"    ✅ Updated")

        if args.fix:
            print("\n✅ Fixes applied!")
        else:
            print("\n💡 Run with --fix to apply these changes")

    print("\n✅ Audit complete!")
    db.close()


if __name__ == "__main__":
    main()
