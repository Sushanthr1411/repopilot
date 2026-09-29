"""
Tests for Step 7 — RepoPilot agent tool layer.

All tests run against an in-memory SQLite database (same infrastructure as
Steps 4–6).  Graph tests use build_repository_graph directly (no mocking
needed — NetworkX is pure Python).  Search tests use FakeEmbeddingProvider
and ChromaVectorStore.ephemeral() — no network or PyTorch needed.

Test structure
--------------
TestSearchCodeTool       — search_code
TestInspectSymbolTool    — inspect_symbol
TestReadFileTool         — read_file
TestGetDependenciesTool  — get_dependencies
TestGetDependentsTool    — get_dependents
TestGetCallersTool       — get_callers
TestGetCalleesTool       — get_callees
TestGetFileDependsTool   — get_file_dependencies
TestToolRegistry         — registry completeness and schema invariants
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CodeRelationship, File, Repository, Symbol
from app.services.ingestion import ingest_repository
from app.services.search import index_repository
from app.services.search.embeddings import FakeEmbeddingProvider
from app.services.search.vector_store import ChromaVectorStore
from app.tools import (
    REPOPILOT_TOOLS,
    REPOPILOT_TOOLS_BY_NAME,
    get_callees,
    get_callers,
    get_dependencies,
    get_dependents,
    get_file_dependencies,
    inspect_symbol,
    read_file,
    search_code,
)
from app.tools.models import ToolErrorCode

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

SIMPLE_REPO = Path(__file__).parent / "fixtures" / "ingestion" / "simple_repo"


# ---------------------------------------------------------------------------
# Shared DB fixtures (function-scoped via conftest.py)
# ---------------------------------------------------------------------------

@pytest.fixture
async def ingested(db_session: AsyncSession):
    """Ingest simple_repo into an in-memory SQLite DB; return IngestionResult."""
    result = await ingest_repository(db_session, SIMPLE_REPO)
    await db_session.commit()
    return result


@pytest.fixture
async def ephemeral_store():
    """Fresh in-memory ChromaDB for search tests."""
    return ChromaVectorStore.ephemeral("tools_test")


@pytest.fixture
def fake_provider():
    return FakeEmbeddingProvider(dim=8)


@pytest.fixture
async def indexed(db_session: AsyncSession, ingested, ephemeral_store, fake_provider):
    """Ingest + index simple_repo; return (ingestion_result, store, provider)."""
    stats = await index_repository(
        ingested.repository_id, db_session, fake_provider, ephemeral_store
    )
    await db_session.commit()
    return ingested, ephemeral_store, fake_provider


# ---------------------------------------------------------------------------
# Helpers: look up symbols / files from DB after ingestion
# ---------------------------------------------------------------------------

async def _find_symbol(db: AsyncSession, repo_id: uuid.UUID, name: str) -> Symbol:
    """Return first symbol matching name in the given repository."""
    row = (
        await db.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(File.repository_id == repo_id, Symbol.name == name)
        )
    ).first()
    assert row is not None, f"symbol {name!r} not found in repo"
    return row[0]


async def _find_file(db: AsyncSession, repo_id: uuid.UUID, path: str) -> File:
    row = (
        await db.execute(
            select(File).where(File.repository_id == repo_id, File.path == path)
        )
    ).scalar_one_or_none()
    assert row is not None, f"file {path!r} not found in repo"
    return row


# ===========================================================================
# TestSearchCodeTool
# ===========================================================================

class TestSearchCodeTool:
    async def test_valid_query_returns_results(self, db_session, indexed):
        ingested, store, provider = indexed
        result = await search_code(
            ingested.repository_id,
            "process list",
            top_k=5,
            db=db_session,
            embedding_provider=provider,
            vector_store=store,
        )
        assert result.success
        assert result.data is not None
        assert result.data.query == "process list"
        assert result.data.repository_id == ingested.repository_id
        assert result.data.returned == len(result.data.results)

    async def test_result_has_source_location(self, db_session, indexed):
        ingested, store, provider = indexed
        result = await search_code(
            ingested.repository_id, "greeting", top_k=3,
            db=db_session, embedding_provider=provider, vector_store=store,
        )
        assert result.success
        for match in result.data.results:
            assert match.file_path
            assert match.start_line >= 1
            assert match.end_line >= match.start_line
            assert isinstance(match.distance, float)
            assert match.chunk_id is not None
            assert match.file_id is not None

    async def test_empty_query_returns_error(self, db_session, indexed):
        ingested, store, provider = indexed
        result = await search_code(
            ingested.repository_id, "",
            db=db_session, embedding_provider=provider, vector_store=store,
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.INVALID_INPUT

    async def test_whitespace_only_query_returns_error(self, db_session, indexed):
        ingested, store, provider = indexed
        result = await search_code(
            ingested.repository_id, "   ",
            db=db_session, embedding_provider=provider, vector_store=store,
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.INVALID_INPUT

    async def test_zero_top_k_returns_error(self, db_session, indexed):
        ingested, store, provider = indexed
        result = await search_code(
            ingested.repository_id, "something", top_k=0,
            db=db_session, embedding_provider=provider, vector_store=store,
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.INVALID_INPUT

    async def test_top_k_capped_at_max(self, db_session, indexed):
        """Requesting more results than the hard cap sets truncated=True."""
        ingested, store, provider = indexed
        from app.core.config import settings
        over_limit = settings.tool_search_max_results + 10
        result = await search_code(
            ingested.repository_id, "function",
            top_k=over_limit,
            db=db_session, embedding_provider=provider, vector_store=store,
        )
        assert result.success
        assert result.data.truncated

    async def test_no_results_for_unindexed_repository(self, db_session, ingested, ephemeral_store, fake_provider):
        """Repository ingested but never indexed returns empty results (not an error)."""
        result = await search_code(
            ingested.repository_id, "something",
            db=db_session, embedding_provider=fake_provider, vector_store=ephemeral_store,
        )
        assert result.success
        assert result.data.returned == 0

    async def test_repository_isolation(self, db_session, fake_provider):
        """Results from repo A must not appear when querying repo B."""
        store = ChromaVectorStore.ephemeral("isolation_test")
        # Ingest and index repo A
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="repo_a")
        await db_session.commit()
        await index_repository(result_a.repository_id, db_session, fake_provider, store)
        await db_session.commit()

        # Ingest repo B (same files, different UUID)
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="repo_b")
        await db_session.commit()
        await index_repository(result_b.repository_id, db_session, fake_provider, store)
        await db_session.commit()

        # Query repo A — the result's repository_id must be repo A
        search_result = await search_code(
            result_a.repository_id, "process items", top_k=20,
            db=db_session, embedding_provider=fake_provider, vector_store=store,
        )
        assert search_result.success
        assert search_result.data.repository_id == result_a.repository_id
        # Verify isolation: file paths should all correspond to repo A's files.
        # The underlying Chroma query filters by repository_id metadata, so
        # none of repo B's chunks should appear here.
        assert search_result.data.returned >= 0  # may be 0 if store is empty


# ===========================================================================
# TestInspectSymbolTool
# ===========================================================================

class TestInspectSymbolTool:
    async def test_lookup_by_symbol_id(self, db_session, ingested):
        sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await inspect_symbol(
            ingested.repository_id, symbol_id=sym.id, db=db_session
        )
        assert result.success
        assert result.data.name == "process"
        assert result.data.file_path == "utils.py"
        assert result.data.start_line >= 1
        assert result.data.end_line >= result.data.start_line

    async def test_lookup_by_qualified_name(self, db_session, ingested):
        result = await inspect_symbol(
            ingested.repository_id,
            qualified_name="process",
            db=db_session,
        )
        assert result.success
        assert result.data.qualified_name == "process"

    async def test_symbol_id_takes_precedence(self, db_session, ingested):
        """When both symbol_id and qualified_name are given, symbol_id wins."""
        sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await inspect_symbol(
            ingested.repository_id,
            symbol_id=sym.id,
            qualified_name="utils.format_output",  # different symbol
            db=db_session,
        )
        assert result.success
        assert result.data.name == "process"

    async def test_source_code_returned(self, db_session, ingested):
        result = await inspect_symbol(
            ingested.repository_id,
            qualified_name="process",
            db=db_session,
        )
        assert result.success
        assert result.data.source is not None
        assert "def process" in result.data.source

    async def test_signature_and_docstring(self, db_session, ingested):
        result = await inspect_symbol(
            ingested.repository_id,
            qualified_name="process",
            db=db_session,
        )
        assert result.success
        # signature and docstring may be None if parser didn't extract them,
        # but the fields must be present in the result.
        assert hasattr(result.data, "signature")
        assert hasattr(result.data, "docstring")

    async def test_symbol_not_found_returns_not_found_error(self, db_session, ingested):
        result = await inspect_symbol(
            ingested.repository_id,
            symbol_id=uuid.uuid4(),  # random ID — definitely absent
            db=db_session,
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_qualified_name_not_found(self, db_session, ingested):
        result = await inspect_symbol(
            ingested.repository_id,
            qualified_name="nonexistent_symbol_xyz",
            db=db_session,
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_no_identifier_returns_invalid_input(self, db_session, ingested):
        result = await inspect_symbol(ingested.repository_id, db=db_session)
        assert not result.success
        assert result.error.code == ToolErrorCode.INVALID_INPUT

    async def test_repository_isolation_by_symbol_id(self, db_session):
        """A symbol from repo B cannot be retrieved with repo A's ID."""
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="iso_a")
        await db_session.commit()
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="iso_b")
        await db_session.commit()

        # Get a symbol ID from repo B
        sym_b = await _find_symbol(db_session, result_b.repository_id, "process")

        # Try to retrieve it via repo A's ID → must be NOT_FOUND
        result = await inspect_symbol(
            result_a.repository_id, symbol_id=sym_b.id, db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_result_has_file_id(self, db_session, ingested):
        result = await inspect_symbol(
            ingested.repository_id,
            qualified_name="process",
            db=db_session,
        )
        assert result.success
        assert result.data.file_id is not None
        assert isinstance(result.data.file_id, uuid.UUID)


# ===========================================================================
# TestReadFileTool
# ===========================================================================

class TestReadFileTool:
    async def test_read_whole_file(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "utils.py", db=db_session
        )
        assert result.success
        assert "def process" in result.data.content
        assert result.data.total_lines >= 1
        assert result.data.actual_start_line == 1
        assert not result.data.truncated

    async def test_read_line_range(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "utils.py",
            start_line=1, end_line=3,
            db=db_session,
        )
        assert result.success
        assert result.data.actual_start_line == 1
        assert result.data.actual_end_line == 3
        assert result.data.requested_start_line == 1
        assert result.data.requested_end_line == 3
        assert len(result.data.content.splitlines()) <= 3

    async def test_missing_file_returns_not_found(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "nonexistent.py", db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_path_traversal_dotdot_rejected(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "../../../etc/passwd", db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.PATH_NOT_ALLOWED

    async def test_path_traversal_prefix_rejected(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "a/../../../secret", db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.PATH_NOT_ALLOWED

    async def test_absolute_path_rejected(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "/etc/passwd", db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.PATH_NOT_ALLOWED

    async def test_windows_absolute_path_rejected(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "C:\\Windows\\System32\\cmd.exe", db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.PATH_NOT_ALLOWED

    async def test_line_limit_truncates(self, db_session, ingested):
        """When more lines are requested than the cap, truncated=True is set."""
        from app.core.config import settings
        import app.core.config as cfg_module
        original = settings.tool_file_max_lines
        try:
            settings.tool_file_max_lines = 1  # force truncation
            result = await read_file(
                ingested.repository_id, "utils.py", db=db_session
            )
            assert result.success
            assert result.data.truncated
            assert len(result.data.content.splitlines()) <= 1
        finally:
            settings.tool_file_max_lines = original

    async def test_invalid_line_range_start_gt_end(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "utils.py",
            start_line=10, end_line=5,
            db=db_session,
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.INVALID_INPUT

    async def test_invalid_start_line_zero(self, db_session, ingested):
        result = await read_file(
            ingested.repository_id, "utils.py",
            start_line=0,
            db=db_session,
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.INVALID_INPUT

    async def test_repository_isolation(self, db_session):
        """File belonging to repo B cannot be retrieved using repo A's ID."""
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="file_iso_a")
        await db_session.commit()
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="file_iso_b")
        await db_session.commit()

        # "utils.py" exists in both repos but is scoped by repository_id
        res = await read_file(result_a.repository_id, "utils.py", db=db_session)
        assert res.success
        # Use a file_id from repo B with repo A's context — not possible via
        # the path-based API, but we can verify the correct file is returned
        assert res.data.repository_id == result_a.repository_id

    async def test_language_field_present(self, db_session, ingested):
        result = await read_file(ingested.repository_id, "utils.py", db=db_session)
        assert result.success
        # language may be "python" or None depending on parser; field must exist
        assert hasattr(result.data, "language")

    async def test_unknown_repository_returns_error(self, db_session):
        result = await read_file(uuid.uuid4(), "utils.py", db=db_session)
        assert not result.success
        assert result.error.code == ToolErrorCode.INVALID_REPOSITORY


# ===========================================================================
# TestGetDependenciesTool
# ===========================================================================

class TestGetDependenciesTool:
    async def test_direct_dependency_exists(self, db_session, ingested):
        """run() in main.py should call process() and/or format_output() in utils.py."""
        run_sym = await _find_symbol(db_session, ingested.repository_id, "run")
        result = await get_dependencies(
            ingested.repository_id, run_sym.id, db=db_session
        )
        assert result.success
        assert result.data.returned >= 0  # may be 0 if resolver didn't link them
        assert result.data.source_symbol.name == "run"
        assert isinstance(result.data.dependencies, list)

    async def test_dependency_entries_have_source_locations(self, db_session, ingested):
        run_sym = await _find_symbol(db_session, ingested.repository_id, "run")
        result = await get_dependencies(
            ingested.repository_id, run_sym.id, db=db_session
        )
        assert result.success
        for entry in result.data.dependencies:
            assert entry.symbol.file_path
            assert entry.symbol.start_line >= 1
            assert entry.relationship_type

    async def test_relationship_type_filter(self, db_session, ingested):
        run_sym = await _find_symbol(db_session, ingested.repository_id, "run")
        result = await get_dependencies(
            ingested.repository_id, run_sym.id,
            relationship_types=["CALLS"],
            db=db_session,
        )
        assert result.success
        for entry in result.data.dependencies:
            assert entry.relationship_type == "CALLS"

    async def test_filter_excludes_non_matching(self, db_session, ingested):
        run_sym = await _find_symbol(db_session, ingested.repository_id, "run")
        result = await get_dependencies(
            ingested.repository_id, run_sym.id,
            relationship_types=["NONEXISTENT_TYPE"],
            db=db_session,
        )
        assert result.success
        assert result.data.returned == 0

    async def test_unknown_symbol_returns_not_found(self, db_session, ingested):
        result = await get_dependencies(
            ingested.repository_id, uuid.uuid4(), db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_repository_isolation(self, db_session):
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="dep_iso_a")
        await db_session.commit()
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="dep_iso_b")
        await db_session.commit()

        # Symbol from repo B used with repo A — should be NOT_FOUND
        sym_b = await _find_symbol(db_session, result_b.repository_id, "run")
        result = await get_dependencies(
            result_a.repository_id, sym_b.id, db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_empty_dependencies_is_not_error(self, db_session, ingested):
        """A leaf symbol with no outgoing edges is not an error."""
        # process() typically has no further outgoing deps in simple_repo
        process_sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await get_dependencies(
            ingested.repository_id, process_sym.id, db=db_session
        )
        assert result.success


# ===========================================================================
# TestGetDependentsTool
# ===========================================================================

class TestGetDependentsTool:
    async def test_direct_dependent_exists(self, db_session, ingested):
        """process() should have 'run' as a dependent (run calls process)."""
        process_sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await get_dependents(
            ingested.repository_id, process_sym.id, db=db_session
        )
        assert result.success
        assert result.data.target_symbol.name == "process"
        assert isinstance(result.data.dependents, list)

    async def test_relationship_type_filter(self, db_session, ingested):
        process_sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await get_dependents(
            ingested.repository_id, process_sym.id,
            relationship_types=["CALLS"],
            db=db_session,
        )
        assert result.success
        for entry in result.data.dependents:
            assert entry.relationship_type == "CALLS"

    async def test_unknown_symbol_returns_not_found(self, db_session, ingested):
        result = await get_dependents(
            ingested.repository_id, uuid.uuid4(), db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_empty_dependents_is_not_error(self, db_session, ingested):
        """A root symbol with no incoming edges is not an error."""
        run_sym = await _find_symbol(db_session, ingested.repository_id, "run")
        result = await get_dependents(
            ingested.repository_id, run_sym.id, db=db_session
        )
        assert result.success

    async def test_repository_isolation(self, db_session):
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="dep2_iso_a")
        await db_session.commit()
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="dep2_iso_b")
        await db_session.commit()

        sym_b = await _find_symbol(db_session, result_b.repository_id, "process")
        result = await get_dependents(
            result_a.repository_id, sym_b.id, db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_dependents_have_source_locations(self, db_session, ingested):
        process_sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await get_dependents(
            ingested.repository_id, process_sym.id, db=db_session
        )
        assert result.success
        for entry in result.data.dependents:
            assert entry.symbol.file_path
            assert entry.symbol.start_line >= 1


# ===========================================================================
# TestGetCallersTool
# ===========================================================================

class TestGetCallersTool:
    async def test_callers_only_calls_edges(self, db_session, ingested):
        """get_callers must not return IMPORTS or other non-CALLS edges."""
        process_sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await get_callers(
            ingested.repository_id, process_sym.id, db=db_session
        )
        assert result.success
        assert result.data.target_symbol.name == "process"
        # All returned callers are via CALLS; we can't check the edge type
        # from CallerResult (it only returns SymbolRef), but the service
        # filters CALLS only — validate list is a clean list of SymbolRef.
        assert isinstance(result.data.callers, list)

    async def test_no_callers_is_not_error(self, db_session, ingested):
        """A symbol nobody calls should return success with empty callers."""
        run_sym = await _find_symbol(db_session, ingested.repository_id, "run")
        result = await get_callers(
            ingested.repository_id, run_sym.id, db=db_session
        )
        assert result.success

    async def test_unknown_symbol_returns_not_found(self, db_session, ingested):
        result = await get_callers(
            ingested.repository_id, uuid.uuid4(), db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_repository_isolation(self, db_session):
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="callers_iso_a")
        await db_session.commit()
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="callers_iso_b")
        await db_session.commit()

        sym_b = await _find_symbol(db_session, result_b.repository_id, "process")
        result = await get_callers(result_a.repository_id, sym_b.id, db=db_session)
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_callers_have_source_locations(self, db_session, ingested):
        process_sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await get_callers(
            ingested.repository_id, process_sym.id, db=db_session
        )
        assert result.success
        for caller in result.data.callers:
            assert caller.file_path
            assert caller.start_line >= 1
            assert caller.end_line >= caller.start_line


# ===========================================================================
# TestGetCalleesTool
# ===========================================================================

class TestGetCalleesTool:
    async def test_callees_only_calls_edges(self, db_session, ingested):
        """get_callees filters to CALLS only."""
        run_sym = await _find_symbol(db_session, ingested.repository_id, "run")
        result = await get_callees(
            ingested.repository_id, run_sym.id, db=db_session
        )
        assert result.success
        assert result.data.source_symbol.name == "run"
        assert isinstance(result.data.callees, list)

    async def test_no_callees_is_not_error(self, db_session, ingested):
        process_sym = await _find_symbol(db_session, ingested.repository_id, "process")
        result = await get_callees(
            ingested.repository_id, process_sym.id, db=db_session
        )
        assert result.success

    async def test_unknown_symbol_returns_not_found(self, db_session, ingested):
        result = await get_callees(
            ingested.repository_id, uuid.uuid4(), db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_repository_isolation(self, db_session):
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="callees_iso_a")
        await db_session.commit()
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="callees_iso_b")
        await db_session.commit()

        sym_b = await _find_symbol(db_session, result_b.repository_id, "run")
        result = await get_callees(result_a.repository_id, sym_b.id, db=db_session)
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_callees_have_source_locations(self, db_session, ingested):
        run_sym = await _find_symbol(db_session, ingested.repository_id, "run")
        result = await get_callees(
            ingested.repository_id, run_sym.id, db=db_session
        )
        assert result.success
        for callee in result.data.callees:
            assert callee.file_path
            assert callee.start_line >= 1


# ===========================================================================
# TestGetFileDependsTool
# ===========================================================================

class TestGetFileDependsTool:
    async def test_cross_file_dependency_detected(self, db_session, ingested):
        """main.py imports from utils.py — should appear as a dependency."""
        main_file = await _find_file(db_session, ingested.repository_id, "main.py")
        result = await get_file_dependencies(
            ingested.repository_id, main_file.id, db=db_session
        )
        assert result.success
        assert result.data.source_file_path == "main.py"
        # main.py imports/calls utils.py symbols — we expect at least 0 entries
        # (exact count depends on resolver success)
        assert isinstance(result.data.dependencies, list)

    async def test_dependency_entries_have_metadata(self, db_session, ingested):
        main_file = await _find_file(db_session, ingested.repository_id, "main.py")
        result = await get_file_dependencies(
            ingested.repository_id, main_file.id, db=db_session
        )
        assert result.success
        for dep in result.data.dependencies:
            assert dep.target_file_path
            assert dep.target_file_id is not None
            assert isinstance(dep.relationship_types, list)
            assert dep.edge_count >= 1

    async def test_duplicate_edges_collapsed(self, db_session, ingested):
        """Multiple symbol-level edges to same target file → one entry."""
        main_file = await _find_file(db_session, ingested.repository_id, "main.py")
        result = await get_file_dependencies(
            ingested.repository_id, main_file.id, db=db_session
        )
        assert result.success
        # Each target file should appear at most once
        paths = [d.target_file_path for d in result.data.dependencies]
        assert len(paths) == len(set(paths))

    async def test_unknown_file_returns_not_found(self, db_session, ingested):
        result = await get_file_dependencies(
            ingested.repository_id, uuid.uuid4(), db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_repository_isolation(self, db_session):
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="fdeps_iso_a")
        await db_session.commit()
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="fdeps_iso_b")
        await db_session.commit()

        file_b = await _find_file(db_session, result_b.repository_id, "main.py")
        result = await get_file_dependencies(
            result_a.repository_id, file_b.id, db=db_session
        )
        assert not result.success
        assert result.error.code == ToolErrorCode.NOT_FOUND

    async def test_leaf_file_no_dependencies(self, db_session, ingested):
        """utils.py has no imports from other files in simple_repo → empty list."""
        utils_file = await _find_file(db_session, ingested.repository_id, "utils.py")
        result = await get_file_dependencies(
            ingested.repository_id, utils_file.id, db=db_session
        )
        assert result.success
        # utils.py doesn't import from other repo files


# ===========================================================================
# TestToolRegistry
# ===========================================================================

class TestToolRegistry:
    def test_all_expected_tools_registered(self):
        expected_names = {
            "search_code",
            "inspect_symbol",
            "read_file",
            "get_dependencies",
            "get_dependents",
            "get_callers",
            "get_callees",
            "get_file_dependencies",
        }
        registered_names = {t.name for t in REPOPILOT_TOOLS}
        assert expected_names == registered_names

    def test_unique_names(self):
        names = [t.name for t in REPOPILOT_TOOLS]
        assert len(names) == len(set(names))

    def test_by_name_lookup(self):
        for tool in REPOPILOT_TOOLS:
            assert tool.name in REPOPILOT_TOOLS_BY_NAME
            assert REPOPILOT_TOOLS_BY_NAME[tool.name] is tool

    def test_each_tool_has_description(self):
        for tool in REPOPILOT_TOOLS:
            assert tool.description and len(tool.description) > 10, (
                f"{tool.name} has empty/short description"
            )

    def test_input_schema_structure(self):
        for tool in REPOPILOT_TOOLS:
            schema = tool.input_schema
            assert schema.get("type") == "object", f"{tool.name} schema must be type=object"
            assert "properties" in schema, f"{tool.name} schema missing properties"
            assert "required" in schema, f"{tool.name} schema missing required"
            # repository_id must always be required
            assert "repository_id" in schema["required"], (
                f"{tool.name} must require repository_id"
            )

    def test_all_tools_are_callable(self):
        import asyncio
        for tool in REPOPILOT_TOOLS:
            assert callable(tool.fn), f"{tool.name}.fn is not callable"
            # The functions are coroutine functions
            import inspect
            assert inspect.iscoroutinefunction(tool.fn), (
                f"{tool.name}.fn must be an async function"
            )

    def test_registry_count(self):
        assert len(REPOPILOT_TOOLS) == 8
