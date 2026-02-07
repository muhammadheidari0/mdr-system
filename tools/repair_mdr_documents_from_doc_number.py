from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

# Ensure project root is on import path when executed via:
# python tools/repair_mdr_documents_from_doc_number.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.models import MdrDocument
from app.db.session import SessionLocal


@dataclass
class PlannedChange:
    doc_id: int
    doc_number: str
    updates: Dict[str, str]
    before: Dict[str, str]


def _norm(value: object) -> str:
    return str(value or "").strip().upper()


def parse_doc_number(doc_number: str) -> Optional[Dict[str, str]]:
    code = _norm(doc_number)
    if not code:
        return None

    parts = code.split("-", 2)
    if len(parts) != 3:
        return None

    project_code, middle, suffix = parts
    if len(middle) < 4 or len(suffix) < 2:
        return None

    mdr_code = middle[0]
    phase_code = middle[1]
    core = middle[2:]

    # Legacy format uses 2-digit serial at the end of middle section.
    serial_match = re.search(r"(\d{2})$", core)
    if serial_match:
        package_code = core[:-2]
    else:
        # Fallback for non-standard rows.
        serial_any = re.search(r"(\d+)$", core)
        if serial_any and len(core) > len(serial_any.group(1)):
            package_code = core[:-len(serial_any.group(1))]
        else:
            package_code = core
    package_code = package_code or core
    if not package_code:
        return None

    discipline_code = package_code[:2] if len(package_code) >= 2 else ""
    block = suffix[0]
    level_code = suffix[1:]
    if not level_code:
        return None

    return {
        "project_code": project_code,
        "mdr_code": mdr_code,
        "phase_code": phase_code,
        "discipline_code": discipline_code,
        "package_code": package_code,
        "block": block,
        "level_code": level_code,
    }


def build_plan(rows: Iterable[MdrDocument]) -> tuple[list[PlannedChange], int]:
    plan: list[PlannedChange] = []
    invalid_doc_number = 0

    for row in rows:
        parsed = parse_doc_number(row.doc_number or "")
        if not parsed:
            invalid_doc_number += 1
            continue

        before = {
            "project_code": _norm(row.project_code),
            "mdr_code": _norm(row.mdr_code),
            "phase_code": _norm(row.phase_code),
            "discipline_code": _norm(row.discipline_code),
            "package_code": _norm(row.package_code),
            "block": _norm(row.block),
            "level_code": _norm(row.level_code),
        }

        updates = {k: v for k, v in parsed.items() if _norm(before.get(k)) != _norm(v)}
        if updates:
            plan.append(
                PlannedChange(
                    doc_id=row.id,
                    doc_number=row.doc_number,
                    updates=updates,
                    before=before,
                )
            )

    return plan, invalid_doc_number


def print_plan(plan: list[PlannedChange], invalid_count: int, max_rows: int) -> None:
    print("=== MDR Repair Plan (Dry Run) ===")
    print(f"Rows needing update: {len(plan)}")
    print(f"Rows skipped (invalid doc_number): {invalid_count}")
    if not plan:
        return

    show = plan[:max_rows]
    for item in show:
        print(f"\n[id={item.doc_id}] {item.doc_number}")
        for field, new_value in item.updates.items():
            old_value = item.before.get(field, "")
            print(f"  - {field}: '{old_value}' -> '{new_value}'")

    if len(plan) > len(show):
        print(f"\n... {len(plan) - len(show)} more row(s) not shown.")


def apply_plan(plan: list[PlannedChange]) -> int:
    if not plan:
        return 0

    by_id = {item.doc_id: item for item in plan}
    with SessionLocal() as db:
        rows = db.query(MdrDocument).filter(MdrDocument.id.in_(list(by_id.keys()))).all()
        for row in rows:
            item = by_id.get(row.id)
            if not item:
                continue
            for field, value in item.updates.items():
                setattr(row, field, value)
        db.commit()
    return len(plan)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repair mdr_documents metadata fields from doc_number.\n"
            "Default mode is DRY RUN (report only). Use --apply to write changes."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Apply planned updates to database.")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=200,
        help="Maximum rows to print in dry-run report (default: 200).",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = db.query(MdrDocument).order_by(MdrDocument.id.asc()).all()
        plan, invalid_count = build_plan(rows)

    print_plan(plan, invalid_count, max_rows=max(1, args.max_rows))

    if not args.apply:
        print("\nDry run finished. No data was changed.")
        return 0

    changed = apply_plan(plan)
    print(f"\nApplied updates to {changed} row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
