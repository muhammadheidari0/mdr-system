from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import ArchiveFile, DocumentRevision, MdrDocument
from app.db.session import engine
from app.services.edms_export_manifest import export_archive_manifest_rows


def test_edms_archive_manifest_export_contains_expected_keys() -> None:
    doc_number = f"TSEED-EDMS-{uuid.uuid4().hex[:8].upper()}"
    with Session(engine) as db:
        document = MdrDocument(
            doc_number=doc_number,
            project_code="TSEED",
            phase_code="X",
            discipline_code="GN",
            package_code="00",
            block="A",
            level_code="GEN",
            mdr_code="E",
            subject="Native EDMS Export",
        )
        db.add(document)
        db.flush()

        revision = DocumentRevision(document_id=int(document.id), revision="00", status="IFA")
        db.add(revision)
        db.flush()

        archive_file = ArchiveFile(
            revision_id=int(revision.id),
            original_name="native-edms.pdf",
            stored_path=f"./files/technical/{doc_number}.pdf",
            mime_type="application/pdf",
            size_bytes=128,
            file_kind="pdf",
            revision="00",
            status="IFA",
            uploaded_at=datetime.utcnow(),
            uploaded_by="seed.manager@mdr.local",
        )
        db.add(archive_file)
        db.commit()

        items = export_archive_manifest_rows(db, project_code="TSEED")

    row = next(item for item in items if item["doc_number"] == doc_number)
    assert row["project_code"] == "TSEED"
    assert row["revision"] == "00"
    assert row["file_kind"] == "pdf"
    assert row["source_path"].endswith(f"{doc_number}.pdf")
