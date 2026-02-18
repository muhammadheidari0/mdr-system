from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, UploadFile

from app.services.storage_policy import policy_is_enforced, policy_size_limit_bytes

_HEAD_BYTES = 8192
_CHUNK_SIZE = 1024 * 1024

_DANGEROUS_SIGNATURE_MIMES = {
    b"MZ": "application/x-dosexec",
    b"\x7fELF": "application/x-executable",
    b"#!": "text/x-shellscript",
}

_SIGNATURE_HINTS: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"PK\x03\x04", "application/zip"),
    (b"PK\x05\x06", "application/zip"),
    (b"PK\x07\x08", "application/zip"),
    (b"AC10", "application/x-dwg"),
]

_EXTENSION_MIME_HINTS: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".xls": {
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    },
    ".zip": {"application/zip"},
    ".dxf": {"application/dxf", "image/vnd.dxf", "application/octet-stream", "text/plain"},
    ".dwg": {"application/x-dwg", "application/acad", "image/vnd.dwg", "application/octet-stream"},
    ".ifc": {"model/ifc", "application/x-step", "application/octet-stream", "text/plain"},
}


@dataclass
class ValidationOutcome:
    status: str
    detected_mime: str
    declared_mime: str
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SavedFileInfo:
    stored_path: str
    size_bytes: int
    sha256: str
    detected_mime: str
    declared_mime: str
    validation_status: str
    validation_notes: str


def _normalize_mime(value: str | None) -> str:
    return str(value or "").strip().lower()


def _normalize_ext(name: str | None) -> str:
    return Path(str(name or "")).suffix.lower().strip()


def _detect_mime_from_magic(head: bytes) -> str:
    try:
        import magic  # type: ignore

        value = magic.from_buffer(head or b"", mime=True)
    except Exception:
        return ""
    return _normalize_mime(value)


def _detect_mime_from_signatures(head: bytes, filename: str, declared_mime: str) -> str:
    for signature, mime in _DANGEROUS_SIGNATURE_MIMES.items():
        if head.startswith(signature):
            return mime
    for signature, mime in _SIGNATURE_HINTS:
        if head.startswith(signature):
            return mime
    guessed, _ = mimetypes.guess_type(filename or "")
    guessed_mime = _normalize_mime(guessed)
    if guessed_mime:
        return guessed_mime
    return _normalize_mime(declared_mime)


def _detect_mime(head: bytes, filename: str, declared_mime: str) -> str:
    detected = _detect_mime_from_magic(head)
    if detected:
        return detected
    return _detect_mime_from_signatures(head, filename, declared_mime)


def _mime_allowed_for_kind(policy: dict, file_kind: str) -> set[str]:
    kind = str(file_kind or "").strip().lower()
    if kind not in {"pdf", "native", "attachment"}:
        kind = "attachment"
    by_kind = policy.get("allowed_mimes_by_kind", {})
    values = by_kind.get(kind) if isinstance(by_kind, dict) else []
    return {str(item or "").strip().lower() for item in values if str(item or "").strip()}


