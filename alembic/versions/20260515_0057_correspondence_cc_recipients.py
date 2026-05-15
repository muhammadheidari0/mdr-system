"""Add correspondence copy recipients.

Revision ID: 20260515_0057
Revises: 20260515_0056
Create Date: 2026-05-15 15:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260515_0057"
down_revision = "20260515_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("correspondences", sa.Column("cc_recipients", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("correspondences", "cc_recipients")
