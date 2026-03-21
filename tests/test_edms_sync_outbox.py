from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import engine
from app.services.edms_event_signing import build_signed_event, verify_signed_event
from app.services.edms_sync_outbox import build_master_data_snapshot, build_sync_envelopes


def test_edms_event_signing_roundtrip() -> None:
    envelope = build_signed_event(
        secret="secret-value",
        entity="projects",
        operation="upsert",
        payload={"projects": [{"code": "T202"}]},
    )
    assert envelope["signature"]
    assert verify_signed_event("secret-value", envelope) is True
    assert verify_signed_event("wrong-secret", envelope) is False


def test_edms_master_data_snapshot_contains_seeded_blocks() -> None:
    with Session(engine) as db:
        snapshot = build_master_data_snapshot(db)
    assert "projects" in snapshot
    assert "users" in snapshot
    assert isinstance(snapshot["permission_catalog"], list)


def test_edms_sync_envelopes_cover_all_native_targets() -> None:
    with Session(engine) as db:
        envelopes = build_sync_envelopes(db, secret="sync-secret")
    assert set(envelopes.keys()) == {"projects", "catalogs", "organizations", "users", "permissions", "scopes"}
    for envelope in envelopes.values():
        assert envelope["signature"]
