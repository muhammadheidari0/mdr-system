from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.db.base import Base

# Ensure metadata is populated before checks.
import app.db.models  # noqa: F401


def test_no_duplicate_index_names_in_metadata() -> None:
    duplicate_index_names: list[str] = []

    for table in Base.metadata.tables.values():
        names: list[str] = []
        for idx in table.indexes:
            names.append(str(idx.name or "__".join(col.name for col in idx.columns)))

        duplicates = [name for name, count in Counter(names).items() if count > 1]
        if duplicates:
            duplicate_index_names.append(f"{table.name}: {', '.join(sorted(duplicates))}")

    assert not duplicate_index_names, (
        "Duplicate index names detected in SQLAlchemy metadata. "
        + " | ".join(duplicate_index_names)
    )


def test_base_template_has_no_inline_onclick_handlers() -> None:
    base_template = Path("templates/base.html")
    content = base_template.read_text(encoding="utf-8")
    assert "onclick=" not in content.lower()
