"""Add organization contracts table.

Revision ID: 20260501_0026
Revises: 20260430_0025
Create Date: 2026-05-01 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260501_0026"
down_revision = "20260430_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_contracts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("contract_number", sa.String(length=128), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["blocks.id"],
            name=op.f("fk_organization_contracts_block_id_blocks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_contracts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_contracts")),
    )
    op.create_index(
        "ix_org_contracts_org_sort",
        "organization_contracts",
        ["organization_id", "sort_order"],
        unique=False,
    )
    op.create_index(
        "ix_org_contracts_block",
        "organization_contracts",
        ["block_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_contracts_organization_id"),
        "organization_contracts",
        ["organization_id"],
        unique=False,
    )
    op.alter_column(
        "organization_contracts",
        "sort_order",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_organization_contracts_organization_id"), table_name="organization_contracts")
    op.drop_index("ix_org_contracts_block", table_name="organization_contracts")
    op.drop_index("ix_org_contracts_org_sort", table_name="organization_contracts")
    op.drop_table("organization_contracts")
