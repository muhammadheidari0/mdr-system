from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def _bash_executable() -> str | None:
    candidates = [
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            probe = subprocess.run(
                [candidate, "-lc", "echo ok"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        if probe.returncode == 0:
            return candidate
    return None


def _has_working_bash() -> bool:
    return _bash_executable() is not None


@pytest.mark.skipif(not _has_working_bash(), reason="working bash is required")
def test_render_caddyfile_http_mode_for_fqdn(tmp_path: Path) -> None:
    output = tmp_path / "Caddyfile.http"
    bash = _bash_executable()
    assert bash is not None
    result = subprocess.run(
        [
            bash,
            "tools/render_caddyfile.sh",
            "--domain",
            "mdr.internal",
            "--tls-mode",
            "http",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert "http://mdr.internal {" in text
    assert "Strict-Transport-Security" not in text


@pytest.mark.skipif(not _has_working_bash(), reason="working bash is required")
def test_render_caddyfile_internal_mode(tmp_path: Path) -> None:
    output = tmp_path / "Caddyfile.internal"
    bash = _bash_executable()
    assert bash is not None
    result = subprocess.run(
        [
            bash,
            "tools/render_caddyfile.sh",
            "--domain",
            "mdr.internal",
            "--tls-mode",
            "internal",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert "tls internal" in text
    assert "mdr.internal {" in text


@pytest.mark.skipif(not _has_working_bash(), reason="working bash is required")
def test_render_caddyfile_custom_mode(tmp_path: Path) -> None:
    output = tmp_path / "Caddyfile.custom"
    bash = _bash_executable()
    assert bash is not None
    result = subprocess.run(
        [
            bash,
            "tools/render_caddyfile.sh",
            "--domain",
            "mdr.internal",
            "--tls-mode",
            "custom",
            "--tls-cert-file",
            "/opt/mdr_app/docker/certs/server.crt",
            "--tls-key-file",
            "/opt/mdr_app/docker/certs/server.key",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert "tls /opt/mdr_app/docker/certs/server.crt /opt/mdr_app/docker/certs/server.key" in text


@pytest.mark.skipif(not _has_working_bash(), reason="working bash is required")
def test_render_caddyfile_rejects_non_http_tls_mode_for_ipv4(tmp_path: Path) -> None:
    output = tmp_path / "Caddyfile.invalid"
    bash = _bash_executable()
    assert bash is not None
    result = subprocess.run(
        [
            bash,
            "tools/render_caddyfile.sh",
            "--domain",
            "185.231.181.48",
            "--tls-mode",
            "internal",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "IPv4 deployments only support --tls-mode http" in result.stderr
