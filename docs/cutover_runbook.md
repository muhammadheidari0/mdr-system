# Cutover Runbook (PostgreSQL)

## Purpose

This runbook is the operational path for staging rehearsal and production cutover.
It assumes:

- SQLite source: `sqlite:///./database/mdr_project.db`
- PostgreSQL target: `postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app`
- Alembic head is current (`20260211_0003`)

## A) Staging Rehearsal

1. Freeze window start and set read-only mode for write APIs.
2. Apply schema on target:
   `alembic upgrade head`
3. Execute ETL with truncate:
   `python tools/sqlite_to_postgres_etl.py --execute --truncate-target --postgres-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app`
4. Generate parity report:
   `python tools/data_parity_report.py --source-url sqlite:///./database/mdr_project.db --target-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app --report reports/data_parity_report_cutover.json`
5. Enforce parity gate (mandatory zero mismatches):
   `python tools/parity_gate.py --report reports/data_parity_report_cutover.json --max-count-mismatches 0 --max-unique-issues 0 --max-fk-violations 0`
6. Drift gate target/source:
   `python tools/schema_drift_report.py --database-url postgresql+psycopg://mdr:mdr@localhost:5432/mdr_app --out reports/schema_drift_report_post_cutover.json --fail-on-warning`
   `python tools/schema_drift_report.py --database-url sqlite:///./database/mdr_project.db --out reports/schema_drift_report_source_post_cutover.json --fail-on-warning`
7. Run release gates:
   - backend primary tests
   - frontend `gen:api`, `typecheck`, `build`
   - critical e2e (`npm run e2e:critical`, `PW_USE_SYSTEM_CHROME=1` if browser download is blocked)

## B) Rollback Drill (Required Evidence)

Record these items in the rehearsal ticket:

- `freeze_start_utc` and `freeze_end_utc`
- pre-cutover backup/snapshot id
- rollback trigger reason (simulated or real)
- rollback start/end timestamps
- post-rollback health checks (`/api/v1/health`, smoke tests)
- total recovery duration (minutes)

Suggested markdown template:

```text
Rollback Drill Report
- Date UTC:
- Environment:
- Snapshot ID:
- Trigger:
- Rollback Start UTC:
- Rollback End UTC:
- Recovery Duration (min):
- Health Check Result:
- Smoke Result:
- Notes:
```

## C) Production Cutover Order

1. Enable read-only mode (`READ_ONLY_MODE=true`) and announce freeze start.
2. Run `alembic upgrade head`.
3. Run ETL execute + parity report + parity gate (all zero).
4. Run drift gates (target and source).
5. Run health + smoke checks.
6. Disable read-only mode (`READ_ONLY_MODE=false`) and announce freeze end.
7. Validate freeze duration: target is <= 60 minutes, otherwise rollback.

## D) Go/No-Go Criteria

Go only if all are true:

- parity gate passes with `count_mismatches=0`
- drift gates return `severity=ok`
- backend/frontend/e2e release gates are green
- rollback drill evidence exists and recovery duration is within target
- planned freeze budget remains <= 60 minutes

## E) Legacy Artifact Retention

- Keep pre-cutover snapshot + cutover reports for 7 days.
- Keep pre-cutover application image/tag for 7 days.
- Permanent cleanup of legacy artifacts is allowed after day 7 if no rollback trigger occurred.
