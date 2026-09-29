"""
API endpoint tests for RepoPilot AI.

Uses httpx.AsyncClient + ASGITransport to exercise FastAPI routes end-to-end
without a running server.  All external dependencies (embedding model,
vector store, LLM) are replaced with lightweight in-process fakes via
FastAPI's dependency_overrides mechanism.

No real LLM, Chroma, or sentence-transformers calls are made.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.deps import get_db, get_embedding_provider, get_llm_client, get_vector_store
from app.main import app
from app.services.agent.llm import LLMResponse
from app.services.search.embeddings import FakeEmbeddingProvider
from app.services.search.vector_store import ChromaVectorStore

# ---------------------------------------------------------------------------
# Fixture repository path
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"
SIMPLE_REPO = _FIXTURES / "simple_repo"


# ---------------------------------------------------------------------------
# Fake LLM client (no real LLM calls)
# ---------------------------------------------------------------------------

class _FakeDirectLLMClient:
    """Always returns a text answer without requesting any tool calls."""

    async def complete(self, messages, tools=None, max_tokens=None, temperature=None):
        return LLMResponse(
            content="This is a test answer from the fake LLM.",
            tool_calls=[],
            model="fake-model",
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def api_client(db_engine):
    """
    Async HTTP client backed by the FastAPI app with all infrastructure
    dependencies overridden for testing.

    - DB: in-memory SQLite from db_engine (function-scoped, fresh per test)
    - Embedding: FakeEmbeddingProvider (deterministic, no sentence-transformers)
    - Vector store: ephemeral in-memory ChromaDB collection
    - LLM: _FakeDirectLLMClient (no real API calls)
    """
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_db():
        async with factory() as session:
            yield session

    fake_embedding = FakeEmbeddingProvider(dim=8)
    fake_vector_store = ChromaVectorStore.ephemeral("test_api")
    fake_llm = _FakeDirectLLMClient()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_embedding_provider] = lambda: fake_embedding
    app.dependency_overrides[get_vector_store] = lambda: fake_vector_store
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def created_repo(api_client):
    """A repository registered via POST /api/v1/repositories (status=pending)."""
    r = await api_client.post(
        "/api/v1/repositories",
        json={"name": "simple-repo", "local_path": str(SIMPLE_REPO)},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
async def ingested_repo(api_client, created_repo):
    """A repository registered AND ingested (status=ready)."""
    repo_id = created_repo["id"]
    r = await api_client.post(f"/api/v1/repositories/{repo_id}/ingest")
    assert r.status_code == 200, r.text
    return created_repo


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    async def test_legacy_health(self, api_client):
        r = await api_client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    async def test_v1_health(self, api_client):
        r = await api_client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------

class TestCreateRepository:
    async def test_create_success(self, api_client):
        r = await api_client.post(
            "/api/v1/repositories",
            json={"name": "my-repo", "local_path": str(SIMPLE_REPO)},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "my-repo"
        assert data["status"] == "pending"
        assert data["file_count"] == 0
        assert data["symbol_count"] == 0
        assert "id" in data

    async def test_create_with_source_url(self, api_client):
        r = await api_client.post(
            "/api/v1/repositories",
            json={
                "name": "with-url",
                "local_path": str(SIMPLE_REPO),
                "source_url": "https://github.com/example/repo",
            },
        )
        assert r.status_code == 201
        assert r.json()["source_url"] == "https://github.com/example/repo"

    async def test_create_nonexistent_path(self, api_client):
        r = await api_client.post(
            "/api/v1/repositories",
            json={"name": "bad", "local_path": "/nonexistent/path/xyz"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "PATH_NOT_FOUND"

    async def test_create_file_path_rejected(self, api_client, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1")
        r = await api_client.post(
            "/api/v1/repositories",
            json={"name": "file-not-dir", "local_path": str(f)},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "PATH_NOT_DIRECTORY"

    async def test_create_empty_name_rejected(self, api_client):
        r = await api_client.post(
            "/api/v1/repositories",
            json={"name": "", "local_path": str(SIMPLE_REPO)},
        )
        assert r.status_code == 422  # Pydantic validation error


class TestGetRepository:
    async def test_get_success(self, api_client, created_repo):
        r = await api_client.get(f"/api/v1/repositories/{created_repo['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == created_repo["id"]
        assert data["name"] == created_repo["name"]

    async def test_get_not_found(self, api_client):
        r = await api_client.get(f"/api/v1/repositories/{uuid.uuid4()}")
        assert r.status_code == 404

    async def test_get_counts_after_ingest(self, api_client, ingested_repo):
        r = await api_client.get(f"/api/v1/repositories/{ingested_repo['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["file_count"] > 0
        assert data["symbol_count"] > 0
        assert data["status"] == "ready"


class TestIngest:
    async def test_ingest_success(self, api_client, created_repo):
        r = await api_client.post(f"/api/v1/repositories/{created_repo['id']}/ingest")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ready"
        assert data["total_files"] > 0
        assert data["total_symbols"] > 0
        assert data["repository_id"] == created_repo["id"]

    async def test_ingest_not_found(self, api_client):
        r = await api_client.post(f"/api/v1/repositories/{uuid.uuid4()}/ingest")
        assert r.status_code == 404

    async def test_ingest_twice_succeeds(self, api_client, ingested_repo):
        # Re-ingestion must work (clears + re-parses)
        r = await api_client.post(f"/api/v1/repositories/{ingested_repo['id']}/ingest")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    async def test_ingest_returns_parse_stats(self, api_client, created_repo):
        r = await api_client.post(f"/api/v1/repositories/{created_repo['id']}/ingest")
        data = r.json()
        assert "parsed_files" in data
        assert "files_with_errors" in data
        assert "total_relationships" in data


class TestIndex:
    async def test_index_success(self, api_client, ingested_repo):
        r = await api_client.post(f"/api/v1/repositories/{ingested_repo['id']}/index")
        assert r.status_code == 200
        data = r.json()
        assert data["repository_id"] == ingested_repo["id"]
        assert "chunks_created" in data

    async def test_index_not_ready(self, api_client, created_repo):
        r = await api_client.post(f"/api/v1/repositories/{created_repo['id']}/index")
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "NOT_READY"

    async def test_index_not_found(self, api_client):
        r = await api_client.post(f"/api/v1/repositories/{uuid.uuid4()}/index")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

class TestFiles:
    async def test_list_files(self, api_client, ingested_repo):
        r = await api_client.get(f"/api/v1/repositories/{ingested_repo['id']}/files")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        assert len(data["items"]) > 0
        assert data["limit"] == 50
        assert data["offset"] == 0

    async def test_list_files_pagination(self, api_client, ingested_repo):
        r = await api_client.get(
            f"/api/v1/repositories/{ingested_repo['id']}/files?limit=1&offset=0"
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 1
        assert data["limit"] == 1
        assert data["offset"] == 0

    async def test_list_files_repo_not_found(self, api_client):
        r = await api_client.get(f"/api/v1/repositories/{uuid.uuid4()}/files")
        assert r.status_code == 404

    async def test_get_file_content(self, api_client, ingested_repo):
        repo_id = ingested_repo["id"]
        files_r = await api_client.get(f"/api/v1/repositories/{repo_id}/files")
        file_id = files_r.json()["items"][0]["id"]

        r = await api_client.get(f"/api/v1/repositories/{repo_id}/files/{file_id}")
        assert r.status_code == 200
        data = r.json()
        assert "content" in data
        assert data["total_lines"] > 0
        assert len(data["content"]) > 0

    async def test_get_file_line_range(self, api_client, ingested_repo):
        repo_id = ingested_repo["id"]
        files_r = await api_client.get(f"/api/v1/repositories/{repo_id}/files")
        file_id = files_r.json()["items"][0]["id"]

        r = await api_client.get(
            f"/api/v1/repositories/{repo_id}/files/{file_id}?start_line=1&end_line=3"
        )
        assert r.status_code == 200
        content = r.json()["content"]
        # Should be at most 3 lines
        assert len(content.splitlines()) <= 3

    async def test_get_file_not_found(self, api_client, ingested_repo):
        r = await api_client.get(
            f"/api/v1/repositories/{ingested_repo['id']}/files/{uuid.uuid4()}"
        )
        assert r.status_code == 404

    async def test_file_belongs_to_other_repo(self, api_client, ingested_repo):
        # Create a second independent repo (not ingested, has no files)
        r2 = await api_client.post(
            "/api/v1/repositories",
            json={"name": "other-repo", "local_path": str(SIMPLE_REPO)},
        )
        assert r2.status_code == 201
        other_repo_id = r2.json()["id"]

        # Get a file that belongs to ingested_repo
        repo_id = ingested_repo["id"]
        files_r = await api_client.get(f"/api/v1/repositories/{repo_id}/files")
        file_id = files_r.json()["items"][0]["id"]

        # Accessing that file via the OTHER repo's ID must 404
        r = await api_client.get(f"/api/v1/repositories/{other_repo_id}/files/{file_id}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------

class TestSymbols:
    async def test_list_symbols(self, api_client, ingested_repo):
        r = await api_client.get(f"/api/v1/repositories/{ingested_repo['id']}/symbols")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        assert len(data["items"]) > 0

    async def test_list_symbols_filter_type(self, api_client, ingested_repo):
        r = await api_client.get(
            f"/api/v1/repositories/{ingested_repo['id']}/symbols?symbol_type=function"
        )
        assert r.status_code == 200
        data = r.json()
        for item in data["items"]:
            assert item["symbol_type"] == "function"

    async def test_list_symbols_filter_name(self, api_client, ingested_repo):
        # "run" is defined in simple_repo/main.py
        r = await api_client.get(
            f"/api/v1/repositories/{ingested_repo['id']}/symbols?name=run"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        for item in data["items"]:
            assert "run" in item["name"].lower()

    async def test_list_symbols_pagination(self, api_client, ingested_repo):
        r = await api_client.get(
            f"/api/v1/repositories/{ingested_repo['id']}/symbols?limit=2&offset=0"
        )
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 2

    async def test_list_symbols_repo_not_found(self, api_client):
        r = await api_client.get(f"/api/v1/repositories/{uuid.uuid4()}/symbols")
        assert r.status_code == 404

    async def test_get_symbol(self, api_client, ingested_repo):
        repo_id = ingested_repo["id"]
        syms_r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols")
        sym_id = syms_r.json()["items"][0]["id"]

        r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols/{sym_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == sym_id
        assert "file_path" in data
        assert "start_line" in data

    async def test_get_symbol_not_found(self, api_client, ingested_repo):
        r = await api_client.get(
            f"/api/v1/repositories/{ingested_repo['id']}/symbols/{uuid.uuid4()}"
        )
        assert r.status_code == 404

    async def test_symbol_has_file_path(self, api_client, ingested_repo):
        repo_id = ingested_repo["id"]
        r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols")
        for item in r.json()["items"]:
            assert "file_path" in item
            assert item["file_path"] != ""


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

class TestGraph:
    async def test_get_graph(self, api_client, ingested_repo):
        r = await api_client.get(f"/api/v1/repositories/{ingested_repo['id']}/graph")
        assert r.status_code == 200
        data = r.json()
        assert data["repository_id"] == ingested_repo["id"]
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        assert len(data["nodes"]) > 0

    async def test_get_graph_not_found(self, api_client):
        r = await api_client.get(f"/api/v1/repositories/{uuid.uuid4()}/graph")
        assert r.status_code == 404

    async def test_get_graph_empty_repo(self, api_client, created_repo):
        # Pending repo: no symbols → empty graph is valid
        r = await api_client.get(f"/api/v1/repositories/{created_repo['id']}/graph")
        assert r.status_code == 200
        data = r.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    async def test_get_symbol_callers(self, api_client, ingested_repo):
        repo_id = ingested_repo["id"]
        syms_r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols")
        sym_id = syms_r.json()["items"][0]["id"]

        r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols/{sym_id}/callers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_get_symbol_callees(self, api_client, ingested_repo):
        repo_id = ingested_repo["id"]
        syms_r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols")
        sym_id = syms_r.json()["items"][0]["id"]

        r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols/{sym_id}/callees")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_get_symbol_dependencies(self, api_client, ingested_repo):
        repo_id = ingested_repo["id"]
        syms_r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols")
        sym_id = syms_r.json()["items"][0]["id"]

        r = await api_client.get(
            f"/api/v1/repositories/{repo_id}/symbols/{sym_id}/dependencies"
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_get_symbol_dependents(self, api_client, ingested_repo):
        repo_id = ingested_repo["id"]
        syms_r = await api_client.get(f"/api/v1/repositories/{repo_id}/symbols")
        sym_id = syms_r.json()["items"][0]["id"]

        r = await api_client.get(
            f"/api/v1/repositories/{repo_id}/symbols/{sym_id}/dependents"
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_graph_callers_repo_not_found(self, api_client):
        r = await api_client.get(
            f"/api/v1/repositories/{uuid.uuid4()}/symbols/{uuid.uuid4()}/callers"
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    async def test_search_returns_response(self, api_client, ingested_repo):
        r = await api_client.post(
            f"/api/v1/repositories/{ingested_repo['id']}/search",
            json={"query": "function definition", "top_k": 5},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "function definition"
        assert isinstance(data["results"], list)

    async def test_search_repo_not_found(self, api_client):
        r = await api_client.post(
            f"/api/v1/repositories/{uuid.uuid4()}/search",
            json={"query": "test"},
        )
        assert r.status_code == 404

    async def test_search_top_k_validation(self, api_client, ingested_repo):
        r = await api_client.post(
            f"/api/v1/repositories/{ingested_repo['id']}/search",
            json={"query": "code", "top_k": 200},
        )
        assert r.status_code == 422  # top_k > 100 is invalid

    async def test_search_result_fields(self, api_client, ingested_repo):
        r = await api_client.post(
            f"/api/v1/repositories/{ingested_repo['id']}/search",
            json={"query": "run", "top_k": 3},
        )
        assert r.status_code == 200
        results = r.json()["results"]
        for item in results:
            assert "chunk_id" in item
            assert "file_path" in item
            assert "content" in item
            assert "distance" in item


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class TestAgent:
    async def test_ask_success(self, api_client, ingested_repo):
        r = await api_client.post(
            f"/api/v1/repositories/{ingested_repo['id']}/ask",
            json={"question": "What does this codebase do?"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "answer" in data
        assert data["answer"] != ""
        assert isinstance(data["sources"], list)
        assert isinstance(data["tools_used"], list)
        assert isinstance(data["iterations"], int)
        assert isinstance(data["truncated"], bool)

    async def test_ask_not_ready(self, api_client, created_repo):
        r = await api_client.post(
            f"/api/v1/repositories/{created_repo['id']}/ask",
            json={"question": "test"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "NOT_READY"

    async def test_ask_repo_not_found(self, api_client):
        r = await api_client.post(
            f"/api/v1/repositories/{uuid.uuid4()}/ask",
            json={"question": "test"},
        )
        assert r.status_code == 404

    async def test_ask_answer_is_string(self, api_client, ingested_repo):
        r = await api_client.post(
            f"/api/v1/repositories/{ingested_repo['id']}/ask",
            json={"question": "How is the code structured?"},
        )
        assert r.status_code == 200
        assert isinstance(r.json()["answer"], str)
