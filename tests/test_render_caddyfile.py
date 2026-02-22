from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def _has_working_bash() -> bool:
    if shutil.which("bash") is None:
        return False
    try:
        probe = subprocess.run(
            ["bash", "-lc", "echo ok"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return probe.returncode == 0


@pytest.mark.skipif(not _has_working_bash(), reason="working bash is required")
def test_render_caddyfile_domain_mode(tmp_path: Path) -> None:
    output = tmp_path / "Caddyfile.domain"
    result = subprocess.run(
        [
            "bash",
            "tools/render_caddyfile.sh",
            "--domain",
            "https://esms.example.com/path",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert "esms.example.com {" in text
    assert "Strict-Transport-Security" in text


@pytest.mark.skipif(not _has_working_bash(), reason="working bash is required")
def test_render_caddyfile_ip_mode(tmp_path: Path) -> None:
    output = tmp_path / "Caddyfile.ip"
    result = subprocess.run(
        [
            "bash",
            "tools/render_caddyfile.sh",
            "--domain",
            "http://185.231.181.48:443/anything",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert ":80 {" in text
    assert "Strict-Transport-Security" not in text
