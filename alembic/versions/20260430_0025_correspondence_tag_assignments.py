"""Add shared correspondence tag assignments.

Revision ID: 20260430_0025
Revises: 20260429_0024
Create Date: 2026-04-30 11:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_0025"
down_revision = "20260429_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "correspondence_tag_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("correspondence_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by_id", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"],
            ["users.id"],
            name=op.f("fk_correspondence_tag_assignments_assigned_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["correspondence_id"],
            ["correspondences.id"],
            name=op.f("fk_correspondence_tag_assignments_correspondence_id_correspondences"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["document_tags.id"],
            name=op.f("fk_correspondence_tag_assignments_tag_id_document_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_correspondence_tag_assignments")),
        sa.UniqueConstraint("correspondence_id", "tag_id", name="uq_corr_tag_assignment"),
    )
    op.create_index(
        "ix_cta_correspondence",
        "correspondence_tag_assignments",
        ["correspondence_id"],
        unique=False,
    )
    op.create_index(
        "ix_cta_tag",
        "correspondence_tag_assignments",
        ["tag_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cta_tag", table_name="correspondence_tag_assignments")
    op.drop_index("ix_cta_correspondence", table_name="correspondence_tag_assignments")
    op.drop_table("correspondence_tag_assignments")
