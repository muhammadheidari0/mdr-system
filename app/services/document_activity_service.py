from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import DocumentActivity, MdrDocument


def _to_json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def serialize_document_snapshot(document: MdrDocument | None) -> dict[str, Any] | None:
    if not document:
        return None
    return {
        "id": int(document.id or 0),
        "doc_number": str(document.doc_number or "").strip(),
        "doc_title_e": document.doc_title_e,
        "doc_title_p": document.doc_title_p,
        "subject": document.subject,
        "project_code": document.project_code,
        "phase_code": document.phase_code,
        "discipline_code": document.discipline_code,
        "package_code": document.package_code,
        "block": document.block,
        "level_code": document.level_code,
        "mdr_code": document.mdr_code,
        "notes": document.notes,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
        "deleted_at": document.deleted_at.isoformat() if document.deleted_at else None,
    }


def log_document_activity(
    db: Session,
    document_id: int,
    action: str,
    user: Any,
    detail: str | None = None,
    before_data: Any = None,
    after_data: Any = None,
) -> DocumentActivity:
    row = DocumentActivity(
        document_id=int(document_id),
        action=str(action or "").strip()[:64],
        detail=str(detail or "").strip() or None,
        before_json=_to_json_text(before_data),
        after_json=_to_json_text(after_data),
        actor_user_id=getattr(user, "id", None),
        actor_name=getattr(user, "full_name", None) or getattr(user, "email", None),
        actor_email=getattr(user, "email", None),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row
