"""
Manual verification script for Step 6 — Code Chunking & Semantic Indexing.

Usage (from the backend/ directory):
    uv run python scripts/verify_search.py

What this demonstrates
----------------------
1.  Ingest the simple_repo test fixture into an in-memory SQLite database.
2.  Index the repository (chunk → embed → store in ephemeral ChromaDB).
3.  Search for "process list of items" and print file paths + line ranges.
4.  Show repository isolation: two ingestions, query only returns repo A results.
5.  Show re-indexing: repeated index_repository() does not produce duplicates.

The embedding model is loaded from settings (EMBEDDING_MODEL env var or
the default all-MiniLM-L6-v2).  The first run downloads the model (~80 MB);
subsequent runs use the local cache (~/.cache/huggingface/).

Exit code 0 = success.  Non-zero = failure.
"""

import asyncio
import sys
from pathlib import Path

# Make sure the backend package is importable when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base
import app.db.models  # noqa: F401 — register models

from app.services.ingestion import ingest_repository
from app.services.search import index_repository, search_repository
from app.services.search.embeddings import SentenceTransformerProvider
from app.services.search.vector_store import ChromaVectorStore
from app.core.config import settings

SIMPLE_REPO = Path(__file__).parent.parent / "tests" / "fixtures" / "ingestion" / "simple_repo"


async def main() -> None:
    # ---------- in-memory SQLite + ephemeral Chroma for demo ----------
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession,
                                  expire_on_commit=False, autoflush=True)

    print(f"Loading embedding model: {settings.embedding_model!r}")
    try:
        provider = SentenceTransformerProvider(settings.embedding_model)
        _ = provider.embed_query("warmup")  # triggers lazy load
        print("Model loaded.\n")
    except (OSError, ImportError, Exception) as exc:
        # Windows Application Control policy may block PyTorch DLLs (same
        # policy that blocked SQLAlchemy Cython DLLs — same environment).
        print(f"WARNING: Could not load SentenceTransformer: {exc}")
        print("Falling back to FakeEmbeddingProvider (deterministic hash vectors).")
        print("Semantic relevance ordering will be hash-based, not semantic.\n")
        from app.services.search.embeddings import FakeEmbeddingProvider  # noqa: PLC0415
        provider = FakeEmbeddingProvider(dim=384)  # same dim as all-MiniLM-L6-v2

    store = ChromaVectorStore.ephemeral(collection_name="verify_demo")

    async with factory() as db:
        # ----------------------------------------------------------------
        # 1. Ingest
        # ----------------------------------------------------------------
        print("1. Ingesting simple_repo...")
        ingestion = await ingest_repository(db, SIMPLE_REPO)
        await db.commit()
        print(f"   {ingestion.total_symbols} symbols | {ingestion.total_files} files")

        # ----------------------------------------------------------------
        # 2. Index
        # ----------------------------------------------------------------
        print("\n2. Indexing repository...")
        stats = await index_repository(ingestion.repository_id, db, provider, store)
        await db.commit()
        print(f"   {stats.chunks_created} chunks created")

        # ----------------------------------------------------------------
        # 3. Search
        # ----------------------------------------------------------------
        queries = [
            "process list of items",
            "greeting user name",
            "format output string",
        ]
        for query in queries:
            print(f"\n3. Search: {query!r}")
            results = await search_repository(
                ingestion.repository_id, query, top_k=3,
                db=db, embedding_provider=provider, vector_store=store,
            )
            if not results:
                print("   (no results)")
            for r in results:
                loc = f"{r.file_path}:{r.start_line}-{r.end_line}"
                sym = r.qualified_name or "(module-level)"
                print(f"   [{r.distance:.4f}] {loc} — {sym}")
                print(f"         {r.content[:80].strip()!r}")

        # ----------------------------------------------------------------
        # 4. Repository isolation
        # ----------------------------------------------------------------
        print("\n4. Testing repository isolation...")
        ingestion_b = await ingest_repository(db, SIMPLE_REPO, name="repo_b")
        await db.commit()
        stats_b = await index_repository(ingestion_b.repository_id, db, provider, store)
        await db.commit()
        print(f"   Repo B indexed: {stats_b.chunks_created} chunks")

        # Search repo A; results must all belong to repo A
        results_a = await search_repository(
            ingestion.repository_id, "process", top_k=20,
            db=db, embedding_provider=provider, vector_store=store,
        )
        cross = [r for r in results_a if r.repository_id != ingestion.repository_id]
        if cross:
            print(f"   FAIL: {len(cross)} cross-repository results found!")
            sys.exit(1)
        print(f"   PASS: all {len(results_a)} results belong to repo A")

        # ----------------------------------------------------------------
        # 5. Re-indexing
        # ----------------------------------------------------------------
        print("\n5. Testing re-indexing (no duplicates)...")
        stats_reindex = await index_repository(
            ingestion.repository_id, db, provider, store
        )
        await db.commit()
        if stats_reindex.chunks_created != stats.chunks_created:
            print(
                f"   FAIL: chunk count changed from {stats.chunks_created} "
                f"to {stats_reindex.chunks_created}"
            )
            sys.exit(1)
        ids_after = store.get_ids_for_repository(str(ingestion.repository_id))
        if len(ids_after) != stats_reindex.chunks_created:
            print(
                f"   FAIL: Chroma has {len(ids_after)} vectors but DB has "
                f"{stats_reindex.chunks_created} chunks"
            )
            sys.exit(1)
        print(
            f"   PASS: {stats_reindex.chunks_created} chunks after re-index "
            f"(no duplicates, deleted {stats_reindex.chunks_deleted} old)"
        )

    print("\n✓ All verification steps passed.")


if __name__ == "__main__":
    asyncio.run(main())
