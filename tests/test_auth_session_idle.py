from __future__ import annotations

import json
from datetime import datetime, timedelta
from hashlib import sha256

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.models import SettingsKV
from app.db.session import SessionLocal
from app.main import app
from tests.auth_helpers import get_test_admin_credentials


client = TestClient(app)


def _session_key(token: str) -> str:
    return f"auth.sess:{sha256(token.encode('utf-8')).hexdigest()[:48]}"


def _login_token() -> tuple[str, str]:
    email, password = get_test_admin_credentials()
    login = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, login.text
    token = str(login.json().get("access_token") or "")
    assert token
    return email, token


def _read_session_payload(token: str) -> dict[str, object]:
    with SessionLocal() as db:
        row = db.query(SettingsKV).filter(SettingsKV.key == _session_key(token)).first()
        assert row is not None
        return json.loads(str(row.value or "{}"))


def test_auth_session_idle_timeout_rejects_stale_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AUTH_IDLE_TIMEOUT_MINUTES", 20)
    email, token = _login_token()

    key = _session_key(token)
    stale_seen = datetime.utcnow() - timedelta(minutes=21)
    with SessionLocal() as db:
        row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
        if row:
            row.value = json.dumps({"email": email, "last_seen": stale_seen.isoformat(timespec="seconds")})
            row.updated_at = stale_seen
        else:
            db.add(
                SettingsKV(
                    key=key,
                    value=json.dumps({"email": email, "last_seen": stale_seen.isoformat(timespec="seconds")}),
                    updated_at=stale_seen,
                )
            )
        db.commit()

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401, response.text
    assert "inactivity" in str(response.json().get("detail") or "").lower()


def test_auth_session_idle_timeout_zero_disables_idle_expiry(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AUTH_IDLE_TIMEOUT_MINUTES", 0)
    email, token = _login_token()

    stale_seen = datetime.utcnow() - timedelta(days=7)
    with SessionLocal() as db:
        db.merge(
            SettingsKV(
                key=_session_key(token),
                value=json.dumps({"email": email, "last_seen": stale_seen.isoformat(timespec="seconds")}),
                updated_at=stale_seen,
            )
        )
        db.commit()

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}", "X-User-Activity": "1"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("idle_timeout_minutes") == 0
    assert body.get("heartbeat_interval_seconds") == 0


def test_auth_session_only_touches_on_user_activity_header(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AUTH_IDLE_TIMEOUT_MINUTES", 20)
    email, token = _login_token()
    key = _session_key(token)
    old_seen = datetime.utcnow() - timedelta(minutes=10)
    with SessionLocal() as db:
        row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
        if row:
            row.value = json.dumps({"email": email, "last_seen": old_seen.isoformat(timespec="seconds")})
            row.updated_at = old_seen
        else:
            db.add(
                SettingsKV(
                    key=key,
                    value=json.dumps({"email": email, "last_seen": old_seen.isoformat(timespec="seconds")}),
                    updated_at=old_seen,
                )
            )
        db.commit()

    passive = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert passive.status_code == 200, passive.text
    assert passive.json().get("idle_timeout_minutes") == 20
    assert passive.json().get("heartbeat_interval_seconds") == 300
    passive_payload = _read_session_payload(token)
    assert str(passive_payload.get("last_seen") or "") == old_seen.isoformat(timespec="seconds")

    active = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}", "X-User-Activity": "1"})
    assert active.status_code == 200, active.text
    active_payload = _read_session_payload(token)
    assert datetime.fromisoformat(str(active_payload.get("last_seen"))) > old_seen

    recent_seen = datetime.utcnow() - timedelta(seconds=30)
    with SessionLocal() as db:
        row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
        assert row is not None
        row.value = json.dumps({"email": email, "last_seen": recent_seen.isoformat(timespec="seconds")})
        row.updated_at = recent_seen
        db.commit()

    throttled = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}", "X-User-Activity": "1"})
    assert throttled.status_code == 200, throttled.text
    throttled_payload = _read_session_payload(token)
    assert str(throttled_payload.get("last_seen") or "") == recent_seen.isoformat(timespec="seconds")

    logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200, logout.text
    with SessionLocal() as db:
        assert db.query(SettingsKV).filter(SettingsKV.key == key).first() is None
