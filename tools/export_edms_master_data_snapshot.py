from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.edms_sync_outbox import build_master_data_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Export master data snapshot for native EDMS sync.")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON output to this path.")
    args = parser.parse_args()

    with SessionLocal() as db:
        snapshot = build_master_data_snapshot(db)

    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