def _set_from_iter(values: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for value in values:
        normalized = _normalize_mime(value)
        if normalized:
            out.add(normalized)
    return out


def evaluate_validation(
    *,
    policy: dict,
    file_name: str,
    declared_mime: str,
    detected_mime: str,
) -> ValidationOutcome:
    ext = _normalize_ext(file_name)
    blocked_extensions = {
        str(item or "").strip().lower().lstrip(".")
        for item in policy.get("blocked_extensions", [])
        if str(item or "").strip()
    }
    dangerous_mimes = _set_from_iter(policy.get("dangerous_mimes", []))
    declared = _normalize_mime(declared_mime)
    detected = _normalize_mime(detected_mime)

    issues: list[str] = []
    warnings: list[str] = []

    if ext and ext.lstrip(".") in blocked_extensions:
        issues.append(f"Blocked extension: {ext}")

    if detected and detected in dangerous_mimes:
        issues.append(f"Dangerous mime type detected: {detected}")

    extension_hints = _EXTENSION_MIME_HINTS.get(ext, set())
    if extension_hints and detected and detected not in extension_hints:
        warnings.append(
            f"Detected mime `{detected}` does not match file extension `{ext}` expectations."
        )

    if declared and detected and declared != detected:
        warnings.append(f"Declared mime `{declared}` differs from detected mime `{detected}`.")

    # Hard reject if there is an explicit dangerous indicator.
    if issues:
        return ValidationOutcome(
            status="rejected",
            detected_mime=detected,
            declared_mime=declared,
            issues=issues,
            warnings=warnings,
        )

    if warnings:
        status = "rejected" if policy_is_enforced(policy) else "warning"
        return ValidationOutcome(
            status=status,
            detected_mime=detected,
            declared_mime=declared,
            issues=[],
            warnings=warnings,
        )

    return ValidationOutcome(
        status="valid",
        detected_mime=detected,
        declared_mime=declared,
        issues=[],
        warnings=[],
    )


def save_upload_with_integrity(
    *,
    file: UploadFile,
    destination_folder: str,
    new_name: str,
    file_kind: str,
    policy: dict,
) -> SavedFileInfo:
    dest = Path(destination_folder)
    dest.mkdir(parents=True, exist_ok=True)

    file_path = dest / str(new_name)
    size_limit = policy_size_limit_bytes(policy, file_kind)
    declared_mime = _normalize_mime(getattr(file, "content_type", None))
    sha256 = hashlib.sha256()
    total_size = 0
    head = bytearray()

    try:
        if hasattr(file.file, "seek"):
            file.file.seek(0)
        with open(file_path, "wb") as stream:
            while True:
                chunk = file.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if size_limit and total_size > size_limit:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File exceeds allowed size for `{file_kind}`. "
                            f"Maximum allowed: {size_limit // (1024 * 1024)} MB."
                        ),
                    )
                stream.write(chunk)
                sha256.update(chunk)
                if len(head) < _HEAD_BYTES:
                    remaining = _HEAD_BYTES - len(head)
                    head.extend(chunk[:remaining])
    except Exception:
        if file_path.exists():
            os.remove(file_path)
        raise

    detected_mime = _detect_mime(bytes(head), str(getattr(file, "filename", "") or ""), declared_mime)
    outcome = evaluate_validation(
        policy=policy,
        file_name=str(getattr(file, "filename", "") or ""),
        declared_mime=declared_mime,
        detected_mime=detected_mime,
    )

    allowed_for_kind = _mime_allowed_for_kind(policy, file_kind)
    if outcome.status != "rejected" and allowed_for_kind and detected_mime and detected_mime not in allowed_for_kind:
        extra_warning = f"Detected mime `{detected_mime}` is not allowed for `{file_kind}`."
        if policy_is_enforced(policy):
            outcome = ValidationOutcome(
                status="rejected",
                detected_mime=detected_mime,
                declared_mime=declared_mime,
                issues=outcome.issues,
                warnings=outcome.warnings + [extra_warning],
            )
        else:
            outcome = ValidationOutcome(
                status="warning",
                detected_mime=detected_mime,
                declared_mime=declared_mime,
                issues=outcome.issues,
                warnings=outcome.warnings + [extra_warning],
            )

    if outcome.status == "rejected":
        if file_path.exists():
            os.remove(file_path)
        message_parts = outcome.issues + outcome.warnings
        raise HTTPException(status_code=422, detail="; ".join(message_parts) or "File validation rejected.")

    return SavedFileInfo(
        stored_path=str(file_path),
        size_bytes=total_size,
        sha256=sha256.hexdigest(),
        detected_mime=outcome.detected_mime or declared_mime,
        declared_mime=declared_mime,
        validation_status=outcome.status,
        validation_notes="; ".join(outcome.warnings),
    )

