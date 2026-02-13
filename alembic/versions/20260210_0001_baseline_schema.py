"""Baseline schema from SQLAlchemy metadata

Revision ID: 20260210_0001
Revises:
Create Date: 2026-02-10 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.db.base import Base

# Import models so Base.metadata has every table.
import app.db.models  # noqa: F401

# revision identifiers, used by Alembic.
revision = "20260210_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)

    # Some legacy model definitions contain duplicate index declarations
    # (e.g. `index=True` + explicit `Index(...)` on the same column/name).
    # Deduplicate here to keep baseline migration deterministic.
    for table in metadata.tables.values():
        seen: set[str] = set()
        duplicates = []
        for idx in list(table.indexes):
            key = idx.name or "__".join(col.name for col in idx.columns)
            if key in seen:
                duplicates.append(idx)
            else:
                seen.add(key)
        for idx in duplicates:
            table.indexes.discard(idx)

    metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
