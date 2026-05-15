"""Add meeting minute numbering and external relations.

Revision ID: 20260511_0052
Revises: 20260511_0051
Create Date: 2026-05-11 17:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_0052"
down_revision = "20260511_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meeting_minute_sequences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("period", sa.String(length=8), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "project_code",
            "period",
            name="uq_meeting_minute_sequences_project_period",
        ),
    )
    op.create_index(
        "ix_meeting_minute_sequences_project_period",
        "meeting_minute_sequences",
        ["project_code", "period"],
    )

    op.create_table(
        "meeting_minute_external_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("meeting_minute_id", sa.Integer(), nullable=False),
        sa.Column("target_entity_type", sa.String(length=32), nullable=False),
        sa.Column("target_entity_id", sa.String(length=128), nullable=False),
        sa.Column("target_code", sa.String(length=120), nullable=False),
        sa.Column("target_title", sa.Text(), nullable=True),
        sa.Column("target_project_code", sa.String(length=50), nullable=True),
        sa.Column("target_status", sa.String(length=64), nullable=True),
        sa.Column("relation_type", sa.String(length=32), nullable=False, server_default="related"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["meeting_minute_id"], ["meeting_minutes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "meeting_minute_id",
            "target_entity_type",
            "target_entity_id",
            "relation_type",
            name="uq_meeting_minute_external_relation",
        ),
    )
    op.create_index("ix_mm_ext_relations_source", "meeting_minute_external_relations", ["meeting_minute_id"])
    op.create_index(
        "ix_mm_ext_relations_target",
        "meeting_minute_external_relations",
        ["target_entity_type", "target_entity_id"],
    )
    op.create_index(
        "ix_mm_ext_relations_code",
        "meeting_minute_external_relations",
        ["target_entity_type", "target_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_mm_ext_relations_code", table_name="meeting_minute_external_relations")
    op.drop_index("ix_mm_ext_relations_target", table_name="meeting_minute_external_relations")
    op.drop_index("ix_mm_ext_relations_source", table_name="meeting_minute_external_relations")
    op.drop_table("meeting_minute_external_relations")

    op.drop_index("ix_meeting_minute_sequences_project_period", table_name="meeting_minute_sequences")
    op.drop_table("meeting_minute_sequences")
