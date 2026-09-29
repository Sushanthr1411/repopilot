"""
Repository indexing service.

index_repository() pipeline
----------------------------
1.  Load repository metadata + files + symbols from PostgreSQL.
2.  For each file, read source from disk.
3.  Generate Chunk objects (chunker.chunk_file).
4.  Embed all chunk contents in one batched call.
5.  Delete existing CodeChunk rows for the repository (PostgreSQL).
6.  Delete existing vectors for the repository (ChromaDB).
7.  Insert new CodeChunk rows.
8.  Upsert embeddings + metadata into ChromaDB.
9.  Return IndexStats.

Consistency strategy
--------------------
Embedding is performed BEFORE deleting existing data so that if embedding
fails the old indexed data remains intact.  Steps 5-8 may leave the two
stores temporarily inconsistent if a late failure occurs; re-running
index_repository() is always safe and will produce a consistent state.

PostgreSQL and ChromaDB do NOT share an ACID transaction.  This is an
accepted trade-off: the metadata stays consistent within each store, and
the pair becomes consistent after a successful run.

Re-indexing
-----------
Calling index_repository() on an already-indexed repository is safe.
Old chunks are deleted (DB + Chroma) and replaced with fresh ones using
new UUIDs.  Deterministic IDs are guaranteed by: str(CodeChunk.id).

Caller note
-----------
The caller must commit the db session after a successful return.
On any raised exception the session should be rolled back by the caller.
"""

import logging
import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CodeChunk, File, Repository, Symbol
from app.services.search.chunker import chunk_file
from app.services.search.embeddings import EmbeddingProvider
from app.services.search.models import Chunk, IndexStats, SymbolInfo
from app.services.search.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


def _chunk_to_metadata(chunk: Chunk) -> dict:
    """Convert a Chunk to a Chroma-compatible metadata dict (no None values)."""
    return {
        "repository_id": str(chunk.repository_id),
        "file_id": str(chunk.file_id),
        "chunk_id": str(chunk.chunk_id),
        "file_path": chunk.file_path,
        "symbol_id": str(chunk.symbol_id) if chunk.symbol_id else "",
        "symbol_name": chunk.symbol_name or "",
        "qualified_name": chunk.qualified_name or "",
        "symbol_type": chunk.symbol_type or "",
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }


