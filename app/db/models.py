# app/db/models.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Text,
    Index,
    Float,
    Boolean,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign

from app.db.base import Base

# ----------------------------------------------------------------
# 1. Authentication & Users
# ----------------------------------------------------------------
class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("code", name="uq_organizations_code"),
        Index("ix_organizations_parent", "parent_id"),
        Index("ix_organizations_type", "org_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    org_type: Mapped[str] = mapped_column(String(32), nullable=False, default="contractor")
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    parent: Mapped["Organization | None"] = relationship(
        "Organization",
        remote_side="Organization.id",
        back_populates="children",
    )
    children: Mapped[List["Organization"]] = relationship(
        "Organization",
        back_populates="parent",
    )
    users: Mapped[List["User"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))

    role: Mapped[str] = mapped_column(String(50), default="user")
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organization_role: Mapped[str] = mapped_column(String(32), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transmittals_created: Mapped[List["Transmittal"]] = relationship(back_populates="creator")
    correspondences_created: Mapped[List["Correspondence"]] = relationship(back_populates="created_by")
    correspondence_actions_from: Mapped[List["CorrespondenceAction"]] = relationship(
        "CorrespondenceAction",
        foreign_keys="CorrespondenceAction.from_user_id",
        back_populates="from_user",
    )
    correspondence_actions_to: Mapped[List["CorrespondenceAction"]] = relationship(
        "CorrespondenceAction",
        foreign_keys="CorrespondenceAction.to_user_id",
        back_populates="to_user",
    )
    correspondence_attachments_uploaded: Mapped[List["CorrespondenceAttachment"]] = relationship(
        "CorrespondenceAttachment",
        foreign_keys="CorrespondenceAttachment.uploaded_by_id",
        back_populates="uploaded_by",
    )
    settings_audit_logs: Mapped[List["SettingsAuditLog"]] = relationship(back_populates="actor")
    project_scopes: Mapped[List["UserProjectScope"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    discipline_scopes: Mapped[List["UserDisciplineScope"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    organization: Mapped["Organization | None"] = relationship(back_populates="users")

# ----------------------------------------------------------------
# 2. Base Tables & Lookups
# ----------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # T202
    name_e: Mapped[str | None] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))
    root_path: Mapped[str | None] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    docnum_template: Mapped[str] = mapped_column(
        String, default="{PROJECT}-{MDR}{PKG}-{BLK}{LVL}"
    )

    documents: Mapped[List["MdrDocument"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    transmittals: Mapped[List["Transmittal"]] = relationship(back_populates="project")
    correspondences: Mapped[List["Correspondence"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    blocks: Mapped[List["Block"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("project_code", "code", name="uq_blocks_project_code"),
        Index("ix_blocks_project_code", "project_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    project_code: Mapped[str] = mapped_column(String(50), ForeignKey("projects.code"))
    code: Mapped[str] = mapped_column(String(10))  # T, A, B, ...
    name_e: Mapped[str | None] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped["Project"] = relationship(back_populates="blocks")

class Phase(Base):
    __tablename__ = "phases"

    ph_code: Mapped[str] = mapped_column(String(10), primary_key=True)  # P,E,C...
    name_e: Mapped[str] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))

    documents: Mapped[List["MdrDocument"]] = relationship(back_populates="phase")

class Discipline(Base):
    __tablename__ = "disciplines"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)  # AR, ST
    name_e: Mapped[str] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))

    packages: Mapped[List["Package"]] = relationship(
        back_populates="discipline", cascade="all, delete-orphan"
    )
    documents: Mapped[List["MdrDocument"]] = relationship(back_populates="discipline")
    correspondences: Mapped[List["Correspondence"]] = relationship(back_populates="discipline")


class IssuingEntity(Base):
    __tablename__ = "issuing_entities"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)  # COM, T202, G
    name_e: Mapped[str] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))
    project_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    correspondences: Mapped[List["Correspondence"]] = relationship(back_populates="issuing_entity")


class CorrespondenceCategory(Base):
    __tablename__ = "correspondence_categories"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)  # CO, M, L, ...
    name_e: Mapped[str] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    correspondences: Mapped[List["Correspondence"]] = relationship(back_populates="category")

class Package(Base):
    __tablename__ = "packages"
    __table_args__ = (
        UniqueConstraint("discipline_code", "package_code", name="uq_packages_disc_pkg"),
        Index("ix_packages_disc", "discipline_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discipline_code: Mapped[str] = mapped_column(String(20), ForeignKey("disciplines.code"))
    package_code: Mapped[str] = mapped_column(String(30))  # 01, AR01, ...
    name_e: Mapped[str] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))

    discipline: Mapped["Discipline"] = relationship(back_populates="packages")

    documents: Mapped[List["MdrDocument"]] = relationship(
        "MdrDocument",
        primaryjoin=(
            "and_("
            "foreign(MdrDocument.discipline_code)==Package.discipline_code, "
            "foreign(MdrDocument.package_code)==Package.package_code"
            ")"
        ),
        viewonly=True,
    )

class Level(Base):
    __tablename__ = "levels"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)  # GEN, L01
    name_e: Mapped[str | None] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    documents: Mapped[List["MdrDocument"]] = relationship(back_populates="level")

# ----------------------------------------------------------------
# 3. Document Status & Categories
# ----------------------------------------------------------------
class DocStatus(Base):
    __tablename__ = "doc_statuses"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True) # IFA, IFC
    name: Mapped[str] = mapped_column(String(100)) 
    description: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class MdrCategory(Base):
    __tablename__ = "mdr_categories"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)  # E, P, C
    name_e: Mapped[str] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))
    folder_name: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    documents: Mapped[List["MdrDocument"]] = relationship(back_populates="mdr_category")

