# app/services/docnum_service.py
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import MdrDocument


def _normalize_pkg_code(discipline_code: str | None, pkg_code: str | None) -> str:
    disc = str(discipline_code or "").strip().upper()
    raw = str(pkg_code or "").strip().upper()
    if not raw:
        return "00"
    if disc and raw.startswith(disc) and len(raw) > len(disc):
        stripped = raw[len(disc) :].strip()
        if stripped:
            return stripped
    return raw


def build_doc_number_parts(
    project_code: str,
    mdr_code: str,
    phase_code: str,
    discipline_code: str,
    pkg_code: str,
    block: str,
    level: str,
) -> tuple[str, str]:
    prj = (project_code or "").strip().upper()
    mdr = (mdr_code or "").strip().upper()
    phase = (phase_code or "X").strip().upper()
    disc = (discipline_code or "").strip().upper()
    pkg = _normalize_pkg_code(disc, pkg_code)
    blk = (block or "").strip().upper()
    lvl = (level or "").strip().upper()
    prefix_part = f"{prj}-{mdr}{phase}{disc}{pkg}"
    suffix_part = f"-{blk}{lvl}"
    return prefix_part, suffix_part


def generate_next_doc_number(
    db: Session,
    project_code: str,
    mdr_code: str,
    phase_code: str,
    discipline_code: str,
    pkg_code: str,
    block: str,
    level: str,
    subject_p: Optional[str] = None,
    forced_serial: Optional[int] = None,
) -> tuple[str, str]:
    """
    Generate document number in legacy format:
    PROJECT-MDR+PHASE+DISC+PKG+SERIAL-BLOCK+LEVEL
    """
    prefix_part, suffix_part = build_doc_number_parts(
        project_code=project_code,
        mdr_code=mdr_code,
        phase_code=phase_code,
        discipline_code=discipline_code,
        pkg_code=pkg_code,
        block=block,
        level=level,
    )

    # Subject uniqueness is resolved by metadata existence check before this function.
    # Keep parameter for backward-compatible call sites.
    _ = subject_p

    # Scenario 1: Forced/manual serial.
    if forced_serial is not None:
        serial_str = f"{forced_serial:02d}"
        return f"{prefix_part}{serial_str}{suffix_part}", serial_str

    # Scenario 2: Allocate next max serial in the same coding scope.
    search_pattern = f"{prefix_part}%{suffix_part}"
    last_docs = (
        db.query(MdrDocument.doc_number)
        .filter(MdrDocument.doc_number.like(search_pattern))
        .all()
    )

    max_serial = 0

    for (doc_num,) in last_docs:
        try:
            full = str(doc_num or "").strip().upper()
            if not full.startswith(prefix_part):
                continue
            middle = full[len(prefix_part) :]
            if suffix_part and middle.endswith(suffix_part):
                middle = middle[: -len(suffix_part)]
            if not re.fullmatch(r"\d+", middle or ""):
                continue
            current_s = int(middle)
            if current_s > max_serial:
                max_serial = current_s
        except Exception:
            continue

    next_serial = max_serial + 1
    serial_str = f"{next_serial:02d}"
    final_doc_num = f"{prefix_part}{serial_str}{suffix_part}"
    return final_doc_num, serial_str


def generate_subjectless_doc_number(
    db: Session,
    project_code: str,
    mdr_code: str,
    phase_code: str,
    discipline_code: str,
    pkg_code: str,
    block: str,
    level: str,
    start_serial: int = 1,
) -> tuple[str, str]:
    """
    Generate doc number for subjectless rows.
    Policy: pick the first available serial starting from `start_serial` (default 01)
    inside the exact coding scope (PROJECT-MDR+PHASE+DISC+PKG + BLOCK+LEVEL).
    """
    prefix_part, suffix_part = build_doc_number_parts(
        project_code=project_code,
        mdr_code=mdr_code,
        phase_code=phase_code,
        discipline_code=discipline_code,
        pkg_code=pkg_code,
        block=block,
        level=level,
    )

    search_pattern = f"{prefix_part}%{suffix_part}"
    rows = (
        db.query(MdrDocument.doc_number)
        .filter(MdrDocument.doc_number.like(search_pattern))
        .all()
    )

    used_serials: set[int] = set()
    for (doc_num,) in rows:
        try:
            full = str(doc_num or "").strip().upper()
            if not full.startswith(prefix_part):
                continue
            middle = full[len(prefix_part) :]
            if suffix_part and middle.endswith(suffix_part):
                middle = middle[: -len(suffix_part)]
            if not re.fullmatch(r"\d+", middle or ""):
                continue
            used_serials.add(int(middle))
        except Exception:
            continue

    serial_int = max(1, int(start_serial or 1))
    while serial_int in used_serials:
        serial_int += 1

    serial_str = f"{serial_int:02d}"
    return f"{prefix_part}{serial_str}{suffix_part}", serial_str