async def index_repository(
    repository_id: uuid.UUID,
    db: AsyncSession,
    embedding_provider: EmbeddingProvider,
    vector_store: ChromaVectorStore,
    *,
    max_chunk_lines: int = 80,
    overlap_lines: int = 5,
) -> IndexStats:
    """
    Index one repository: chunk → embed → persist.

    Args:
        repository_id:      UUID of an already-ingested repository.
        db:                 Open AsyncSession; caller owns the transaction.
        embedding_provider: Provides embed_documents() / embed_query().
        vector_store:       Wraps ChromaDB collection.
        max_chunk_lines:    Lines-per-chunk threshold (oversized = split).
        overlap_lines:      Overlap for split sub-chunks.

    Returns:
        IndexStats describing what was created / deleted.

    Raises:
        ValueError:  repository_id not found in the database.
        Exception:   Re-raised on embedding or vector store failure.
    """
    # ------------------------------------------------------------------ #
    # 1. Load repository record                                           #
    # ------------------------------------------------------------------ #
    repo = await db.get(Repository, repository_id)
    if repo is None:
        raise ValueError(f"Repository {repository_id} not found")
    if not repo.local_path:
        raise ValueError(f"Repository {repository_id} has no local_path; cannot read source files")

    repo_root = Path(repo.local_path)

    # ------------------------------------------------------------------ #
    # 2. Load files + symbols                                             #
    # ------------------------------------------------------------------ #
    files_result = await db.execute(
        select(File).where(File.repository_id == repository_id)
    )
    files = files_result.scalars().all()

    syms_result = await db.execute(
        select(Symbol)
        .join(File, Symbol.file_id == File.id)
        .where(File.repository_id == repository_id)
    )
    all_symbols = syms_result.scalars().all()

    # Group symbols by file_id
    syms_by_file: dict[uuid.UUID, list[SymbolInfo]] = {}
    for sym in all_symbols:
        info = SymbolInfo(
            symbol_id=sym.id,
            name=sym.name,
            qualified_name=sym.qualified_name,
            symbol_type=sym.symbol_type,
            start_line=sym.start_line,
            end_line=sym.end_line,
        )
        syms_by_file.setdefault(sym.file_id, []).append(info)

    # ------------------------------------------------------------------ #
    # 3. Generate chunks (in memory)                                      #
    # ------------------------------------------------------------------ #
    all_chunks: list[Chunk] = []
    files_skipped = 0

    for file_rec in files:
        file_path = repo_root / file_rec.path
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            files_skipped += 1
            continue

        file_symbols = syms_by_file.get(file_rec.id, [])
        file_chunks = chunk_file(
            content,
            file_rec.id,
            repository_id,
            file_rec.path,
            file_symbols,
            max_chunk_lines=max_chunk_lines,
            overlap_lines=overlap_lines,
        )
        all_chunks.extend(file_chunks)

    logger.info(
        "Repository %s: generated %d chunks from %d files (%d skipped)",
        repository_id, len(all_chunks), len(files), files_skipped,
    )

    # ------------------------------------------------------------------ #
    # 4. Embed all chunks (batched, before touching any stored data)      #
    # ------------------------------------------------------------------ #
    texts = [c.content for c in all_chunks]
    if texts:
        logger.info("Embedding %d chunks...", len(texts))
        embeddings = embedding_provider.embed_documents(texts)
    else:
        embeddings = []

    # ------------------------------------------------------------------ #
    # 5. Count old chunks (for stats) then delete them from DB            #
    # ------------------------------------------------------------------ #
    old_ids_result = await db.execute(
        select(CodeChunk.id).where(CodeChunk.repository_id == repository_id)
    )
    old_db_ids = [row[0] for row in old_ids_result.all()]
    chunks_deleted = len(old_db_ids)

    if old_db_ids:
        await db.execute(
            delete(CodeChunk).where(CodeChunk.repository_id == repository_id)
        )
        logger.debug("Deleted %d old CodeChunk rows", chunks_deleted)

    # ------------------------------------------------------------------ #
    # 6. Delete old vectors from ChromaDB                                 #
    # ------------------------------------------------------------------ #
    old_chroma_ids = vector_store.get_ids_for_repository(str(repository_id))
    if old_chroma_ids:
        vector_store.delete_by_ids(old_chroma_ids)
        logger.debug("Deleted %d old Chroma vectors", len(old_chroma_ids))

    # ------------------------------------------------------------------ #
    # 7. Persist new CodeChunk rows                                        #
    # ------------------------------------------------------------------ #
    for chunk in all_chunks:
        db.add(CodeChunk(
            id=chunk.chunk_id,
            repository_id=chunk.repository_id,
            file_id=chunk.file_id,
            symbol_id=chunk.symbol_id,
            content=chunk.content,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            content_hash=chunk.content_hash,
        ))

    # ------------------------------------------------------------------ #
    # 8. Upsert into ChromaDB                                              #
    # ------------------------------------------------------------------ #
    if all_chunks and embeddings:
        ids = [str(c.chunk_id) for c in all_chunks]
        docs = [c.content for c in all_chunks]
        metas = [_chunk_to_metadata(c) for c in all_chunks]
        vector_store.upsert(ids, embeddings, docs, metas)
        logger.info("Upserted %d vectors into ChromaDB", len(all_chunks))

    return IndexStats(
        repository_id=repository_id,
        total_files=len(files),
        chunks_created=len(all_chunks),
        chunks_deleted=chunks_deleted,
        files_skipped=files_skipped,
    )
