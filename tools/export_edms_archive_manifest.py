from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.edms_export_manifest import export_archive_manifest_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Export MDR archive rows for native EDMS import.")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON output to this path.")
    parser.add_argument("--project-code", default=None, help="Optional project code filter.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max row count.")
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = export_archive_manifest_rows(db, project_code=args.project_code, limit=args.limit)

    payload = {"count": len(rows), "items": rows}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
