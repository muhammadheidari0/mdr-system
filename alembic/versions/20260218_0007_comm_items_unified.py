"""Add unified communication items schema (RFI/NCR/TECH).

Revision ID: 20260218_0007
Revises: 20260217_0006
Create Date: 2026-02-18 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260218_0007"
down_revision = "20260217_0006"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _seed_lookup_data() -> None:
    bind = op.get_bind()

    workflow_status_rows = [
        ("RFI", "DRAFT", "Draft", False, 10),
        ("RFI", "SUBMITTED", "Submitted", False, 20),
        ("RFI", "IN_REVIEW", "In Review", False, 30),
        ("RFI", "RETURNED", "Returned", False, 40),
        ("RFI", "ANSWERED", "Answered", False, 50),
        ("RFI", "CLOSED", "Closed", True, 60),
        ("RFI", "SUPERSEDED", "Superseded", True, 70),
        ("NCR", "ISSUED", "Issued", False, 10),
        ("NCR", "CONTRACTOR_REPLY", "Contractor Reply", False, 20),
        ("NCR", "ACCEPTED", "Accepted", False, 30),
        ("NCR", "REJECTED", "Rejected", False, 40),
        ("NCR", "RECTIFIED", "Rectified", False, 50),
        ("NCR", "VERIFIED", "Verified", False, 60),
        ("NCR", "CLOSED", "Closed", True, 70),
        ("NCR", "REOPENED", "Reopened", False, 80),
        ("TECH", "DRAFT", "Draft", False, 10),
        ("TECH", "SUBMITTED", "Submitted", False, 20),
        ("TECH", "IN_REVIEW", "In Review", False, 30),
        ("TECH", "APPROVED", "Approved", False, 40),
        ("TECH", "APPROVED_AS_NOTED", "Approved As Noted", False, 50),
        ("TECH", "REVISE_RESUBMIT", "Revise & Resubmit", False, 60),
        ("TECH", "REJECTED", "Rejected", False, 70),
        ("TECH", "CLOSED", "Closed", True, 80),
    ]
    for item_type, code, label, is_terminal, sort_order in workflow_status_rows:
        exists = bind.execute(
            sa.text(
                """
                SELECT 1
                FROM workflow_statuses
                WHERE item_type = :item_type AND code = :code
                LIMIT 1
                """
            ),
            {
                "item_type": item_type,
                "code": code,
            },
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO workflow_statuses (
                    item_type, code, label, is_terminal, sort_order, is_active
                ) VALUES (
                    :item_type, :code, :label, :is_terminal, :sort_order, :is_active
                )
                """
            ),
            {
                "item_type": item_type,
                "code": code,
                "label": label,
                "is_terminal": bool(is_terminal),
                "sort_order": int(sort_order),
                "is_active": True,
            },
        )

    workflow_transition_rows = [
        ("RFI", "DRAFT", "SUBMITTED", False),
        ("RFI", "SUBMITTED", "IN_REVIEW", False),
        ("RFI", "IN_REVIEW", "RETURNED", False),
        ("RFI", "RETURNED", "SUBMITTED", False),
        ("RFI", "IN_REVIEW", "ANSWERED", False),
        ("RFI", "ANSWERED", "CLOSED", False),
        ("RFI", "ANSWERED", "SUPERSEDED", False),
        ("NCR", "ISSUED", "CONTRACTOR_REPLY", False),
        ("NCR", "CONTRACTOR_REPLY", "ACCEPTED", False),
        ("NCR", "CONTRACTOR_REPLY", "REJECTED", False),
        ("NCR", "REJECTED", "CONTRACTOR_REPLY", False),
        ("NCR", "ACCEPTED", "RECTIFIED", False),
        ("NCR", "RECTIFIED", "VERIFIED", False),
        ("NCR", "VERIFIED", "CLOSED", False),
        ("NCR", "CLOSED", "REOPENED", True),
        ("NCR", "REOPENED", "CONTRACTOR_REPLY", False),
        ("TECH", "DRAFT", "SUBMITTED", False),
        ("TECH", "SUBMITTED", "IN_REVIEW", False),
        ("TECH", "IN_REVIEW", "APPROVED", False),
        ("TECH", "IN_REVIEW", "APPROVED_AS_NOTED", False),
        ("TECH", "IN_REVIEW", "REVISE_RESUBMIT", False),
        ("TECH", "IN_REVIEW", "REJECTED", False),
        ("TECH", "REVISE_RESUBMIT", "SUBMITTED", False),
        ("TECH", "APPROVED", "CLOSED", False),
        ("TECH", "APPROVED_AS_NOTED", "CLOSED", False),
        ("TECH", "REJECTED", "CLOSED", False),
    ]
    for item_type, from_status, to_status, requires_note in workflow_transition_rows:
        exists = bind.execute(
            sa.text(
                """
                SELECT 1
                FROM workflow_transitions
                WHERE item_type = :item_type
                  AND from_status_code = :from_status_code
                  AND to_status_code = :to_status_code
                LIMIT 1
                """
            ),
            {
                "item_type": item_type,
                "from_status_code": from_status,
                "to_status_code": to_status,
            },
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO workflow_transitions (
                    item_type, from_status_code, to_status_code, requires_note, is_active
                ) VALUES (
                    :item_type, :from_status_code, :to_status_code, :requires_note, :is_active
                )
                """
            ),
            {
                "item_type": item_type,
                "from_status_code": from_status,
                "to_status_code": to_status,
                "requires_note": bool(requires_note),
                "is_active": True,
            },
        )

    tech_subtypes = [
        ("SUBMITTAL", "Submittal", 10),
        ("TRANSMITTAL", "Transmittal", 20),
        ("INSTRUCTION", "Instruction", 30),
        ("MOM", "MoM", 40),
        ("DAILY_REPORT", "Daily Report", 50),
        ("IR", "Inspection Request", 60),
    ]
    for code, label, sort_order in tech_subtypes:
        exists = bind.execute(
            sa.text("SELECT 1 FROM tech_subtypes WHERE code = :code LIMIT 1"),
            {"code": code},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO tech_subtypes (code, label, sort_order, is_active)
                VALUES (:code, :label, :sort_order, :is_active)
                """
            ),
            {
                "code": code,
                "label": label,
                "sort_order": int(sort_order),
                "is_active": True,
            },
        )

    review_results = [
        ("APPROVED", "Approved", 10),
        ("APPROVED_AS_NOTED", "Approved As Noted", 20),
        ("REVISE_RESUBMIT", "Revise & Resubmit", 30),
        ("REJECTED", "Rejected", 40),
    ]
    for code, label, sort_order in review_results:
        exists = bind.execute(
            sa.text("SELECT 1 FROM review_results WHERE code = :code LIMIT 1"),
            {"code": code},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO review_results (code, label, sort_order, is_active)
                VALUES (:code, :label, :sort_order, :is_active)
                """
            ),
            {
                "code": code,
                "label": label,
                "sort_order": int(sort_order),
                "is_active": True,
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "workflow_statuses"):
        op.create_table(
            "workflow_statuses",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("item_type", sa.String(length=16), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("label", sa.String(length=128), nullable=False),
            sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("item_type", "code", name="uq_workflow_status_item_type_code"),
        )
        op.create_index(
            "ix_workflow_status_item_type_sort",
            "workflow_statuses",
            ["item_type", "sort_order"],
            unique=False,
        )

    if not _table_exists(inspector, "workflow_transitions"):
        op.create_table(
            "workflow_transitions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("item_type", sa.String(length=16), nullable=False),
            sa.Column("from_status_code", sa.String(length=64), nullable=False),
            sa.Column("to_status_code", sa.String(length=64), nullable=False),
            sa.Column("requires_note", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "item_type",
                "from_status_code",
                "to_status_code",
                name="uq_workflow_transition_item_from_to",
            ),
        )
        op.create_index(
            "ix_workflow_transition_item_from",
            "workflow_transitions",
            ["item_type", "from_status_code"],
            unique=False,
        )

    if not _table_exists(inspector, "tech_subtypes"):
        op.create_table(
            "tech_subtypes",
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("label", sa.String(length=128), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.PrimaryKeyConstraint("code"),
        )

    if not _table_exists(inspector, "review_results"):
        op.create_table(
            "review_results",
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("label", sa.String(length=128), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.PrimaryKeyConstraint("code"),
        )

    if not _table_exists(inspector, "comm_items"):
        op.create_table(
            "comm_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("item_no", sa.String(length=128), nullable=False),
            sa.Column("item_type", sa.String(length=16), nullable=False),
            sa.Column("project_code", sa.String(length=50), nullable=False),
            sa.Column("discipline_code", sa.String(length=20), nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=True),
            sa.Column("zone", sa.String(length=128), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("short_description", sa.Text(), nullable=True),
            sa.Column("status_code", sa.String(length=64), nullable=False),
            sa.Column("priority", sa.String(length=32), nullable=False, server_default="normal"),
            sa.Column("response_due_date", sa.DateTime(), nullable=True),
            sa.Column("assignee_user_id", sa.Integer(), nullable=True),
            sa.Column("recipient_org_id", sa.Integer(), nullable=True),
            sa.Column("contractor_org_id", sa.Integer(), nullable=True),
            sa.Column("consultant_org_id", sa.Integer(), nullable=True),
            sa.Column("contract_clause_ref", sa.String(length=255), nullable=True),
            sa.Column("spec_clause_ref", sa.String(length=255), nullable=True),
            sa.Column("wbs_code", sa.String(length=64), nullable=True),
            sa.Column("activity_code", sa.String(length=64), nullable=True),
            sa.Column("potential_impact_time", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("potential_impact_cost", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("potential_impact_quality", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("potential_impact_safety", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("impact_note", sa.Text(), nullable=True),
            sa.Column("delay_days_estimate", sa.Integer(), nullable=True),
            sa.Column("cost_estimate", sa.Float(), nullable=True),
            sa.Column("claim_notice_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("notice_deadline", sa.DateTime(), nullable=True),
            sa.Column("is_superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("superseded_by_item_id", sa.Integer(), nullable=True),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["discipline_code"], ["disciplines.code"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["recipient_org_id"], ["organizations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["contractor_org_id"], ["organizations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["consultant_org_id"], ["organizations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["superseded_by_item_id"], ["comm_items.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("item_no", name="uq_comm_items_item_no"),
        )
        op.create_index("ix_comm_items_item_no", "comm_items", ["item_no"], unique=False)
        op.create_index("ix_comm_items_item_type", "comm_items", ["item_type"], unique=False)
        op.create_index("ix_comm_items_project_code", "comm_items", ["project_code"], unique=False)
        op.create_index("ix_comm_items_discipline_code", "comm_items", ["discipline_code"], unique=False)
        op.create_index("ix_comm_items_status_code", "comm_items", ["status_code"], unique=False)
        op.create_index(
            "ix_comm_items_project_disc_type_status_created",
            "comm_items",
            ["project_code", "discipline_code", "item_type", "status_code", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_comm_items_response_due_date",
            "comm_items",
            ["response_due_date"],
            unique=False,
        )
        op.create_index(
            "ix_comm_items_notice_deadline",
            "comm_items",
            ["notice_deadline"],
            unique=False,
        )
        op.create_index(
            "ix_comm_items_org_module",
            "comm_items",
            ["organization_id", "item_type", "status_code"],
            unique=False,
        )

    if not _table_exists(inspector, "rfi_details"):
        op.create_table(
            "rfi_details",
            sa.Column("comm_item_id", sa.Integer(), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("proposed_solution", sa.Text(), nullable=True),
            sa.Column("answer_text", sa.Text(), nullable=True),
            sa.Column("answered_at", sa.DateTime(), nullable=True),
            sa.Column("drawing_refs_json", sa.Text(), nullable=True),
            sa.Column("spec_refs_json", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["comm_item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("comm_item_id"),
        )

    if not _table_exists(inspector, "ncr_details"):
        op.create_table(
            "ncr_details",
            sa.Column("comm_item_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=True),
            sa.Column("severity", sa.String(length=32), nullable=True),
            sa.Column("nonconformance_text", sa.Text(), nullable=False),
            sa.Column("containment_action", sa.Text(), nullable=True),
            sa.Column("rectification_method", sa.Text(), nullable=True),
            sa.Column("rectification_due_date", sa.DateTime(), nullable=True),
            sa.Column("root_cause", sa.Text(), nullable=True),
            sa.Column("corrective_action", sa.Text(), nullable=True),
            sa.Column("preventive_action", sa.Text(), nullable=True),
            sa.Column("verification_note", sa.Text(), nullable=True),
            sa.Column("verified_by_id", sa.Integer(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["comm_item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("comm_item_id"),
        )

    if not _table_exists(inspector, "tech_details"):
        op.create_table(
            "tech_details",
            sa.Column("comm_item_id", sa.Integer(), nullable=False),
            sa.Column("tech_subtype_code", sa.String(length=32), nullable=False),
            sa.Column("document_title", sa.String(length=255), nullable=True),
            sa.Column("document_no", sa.String(length=128), nullable=True),
            sa.Column("revision", sa.String(length=32), nullable=True),
            sa.Column("transmittal_no", sa.String(length=128), nullable=True),
            sa.Column("submission_no", sa.String(length=128), nullable=True),
            sa.Column("review_cycle_no", sa.Integer(), nullable=True),
            sa.Column("review_result_code", sa.String(length=32), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("meeting_date", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["comm_item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tech_subtype_code"], ["tech_subtypes.code"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["review_result_code"], ["review_results.code"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("comm_item_id"),
        )
        op.create_index(
            "ix_tech_details_tech_subtype_code",
            "tech_details",
            ["tech_subtype_code"],
            unique=False,
        )

    if not _table_exists(inspector, "item_sequences"):
        op.create_table(
            "item_sequences",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_code", sa.String(length=50), nullable=False),
            sa.Column("item_type", sa.String(length=16), nullable=False),
            sa.Column("discipline_code", sa.String(length=20), nullable=False),
            sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["discipline_code"], ["disciplines.code"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_code",
                "item_type",
                "discipline_code",
                name="uq_item_sequences_project_type_discipline",
            ),
        )

    if not _table_exists(inspector, "item_status_logs"):
        op.create_table(
            "item_status_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("from_status_code", sa.String(length=64), nullable=True),
            sa.Column("to_status_code", sa.String(length=64), nullable=False),
            sa.Column("changed_by_id", sa.Integer(), nullable=True),
            sa.Column("changed_at", sa.DateTime(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_item_status_logs_item_id", "item_status_logs", ["item_id"], unique=False)
        op.create_index(
            "ix_item_status_logs_item_changed_at",
            "item_status_logs",
            ["item_id", "changed_at"],
            unique=False,
        )

    if not _table_exists(inspector, "item_field_audits"):
        op.create_table(
            "item_field_audits",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("field_name", sa.String(length=64), nullable=False),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=True),
            sa.Column("changed_by_id", sa.Integer(), nullable=True),
            sa.Column("changed_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_item_field_audits_item_id", "item_field_audits", ["item_id"], unique=False)
        op.create_index(
            "ix_item_field_audits_item_changed_at",
            "item_field_audits",
            ["item_id", "changed_at"],
            unique=False,
        )

    if not _table_exists(inspector, "item_comments"):
        op.create_table(
            "item_comments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("comment_text", sa.Text(), nullable=False),
            sa.Column("comment_type", sa.String(length=32), nullable=False, server_default="comment"),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_item_comments_item_id", "item_comments", ["item_id"], unique=False)
        op.create_index(
            "ix_item_comments_item_created_at",
            "item_comments",
            ["item_id", "created_at"],
            unique=False,
        )

    if not _table_exists(inspector, "item_attachments"):
        op.create_table(
            "item_attachments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("stored_path", sa.String(length=1024), nullable=False),
            sa.Column("file_kind", sa.String(length=20), nullable=False, server_default="attachment"),
            sa.Column("mime_type", sa.String(length=128), nullable=True),
            sa.Column("detected_mime", sa.String(length=128), nullable=True),
            sa.Column("validation_status", sa.String(length=32), nullable=True),
            sa.Column("sha256", sa.String(length=64), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="local"),
            sa.Column("gdrive_file_id", sa.String(length=255), nullable=True),
            sa.Column("mirror_status", sa.String(length=32), nullable=True),
            sa.Column("mirror_updated_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_item_attachments_item_id", "item_attachments", ["item_id"], unique=False)
        op.create_index(
            "ix_item_attachments_item_uploaded_at",
            "item_attachments",
            ["item_id", "uploaded_at"],
            unique=False,
        )
        op.create_index(
            "ix_item_attachments_validation_status",
            "item_attachments",
            ["validation_status"],
            unique=False,
        )
        op.create_index("ix_item_attachments_sha256", "item_attachments", ["sha256"], unique=False)
        op.create_index(
            "ix_item_attachments_gdrive_file_id",
            "item_attachments",
            ["gdrive_file_id"],
            unique=False,
        )
        op.create_index(
            "ix_item_attachments_mirror_status",
            "item_attachments",
            ["mirror_status"],
            unique=False,
        )

    if not _table_exists(inspector, "item_relations"):
        op.create_table(
            "item_relations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("from_item_id", sa.Integer(), nullable=False),
            sa.Column("to_item_id", sa.Integer(), nullable=False),
            sa.Column("relation_type", sa.String(length=64), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_by_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["from_item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["to_item_id"], ["comm_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_item_relations_relation_type", "item_relations", ["relation_type"], unique=False)
        op.create_index("ix_item_relations_from_item", "item_relations", ["from_item_id"], unique=False)
        op.create_index("ix_item_relations_to_item", "item_relations", ["to_item_id"], unique=False)

    _seed_lookup_data()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "item_relations"):
        op.drop_table("item_relations")
    if _table_exists(inspector, "item_attachments"):
        op.drop_table("item_attachments")
    if _table_exists(inspector, "item_comments"):
        op.drop_table("item_comments")
    if _table_exists(inspector, "item_field_audits"):
        op.drop_table("item_field_audits")
    if _table_exists(inspector, "item_status_logs"):
        op.drop_table("item_status_logs")
    if _table_exists(inspector, "item_sequences"):
        op.drop_table("item_sequences")
    if _table_exists(inspector, "tech_details"):
        op.drop_table("tech_details")
    if _table_exists(inspector, "ncr_details"):
        op.drop_table("ncr_details")
    if _table_exists(inspector, "rfi_details"):
        op.drop_table("rfi_details")
    if _table_exists(inspector, "comm_items"):
        op.drop_table("comm_items")
    if _table_exists(inspector, "review_results"):
        op.drop_table("review_results")
    if _table_exists(inspector, "tech_subtypes"):
        op.drop_table("tech_subtypes")
    if _table_exists(inspector, "workflow_transitions"):
        op.drop_table("workflow_transitions")
    if _table_exists(inspector, "workflow_statuses"):
        op.drop_table("workflow_statuses")
