from __future__ import annotations

from pathlib import Path


def test_bootstrap_offline_cli_and_tls_contract() -> None:
    script = Path("tools/bootstrap_offline.sh").read_text(encoding="utf-8")
    assert "--package-dir" in script
    assert "--tls-mode" in script
    assert "--tls-cert-file" in script
    assert "--tls-key-file" in script
    assert "--admin-password-file" in script
    assert "--postgres-password-file" in script
    assert "--secret-key-file" in script
    assert "--allow-public-acme" in script
    assert "CADDY_TLS_MODE" in script
    assert "TLS_CERT_FILE" in script
    assert "TLS_KEY_FILE" in script
    assert "sha256sum -c checksums.txt" in script
    assert "COMPOSE_FILE_NAME" in script
    assert "up -d --no-build" in script


def test_bootstrap_offline_avoids_online_dependencies() -> None:
    script = Path("tools/bootstrap_offline.sh").read_text(encoding="utf-8")
    assert "git clone" not in script
    assert "git fetch" not in script
    assert "apt-get install" not in script
    assert "up -d --build" not in script
