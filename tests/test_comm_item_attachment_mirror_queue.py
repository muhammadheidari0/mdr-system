from __future__ import annotations

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.storage_jobs import job_payload
from app.services.storage_sync import (
    JOB_NEXTCLOUD_MIRROR,
    ENTITY_COMM_ITEM_ATTACHMENT,
    enqueue_comm_item_mirror_job,
)


def test_comm_item_attachment_enqueue_nextcloud_job(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEXTCLOUD_BASE_URL", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_USERNAME", "")
    monkeypatch.setattr(settings, "NEXTCLOUD_APP_PASSWORD", "")

    integrations = {
        "mirror": {"provider": "nextcloud"},
        "google_drive": {"enabled": False},
        "openproject": {"enabled": False},
        "nextcloud": {
            "enabled": True,
            "base_url": "https://nextcloud.example.com",
            "username": "nc-user",
            "app_password": "nc-pass",
            "root_path": "/mdr",
        },
        "local_cache": {"enabled": True},
    }
    monkeypatch.setattr("app.services.storage_sync.get_storage_integrations", lambda _db: integrations)

    with SessionLocal() as db:
        job = enqueue_comm_item_mirror_job(db, attachment_id=9091)
        assert job is not None
        assert str(job.job_type) == JOB_NEXTCLOUD_MIRROR
        payload = job_payload(job)
        assert payload.get("entity_type") == ENTITY_COMM_ITEM_ATTACHMENT
        assert int(payload.get("entity_id") or 0) == 9091
        assert payload.get("mirror_provider") == "nextcloud"
        db.rollback()
