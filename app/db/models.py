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
    CheckConstraint,
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
    contracts: Mapped[List["OrganizationContract"]] = relationship(
        "OrganizationContract",
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="OrganizationContract.sort_order, OrganizationContract.id",
    )


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
    meeting_minutes_created: Mapped[List["MeetingMinute"]] = relationship(
        "MeetingMinute",
        foreign_keys="MeetingMinute.created_by_id",
        back_populates="created_by",
    )
    meeting_resolutions_created: Mapped[List["MeetingResolution"]] = relationship(
        "MeetingResolution",
        foreign_keys="MeetingResolution.created_by_id",
        back_populates="created_by",
    )
    meeting_resolution_responsibilities: Mapped[List["MeetingResolution"]] = relationship(
        "MeetingResolution",
        foreign_keys="MeetingResolution.responsible_user_id",
        back_populates="responsible_user",
    )
    meeting_minute_attachments_uploaded: Mapped[List["MeetingMinuteAttachment"]] = relationship(
        "MeetingMinuteAttachment",
        foreign_keys="MeetingMinuteAttachment.uploaded_by_id",
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
    meeting_minutes: Mapped[List["MeetingMinute"]] = relationship(
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


class OrganizationContract(Base):
    __tablename__ = "organization_contracts"
    __table_args__ = (
        Index("ix_org_contracts_org_sort", "organization_id", "sort_order"),
        Index("ix_org_contracts_block", "block_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_number: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    block_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("blocks.id", ondelete="SET NULL"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization: Mapped["Organization"] = relationship("Organization", back_populates="contracts")
    block: Mapped["Block | None"] = relationship("Block")

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


class CorrespondenceDepartment(Base):
    __tablename__ = "correspondence_departments"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name_e: Mapped[str] = mapped_column(String(255))
    name_p: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    correspondences: Mapped[List["Correspondence"]] = relationship(back_populates="department")

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

    # Audit / soft-delete
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    deleted_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="documents")
    phase: Mapped["Phase"] = relationship(back_populates="documents")
    discipline: Mapped["Discipline"] = relationship(back_populates="documents")
    level: Mapped["Level"] = relationship(back_populates="documents")
    mdr_category: Mapped["MdrCategory"] = relationship(back_populates="documents")
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[updated_by_id]
    )
    deleted_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[deleted_by_id]
    )

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
    comments: Mapped[List["DocumentComment"]] = relationship(
        "DocumentComment", back_populates="document", cascade="all, delete-orphan"
    )
    activities: Mapped[List["DocumentActivity"]] = relationship(
        "DocumentActivity", back_populates="document", cascade="all, delete-orphan"
    )
    outgoing_relations: Mapped[List["DocumentRelation"]] = relationship(
        "DocumentRelation",
        foreign_keys="DocumentRelation.source_document_id",
        back_populates="source_document",
        cascade="all, delete-orphan",
    )
    incoming_relations: Mapped[List["DocumentRelation"]] = relationship(
        "DocumentRelation",
        foreign_keys="DocumentRelation.target_document_id",
        back_populates="target_document",
        cascade="all, delete-orphan",
    )
    outgoing_external_relations: Mapped[List["DocumentExternalRelation"]] = relationship(
        "DocumentExternalRelation",
        foreign_keys="DocumentExternalRelation.source_document_id",
        back_populates="source_document",
        cascade="all, delete-orphan",
    )
    tag_assignments: Mapped[List["DocumentTagAssignment"]] = relationship(
        "DocumentTagAssignment", back_populates="document", cascade="all, delete-orphan"
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
    mirror_provider: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_remote_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mirror_remote_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
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
    public_shares: Mapped[List["ArchiveFilePublicShare"]] = relationship(
        "ArchiveFilePublicShare",
        back_populates="archive_file",
        cascade="all, delete-orphan",
        order_by="ArchiveFilePublicShare.created_at.desc(), ArchiveFilePublicShare.id.desc()",
    )


class ArchiveFilePublicShare(Base):
    __tablename__ = "archive_file_public_shares"
    __table_args__ = (
        Index("ix_archive_file_public_shares_file", "file_id"),
        Index("ix_archive_file_public_shares_provider_share", "provider", "provider_share_id"),
        Index("ix_archive_file_public_shares_active", "file_id", "revoked_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archive_files.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), default="nextcloud", nullable=False)
    provider_share_id: Mapped[str] = mapped_column(String(128), nullable=False)
    token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    share_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    resolved_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    permissions: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    password_set: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    archive_file: Mapped["ArchiveFile"] = relationship("ArchiveFile", back_populates="public_shares")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    revoked_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[revoked_by_id])

# ----------------------------------------------------------------
# 5a. Document Comments, Activity, Relations & Tags
# ----------------------------------------------------------------
class DocumentComment(Base):
    __tablename__ = "document_comments"
    __table_args__ = (
        Index("ix_doc_comments_document_id", "document_id"),
        Index("ix_doc_comments_parent_id", "parent_id"),
        Index("ix_doc_comments_created_at", "created_at"),
        Index("ix_doc_comments_document_revision_created", "document_id", "revision_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_comments.id", ondelete="CASCADE"), nullable=True
    )
    revision_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_revisions.id", ondelete="SET NULL"), nullable=True
    )
    author_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[str | None] = mapped_column(String(255))
    author_email: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    document: Mapped["MdrDocument"] = relationship("MdrDocument", back_populates="comments")
    revision: Mapped[Optional["DocumentRevision"]] = relationship("DocumentRevision")
    parent: Mapped[Optional["DocumentComment"]] = relationship(
        "DocumentComment", remote_side="DocumentComment.id", uselist=False
    )
    author: Mapped[Optional["User"]] = relationship("User")


class DocumentActivity(Base):
    __tablename__ = "document_activities"
    __table_args__ = (
        Index("ix_doc_activities_doc_created", "document_id", "created_at"),
        Index("ix_doc_activities_action", "action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_name: Mapped[str | None] = mapped_column(String(255))
    actor_email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped["MdrDocument"] = relationship("MdrDocument", back_populates="activities")
    actor: Mapped[Optional["User"]] = relationship("User")


class DocumentRelation(Base):
    __tablename__ = "document_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id", "target_document_id", "relation_type",
            name="uq_document_relation",
        ),
        CheckConstraint(
            "source_document_id != target_document_id",
            name="ck_document_relation_no_self",
        ),
        Index("ix_doc_relations_source", "source_document_id"),
        Index("ix_doc_relations_target", "target_document_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="CASCADE"), nullable=False
    )
    target_document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="related")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source_document: Mapped["MdrDocument"] = relationship(
        "MdrDocument", foreign_keys=[source_document_id], back_populates="outgoing_relations"
    )
    target_document: Mapped["MdrDocument"] = relationship(
        "MdrDocument", foreign_keys=[target_document_id], back_populates="incoming_relations"
    )
    created_by: Mapped[Optional["User"]] = relationship("User")


class DocumentExternalRelation(Base):
    __tablename__ = "document_external_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "target_entity_type",
            "target_entity_id",
            "relation_type",
            name="uq_document_external_relation",
        ),
        Index("ix_doc_ext_relations_source", "source_document_id"),
        Index("ix_doc_ext_relations_target", "target_entity_type", "target_entity_id"),
        Index("ix_doc_ext_relations_code", "target_entity_type", "target_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_code: Mapped[str] = mapped_column(String(120), nullable=False)
    target_title: Mapped[str | None] = mapped_column(Text)
    target_project_code: Mapped[str | None] = mapped_column(String(50))
    target_status: Mapped[str | None] = mapped_column(String(64))
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="related")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source_document: Mapped["MdrDocument"] = relationship(
        "MdrDocument", foreign_keys=[source_document_id], back_populates="outgoing_external_relations"
    )
    created_by: Mapped[Optional["User"]] = relationship("User")


class DocumentTag(Base):
    __tablename__ = "document_tags"
    __table_args__ = (
        UniqueConstraint("scope", "name", name="uq_document_tags_scope_name"),
        Index("ix_doc_tags_name", "name"),
        Index("ix_doc_tags_scope_name", "scope", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32), default="document", index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    assignments: Mapped[List["DocumentTagAssignment"]] = relationship(
        "DocumentTagAssignment", back_populates="tag", cascade="all, delete-orphan"
    )
    correspondence_assignments: Mapped[List["CorrespondenceTagAssignment"]] = relationship(
        "CorrespondenceTagAssignment", back_populates="tag", cascade="all, delete-orphan"
    )


class DocumentTagAssignment(Base):
    __tablename__ = "document_tag_assignments"
    __table_args__ = (
        UniqueConstraint("document_id", "tag_id", name="uq_doc_tag_assignment"),
        Index("ix_dta_document", "document_id"),
        Index("ix_dta_tag", "tag_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_tags.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document: Mapped["MdrDocument"] = relationship("MdrDocument", back_populates="tag_assignments")
    tag: Mapped["DocumentTag"] = relationship("DocumentTag", back_populates="assignments")
    assigned_by: Mapped[Optional["User"]] = relationship("User")


# ----------------------------------------------------------------
# 5b. Transmittals
# ----------------------------------------------------------------
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
    file_kind: Mapped[str] = mapped_column(String(20), default="pdf", nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    department_code: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("correspondence_departments.code", ondelete="SET NULL"), index=True
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
    cc_recipients: Mapped[str | None] = mapped_column(Text)
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
    department: Mapped[Optional["CorrespondenceDepartment"]] = relationship(back_populates="correspondences")
    created_by: Mapped[Optional["User"]] = relationship(back_populates="correspondences_created")
    actions: Mapped[List["CorrespondenceAction"]] = relationship(
        back_populates="correspondence", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["CorrespondenceAttachment"]] = relationship(
        back_populates="correspondence", cascade="all, delete-orphan"
    )
    external_relations: Mapped[List["CorrespondenceExternalRelation"]] = relationship(
        "CorrespondenceExternalRelation", back_populates="correspondence", cascade="all, delete-orphan"
    )
    tag_assignments: Mapped[List["CorrespondenceTagAssignment"]] = relationship(
        "CorrespondenceTagAssignment", back_populates="correspondence", cascade="all, delete-orphan"
    )


class CorrespondenceTagAssignment(Base):
    __tablename__ = "correspondence_tag_assignments"
    __table_args__ = (
        UniqueConstraint("correspondence_id", "tag_id", name="uq_corr_tag_assignment"),
        Index("ix_cta_correspondence", "correspondence_id"),
        Index("ix_cta_tag", "tag_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    correspondence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("correspondences.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_tags.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    correspondence: Mapped["Correspondence"] = relationship(
        "Correspondence", back_populates="tag_assignments"
    )
    tag: Mapped["DocumentTag"] = relationship(
        "DocumentTag", back_populates="correspondence_assignments"
    )
    assigned_by: Mapped[Optional["User"]] = relationship("User")


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
    mirror_provider: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_remote_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mirror_remote_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
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


class CorrespondenceExternalRelation(Base):
    __tablename__ = "correspondence_external_relations"
    __table_args__ = (
        UniqueConstraint(
            "correspondence_id",
            "target_entity_type",
            "target_entity_id",
            "relation_type",
            name="uq_correspondence_external_relation",
        ),
        Index("ix_corr_ext_relations_source", "correspondence_id"),
        Index("ix_corr_ext_relations_target", "target_entity_type", "target_entity_id"),
        Index("ix_corr_ext_relations_code", "target_entity_type", "target_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    correspondence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("correspondences.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_code: Mapped[str] = mapped_column(String(120), nullable=False)
    target_title: Mapped[str | None] = mapped_column(Text)
    target_project_code: Mapped[str | None] = mapped_column(String(50))
    target_status: Mapped[str | None] = mapped_column(String(64))
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="related")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    correspondence: Mapped["Correspondence"] = relationship(
        "Correspondence", back_populates="external_relations"
    )
    created_by: Mapped[Optional["User"]] = relationship("User")


class MeetingMinute(Base):
    __tablename__ = "meeting_minutes"
    __table_args__ = (
        Index("ix_meeting_minutes_project_date", "project_code", "meeting_date"),
        Index("ix_meeting_minutes_meeting_no", "meeting_no"),
        Index("ix_meeting_minutes_status", "status"),
        Index("ix_meeting_minutes_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_no: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    project_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="SET NULL"), index=True, nullable=True
    )
    meeting_type: Mapped[str] = mapped_column(String(64), default="General", index=True)
    meeting_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chairperson: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secretary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    participants: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Open", index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[Optional["Project"]] = relationship(back_populates="meeting_minutes")
    created_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by_id],
        back_populates="meeting_minutes_created",
    )
    resolutions: Mapped[List["MeetingResolution"]] = relationship(
        back_populates="meeting_minute", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["MeetingMinuteAttachment"]] = relationship(
        back_populates="meeting_minute", cascade="all, delete-orphan"
    )
    external_relations: Mapped[List["MeetingMinuteExternalRelation"]] = relationship(
        "MeetingMinuteExternalRelation", back_populates="meeting_minute", cascade="all, delete-orphan"
    )


class MeetingMinuteSequence(Base):
    __tablename__ = "meeting_minute_sequences"
    __table_args__ = (
        UniqueConstraint(
            "project_code",
            "period",
            name="uq_meeting_minute_sequences_project_period",
        ),
        Index("ix_meeting_minute_sequences_project_period", "project_code", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(String(50), nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class MeetingResolution(Base):
    __tablename__ = "meeting_resolutions"
    __table_args__ = (
        Index("ix_meeting_resolutions_minute", "meeting_minute_id"),
        Index("ix_meeting_resolutions_status_due", "status", "due_date"),
        Index("ix_meeting_resolutions_responsible_user", "responsible_user_id"),
        Index("ix_meeting_resolutions_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_minute_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meeting_minutes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resolution_no: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    responsible_org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    responsible_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Open", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="Normal", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    meeting_minute: Mapped["MeetingMinute"] = relationship(back_populates="resolutions")
    responsible_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[responsible_user_id],
        back_populates="meeting_resolution_responsibilities",
    )
    responsible_org: Mapped[Optional["Organization"]] = relationship("Organization")
    created_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by_id],
        back_populates="meeting_resolutions_created",
    )
    attachments: Mapped[List["MeetingMinuteAttachment"]] = relationship(
        back_populates="resolution"
    )


class MeetingMinuteAttachment(Base):
    __tablename__ = "meeting_minute_attachments"
    __table_args__ = (
        Index("ix_meeting_minute_attachments_minute", "meeting_minute_id"),
        Index("ix_meeting_minute_attachments_resolution", "resolution_id"),
        Index("ix_meeting_minute_attachments_uploaded_at", "uploaded_at"),
        Index("ix_meeting_minute_attachments_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_minute_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meeting_minutes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resolution_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("meeting_resolutions.id", ondelete="SET NULL"), nullable=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_kind: Mapped[str] = mapped_column(String(20), default="attachment", nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detected_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(32), default="local", nullable=False, index=True)
    mirror_provider: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_remote_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mirror_remote_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mirror_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meeting_minute: Mapped["MeetingMinute"] = relationship(back_populates="attachments")
    resolution: Mapped[Optional["MeetingResolution"]] = relationship(back_populates="attachments")
    uploaded_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[uploaded_by_id],
        back_populates="meeting_minute_attachments_uploaded",
    )


class MeetingMinuteExternalRelation(Base):
    __tablename__ = "meeting_minute_external_relations"
    __table_args__ = (
        UniqueConstraint(
            "meeting_minute_id",
            "target_entity_type",
            "target_entity_id",
            "relation_type",
            name="uq_meeting_minute_external_relation",
        ),
        Index("ix_mm_ext_relations_source", "meeting_minute_id"),
        Index("ix_mm_ext_relations_target", "target_entity_type", "target_entity_id"),
        Index("ix_mm_ext_relations_code", "target_entity_type", "target_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_minute_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meeting_minutes.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_code: Mapped[str] = mapped_column(String(120), nullable=False)
    target_title: Mapped[str | None] = mapped_column(Text)
    target_project_code: Mapped[str | None] = mapped_column(String(50))
    target_status: Mapped[str | None] = mapped_column(String(64))
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="related")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meeting_minute: Mapped["MeetingMinute"] = relationship(
        "MeetingMinute", back_populates="external_relations"
    )
    created_by: Mapped[Optional["User"]] = relationship("User")


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
    mirror_provider: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_remote_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mirror_remote_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
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


class WorkInstruction(Base):
    __tablename__ = "work_instructions"
    __table_args__ = (
        UniqueConstraint("instruction_no", name="uq_work_instructions_instruction_no"),
        UniqueConstraint("legacy_comm_item_id", name="uq_work_instructions_legacy_comm_item"),
        Index(
            "ix_work_instructions_project_disc_status_created",
            "project_code",
            "discipline_code",
            "status_code",
            "created_at",
        ),
        Index("ix_work_instructions_response_due_date", "response_due_date"),
        Index("ix_work_instructions_org_status", "organization_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legacy_comm_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    instruction_no: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    legacy_subtype: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_legacy_readonly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    status_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="NORMAL")
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

    potential_impact_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    potential_impact_cost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    potential_impact_quality: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    potential_impact_safety: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    impact_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_days_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    claim_notice_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notice_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    legacy_comm_item: Mapped["CommItem | None"] = relationship("CommItem")
    project: Mapped["Project"] = relationship("Project")
    discipline: Mapped["Discipline"] = relationship("Discipline")
    organization: Mapped["Organization | None"] = relationship("Organization", foreign_keys=[organization_id])
    recipient_org: Mapped["Organization | None"] = relationship("Organization", foreign_keys=[recipient_org_id])
    assignee_user: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_user_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    reviewed_by: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_id])
    review_result: Mapped["ReviewResult | None"] = relationship("ReviewResult")
    status_logs: Mapped[List["WorkInstructionStatusLog"]] = relationship(
        back_populates="instruction", cascade="all, delete-orphan"
    )
    field_audits: Mapped[List["WorkInstructionFieldAudit"]] = relationship(
        back_populates="instruction", cascade="all, delete-orphan"
    )
    comments: Mapped[List["WorkInstructionComment"]] = relationship(
        back_populates="instruction", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["WorkInstructionAttachment"]] = relationship(
        back_populates="instruction", cascade="all, delete-orphan"
    )
    outgoing_relations: Mapped[List["WorkInstructionRelation"]] = relationship(
        "WorkInstructionRelation",
        foreign_keys="WorkInstructionRelation.from_instruction_id",
        back_populates="from_instruction",
        cascade="all, delete-orphan",
    )
    incoming_relations: Mapped[List["WorkInstructionRelation"]] = relationship(
        "WorkInstructionRelation",
        foreign_keys="WorkInstructionRelation.to_instruction_id",
        back_populates="to_instruction",
        cascade="all, delete-orphan",
    )


class WorkInstructionSequence(Base):
    __tablename__ = "work_instruction_sequences"
    __table_args__ = (
        UniqueConstraint(
            "project_code",
            "discipline_code",
            name="uq_work_instruction_sequences_project_discipline",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False
    )
    discipline_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="CASCADE"), nullable=False
    )
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class WorkInstructionStatusLog(Base):
    __tablename__ = "work_instruction_status_logs"
    __table_args__ = (
        Index("ix_work_instruction_status_logs_instruction_changed_at", "instruction_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instruction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("work_instructions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status_code: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    instruction: Mapped["WorkInstruction"] = relationship(back_populates="status_logs")
    changed_by: Mapped["User | None"] = relationship("User", foreign_keys=[changed_by_id])


class WorkInstructionFieldAudit(Base):
    __tablename__ = "work_instruction_field_audits"
    __table_args__ = (
        Index("ix_work_instruction_field_audits_instruction_changed_at", "instruction_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instruction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("work_instructions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    instruction: Mapped["WorkInstruction"] = relationship(back_populates="field_audits")
    changed_by: Mapped["User | None"] = relationship("User", foreign_keys=[changed_by_id])


class WorkInstructionComment(Base):
    __tablename__ = "work_instruction_comments"
    __table_args__ = (
        Index("ix_work_instruction_comments_instruction_created_at", "instruction_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instruction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("work_instructions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    comment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="comment")
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    instruction: Mapped["WorkInstruction"] = relationship(back_populates="comments")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])


class WorkInstructionAttachment(Base):
    __tablename__ = "work_instruction_attachments"
    __table_args__ = (
        Index("ix_work_instruction_attachments_instruction_uploaded_at", "instruction_id", "uploaded_at"),
        Index(
            "ix_work_instruction_attachments_instruction_scope_uploaded_at",
            "instruction_id",
            "scope_code",
            "uploaded_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instruction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("work_instructions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    legacy_item_attachment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("item_attachments.id", ondelete="SET NULL"), nullable=True, index=True
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
    mirror_provider: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_remote_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mirror_remote_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mirror_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    mirror_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    instruction: Mapped["WorkInstruction"] = relationship(back_populates="attachments")
    uploaded_by: Mapped["User | None"] = relationship("User", foreign_keys=[uploaded_by_id])


class WorkInstructionRelation(Base):
    __tablename__ = "work_instruction_relations"
    __table_args__ = (
        Index("ix_work_instruction_relations_from_instruction", "from_instruction_id"),
        Index("ix_work_instruction_relations_to_instruction", "to_instruction_id"),
        Index("ix_work_instruction_relations_from_comm_item", "from_comm_item_id"),
        Index("ix_work_instruction_relations_to_comm_item", "to_comm_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_instruction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("work_instructions.id", ondelete="CASCADE"), nullable=True
    )
    from_comm_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), nullable=True
    )
    to_instruction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("work_instructions.id", ondelete="CASCADE"), nullable=True
    )
    to_comm_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("comm_items.id", ondelete="CASCADE"), nullable=True
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    from_instruction: Mapped["WorkInstruction | None"] = relationship(
        "WorkInstruction",
        foreign_keys=[from_instruction_id],
        back_populates="outgoing_relations",
    )
    to_instruction: Mapped["WorkInstruction | None"] = relationship(
        "WorkInstruction",
        foreign_keys=[to_instruction_id],
        back_populates="incoming_relations",
    )
    from_comm_item: Mapped["CommItem | None"] = relationship("CommItem", foreign_keys=[from_comm_item_id])
    to_comm_item: Mapped["CommItem | None"] = relationship("CommItem", foreign_keys=[to_comm_item_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])


class SiteLogWorkflowStatus(Base):
    __tablename__ = "site_log_workflow_statuses"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogRoleCatalog(Base):
    __tablename__ = "site_log_role_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_role_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogWorkSectionCatalog(Base):
    __tablename__ = "site_log_work_section_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_work_section_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogEquipmentCatalog(Base):
    __tablename__ = "site_log_equipment_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_equipment_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogMaterialCatalog(Base):
    __tablename__ = "site_log_material_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_material_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogEquipmentStatusCatalog(Base):
    __tablename__ = "site_log_equipment_status_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_equipment_status_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogAttachmentTypeCatalog(Base):
    __tablename__ = "site_log_attachment_type_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_attachment_type_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogShiftCatalog(Base):
    __tablename__ = "site_log_shift_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_shift_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogWeatherCatalog(Base):
    __tablename__ = "site_log_weather_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_weather_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogIssueTypeCatalog(Base):
    __tablename__ = "site_log_issue_type_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_issue_type_catalog_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SiteLogActivityCatalog(Base):
    __tablename__ = "site_log_activity_catalog"
    __table_args__ = (
        UniqueConstraint(
            "project_code",
            "organization_id",
            "organization_contract_id",
            "activity_code",
            name="uq_site_log_activity_catalog_scope_code",
        ),
        Index("ix_site_log_activity_catalog_project_sort", "project_code", "sort_order"),
        Index("ix_site_log_activity_catalog_org", "organization_id"),
        Index("ix_site_log_activity_catalog_contract", "organization_contract_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organization_contract_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("organization_contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    activity_title: Mapped[str] = mapped_column(String(255), nullable=False)
    activity_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    activity_type_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wbs_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    project: Mapped["Project"] = relationship("Project")
    organization: Mapped["Organization | None"] = relationship("Organization")
    organization_contract: Mapped["OrganizationContract | None"] = relationship("OrganizationContract")
    pms_mapping: Mapped["SiteLogActivityPmsMapping | None"] = relationship(
        "SiteLogActivityPmsMapping",
        back_populates="activity_catalog",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SiteLogPmsTemplate(Base):
    __tablename__ = "site_log_pms_templates"
    __table_args__ = (
        UniqueConstraint("code", name="uq_site_log_pms_templates_code"),
        Index("ix_site_log_pms_templates_active_sort", "is_active", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    steps: Mapped[List["SiteLogPmsTemplateStep"]] = relationship(
        "SiteLogPmsTemplateStep",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="SiteLogPmsTemplateStep.sort_order, SiteLogPmsTemplateStep.id",
    )
    activity_mappings: Mapped[List["SiteLogActivityPmsMapping"]] = relationship(
        "SiteLogActivityPmsMapping",
        back_populates="template",
    )


class SiteLogPmsTemplateStep(Base):
    __tablename__ = "site_log_pms_template_steps"
    __table_args__ = (
        UniqueConstraint("template_id", "step_code", name="uq_site_log_pms_template_steps_template_code"),
        Index("ix_site_log_pms_template_steps_template_sort", "template_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_log_pms_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_code: Mapped[str] = mapped_column(String(64), nullable=False)
    step_title: Mapped[str] = mapped_column(String(255), nullable=False)
    weight_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    template: Mapped["SiteLogPmsTemplate"] = relationship("SiteLogPmsTemplate", back_populates="steps")


class SiteLogActivityPmsMapping(Base):
    __tablename__ = "site_log_activity_pms_mappings"
    __table_args__ = (
        UniqueConstraint("activity_catalog_id", name="uq_site_log_activity_pms_mappings_activity"),
        Index("ix_site_log_activity_pms_mappings_template", "template_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_catalog_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_log_activity_catalog.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_log_pms_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    template_title: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    activity_catalog: Mapped["SiteLogActivityCatalog"] = relationship(
        "SiteLogActivityCatalog", back_populates="pms_mapping"
    )
    template: Mapped["SiteLogPmsTemplate"] = relationship("SiteLogPmsTemplate", back_populates="activity_mappings")
    steps: Mapped[List["SiteLogActivityPmsStep"]] = relationship(
        "SiteLogActivityPmsStep",
        back_populates="mapping",
        cascade="all, delete-orphan",
        order_by="SiteLogActivityPmsStep.sort_order, SiteLogActivityPmsStep.id",
    )


class SiteLogActivityPmsStep(Base):
    __tablename__ = "site_log_activity_pms_steps"
    __table_args__ = (
        UniqueConstraint("mapping_id", "step_code", name="uq_site_log_activity_pms_steps_mapping_code"),
        Index("ix_site_log_activity_pms_steps_mapping_sort", "mapping_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mapping_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_log_activity_pms_mappings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_template_step_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("site_log_pms_template_steps.id", ondelete="SET NULL"), nullable=True
    )
    step_code: Mapped[str] = mapped_column(String(64), nullable=False)
    step_title: Mapped[str] = mapped_column(String(255), nullable=False)
    weight_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    mapping: Mapped["SiteLogActivityPmsMapping"] = relationship("SiteLogActivityPmsMapping", back_populates="steps")


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
    discipline_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="RESTRICT"), nullable=True, index=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organization_contract_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("organization_contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    log_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    work_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    shift: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contract_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contract_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contract_block: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qc_test_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qc_inspection_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qc_open_ncr_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qc_open_punch_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qc_summary_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    qc_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    weather: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_work_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_plan_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    discipline: Mapped["Discipline | None"] = relationship("Discipline")
    organization: Mapped["Organization | None"] = relationship("Organization", foreign_keys=[organization_id])
    organization_contract: Mapped["OrganizationContract | None"] = relationship(
        "OrganizationContract",
        foreign_keys=[organization_contract_id],
    )
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
    material_rows: Mapped[List["SiteLogMaterialRow"]] = relationship(
        back_populates="site_log", cascade="all, delete-orphan"
    )
    issue_rows: Mapped[List["SiteLogIssueRow"]] = relationship(
        back_populates="site_log", cascade="all, delete-orphan"
    )
    attachment_rows: Mapped[List["SiteLogAttachmentRow"]] = relationship(
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
    work_section_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    work_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    claimed_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verified_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    site_log: Mapped["SiteLog"] = relationship(back_populates="equipment_rows")


class SiteLogActivityRow(Base):
    __tablename__ = "site_log_activity_rows"
    __table_args__ = (
        Index("ix_site_log_activity_rows_site_activity", "site_log_id", "activity_code"),
        Index("ix_site_log_activity_rows_measurement_qc", "measurement_status", "qc_status"),
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
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    personnel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pms_mapping_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("site_log_activity_pms_mappings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pms_template_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pms_template_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pms_template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pms_step_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pms_step_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pms_step_weight_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    today_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    cumulative_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    supervisor_today_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    supervisor_cumulative_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    supervisor_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qc_status: Mapped[str | None] = mapped_column(String(32), nullable=True, default="PENDING")
    qc_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    qc_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    qc_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurement_status: Mapped[str | None] = mapped_column(String(32), nullable=True, default="DRAFT")
    measurement_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    measurement_updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activity_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    site_log: Mapped["SiteLog"] = relationship(back_populates="activity_rows")
    pms_mapping: Mapped["SiteLogActivityPmsMapping | None"] = relationship("SiteLogActivityPmsMapping")
    qc_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[qc_by_user_id])
    measurement_updated_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[measurement_updated_by_user_id]
    )


class SiteLogMaterialRow(Base):
    __tablename__ = "site_log_material_rows"
    __table_args__ = (
        Index("ix_site_log_material_rows_site_code", "site_log_id", "material_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consumption_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consumption_floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    incoming_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    consumed_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    cumulative_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    site_log: Mapped["SiteLog"] = relationship(back_populates="material_rows")


class SiteLogIssueRow(Base):
    __tablename__ = "site_log_issue_rows"
    __table_args__ = (
        Index("ix_site_log_issue_rows_site_type", "site_log_id", "issue_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issue_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsible_party: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    site_log: Mapped["SiteLog"] = relationship(back_populates="issue_rows")


class SiteLogAttachmentRow(Base):
    __tablename__ = "site_log_attachment_rows"
    __table_args__ = (
        Index("ix_site_log_attachment_rows_site_type", "site_log_id", "attachment_type"),
        Index("ix_site_log_attachment_rows_linked_attachment", "linked_attachment_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attachment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_attachment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("site_log_attachments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    site_log: Mapped["SiteLog"] = relationship(back_populates="attachment_rows")
    linked_attachment: Mapped["SiteLogAttachment | None"] = relationship(
        "SiteLogAttachment",
        back_populates="report_rows",
        foreign_keys=[linked_attachment_id],
    )


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
    report_rows: Mapped[List["SiteLogAttachmentRow"]] = relationship(
        "SiteLogAttachmentRow",
        back_populates="linked_attachment",
        foreign_keys="SiteLogAttachmentRow.linked_attachment_id",
    )


class BimPublishRun(Base):
    __tablename__ = "bim_publish_runs"
    __table_args__ = (
        UniqueConstraint("run_uid", name="uq_bim_publish_runs_run_uid"),
        Index("ix_bim_publish_runs_project_status", "project_code", "status"),
        Index("ix_bim_publish_runs_ingestion_mode", "ingestion_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_uid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    run_client_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False
    )
    model_guid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revit_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    plugin_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ingestion_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="legacy_direct", index=True)
    staging_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    approved_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    plugin_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    items: Mapped[List["BimPublishItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class BimPublishItem(Base):
    __tablename__ = "bim_publish_items"
    __table_args__ = (
        UniqueConstraint("idempotency_hash", name="uq_bim_publish_items_idempotency_hash"),
        UniqueConstraint("run_id", "item_index", name="uq_bim_publish_items_run_item_index"),
        Index("ix_bim_publish_items_run_state", "run_id", "state"),
        Index(
            "ix_bim_publish_items_project_sheet_revision",
            "project_code",
            "sheet_unique_id",
            "requested_revision",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bim_publish_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    project_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sheet_unique_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sheet_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doc_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    requested_revision: Mapped[str] = mapped_column(String(32), nullable=False)
    status_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    include_native: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotency_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    staging_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    staging_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    validation_state: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    validation_errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="SET NULL"), nullable=True
    )
    applied_revision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pdf_file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_files.id", ondelete="SET NULL"), nullable=True
    )
    native_file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_files.id", ondelete="SET NULL"), nullable=True
    )
    archive_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mdr_documents.id", ondelete="SET NULL"), nullable=True
    )
    archive_file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_files.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["BimPublishRun"] = relationship(back_populates="items")


class BimScheduleRun(Base):
    __tablename__ = "bim_schedule_runs"
    __table_args__ = (
        UniqueConstraint("run_uid", name="uq_bim_schedule_runs_run_uid"),
        Index("ix_bim_schedule_runs_project_profile_status", "project_code", "profile_code", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_uid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_guid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    view_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staging", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    rows: Mapped[List["BimScheduleRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class BimScheduleRow(Base):
    __tablename__ = "bim_schedule_rows"
    __table_args__ = (
        UniqueConstraint("run_id", "row_no", name="uq_bim_schedule_rows_run_row_no"),
        Index("ix_bim_schedule_rows_run_state", "run_id", "row_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bim_schedule_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    row_state: Mapped[str] = mapped_column(String(16), nullable=False, default="VALID")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    element_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    equipment_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    run: Mapped["BimScheduleRun"] = relationship(back_populates="rows")


class BimMtoItem(Base):
    __tablename__ = "bim_mto_items"
    __table_args__ = (
        Index(
            "ix_bim_mto_items_project_model_element",
            "project_code",
            "model_guid",
            "element_key",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False
    )
    model_guid: Mapped[str] = mapped_column(String(64), nullable=False)
    element_key: Mapped[str] = mapped_column(String(255), nullable=False)
    values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bim_schedule_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class BimEquipmentItem(Base):
    __tablename__ = "bim_equipment_items"
    __table_args__ = (
        Index(
            "ix_bim_equipment_items_project_model_equipment",
            "project_code",
            "model_guid",
            "equipment_key",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False
    )
    model_guid: Mapped[str] = mapped_column(String(64), nullable=False)
    equipment_key: Mapped[str] = mapped_column(String(255), nullable=False)
    values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bim_schedule_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class BimRevitSyncRun(Base):
    __tablename__ = "bim_revit_sync_runs"
    __table_args__ = (
        UniqueConstraint("run_uid", name="uq_bim_revit_sync_runs_run_uid"),
        Index("ix_bim_revit_sync_runs_project_model_status", "project_code", "client_model_guid", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_uid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False, index=True
    )
    client_model_guid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    requested_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[List["BimRevitSyncItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class BimRevitSyncItem(Base):
    __tablename__ = "bim_revit_sync_items"
    __table_args__ = (
        UniqueConstraint("run_id", "sync_key", name="uq_bim_revit_sync_items_run_sync_key"),
        Index("ix_bim_revit_sync_items_run_state", "run_id", "state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bim_revit_sync_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sync_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_log_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    section_code: Mapped[str] = mapped_column(String(32), nullable=False)
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False, default="upsert")
    row_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["BimRevitSyncRun"] = relationship(back_populates="items")


class BimRevitClientState(Base):
    __tablename__ = "bim_revit_client_state"
    __table_args__ = (
        UniqueConstraint(
            "project_code",
            "client_model_guid",
            "user_id",
            name="uq_bim_revit_client_state_project_model_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="CASCADE"), nullable=False, index=True
    )
    client_model_guid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_cursor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_manifest_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_pull_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


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


class PowerBiApiToken(Base):
    __tablename__ = "power_bi_api_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_power_bi_api_tokens_hash"),
        Index("ix_power_bi_api_tokens_active", "is_active", "revoked_at"),
        Index("ix_power_bi_api_tokens_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_hint: Mapped[str | None] = mapped_column(String(48), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default='["site_logs:report_read"]')
    allowed_project_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_report_sections: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_ip_ranges: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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


class NativeEdmsSyncEvent(Base):
    __tablename__ = "native_edms_sync_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_native_edms_sync_events_event_id"),
        Index("ix_native_edms_sync_events_entity_state", "entity", "delivery_state"),
        Index("ix_native_edms_sync_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NativeEdmsCutoverSnapshot(Base):
    __tablename__ = "native_edms_cutover_snapshots"
    __table_args__ = (
        Index("ix_native_edms_cutover_snapshots_snapshot_type", "snapshot_type"),
        Index("ix_native_edms_cutover_snapshots_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_name: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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


class PermitQcTemplate(Base):
    __tablename__ = "permit_qc_templates"
    __table_args__ = (
        Index("ix_permit_qc_templates_active", "is_active"),
        Index("ix_permit_qc_templates_project_discipline", "project_code", "discipline_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_code: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="SET NULL"), nullable=True, index=True
    )
    discipline_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped["Project | None"] = relationship("Project")
    discipline: Mapped["Discipline | None"] = relationship("Discipline")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_id])
    stations: Mapped[List["PermitQcTemplateStation"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )
    permits: Mapped[List["PermitQcPermit"]] = relationship(back_populates="template")


class PermitQcTemplateStation(Base):
    __tablename__ = "permit_qc_template_stations"
    __table_args__ = (
        UniqueConstraint("template_id", "station_key", name="uq_permit_qc_template_station_key"),
        Index("ix_permit_qc_template_stations_template_sort", "template_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permit_qc_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_key: Mapped[str] = mapped_column(String(64), nullable=False)
    station_label: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    template: Mapped["PermitQcTemplate"] = relationship(back_populates="stations")
    organization: Mapped["Organization | None"] = relationship("Organization")
    checks: Mapped[List["PermitQcTemplateCheck"]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )


class PermitQcTemplateCheck(Base):
    __tablename__ = "permit_qc_template_checks"
    __table_args__ = (
        UniqueConstraint("station_id", "check_code", name="uq_permit_qc_template_check_code"),
        Index("ix_permit_qc_template_checks_station_sort", "station_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permit_qc_template_stations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_code: Mapped[str] = mapped_column(String(64), nullable=False)
    check_label: Mapped[str] = mapped_column(String(255), nullable=False)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False, default="BOOLEAN")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    station: Mapped["PermitQcTemplateStation"] = relationship(back_populates="checks")


class PermitQcPermit(Base):
    __tablename__ = "permit_qc_permits"
    __table_args__ = (
        UniqueConstraint("project_code", "permit_no", name="uq_permit_qc_permit_project_no"),
        Index("ix_permit_qc_permits_status", "status_code"),
        Index("ix_permit_qc_permits_permit_date", "permit_date"),
        Index("ix_permit_qc_permits_project_disc", "project_code", "discipline_code"),
        Index("ix_permit_qc_permits_org_status", "organization_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    permit_no: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    permit_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    wall_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    floor_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    elevation_start: Mapped[str | None] = mapped_column(String(64), nullable=True)
    elevation_end: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_code: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")

    project_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    discipline_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("disciplines.code", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("permit_qc_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contractor_org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    consultant_org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped["Project"] = relationship("Project")
    discipline: Mapped["Discipline"] = relationship("Discipline")
    template: Mapped["PermitQcTemplate | None"] = relationship(back_populates="permits")
    organization: Mapped["Organization | None"] = relationship("Organization", foreign_keys=[organization_id])
    contractor_org: Mapped["Organization | None"] = relationship(
        "Organization", foreign_keys=[contractor_org_id]
    )
    consultant_org: Mapped["Organization | None"] = relationship(
        "Organization", foreign_keys=[consultant_org_id]
    )
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_id])
    stations: Mapped[List["PermitQcPermitStation"]] = relationship(
        back_populates="permit", cascade="all, delete-orphan"
    )
    attachments: Mapped[List["PermitQcPermitAttachment"]] = relationship(
        back_populates="permit", cascade="all, delete-orphan"
    )
    events: Mapped[List["PermitQcPermitEvent"]] = relationship(
        back_populates="permit", cascade="all, delete-orphan"
    )


class PermitQcPermitStation(Base):
    __tablename__ = "permit_qc_permit_stations"
    __table_args__ = (
        Index("ix_permit_qc_permit_stations_permit_sort", "permit_id", "sort_order"),
        Index("ix_permit_qc_permit_stations_status", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permit_qc_permits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_station_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("permit_qc_template_stations.id", ondelete="SET NULL"), nullable=True
    )
    station_key: Mapped[str] = mapped_column(String(64), nullable=False)
    station_label: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_code: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    reviewed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    permit: Mapped["PermitQcPermit"] = relationship(back_populates="stations")
    template_station: Mapped["PermitQcTemplateStation | None"] = relationship("PermitQcTemplateStation")
    organization: Mapped["Organization | None"] = relationship("Organization")
    reviewed_by: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_id])
    checks: Mapped[List["PermitQcPermitCheck"]] = relationship(
        back_populates="permit_station", cascade="all, delete-orphan"
    )


class PermitQcPermitCheck(Base):
    __tablename__ = "permit_qc_permit_checks"
    __table_args__ = (
        Index("ix_permit_qc_permit_checks_station_sort", "permit_station_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    permit_station_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permit_qc_permit_stations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_check_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("permit_qc_template_checks.id", ondelete="SET NULL"), nullable=True
    )
    check_code: Mapped[str] = mapped_column(String(64), nullable=False)
    check_label: Mapped[str] = mapped_column(String(255), nullable=False)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False, default="BOOLEAN")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    permit_station: Mapped["PermitQcPermitStation"] = relationship(back_populates="checks")
    template_check: Mapped["PermitQcTemplateCheck | None"] = relationship("PermitQcTemplateCheck")


class PermitQcPermitAttachment(Base):
    __tablename__ = "permit_qc_permit_attachments"
    __table_args__ = (
        Index("ix_permit_qc_permit_attachments_permit", "permit_id"),
        Index("ix_permit_qc_permit_attachments_uploaded_at", "uploaded_at"),
        Index("ix_permit_qc_permit_attachments_sha256", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permit_qc_permits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="attachment")
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detected_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    uploaded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    permit: Mapped["PermitQcPermit"] = relationship(back_populates="attachments")
    uploaded_by: Mapped["User | None"] = relationship("User", foreign_keys=[uploaded_by_id])


class PermitQcPermitEvent(Base):
    __tablename__ = "permit_qc_permit_events"
    __table_args__ = (
        Index("ix_permit_qc_permit_events_permit_created", "permit_id", "created_at"),
        Index("ix_permit_qc_permit_events_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    permit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permit_qc_permits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("permit_qc_permit_stations.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    permit: Mapped["PermitQcPermit"] = relationship(back_populates="events")
    station: Mapped["PermitQcPermitStation | None"] = relationship("PermitQcPermitStation")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
