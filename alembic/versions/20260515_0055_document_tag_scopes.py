"""Split document and correspondence tag catalogs.

Revision ID: 20260515_0055
Revises: 20260515_0054
Create Date: 2026-05-15 11:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_0055"
down_revision = "20260515_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_tags",
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="document"),
    )
    op.create_index("ix_document_tags_scope", "document_tags", ["scope"], unique=False)

    op.drop_constraint("document_tags_name_key", "document_tags", type_="unique")

    # Tags that were used by both modules are duplicated so each catalog can
    # evolve independently while keeping existing assignments intact.
    op.execute(
        """
        WITH dual_scope_tags AS (
            SELECT dt.id AS old_id, dt.name, dt.color, dt.created_at
            FROM document_tags dt
            WHERE EXISTS (
                SELECT 1 FROM document_tag_assignments dta WHERE dta.tag_id = dt.id
            )
            AND EXISTS (
                SELECT 1 FROM correspondence_tag_assignments cta WHERE cta.tag_id = dt.id
            )
        ),
        inserted AS (
            INSERT INTO document_tags (name, color, created_at, scope)
            SELECT name, color, created_at, 'correspondence'
            FROM dual_scope_tags
            RETURNING id, name
        )
        UPDATE correspondence_tag_assignments cta
        SET tag_id = inserted.id
        FROM dual_scope_tags
        JOIN inserted ON inserted.name = dual_scope_tags.name
        WHERE cta.tag_id = dual_scope_tags.old_id
        """
    )

    op.execute(
        """
        UPDATE document_tags dt
        SET scope = 'correspondence'
        WHERE NOT EXISTS (
            SELECT 1 FROM document_tag_assignments dta WHERE dta.tag_id = dt.id
        )
        """
    )
    op.execute(
        """
        UPDATE document_tags dt
        SET scope = 'document'
        WHERE EXISTS (
            SELECT 1 FROM document_tag_assignments dta WHERE dta.tag_id = dt.id
        )
        """
    )

    op.create_unique_constraint(
        "uq_document_tags_scope_name",
        "document_tags",
        ["scope", "name"],
    )
    op.create_index("ix_doc_tags_scope_name", "document_tags", ["scope", "name"], unique=False)
    op.alter_column("document_tags", "scope", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_doc_tags_scope_name", table_name="document_tags")
    op.drop_constraint("uq_document_tags_scope_name", "document_tags", type_="unique")

    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                name,
                first_value(id) OVER (
                    PARTITION BY name
                    ORDER BY CASE WHEN scope = 'document' THEN 0 ELSE 1 END, id
                ) AS keep_id,
                row_number() OVER (
                    PARTITION BY name
                    ORDER BY CASE WHEN scope = 'document' THEN 0 ELSE 1 END, id
                ) AS rn
            FROM document_tags
        ),
        dupes AS (
            SELECT id, keep_id FROM ranked WHERE rn > 1
        )
        UPDATE document_tag_assignments dta
        SET tag_id = dupes.keep_id
        FROM dupes
        WHERE dta.tag_id = dupes.id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                name,
                first_value(id) OVER (
                    PARTITION BY name
                    ORDER BY CASE WHEN scope = 'document' THEN 0 ELSE 1 END, id
                ) AS keep_id,
                row_number() OVER (
                    PARTITION BY name
                    ORDER BY CASE WHEN scope = 'document' THEN 0 ELSE 1 END, id
                ) AS rn
            FROM document_tags
        ),
        dupes AS (
            SELECT id, keep_id FROM ranked WHERE rn > 1
        )
        UPDATE correspondence_tag_assignments cta
        SET tag_id = dupes.keep_id
        FROM dupes
        WHERE cta.tag_id = dupes.id
        """
    )
    op.execute(
        """
        DELETE FROM document_tags dt
        USING (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY name
                        ORDER BY CASE WHEN scope = 'document' THEN 0 ELSE 1 END, id
                    ) AS rn
                FROM document_tags
            ) ranked
            WHERE rn > 1
        ) dupes
        WHERE dt.id = dupes.id
        """
    )

    op.create_unique_constraint("document_tags_name_key", "document_tags", ["name"])
    op.drop_index("ix_document_tags_scope", table_name="document_tags")
    op.drop_column("document_tags", "scope")
