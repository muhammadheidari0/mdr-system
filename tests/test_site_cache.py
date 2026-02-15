from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _create_site_profile(admin_headers: dict[str, str]) -> tuple[int, str]:
    code = f"SITE_{uuid.uuid4().hex[:8].upper()}"
    response = client.post(
        "/api/v1/settings/site-cache/profiles/upsert",
        json={
            "code": code,
            "name": f"Site {code}",
            "project_code": "TSEED",
            "local_root_path": r"\\\\site-server\\mdr_cache",
            "fallback_mode": "local_first",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    return int(payload.get("item", {}).get("id") or 0), code


def _delete_site_profile(admin_headers: dict[str, str], profile_id: int) -> None:
    client.post(
        "/api/v1/settings/site-cache/profiles/delete",
        json={"id": int(profile_id), "hard_delete": True},
        headers=admin_headers,
    )


def test_site_cache_profile_rule_token_manifest_and_context_contract() -> None:
    admin_headers = get_auth_headers(client)
    profile_id = 0
    site_code = ""
    minted_token = ""
    try:
        profile_id, site_code = _create_site_profile(admin_headers)
        assert profile_id > 0

        cidr_response = client.post(
            "/api/v1/settings/site-cache/cidrs/upsert",
            json={"profile_id": profile_id, "cidr": "10.88.0.0/16", "is_active": True},
            headers=admin_headers,
        )
        assert cidr_response.status_code == 200, cidr_response.text

        rule_response = client.post(
            "/api/v1/settings/site-cache/rules/upsert",
            json={
                "profile_id": profile_id,
                "name": "IFA/IFC only",
                "project_code": "TSEED",
                "status_codes": "IFA,IFC",
                "include_native": False,
                "primary_only": True,
                "latest_revision_only": True,
                "priority": 10,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert rule_response.status_code == 200, rule_response.text

        mint_response = client.post(
            "/api/v1/settings/site-cache/tokens/mint",
            json={"profile_id": profile_id, "description": "pytest token"},
            headers=admin_headers,
        )
        assert mint_response.status_code == 200, mint_response.text
        minted_token = str(mint_response.json().get("token") or "").strip()
        assert minted_token

        dry_run_rebuild = client.post(
            "/api/v1/settings/site-cache/rebuild-pins",
            json={"profile_id": profile_id, "dry_run": True},
            headers=admin_headers,
        )
        assert dry_run_rebuild.status_code == 200, dry_run_rebuild.text
        assert dry_run_rebuild.json().get("ok") is True

        site_headers = {"Authorization": f"Bearer {minted_token}"}
        manifest_response = client.get(
            "/api/v1/storage/site-manifest",
            params={"site_code": site_code},
            headers=site_headers,
        )
        assert manifest_response.status_code == 200, manifest_response.text
        manifest_payload = manifest_response.json()
        assert manifest_payload.get("ok") is True
        assert manifest_payload.get("site_code") == site_code
        assert isinstance(manifest_payload.get("items"), list)

        heartbeat_response = client.post(
            "/api/v1/storage/site-agent/heartbeat",
            json={
                "site_code": site_code,
                "hostname": "pytest-agent",
                "summary": {"downloaded": 0, "skipped": 0, "failed": 0},
            },
            headers=site_headers,
        )
        assert heartbeat_response.status_code == 200, heartbeat_response.text
        assert heartbeat_response.json().get("ok") is True

        context_headers = dict(admin_headers)
        context_headers["X-Forwarded-For"] = "10.88.22.15"
        context_response = client.get(
            "/api/v1/storage/site-context",
            params={"project_code": "TSEED"},
            headers=context_headers,
        )
        assert context_response.status_code == 200, context_response.text
        context_payload = context_response.json()
        assert context_payload.get("site_active") is True
        assert context_payload.get("matched_cidr") == "10.88.0.0/16"
        profile_payload = context_payload.get("profile") or {}
        assert profile_payload.get("code") == site_code

        token_rows = client.get(
            "/api/v1/settings/site-cache/tokens",
            params={"profile_id": profile_id},
            headers=admin_headers,
        )
        assert token_rows.status_code == 200, token_rows.text
        rows = token_rows.json().get("items", [])
        assert rows, "Expected at least one active token"
        token_id = int(rows[0].get("id") or 0)
        assert token_id > 0

        revoke_response = client.post(
            "/api/v1/settings/site-cache/tokens/revoke",
            json={"token_id": token_id},
            headers=admin_headers,
        )
        assert revoke_response.status_code == 200, revoke_response.text
        assert revoke_response.json().get("ok") is True

        manifest_after_revoke = client.get(
            "/api/v1/storage/site-manifest",
            params={"site_code": site_code},
            headers=site_headers,
        )
        assert manifest_after_revoke.status_code == 401, manifest_after_revoke.text
    finally:
        if profile_id:
            _delete_site_profile(admin_headers, profile_id)


def test_site_cache_invalid_cidr_rejected() -> None:
    admin_headers = get_auth_headers(client)
    profile_id, _ = _create_site_profile(admin_headers)
    try:
        bad_cidr = client.post(
            "/api/v1/settings/site-cache/cidrs/upsert",
            json={"profile_id": profile_id, "cidr": "not-a-cidr", "is_active": True},
            headers=admin_headers,
        )
        assert bad_cidr.status_code == 400, bad_cidr.text
    finally:
        _delete_site_profile(admin_headers, profile_id)


def test_site_agent_download_contract_for_pinned_file() -> None:
    admin_headers = get_auth_headers(client)
    profile_id = 0
    site_code = ""
    token = ""
    doc_number = f"TSEED-EGN{uuid.uuid4().hex[:4].upper()}01-TGEN"
    document_id = 0
    file_id = 0
    try:
        register = client.post(
            "/api/v1/archive/register-document",
            data={
                "doc_number": doc_number,
                "project_code": "TSEED",
                "mdr_code": "E",
                "phase": "X",
                "discipline": "GN",
                "package": "00",
                "block": "T",
                "level": "GEN",
                "subject_e": f"Site cache {uuid.uuid4().hex[:6]}",
            },
            headers=admin_headers,
        )
        assert register.status_code == 200, register.text
        document_id = int(register.json().get("document_id") or 0)
        assert document_id > 0

        upload = client.post(
            "/api/v1/archive/upload",
            data={
                "document_id": str(document_id),
                "revision": "00",
                "status": "IFA",
                "file_kind": "pdf",
            },
            files={"file": ("site.pdf", io.BytesIO(b"%PDF-1.4\nsite-cache\n"), "application/pdf")},
            headers=admin_headers,
        )
        assert upload.status_code == 200, upload.text
        file_id = int(upload.json().get("file_id") or 0)
        assert file_id > 0

        profile_id, site_code = _create_site_profile(admin_headers)

        cidr_response = client.post(
            "/api/v1/settings/site-cache/cidrs/upsert",
            json={"profile_id": profile_id, "cidr": "10.99.0.0/16", "is_active": True},
            headers=admin_headers,
        )
        assert cidr_response.status_code == 200, cidr_response.text

        rule_response = client.post(
            "/api/v1/settings/site-cache/rules/upsert",
            json={
                "profile_id": profile_id,
                "name": "match test doc",
                "project_code": "TSEED",
                "status_codes": "IFA",
                "include_native": False,
                "primary_only": True,
                "latest_revision_only": True,
                "priority": 1,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert rule_response.status_code == 200, rule_response.text

        mint = client.post(
            "/api/v1/settings/site-cache/tokens/mint",
            json={"profile_id": profile_id},
            headers=admin_headers,
        )
        assert mint.status_code == 200, mint.text
        token = str(mint.json().get("token") or "").strip()
        assert token

        rebuild = client.post(
            "/api/v1/settings/site-cache/rebuild-pins",
            json={"profile_id": profile_id, "dry_run": False},
            headers=admin_headers,
        )
        assert rebuild.status_code == 200, rebuild.text
        assert rebuild.json().get("ok") is True

        site_headers = {"Authorization": f"Bearer {token}"}
        manifest = client.get(
            "/api/v1/storage/site-manifest",
            params={"site_code": site_code},
            headers=site_headers,
        )
        assert manifest.status_code == 200, manifest.text
        manifest_items = manifest.json().get("items", [])
        manifest_ids = {int(item.get("file_id") or 0) for item in manifest_items}
        assert file_id in manifest_ids

        download = client.get(
            f"/api/v1/storage/site-agent/download/{file_id}",
            params={"site_code": site_code},
            headers=site_headers,
        )
        assert download.status_code == 200, download.text
        assert download.content
    finally:
        if profile_id:
            _delete_site_profile(admin_headers, profile_id)
