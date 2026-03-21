from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app.db.session import SessionLocal
from app.services.edms_export_manifest import export_archive_manifest_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate native EDMS parity report from archive manifest rows.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = export_archive_manifest_rows(db)

    key_counter = Counter((row["doc_number"], row["revision"], row["file_kind"]) for row in rows)
    duplicates = [
        {"doc_number": doc_number, "revision": revision, "file_kind": file_kind, "count": count}
        for (doc_number, revision, file_kind), count in key_counter.items()
        if count > 1
    ]
    payload = {
        "row_count": len(rows),
        "duplicate_key_count": len(duplicates),
        "duplicates": duplicates,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
