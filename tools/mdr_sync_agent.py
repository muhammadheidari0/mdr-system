from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


AGENT_VERSION = "2.0.0"
INDEX_FILE_NAME = "manifest.local.json"


def _sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().lower()


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": f"mdr-sync-agent/{AGENT_VERSION}",
    }


def _safe_rel_path(value: str | None, file_id: int) -> Path:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return Path(f"files/{int(file_id)}")
    chunks: list[str] = []
    for part in raw.split("/"):
        part = part.strip()
        if not part or part in {".", ".."}:
            continue
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_", ".", " "} else "-" for ch in part)
        safe = " ".join(safe.split()) or "-"
        chunks.append(safe)
    if not chunks:
        return Path(f"files/{int(file_id)}")
    return Path(*chunks)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_site_manifest(base_url: str, site_code: str, site_token: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    url = f"{base_url.rstrip('/')}/api/v1/storage/site-manifest"
    res = requests.get(
        url,
        headers=_headers(site_token),
        params={"site_code": site_code},
        timeout=60,
    )
    res.raise_for_status()
    payload = res.json()
    items = payload.get("items", [])
    return payload, items if isinstance(items, list) else []


def send_heartbeat(
    base_url: str,
    site_code: str,
    site_token: str,
    summary: dict[str, Any],
) -> None:
    url = f"{base_url.rstrip('/')}/api/v1/storage/site-agent/heartbeat"
    payload = {
        "site_code": site_code,
        "hostname": socket.gethostname(),
        "app_version": AGENT_VERSION,
        "summary": summary,
    }
    res = requests.post(url, headers=_headers(site_token), json=payload, timeout=30)
    res.raise_for_status()


def download_file(
    *,
    base_url: str,
    site_code: str,
    site_token: str,
    file_id: int,
    out_path: Path,
) -> None:
    url = f"{base_url.rstrip('/')}/api/v1/storage/site-agent/download/{int(file_id)}"
    res = requests.get(
        url,
        headers=_headers(site_token),
        params={"site_code": site_code},
        stream=True,
        timeout=180,
    )
    res.raise_for_status()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(f"{out_path.suffix}.part")
    with open(tmp_path, "wb") as stream:
        for chunk in res.iter_content(chunk_size=1024 * 1024):
            if chunk:
                stream.write(chunk)
    os.replace(tmp_path, out_path)


def _load_local_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {"files": {}, "updated_at": None}
    try:
        parsed = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"files": {}, "updated_at": None}
    if not isinstance(parsed, dict):
        return {"files": {}, "updated_at": None}
    files = parsed.get("files")
    if not isinstance(files, dict):
        files = {}
    return {"files": files, "updated_at": parsed.get("updated_at")}


def _save_local_index(index_path: Path, files: dict[str, Any]) -> None:
    payload = {"files": files, "updated_at": _now_iso(), "agent_version": AGENT_VERSION}
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class DownloadTask:
    file_id: int
    file_name: str
    relative_path: Path
    expected_hash: str
    mirror_status: str | None


def _prune_extra_files(out_dir: Path, expected_abs_paths: set[Path], *, dry_run: bool) -> int:
    removed = 0
    for root, _, files in os.walk(out_dir):
        for file_name in files:
            path = Path(root) / file_name
            if path.name == INDEX_FILE_NAME:
                continue
            if path not in expected_abs_paths:
                removed += 1
                if not dry_run:
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass

    if not dry_run:
        for root, dirs, _ in os.walk(out_dir, topdown=False):
            for dir_name in dirs:
                candidate = Path(root) / dir_name
                try:
                    if not any(candidate.iterdir()):
                        candidate.rmdir()
                except Exception:
                    pass
    return removed


