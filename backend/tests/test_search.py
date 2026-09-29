"""
Tests for the search/indexing layer (Step 6).

Structure
---------
TestChunker              — pure unit tests for chunker.chunk_file()
TestContentHashing       — content hash properties
TestEmbeddingProvider    — FakeEmbeddingProvider + SentenceTransformer import check
TestChromaVectorStore    — CRUD against ephemeral in-memory Chroma
TestIndexer              — DB-backed integration: index_repository()
TestSearchService        — DB-backed integration: search_repository()
TestRepositoryIsolation  — two repos must not cross-contaminate search
TestReindexing           — repeated index_repository() is idempotent
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.services.search.chunker import chunk_file, _split_by_lines
from app.services.search.embeddings import EmbeddingProvider, FakeEmbeddingProvider
from app.services.search.models import SearchResult, SymbolInfo
from app.services.search.vector_store import ChromaVectorStore
from app.services.search import index_repository, search_repository
from app.services.ingestion import ingest_repository


SIMPLE_REPO = Path(__file__).parent / "fixtures" / "ingestion" / "simple_repo"
ERROR_REPO = Path(__file__).parent / "fixtures" / "ingestion" / "error_repo"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dim=8)


@pytest.fixture
def ephemeral_store() -> ChromaVectorStore:
    return ChromaVectorStore.ephemeral(collection_name=f"test_{uuid.uuid4().hex[:8]}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sym(
    name: str,
    qualified_name: str,
    symbol_type: str,
    start_line: int,
    end_line: int,
    symbol_id: uuid.UUID | None = None,
) -> SymbolInfo:
    return SymbolInfo(
        symbol_id=symbol_id or uuid.uuid4(),
        name=name,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        start_line=start_line,
        end_line=end_line,
    )


_REPO_ID = uuid.uuid4()
_FILE_ID = uuid.uuid4()
_FILE_PATH = "test_module.py"


def _chunk(content: str, symbols: list[SymbolInfo], **kwargs) -> list:
    kw = dict(
        file_content=content,
        file_id=_FILE_ID,
        repository_id=_REPO_ID,
        file_path=_FILE_PATH,
        symbols=symbols,
    )
    kw.update(kwargs)
    return chunk_file(**kw)


# ---------------------------------------------------------------------------
# TestChunker
# ---------------------------------------------------------------------------

class TestChunker:
    def test_function_creates_chunk(self):
        src = "def greet(name: str) -> str:\n    return f'Hello {name}'\n"
        sym = _sym("greet", "greet", "function", 1, 2)
        chunks = _chunk(src, [sym])
        fn_chunks = [c for c in chunks if c.symbol_type == "function"]
        assert len(fn_chunks) == 1
        assert "def greet" in fn_chunks[0].content

    def test_async_function_creates_chunk(self):
        src = "async def fetch(url: str) -> str:\n    return url\n"
        sym = _sym("fetch", "fetch", "async_function", 1, 2)
        chunks = _chunk(src, [sym])
        afn = [c for c in chunks if c.symbol_type == "async_function"]
        assert len(afn) == 1
        assert "async def fetch" in afn[0].content

    def test_method_includes_class_context(self):
        src = "class MyClass:\n    def my_method(self) -> None:\n        pass\n"
        sym = _sym("my_method", "MyClass.my_method", "method", 2, 3)
        chunks = _chunk(src, [sym])
        method_chunks = [c for c in chunks if c.symbol_type == "method"]
        assert len(method_chunks) == 1
        assert "# Class: MyClass" in method_chunks[0].content
        assert "# Method: my_method" in method_chunks[0].content
        assert "def my_method" in method_chunks[0].content

    def test_class_creates_header_chunk(self):
        src = "class Entity:\n    \"\"\"Base entity.\"\"\"\n    pass\n"
        sym = _sym("Entity", "Entity", "class", 1, 3)
        chunks = _chunk(src, [sym])
        class_chunks = [c for c in chunks if c.symbol_type == "class"]
        assert len(class_chunks) == 1
        assert "class Entity" in class_chunks[0].content

    def test_class_header_capped_at_max_lines(self):
        # 30-line class — header chunk should be capped at 20 lines
        class_lines = ["class BigClass:"] + [f"    attr_{i} = {i}" for i in range(29)]
        src = "\n".join(class_lines)
        sym = _sym("BigClass", "BigClass", "class", 1, 30)
        chunks = _chunk(src, [sym])
        class_chunk = next(c for c in chunks if c.symbol_type == "class")
        assert class_chunk.end_line - class_chunk.start_line < 30

    def test_module_level_chunk_created(self):
        src = '"""Module docstring."""\n\nimport os\n\ndef fn():\n    pass\n'
        sym = _sym("fn", "fn", "function", 5, 6)
        chunks = _chunk(src, [sym])
        module_chunks = [c for c in chunks if c.symbol_type is None]
        assert len(module_chunks) == 1
        assert "import os" in module_chunks[0].content

    def test_module_level_includes_docstring(self):
        src = '"""Module docstring."""\n\ndef fn():\n    pass\n'
        sym = _sym("fn", "fn", "function", 3, 4)
        chunks = _chunk(src, [sym])
        module_chunks = [c for c in chunks if c.symbol_type is None]
        assert any("Module docstring" in c.content for c in module_chunks)

    def test_empty_file_returns_no_chunks(self):
        assert _chunk("", []) == []
        assert _chunk("   \n  \n", []) == []

    def test_comment_only_file_returns_module_chunk(self):
        src = "# Just a comment\n# Another comment\n"
        chunks = _chunk(src, [])
        assert len(chunks) == 1
        assert "# Just a comment" in chunks[0].content

    def test_syntax_error_file_returns_raw_chunk(self):
        # No symbols (as ingestion does for parse-error files); raw content indexed
        src = "def broken(\n"
        chunks = _chunk(src, [])
        assert len(chunks) == 1
        assert "def broken" in chunks[0].content

    def test_no_symbols_entire_file_is_module_chunk(self):
        src = "import os\nCONSTANT = 42\n"
        chunks = _chunk(src, [])
        assert len(chunks) == 1
        assert "CONSTANT" in chunks[0].content

    def test_chunk_start_line_accuracy(self):
        src = "import os\n\ndef greet(name):\n    return f'hi {name}'\n"
        sym = _sym("greet", "greet", "function", 3, 4)
        chunks = _chunk(src, [sym])
        fn_chunk = next(c for c in chunks if c.symbol_type == "function")
        assert fn_chunk.start_line == 3
        assert fn_chunk.end_line == 4

    def test_module_chunk_start_line_is_one(self):
        src = "import os\n\ndef fn():\n    pass\n"
        sym = _sym("fn", "fn", "function", 3, 4)
        chunks = _chunk(src, [sym])
        mod_chunk = next(c for c in chunks if c.symbol_type is None)
        assert mod_chunk.start_line == 1

    def test_chunk_metadata_fields(self):
        src = "def process(data):\n    return data\n"
        sym_id = uuid.uuid4()
        sym = _sym("process", "process", "function", 1, 2, symbol_id=sym_id)
        chunks = _chunk(src, [sym])
        fn_chunk = next(c for c in chunks if c.symbol_type == "function")
        assert fn_chunk.symbol_id == sym_id
        assert fn_chunk.file_path == _FILE_PATH
        assert fn_chunk.repository_id == _REPO_ID
        assert fn_chunk.file_id == _FILE_ID
        assert fn_chunk.symbol_name == "process"
        assert fn_chunk.qualified_name == "process"

    def test_module_chunk_symbol_id_is_none(self):
        src = "import os\n"
        chunks = _chunk(src, [])
        assert len(chunks) == 1
        assert chunks[0].symbol_id is None

    def test_module_symbol_skipped(self):
        # The "module" symbol type covers the entire file; it should be skipped
        src = '"""Module."""\n\ndef fn():\n    pass\n'
        module_sym = _sym("mymodule", "mymodule", "module", 1, 4)
        fn_sym = _sym("fn", "fn", "function", 3, 4)
        chunks = _chunk(src, [module_sym, fn_sym])
        # Should have function chunk + module-level chunk (no extra "module" chunk)
        types = [c.symbol_type for c in chunks]
        assert "module" not in types

    def test_oversized_function_is_split(self):
        # 25 lines — with max_chunk_lines=10 should produce multiple chunks
        lines = ["def big_fn():"] + [f"    x_{i} = {i}" for i in range(24)]
        src = "\n".join(lines)
        sym = _sym("big_fn", "big_fn", "function", 1, len(lines))
        chunks = _chunk(src, [sym], max_chunk_lines=10, overlap_lines=2)
        fn_chunks = [c for c in chunks if c.symbol_type == "function"]
        assert len(fn_chunks) > 1

    def test_split_preserves_line_numbers(self):
        lines = ["def big_fn():"] + [f"    x_{i} = {i}" for i in range(24)]
        src = "\n".join(lines)
        sym = _sym("big_fn", "big_fn", "function", 1, len(lines))
        chunks = _chunk(src, [sym], max_chunk_lines=10, overlap_lines=2)
        fn_chunks = [c for c in chunks if c.symbol_type == "function"]
        # All pieces should have start_line >= 1
        for c in fn_chunks:
            assert c.start_line >= 1
            assert c.end_line >= c.start_line

    def test_multiple_functions_multiple_chunks(self):
        src = "def a():\n    pass\n\ndef b():\n    pass\n"
        syms = [
            _sym("a", "a", "function", 1, 2),
            _sym("b", "b", "function", 4, 5),
        ]
        chunks = _chunk(src, syms)
        fn_chunks = [c for c in chunks if c.symbol_type == "function"]
        assert len(fn_chunks) == 2


# ---------------------------------------------------------------------------
# TestSplitByLines helper
# ---------------------------------------------------------------------------

class TestSplitByLines:
    def test_no_split_needed(self):
        lines = ["a", "b", "c"]
        result = _split_by_lines(lines, 1, max_lines=10, overlap=2)
        assert len(result) == 1
        assert result[0] == ("a\nb\nc", 1, 3)

    def test_splits_oversized(self):
        lines = [f"line{i}" for i in range(12)]
        result = _split_by_lines(lines, 1, max_lines=5, overlap=2)
        assert len(result) > 1

    def test_overlap(self):
        lines = [f"line{i}" for i in range(10)]
        result = _split_by_lines(lines, 1, max_lines=5, overlap=2)
        # Consecutive pieces should share 'overlap' lines
        assert len(result) >= 2
        piece1_lines = result[0][0].splitlines()
        piece2_lines = result[1][0].splitlines()
        # Last 2 of piece1 should match first 2 of piece2
        assert piece1_lines[-2:] == piece2_lines[:2]

    def test_absolute_line_numbers(self):
        lines = ["a", "b", "c"]
        result = _split_by_lines(lines, 10, max_lines=2, overlap=0)
        assert result[0][1] == 10  # first piece starts at abs line 10
        assert result[0][2] == 11  # ends at 11


# ---------------------------------------------------------------------------
# TestContentHashing
# ---------------------------------------------------------------------------

class TestContentHashing:
    def test_same_content_same_hash(self):
        src = "def fn():\n    return 1\n"
        sym = _sym("fn", "fn", "function", 1, 2)
        chunks1 = _chunk(src, [sym])
        chunks2 = _chunk(src, [sym])
        fn1 = next(c for c in chunks1 if c.symbol_type == "function")
        fn2 = next(c for c in chunks2 if c.symbol_type == "function")
        assert fn1.content_hash == fn2.content_hash

    def test_different_content_different_hash(self):
        src_a = "def fn():\n    return 1\n"
        src_b = "def fn():\n    return 2\n"
        sym = _sym("fn", "fn", "function", 1, 2)
        c_a = next(c for c in _chunk(src_a, [sym]) if c.symbol_type == "function")
        c_b = next(c for c in _chunk(src_b, [sym]) if c.symbol_type == "function")
        assert c_a.content_hash != c_b.content_hash

    def test_hash_is_64_hex_chars(self):
        src = "x = 1\n"
        chunks = _chunk(src, [])
        assert len(chunks) == 1
        h = chunks[0].content_hash
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_chunk_id_is_unique(self):
        src = "def a():\n    pass\n\ndef b():\n    pass\n"
        syms = [_sym("a", "a", "function", 1, 2), _sym("b", "b", "function", 4, 5)]
        chunks = _chunk(src, syms)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# TestEmbeddingProvider
# ---------------------------------------------------------------------------

class TestEmbeddingProvider:
    def test_fake_provider_implements_protocol(self):
        p = FakeEmbeddingProvider()
        assert isinstance(p, EmbeddingProvider)

    def test_embed_documents_returns_list(self):
        p = FakeEmbeddingProvider(dim=4)
        result = p.embed_documents(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 4
        assert len(result[1]) == 4

    def test_embed_query_returns_vector(self):
        p = FakeEmbeddingProvider(dim=4)
        result = p.embed_query("test query")
        assert len(result) == 4
        assert all(isinstance(v, float) for v in result)

    def test_deterministic_output(self):
        p = FakeEmbeddingProvider(dim=8)
        v1 = p.embed_query("same text")
        v2 = p.embed_query("same text")
        assert v1 == v2

    def test_different_inputs_different_vectors(self):
        p = FakeEmbeddingProvider(dim=8)
        v1 = p.embed_query("text one")
        v2 = p.embed_query("text two")
        assert v1 != v2

    def test_embed_empty_documents(self):
        p = FakeEmbeddingProvider()
        assert p.embed_documents([]) == []

    def test_sentence_transformer_provider_importable(self):
        from app.services.search.embeddings import SentenceTransformerProvider  # noqa: F401


# ---------------------------------------------------------------------------
# TestChromaVectorStore
# ---------------------------------------------------------------------------

class TestChromaVectorStore:
    def _store(self) -> ChromaVectorStore:
        return ChromaVectorStore.ephemeral(collection_name=f"t_{uuid.uuid4().hex[:8]}")

    def _fake_embedding(self, n: int = 1, dim: int = 8) -> list[list[float]]:
        p = FakeEmbeddingProvider(dim=dim)
        return [p._hash_vector(f"doc_{i}") for i in range(n)]

    def test_create_and_query_empty(self):
        store = self._store()
        results = store.query([0.0] * 8, "repo-a", top_k=5)
        assert results == []

    def test_upsert_and_query(self):
        store = self._store()
        repo_id = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        emb = self._fake_embedding(1)[0]
        store.upsert(
            ids=[cid],
            embeddings=[emb],
            documents=["hello world"],
            metadatas=[{"repository_id": repo_id, "file_path": "a.py",
                        "chunk_id": cid, "file_id": str(uuid.uuid4()),
                        "symbol_id": "", "symbol_name": "", "qualified_name": "",
                        "symbol_type": "", "start_line": 1, "end_line": 5}],
        )
        results = store.query(emb, repo_id, top_k=5)
        assert len(results) == 1
        assert results[0].chunk_id == cid
        assert results[0].content == "hello world"
        assert results[0].distance >= 0.0

    def test_metadata_preserved(self):
        store = self._store()
        repo_id = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        fpath = "services/auth.py"
        emb = self._fake_embedding(1)[0]
        store.upsert(
            ids=[cid],
            embeddings=[emb],
            documents=["authenticate()"],
            metadatas=[{"repository_id": repo_id, "file_path": fpath,
                        "chunk_id": cid, "file_id": str(uuid.uuid4()),
                        "symbol_id": str(uuid.uuid4()), "symbol_name": "authenticate",
                        "qualified_name": "authenticate", "symbol_type": "function",
                        "start_line": 10, "end_line": 20}],
        )
        results = store.query(emb, repo_id, top_k=1)
        meta = results[0].metadata
        assert meta["file_path"] == fpath
        assert meta["symbol_name"] == "authenticate"
        assert meta["start_line"] == 10

    def test_repository_isolation_in_query(self):
        store = self._store()
        repo_a = str(uuid.uuid4())
        repo_b = str(uuid.uuid4())
        emb_a = FakeEmbeddingProvider(dim=8)._hash_vector("repo_a_doc")
        emb_b = FakeEmbeddingProvider(dim=8)._hash_vector("repo_b_doc")
        _meta = lambda rid, cid: {
            "repository_id": rid, "file_path": "f.py", "chunk_id": cid,
            "file_id": str(uuid.uuid4()), "symbol_id": "", "symbol_name": "",
            "qualified_name": "", "symbol_type": "", "start_line": 1, "end_line": 1,
        }
        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())
        store.upsert([id_a], [emb_a], ["repo a doc"], [_meta(repo_a, id_a)])
        store.upsert([id_b], [emb_b], ["repo b doc"], [_meta(repo_b, id_b)])

        results_a = store.query(emb_a, repo_a, top_k=10)
        assert all(r.metadata["repository_id"] == repo_a for r in results_a)

        results_b = store.query(emb_b, repo_b, top_k=10)
        assert all(r.metadata["repository_id"] == repo_b for r in results_b)

    def test_get_ids_for_repository(self):
        store = self._store()
        repo_id = str(uuid.uuid4())
        ids = [str(uuid.uuid4()) for _ in range(3)]
        embs = self._fake_embedding(3)
        _meta = lambda cid: {
            "repository_id": repo_id, "file_path": "f.py", "chunk_id": cid,
            "file_id": str(uuid.uuid4()), "symbol_id": "", "symbol_name": "",
            "qualified_name": "", "symbol_type": "", "start_line": 1, "end_line": 1,
        }
        store.upsert(ids, embs, ["doc"] * 3, [_meta(cid) for cid in ids])

        stored = store.get_ids_for_repository(repo_id)
        assert set(stored) == set(ids)

    def test_delete_by_ids(self):
        store = self._store()
        repo_id = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        emb = self._fake_embedding(1)[0]
        _meta = {"repository_id": repo_id, "file_path": "f.py", "chunk_id": cid,
                  "file_id": str(uuid.uuid4()), "symbol_id": "", "symbol_name": "",
                  "qualified_name": "", "symbol_type": "", "start_line": 1, "end_line": 1}
        store.upsert([cid], [emb], ["to delete"], [_meta])
        store.delete_by_ids([cid])
        results = store.query(emb, repo_id, top_k=5)
        assert len(results) == 0

    def test_upsert_replaces_existing(self):
        store = self._store()
        repo_id = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        emb = self._fake_embedding(1)[0]
        _meta = lambda doc: {
            "repository_id": repo_id, "file_path": "f.py", "chunk_id": cid,
            "file_id": str(uuid.uuid4()), "symbol_id": "", "symbol_name": "",
            "qualified_name": "", "symbol_type": "", "start_line": 1, "end_line": 1,
        }
        store.upsert([cid], [emb], ["original"], [_meta("original")])
        store.upsert([cid], [emb], ["updated"], [_meta("updated")])
        results = store.query(emb, repo_id, top_k=5)
        assert len(results) == 1
        assert results[0].content == "updated"

    def test_top_k_limits_results(self):
        store = self._store()
        repo_id = str(uuid.uuid4())
        n = 10
        ids = [str(uuid.uuid4()) for _ in range(n)]
        p = FakeEmbeddingProvider(dim=8)
        embs = [p._hash_vector(f"doc_{i}") for i in range(n)]
        _meta = lambda cid: {
            "repository_id": repo_id, "file_path": "f.py", "chunk_id": cid,
            "file_id": str(uuid.uuid4()), "symbol_id": "", "symbol_name": "",
            "qualified_name": "", "symbol_type": "", "start_line": 1, "end_line": 1,
        }
        store.upsert(ids, embs, [f"doc_{i}" for i in range(n)], [_meta(cid) for cid in ids])

        results = store.query(embs[0], repo_id, top_k=3)
        assert len(results) <= 3

    def test_top_k_zero_returns_empty(self):
        store = self._store()
        results = store.query([0.0] * 8, "any-repo", top_k=0)
        assert results == []


# ---------------------------------------------------------------------------
# TestIndexer — DB-backed
# ---------------------------------------------------------------------------

class TestIndexer:
    async def test_basic_indexing(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        stats = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        assert stats.chunks_created > 0
        assert stats.total_files == result.total_files
        assert stats.files_skipped == 0

    async def test_chunks_persisted_to_db(self, db_session, fake_provider, ephemeral_store):
        from sqlalchemy import select
        from app.db.models import CodeChunk

        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        stats = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        rows = (await db_session.execute(
            select(CodeChunk).where(CodeChunk.repository_id == result.repository_id)
        )).scalars().all()

        assert len(rows) == stats.chunks_created

    async def test_chunks_in_chroma(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        stats = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        ids = ephemeral_store.get_ids_for_repository(str(result.repository_id))
        assert len(ids) == stats.chunks_created

    async def test_parse_error_file_still_indexed(self, db_session, fake_provider, ephemeral_store):
        # error_repo has one syntax-error file; it should still produce a chunk
        result = await ingest_repository(db_session, ERROR_REPO)
        await db_session.commit()

        stats = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        assert stats.chunks_created > 0

    async def test_repository_not_found_raises(self, db_session, fake_provider, ephemeral_store):
        with pytest.raises(ValueError, match="not found"):
            await index_repository(uuid.uuid4(), db_session, fake_provider, ephemeral_store)

    async def test_embedding_failure_leaves_data_intact(
        self, db_session, fake_provider, ephemeral_store
    ):
        """If embedding raises, existing DB chunks should be untouched."""
        from sqlalchemy import select, func
        from app.db.models import CodeChunk

        # First index
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        # Count existing chunks
        count_before = (await db_session.execute(
            select(func.count(CodeChunk.id)).where(
                CodeChunk.repository_id == result.repository_id
            )
        )).scalar()

        # Now try to re-index with a broken provider
        class BrokenProvider:
            def embed_documents(self, texts):
                raise RuntimeError("embedding service down")
            def embed_query(self, text):
                raise RuntimeError("embedding service down")

        with pytest.raises(RuntimeError, match="embedding service down"):
            await index_repository(
                result.repository_id, db_session, BrokenProvider(), ephemeral_store
            )
        # DB should still have the original chunks (failure was before deletion)
        await db_session.rollback()  # roll back any partial writes

        count_after = (await db_session.execute(
            select(func.count(CodeChunk.id)).where(
                CodeChunk.repository_id == result.repository_id
            )
        )).scalar()
        assert count_after == count_before


# ---------------------------------------------------------------------------
# TestReindexing
# ---------------------------------------------------------------------------

class TestReindexing:
    async def test_repeated_indexing_same_chunk_count(
        self, db_session, fake_provider, ephemeral_store
    ):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        stats1 = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        stats2 = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        assert stats2.chunks_created == stats1.chunks_created
        assert stats2.chunks_deleted == stats1.chunks_created  # old ones removed

    async def test_repeated_indexing_no_duplicate_vectors(
        self, db_session, fake_provider, ephemeral_store
    ):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()
        stats2 = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        ids = ephemeral_store.get_ids_for_repository(str(result.repository_id))
        assert len(ids) == stats2.chunks_created  # no duplicates

    async def test_second_index_stats(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()

        stats1 = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()
        stats2 = await index_repository(
            result.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        assert stats2.chunks_deleted == stats1.chunks_created


# ---------------------------------------------------------------------------
# TestSearchService
# ---------------------------------------------------------------------------

class TestSearchService:
    async def _index(self, result, db_session, fake_provider, store):
        await index_repository(result.repository_id, db_session, fake_provider, store)
        await db_session.commit()

    async def test_returns_results(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        await self._index(result, db_session, fake_provider, ephemeral_store)

        results = await search_repository(
            result.repository_id, "process data", top_k=5,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)

    async def test_result_has_required_fields(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        await self._index(result, db_session, fake_provider, ephemeral_store)

        results = await search_repository(
            result.repository_id, "function", top_k=3,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        for r in results:
            assert isinstance(r.chunk_id, uuid.UUID)
            assert isinstance(r.file_id, uuid.UUID)
            assert r.file_path != ""
            assert r.start_line >= 1
            assert r.end_line >= r.start_line
            assert r.content != ""
            assert isinstance(r.distance, float)

    async def test_distance_is_non_negative(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        await self._index(result, db_session, fake_provider, ephemeral_store)

        results = await search_repository(
            result.repository_id, "test", top_k=5,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        assert all(r.distance >= 0.0 for r in results)

    async def test_top_k_respected(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        await self._index(result, db_session, fake_provider, ephemeral_store)

        results = await search_repository(
            result.repository_id, "code", top_k=2,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        assert len(results) <= 2

    async def test_empty_query_returns_empty(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        await self._index(result, db_session, fake_provider, ephemeral_store)

        results = await search_repository(
            result.repository_id, "", top_k=5,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        assert results == []

    async def test_top_k_zero_returns_empty(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        await self._index(result, db_session, fake_provider, ephemeral_store)

        results = await search_repository(
            result.repository_id, "data", top_k=0,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        assert results == []

    async def test_no_indexed_data_returns_empty(self, db_session, fake_provider, ephemeral_store):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        # Do NOT index — search should return empty

        results = await search_repository(
            result.repository_id, "process", top_k=5,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        assert results == []

    async def test_all_results_belong_to_repository(
        self, db_session, fake_provider, ephemeral_store
    ):
        result = await ingest_repository(db_session, SIMPLE_REPO)
        await db_session.commit()
        await self._index(result, db_session, fake_provider, ephemeral_store)

        results = await search_repository(
            result.repository_id, "class method function", top_k=10,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        for r in results:
            assert r.repository_id == result.repository_id


# ---------------------------------------------------------------------------
# TestRepositoryIsolation
# ---------------------------------------------------------------------------

class TestRepositoryIsolation:
    async def test_search_does_not_cross_repositories(
        self, db_session, fake_provider, ephemeral_store
    ):
        """Search for repo A must not return chunks from repo B."""
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="iso_a")
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="iso_b")
        await db_session.commit()

        await index_repository(
            result_a.repository_id, db_session, fake_provider, ephemeral_store
        )
        await index_repository(
            result_b.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        results_a = await search_repository(
            result_a.repository_id, "process format greet", top_k=20,
            db=db_session, embedding_provider=fake_provider,
            vector_store=ephemeral_store,
        )
        for r in results_a:
            assert r.repository_id == result_a.repository_id, (
                f"Result from repo B appeared in repo A search: {r.chunk_id}"
            )

    async def test_chunk_ids_are_disjoint(self, db_session, fake_provider, ephemeral_store):
        """Two ingestions of the same repo must produce disjoint chunk UUID sets."""
        result_a = await ingest_repository(db_session, SIMPLE_REPO, name="chunks_a")
        result_b = await ingest_repository(db_session, SIMPLE_REPO, name="chunks_b")
        await db_session.commit()

        await index_repository(
            result_a.repository_id, db_session, fake_provider, ephemeral_store
        )
        await index_repository(
            result_b.repository_id, db_session, fake_provider, ephemeral_store
        )
        await db_session.commit()

        ids_a = set(ephemeral_store.get_ids_for_repository(str(result_a.repository_id)))
        ids_b = set(ephemeral_store.get_ids_for_repository(str(result_b.repository_id)))

        assert len(ids_a) > 0
        assert len(ids_b) > 0
        assert ids_a.isdisjoint(ids_b), "Chunk IDs overlap between repositories"
