from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Value of type {type(value).__name__} is not JSON serializable")


def canonicalize_payload(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def sign_envelope(secret: str, envelope: dict[str, Any]) -> str:
    body = dict(envelope)
    body.pop("signature", None)
    encoded_secret = str(secret or "").encode("utf-8")
    encoded_body = canonicalize_payload(body).encode("utf-8")
    return hmac.new(encoded_secret, encoded_body, hashlib.sha256).hexdigest()


def build_signed_event(
    *,
    secret: str,
    entity: str,
    operation: str,
    payload: dict[str, Any],
    source: str = "mdr_app",
    version: int = 1,
    event_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    envelope = {
        "event_id": str(event_id or uuid4()),
        "entity": str(entity or "").strip(),
        "operation": str(operation or "").strip(),
        "version": int(version),
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
        "source": str(source or "mdr_app").strip() or "mdr_app",
        "payload": payload,
    }
    envelope["signature"] = sign_envelope(secret, envelope)
    return envelope


def verify_signed_event(secret: str, envelope: dict[str, Any]) -> bool:
    expected = sign_envelope(secret, envelope)
    provided = str(envelope.get("signature") or "").strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)