def run_sync(
    *,
    base_url: str,
    site_code: str,
    site_token: str,
    out_dir: Path,
    dry_run: bool = False,
    prune: bool = False,
    max_workers: int = 4,
) -> dict[str, Any]:
    manifest_payload, manifest_items = fetch_site_manifest(base_url, site_code, site_token)
    index_path = out_dir / INDEX_FILE_NAME
    local_index = _load_local_index(index_path)
    local_files = local_index.get("files", {})
    if not isinstance(local_files, dict):
        local_files = {}

    tasks: list[DownloadTask] = []
    skipped = 0
    planned = 0
    expected_abs_paths: set[Path] = set()
    new_index: dict[str, Any] = {}

    for item in manifest_items:
        file_id = int(item.get("file_id") or 0)
        if file_id <= 0:
            continue

        rel_path = _safe_rel_path(item.get("relative_path"), file_id)
        target = out_dir / rel_path
        expected_abs_paths.add(target)
        expected_hash = str(item.get("version_hash") or item.get("sha256") or "").strip().lower()
        file_name = str(item.get("file_name") or rel_path.name or f"file_{file_id}")
        mirror_status = str(item.get("mirror_status") or "").strip() or None

        if target.exists() and expected_hash:
            current_hash = _sha256_for_file(target)
            if current_hash == expected_hash:
                skipped += 1
                new_index[str(file_id)] = {
                    "path": str(rel_path).replace("\\", "/"),
                    "sha256": current_hash,
                    "status": "cached",
                    "file_name": file_name,
                    "mirror_status": mirror_status,
                    "updated_at": _now_iso(),
                }
                continue

        planned += 1
        tasks.append(
            DownloadTask(
                file_id=file_id,
                file_name=file_name,
                relative_path=rel_path,
                expected_hash=expected_hash,
                mirror_status=mirror_status,
            )
        )

    downloaded = 0
    failed = 0
    download_errors: list[dict[str, Any]] = []

    def _execute(task: DownloadTask) -> tuple[DownloadTask, str, str]:
        target = out_dir / task.relative_path
        if dry_run:
            return task, "planned", ""
        download_file(
            base_url=base_url,
            site_code=site_code,
            site_token=site_token,
            file_id=task.file_id,
            out_path=target,
        )
        current_hash = _sha256_for_file(target)
        if task.expected_hash and current_hash != task.expected_hash:
            raise RuntimeError(
                f"Hash mismatch for file_id={task.file_id}: expected={task.expected_hash} got={current_hash}"
            )
        return task, "downloaded", current_hash

    if tasks:
        workers = max(1, min(int(max_workers or 1), 32))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_execute, task) for task in tasks]
            for future in as_completed(futures):
                try:
                    task, status, current_hash = future.result()
                    if status == "planned":
                        new_index[str(task.file_id)] = {
                            "path": str(task.relative_path).replace("\\", "/"),
                            "sha256": task.expected_hash or None,
                            "status": "planned",
                            "file_name": task.file_name,
                            "mirror_status": task.mirror_status,
                            "updated_at": _now_iso(),
                        }
                    else:
                        downloaded += 1
                        new_index[str(task.file_id)] = {
                            "path": str(task.relative_path).replace("\\", "/"),
                            "sha256": current_hash,
                            "status": "downloaded",
                            "file_name": task.file_name,
                            "mirror_status": task.mirror_status,
                            "updated_at": _now_iso(),
                        }
                except Exception as exc:
                    failed += 1
                    message = str(exc)
                    download_errors.append({"error": message})
    if dry_run:
        downloaded = 0

    # Keep previous index rows for pinned files that were skipped.
    for item in manifest_items:
        file_id = int(item.get("file_id") or 0)
        if file_id <= 0 or str(file_id) in new_index:
            continue
        rel_path = _safe_rel_path(item.get("relative_path"), file_id)
        target = out_dir / rel_path
        if target.exists():
            sha = str(item.get("version_hash") or item.get("sha256") or "").strip().lower()
            if not sha:
                try:
                    sha = _sha256_for_file(target)
                except Exception:
                    sha = ""
            new_index[str(file_id)] = {
                "path": str(rel_path).replace("\\", "/"),
                "sha256": sha or None,
                "status": "cached",
                "file_name": str(item.get("file_name") or rel_path.name),
                "mirror_status": str(item.get("mirror_status") or "").strip() or None,
                "updated_at": _now_iso(),
            }

    pruned = 0
    if prune:
        pruned = _prune_extra_files(out_dir, expected_abs_paths, dry_run=dry_run)

    if not dry_run:
        _save_local_index(index_path, new_index)
    else:
        # Keep a preview for operators even in dry-run mode.
        preview_path = out_dir / f"{INDEX_FILE_NAME}.dryrun.json"
        _save_local_index(preview_path, new_index)

    summary = {
        "site_code": site_code,
        "scope": manifest_payload.get("scope"),
        "profile_id": manifest_payload.get("profile_id"),
        "total": len(manifest_items),
        "planned": planned,
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "pruned": pruned,
        "dry_run": bool(dry_run),
        "max_workers": max(1, min(int(max_workers or 1), 32)),
        "timestamp": _now_iso(),
        "errors": download_errors[:50],
    }
    try:
        send_heartbeat(base_url, site_code, site_token, summary)
    except Exception as exc:
        summary["heartbeat_error"] = str(exc)
    return summary