# ----------------------------------------------------------------
# 4. MDR Core (MdrDocument + DocumentRevision)
# ----------------------------------------------------------------
class MdrDocument(Base):
    __tablename__ = "mdr_documents"
    
    __table_args__ = (
        Index("ix_mdr_doc_num", "doc_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Document Number (Main Unique Key)
    doc_number: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    
    doc_title_e: Mapped[str | None] = mapped_column(String(255))
    doc_title_p: Mapped[str | None] = mapped_column(String(255))
    
    # ✅ Important Subject column for grouping and serial generation
    subject: Mapped[str | None] = mapped_column(String(255))

    # Foreign Keys (Relationships)
    project_code: Mapped[str] = mapped_column(String(50), ForeignKey("projects.code"))
    phase_code: Mapped[str | None] = mapped_column(String(10), ForeignKey("phases.ph_code"))
    discipline_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("disciplines.code"))
    package_code: Mapped[str | None] = mapped_column(String(30)) # Logical relation with Package

    block: Mapped[str | None] = mapped_column(String(10))
    level_code: Mapped[str | None] = mapped_column(String(20), ForeignKey("levels.code"))

    mdr_code: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("mdr_categories.code"), nullable=True
    )

    estimated_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="documents")
    phase: Mapped["Phase"] = relationship(back_populates="documents")
    discipline: Mapped["Discipline"] = relationship(back_populates="documents")
    level: Mapped["Level"] = relationship(back_populates="documents")
    mdr_category: Mapped["MdrCategory"] = relationship(back_populates="documents")

    # Special relation with package (composite key)
    package: Mapped["Package"] = relationship(
        "Package",
        primaryjoin=(
            "and_("
            "foreign(MdrDocument.discipline_code)==Package.discipline_code, "
            "foreign(MdrDocument.package_code)==Package.package_code"
            ")"
        ),
        viewonly=True,
    )

    revisions: Mapped[List["DocumentRevision"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

class DocumentRevision(Base):
    __tablename__ = "document_revisions"

    __table_args__ = (
        UniqueConstraint("document_id", "revision", name="uix_document_revision"),
        Index("ix_docrev_document_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="CASCADE")
    )

    revision: Mapped[str] = mapped_column(String(50), default="00")
    status: Mapped[str | None] = mapped_column(String(50))
    
    # ✅ Added file_name column as requested
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped["MdrDocument"] = relationship(back_populates="revisions")
    archive_files: Mapped[List["ArchiveFile"]] = relationship(back_populates="document_revision")


# ----------------------------------------------------------------
# 5. Archive & Transmittals
# ----------------------------------------------------------------
class ArchiveFile(Base):
    __tablename__ = "archive_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_revisions.id", ondelete="CASCADE")
    )

    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(1024))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    detected_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local", nullable=False, index=True)
    gdrive_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mirror_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    file_kind: Mapped[str] = mapped_column(String(20), default="pdf", nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    companion_file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_files.id"), nullable=True
    )

    revision: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(64))

    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    uploaded_by: Mapped[str | None] = mapped_column(String(128))

    document_revision: Mapped["DocumentRevision"] = relationship(back_populates="archive_files")
    companion_file: Mapped[Optional["ArchiveFile"]] = relationship(
        "ArchiveFile",
        remote_side=[id],
        foreign_keys=[companion_file_id],
        uselist=False,
    )

