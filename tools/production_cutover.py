from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mask_db_url(value: str) -> str:
    raw = str(value or "")
    if "://" not in raw:
        return raw
    try:
        parsed = urlsplit(raw)
        if "@" not in parsed.netloc:
            return raw
        auth, host = parsed.netloc.rsplit("@", 1)
        if ":" in auth:
            user, _ = auth.split(":", 1)
            masked_netloc = f"{user}:***@{host}"
        else:
            masked_netloc = f"***@{host}"
        return urlunsplit((parsed.scheme, masked_netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return raw


def _run(cmd: list[str], env: dict[str, str]) -> None:
    masked = [_mask_db_url(part) for part in cmd]
    print(f"[run] {' '.join(shlex.quote(part) for part in masked)}")
    subprocess.run(cmd, env=env, check=True)


def _resolve_python_bin() -> str:
    explicit = str(os.environ.get("CUTOVER_PYTHON", "")).strip()
    if explicit:
        return explicit

    project_root = Path(__file__).resolve().parents[1]
    venv_python = (
        project_root / ".venv" / "Scripts" / "python.exe"
        if os.name == "nt"
        else project_root / ".venv" / "bin" / "python"
    )
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _run_alembic_upgrade(python_bin: str, env: dict[str, str]) -> None:
    try:
        _run([python_bin, "-m", "alembic", "upgrade", "head"], env=env)
        return
    except subprocess.CalledProcessError:
        pass

    try:
        _run(
            [
                python_bin,
                "-c",
                "from alembic.config import main; main(argv=['upgrade','head'])",
            ],
            env=env,
        )
        return
    except subprocess.CalledProcessError:
        pass

    _run(["alembic", "upgrade", "head"], env=env)


def _base_env(postgres_url: str, *, read_only_mode: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["APP_ENV"] = str(env.get("APP_ENV") or "production")
    env["SECRET_KEY"] = str(env.get("SECRET_KEY") or "cutover-prod-secret")
    env["DATABASE_URL"] = postgres_url
    env["READ_ONLY_MODE"] = "true" if read_only_mode else "false"
    env["TEST_PROFILE"] = str(env.get("TEST_PROFILE") or "postgres_main")
    env["ADMIN_EMAIL"] = str(env.get("ADMIN_EMAIL") or "admin@mdr.local")
    env["ADMIN_PASSWORD"] = str(env.get("ADMIN_PASSWORD") or "ChangeMe#12345")
    env["TEST_ADMIN_EMAIL"] = str(env.get("TEST_ADMIN_EMAIL") or "admin@mdr.local")
    env["TEST_ADMIN_PASSWORD"] = str(env.get("TEST_ADMIN_PASSWORD") or "ChangeMe#12345")
    return env


def _health_check(python_bin: str, env: dict[str, str], *, label: str) -> None:
    code = (
        "from fastapi.testclient import TestClient; "
        "from app.main import app; "
        "c=TestClient(app); "
        "r=c.get('/api/v1/health'); "
        "body=r.json() if r.headers.get('content-type','').startswith('application/json') else {}; "
        "print('[health]', r.status_code, body); "
        "import sys; "
        "sys.exit(0 if r.status_code==200 and bool(body.get('ok')) else 1)"
    )
    print(f"[phase] health-check ({label})")
    _run([python_bin, "-c", code], env=env)


def _smoke_check(python_bin: str, env: dict[str, str]) -> None:
    print("[phase] smoke-check (read-only + UI public)")
    _run(
        [
            python_bin,
            "-m",
            "pytest",
            "-q",
            "tests/test_endpoint_fixes.py::test_read_only_mode_blocks_write_routes_but_allows_login",
            "tests/test_ui_smoke.py::test_ui_smoke_public_pages_load",
        ],
        env=env,
    )


@dataclass
class CutoverResult:
    freeze_start_utc: str
    freeze_end_utc: str
    freeze_duration_minutes: float
    freeze_budget_minutes: int
    parity_report: str
    drift_target_report: str
    drift_source_report: str
    status: str
    rollback_trigger: str | None
    rollback_required: bool
    rollback_window_days: int
    environment: str
    target_database_url_masked: str


def _write_reports(report_dir: Path, result: CutoverResult) -> None:
    json_path = report_dir / "production_cutover_report.json"
    md_path = report_dir / "production_cutover_report.md"

    payload = {
        "freeze_start_utc": result.freeze_start_utc,
        "freeze_end_utc": result.freeze_end_utc,
        "freeze_duration_minutes": result.freeze_duration_minutes,
        "freeze_budget_minutes": result.freeze_budget_minutes,
        "parity_report": result.parity_report,
        "drift_target_report": result.drift_target_report,
        "drift_source_report": result.drift_source_report,
        "status": result.status,
        "rollback_trigger": result.rollback_trigger,
        "rollback_required": result.rollback_required,
        "rollback_window_days": result.rollback_window_days,
        "environment": result.environment,
        "target_database_url": result.target_database_url_masked,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md = (
        "Production Cutover Report\n"
        f"- Environment: {result.environment}\n"
        f"- Freeze Start UTC: {result.freeze_start_utc}\n"
        f"- Freeze End UTC: {result.freeze_end_utc}\n"
        f"- Freeze Duration (min): {result.freeze_duration_minutes:.2f}\n"
        f"- Freeze Budget (min): {result.freeze_budget_minutes}\n"
        f"- Status: {result.status}\n"
        f"- Rollback Required: {result.rollback_required}\n"
        f"- Rollback Trigger: {result.rollback_trigger or '-'}\n"
        f"- Rollback Window (days): {result.rollback_window_days}\n"
        f"- Parity Report: {result.parity_report}\n"
        f"- Drift Target Report: {result.drift_target_report}\n"
        f"- Drift Source Report: {result.drift_source_report}\n"
    )
    md_path.write_text(md, encoding="utf-8")
    print(f"[artifact] {json_path}")
    print(f"[artifact] {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run production cutover order with freeze tracking.")
    parser.add_argument(
        "--sqlite-url",
        default="sqlite:///./database/mdr_project.db",
        help="SQLite source URL for ETL/parity.",
    )
    parser.add_argument(
        "--postgres-url",
        default="postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app",
        help="PostgreSQL target URL for migration and parity.",
    )
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="Directory for generated reports.",
    )
    parser.add_argument(
        "--freeze-budget-minutes",
        type=int,
        default=60,
        help="Maximum freeze duration before rollback is required.",
    )
    parser.add_argument(
        "--rollback-window-days",
        type=int,
        default=7,
        help="Retention/rollback window in days.",
    )
    args = parser.parse_args()

    python_bin = _resolve_python_bin()
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    sqlite_url = str(args.sqlite_url).strip()
    postgres_url = str(args.postgres_url).strip()

    parity_report = report_dir / "data_parity_report_cutover.json"
    drift_target_report = report_dir / "schema_drift_report_post_cutover.json"
    drift_source_report = report_dir / "schema_drift_report_source_post_cutover.json"

    freeze_start = _utc_now()
    print(f"[freeze] start={_utc_iso(freeze_start)} READ_ONLY_MODE=true")
    env_freeze = _base_env(postgres_url, read_only_mode=True)

    try:
        _run_alembic_upgrade(python_bin, env_freeze)
        _run(
            [
                python_bin,
                "tools/sqlite_to_postgres_etl.py",
                "--execute",
                "--truncate-target",
                "--postgres-url",
                postgres_url,
            ],
            env=env_freeze,
        )
        _run(
            [
                python_bin,
                "tools/data_parity_report.py",
                "--source-url",
                sqlite_url,
                "--target-url",
                postgres_url,
                "--report",
                str(parity_report),
            ],
            env=env_freeze,
        )
        _run(
            [
                python_bin,
                "tools/parity_gate.py",
                "--report",
                str(parity_report),
                "--max-count-mismatches",
                "0",
                "--max-unique-issues",
                "0",
                "--max-fk-violations",
                "0",
            ],
            env=env_freeze,
        )
        _run(
            [
                python_bin,
                "tools/schema_drift_report.py",
                "--database-url",
                postgres_url,
                "--out",
                str(drift_target_report),
                "--fail-on-warning",
            ],
            env=env_freeze,
        )
        _run(
            [
                python_bin,
                "tools/schema_drift_report.py",
                "--database-url",
                sqlite_url,
                "--out",
                str(drift_source_report),
                "--fail-on-warning",
            ],
            env=env_freeze,
        )

        _health_check(python_bin, env_freeze, label="freeze-on")
        _smoke_check(python_bin, env_freeze)
    except Exception:
        freeze_end = _utc_now()
        duration_min = (freeze_end - freeze_start).total_seconds() / 60.0
        status = "rollback_required"
        trigger = "cutover_step_failed"
        result = CutoverResult(
            freeze_start_utc=_utc_iso(freeze_start),
            freeze_end_utc=_utc_iso(freeze_end),
            freeze_duration_minutes=duration_min,
            freeze_budget_minutes=int(args.freeze_budget_minutes),
            parity_report=str(parity_report),
            drift_target_report=str(drift_target_report),
            drift_source_report=str(drift_source_report),
            status=status,
            rollback_trigger=trigger,
            rollback_required=True,
            rollback_window_days=int(args.rollback_window_days),
            environment=str(env_freeze.get("APP_ENV") or "production"),
            target_database_url_masked=_mask_db_url(postgres_url),
        )
        _write_reports(report_dir, result)
        raise

    env_unfreeze = _base_env(postgres_url, read_only_mode=False)
    _health_check(python_bin, env_unfreeze, label="freeze-off")
    freeze_end = _utc_now()
    duration_min = (freeze_end - freeze_start).total_seconds() / 60.0

    over_budget = duration_min > float(args.freeze_budget_minutes)
    status = "rollback_required" if over_budget else "go"
    trigger = "freeze_budget_exceeded" if over_budget else None

    print(f"[freeze] end={_utc_iso(freeze_end)} READ_ONLY_MODE=false")
    print(f"[freeze] duration_min={duration_min:.2f} budget_min={int(args.freeze_budget_minutes)}")

    result = CutoverResult(
        freeze_start_utc=_utc_iso(freeze_start),
        freeze_end_utc=_utc_iso(freeze_end),
        freeze_duration_minutes=duration_min,
        freeze_budget_minutes=int(args.freeze_budget_minutes),
        parity_report=str(parity_report),
        drift_target_report=str(drift_target_report),
        drift_source_report=str(drift_source_report),
        status=status,
        rollback_trigger=trigger,
        rollback_required=bool(over_budget),
        rollback_window_days=int(args.rollback_window_days),
        environment=str(env_freeze.get("APP_ENV") or "production"),
        target_database_url_masked=_mask_db_url(postgres_url),
    )
    _write_reports(report_dir, result)

    if over_budget:
        raise SystemExit("[cutover] freeze budget exceeded; rollback required.")
    print("[cutover] PASS")


if __name__ == "__main__":
    main()
