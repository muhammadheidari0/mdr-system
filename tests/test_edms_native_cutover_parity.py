from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_verify_edms_cutover_snapshot_tool(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps({"projects": [{"code": "T1"}], "users": [{"id": 1}]}), encoding="utf-8")
    after.write_text(json.dumps({"projects": [{"code": "T1"}], "users": [{"id": 1}]}), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "tools/verify_edms_cutover_snapshot.py", "--before", str(before), "--after", str(after)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
