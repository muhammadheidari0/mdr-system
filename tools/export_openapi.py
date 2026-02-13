from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app


def export_openapi(out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    out_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI spec to JSON.")
    parser.add_argument(
        "--out",
        default="frontend/openapi.json",
        help="Output file path (default: frontend/openapi.json)",
    )
    args = parser.parse_args()

    output = export_openapi(Path(args.out))
    print(f"[ok] OpenAPI schema exported: {output}")


if __name__ == "__main__":
    main()
