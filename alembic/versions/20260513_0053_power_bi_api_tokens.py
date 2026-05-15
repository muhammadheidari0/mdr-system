"""Add Power BI API tokens.

Revision ID: 20260513_0053
Revises: 20260511_0052
Create Date: 2026-05-13 04:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0053"
down_revision = "20260511_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "power_bi_api_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=48), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False, server_default='["site_logs:report_read"]'),
        sa.Column("allowed_project_codes", sa.Text(), nullable=True),
        sa.Column("allowed_report_sections", sa.Text(), nullable=True),
        sa.Column("allowed_ip_ranges", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token_hash", name="uq_power_bi_api_tokens_hash"),
    )
    op.create_index("ix_power_bi_api_tokens_token_hash", "power_bi_api_tokens", ["token_hash"], unique=True)
    op.create_index("ix_power_bi_api_tokens_active", "power_bi_api_tokens", ["is_active", "revoked_at"])
    op.create_index("ix_power_bi_api_tokens_created_at", "power_bi_api_tokens", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_power_bi_api_tokens_created_at", table_name="power_bi_api_tokens")
    op.drop_index("ix_power_bi_api_tokens_active", table_name="power_bi_api_tokens")
    op.drop_index("ix_power_bi_api_tokens_token_hash", table_name="power_bi_api_tokens")
    op.drop_table("power_bi_api_tokens")
