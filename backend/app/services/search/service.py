"""
Semantic search service.

search_repository() pipeline
------------------------------
1.  Embed the query string (single call to the embedding provider).
2.  Query ChromaDB with a repository_id metadata filter.
3.  Convert each VectorResult into a typed SearchResult.

Repository isolation is applied at the vector-store query level
(not only in application code) via the ChromaDB `where` filter.

Score convention
----------------
Results are ordered by cosine distance ascending (closer = more relevant).
The field is named `distance` to accurately reflect that lower is better.
Distance range with cosine space: 0 (identical) to 2 (opposite).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.search.embeddings import EmbeddingProvider
from app.services.search.models import SearchResult
from app.services.search.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


async def search_repository(
    repository_id: uuid.UUID,
    query: str,
    top_k: int = 10,
    *,
    db: AsyncSession,  # reserved for future DB enrichment / filtering
    embedding_provider: EmbeddingProvider,
    vector_store: ChromaVectorStore,
) -> list[SearchResult]:
    """
    Semantic search over an indexed repository.

    Args:
        repository_id:      Scope results to this repository only.
        query:              Natural-language search string.
        top_k:              Maximum number of results to return.
        db:                 AsyncSession (currently unused; reserved for future
                            DB-enrichment pass to keep metadata fresh).
        embedding_provider: Provides embed_query().
        vector_store:       ChromaDB adapter to query.

    Returns:
        List of SearchResult sorted by distance ascending (best first).
        Empty list when no indexed chunks exist or the query matches nothing.
    """
    if top_k <= 0 or not query:
        return []

    query_embedding = embedding_provider.embed_query(query)

    vector_results = vector_store.query(
        query_embedding=query_embedding,
        repository_id=str(repository_id),
        top_k=top_k,
    )

    results: list[SearchResult] = []
    for vr in vector_results:
        meta = vr.metadata or {}
        symbol_id_str = meta.get("symbol_id", "")
        try:
            symbol_id = uuid.UUID(symbol_id_str) if symbol_id_str else None
        except ValueError:
            symbol_id = None

        try:
            file_id = uuid.UUID(meta.get("file_id", ""))
        except ValueError:
            file_id = uuid.UUID(int=0)  # fallback — should not happen

        results.append(SearchResult(
            chunk_id=uuid.UUID(vr.chunk_id),
            repository_id=repository_id,
            file_id=file_id,
            file_path=meta.get("file_path", ""),
            symbol_id=symbol_id,
            symbol_name=meta.get("symbol_name") or None,
            qualified_name=meta.get("qualified_name") or None,
            start_line=int(meta.get("start_line", 0)),
            end_line=int(meta.get("end_line", 0)),
            content=vr.content,
            distance=vr.distance,
        ))

    logger.debug(
        "search_repository(%s, %r) → %d results", repository_id, query, len(results)
    )
    return results
