from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.db.models import PowerBiApiToken
from app.db.session import SessionLocal
from app.main import app
from tests.auth_helpers import get_auth_headers
from tests.site_logs_helpers import ensure_project_discipline


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _cleanup_power_bi_tokens(name_prefix: str = "pytest-powerbi") -> None:
    with SessionLocal() as db:
        rows = db.query(PowerBiApiToken).filter(PowerBiApiToken.name.like(f"{name_prefix}%")).all()
        for row in rows:
            db.delete(row)
        db.commit()


def test_power_bi_token_show_once_read_only_revoke_and_last_used() -> None:
    headers = _admin_headers()
    project_code, _discipline_code = ensure_project_discipline(client, headers)
    _cleanup_power_bi_tokens()

    try:
        mint_res = client.post(
            "/api/v1/settings/power-bi/tokens/mint",
            json={
                "name": "pytest-powerbi-main",
                "allowed_project_codes": [project_code],
                "allowed_report_sections": ["general"],
            },
            headers=headers,
        )
        assert mint_res.status_code == 200, mint_res.text
        minted = mint_res.json()
        token = str(minted.get("token") or "")
        assert token.startswith("pbi_edms_")
        assert minted.get("item", {}).get("token_hint")
        assert "token_hash" not in minted.get("item", {})

        list_res = client.get("/api/v1/settings/power-bi/tokens", headers=headers)
        assert list_res.status_code == 200, list_res.text
        list_text = list_res.text
        assert token not in list_text
        assert "token_hash" not in list_text

        audit_res = client.get(
            "/api/v1/settings/audit-logs?action=power_bi_token.mint&page_size=1",
            headers=headers,
        )
        assert audit_res.status_code == 200, audit_res.text
        assert token not in audit_res.text

        bi_headers = {"Authorization": f"Bearer {token}"}
        csv_res = client.get(
            f"/api/v1/site-logs/reports/table.csv?project_code={project_code}&report_section=general",
            headers=bi_headers,
        )
        assert csv_res.status_code == 200, csv_res.text
        assert "text/csv" in csv_res.headers.get("content-type", "")

        item_id = int(minted.get("item", {}).get("id") or 0)
        assert item_id > 0
        with SessionLocal() as db:
            row = db.query(PowerBiApiToken).filter(PowerBiApiToken.id == item_id).first()
            assert row is not None
            first_last_used = row.last_used_at
        assert first_last_used is not None

        second_csv_res = client.get(
            f"/api/v1/site-logs/reports/table.csv?project_code={project_code}&report_section=general",
            headers=bi_headers,
        )
        assert second_csv_res.status_code == 200, second_csv_res.text
        with SessionLocal() as db:
            row = db.query(PowerBiApiToken).filter(PowerBiApiToken.id == item_id).first()
            assert row is not None
            assert row.last_used_at == first_last_used

        json_res = client.get(
            f"/api/v1/site-logs/reports/table?project_code={project_code}&report_section=general",
            headers=bi_headers,
        )
        assert json_res.status_code == 401, json_res.text

        settings_res = client.get("/api/v1/settings/power-bi/tokens", headers=bi_headers)
        assert settings_res.status_code == 401, settings_res.text

        revoke_res = client.post(f"/api/v1/settings/power-bi/tokens/{item_id}/revoke", headers=headers)
        assert revoke_res.status_code == 200, revoke_res.text

        revoked_csv_res = client.get(
            f"/api/v1/site-logs/reports/table.csv?project_code={project_code}&report_section=general",
            headers=bi_headers,
        )
        assert revoked_csv_res.status_code == 401, revoked_csv_res.text
    finally:
        _cleanup_power_bi_tokens()


def test_power_bi_token_expiry_and_report_section_scope() -> None:
    headers = _admin_headers()
    _cleanup_power_bi_tokens()

    try:
        expired_res = client.post(
            "/api/v1/settings/power-bi/tokens/mint",
            json={
                "name": "pytest-powerbi-expired",
                "expires_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
            },
            headers=headers,
        )
        assert expired_res.status_code == 200, expired_res.text
        expired_token = str(expired_res.json().get("token") or "")
        expired_csv = client.get(
            "/api/v1/site-logs/reports/table.csv?report_section=general",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert expired_csv.status_code == 401, expired_csv.text

        scoped_res = client.post(
            "/api/v1/settings/power-bi/tokens/mint",
            json={
                "name": "pytest-powerbi-section-scope",
                "allowed_report_sections": ["general"],
            },
            headers=headers,
        )
        assert scoped_res.status_code == 200, scoped_res.text
        scoped_token = str(scoped_res.json().get("token") or "")
        denied_csv = client.get(
            "/api/v1/site-logs/reports/table.csv?report_section=manpower",
            headers={"Authorization": f"Bearer {scoped_token}"},
        )
        assert denied_csv.status_code == 403, denied_csv.text
    finally:
        _cleanup_power_bi_tokens()
