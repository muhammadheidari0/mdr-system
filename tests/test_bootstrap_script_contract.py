from __future__ import annotations

from pathlib import Path


def test_bootstrap_script_contains_reset_db_and_admin_sync_contract() -> None:
    script = Path("tools/bootstrap_ubuntu2404.sh").read_text(encoding="utf-8")
    assert "--reset-db" in script
    assert "sync_admin_account()" in script
    assert "exec -T \\" in script
    assert "CADDYFILE_PATH" in script
    assert "public_health_url" in script


def test_bootstrap_help_mentions_reset_db() -> None:
    script = Path("tools/bootstrap_ubuntu2404.sh").read_text(encoding="utf-8")
    assert "--reset-db                  Drop compose volumes and purge postgres data directory" in script
