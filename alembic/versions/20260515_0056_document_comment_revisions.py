"""Link document comments to revisions.

Revision ID: 20260515_0056
Revises: 20260515_0055
Create Date: 2026-05-15 12:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_0056"
down_revision = "20260515_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_comments", sa.Column("revision_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_document_comments_revision_id_document_revisions",
        "document_comments",
        "document_revisions",
        ["revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_doc_comments_document_revision_created",
        "document_comments",
        ["document_id", "revision_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_doc_comments_document_revision_created", table_name="document_comments")
    op.drop_constraint(
        "fk_document_comments_revision_id_document_revisions",
        "document_comments",
        type_="foreignkey",
    )
    op.drop_column("document_comments", "revision_id")
