import argparse
import sqlite3
from pathlib import Path


def has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return any(r[1] == col for r in rows)


def add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    if has_column(conn, table, col):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl};")


def ensure_unique_index(conn: sqlite3.Connection, name: str, table: str, col: str) -> None:
    dups = conn.execute(
        f"""
        SELECT {col}, COUNT(*)
        FROM {table}
        WHERE {col} IS NOT NULL
        GROUP BY {col}
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    if dups:
        raise RuntimeError(
            f"Cannot create UNIQUE index {name}: duplicates found in {table}.{col}: {dups}"
        )
    conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table}({col});")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--db",
        default=r".\database\mdr_project.db",
        help="Path to sqlite db file (default: .\\database\\mdr_project.db)",
    )
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    print("DB PATH:", db_path)

    if not db_path.exists():
        raise RuntimeError(f"DB file not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        # Disable FK checks while patching
        conn.execute("PRAGMA foreign_keys=OFF;")

        # ---- projects: add legacy 'code' column for old FKs (projects.code)
        add_column_if_missing(conn, "projects", "code", "TEXT")
        conn.execute("UPDATE projects SET code = project_code WHERE code IS NULL OR code = '';")
        ensure_unique_index(conn, "ux_projects_code", "projects", "code")

        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_projects_sync_ins
            AFTER INSERT ON projects
            BEGIN
              UPDATE projects SET code = NEW.project_code
              WHERE id = NEW.id AND (NEW.code IS NULL OR NEW.code = '');
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_projects_sync_upd
            AFTER UPDATE OF project_code ON projects
            BEGIN
              UPDATE projects SET code = NEW.project_code
              WHERE id = NEW.id;
            END;
            """
        )

        # ---- disciplines: add legacy 'code' column for old FKs (disciplines.code)
        add_column_if_missing(conn, "disciplines", "code", "TEXT")
        conn.execute("UPDATE disciplines SET code = discipline_code WHERE code IS NULL OR code = '';")
        ensure_unique_index(conn, "ux_disciplines_code", "disciplines", "code")

        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_disciplines_sync_ins
            AFTER INSERT ON disciplines
            BEGIN
              UPDATE disciplines SET code = NEW.discipline_code
              WHERE discipline_code = NEW.discipline_code AND (NEW.code IS NULL OR NEW.code = '');
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_disciplines_sync_upd
            AFTER UPDATE OF discipline_code ON disciplines
            BEGIN
              UPDATE disciplines SET code = NEW.discipline_code
              WHERE discipline_code = NEW.discipline_code;
            END;
            """
        )

        # ---- phases: FK references phases(ph_code) so make it UNIQUE
        ensure_unique_index(conn, "ux_phases_ph_code", "phases", "ph_code")

        # ---- levels: FK references levels(code) so make it UNIQUE
        ensure_unique_index(conn, "ux_levels_code", "levels", "code")

        conn.commit()

        # Re-enable FK checks
        conn.execute("PRAGMA foreign_keys=ON;")

        print("OK: FK mismatch patch applied successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
