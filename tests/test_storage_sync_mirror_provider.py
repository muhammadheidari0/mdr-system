from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.storage_jobs import job_payload
from app.services.storage_sync import (
    JOB_GOOGLE_DRIVE_MIRROR,
    JOB_NEXTCLOUD_MIRROR,
    ENTITY_COMM_ITEM_ATTACHMENT,
    enqueue_comm_item_mirror_job,
    process_job,
    resolve_mirror_enqueue_plan,
)


def _base_integrations() -> dict:
    return {
        "mirror": {"provider": "none"},
        "google_drive": {"enabled": False},
        "openproject": {"enabled": False},
        "nextcloud": {"enabled": False},
        "local_cache": {"enabled": True},
    }


def test_resolve_mirror_enqueue_plan_none() -> None:
    plan = resolve_mirror_enqueue_plan(_base_integrations())
    assert plan.get("provider") is None
    assert plan.get("status") == "disabled"
    assert plan.get("enqueue") is False
    assert plan.get("job_type") is None


def test_resolve_mirror_enqueue_plan_google_drive(monkeypatch) -> None:
    integrations = _base_integrations()
    integrations["mirror"]["provider"] = "google_drive"
    integrations["google_drive"]["enabled"] = True

    monkeypatch.setattr(settings, "GDRIVE_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    plan = resolve_mirror_enqueue_plan(integrations)
    assert plan.get("provider") == "google_drive"
    assert plan.get("status") == "pending"
    assert plan.get("enqueue") is True
    assert plan.get("job_type") == JOB_GOOGLE_DRIVE_MIRROR

    monkeypatch.setattr(settings, "GDRIVE_SERVICE_ACCOUNT_JSON", "")
    disabled_plan = resolve_mirror_enqueue_plan(integrations)
    assert disabled_plan.get("provider") == "google_drive"
    assert disabled_plan.get("status") == "disabled"
    assert disabled_plan.get("enqueue") is False
    assert disabled_plan.get("job_type") is None


def test_resolve_mirror_enqueue_plan_nextcloud(monkeypatch) -> None:
    integrations = _base_integrations()
    integrations["mirror"]["provider"] = "nextcloud"
    integrations["nextcloud"] = {
        "enabled": True,
        "base_url": "https://nextcloud.example.com",
        "username": "nc-user",
        "app_password": "nc-pass",
        "root_path": "/mdr",
    }
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")

    plan = resolve_mirror_enqueue_plan(integrations)
    assert plan.get("provider") == "nextcloud"
    assert plan.get("status") == "pending"
    assert plan.get("enqueue") is True
    assert plan.get("job_type") == JOB_NEXTCLOUD_MIRROR


def test_enqueue_comm_item_mirror_job_uses_active_provider(monkeypatch) -> None:
    base = _base_integrations()
    monkeypatch.setattr(settings, "GDRIVE_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")

    # none provider => no enqueue
    monkeypatch.setattr("app.services.storage_sync.get_storage_integrations", lambda _db: base)
    with SessionLocal() as db:
        job = enqueue_comm_item_mirror_job(db, attachment_id=1001)
        assert job is None
        db.rollback()

    # google provider => google job
    google_cfg = {
        **base,
        "mirror": {"provider": "google_drive"},
        "google_drive": {"enabled": True},
    }
    monkeypatch.setattr("app.services.storage_sync.get_storage_integrations", lambda _db: google_cfg)
    with SessionLocal() as db:
        job = enqueue_comm_item_mirror_job(db, attachment_id=1002)
        assert job is not None
        assert str(job.job_type) == JOB_GOOGLE_DRIVE_MIRROR
        payload = job_payload(job)
        assert payload.get("entity_type") == ENTITY_COMM_ITEM_ATTACHMENT
        assert int(payload.get("entity_id") or 0) == 1002
        assert payload.get("mirror_provider") == "google_drive"
        db.rollback()

    # nextcloud provider => nextcloud job
    nextcloud_cfg = {
        **base,
        "mirror": {"provider": "nextcloud"},
        "nextcloud": {
            "enabled": True,
            "base_url": "https://nextcloud.example.com",
            "username": "nc-user",
            "app_password": "nc-pass",
            "root_path": "/mdr",
        },
    }
    monkeypatch.setattr("app.services.storage_sync.get_storage_integrations", lambda _db: nextcloud_cfg)
    with SessionLocal() as db:
        job = enqueue_comm_item_mirror_job(db, attachment_id=1003)
        assert job is not None
        assert str(job.job_type) == JOB_NEXTCLOUD_MIRROR
        payload = job_payload(job)
        assert payload.get("entity_type") == ENTITY_COMM_ITEM_ATTACHMENT
        assert int(payload.get("entity_id") or 0) == 1003
        assert payload.get("mirror_provider") == "nextcloud"
        db.rollback()


def test_enqueue_comm_item_mirror_job_skips_nextcloud_mirror_for_nextcloud_primary(monkeypatch) -> None:
    base = _base_integrations()
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")

    nextcloud_cfg = {
        **base,
        "mirror": {"provider": "nextcloud"},
        "nextcloud": {
            "enabled": True,
            "base_url": "https://nextcloud.example.com",
            "username": "nc-user",
            "app_password": "nc-pass",
            "root_path": "/mdr",
            "mode": "webdav",
        },
    }
    monkeypatch.setattr("app.services.storage_sync.get_storage_integrations", lambda _db: nextcloud_cfg)
    monkeypatch.setattr(
        "app.services.storage_sync._row_uses_nextcloud_primary_storage",
        lambda *_args, **_kwargs: True,
    )

    with SessionLocal() as db:
        job = enqueue_comm_item_mirror_job(db, attachment_id=1101)
        assert job is None
        db.rollback()


def test_enqueue_comm_item_mirror_job_keeps_google_mirror_for_nextcloud_primary(monkeypatch) -> None:
    base = _base_integrations()
    monkeypatch.setattr(settings, "GDRIVE_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')

    google_cfg = {
        **base,
        "mirror": {"provider": "google_drive"},
        "google_drive": {"enabled": True},
        "nextcloud": {
            "enabled": True,
            "base_url": "https://nextcloud.example.com",
            "username": "nc-user",
            "app_password": "nc-pass",
            "root_path": "/mdr",
            "mode": "webdav",
        },
    }
    monkeypatch.setattr("app.services.storage_sync.get_storage_integrations", lambda _db: google_cfg)
    monkeypatch.setattr(
        "app.services.storage_sync._row_uses_nextcloud_primary_storage",
        lambda *_args, **_kwargs: True,
    )

    with SessionLocal() as db:
        job = enqueue_comm_item_mirror_job(db, attachment_id=1102)
        assert job is not None
        assert str(job.job_type) == JOB_GOOGLE_DRIVE_MIRROR
        payload = job_payload(job)
        assert payload.get("mirror_provider") == "google_drive"
        db.rollback()


def test_process_google_drive_mirror_downloads_webdav_primary_source(monkeypatch) -> None:
    integrations = {
        **_base_integrations(),
        "mirror": {"provider": "google_drive"},
        "google_drive": {"enabled": True, "root_folder_id": "root-folder"},
        "nextcloud": {
            "enabled": True,
            "base_url": "https://nextcloud.example.com",
            "username": "nc-user",
            "app_password": "nc-pass",
            "root_path": "/ARCA-NTN",
            "mode": "webdav",
        },
    }
    monkeypatch.setattr(settings, "GDRIVE_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    monkeypatch.setattr(settings, "GDRIVE_SHARED_DRIVE_ID", "")

    fake_row = SimpleNamespace(
        id=501,
        mirror_provider=None,
        mirror_remote_id=None,
        mirror_remote_url=None,
        mirror_status="pending",
        mirror_updated_at=None,
        gdrive_file_id=None,
    )
    monkeypatch.setattr(
        "app.services.storage_sync._resolve_entity_file",
        lambda *_args, **_kwargs: (
            "webdav://ARCA-NTN/comm-items/E2E/GN/RFI/2026/04/test-file.pdf",
            "test-file.pdf",
            "application/pdf",
            fake_row,
        ),
    )
    monkeypatch.setattr(
        "app.services.storage_sync._mirror_relative_path",
        lambda *_args, **_kwargs: "comm-items/E2E/GN/RFI/2026/04/test-file.pdf",
    )

    downloaded: dict[str, str] = {}
    uploaded: dict[str, str] = {}

    class _FakeNextcloudAdapter:
        def __init__(self, **kwargs):
            downloaded["root_path"] = str(kwargs.get("root_path") or "")

        def download_file_stream(self, remote_relative_path: str):
            downloaded["remote_relative_path"] = remote_relative_path
            yield b"mirror-from-webdav"

    class _FakeGoogleDriveAdapter:
        def __init__(self, **kwargs):
            uploaded["root_folder_id"] = str(kwargs.get("root_folder_id") or "")

        def upload_file(self, *, local_path: str, display_name: str, mime_type: str, folder_path: str | None = None, folder_id: str | None = None):
            uploaded["local_path"] = local_path
            uploaded["display_name"] = display_name
            uploaded["mime_type"] = mime_type
            uploaded["folder_path"] = str(folder_path or "")
            uploaded["content"] = Path(local_path).read_bytes().decode("utf-8")
            return {"file_id": "gd-501", "web_view_link": "https://drive.example/file/gd-501"}

    monkeypatch.setattr("app.services.storage_sync.NextcloudAdapter", _FakeNextcloudAdapter)
    monkeypatch.setattr("app.services.storage_sync.GoogleDriveAdapter", _FakeGoogleDriveAdapter)

    job = SimpleNamespace(
        job_type=JOB_GOOGLE_DRIVE_MIRROR,
        payload_json=json.dumps(
            {
                "entity_type": ENTITY_COMM_ITEM_ATTACHMENT,
                "entity_id": 501,
                "mirror_provider": "google_drive",
            }
        ),
    )

    with SessionLocal() as db:
        result = process_job(db, job, integrations)

    assert result.get("status") == "mirrored"
    assert downloaded.get("root_path") == "/ARCA-NTN"
    assert downloaded.get("remote_relative_path") == "ARCA-NTN/comm-items/E2E/GN/RFI/2026/04/test-file.pdf"
    assert uploaded.get("display_name") == "test-file.pdf"
    assert uploaded.get("mime_type") == "application/pdf"
    assert uploaded.get("folder_path") == "comm-items/E2E/GN/RFI/2026/04"
    assert uploaded.get("content") == "mirror-from-webdav"
    assert not Path(str(uploaded.get("local_path") or "")).exists()
    assert fake_row.mirror_provider == "google_drive"
    assert fake_row.mirror_status == "mirrored"
    assert fake_row.gdrive_file_id == "gd-501"


def test_process_nextcloud_mirror_disables_stale_job_for_nextcloud_primary(monkeypatch) -> None:
    integrations = {
        **_base_integrations(),
        "mirror": {"provider": "nextcloud"},
        "nextcloud": {
            "enabled": True,
            "base_url": "https://nextcloud.example.com",
            "username": "nc-user",
            "app_password": "nc-pass",
            "root_path": "/ARCA-NTN",
            "mode": "webdav",
        },
    }
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")

    fake_row = SimpleNamespace(
        id=601,
        mirror_provider=None,
        mirror_remote_id=None,
        mirror_remote_url=None,
        mirror_status="pending",
        mirror_updated_at=None,
        gdrive_file_id=None,
    )
    monkeypatch.setattr(
        "app.services.storage_sync._resolve_entity_file",
        lambda *_args, **_kwargs: (
            "webdav://ARCA-NTN/comm-items/E2E/GN/RFI/2026/04/test-file.pdf",
            "test-file.pdf",
            "application/pdf",
            fake_row,
        ),
    )
    monkeypatch.setattr(
        "app.services.storage_sync._row_uses_nextcloud_primary_storage",
        lambda *_args, **_kwargs: True,
    )

    class _FailIfConstructed:
        def __init__(self, **_kwargs):
            raise AssertionError("Nextcloud mirror adapter should not be constructed for nextcloud primary rows")

    monkeypatch.setattr("app.services.storage_sync.NextcloudAdapter", _FailIfConstructed)

    job = SimpleNamespace(
        job_type=JOB_NEXTCLOUD_MIRROR,
        payload_json=json.dumps(
            {
                "entity_type": ENTITY_COMM_ITEM_ATTACHMENT,
                "entity_id": 601,
                "mirror_provider": "nextcloud",
            }
        ),
    )

    with SessionLocal() as db:
        result = process_job(db, job, integrations)

    assert result.get("status") == "disabled"
    assert result.get("reason") == "primary_nextcloud"
    assert fake_row.mirror_provider == "nextcloud"
    assert fake_row.mirror_status == "disabled"
