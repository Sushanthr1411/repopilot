"""
Unit tests for SQLAlchemy models.
These tests inspect metadata only — no live database required.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.db.database import Base
import app.db.models  # noqa: F401 — register models with Base
from app.db.models import CodeRelationship, File, Repository, Symbol


# ---------------------------------------------------------------------------
# Table presence
# ---------------------------------------------------------------------------

def test_all_tables_registered():
    table_names = set(Base.metadata.tables.keys())
    assert "repositories" in table_names
    assert "files" in table_names
    assert "symbols" in table_names
    assert "relationships" in table_names


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class TestRepositoryModel:
    def test_tablename(self):
        assert Repository.__tablename__ == "repositories"

    def test_required_columns_present(self):
        cols = {c.name for c in Repository.__table__.columns}
        assert {"id", "name", "source_url", "local_path", "status", "created_at", "updated_at"} <= cols

    def test_status_column_is_string(self):
        col = Repository.__table__.c["status"]
        from sqlalchemy import String
        assert isinstance(col.type, String)

    def test_status_default_value(self):
        col = Repository.__table__.c["status"]
        assert col.server_default is not None

    def test_source_url_nullable(self):
        assert Repository.__table__.c["source_url"].nullable is True

    def test_local_path_nullable(self):
        assert Repository.__table__.c["local_path"].nullable is True

    def test_files_relationship_configured(self):
        assert hasattr(Repository, "files")

    def test_code_relationships_relationship_configured(self):
        assert hasattr(Repository, "code_relationships")


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------

class TestFileModel:
    def test_tablename(self):
        assert File.__tablename__ == "files"

    def test_required_columns_present(self):
        cols = {c.name for c in File.__table__.columns}
        assert {"id", "repository_id", "path", "language", "size", "content_hash", "created_at", "updated_at"} <= cols

    def test_repository_id_fk(self):
        fks = {fk.target_fullname for fk in File.__table__.c["repository_id"].foreign_keys}
        assert "repositories.id" in fks

    def test_unique_constraint_repository_path(self):
        constraint_names = {uc.name for uc in File.__table__.constraints}
        assert "uq_files_repository_path" in constraint_names

    def test_index_repository_id(self):
        index_names = {idx.name for idx in File.__table__.indexes}
        assert "ix_files_repository_id" in index_names

    def test_language_nullable(self):
        assert File.__table__.c["language"].nullable is True

    def test_size_nullable(self):
        assert File.__table__.c["size"].nullable is True

    def test_content_hash_nullable(self):
        assert File.__table__.c["content_hash"].nullable is True

    def test_symbols_relationship_configured(self):
        assert hasattr(File, "symbols")

    def test_repository_relationship_configured(self):
        assert hasattr(File, "repository")


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------

class TestSymbolModel:
    def test_tablename(self):
        assert Symbol.__tablename__ == "symbols"

    def test_required_columns_present(self):
        cols = {c.name for c in Symbol.__table__.columns}
        assert {
            "id", "file_id", "name", "qualified_name", "symbol_type",
            "start_line", "end_line", "signature", "docstring",
            "created_at", "updated_at",
        } <= cols

    def test_file_id_fk(self):
        fks = {fk.target_fullname for fk in Symbol.__table__.c["file_id"].foreign_keys}
        assert "files.id" in fks

    def test_index_file_id(self):
        index_names = {idx.name for idx in Symbol.__table__.indexes}
        assert "ix_symbols_file_id" in index_names

    def test_index_qualified_name(self):
        index_names = {idx.name for idx in Symbol.__table__.indexes}
        assert "ix_symbols_qualified_name" in index_names

    def test_signature_nullable(self):
        assert Symbol.__table__.c["signature"].nullable is True

    def test_docstring_nullable(self):
        assert Symbol.__table__.c["docstring"].nullable is True

    def test_outgoing_relationships_configured(self):
        assert hasattr(Symbol, "outgoing_relationships")

    def test_incoming_relationships_configured(self):
        assert hasattr(Symbol, "incoming_relationships")


# ---------------------------------------------------------------------------
# CodeRelationship
# ---------------------------------------------------------------------------

class TestCodeRelationshipModel:
    def test_tablename(self):
        assert CodeRelationship.__tablename__ == "relationships"

    def test_required_columns_present(self):
        cols = {c.name for c in CodeRelationship.__table__.columns}
        assert {
            "id", "repository_id", "source_symbol_id", "target_symbol_id",
            "relationship_type", "confidence", "created_at",
        } <= cols

    def test_repository_id_fk(self):
        fks = {fk.target_fullname for fk in CodeRelationship.__table__.c["repository_id"].foreign_keys}
        assert "repositories.id" in fks

    def test_source_symbol_fk(self):
        fks = {fk.target_fullname for fk in CodeRelationship.__table__.c["source_symbol_id"].foreign_keys}
        assert "symbols.id" in fks

    def test_target_symbol_fk(self):
        fks = {fk.target_fullname for fk in CodeRelationship.__table__.c["target_symbol_id"].foreign_keys}
        assert "symbols.id" in fks

    def test_confidence_nullable(self):
        assert CodeRelationship.__table__.c["confidence"].nullable is True

    def test_index_repository_id(self):
        index_names = {idx.name for idx in CodeRelationship.__table__.indexes}
        assert "ix_relationships_repository_id" in index_names

    def test_index_source_symbol_id(self):
        index_names = {idx.name for idx in CodeRelationship.__table__.indexes}
        assert "ix_relationships_source_symbol_id" in index_names

    def test_index_target_symbol_id(self):
        index_names = {idx.name for idx in CodeRelationship.__table__.indexes}
        assert "ix_relationships_target_symbol_id" in index_names

    def test_source_symbol_relationship_configured(self):
        assert hasattr(CodeRelationship, "source_symbol")

    def test_target_symbol_relationship_configured(self):
        assert hasattr(CodeRelationship, "target_symbol")
