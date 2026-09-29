"""
search_code — find relevant code chunks using natural language.

Calls the existing semantic search service from Step 6.
Repository isolation is enforced by the search service (Chroma metadata filter).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.search.embeddings import EmbeddingProvider
from app.services.search.service import search_repository
from app.services.search.vector_store import ChromaVectorStore
from app.tools.models import (
    CodeSearchMatch,
    SearchCodeResult,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

logger = logging.getLogger(__name__)


async def search_code(
    repository_id: uuid.UUID,
    query: str,
    top_k: int = 5,
    *,
    db: AsyncSession,
    embedding_provider: EmbeddingProvider,
    vector_store: ChromaVectorStore,
) -> ToolResult[SearchCodeResult]:
    """
    Semantic search over the indexed chunks of a repository.

    Args:
        repository_id:      Scope all results to this repository.
        query:              Natural-language description of the code to find.
        top_k:              Desired number of results (capped at
                            settings.tool_search_max_results).
        db:                 AsyncSession (passed through to search service).
        embedding_provider: Embedding provider for the query.
        vector_store:       ChromaDB store to query.

    Returns:
        ToolResult[SearchCodeResult].  success=False on invalid input or when
        the repository has no indexed chunks.
    """
    if not query or not query.strip():
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.INVALID_INPUT,
                message="query must not be empty",
            ),
        )
    if top_k <= 0:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.INVALID_INPUT,
                message="top_k must be a positive integer",
            ),
        )

    max_k = settings.tool_search_max_results
    truncated = top_k > max_k
    effective_k = min(top_k, max_k)

    try:
        raw_results = await search_repository(
            repository_id,
            query,
            top_k=effective_k,
            db=db,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
    except Exception:
        logger.exception("search_code: search_repository raised unexpectedly")
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.TOOL_ERROR,
                message="internal error during semantic search",
            ),
        )

    matches = [
        CodeSearchMatch(
            chunk_id=r.chunk_id,
            file_id=r.file_id,
            file_path=r.file_path,
            symbol_id=r.symbol_id,
            symbol_name=r.symbol_name,
            qualified_name=r.qualified_name,
            start_line=r.start_line,
            end_line=r.end_line,
            content=r.content,
            distance=r.distance,
        )
        for r in raw_results
    ]

    logger.debug(
        "search_code(%s, %r) → %d results (truncated=%s)",
        repository_id, query, len(matches), truncated,
    )

    return ToolResult(
        success=True,
        data=SearchCodeResult(
            repository_id=repository_id,
            query=query,
            results=matches,
            returned=len(matches),
            truncated=truncated,
        ),
    )
