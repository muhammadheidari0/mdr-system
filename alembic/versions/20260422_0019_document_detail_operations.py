"""Add document detail, comments, activity, relations and tags.

Revision ID: 20260422_0019
Revises: 20260320_0018
Create Date: 2026-04-22 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260422_0019"
down_revision = "20260320_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- MdrDocument audit / soft-delete columns ---
    op.add_column("mdr_documents", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column(
        "mdr_documents",
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("mdr_documents", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column(
        "mdr_documents",
        sa.Column("deleted_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_mdr_documents_deleted_at", "mdr_documents", ["deleted_at"])

    # --- document_comments ---
    op.create_table(
        "document_comments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("mdr_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("document_comments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("author_name", sa.String(255)),
        sa.Column("author_email", sa.String(255)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_doc_comments_document_id", "document_comments", ["document_id"])
    op.create_index("ix_doc_comments_parent_id", "document_comments", ["parent_id"])
    op.create_index("ix_doc_comments_created_at", "document_comments", ["created_at"])

    # --- document_activities ---
    op.create_table(
        "document_activities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("mdr_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_name", sa.String(255)),
        sa.Column("actor_email", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_doc_activities_doc_created", "document_activities", ["document_id", "created_at"])
    op.create_index("ix_doc_activities_action", "document_activities", ["action"])

    # --- document_relations ---
    op.create_table(
        "document_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_document_id",
            sa.Integer(),
            sa.ForeignKey("mdr_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_document_id",
            sa.Integer(),
            sa.ForeignKey("mdr_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(32), nullable=False, server_default="related"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source_document_id", "target_document_id", "relation_type",
            name="uq_document_relation",
        ),
        sa.CheckConstraint(
            "source_document_id != target_document_id",
            name="ck_document_relation_no_self",
        ),
    )
    op.create_index("ix_doc_relations_source", "document_relations", ["source_document_id"])
    op.create_index("ix_doc_relations_target", "document_relations", ["target_document_id"])

    # --- document_tags ---
    op.create_table(
        "document_tags",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), unique=True, nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_doc_tags_name", "document_tags", ["name"])

    # --- document_tag_assignments ---
    op.create_table(
        "document_tag_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("mdr_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("document_tags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "tag_id", name="uq_doc_tag_assignment"),
    )
    op.create_index("ix_dta_document", "document_tag_assignments", ["document_id"])
    op.create_index("ix_dta_tag", "document_tag_assignments", ["tag_id"])


def downgrade() -> None:
    op.drop_table("document_tag_assignments")
    op.drop_table("document_tags")
    op.drop_table("document_relations")
    op.drop_table("document_activities")
    op.drop_table("document_comments")
    op.drop_index("ix_mdr_documents_deleted_at", table_name="mdr_documents")
    op.drop_column("mdr_documents", "deleted_by_id")
    op.drop_column("mdr_documents", "deleted_at")
    op.drop_column("mdr_documents", "updated_by_id")
    op.drop_column("mdr_documents", "updated_at")
