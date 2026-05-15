from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import get_auth_headers


client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    return get_auth_headers(client)


def _ensure_block(headers: dict[str, str]) -> int:
    block_code = f"B{uuid4().hex[:4].upper()}"
    upsert_res = client.post(
        "/api/v1/settings/blocks/upsert",
        json={
            "project_code": "TSEED",
            "code": block_code,
            "name_e": f"Block {block_code}",
            "name_p": f"Block {block_code}",
            "sort_order": 10,
            "is_active": True,
        },
        headers=headers,
    )
    assert upsert_res.status_code == 200, upsert_res.text

    list_res = client.get("/api/v1/settings/blocks", headers=headers)
    assert list_res.status_code == 200, list_res.text
    block = next(
        (
            item
            for item in list_res.json().get("items", [])
            if str(item.get("project_code") or "").strip().upper() == "TSEED"
            and str(item.get("code") or "").strip().upper() == block_code
        ),
        None,
    )
    assert block is not None
    return int(block.get("id") or 0)


def test_organization_upsert_supports_multiple_contracts() -> None:
    headers = _admin_headers()
    block_id = _ensure_block(headers)
    org_code = f"ORGCT{uuid4().hex[:6].upper()}"
    org_id = 0

    try:
        create_res = client.post(
            "/api/v1/settings/organizations/upsert",
            json={
                "code": org_code,
                "name": f"Organization {org_code}",
                "org_type": "contractor",
                "is_active": True,
                "contracts": [
                    {
                        "contract_number": f"CNT-{uuid4().hex[:4].upper()}",
                        "subject": "Primary package delivery",
                        "block_id": block_id,
                    },
                    {
                        "contract_number": f"CNT-{uuid4().hex[:4].upper()}",
                        "subject": "Secondary support scope",
                    },
                ],
            },
            headers=headers,
        )
        assert create_res.status_code == 200, create_res.text
        create_body = create_res.json()
        item = create_body.get("item") or {}
        org_id = int(item.get("id") or 0)
        assert org_id > 0
        assert int(item.get("contracts_count") or 0) == 2
        contracts = item.get("contracts") or []
        assert len(contracts) == 2
        assert int(contracts[0].get("block_id") or 0) == block_id

        update_res = client.post(
            "/api/v1/settings/organizations/upsert",
            json={
                "id": org_id,
                "code": org_code,
                "name": f"Organization {org_code} Updated",
                "org_type": "contractor",
                "is_active": False,
                "contracts": [
                    {
                        "id": contracts[0]["id"],
                        "contract_number": contracts[0]["contract_number"],
                        "subject": "Primary package delivery revised",
                        "block_id": block_id,
                    },
                    {
                        "contract_number": f"CNT-{uuid4().hex[:4].upper()}",
                        "subject": "Third-party inspection scope",
                    },
                ],
            },
            headers=headers,
        )
        assert update_res.status_code == 200, update_res.text
        update_item = update_res.json().get("item") or {}
        update_contracts = update_item.get("contracts") or []
        assert len(update_contracts) == 2
        assert {contract.get("subject") for contract in update_contracts} == {
            "Primary package delivery revised",
            "Third-party inspection scope",
        }

        legacy_res = client.post(
            "/api/v1/settings/organizations/upsert",
            json={
                "id": org_id,
                "code": org_code,
                "name": f"Organization {org_code} Legacy",
                "org_type": "contractor",
                "is_active": True,
            },
            headers=headers,
        )
        assert legacy_res.status_code == 200, legacy_res.text

        list_res = client.get("/api/v1/settings/organizations?include_inactive=true", headers=headers)
        assert list_res.status_code == 200, list_res.text
        row = next(
            (entry for entry in list_res.json().get("items", []) if int(entry.get("id") or 0) == org_id),
            None,
        )
        assert row is not None
        assert bool(row.get("is_active")) is True
        assert int(row.get("contracts_count") or 0) == 2
        assert {contract.get("subject") for contract in row.get("contracts") or []} == {
            "Primary package delivery revised",
            "Third-party inspection scope",
        }
    finally:
        if org_id > 0:
            cleanup_res = client.post(
                "/api/v1/settings/organizations/delete",
                json={"id": org_id, "hard_delete": True},
                headers=headers,
            )
            assert cleanup_res.status_code == 200, cleanup_res.text
