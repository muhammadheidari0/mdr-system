"""Add site cache core tables for profile/rule/token/cidr.

Revision ID: 20260216_0005
Revises: 20260215_0004
Create Date: 2026-02-16 10:15:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260216_0005"
down_revision = "20260215_0004"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(str(idx.get("name")) == index_name for idx in inspector.get_indexes(table_name))


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _index_exists(inspector, table_name, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "site_cache_profiles"):
        op.create_table(
            "site_cache_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("project_code", sa.String(length=50), nullable=True),
            sa.Column("local_root_path", sa.String(length=1024), nullable=True),
            sa.Column(
                "fallback_mode",
                sa.String(length=32),
                nullable=False,
                server_default="local_first",
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("last_heartbeat_info", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["project_code"],
                ["projects.code"],
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint("code", name="uq_site_cache_profiles_code"),
        )
    _create_index_if_missing("site_cache_profiles", "ix_site_cache_profiles_code", ["code"], unique=True)
    _create_index_if_missing("site_cache_profiles", "ix_site_cache_profiles_project", ["project_code"])
    _create_index_if_missing("site_cache_profiles", "ix_site_cache_profiles_active", ["is_active"])

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "site_cache_profile_cidrs"):
        op.create_table(
            "site_cache_profile_cidrs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("cidr", sa.String(length=64), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["profile_id"],
                ["site_cache_profiles.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("profile_id", "cidr", name="uq_site_cache_profile_cidr"),
        )
    _create_index_if_missing("site_cache_profile_cidrs", "ix_site_cache_profile_cidrs_profile_id", ["profile_id"])
    _create_index_if_missing("site_cache_profile_cidrs", "ix_site_cache_profile_cidrs_cidr", ["cidr"])
    _create_index_if_missing("site_cache_profile_cidrs", "ix_site_cache_profile_cidrs_active", ["is_active"])

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "site_cache_pin_rules"):
        op.create_table(
            "site_cache_pin_rules",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("project_code", sa.String(length=50), nullable=True),
            sa.Column("discipline_code", sa.String(length=20), nullable=True),
            sa.Column(
                "status_codes",
                sa.String(length=255),
                nullable=False,
                server_default="IFA,IFC",
            ),
            sa.Column(
                "include_native",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("FALSE"),
            ),
            sa.Column(
                "primary_only",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column(
                "latest_revision_only",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column(
                "priority",
                sa.Integer(),
                nullable=False,
                server_default="100",
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["profile_id"],
                ["site_cache_profiles.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["project_code"],
                ["projects.code"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["discipline_code"],
                ["disciplines.code"],
                ondelete="SET NULL",
            ),
        )
    _create_index_if_missing("site_cache_pin_rules", "ix_site_cache_pin_rules_profile_id", ["profile_id"])
    _create_index_if_missing(
        "site_cache_pin_rules",
        "ix_site_cache_pin_rules_profile",
        ["profile_id", "is_active"],
    )
    _create_index_if_missing("site_cache_pin_rules", "ix_site_cache_pin_rules_project", ["project_code"])
    _create_index_if_missing("site_cache_pin_rules", "ix_site_cache_pin_rules_discipline", ["discipline_code"])

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "site_cache_agent_tokens"):
        op.create_table(
            "site_cache_agent_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("token_hint", sa.String(length=32), nullable=True),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["profile_id"],
                ["site_cache_profiles.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["created_by_id"],
                ["users.id"],
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint("token_hash", name="uq_site_cache_agent_tokens_hash"),
        )
    _create_index_if_missing("site_cache_agent_tokens", "ix_site_cache_agent_tokens_profile_id", ["profile_id"])
    _create_index_if_missing("site_cache_agent_tokens", "ix_site_cache_agent_tokens_token_hash", ["token_hash"], unique=True)
    _create_index_if_missing(
        "site_cache_agent_tokens",
        "ix_site_cache_agent_tokens_profile_active",
        ["profile_id", "is_active"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "site_cache_agent_tokens"):
        for index_name in [
            "ix_site_cache_agent_tokens_profile_active",
            "ix_site_cache_agent_tokens_token_hash",
            "ix_site_cache_agent_tokens_profile_id",
        ]:
            if _index_exists(inspector, "site_cache_agent_tokens", index_name):
                op.drop_index(index_name, table_name="site_cache_agent_tokens")
        op.drop_table("site_cache_agent_tokens")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "site_cache_pin_rules"):
        for index_name in [
            "ix_site_cache_pin_rules_discipline",
            "ix_site_cache_pin_rules_project",
            "ix_site_cache_pin_rules_profile",
            "ix_site_cache_pin_rules_profile_id",
        ]:
            if _index_exists(inspector, "site_cache_pin_rules", index_name):
                op.drop_index(index_name, table_name="site_cache_pin_rules")
        op.drop_table("site_cache_pin_rules")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "site_cache_profile_cidrs"):
        for index_name in [
            "ix_site_cache_profile_cidrs_active",
            "ix_site_cache_profile_cidrs_cidr",
            "ix_site_cache_profile_cidrs_profile_id",
        ]:
            if _index_exists(inspector, "site_cache_profile_cidrs", index_name):
                op.drop_index(index_name, table_name="site_cache_profile_cidrs")
        op.drop_table("site_cache_profile_cidrs")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "site_cache_profiles"):
        for index_name in [
            "ix_site_cache_profiles_active",
            "ix_site_cache_profiles_project",
            "ix_site_cache_profiles_code",
        ]:
            if _index_exists(inspector, "site_cache_profiles", index_name):
                op.drop_index(index_name, table_name="site_cache_profiles")
        op.drop_table("site_cache_profiles")
