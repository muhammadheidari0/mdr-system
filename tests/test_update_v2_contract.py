from __future__ import annotations

from pathlib import Path


def test_update_v2_cli_contract_and_exit_codes() -> None:
    script = Path("update.sh").read_text(encoding="utf-8")
    assert "--latest" in script
    assert "--rollback" in script
    assert "--session-id" in script
    assert "--min-free-gb" in script
    assert "--dry-run" in script
    assert "--no-auto-rollback" in script
    assert "EXIT_TAG_NOT_FOUND=2" in script
    assert "EXIT_ENV_INVALID=3" in script
    assert "EXIT_HEALTH_FAIL=4" in script
    assert "EXIT_DOCKER_PERMISSION=5" in script
    assert "EXIT_DISK_GUARD=6" in script
    assert "EXIT_ROLLBACK_FAILED=7" in script


def test_update_v2_has_preflight_stash_force_checkout_and_rollback() -> None:
    script = Path("update.sh").read_text(encoding="utf-8")
    assert "self_chmod_tools()" in script
    assert "acquire_lock()" in script
    assert "configure_docker_cmd()" in script
    assert "check_disk_guard()" in script
    assert "validate_env_contract()" in script
    assert "git stash push -u -m" in script
    assert "git checkout -f --detach" in script
    assert "render_caddyfile_required" in script
    assert "rollback_from_session_file" in script
    assert "find_last_deployed_session" in script
    assert "public health check failed (warning only)" in script
