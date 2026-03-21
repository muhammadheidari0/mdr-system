from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_block(snapshot: dict[str, Any], key: str) -> int:
    value = snapshot.get(key)
    return len(value) if isinstance(value, list) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two native EDMS cutover snapshots.")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()

    before = _load_json(args.before)
    after = _load_json(args.after)
    keys = sorted(set(before.keys()) | set(after.keys()))
    report = []
    for key in keys:
        report.append(
            {
                "key": key,
                "before_count": _count_block(before, key),
                "after_count": _count_block(after, key),
                "match": _count_block(before, key) == _count_block(after, key),
            }
        )
    print(json.dumps({"ok": all(item["match"] for item in report), "items": report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
