"""Add document external relations.

Revision ID: 20260506_0039
Revises: 20260505_0038
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260506_0039"
down_revision = "20260505_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_external_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_document_id",
            sa.Integer(),
            sa.ForeignKey("mdr_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_entity_type", sa.String(length=32), nullable=False),
        sa.Column("target_entity_id", sa.Integer(), nullable=False),
        sa.Column("target_code", sa.String(length=120), nullable=False),
        sa.Column("target_title", sa.Text(), nullable=True),
        sa.Column("target_project_code", sa.String(length=50), nullable=True),
        sa.Column("target_status", sa.String(length=64), nullable=True),
        sa.Column("relation_type", sa.String(length=32), nullable=False, server_default="related"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source_document_id",
            "target_entity_type",
            "target_entity_id",
            "relation_type",
            name="uq_document_external_relation",
        ),
    )
    op.create_index("ix_doc_ext_relations_source", "document_external_relations", ["source_document_id"])
    op.create_index(
        "ix_doc_ext_relations_target",
        "document_external_relations",
        ["target_entity_type", "target_entity_id"],
    )
    op.create_index(
        "ix_doc_ext_relations_code",
        "document_external_relations",
        ["target_entity_type", "target_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_doc_ext_relations_code", table_name="document_external_relations")
    op.drop_index("ix_doc_ext_relations_target", table_name="document_external_relations")
    op.drop_index("ix_doc_ext_relations_source", table_name="document_external_relations")
    op.drop_table("document_external_relations")
