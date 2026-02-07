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
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))

    role: Mapped[str] = mapped_column(String(50), default="user")
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
    size_bytes: Mapped[int | None] = mapped_column(Integer)
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
        Index("ix_correspondences_issuing_code", "issuing_code"),
        Index("ix_correspondences_category_code", "category_code"),
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
    size_bytes: Mapped[int | None] = mapped_column(Integer)
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
