"""
Tests for the repository ingestion service.

Test DB
-------
All tests use an in-memory SQLite database via the db_session fixture in conftest.py.
No live PostgreSQL is required.

Session management
------------------
ingest_repository() adds objects but does NOT commit.  autoflush=True on the
session means a SELECT query automatically flushes pending objects first, so
data is visible without an explicit flush/commit.

Fixture repos
-------------
  simple_repo/    utils.py + models.py + main.py   — cross-file CALLS, IMPORTS, INHERITS
  ambiguous_repo/ alpha.py + beta.py + gamma.py    — same function name in two files
  error_repo/     good.py + bad.py(syntax error)   — partial-parse repo
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import CodeRelationship, File, Repository, Symbol
from app.services.ingestion import IngestionResult, ingest_repository

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"
SIMPLE_REPO = _FIXTURES / "simple_repo"
AMBIGUOUS_REPO = _FIXTURES / "ambiguous_repo"
ERROR_REPO = _FIXTURES / "error_repo"


# ---------------------------------------------------------------------------
# Repository validation
# ---------------------------------------------------------------------------

class TestRepositoryValidation:
    async def test_nonexistent_path_raises(self, db_session):
        with pytest.raises(ValueError, match="does not exist"):
            await ingest_repository(db_session, "/nonexistent/path/xyz")

    async def test_file_path_raises(self, db_session, tmp_path):
        f = tmp_path / "file.py"
        f.write_text("x = 1")
        with pytest.raises(ValueError, match="not a directory"):
            await ingest_repository(db_session, f)

    async def test_valid_path_accepted(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        assert result.status == "ready"


# ---------------------------------------------------------------------------
# Basic ingestion — simple_repo
# ---------------------------------------------------------------------------

class TestBasicIngestion:
    async def test_repository_record_created(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)

        repos = (await db_session.execute(select(Repository))).scalars().all()
        assert len(repos) == 1
        assert repos[0].id == result.repository_id
        assert repos[0].status == "ready"

    async def test_repository_name_defaults_to_dirname(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        assert result.repository_name == "simple_repo"

    async def test_custom_name_used(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO, name="My Repo")
        assert result.repository_name == "My Repo"

    async def test_file_count(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        # utils.py, models.py, main.py — three files
        assert result.total_files == 3
        assert result.parsed_files == 3
        assert result.files_with_errors == 0

    async def test_file_rows_created(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        files = (await db_session.execute(select(File))).scalars().all()
        assert len(files) == 3

    async def test_file_paths_are_posix_relative(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        files = (await db_session.execute(select(File))).scalars().all()
        paths = {f.path for f in files}
        assert paths == {"utils.py", "models.py", "main.py"}

    async def test_file_has_size_and_hash(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        files = (await db_session.execute(select(File))).scalars().all()
        for f in files:
            assert f.size is not None and f.size > 0
            assert f.content_hash is not None and len(f.content_hash) == 64

    async def test_symbols_created(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        assert result.total_symbols > 0

        syms = (await db_session.execute(select(Symbol))).scalars().all()
        assert len(syms) == result.total_symbols


# ---------------------------------------------------------------------------
# Symbol metadata
# ---------------------------------------------------------------------------

class TestSymbolPersistence:
    async def test_module_symbols_present(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        module_syms = (await db_session.execute(
            select(Symbol).where(Symbol.symbol_type == "module")
        )).scalars().all()
        qnames = {s.qualified_name for s in module_syms}
        # One module symbol per file
        assert "utils" in qnames
        assert "models" in qnames
        assert "main" in qnames

    async def test_class_symbol_type_and_name(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        user = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "User")
        )).scalars().first()
        assert user is not None
        assert user.symbol_type == "class"
        assert user.name == "User"

    async def test_method_symbol_type(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        greet = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "User.greet")
        )).scalars().first()
        assert greet is not None
        assert greet.symbol_type == "method"

    async def test_function_symbol_type(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        proc = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "process")
        )).scalars().first()
        assert proc is not None
        assert proc.symbol_type == "function"

    async def test_qualified_name_preserved(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        init = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "User.__init__")
        )).scalars().first()
        assert init is not None
        assert init.name == "__init__"

    async def test_source_lines_preserved(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        proc = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "process")
        )).scalars().first()
        assert proc is not None
        assert proc.start_line >= 1
        assert proc.end_line >= proc.start_line

    async def test_docstring_preserved(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        entity = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "Entity")
        )).scalars().first()
        assert entity is not None
        assert entity.docstring == "Base entity class."

    async def test_signature_preserved(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        run = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "run")
        )).scalars().first()
        assert run is not None
        assert run.signature is not None
        assert "data" in run.signature


# ---------------------------------------------------------------------------
# DEFINES relationships
# ---------------------------------------------------------------------------

class TestDefinesRelationships:
    async def test_module_defines_class(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        # models module should DEFINE User
        models_mod = (await db_session.execute(
            select(Symbol).where(
                Symbol.qualified_name == "models",
                Symbol.symbol_type == "module",
            )
        )).scalars().first()
        user_sym = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "User")
        )).scalars().first()
        assert models_mod and user_sym

        rel = (await db_session.execute(
            select(CodeRelationship).where(
                CodeRelationship.source_symbol_id == models_mod.id,
                CodeRelationship.target_symbol_id == user_sym.id,
                CodeRelationship.relationship_type == "DEFINES",
            )
        )).scalars().first()
        assert rel is not None
        assert rel.confidence == 1.0

    async def test_class_defines_method(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        user_sym = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "User")
        )).scalars().first()
        greet_sym = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "User.greet")
        )).scalars().first()
        assert user_sym and greet_sym

        rel = (await db_session.execute(
            select(CodeRelationship).where(
                CodeRelationship.source_symbol_id == user_sym.id,
                CodeRelationship.target_symbol_id == greet_sym.id,
                CodeRelationship.relationship_type == "DEFINES",
            )
        )).scalars().first()
        assert rel is not None


# ---------------------------------------------------------------------------
# INHERITS relationships
# ---------------------------------------------------------------------------

class TestInheritsRelationships:
    async def test_user_inherits_entity(self, db_session):
        await ingest_repository(db_session, SIMPLE_REPO)

        user_sym = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "User")
        )).scalars().first()
        entity_sym = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "Entity")
        )).scalars().first()
        assert user_sym and entity_sym

        rel = (await db_session.execute(
            select(CodeRelationship).where(
                CodeRelationship.source_symbol_id == user_sym.id,
                CodeRelationship.target_symbol_id == entity_sym.id,
                CodeRelationship.relationship_type == "INHERITS",
            )
        )).scalars().first()
        assert rel is not None
        assert rel.confidence == 1.0


# ---------------------------------------------------------------------------
# CALLS relationships
# ---------------------------------------------------------------------------

class TestCallsRelationships:
    async def test_cross_file_call_resolved(self, db_session):
        """run() in main.py calls process() in utils.py — should resolve."""
        await ingest_repository(db_session, SIMPLE_REPO)

        run_sym = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "run")
        )).scalars().first()
        proc_sym = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "process")
        )).scalars().first()
        assert run_sym and proc_sym

        rel = (await db_session.execute(
            select(CodeRelationship).where(
                CodeRelationship.source_symbol_id == run_sym.id,
                CodeRelationship.target_symbol_id == proc_sym.id,
                CodeRelationship.relationship_type == "CALLS",
            )
        )).scalars().first()
        assert rel is not None
        assert rel.confidence == pytest.approx(0.9)

    async def test_builtin_calls_not_persisted(self, db_session):
        """Calls to Python builtins (str, join) have no repo symbol → not persisted."""
        await ingest_repository(db_session, SIMPLE_REPO)

        # No symbol named "str" or "join" should exist
        str_sym = (await db_session.execute(
            select(Symbol).where(Symbol.name == "str")
        )).scalars().first()
        assert str_sym is None


# ---------------------------------------------------------------------------
# IMPORTS relationships
# ---------------------------------------------------------------------------

class TestImportsRelationships:
    async def test_local_import_resolved(self, db_session):
        """from utils import process — should resolve to the process symbol."""
        await ingest_repository(db_session, SIMPLE_REPO)

        proc_sym = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "process")
        )).scalars().first()
        assert proc_sym is not None

        imports = (await db_session.execute(
            select(CodeRelationship).where(
                CodeRelationship.target_symbol_id == proc_sym.id,
                CodeRelationship.relationship_type == "IMPORTS",
            )
        )).scalars().all()
        assert len(imports) >= 1

    async def test_external_import_not_persisted(self, db_session):
        """External stdlib/third-party symbols must NOT be created in the DB."""
        await ingest_repository(db_session, SIMPLE_REPO)

        # utils.py and models.py have no imports; main.py imports only from utils.
        # No external stdlib symbols (like 'typing' or 'Optional') should exist.
        external = (await db_session.execute(
            select(Symbol).where(Symbol.name.in_(["Optional", "dataclass", "typing"]))
        )).scalars().all()
        assert len(external) == 0


# ---------------------------------------------------------------------------
# Ambiguous name resolution
# ---------------------------------------------------------------------------

class TestAmbiguousResolution:
    async def test_ambiguous_call_not_resolved(self, db_session):
        """
        gamma.caller() calls helper(), but helper exists in BOTH alpha.py and
        beta.py.  The resolver must not arbitrarily pick one target.  The CALLS
        relationship should be left unresolved (not persisted).
        """
        result = await ingest_repository(db_session, AMBIGUOUS_REPO)

        calls = (await db_session.execute(
            select(CodeRelationship).where(
                CodeRelationship.relationship_type == "CALLS"
            )
        )).scalars().all()
        # The only CALLS in this repo is the ambiguous helper() — must not be persisted
        assert len(calls) == 0
        assert result.unresolved_relationships >= 1

    async def test_ambiguous_repo_symbols_still_created(self, db_session):
        """Even though a call was unresolved, all defined symbols must be persisted."""
        await ingest_repository(db_session, AMBIGUOUS_REPO)

        # Both helper() definitions and caller() must be in the DB
        helpers = (await db_session.execute(
            select(Symbol).where(Symbol.name == "helper")
        )).scalars().all()
        assert len(helpers) == 2  # one from alpha.py, one from beta.py

        callers = (await db_session.execute(
            select(Symbol).where(Symbol.name == "caller")
        )).scalars().all()
        assert len(callers) == 1


# ---------------------------------------------------------------------------
# Parse errors
# ---------------------------------------------------------------------------

class TestParseErrors:
    async def test_status_ready_despite_error_file(self, db_session):
        """A single syntax-error file must NOT cause the whole ingestion to fail."""
        result = await ingest_repository(db_session, ERROR_REPO)
        assert result.status == "ready"
        assert result.files_with_errors == 1
        assert result.parsed_files == 1
        assert result.total_files == 2

    async def test_parse_error_summary_recorded(self, db_session):
        result = await ingest_repository(db_session, ERROR_REPO)
        assert len(result.parse_errors) >= 1
        assert any("bad.py" in e for e in result.parse_errors)

    async def test_valid_file_symbols_persisted_despite_peer_error(self, db_session):
        """Symbols from good.py must still appear in the DB."""
        await ingest_repository(db_session, ERROR_REPO)

        greet = (await db_session.execute(
            select(Symbol).where(Symbol.qualified_name == "greet")
        )).scalars().first()
        assert greet is not None
        assert greet.symbol_type == "function"

    async def test_error_file_row_created(self, db_session):
        """A File row must be created even for the syntax-error file."""
        await ingest_repository(db_session, ERROR_REPO)

        files = (await db_session.execute(select(File))).scalars().all()
        paths = {f.path for f in files}
        assert "bad.py" in paths
        assert "good.py" in paths

    async def test_error_file_has_no_symbols(self, db_session):
        await ingest_repository(db_session, ERROR_REPO)

        bad_file = (await db_session.execute(
            select(File).where(File.path == "bad.py")
        )).scalars().first()
        assert bad_file is not None

        bad_syms = (await db_session.execute(
            select(Symbol).where(Symbol.file_id == bad_file.id)
        )).scalars().all()
        assert len(bad_syms) == 0


# ---------------------------------------------------------------------------
# Re-ingestion
# ---------------------------------------------------------------------------

class TestReingestion:
    async def test_second_call_creates_new_repository(self, db_session):
        """
        Each call to ingest_repository() creates an independent Repository record.
        Re-ingesting the same path does NOT overwrite existing data.
        """
        result1 = await ingest_repository(db_session, SIMPLE_REPO)
        result2 = await ingest_repository(db_session, SIMPLE_REPO)

        assert result1.repository_id != result2.repository_id

        repos = (await db_session.execute(select(Repository))).scalars().all()
        assert len(repos) == 2

    async def test_second_call_does_not_duplicate_across_repos(self, db_session):
        """
        The second ingestion must not violate the (repository_id, path) unique
        constraint — each repo has its own File rows.
        """
        result1 = await ingest_repository(db_session, SIMPLE_REPO)
        result2 = await ingest_repository(db_session, SIMPLE_REPO)

        files1 = (await db_session.execute(
            select(File).where(File.repository_id == result1.repository_id)
        )).scalars().all()
        files2 = (await db_session.execute(
            select(File).where(File.repository_id == result2.repository_id)
        )).scalars().all()

        assert len(files1) == 3
        assert len(files2) == 3
        # Different File UUIDs for the two ingestions
        ids1 = {f.id for f in files1}
        ids2 = {f.id for f in files2}
        assert ids1.isdisjoint(ids2)

    async def test_ingestion_result_has_repository_id(self, db_session):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        assert isinstance(result.repository_id, uuid.UUID)
        assert result.repository_id != uuid.UUID(int=0)
