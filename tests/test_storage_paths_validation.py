from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.storage import StorageManager
from tests.auth_helpers import get_auth_headers

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _read_paths(headers: dict[str, str]) -> dict:
    response = client.get("/api/v1/settings/storage-paths", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("ok") is True
    return body


def _restore_paths(headers: dict[str, str], before: dict) -> None:
    payload = {
        "mdr_storage_path": str(before.get("mdr_storage_path") or "./files/technical"),
        "correspondence_storage_path": str(
            before.get("correspondence_storage_path") or "./files/correspondence"
        ),
    }
    response = client.post("/api/v1/settings/storage-paths", json=payload, headers=headers)
    assert response.status_code == 200, response.text


def test_storage_paths_reject_relative_when_absolute_required(monkeypatch, tmp_path: Path) -> None:
    headers = _admin_headers()
    before = _read_paths(headers)
    allowed_root = (tmp_path / "allowed").resolve()
    allowed_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", str(allowed_root))
    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)

    response = client.post(
        "/api/v1/settings/storage-paths",
        json={
            "mdr_storage_path": "./files/technical",
            "correspondence_storage_path": str((allowed_root / "correspondence").resolve()),
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    detail = response.json().get("detail") or []
    assert any(
        str(item.get("field") or "") == "mdr_storage_path"
        and str(item.get("code") or "") == "path_not_absolute"
        for item in detail
        if isinstance(item, dict)
    )

    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", False)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)
    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", "")
    _restore_paths(headers, before)


def test_storage_paths_reject_outside_allowed_roots(monkeypatch, tmp_path: Path) -> None:
    headers = _admin_headers()
    before = _read_paths(headers)
    allowed_root = (tmp_path / "allowed").resolve()
    outside_root = (tmp_path / "outside").resolve()
    allowed_root.mkdir(parents=True, exist_ok=True)
    outside_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", str(allowed_root))
    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)

    response = client.post(
        "/api/v1/settings/storage-paths",
        json={
            "mdr_storage_path": str((outside_root / "technical").resolve()),
            "correspondence_storage_path": str((allowed_root / "correspondence").resolve()),
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    detail = response.json().get("detail") or []
    assert any(
        str(item.get("field") or "") == "mdr_storage_path"
        and str(item.get("code") or "") == "path_outside_allowed_roots"
        for item in detail
        if isinstance(item, dict)
    )

    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", False)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)
    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", "")
    _restore_paths(headers, before)


def test_storage_paths_reject_non_writable_path(monkeypatch, tmp_path: Path) -> None:
    headers = _admin_headers()
    before = _read_paths(headers)
    allowed_root = (tmp_path / "allowed").resolve()
    allowed_root.mkdir(parents=True, exist_ok=True)
    not_a_directory = allowed_root / "locked.txt"
    not_a_directory.write_text("locked", encoding="utf-8")

    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", str(allowed_root))
    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", True)

    response = client.post(
        "/api/v1/settings/storage-paths",
        json={
            "mdr_storage_path": str(not_a_directory.resolve()),
            "correspondence_storage_path": str((allowed_root / "correspondence").resolve()),
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    detail = response.json().get("detail") or []
    assert any(
        str(item.get("field") or "") == "mdr_storage_path"
        and str(item.get("code") or "") == "path_not_writable"
        for item in detail
        if isinstance(item, dict)
    )

    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", False)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)
    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", "")
    _restore_paths(headers, before)


def test_storage_paths_accept_absolute_writable_under_allowed_roots(monkeypatch, tmp_path: Path) -> None:
    headers = _admin_headers()
    before = _read_paths(headers)
    allowed_root = (tmp_path / "allowed").resolve()
    allowed_root.mkdir(parents=True, exist_ok=True)
    mdr_path = (allowed_root / "technical").resolve()
    corr_path = (allowed_root / "correspondence").resolve()

    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", str(allowed_root))
    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", True)

    try:
        response = client.post(
            "/api/v1/settings/storage-paths",
            json={
                "mdr_storage_path": str(mdr_path),
                "correspondence_storage_path": str(corr_path),
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("ok") is True
        assert str(body.get("mdr_storage_path") or "") == str(mdr_path)
        assert str(body.get("correspondence_storage_path") or "") == str(corr_path)
    finally:
        monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", False)
        monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)
        monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", "")
        _restore_paths(headers, before)


def test_storage_validate_unc_path_under_unc_allowed_root(monkeypatch) -> None:
    unc_root = r"\\192.168.5.5\share"
    unc_target = r"\\192.168.5.5\share\technical"
    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", unc_root)
    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", True)
    monkeypatch.setattr(StorageManager, "_probe_writable", staticmethod(lambda _path: None))

    normalized, errors = StorageManager.validate_storage_path(unc_target, field="mdr_storage_path")
    assert errors == []
    assert normalized.lower().startswith(unc_root.lower())


def test_storage_validate_unc_path_reject_when_unc_root_not_allowed(monkeypatch) -> None:
    unc_target = r"\\192.168.5.5\share\technical"
    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", str(Path(settings.BASE_DIR).resolve()))
    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", False)

    _, errors = StorageManager.validate_storage_path(unc_target, field="mdr_storage_path")
    assert any(
        str(item.get("code") or "") == "path_outside_allowed_roots"
        for item in errors
        if isinstance(item, dict)
    )


def test_storage_validate_unc_path_uses_credentials_for_mount(monkeypatch) -> None:
    unc_root = r"\\192.168.5.5\share"
    unc_target = r"\\192.168.5.5\share\technical"
    calls: list[tuple[str, str, str]] = []

    def _fake_mount(*, unc_path: str, username: str, password: str) -> None:
        calls.append((unc_path, username, password))

    monkeypatch.setattr(settings, "STORAGE_ALLOWED_ROOTS", unc_root)
    monkeypatch.setattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True)
    monkeypatch.setattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", True)
    monkeypatch.setattr(StorageManager, "_ensure_unc_connected_with_credentials", classmethod(lambda cls, **kwargs: _fake_mount(**kwargs)))
    monkeypatch.setattr(StorageManager, "_probe_writable", staticmethod(lambda _path: None))

    normalized, errors = StorageManager.validate_storage_path(
        unc_target,
        field="mdr_storage_path",
        network_username=r"DOMAIN\svc_mdr",
        network_password="secret",
    )
    assert errors == []
    assert normalized.lower().startswith(unc_root.lower())
    assert calls == [(normalized, r"DOMAIN\svc_mdr", "secret")]
