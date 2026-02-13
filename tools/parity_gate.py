from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Report file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _count_mismatch_tables(report: dict[str, Any], ignored: set[str]) -> list[str]:
    tables = report.get("tables", {}) or {}
    mismatches: list[str] = []
    for table_name, row in tables.items():
        if table_name in ignored:
            continue
        if int(row.get("source_count", 0)) != int(row.get("target_count", 0)):
            mismatches.append(str(table_name))
    return sorted(mismatches)


def _unique_issue_tables(report: dict[str, Any]) -> list[str]:
    tables = report.get("tables", {}) or {}
    issues: list[str] = []
    for table_name, row in tables.items():
        source_dups = int(row.get("source_duplicate_groups", 0))
        target_dups = int(row.get("target_duplicate_groups", 0))
        if source_dups > 0 or target_dups > 0:
            issues.append(str(table_name))
    return sorted(issues)


def _fk_violation_tables(report: dict[str, Any]) -> list[str]:
    tables = report.get("tables", {}) or {}
    violations: list[str] = []
    for table_name, row in tables.items():
        fk_rows = row.get("fk_violations", []) or []
        if fk_rows:
            violations.append(str(table_name))
    return sorted(violations)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail CI if data parity report has unacceptable drift.")
    parser.add_argument("--report", required=True, help="Path to JSON report from tools/data_parity_report.py")
    parser.add_argument("--max-count-mismatches", type=int, default=0)
    parser.add_argument("--max-unique-issues", type=int, default=0)
    parser.add_argument("--max-fk-violations", type=int, default=0)
    parser.add_argument(
        "--count-mismatch-scope",
        choices=("all", "strict"),
        default="all",
        help="`all`: fail on any table mismatch, `strict`: fail only for strict tables and warn for others.",
    )
    parser.add_argument(
        "--strict-count-table",
        action="append",
        default=[],
        help="Strict table list for count mismatch scope=strict (repeatable).",
    )
    parser.add_argument(
        "--ignore-count-mismatch-table",
        action="append",
        default=[],
        help="Table name to ignore from count mismatch gate (repeatable).",
    )
    args = parser.parse_args()

    report = _load_report(Path(args.report))
    ignored = {str(name).strip() for name in (args.ignore_count_mismatch_table or []) if str(name).strip()}
    strict_tables = {str(name).strip() for name in (args.strict_count_table or []) if str(name).strip()}

    count_mismatch_tables_all = _count_mismatch_tables(report, ignored)
    count_mismatch_tables = count_mismatch_tables_all
    non_strict_count_mismatch_tables: list[str] = []
    if args.count_mismatch_scope == "strict":
        if not strict_tables:
            raise SystemExit(
                "count-mismatch-scope=strict requires at least one --strict-count-table."
            )
        count_mismatch_tables = sorted([name for name in count_mismatch_tables_all if name in strict_tables])
        non_strict_count_mismatch_tables = sorted(
            [name for name in count_mismatch_tables_all if name not in strict_tables]
        )

    unique_issue_tables = _unique_issue_tables(report)
    fk_violation_tables = _fk_violation_tables(report)

    count_mismatches = len(count_mismatch_tables)
    unique_issues = len(unique_issue_tables)
    fk_violations = int(report.get("summary", {}).get("fk_violations", 0) or 0)

    print(
        "[parity-gate]",
        f"count_scope={args.count_mismatch_scope}",
        f"strict_tables={','.join(sorted(strict_tables)) if strict_tables else '-'}",
        f"count_mismatches_all={len(count_mismatch_tables_all)}",
        f"count_mismatches={count_mismatches}",
        f"unique_issues={unique_issues}",
        f"fk_violations={fk_violations}",
    )
    if non_strict_count_mismatch_tables:
        print(
            "[parity-gate][warn]",
            "non-strict count mismatches (not failing in strict mode):",
            ", ".join(non_strict_count_mismatch_tables),
        )

    failures: list[str] = []
    if count_mismatches > args.max_count_mismatches:
        failures.append(
            f"count mismatches {count_mismatches} > {args.max_count_mismatches} "
            f"(tables: {', '.join(count_mismatch_tables)})"
        )
    if unique_issues > args.max_unique_issues:
        failures.append(
            f"unique issues {unique_issues} > {args.max_unique_issues} (tables: {', '.join(unique_issue_tables)})"
        )
    if fk_violations > args.max_fk_violations:
        failures.append(
            f"fk violations {fk_violations} > {args.max_fk_violations} (tables: {', '.join(fk_violation_tables)})"
        )

    if failures:
        for row in failures:
            print(f"[parity-gate][fail] {row}")
        raise SystemExit(2)

    print("[parity-gate] PASS")


if __name__ == "__main__":
    main()
