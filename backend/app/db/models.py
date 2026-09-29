"""
SQLAlchemy ORM models for RepoPilot AI.

Entity hierarchy:
    Repository
    └── File          (repository_id FK, unique on repository_id+path)
        └── Symbol    (file_id FK)

    Relationship      (repository_id FK, source_symbol_id FK, target_symbol_id FK)
      source ──► Symbol
      target ──► Symbol

Relationships are directed: source_symbol_id calls/imports/etc target_symbol_id.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class Repository(Base):
    """A Python repository being analysed."""

    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    # Status values: pending | ingesting | ready | failed
    # Stored as plain VARCHAR — easy to evolve without DDL enum changes.
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    files: Mapped[list["File"]] = relationship(
        "File", back_populates="repository", cascade="all, delete-orphan"
    )
    code_relationships: Mapped[list["CodeRelationship"]] = relationship(
        "CodeRelationship", back_populates="repository", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Repository id={self.id} name={self.name!r} status={self.status!r}>"


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------

class File(Base):
    """A source file belonging to a repository."""

    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("repository_id", "path", name="uq_files_repository_path"),
        Index("ix_files_repository_id", "repository_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    repository: Mapped["Repository"] = relationship("Repository", back_populates="files")
    symbols: Mapped[list["Symbol"]] = relationship(
        "Symbol", back_populates="file", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<File id={self.id} path={self.path!r}>"


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------

class Symbol(Base):
    """
    A named code element inside a file: module, class, function, method, etc.

    symbol_type values: module | class | function | async_function | method
    """

    __tablename__ = "symbols"
    __table_args__ = (
        Index("ix_symbols_file_id", "file_id"),
        Index("ix_symbols_qualified_name", "qualified_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    # symbol_type values: module | class | function | async_function | method
    symbol_type: Mapped[str] = mapped_column(String(50), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    file: Mapped["File"] = relationship("File", back_populates="symbols")
    outgoing_relationships: Mapped[list["CodeRelationship"]] = relationship(
        "CodeRelationship",
        foreign_keys="CodeRelationship.source_symbol_id",
        back_populates="source_symbol",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list["CodeRelationship"]] = relationship(
        "CodeRelationship",
        foreign_keys="CodeRelationship.target_symbol_id",
        back_populates="target_symbol",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Symbol id={self.id} qualified_name={self.qualified_name!r} type={self.symbol_type!r}>"


# ---------------------------------------------------------------------------
# CodeRelationship
# ---------------------------------------------------------------------------

class CodeRelationship(Base):
    """
    A directed relationship between two symbols.

    Direction: source_symbol_id ──► target_symbol_id

    relationship_type values: IMPORTS | DEFINES | CALLS | INHERITS | USES

    confidence is nullable to support future uncertain/inferred relationships.
    The schema does not enforce a fixed enum so new relationship types can be
    added without a DDL change.
    """

    __tablename__ = "relationships"
    __table_args__ = (
        Index("ix_relationships_repository_id", "repository_id"),
        Index("ix_relationships_source_symbol_id", "source_symbol_id"),
        Index("ix_relationships_target_symbol_id", "target_symbol_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    source_symbol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False
    )
    target_symbol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False
    )
    # relationship_type values: IMPORTS | DEFINES | CALLS | INHERITS | USES
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="code_relationships"
    )
    source_symbol: Mapped["Symbol"] = relationship(
        "Symbol",
        foreign_keys=[source_symbol_id],
        back_populates="outgoing_relationships",
    )
    target_symbol: Mapped["Symbol"] = relationship(
        "Symbol",
        foreign_keys=[target_symbol_id],
        back_populates="incoming_relationships",
    )

    def __repr__(self) -> str:
        return (
            f"<CodeRelationship {self.source_symbol_id} "
            f"--[{self.relationship_type}]--> {self.target_symbol_id}>"
        )


# ---------------------------------------------------------------------------
# CodeChunk
# ---------------------------------------------------------------------------

class CodeChunk(Base):
    """
    A searchable piece of source code extracted from a repository.

    PostgreSQL stores chunk metadata and source content.
    ChromaDB stores the corresponding embedding vectors.

    The relationship between the two stores:
        CodeChunk.id (UUID) ↔ Chroma document id (str(UUID))

    symbol_id is nullable — module-level chunks have no associated symbol.
    """

    __tablename__ = "code_chunks"
    __table_args__ = (
        Index("ix_code_chunks_repository_id", "repository_id"),
        Index("ix_code_chunks_file_id", "file_id"),
        Index("ix_code_chunks_symbol_id", "symbol_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<CodeChunk id={self.id} file_id={self.file_id} lines={self.start_line}-{self.end_line}>"