def install_systemd_templates(base_dir: Path) -> dict[str, str]:
    target_dir = base_dir / "site_cache" / "systemd"
    target_dir.mkdir(parents=True, exist_ok=True)
    service_path = target_dir / "mdr-site-sync.service.example"
    timer_path = target_dir / "mdr-site-sync.timer.example"
    service_path.write_text(
        """[Unit]
Description=MDR Site Sync Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=mdr
WorkingDirectory=/opt/mdr_app
ExecStart=/usr/bin/python3 /opt/mdr_app/tools/mdr_sync_agent.py --base-url https://your-domain.com --site-code SITE_A --site-token YOUR_SITE_TOKEN --out-dir /opt/mdr_site_cache --prune --max-workers 6
""",
        encoding="utf-8",
    )
    timer_path.write_text(
        """[Unit]
Description=Run MDR Site Sync every 15 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Unit=mdr-site-sync.service

[Install]
WantedBy=timers.target
""",
        encoding="utf-8",
    )
    return {
        "service_example": str(service_path),
        "timer_example": str(timer_path),
    }


def install_windows_task_template(base_dir: Path) -> str:
    target_dir = base_dir / "site_cache" / "windows"
    target_dir.mkdir(parents=True, exist_ok=True)
    script_path = target_dir / "mdr_site_sync_task.ps1.example"
    script_path.write_text(
        """$python = "C:\\Python310\\python.exe"
$script = "C:\\mdr_app\\tools\\mdr_sync_agent.py"
$args = @(
  "--base-url", "https://your-domain.com",
  "--site-code", "SITE_A",
  "--site-token", "YOUR_SITE_TOKEN",
  "--out-dir", "D:\\MDR_Site_Cache",
  "--prune",
  "--max-workers", "6"
)
& $python $script @args
""",
        encoding="utf-8",
    )
    return str(script_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="MDR Site Cache Sync Agent (HQ -> Site one-way).")
    parser.add_argument("--base-url", required=True, help="API base URL, e.g. https://your-domain.com")
    parser.add_argument("--site-code", required=True, help="Site profile code configured in HQ settings.")
    parser.add_argument("--site-token", default="", help="Site agent token (preferred).")
    parser.add_argument("--token", default="", help="Backward-compatible alias for --site-token.")
    parser.add_argument("--out-dir", default=str(Path.home() / "MDRSiteCache"), help="Local cache folder.")
    parser.add_argument("--prune", dest="prune", action="store_true", help="Remove local files that are no longer pinned.")
    parser.add_argument("--no-prune", dest="prune", action="store_false", help="Keep old local files not in current manifest.")
    parser.set_defaults(prune=True)
    parser.add_argument("--dry-run", action="store_true", help="Plan changes only, do not download/remove files.")
    parser.add_argument("--max-workers", type=int, default=4, help="Parallel download workers (1..32).")
    parser.add_argument(
        "--install-templates",
        action="store_true",
        help="Write systemd/TaskScheduler template files next to this script and exit.",
    )
    args = parser.parse_args()

    if args.install_templates:
        base = Path(__file__).resolve().parent
        linux_paths = install_systemd_templates(base)
        windows_path = install_windows_task_template(base)
        print(
            json.dumps(
                {
                    "ok": True,
                    "templates": {
                        "linux": linux_paths,
                        "windows": windows_path,
                    },
                },
                ensure_ascii=False,
            )
        )
        return

    token = str(args.site_token or args.token or "").strip()
    if not token:
        raise SystemExit("Missing token. Use --site-token (or --token alias).")

    out_dir = Path(os.path.expanduser(str(args.out_dir))).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = run_sync(
        base_url=str(args.base_url),
        site_code=str(args.site_code).strip(),
        site_token=token,
        out_dir=out_dir,
        dry_run=bool(args.dry_run),
        prune=bool(args.prune),
        max_workers=int(args.max_workers or 1),
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
