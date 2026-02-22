from __future__ import annotations

import pytest

import create_admin


def test_read_admin_config_accepts_password_up_to_72_bytes(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_FULL_NAME", "System Administrator")
    monkeypatch.setenv("ADMIN_PASSWORD", "a" * 72)

    email, full_name, password, generated = create_admin._read_admin_config()
    assert email == "admin@example.com"
    assert full_name == "System Administrator"
    assert password == "a" * 72
    assert generated is False


def test_read_admin_config_rejects_password_over_72_utf8_bytes(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "a" * 73)
    with pytest.raises(ValueError, match="72-byte"):
        create_admin._read_admin_config()


def test_read_admin_config_rejects_multibyte_password_over_72_bytes(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "آ" * 37)  # 74 bytes in UTF-8
    with pytest.raises(ValueError, match="72-byte"):
        create_admin._read_admin_config()
