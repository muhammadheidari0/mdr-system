from __future__ import annotations

import app.db.session as session_module


def test_init_db_skips_runtime_schema_mutation(monkeypatch) -> None:
    create_all_calls: list[str] = []
    smart_migration_calls: list[str] = []

    monkeypatch.setattr(
        session_module.Base.metadata,
        "create_all",
        lambda *args, **kwargs: create_all_calls.append("create_all"),
    )
    monkeypatch.setattr(
        session_module,
        "_run_smart_migrations",
        lambda *args, **kwargs: smart_migration_calls.append("smart_migrations"),
    )

    session_module.init_db()

    assert not create_all_calls
    assert not smart_migration_calls


def test_init_db_runs_bootstrap_only_when_flag_enabled(monkeypatch) -> None:
    create_all_calls: list[str] = []
    smart_migration_calls: list[str] = []

    monkeypatch.setattr(
        session_module.Base.metadata,
        "create_all",
        lambda *args, **kwargs: create_all_calls.append("create_all"),
    )
    monkeypatch.setattr(
        session_module,
        "_run_smart_migrations",
        lambda *args, **kwargs: smart_migration_calls.append("smart_migrations"),
    )

    session_module.init_db(run_data_bootstrap=True)

    assert not create_all_calls
    assert smart_migration_calls == ["smart_migrations"]


def test_runtime_database_url_rejects_non_postgres() -> None:
    try:
        session_module._runtime_database_url("sqlite:///./database/mdr_project.db")
        assert False, "SQLite URL must be rejected in runtime policy."
    except ValueError as exc:
        assert "PostgreSQL" in str(exc)
