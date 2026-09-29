"""
Search / semantic indexing layer for RepoPilot AI.

Public API
----------
index_repository(repository_id, db, embedding_provider, vector_store) -> IndexStats
    Chunk → embed → persist a repository.  Caller commits the db session.

search_repository(repository_id, query, top_k, *, db, embedding_provider, vector_store)
    -> list[SearchResult]
    Semantic search over an indexed repository.

Typical usage
-------------
    from app.services.search import index_repository, search_repository
    from app.services.search.embeddings import SentenceTransformerProvider
    from app.services.search.vector_store import ChromaVectorStore
    from app.core.config import settings

    provider = SentenceTransformerProvider(settings.embedding_model)
    store    = ChromaVectorStore.from_settings(settings)

    stats   = await index_repository(repo_id, db, provider, store)
    await db.commit()

    results = await search_repository(repo_id, "authenticate user", top_k=5,
                                       db=db, embedding_provider=provider,
                                       vector_store=store)
"""

from app.services.search.indexer import index_repository
from app.services.search.models import Chunk, IndexStats, SearchResult, SymbolInfo
from app.services.search.service import search_repository

__all__ = [
    "index_repository",
    "search_repository",
    "Chunk",
    "IndexStats",
    "SearchResult",
    "SymbolInfo",
]
