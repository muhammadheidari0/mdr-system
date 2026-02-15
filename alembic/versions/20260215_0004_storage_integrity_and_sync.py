"""Add storage integrity fields and sync job tables.

Revision ID: 20260215_0004
Revises: 20260211_0003
Create Date: 2026-02-15 22:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260215_0004"
down_revision = "20260211_0003"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(str(col.get("name")) == column_name for col in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(str(idx.get("name")) == index_name for idx in inspector.get_indexes(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _column_exists(inspector, table_name, str(column.name)):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(column)


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

    if _table_exists(inspector, "archive_files"):
        _add_column_if_missing("archive_files", sa.Column("detected_mime", sa.String(length=128), nullable=True))
        _add_column_if_missing("archive_files", sa.Column("validation_status", sa.String(length=32), nullable=True))
        _add_column_if_missing("archive_files", sa.Column("sha256", sa.String(length=64), nullable=True))
        _add_column_if_missing(
            "archive_files",
            sa.Column("storage_backend", sa.String(length=32), nullable=True, server_default="local"),
        )
        _add_column_if_missing("archive_files", sa.Column("gdrive_file_id", sa.String(length=255), nullable=True))
        _add_column_if_missing("archive_files", sa.Column("mirror_status", sa.String(length=32), nullable=True))
        _add_column_if_missing("archive_files", sa.Column("mirror_updated_at", sa.DateTime(), nullable=True))
        _add_column_if_missing("archive_files", sa.Column("deleted_at", sa.DateTime(), nullable=True))

        bind.execute(
            sa.text(
                """
                UPDATE archive_files
                SET storage_backend = 'local'
                WHERE storage_backend IS NULL OR TRIM(storage_backend) = ''
                """
            )
        )

        _create_index_if_missing("archive_files", "ix_archive_files_validation_status", ["validation_status"])
        _create_index_if_missing("archive_files", "ix_archive_files_sha256", ["sha256"])
        _create_index_if_missing("archive_files", "ix_archive_files_storage_backend", ["storage_backend"])
        _create_index_if_missing("archive_files", "ix_archive_files_gdrive_file_id", ["gdrive_file_id"])
        _create_index_if_missing("archive_files", "ix_archive_files_mirror_status", ["mirror_status"])

        with op.batch_alter_table("archive_files") as batch_op:
            batch_op.alter_column(
                "storage_backend",
                existing_type=sa.String(length=32),
                nullable=False,
                existing_server_default="local",
            )

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "correspondence_attachments"):
        _add_column_if_missing(
            "correspondence_attachments",
            sa.Column("detected_mime", sa.String(length=128), nullable=True),
        )
        _add_column_if_missing(
            "correspondence_attachments",
            sa.Column("validation_status", sa.String(length=32), nullable=True),
        )
        _add_column_if_missing("correspondence_attachments", sa.Column("sha256", sa.String(length=64), nullable=True))
        _add_column_if_missing(
            "correspondence_attachments",
            sa.Column("storage_backend", sa.String(length=32), nullable=True, server_default="local"),
        )
        _add_column_if_missing(
            "correspondence_attachments",
            sa.Column("gdrive_file_id", sa.String(length=255), nullable=True),
        )
        _add_column_if_missing(
            "correspondence_attachments",
            sa.Column("mirror_status", sa.String(length=32), nullable=True),
        )
        _add_column_if_missing(
            "correspondence_attachments",
            sa.Column("mirror_updated_at", sa.DateTime(), nullable=True),
        )
        _add_column_if_missing("correspondence_attachments", sa.Column("deleted_at", sa.DateTime(), nullable=True))

        bind.execute(
            sa.text(
                """
                UPDATE correspondence_attachments
                SET storage_backend = 'local'
                WHERE storage_backend IS NULL OR TRIM(storage_backend) = ''
                """
            )
        )

        _create_index_if_missing(
            "correspondence_attachments",
            "ix_corr_attachments_validation_status",
            ["validation_status"],
        )
        _create_index_if_missing("correspondence_attachments", "ix_corr_attachments_sha256", ["sha256"])
        _create_index_if_missing(
            "correspondence_attachments",
            "ix_corr_attachments_storage_backend",
            ["storage_backend"],
        )
        _create_index_if_missing(
            "correspondence_attachments",
            "ix_corr_attachments_gdrive_file_id",
            ["gdrive_file_id"],
        )
        _create_index_if_missing(
            "correspondence_attachments",
            "ix_corr_attachments_mirror_status",
            ["mirror_status"],
        )

        with op.batch_alter_table("correspondence_attachments") as batch_op:
            batch_op.alter_column(
                "storage_backend",
                existing_type=sa.String(length=32),
                nullable=False,
                existing_server_default="local",
            )

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "storage_jobs"):
        op.create_table(
            "storage_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("job_type", sa.String(length=64), nullable=False),
            sa.Column("file_id", sa.Integer(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_retry_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_storage_jobs_job_type", "storage_jobs", ["job_type"], unique=False)
        op.create_index("ix_storage_jobs_file_id", "storage_jobs", ["file_id"], unique=False)
        op.create_index("ix_storage_jobs_status", "storage_jobs", ["status"], unique=False)
        op.create_index(
            "ix_storage_jobs_status_next_retry",
            "storage_jobs",
            ["status", "next_retry_at"],
            unique=False,
        )

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "openproject_links"):
        op.create_table(
            "openproject_links",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entity_type", sa.String(length=32), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("work_package_id", sa.Integer(), nullable=False),
            sa.Column("openproject_attachment_id", sa.String(length=128), nullable=True),
            sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint(
                "entity_type",
                "entity_id",
                "work_package_id",
                name="uq_openproject_entity_wp",
            ),
        )
        op.create_index("ix_openproject_links_entity_type", "openproject_links", ["entity_type"], unique=False)
        op.create_index("ix_openproject_links_entity_id", "openproject_links", ["entity_id"], unique=False)
        op.create_index("ix_openproject_links_work_package_id", "openproject_links", ["work_package_id"], unique=False)
        op.create_index("ix_openproject_links_sync_status", "openproject_links", ["sync_status"], unique=False)

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "local_sync_manifest"):
        op.create_table(
            "local_sync_manifest",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("file_id", sa.Integer(), nullable=False),
            sa.Column("version_hash", sa.String(length=64), nullable=False),
            sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
            sa.Column("last_modified_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("policy_scope", sa.String(length=64), nullable=False, server_default="global"),
            sa.UniqueConstraint("file_id", "policy_scope", name="uq_local_sync_manifest_file_scope"),
        )
        op.create_index("ix_local_sync_manifest_file_id", "local_sync_manifest", ["file_id"], unique=False)
        op.create_index("ix_local_sync_manifest_policy_scope", "local_sync_manifest", ["policy_scope"], unique=False)
        op.create_index(
            "ix_local_sync_manifest_scope",
            "local_sync_manifest",
            ["policy_scope", "is_pinned"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "local_sync_manifest"):
        op.drop_index("ix_local_sync_manifest_scope", table_name="local_sync_manifest")
        op.drop_index("ix_local_sync_manifest_policy_scope", table_name="local_sync_manifest")
        op.drop_index("ix_local_sync_manifest_file_id", table_name="local_sync_manifest")
        op.drop_table("local_sync_manifest")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "openproject_links"):
        op.drop_index("ix_openproject_links_sync_status", table_name="openproject_links")
        op.drop_index("ix_openproject_links_work_package_id", table_name="openproject_links")
        op.drop_index("ix_openproject_links_entity_id", table_name="openproject_links")
        op.drop_index("ix_openproject_links_entity_type", table_name="openproject_links")
        op.drop_table("openproject_links")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "storage_jobs"):
        op.drop_index("ix_storage_jobs_status_next_retry", table_name="storage_jobs")
        op.drop_index("ix_storage_jobs_status", table_name="storage_jobs")
        op.drop_index("ix_storage_jobs_file_id", table_name="storage_jobs")
        op.drop_index("ix_storage_jobs_job_type", table_name="storage_jobs")
        op.drop_table("storage_jobs")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "correspondence_attachments"):
        for index_name in [
            "ix_corr_attachments_mirror_status",
            "ix_corr_attachments_gdrive_file_id",
            "ix_corr_attachments_storage_backend",
            "ix_corr_attachments_sha256",
            "ix_corr_attachments_validation_status",
        ]:
            if _index_exists(inspector, "correspondence_attachments", index_name):
                op.drop_index(index_name, table_name="correspondence_attachments")
        for column_name in [
            "deleted_at",
            "mirror_updated_at",
            "mirror_status",
            "gdrive_file_id",
            "storage_backend",
            "sha256",
            "validation_status",
            "detected_mime",
        ]:
            if _column_exists(inspector, "correspondence_attachments", column_name):
                with op.batch_alter_table("correspondence_attachments") as batch_op:
                    batch_op.drop_column(column_name)

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "archive_files"):
        for index_name in [
            "ix_archive_files_mirror_status",
            "ix_archive_files_gdrive_file_id",
            "ix_archive_files_storage_backend",
            "ix_archive_files_sha256",
            "ix_archive_files_validation_status",
        ]:
            if _index_exists(inspector, "archive_files", index_name):
                op.drop_index(index_name, table_name="archive_files")
        for column_name in [
            "deleted_at",
            "mirror_updated_at",
            "mirror_status",
            "gdrive_file_id",
            "storage_backend",
            "sha256",
            "validation_status",
            "detected_mime",
        ]:
            if _column_exists(inspector, "archive_files", column_name):
                with op.batch_alter_table("archive_files") as batch_op:
                    batch_op.drop_column(column_name)
