"""Split TECH work instructions into a dedicated module.

Revision ID: 20260510_0048
Revises: 20260510_0047
Create Date: 2026-05-10 12:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260510_0048"
down_revision = "20260510_0047"
branch_labels = None
depends_on = None


def _seed_work_instruction_workflow() -> None:
    bind = op.get_bind()
    status_rows = [
        ("WORK_INSTRUCTION", "DRAFT", "Draft", False, 10),
        ("WORK_INSTRUCTION", "SUBMITTED", "Submitted", False, 20),
        ("WORK_INSTRUCTION", "IN_REVIEW", "In Review", False, 30),
        ("WORK_INSTRUCTION", "APPROVED", "Approved", False, 40),
        ("WORK_INSTRUCTION", "APPROVED_AS_NOTED", "Approved As Noted", False, 50),
        ("WORK_INSTRUCTION", "REVISE_RESUBMIT", "Revise & Resubmit", False, 60),
        ("WORK_INSTRUCTION", "REJECTED", "Rejected", False, 70),
        ("WORK_INSTRUCTION", "CLOSED", "Closed", True, 80),
    ]
    for item_type, code, label, is_terminal, sort_order in status_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO workflow_statuses (item_type, code, label, is_terminal, sort_order, is_active)
                SELECT
                    CAST(:item_type AS VARCHAR),
                    CAST(:code AS VARCHAR),
                    CAST(:label AS VARCHAR),
                    CAST(:is_terminal AS BOOLEAN),
                    CAST(:sort_order AS INTEGER),
                    TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM workflow_statuses
                    WHERE item_type = CAST(:item_type AS VARCHAR)
                      AND code = CAST(:code AS VARCHAR)
                )
                """
            ),
            {
                "item_type": item_type,
                "code": code,
                "label": label,
                "is_terminal": bool(is_terminal),
                "sort_order": int(sort_order),
            },
        )

    transition_rows = [
        ("WORK_INSTRUCTION", "DRAFT", "SUBMITTED", False),
        ("WORK_INSTRUCTION", "SUBMITTED", "IN_REVIEW", False),
        ("WORK_INSTRUCTION", "IN_REVIEW", "APPROVED", False),
        ("WORK_INSTRUCTION", "IN_REVIEW", "APPROVED_AS_NOTED", False),
        ("WORK_INSTRUCTION", "IN_REVIEW", "REVISE_RESUBMIT", False),
        ("WORK_INSTRUCTION", "IN_REVIEW", "REJECTED", False),
        ("WORK_INSTRUCTION", "REVISE_RESUBMIT", "SUBMITTED", False),
        ("WORK_INSTRUCTION", "APPROVED", "CLOSED", False),
        ("WORK_INSTRUCTION", "APPROVED_AS_NOTED", "CLOSED", False),
        ("WORK_INSTRUCTION", "REJECTED", "CLOSED", False),
    ]
    for item_type, from_status, to_status, requires_note in transition_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO workflow_transitions (
                    item_type, from_status_code, to_status_code, requires_note, is_active
                )
                SELECT
                    CAST(:item_type AS VARCHAR),
                    CAST(:from_status AS VARCHAR),
                    CAST(:to_status AS VARCHAR),
                    CAST(:requires_note AS BOOLEAN),
                    TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM workflow_transitions
                    WHERE item_type = CAST(:item_type AS VARCHAR)
                      AND from_status_code = CAST(:from_status AS VARCHAR)
                      AND to_status_code = CAST(:to_status AS VARCHAR)
                )
                """
            ),
            {
                "item_type": item_type,
                "from_status": from_status,
                "to_status": to_status,
                "requires_note": bool(requires_note),
            },
        )


def _copy_existing_tech_items() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO work_instructions (
                legacy_comm_item_id,
                instruction_no,
                legacy_subtype,
                is_legacy_readonly,
                project_code,
                discipline_code,
                organization_id,
                zone,
                title,
                description,
                required_action,
                status_code,
                priority,
                response_due_date,
                assignee_user_id,
                recipient_org_id,
                contractor_org_id,
                consultant_org_id,
                contract_clause_ref,
                spec_clause_ref,
                wbs_code,
                activity_code,
                document_title,
                document_no,
                revision,
                transmittal_no,
                submission_no,
                review_cycle_no,
                review_result_code,
                review_note,
                reviewed_by_id,
                reviewed_at,
                potential_impact_time,
                potential_impact_cost,
                potential_impact_quality,
                potential_impact_safety,
                impact_note,
                delay_days_estimate,
                cost_estimate,
                claim_notice_required,
                notice_deadline,
                created_by_id,
                created_at,
                updated_at
            )
            SELECT
                ci.id,
                ci.item_no,
                td.tech_subtype_code,
                CASE WHEN COALESCE(td.tech_subtype_code, 'INSTRUCTION') <> 'INSTRUCTION' THEN TRUE ELSE FALSE END,
                ci.project_code,
                ci.discipline_code,
                ci.organization_id,
                ci.zone,
                ci.title,
                ci.short_description,
                td.review_note,
                ci.status_code,
                ci.priority,
                ci.response_due_date,
                ci.assignee_user_id,
                ci.recipient_org_id,
                ci.contractor_org_id,
                ci.consultant_org_id,
                ci.contract_clause_ref,
                ci.spec_clause_ref,
                ci.wbs_code,
                ci.activity_code,
                td.document_title,
                td.document_no,
                td.revision,
                td.transmittal_no,
                td.submission_no,
                td.review_cycle_no,
                td.review_result_code,
                td.review_note,
                td.reviewed_by_id,
                td.reviewed_at,
                ci.potential_impact_time,
                ci.potential_impact_cost,
                ci.potential_impact_quality,
                ci.potential_impact_safety,
                ci.impact_note,
                ci.delay_days_estimate,
                ci.cost_estimate,
                ci.claim_notice_required,
                ci.notice_deadline,
                ci.created_by_id,
                ci.created_at,
                ci.updated_at
            FROM comm_items ci
            LEFT JOIN tech_details td ON td.comm_item_id = ci.id
            WHERE ci.item_type = 'TECH'
              AND NOT EXISTS (
                  SELECT 1 FROM work_instructions wi
                  WHERE wi.legacy_comm_item_id = ci.id
                     OR wi.instruction_no = ci.item_no
              )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO work_instruction_sequences (project_code, discipline_code, next_value, updated_at)
            SELECT project_code, discipline_code, MAX(next_value), MAX(updated_at)
            FROM item_sequences
            WHERE item_type = 'TECH'
            GROUP BY project_code, discipline_code
            HAVING NOT EXISTS (
                SELECT 1 FROM work_instruction_sequences wis
                WHERE wis.project_code = item_sequences.project_code
                  AND wis.discipline_code = item_sequences.discipline_code
            )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO work_instruction_status_logs (
                instruction_id, from_status_code, to_status_code, changed_by_id, changed_at, note
            )
            SELECT wi.id, isl.from_status_code, isl.to_status_code, isl.changed_by_id, isl.changed_at, isl.note
            FROM item_status_logs isl
            JOIN work_instructions wi ON wi.legacy_comm_item_id = isl.item_id
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO work_instruction_field_audits (
                instruction_id, field_name, old_value, new_value, changed_by_id, changed_at
            )
            SELECT wi.id, ifa.field_name, ifa.old_value, ifa.new_value, ifa.changed_by_id, ifa.changed_at
            FROM item_field_audits ifa
            JOIN work_instructions wi ON wi.legacy_comm_item_id = ifa.item_id
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO work_instruction_comments (
                instruction_id, comment_text, comment_type, created_by_id, created_at
            )
            SELECT wi.id, ic.comment_text, ic.comment_type, ic.created_by_id, ic.created_at
            FROM item_comments ic
            JOIN work_instructions wi ON wi.legacy_comm_item_id = ic.item_id
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO work_instruction_attachments (
                instruction_id,
                legacy_item_attachment_id,
                file_name,
                stored_path,
                file_kind,
                scope_code,
                slot_code,
                note,
                mime_type,
                detected_mime,
                validation_status,
                sha256,
                size_bytes,
                storage_backend,
                gdrive_file_id,
                mirror_provider,
                mirror_remote_id,
                mirror_remote_url,
                mirror_status,
                mirror_updated_at,
                deleted_at,
                uploaded_by_id,
                uploaded_at
            )
            SELECT
                wi.id,
                ia.id,
                ia.file_name,
                ia.stored_path,
                ia.file_kind,
                ia.scope_code,
                ia.slot_code,
                ia.note,
                ia.mime_type,
                ia.detected_mime,
                ia.validation_status,
                ia.sha256,
                ia.size_bytes,
                ia.storage_backend,
                ia.gdrive_file_id,
                ia.mirror_provider,
                ia.mirror_remote_id,
                ia.mirror_remote_url,
                ia.mirror_status,
                ia.mirror_updated_at,
                ia.deleted_at,
                ia.uploaded_by_id,
                ia.uploaded_at
            FROM item_attachments ia
            JOIN work_instructions wi ON wi.legacy_comm_item_id = ia.item_id
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO work_instruction_relations (
                from_instruction_id,
                from_comm_item_id,
                to_instruction_id,
                to_comm_item_id,
                relation_type,
                note,
                created_by_id,
                created_at
            )
            SELECT
                wi_from.id,
                CASE WHEN wi_from.id IS NULL THEN ir.from_item_id ELSE NULL END,
                wi_to.id,
                CASE WHEN wi_to.id IS NULL THEN ir.to_item_id ELSE NULL END,
                ir.relation_type,
                ir.note,
                ir.created_by_id,
                ir.created_at
            FROM item_relations ir
            LEFT JOIN work_instructions wi_from ON wi_from.legacy_comm_item_id = ir.from_item_id
            LEFT JOIN work_instructions wi_to ON wi_to.legacy_comm_item_id = ir.to_item_id
            WHERE wi_from.id IS NOT NULL OR wi_to.id IS NOT NULL
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        "work_instructions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("legacy_comm_item_id", sa.Integer(), nullable=True),
        sa.Column("instruction_no", sa.String(length=128), nullable=False),
        sa.Column("legacy_subtype", sa.String(length=32), nullable=True),
        sa.Column("is_legacy_readonly", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("discipline_code", sa.String(length=20), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("zone", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_action", sa.Text(), nullable=True),
        sa.Column("status_code", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="NORMAL"),
        sa.Column("response_due_date", sa.DateTime(), nullable=True),
        sa.Column("assignee_user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_org_id", sa.Integer(), nullable=True),
        sa.Column("contractor_org_id", sa.Integer(), nullable=True),
        sa.Column("consultant_org_id", sa.Integer(), nullable=True),
        sa.Column("contract_clause_ref", sa.String(length=255), nullable=True),
        sa.Column("spec_clause_ref", sa.String(length=255), nullable=True),
        sa.Column("wbs_code", sa.String(length=64), nullable=True),
        sa.Column("activity_code", sa.String(length=64), nullable=True),
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
        sa.Column("potential_impact_time", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("potential_impact_cost", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("potential_impact_quality", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("potential_impact_safety", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("impact_note", sa.Text(), nullable=True),
        sa.Column("delay_days_estimate", sa.Integer(), nullable=True),
        sa.Column("cost_estimate", sa.Float(), nullable=True),
        sa.Column("claim_notice_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notice_deadline", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["legacy_comm_item_id"], ["comm_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["discipline_code"], ["disciplines.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contractor_org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["consultant_org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_result_code"], ["review_results.code"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instruction_no", name="uq_work_instructions_instruction_no"),
        sa.UniqueConstraint("legacy_comm_item_id", name="uq_work_instructions_legacy_comm_item"),
    )
    op.create_index("ix_work_instructions_instruction_no", "work_instructions", ["instruction_no"], unique=False)
    op.create_index("ix_work_instructions_legacy_comm_item_id", "work_instructions", ["legacy_comm_item_id"], unique=False)
    op.create_index("ix_work_instructions_legacy_subtype", "work_instructions", ["legacy_subtype"], unique=False)
    op.create_index(
        "ix_work_instructions_project_disc_status_created",
        "work_instructions",
        ["project_code", "discipline_code", "status_code", "created_at"],
        unique=False,
    )
    op.create_index("ix_work_instructions_response_due_date", "work_instructions", ["response_due_date"], unique=False)
    op.create_index("ix_work_instructions_org_status", "work_instructions", ["organization_id", "status_code"], unique=False)

    op.create_table(
        "work_instruction_sequences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_code", sa.String(length=50), nullable=False),
        sa.Column("discipline_code", sa.String(length=20), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_code"], ["projects.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["discipline_code"], ["disciplines.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_code",
            "discipline_code",
            name="uq_work_instruction_sequences_project_discipline",
        ),
    )

    op.create_table(
        "work_instruction_status_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instruction_id", sa.Integer(), nullable=False),
        sa.Column("from_status_code", sa.String(length=64), nullable=True),
        sa.Column("to_status_code", sa.String(length=64), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["instruction_id"], ["work_instructions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_work_instruction_status_logs_instruction_changed_at",
        "work_instruction_status_logs",
        ["instruction_id", "changed_at"],
        unique=False,
    )

    op.create_table(
        "work_instruction_field_audits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instruction_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_by_id", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["instruction_id"], ["work_instructions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_work_instruction_field_audits_instruction_changed_at",
        "work_instruction_field_audits",
        ["instruction_id", "changed_at"],
        unique=False,
    )

    op.create_table(
        "work_instruction_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instruction_id", sa.Integer(), nullable=False),
        sa.Column("comment_text", sa.Text(), nullable=False),
        sa.Column("comment_type", sa.String(length=32), nullable=False, server_default="comment"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["instruction_id"], ["work_instructions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_work_instruction_comments_instruction_created_at",
        "work_instruction_comments",
        ["instruction_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "work_instruction_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instruction_id", sa.Integer(), nullable=False),
        sa.Column("legacy_item_attachment_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column("file_kind", sa.String(length=20), nullable=False, server_default="attachment"),
        sa.Column("scope_code", sa.String(length=16), nullable=False, server_default="GENERAL"),
        sa.Column("slot_code", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("detected_mime", sa.String(length=128), nullable=True),
        sa.Column("validation_status", sa.String(length=32), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("gdrive_file_id", sa.String(length=255), nullable=True),
        sa.Column("mirror_provider", sa.String(length=32), nullable=True),
        sa.Column("mirror_remote_id", sa.String(length=255), nullable=True),
        sa.Column("mirror_remote_url", sa.String(length=1024), nullable=True),
        sa.Column("mirror_status", sa.String(length=32), nullable=True),
        sa.Column("mirror_updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["instruction_id"], ["work_instructions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["legacy_item_attachment_id"], ["item_attachments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_work_instruction_attachments_instruction_uploaded_at",
        "work_instruction_attachments",
        ["instruction_id", "uploaded_at"],
        unique=False,
    )
    op.create_index(
        "ix_work_instruction_attachments_instruction_scope_uploaded_at",
        "work_instruction_attachments",
        ["instruction_id", "scope_code", "uploaded_at"],
        unique=False,
    )
    op.create_index(
        "ix_work_instruction_attachments_legacy_item_attachment_id",
        "work_instruction_attachments",
        ["legacy_item_attachment_id"],
        unique=False,
    )

    op.create_table(
        "work_instruction_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_instruction_id", sa.Integer(), nullable=True),
        sa.Column("from_comm_item_id", sa.Integer(), nullable=True),
        sa.Column("to_instruction_id", sa.Integer(), nullable=True),
        sa.Column("to_comm_item_id", sa.Integer(), nullable=True),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["from_instruction_id"], ["work_instructions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_comm_item_id"], ["comm_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_instruction_id"], ["work_instructions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_comm_item_id"], ["comm_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_instruction_relations_from_instruction", "work_instruction_relations", ["from_instruction_id"], unique=False)
    op.create_index("ix_work_instruction_relations_to_instruction", "work_instruction_relations", ["to_instruction_id"], unique=False)
    op.create_index("ix_work_instruction_relations_from_comm_item", "work_instruction_relations", ["from_comm_item_id"], unique=False)
    op.create_index("ix_work_instruction_relations_to_comm_item", "work_instruction_relations", ["to_comm_item_id"], unique=False)

    _seed_work_instruction_workflow()
    _copy_existing_tech_items()


def downgrade() -> None:
    op.drop_index("ix_work_instruction_relations_to_comm_item", table_name="work_instruction_relations")
    op.drop_index("ix_work_instruction_relations_from_comm_item", table_name="work_instruction_relations")
    op.drop_index("ix_work_instruction_relations_to_instruction", table_name="work_instruction_relations")
    op.drop_index("ix_work_instruction_relations_from_instruction", table_name="work_instruction_relations")
    op.drop_table("work_instruction_relations")

    op.drop_index("ix_work_instruction_attachments_legacy_item_attachment_id", table_name="work_instruction_attachments")
    op.drop_index("ix_work_instruction_attachments_instruction_scope_uploaded_at", table_name="work_instruction_attachments")
    op.drop_index("ix_work_instruction_attachments_instruction_uploaded_at", table_name="work_instruction_attachments")
    op.drop_table("work_instruction_attachments")

    op.drop_index("ix_work_instruction_comments_instruction_created_at", table_name="work_instruction_comments")
    op.drop_table("work_instruction_comments")

    op.drop_index("ix_work_instruction_field_audits_instruction_changed_at", table_name="work_instruction_field_audits")
    op.drop_table("work_instruction_field_audits")

    op.drop_index("ix_work_instruction_status_logs_instruction_changed_at", table_name="work_instruction_status_logs")
    op.drop_table("work_instruction_status_logs")

    op.drop_table("work_instruction_sequences")

    op.drop_index("ix_work_instructions_org_status", table_name="work_instructions")
    op.drop_index("ix_work_instructions_response_due_date", table_name="work_instructions")
    op.drop_index("ix_work_instructions_project_disc_status_created", table_name="work_instructions")
    op.drop_index("ix_work_instructions_legacy_subtype", table_name="work_instructions")
    op.drop_index("ix_work_instructions_legacy_comm_item_id", table_name="work_instructions")
    op.drop_index("ix_work_instructions_instruction_no", table_name="work_instructions")
    op.drop_table("work_instructions")

    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM workflow_transitions WHERE item_type = 'WORK_INSTRUCTION'"))
    bind.execute(sa.text("DELETE FROM workflow_statuses WHERE item_type = 'WORK_INSTRUCTION'"))
