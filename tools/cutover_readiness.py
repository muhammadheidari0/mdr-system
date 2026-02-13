from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], env: dict[str, str]) -> None:
    print(f"[run] {' '.join(shlex.quote(part) for part in cmd)}")
    subprocess.run(cmd, env=env, check=True)


def _npm_bin() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


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


def _base_env(postgres_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("APP_ENV", "test")
    env.setdefault("SECRET_KEY", "cutover-readiness-secret")
    env.setdefault("DATABASE_URL", postgres_url)
    env.setdefault("READ_ONLY_MODE", "false")
    env.setdefault("TEST_PROFILE", "postgres_main")
    env.setdefault("ADMIN_EMAIL", "admin@mdr.local")
    env.setdefault("ADMIN_PASSWORD", "ChangeMe#12345")
    env.setdefault("TEST_ADMIN_EMAIL", "admin@mdr.local")
    env.setdefault("TEST_ADMIN_PASSWORD", "ChangeMe#12345")
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Run cutover readiness gates end-to-end.")
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
        help="Directory for generated cutover reports.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip backend test lanes.",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend gen/typecheck/build.",
    )
    parser.add_argument(
        "--skip-e2e",
        action="store_true",
        help="Skip Playwright critical e2e lane.",
    )
    parser.add_argument(
        "--e2e-system-chrome",
        action="store_true",
        help="Set PW_USE_SYSTEM_CHROME=1 for environments that cannot download Playwright browsers.",
    )
    args = parser.parse_args()

    python_bin = _resolve_python_bin()
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    sqlite_url = str(args.sqlite_url).strip()
    postgres_url = str(args.postgres_url).strip()
    env = _base_env(postgres_url)

    parity_report = report_dir / "data_parity_report_cutover.json"
    drift_target_report = report_dir / "schema_drift_report_post_cutover.json"
    drift_source_report = report_dir / "schema_drift_report_source_post_cutover.json"

    print("[phase] 1 - data sync closure")
    _run_alembic_upgrade(python_bin, env)
    _run(
        [
            python_bin,
            "tools/sqlite_to_postgres_etl.py",
            "--execute",
            "--truncate-target",
            "--postgres-url",
            postgres_url,
        ],
        env=env,
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
        env=env,
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
        env=env,
    )

    print("[phase] 2 - schema contract lock")
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
        env=env,
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
        env=env,
    )

    if not args.skip_tests:
        print("[phase] 3 - backend release gate")
        env_pg = env.copy()
        env_pg["TEST_PROFILE"] = "postgres_main"
        env_pg["DATABASE_URL"] = postgres_url
        _run_alembic_upgrade(python_bin, env_pg)
        _run([python_bin, "create_admin.py"], env=env_pg)
        _run(
            [
                python_bin,
                "-m",
                "pytest",
                "-q",
                "test_api.py",
                "tests/test_endpoint_fixes.py",
                "tests/test_regressions.py",
                "tests/test_services.py",
                "tests/test_schema_sanity.py",
                "tests/test_db_runtime_policy.py",
                "tests/test_ui_smoke.py",
                "tests/test_no_legacy_fallbacks.py",
            ],
            env=env_pg,
        )

    if not args.skip_frontend:
        print("[phase] 4 - frontend build/api-type gate")
        npm_bin = _npm_bin()
        _run([npm_bin, "run", "gen:api"], env=env)
        _run([npm_bin, "run", "typecheck"], env=env)
        _run([npm_bin, "run", "build"], env=env)

    if not args.skip_e2e:
        print("[phase] 5 - critical e2e")
        env_e2e = env.copy()
        if args.e2e_system_chrome:
            env_e2e["PW_USE_SYSTEM_CHROME"] = "1"
        npm_bin = _npm_bin()
        _run_alembic_upgrade(python_bin, env_e2e)
        _run([python_bin, "create_admin.py"], env=env_e2e)
        _run([npm_bin, "run", "e2e:critical"], env=env_e2e)

    print("[ok] cutover readiness gates completed")
    print(f"[artifact] parity: {parity_report}")
    print(f"[artifact] drift target: {drift_target_report}")
    print(f"[artifact] drift source: {drift_source_report}")


if __name__ == "__main__":
    main()
