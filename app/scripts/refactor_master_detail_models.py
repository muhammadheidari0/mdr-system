from __future__ import annotations

from pathlib import Path


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _must_replace(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Pattern not found for {label}:\n{old!r}")
    return text.replace(old, new, 1)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    models_path = repo_root / "app" / "db" / "models.py"

    if not models_path.exists():
        raise RuntimeError(f"models.py not found at: {models_path}")

    original = models_path.read_text(encoding="utf-8")
    nl = _detect_newline(original)

    backup = models_path.with_suffix(models_path.suffix + ".bak_before_master_detail")
    backup.write_text(original, encoding="utf-8")

    text = original

    # --- MdrDocument: remove doc_number+revision UniqueConstraint ---
    text = _must_replace(
        text,
        f"        UniqueConstraint(\"doc_number\", \"revision\", name=\"uix_doc_revision\"),{nl}",
        "",
        label="remove_uix_doc_revision",
    )

    # --- MdrDocument: doc_number becomes unique ---
    text = _must_replace(
        text,
        f"    doc_number: Mapped[str] = mapped_column(String(120), index=True) # Not unique globally anymore{nl}",
        f"    doc_number: Mapped[str] = mapped_column(String(120), unique=True, index=True) # Not unique globally anymore{nl}",
        label="make_doc_number_unique",
    )

    # --- MdrDocument: remove revision/status/file_path columns (leave the comment line) ---
    text = _must_replace(
        text,
        f"    revision: Mapped[str] = mapped_column(String(50), default=\"00\"){nl}",
        "",
        label="remove_mdr_document_revision_column",
    )
    text = _must_replace(
        text,
        f"    status: Mapped[str | None] = mapped_column(String(50)) # Now can be joined with DocStatus if needed, but string is flexible{nl}",
        "",
        label="remove_mdr_document_status_column",
    )
    text = _must_replace(
        text,
        f"    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True){nl}",
        "",
        label="remove_mdr_document_file_path_column",
    )

    # Clean up extra blank lines if any ended up duplicated.
    text = text.replace(f"{nl}{nl}{nl}", f"{nl}{nl}")

    # --- MdrDocument: swap archive_files relationship to revisions ---
    text = _must_replace(
        text,
        f"    archive_files: Mapped[list[\"ArchiveFile\"]] = relationship(back_populates=\"document\"){nl}",
        (
            f"    revisions: Mapped[list[\"DocumentRevision\"]] = relationship({nl}"
            f"        back_populates=\"document\", cascade=\"all, delete-orphan\"{nl}"
            f"    ){nl}"
        ),
        label="swap_archive_files_relationship",
    )

    # --- Insert DocumentRevision model before Archive section ---
    archive_anchor = (
        f"{nl}{nl}# ----------------------------------------------------------------{nl}"
        f"# 5. Archive{nl}"
        f"# ----------------------------------------------------------------{nl}"
    )
    if archive_anchor not in text:
        raise RuntimeError("Archive section anchor not found; models.py format changed")

    if "class DocumentRevision(Base):" not in text:
        docrev_block = (
            f"{nl}{nl}class DocumentRevision(Base):{nl}"
            f"    __tablename__ = \"document_revisions\"{nl}{nl}"
            f"    __table_args__ = ({nl}"
            f"        UniqueConstraint(\"document_id\", \"revision\", name=\"uix_document_revision\"),{nl}"
            f"        Index(\"ix_docrev_document_id\", \"document_id\"),{nl}"
            f"    ){nl}{nl}"
            f"    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True){nl}{nl}"
            f"    document_id: Mapped[int] = mapped_column({nl}"
            f"        Integer, ForeignKey(\"mdr_documents.id\", ondelete=\"CASCADE\"){nl}"
            f"    ){nl}{nl}"
            f"    revision: Mapped[str] = mapped_column(String(50), default=\"00\"){nl}"
            f"    status: Mapped[str | None] = mapped_column(String(50)){nl}"
            f"    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True){nl}{nl}"
            f"    notes: Mapped[str | None] = mapped_column(Text){nl}"
            f"    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow){nl}{nl}"
            f"    document: Mapped[\"MdrDocument\"] = relationship(back_populates=\"revisions\"){nl}"
            f"    archive_files: Mapped[list[\"ArchiveFile\"]] = relationship(back_populates=\"document_revision\"){nl}"
        )
        text = text.replace(archive_anchor, docrev_block + archive_anchor, 1)

    # --- ArchiveFile: repoint FK to document_revisions and relationship (avoid name conflict with existing `revision` column) ---
    text = _must_replace(
        text,
        (
            f"    mdr_record_id: Mapped[int] = mapped_column({nl}"
            f"        Integer, ForeignKey(\"mdr_documents.id\", ondelete=\"CASCADE\"){nl}"
            f"    ){nl}"
        ),
        (
            f"    revision_id: Mapped[int] = mapped_column({nl}"
            f"        Integer, ForeignKey(\"document_revisions.id\", ondelete=\"CASCADE\"){nl}"
            f"    ){nl}"
        ),
        label="archivefile_fk_to_revision",
    )

    text = _must_replace(
        text,
        f"    document: Mapped[\"MdrDocument\"] = relationship(back_populates=\"archive_files\"){nl}",
        f"    document_revision: Mapped[\"DocumentRevision\"] = relationship(back_populates=\"archive_files\"){nl}",
        label="archivefile_relationship_to_revision",
    )

    models_path.write_text(text, encoding="utf-8")

    print("OK: models.py updated")
    print("Backup:", backup)


if __name__ == "__main__":
    main()