class Transmittal(Base):
    __tablename__ = "transmittals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # T202-T-O-0410001
    project_code: Mapped[str] = mapped_column(String(32), ForeignKey("projects.code"))

    direction: Mapped[str] = mapped_column(String(1))  # I/O
    send_date: Mapped[str | None] = mapped_column(String(32))
    reply_due_date: Mapped[str | None] = mapped_column(String(32))

    sender: Mapped[str] = mapped_column(String(255))
    receiver: Mapped[str] = mapped_column(String(255))

    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_by_name: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lifecycle_status: Mapped[str | None] = mapped_column(String(16), index=True)
    void_reason: Mapped[str | None] = mapped_column(String(500))
    voided_by: Mapped[str | None] = mapped_column(String(255))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)

    project: Mapped["Project"] = relationship(back_populates="transmittals")
    creator: Mapped["User"] = relationship(back_populates="transmittals_created")

    docs: Mapped[List["TransmittalDoc"]] = relationship(
        back_populates="transmittal", cascade="all, delete-orphan"
    )

class TransmittalDoc(Base):
    __tablename__ = "transmittal_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transmittal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("transmittals.id", ondelete="CASCADE")
    )

    doc_group: Mapped[str | None] = mapped_column(String(8))
    department: Mapped[str | None] = mapped_column(String(128))

    document_code: Mapped[str] = mapped_column(String(128))
    document_title: Mapped[str | None] = mapped_column(String(255))

    revision: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(64))

    electronic_copy: Mapped[bool] = mapped_column(Boolean, default=True)
    hard_copy: Mapped[bool] = mapped_column(Boolean, default=False)

    transmittal: Mapped["Transmittal"] = relationship(back_populates="docs")


class Correspondence(Base):
    __tablename__ = "correspondences"
    __table_args__ = (
        Index("ix_correspondences_project_date", "project_code", "corr_date"),
        Index("ix_correspondences_reference_no", "reference_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="SET NULL"), index=True, nullable=True
    )
    issuing_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("issuing_entities.code", ondelete="RESTRICT"), index=True
    )
    category_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("correspondence_categories.code", ondelete="RESTRICT"), index=True
    )
    discipline_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="SET NULL"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(20), default="Letter", index=True)
    direction: Mapped[str] = mapped_column(String(10), default="IN", index=True)
    reference_no: Mapped[str | None] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(Text)
    sender: Mapped[str | None] = mapped_column(String(255))
    recipient: Mapped[str | None] = mapped_column(Text)
    corr_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="Open", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="Normal")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped[Optional["Project"]] = relationship(back_populates="correspondences")
    discipline: Mapped["Discipline"] = relationship(back_populates="correspondences")
    issuing_entity: Mapped["IssuingEntity"] = relationship(back_populates="correspondences")
    category: Mapped["CorrespondenceCategory"] = relationship(back_populates="correspondences")
    created_by: Mapped[Optional["User"]] = relationship(back_populates="correspondences_created")
    actions: Mapped[List["CorrespondenceAction"]] = relationship(
        back_populates="correspondence", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["CorrespondenceAttachment"]] = relationship(
        back_populates="correspondence", cascade="all, delete-orphan"
    )


class CorrespondenceAction(Base):
    __tablename__ = "correspondence_actions"
    __table_args__ = (
        Index("ix_corr_actions_correspondence", "correspondence_id"),
        Index("ix_corr_actions_status_due", "status", "due_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    correspondence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("correspondences.id", ondelete="CASCADE"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(32), default="comment", index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    from_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    to_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="Open", index=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    correspondence: Mapped["Correspondence"] = relationship(back_populates="actions")
    from_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[from_user_id],
        back_populates="correspondence_actions_from",
    )
    to_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[to_user_id],
        back_populates="correspondence_actions_to",
    )
    attachments: Mapped[List["CorrespondenceAttachment"]] = relationship(back_populates="action")


