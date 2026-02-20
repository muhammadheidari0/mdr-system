from __future__ import annotations

from app.core.config import settings
from app.services.storage_sync import resolve_openproject_runtime


def test_openproject_tls_resolution_force_true(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", False)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "true")
    runtime = resolve_openproject_runtime({"openproject": {"enabled": True, "skip_ssl_verify": True}})
    assert runtime.get("tls_verify") is True
    assert runtime.get("skip_ssl_verify_effective") is False
    assert runtime.get("ssl_source") == "env_force"
    assert runtime.get("ssl_force_active") is True


def test_openproject_tls_resolution_force_false(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "0")
    runtime = resolve_openproject_runtime({"openproject": {"enabled": True, "skip_ssl_verify": False}})
    assert runtime.get("tls_verify") is False
    assert runtime.get("skip_ssl_verify_effective") is True
    assert runtime.get("ssl_source") == "env_force"
    assert runtime.get("ssl_force_active") is True


def test_openproject_tls_resolution_ui_setting(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", True)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    runtime = resolve_openproject_runtime({"openproject": {"enabled": True, "skip_ssl_verify": True}})
    assert runtime.get("tls_verify") is False
    assert runtime.get("skip_ssl_verify_effective") is True
    assert runtime.get("ssl_source") == "settings"
    assert runtime.get("ssl_force_active") is False


def test_openproject_tls_resolution_env_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY", False)
    monkeypatch.setattr(settings, "OPENPROJECT_TLS_VERIFY_FORCE", "")
    runtime = resolve_openproject_runtime({"openproject": {"enabled": True}})
    assert runtime.get("tls_verify") is False
    assert runtime.get("skip_ssl_verify_effective") is True
    assert runtime.get("ssl_source") == "env_default"
    assert runtime.get("ssl_force_active") is False
