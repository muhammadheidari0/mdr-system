from __future__ import annotations

from typing import Any

_SECRET_EXACT_KEYS = {
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "apikey",
}

_SECRET_SUFFIXES = (
    "_token",
    "_secret",
    "_password",
    "_api_key",
    "_apikey",
)


def _is_secret_key(key: Any) -> bool:
    text = str(key or "").strip().lower()
    if not text:
        return False
    if text in _SECRET_EXACT_KEYS:
        return True
    return any(text.endswith(part) for part in _SECRET_SUFFIXES)


def redact_secrets(value: Any, mask: str = "***") -> Any:
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_secret_key(key):
                out[key] = mask
            else:
                out[key] = redact_secrets(item, mask=mask)
        return out
    if isinstance(value, list):
        return [redact_secrets(item, mask=mask) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item, mask=mask) for item in value)
    return value
