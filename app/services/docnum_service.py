# app/services/docnum_service.py
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import MdrDocument


def _normalize_subject_for_serial(value: str | None) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06ff]", "", str(value or "").lower())


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
    prj = (project_code or "").strip().upper()
    mdr = (mdr_code or "").strip().upper()
    phase = (phase_code or "X").strip().upper()
    disc = (discipline_code or "").strip().upper()
    pkg = (pkg_code or "00").strip().upper()
    blk = (block or "").strip().upper()
    lvl = (level or "").strip().upper()
    subj_norm = _normalize_subject_for_serial(subject_p)

    prefix_part = f"{prj}-{mdr}{phase}{disc}{pkg}"
    suffix_part = f"-{blk}{lvl}"

    # Scenario 1: Forced/manual serial.
    if forced_serial is not None:
        serial_str = f"{forced_serial:02d}"
        return f"{prefix_part}{serial_str}{suffix_part}", serial_str

    # Scenario 2/3: Reuse by subject if possible; otherwise allocate next max serial.
    search_pattern = f"{prefix_part}%"
    last_docs = (
        db.query(MdrDocument.doc_number, MdrDocument.subject)
        .filter(MdrDocument.doc_number.like(search_pattern))
        .all()
    )

    max_serial = 0
    found_serial: str | None = None

    for row in last_docs:
        doc_num = row.doc_number
        try:
            start = len(prefix_part)
            remainder = doc_num[start:]
            match = re.match(r"^(\d+)", remainder)
            if not match:
                continue

            serial_str = match.group(1)
            current_s = int(serial_str)
            if current_s > max_serial:
                max_serial = current_s

            if subj_norm and found_serial is None:
                row_subj_norm = _normalize_subject_for_serial(row.subject)
                if row_subj_norm and row_subj_norm == subj_norm:
                    found_serial = serial_str
        except Exception:
            continue

    if found_serial:
        return f"{prefix_part}{found_serial}{suffix_part}", found_serial

    next_serial = max_serial + 1
    serial_str = f"{next_serial:02d}"
    final_doc_num = f"{prefix_part}{serial_str}{suffix_part}"
    return final_doc_num, serial_str
