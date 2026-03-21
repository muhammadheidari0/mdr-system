"""Add native EDMS sync and cutover foundation tables.

Revision ID: 20260320_0018
Revises: 20260228_0017
Create Date: 2026-03-20 23:55:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260320_0018"
down_revision = "20260228_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "native_edms_sync_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("delivery_state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", name="uq_native_edms_sync_events_event_id"),
    )
    op.create_index(
        "ix_native_edms_sync_events_entity_state",
        "native_edms_sync_events",
        ["entity", "delivery_state"],
        unique=False,
    )
    op.create_index(
        "ix_native_edms_sync_events_created_at",
        "native_edms_sync_events",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "native_edms_cutover_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_name", sa.String(length=128), nullable=False),
        sa.Column("snapshot_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_name", name="uq_native_edms_cutover_snapshots_snapshot_name"),
    )
    op.create_index(
        "ix_native_edms_cutover_snapshots_snapshot_type",
        "native_edms_cutover_snapshots",
        ["snapshot_type"],
        unique=False,
    )
    op.create_index(
        "ix_native_edms_cutover_snapshots_created_at",
        "native_edms_cutover_snapshots",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_native_edms_cutover_snapshots_created_at", table_name="native_edms_cutover_snapshots")
    op.drop_index("ix_native_edms_cutover_snapshots_snapshot_type", table_name="native_edms_cutover_snapshots")
    op.drop_table("native_edms_cutover_snapshots")

    op.drop_index("ix_native_edms_sync_events_created_at", table_name="native_edms_sync_events")
    op.drop_index("ix_native_edms_sync_events_entity_state", table_name="native_edms_sync_events")
    op.drop_table("native_edms_sync_events")
