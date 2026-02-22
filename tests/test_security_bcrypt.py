from __future__ import annotations

import pytest

from app.core import security


def test_get_password_hash_and_verify_password_roundtrip() -> None:
    password = "AdminMh3879051"
    hashed = security.get_password_hash(password)
    assert hashed.startswith("$2")
    assert security.verify_password(password, hashed) is True


def test_verify_password_returns_false_for_invalid_hash() -> None:
    assert security.verify_password("secret", "not-a-valid-bcrypt-hash") is False


def test_get_password_hash_rejects_password_longer_than_72_bytes() -> None:
    too_long = "a" * (security.MAX_BCRYPT_PASSWORD_BYTES + 1)
    with pytest.raises(ValueError, match="72-byte"):
        security.get_password_hash(too_long)
