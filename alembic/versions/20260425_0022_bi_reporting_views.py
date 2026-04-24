"""Add BI reporting views for Power BI integration.

Revision ID: 20260425_0022
Revises: 20260424_0021
Create Date: 2026-04-25 10:00:00
"""
from alembic import op


revision = "20260425_0022"
down_revision = "20260424_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # View 1: Site log summary (one row per report)
    op.execute("""
    CREATE OR REPLACE VIEW v_bi_site_log_summary AS
    SELECT
        sl.id,
        sl.log_no,
        sl.log_type,
        sl.log_date,
        sl.weather,
        sl.status_code,
        sl.summary,
        sl.project_code,
        p.name_e AS project_name,
        sl.discipline_code,
        d.name_e AS discipline_name,
        o.name AS organization_name,
        o.org_type AS organization_type,
        sl.created_at,
        sl.submitted_at,
        sl.verified_at,
        cu.full_name AS created_by_name,
        su.full_name AS submitted_by_name,
        vu.full_name AS verified_by_name,
        (SELECT COUNT(*) FROM site_log_manpower_rows mr WHERE mr.site_log_id = sl.id) AS manpower_row_count,
        (SELECT COALESCE(SUM(mr.claimed_count), 0) FROM site_log_manpower_rows mr WHERE mr.site_log_id = sl.id) AS total_claimed_workers,
        (SELECT COALESCE(SUM(mr.claimed_hours), 0) FROM site_log_manpower_rows mr WHERE mr.site_log_id = sl.id) AS total_claimed_manhours,
        (SELECT COALESCE(SUM(mr.verified_count), 0) FROM site_log_manpower_rows mr WHERE mr.site_log_id = sl.id) AS total_verified_workers,
        (SELECT COALESCE(SUM(mr.verified_hours), 0) FROM site_log_manpower_rows mr WHERE mr.site_log_id = sl.id) AS total_verified_manhours,
        (SELECT COUNT(*) FROM site_log_equipment_rows er WHERE er.site_log_id = sl.id) AS equipment_row_count,
        (SELECT COALESCE(SUM(er.claimed_hours), 0) FROM site_log_equipment_rows er WHERE er.site_log_id = sl.id) AS total_equipment_claimed_hours,
        (SELECT COUNT(*) FROM site_log_activity_rows ar WHERE ar.site_log_id = sl.id) AS activity_row_count
    FROM site_logs sl
    LEFT JOIN projects p ON p.code = sl.project_code
    LEFT JOIN disciplines d ON d.code = sl.discipline_code
    LEFT JOIN organizations o ON o.id = sl.organization_id
    LEFT JOIN users cu ON cu.id = sl.created_by_id
    LEFT JOIN users su ON su.id = sl.submitted_by_id
    LEFT JOIN users vu ON vu.id = sl.verified_by_id;
    """)

    # View 2: Site log manpower detail (one row per manpower entry)
    op.execute("""
    CREATE OR REPLACE VIEW v_bi_site_log_manpower AS
    SELECT
        mr.id AS row_id,
        sl.log_no,
        sl.log_date,
        sl.log_type,
        sl.project_code,
        sl.discipline_code,
        sl.status_code,
        o.name AS organization_name,
        mr.role_code,
        mr.role_label,
        mr.claimed_count,
        mr.claimed_hours,
        mr.verified_count,
        mr.verified_hours,
        mr.note
    FROM site_log_manpower_rows mr
    JOIN site_logs sl ON sl.id = mr.site_log_id
    LEFT JOIN organizations o ON o.id = sl.organization_id;
    """)

    # View 3: Site log equipment detail (one row per equipment entry)
    op.execute("""
    CREATE OR REPLACE VIEW v_bi_site_log_equipment AS
    SELECT
        er.id AS row_id,
        sl.log_no,
        sl.log_date,
        sl.log_type,
        sl.project_code,
        sl.discipline_code,
        sl.status_code,
        o.name AS organization_name,
        er.equipment_code,
        er.equipment_label,
        er.claimed_status,
        er.claimed_hours,
        er.verified_status,
        er.verified_hours,
        er.note
    FROM site_log_equipment_rows er
    JOIN site_logs sl ON sl.id = er.site_log_id
    LEFT JOIN organizations o ON o.id = sl.organization_id;
    """)

    # View 4: Site log activity detail (one row per activity entry)
    op.execute("""
    CREATE OR REPLACE VIEW v_bi_site_log_activity AS
    SELECT
        ar.id AS row_id,
        sl.log_no,
        sl.log_date,
        sl.log_type,
        sl.project_code,
        sl.discipline_code,
        sl.status_code,
        o.name AS organization_name,
        ar.activity_code,
        ar.activity_title,
        ar.claimed_progress_pct,
        ar.verified_progress_pct,
        ar.source_system,
        ar.external_ref,
        ar.note
    FROM site_log_activity_rows ar
    JOIN site_logs sl ON sl.id = ar.site_log_id
    LEFT JOIN organizations o ON o.id = sl.organization_id;
    """)

    # View 5: Document status (one row per document)
    op.execute("""
    CREATE OR REPLACE VIEW v_bi_document_status AS
    SELECT
        doc.id,
        doc.doc_number,
        doc.doc_title_e,
        doc.doc_title_p,
        doc.project_code,
        p.name_e AS project_name,
        doc.discipline_code,
        d.name_e AS discipline_name,
        doc.phase_code,
        doc.package_code,
        doc.mdr_code,
        doc.created_at,
        doc.updated_at,
        doc.deleted_at,
        rev.revision AS latest_revision,
        rev.status AS latest_status,
        rev.created_at AS latest_revision_date,
        (SELECT COUNT(*) FROM document_revisions dr WHERE dr.document_id = doc.id) AS revision_count,
        (SELECT COUNT(*) FROM archive_files af
         JOIN document_revisions dr2 ON dr2.id = af.revision_id
         WHERE dr2.document_id = doc.id AND af.deleted_at IS NULL) AS file_count
    FROM mdr_documents doc
    LEFT JOIN projects p ON p.code = doc.project_code
    LEFT JOIN disciplines d ON d.code = doc.discipline_code
    LEFT JOIN LATERAL (
        SELECT dr.revision, dr.status, dr.created_at
        FROM document_revisions dr
        WHERE dr.document_id = doc.id
        ORDER BY dr.id DESC LIMIT 1
    ) rev ON true
    WHERE doc.deleted_at IS NULL;
    """)

    # View 6: Transmittal summary (one row per transmittal)
    op.execute("""
    CREATE OR REPLACE VIEW v_bi_transmittal_summary AS
    SELECT
        t.id,
        t.transmittal_no,
        t.project_code,
        p.name_e AS project_name,
        t.direction,
        t.send_date,
        t.reply_due_date,
        t.sender,
        t.receiver,
        t.lifecycle_status,
        t.doc_count,
        t.created_by_name,
        t.created_at,
        t.voided_at,
        t.void_reason
    FROM transmittals t
    LEFT JOIN projects p ON p.code = t.project_code;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_bi_transmittal_summary;")
    op.execute("DROP VIEW IF EXISTS v_bi_document_status;")
    op.execute("DROP VIEW IF EXISTS v_bi_site_log_activity;")
    op.execute("DROP VIEW IF EXISTS v_bi_site_log_equipment;")
    op.execute("DROP VIEW IF EXISTS v_bi_site_log_manpower;")
    op.execute("DROP VIEW IF EXISTS v_bi_site_log_summary;")