class CorrespondenceAttachment(Base):
    __tablename__ = "correspondence_attachments"
    __table_args__ = (
        Index("ix_corr_attachments_correspondence", "correspondence_id"),
        Index("ix_corr_attachments_uploaded_at", "uploaded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    correspondence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("correspondences.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("correspondence_actions.id", ondelete="SET NULL"), nullable=True
    )
    file_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(1024))
    file_kind: Mapped[str] = mapped_column(String(20), default="attachment")
    mime_type: Mapped[str | None] = mapped_column(String(128))
    detected_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local", nullable=False, index=True)
    gdrive_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mirror_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    correspondence: Mapped["Correspondence"] = relationship(back_populates="attachments")
    action: Mapped[Optional["CorrespondenceAction"]] = relationship(back_populates="attachments")
    uploaded_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[uploaded_by_id],
        back_populates="correspondence_attachments_uploaded",
    )


class WorkflowStatus(Base):
    __tablename__ = "workflow_statuses"
    __table_args__ = (
        UniqueConstraint("item_type", "code", name="uq_workflow_status_item_type_code"),
        Index("ix_workflow_status_item_type_sort", "item_type", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"
    __table_args__ = (
        UniqueConstraint(
            "item_type",
            "from_status_code",
            "to_status_code",
            name="uq_workflow_transition_item_from_to",
        ),
        Index("ix_workflow_transition_item_from", "item_type", "from_status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    from_status_code: Mapped[str] = mapped_column(String(64), nullable=False)
    to_status_code: Mapped[str] = mapped_column(String(64), nullable=False)
    requires_note: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TechSubtype(Base):
    __tablename__ = "tech_subtypes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ReviewResult(Base):
    __tablename__ = "review_results"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CommItem(Base):
    __tablename__ = "comm_items"
    __table_args__ = (
        UniqueConstraint("item_no", name="uq_comm_items_item_no"),
        Index(
            "ix_comm_items_project_disc_type_status_created",
            "project_code",
            "discipline_code",
            "item_type",
            "status_code",
            "created_at",
        ),
        Index("ix_comm_items_response_due_date", "response_due_date"),
        Index("ix_comm_items_notice_deadline", "notice_deadline"),
        Index("ix_comm_items_org_module", "organization_id", "item_type", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_no: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # RFI | NCR | TECH

    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    discipline_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    zone: Mapped[str | None] = mapped_column(String(128), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    response_due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    assignee_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recipient_org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contractor_org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    consultant_org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    contract_clause_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spec_clause_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wbs_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activity_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    potential_impact_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    potential_impact_cost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    potential_impact_quality: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    potential_impact_safety: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    impact_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_days_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    claim_notice_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notice_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    superseded_by_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped["Project"] = relationship("Project")
    discipline: Mapped["Discipline"] = relationship("Discipline")
    organization: Mapped["Organization | None"] = relationship("Organization", foreign_keys=[organization_id])
    recipient_org: Mapped["Organization | None"] = relationship(
        "Organization", foreign_keys=[recipient_org_id]
    )
    assignee_user: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_user_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])

    rfi_detail: Mapped["RfiDetail | None"] = relationship(
        back_populates="item", cascade="all, delete-orphan", uselist=False
    )
    ncr_detail: Mapped["NcrDetail | None"] = relationship(
        back_populates="item", cascade="all, delete-orphan", uselist=False
    )
    tech_detail: Mapped["TechDetail | None"] = relationship(
        back_populates="item", cascade="all, delete-orphan", uselist=False
    )
    status_logs: Mapped[List["ItemStatusLog"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    field_audits: Mapped[List["ItemFieldAudit"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    comments: Mapped[List["ItemComment"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["ItemAttachment"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    outgoing_relations: Mapped[List["ItemRelation"]] = relationship(
        "ItemRelation",
        foreign_keys="ItemRelation.from_item_id",
        back_populates="from_item",
        cascade="all, delete-orphan",
    )
    incoming_relations: Mapped[List["ItemRelation"]] = relationship(
        "ItemRelation",
        foreign_keys="ItemRelation.to_item_id",
        back_populates="to_item",
        cascade="all, delete-orphan",
    )


class RfiDetail(Base):
    __tablename__ = "rfi_details"

    comm_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), primary_key=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    drawing_refs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec_refs_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped["CommItem"] = relationship(back_populates="rfi_detail")


class NcrDetail(Base):
    __tablename__ = "ncr_details"

    comm_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str | None] = mapped_column(String(32), nullable=True)  # NCR | OBSERVATION | CAR
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)  # MINOR | MAJOR | CRITICAL
    nonconformance_text: Mapped[str] = mapped_column(Text, nullable=False)
    containment_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    rectification_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    rectification_due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    preventive_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    item: Mapped["CommItem"] = relationship(back_populates="ncr_detail")
    verified_by: Mapped["User | None"] = relationship("User", foreign_keys=[verified_by_id])


class TechDetail(Base):
    __tablename__ = "tech_details"

    comm_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), primary_key=True
    )
    tech_subtype_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("tech_subtypes.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    revision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transmittal_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submission_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_cycle_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_result_code: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("review_results.code", ondelete="SET NULL"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meeting_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    item: Mapped["CommItem"] = relationship(back_populates="tech_detail")
    tech_subtype: Mapped["TechSubtype"] = relationship("TechSubtype")
    review_result: Mapped["ReviewResult | None"] = relationship("ReviewResult")
    reviewed_by: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_id])


class ItemSequence(Base):
    __tablename__ = "item_sequences"
    __table_args__ = (
        UniqueConstraint(
            "project_code",
            "item_type",
            "discipline_code",
            name="uq_item_sequences_project_type_discipline",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(16), nullable=False)
    discipline_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="CASCADE"), nullable=False
    )
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ItemStatusLog(Base):
    __tablename__ = "item_status_logs"
    __table_args__ = (
        Index("ix_item_status_logs_item_changed_at", "item_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status_code: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped["CommItem"] = relationship(back_populates="status_logs")
    changed_by: Mapped["User | None"] = relationship("User", foreign_keys=[changed_by_id])


class ItemFieldAudit(Base):
    __tablename__ = "item_field_audits"
    __table_args__ = (
        Index("ix_item_field_audits_item_changed_at", "item_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    item: Mapped["CommItem"] = relationship(back_populates="field_audits")
    changed_by: Mapped["User | None"] = relationship("User", foreign_keys=[changed_by_id])


class ItemComment(Base):
    __tablename__ = "item_comments"
    __table_args__ = (
        Index("ix_item_comments_item_created_at", "item_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    comment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="comment")
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    item: Mapped["CommItem"] = relationship(back_populates="comments")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])


class ItemAttachment(Base):
    __tablename__ = "item_attachments"
    __table_args__ = (
        Index("ix_item_attachments_item_uploaded_at", "item_id", "uploaded_at"),
        Index("ix_item_attachments_item_scope_uploaded_at", "item_id", "scope_code", "uploaded_at"),
        Index("ix_item_attachments_item_slot_uploaded_at", "item_id", "slot_code", "uploaded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="attachment")
    scope_code: Mapped[str] = mapped_column(String(16), nullable=False, default="GENERAL", index=True)
    slot_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detected_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    gdrive_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mirror_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    item: Mapped["CommItem"] = relationship(back_populates="attachments")
    uploaded_by: Mapped["User | None"] = relationship("User", foreign_keys=[uploaded_by_id])


class ItemRelation(Base):
    __tablename__ = "item_relations"
    __table_args__ = (
        Index("ix_item_relations_from_item", "from_item_id"),
        Index("ix_item_relations_to_item", "to_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), nullable=False
    )
    to_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    from_item: Mapped["CommItem"] = relationship(
        "CommItem", foreign_keys=[from_item_id], back_populates="outgoing_relations"
    )
    to_item: Mapped["CommItem"] = relationship(
        "CommItem", foreign_keys=[to_item_id], back_populates="incoming_relations"
    )
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])


class SiteLogWorkflowStatus(Base):
    __tablename__ = "site_log_workflow_statuses"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogSequence(Base):
    __tablename__ = "site_log_sequences"
    __table_args__ = (
        UniqueConstraint(
            "project_code",
            "log_type",
            "log_date",
            name="uq_site_log_sequences_project_type_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False
    )
    log_type: Mapped[str] = mapped_column(String(32), nullable=False)
    log_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SiteLog(Base):
    __tablename__ = "site_logs"
    __table_args__ = (
        UniqueConstraint("log_no", name="uq_site_logs_log_no"),
        Index(
            "ix_site_logs_project_disc_type_status_date",
            "project_code",
            "discipline_code",
            "log_type",
            "status_code",
            "log_date",
        ),
        Index("ix_site_logs_status_date", "status_code", "log_date"),
        Index("ix_site_logs_org_status", "organization_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_no: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    log_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    discipline_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    log_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    weather: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submitted_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped["Project"] = relationship("Project")
    discipline: Mapped["Discipline"] = relationship("Discipline")
    organization: Mapped["Organization | None"] = relationship("Organization", foreign_keys=[organization_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    submitted_by: Mapped["User | None"] = relationship("User", foreign_keys=[submitted_by_id])
    verified_by: Mapped["User | None"] = relationship("User", foreign_keys=[verified_by_id])

    manpower_rows: Mapped[List["SiteLogManpowerRow"]] = relationship(
        back_populates="site_log", cascade="all, delete-orphan"
    )
    equipment_rows: Mapped[List["SiteLogEquipmentRow"]] = relationship(
        back_populates="site_log", cascade="all, delete-orphan"
    )
    activity_rows: Mapped[List["SiteLogActivityRow"]] = relationship(
        back_populates="site_log", cascade="all, delete-orphan"
    )
    status_logs: Mapped[List["SiteLogStatusLog"]] = relationship(
        back_populates="site_log", cascade="all, delete-orphan"
    )
    comments: Mapped[List["SiteLogComment"]] = relationship(
        back_populates="site_log", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["SiteLogAttachment"]] = relationship(
        back_populates="site_log", cascade="all, delete-orphan"
    )


class SiteLogManpowerRow(Base):
    __tablename__ = "site_log_manpower_rows"
    __table_args__ = (
        Index("ix_site_log_manpower_rows_site_role", "site_log_id", "role_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    site_log: Mapped["SiteLog"] = relationship(back_populates="manpower_rows")


class SiteLogEquipmentRow(Base):
    __tablename__ = "site_log_equipment_rows"
    __table_args__ = (
        Index("ix_site_log_equipment_rows_site_equipment", "site_log_id", "equipment_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    equipment_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    equipment_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    claimed_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verified_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    site_log: Mapped["SiteLog"] = relationship(back_populates="equipment_rows")


class SiteLogActivityRow(Base):
    __tablename__ = "site_log_activity_rows"
    __table_args__ = (
        Index("ix_site_log_activity_rows_site_activity", "site_log_id", "activity_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activity_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    external_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    site_log: Mapped["SiteLog"] = relationship(back_populates="activity_rows")


class SiteLogStatusLog(Base):
    __tablename__ = "site_log_status_logs"
    __table_args__ = (
        Index("ix_site_log_status_logs_site_changed_at", "site_log_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    site_log: Mapped["SiteLog"] = relationship(back_populates="status_logs")
    changed_by: Mapped["User | None"] = relationship("User", foreign_keys=[changed_by_id])


class SiteLogComment(Base):
    __tablename__ = "site_log_comments"
    __table_args__ = (
        Index("ix_site_log_comments_site_created_at", "site_log_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    comment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="comment")
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    site_log: Mapped["SiteLog"] = relationship(back_populates="comments")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])


class SiteLogAttachment(Base):
    __tablename__ = "site_log_attachments"
    __table_args__ = (
        Index("ix_site_log_attachments_site_uploaded_at", "site_log_id", "uploaded_at"),
        Index("ix_site_log_attachments_site_section_uploaded_at", "site_log_id", "section_code", "uploaded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_code: Mapped[str] = mapped_column(String(32), nullable=False, default="GENERAL", index=True)
    row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="attachment")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detected_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    site_log: Mapped["SiteLog"] = relationship(back_populates="attachments")
    uploaded_by: Mapped["User | None"] = relationship("User", foreign_keys=[uploaded_by_id])


class WorkboardItem(Base):
    __tablename__ = "workboard_items"
    __table_args__ = (
        Index("ix_workboard_module_tab", "module_key", "tab_key"),
        Index("ix_workboard_project_disc", "project_code", "discipline_code"),
        Index("ix_workboard_status_due", "status", "due_date"),
        Index("ix_workboard_org_module_tab", "organization_id", "module_key", "tab_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(32), index=True)  # contractor | consultant
    tab_key: Mapped[str] = mapped_column(String(32), index=True)

    project_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="SET NULL"), nullable=True
    )
    discipline_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="SET NULL"), nullable=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    due_date: Mapped[datetime | None] = mapped_column(DateTime)

    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped[Optional["Project"]] = relationship("Project")
    discipline: Mapped[Optional["Discipline"]] = relationship("Discipline")
    organization: Mapped[Optional["Organization"]] = relationship("Organization")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])


class StorageJob(Base):
    __tablename__ = "storage_jobs"
    __table_args__ = (
        Index("ix_storage_jobs_status_next_retry", "status", "next_retry_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class OpenProjectLink(Base):
    __tablename__ = "openproject_links"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "work_package_id", name="uq_openproject_entity_wp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    work_package_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    openproject_attachment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class OpenProjectImportRun(Base):
    __tablename__ = "openproject_import_runs"
    __table_args__ = (
        Index("ix_openproject_import_runs_status_created", "status_code", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_no: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    status_code: Mapped[str] = mapped_column(String(32), nullable=False, default="VALIDATED", index=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_parent_work_package_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    started_by: Mapped["User | None"] = relationship("User", foreign_keys=[started_by_id])
    rows: Mapped[List["OpenProjectImportRow"]] = relationship(
        "OpenProjectImportRow",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class OpenProjectImportRow(Base):
    __tablename__ = "openproject_import_rows"
    __table_args__ = (
        UniqueConstraint("run_id", "row_no", name="uq_openproject_import_rows_run_row"),
        Index("ix_openproject_import_rows_run_exec", "run_id", "execution_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("openproject_import_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    task_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    start_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    finish_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    predecessors_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_names_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    normalized_finish_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False, default="INVALID", index=True)
    execution_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", index=True)
    created_work_package_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    openproject_href: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    run: Mapped["OpenProjectImportRun"] = relationship("OpenProjectImportRun", back_populates="rows")


class LocalSyncManifest(Base):
    __tablename__ = "local_sync_manifest"
    __table_args__ = (
        UniqueConstraint("file_id", "policy_scope", name="uq_local_sync_manifest_file_scope"),
        Index("ix_local_sync_manifest_scope", "policy_scope", "is_pinned"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_modified_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    policy_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="global", index=True)


class SiteCacheProfile(Base):
    __tablename__ = "site_cache_profiles"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_cache_profiles_code"),
        Index("ix_site_cache_profiles_project", "project_code"),
        Index("ix_site_cache_profiles_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="SET NULL"), nullable=True
    )
    local_root_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    fallback_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="local_first")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_heartbeat_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    project: Mapped["Project | None"] = relationship("Project")
    cidrs: Mapped[List["SiteCacheProfileCIDR"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    pin_rules: Mapped[List["SiteCachePinRule"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    agent_tokens: Mapped[List["SiteCacheAgentToken"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class SiteCacheProfileCIDR(Base):
    __tablename__ = "site_cache_profile_cidrs"
    __table_args__ = (
        UniqueConstraint("profile_id", "cidr", name="uq_site_cache_profile_cidr"),
        Index("ix_site_cache_profile_cidrs_cidr", "cidr"),
        Index("ix_site_cache_profile_cidrs_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site_cache_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cidr: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    profile: Mapped["SiteCacheProfile"] = relationship(back_populates="cidrs")


class SiteCachePinRule(Base):
    __tablename__ = "site_cache_pin_rules"
    __table_args__ = (
        Index("ix_site_cache_pin_rules_profile", "profile_id", "is_active"),
        Index("ix_site_cache_pin_rules_project", "project_code"),
        Index("ix_site_cache_pin_rules_discipline", "discipline_code"),
        Index("ix_site_cache_pin_rules_package", "package_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site_cache_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="SET NULL"), nullable=True
    )
    discipline_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="SET NULL"), nullable=True
    )
    package_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status_codes: Mapped[str] = mapped_column(String(255), nullable=False, default="IFA,IFC")
    include_native: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    primary_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    latest_revision_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    profile: Mapped["SiteCacheProfile"] = relationship(back_populates="pin_rules")
    project: Mapped["Project | None"] = relationship("Project")
    discipline: Mapped["Discipline | None"] = relationship("Discipline")


class SiteCacheAgentToken(Base):
    __tablename__ = "site_cache_agent_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_site_cache_agent_tokens_hash"),
        Index("ix_site_cache_agent_tokens_profile_active", "profile_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("site_cache_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    profile: Mapped["SiteCacheProfile"] = relationship(back_populates="agent_tokens")
    created_by: Mapped["User | None"] = relationship("User")


class SettingsKV(Base):
    __tablename__ = "settings_kv"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SettingsAuditLog(Base):
    __tablename__ = "settings_audit_logs"
    __table_args__ = (
        Index("ix_settings_audit_logs_created_at", "created_at"),
        Index("ix_settings_audit_logs_action", "action"),
        Index("ix_settings_audit_logs_target_type", "target_type"),
        Index("ix_settings_audit_logs_actor", "actor_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_key: Mapped[str | None] = mapped_column(String(128))
    actor_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[str | None] = mapped_column(String(255))
    actor_name: Mapped[str | None] = mapped_column(String(255))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    actor: Mapped["User"] = relationship(back_populates="settings_audit_logs")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role", "permission", name="uq_role_permissions_role_perm"),
        Index("ix_role_permissions_role", "role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    permission: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RoleCategoryPermission(Base):
    __tablename__ = "role_category_permissions"
    __table_args__ = (
        UniqueConstraint("category", "role", "permission", name="uq_role_cat_perm"),
        Index("ix_role_cat_perm_category", "category"),
        Index("ix_role_cat_perm_role", "role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    permission: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RoleCategoryProjectScope(Base):
    __tablename__ = "role_category_project_scopes"
    __table_args__ = (
        UniqueConstraint("category", "role", "project_code", name="uq_role_cat_project_scope"),
        Index("ix_role_cat_project_scope_cat_role", "category", "role"),
        Index("ix_role_cat_project_scope_project", "project_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    project_code: Mapped[str] = mapped_column(String(50), ForeignKey("projects.code", ondelete="CASCADE"))


class RoleCategoryDisciplineScope(Base):
    __tablename__ = "role_category_discipline_scopes"
    __table_args__ = (
        UniqueConstraint("category", "role", "discipline_code", name="uq_role_cat_discipline_scope"),
        Index("ix_role_cat_discipline_scope_cat_role", "category", "role"),
        Index("ix_role_cat_discipline_scope_disc", "discipline_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    discipline_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="CASCADE")
    )


class RoleProjectScope(Base):
    __tablename__ = "role_project_scopes"
    __table_args__ = (
        UniqueConstraint("role", "project_code", name="uq_role_project_scope"),
        Index("ix_role_project_scope_role", "role"),
        Index("ix_role_project_scope_project", "project_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    project_code: Mapped[str] = mapped_column(String(50), ForeignKey("projects.code", ondelete="CASCADE"))


class RoleDisciplineScope(Base):
    __tablename__ = "role_discipline_scopes"
    __table_args__ = (
        UniqueConstraint("role", "discipline_code", name="uq_role_discipline_scope"),
        Index("ix_role_discipline_scope_role", "role"),
        Index("ix_role_discipline_scope_disc", "discipline_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    discipline_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="CASCADE")
    )


class UserProjectScope(Base):
    __tablename__ = "user_project_scopes"
    __table_args__ = (
        UniqueConstraint("user_id", "project_code", name="uq_user_project_scope"),
        Index("ix_user_project_scope_user", "user_id"),
        Index("ix_user_project_scope_project", "project_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    project_code: Mapped[str] = mapped_column(String(50), ForeignKey("projects.code", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(back_populates="project_scopes")


class UserDisciplineScope(Base):
    __tablename__ = "user_discipline_scopes"
    __table_args__ = (
        UniqueConstraint("user_id", "discipline_code", name="uq_user_discipline_scope"),
        Index("ix_user_discipline_scope_user", "user_id"),
        Index("ix_user_discipline_scope_disc", "discipline_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    discipline_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="CASCADE")
    )

    user: Mapped["User"] = relationship(back_populates="discipline_scopes")
