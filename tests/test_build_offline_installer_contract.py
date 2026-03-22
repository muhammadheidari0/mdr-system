from __future__ import annotations

from pathlib import Path


def test_build_offline_installer_builds_expected_artifacts() -> None:
    script = Path("tools/build_offline_installer.sh").read_text(encoding="utf-8")
    assert "--version" in script
    assert "docker build -t" in script
    assert "docker pull postgres:16-alpine" in script
    assert "docker pull caddy:2.8-alpine" in script
    assert "docker save -o" in script
    assert "mdr-offline-installer-" in script
    assert "release_manifest.env" in script
    assert "checksums.txt" in script


def test_build_offline_installer_copies_tls_templates_and_shared_runtime() -> None:
    script = Path("tools/build_offline_installer.sh").read_text(encoding="utf-8")
    assert "docker-compose.offline.yml" in script
    assert "bootstrap_offline.sh" in script
    assert "render_caddyfile.sh" in script
    assert "bootstrap_common.sh" in script
    assert "Caddyfile.http.template" in script
    assert "Caddyfile.internal.template" in script
    assert "Caddyfile.custom.template" in script
    assert "Caddyfile.public.template" in script
