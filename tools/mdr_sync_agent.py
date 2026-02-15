from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests


def _safe_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "file"
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", ".", " "} else "-" for ch in raw)
    return " ".join(cleaned.split()) or "file"


def _sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def fetch_manifest(base_url: str, token: str, scope: str | None) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v1/storage/local-cache/manifest"
    params = {}
    if scope:
        params["policy_scope"] = scope
    response = requests.get(url, headers=_headers(token), params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def download_file(base_url: str, token: str, file_id: int, out_path: Path) -> None:
    url = f"{base_url.rstrip('/')}/api/v1/archive/download/{int(file_id)}"
    response = requests.get(url, headers=_headers(token), stream=True, timeout=120)
    response.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as stream:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                stream.write(chunk)


def run_sync(base_url: str, token: str, out_dir: Path, scope: str | None) -> dict[str, int]:
    manifest = fetch_manifest(base_url, token, scope)
    downloaded = 0
    skipped = 0
    failed = 0

    local_index_path = out_dir / "manifest.local.json"
    local_index: dict[str, Any] = {}
    if local_index_path.exists():
        try:
            local_index = json.loads(local_index_path.read_text(encoding="utf-8"))
            if not isinstance(local_index, dict):
                local_index = {}
        except Exception:
            local_index = {}

    for item in manifest:
        try:
            file_id = int(item.get("file_id") or 0)
            if file_id <= 0:
                continue
            name = _safe_name(str(item.get("file_name") or f"file_{file_id}"))
            expected_hash = str(item.get("version_hash") or item.get("sha256") or "").strip().lower()
            local_name = f"{file_id}_{name}"
            target = out_dir / local_name

            if target.exists() and expected_hash:
                current_hash = _sha256_for_file(target).lower()
                if current_hash == expected_hash:
                    skipped += 1
                    local_index[str(file_id)] = {
                        "path": str(target),
                        "sha256": current_hash,
                        "status": "cached",
                    }
                    continue

            download_file(base_url, token, file_id, target)
            new_hash = _sha256_for_file(target).lower()
            if expected_hash and new_hash != expected_hash:
                raise RuntimeError(
                    f"Hash mismatch for file_id={file_id}: expected={expected_hash} got={new_hash}"
                )
            downloaded += 1
            local_index[str(file_id)] = {
                "path": str(target),
                "sha256": new_hash,
                "status": "downloaded",
            }
        except Exception as exc:
            failed += 1
            local_index[str(item.get("file_id"))] = {
                "status": "failed",
                "error": str(exc),
            }

    out_dir.mkdir(parents=True, exist_ok=True)
    local_index_path.write_text(json.dumps(local_index, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"downloaded": downloaded, "skipped": skipped, "failed": failed, "total": len(manifest)}


def main() -> None:
    parser = argparse.ArgumentParser(description="MDR local cache sync agent (pin-based).")
    parser.add_argument("--base-url", required=True, help="API base URL, e.g. https://your-domain.com")
    parser.add_argument("--token", required=True, help="JWT token")
    parser.add_argument("--out-dir", default=str(Path.home() / "MDRSyncCache"), help="Local cache folder")
    parser.add_argument("--scope", default="", help="Optional policy scope")
    args = parser.parse_args()

    out_dir = Path(os.path.expanduser(str(args.out_dir)))
    summary = run_sync(
        base_url=str(args.base_url),
        token=str(args.token),
        out_dir=out_dir,
        scope=str(args.scope or "").strip() or None,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
