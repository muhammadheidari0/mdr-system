from __future__ import annotations

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.storage_jobs import job_payload
from app.services.storage_sync import (
    JOB_GOOGLE_DRIVE_MIRROR,
    JOB_NEXTCLOUD_MIRROR,
    ENTITY_COMM_ITEM_ATTACHMENT,
    enqueue_comm_item_mirror_job,
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
