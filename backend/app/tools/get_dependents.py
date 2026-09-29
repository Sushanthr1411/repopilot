"""
get_dependents — return direct incoming dependents for a symbol.

Returns symbols that depend on the given symbol (incoming graph edges).
Direction: dependent ──[rel_type]──► target_symbol
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.graph.builder import build_repository_graph
from app.services.graph.service import get_dependents_with_edges, get_symbol_node
from app.tools._graph_helpers import sym_ref
from app.tools.models import (
    DependencyEntry,
    DependentsResult,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

logger = logging.getLogger(__name__)


async def get_dependents(
    repository_id: uuid.UUID,
    symbol_id: uuid.UUID,
    relationship_types: list[str] | None = None,
    *,
    db: AsyncSession,
) -> ToolResult[DependentsResult]:
    """
    Return direct incoming dependents for a symbol.

    Args:
        repository_id:      Scope to this repository.
        symbol_id:          Symbol whose dependents to retrieve.
        relationship_types: When given, only edges of these types are returned.
                            None = all types.
        db:                 Open AsyncSession.

    Returns:
        ToolResult[DependentsResult].  dependents is empty (not an error)
        when the symbol exists but nothing depends on it.
    """
    try:
        graph = await build_repository_graph(repository_id, db)
    except Exception:
        logger.exception("get_dependents: graph build failed")
        return ToolResult(
            success=False,
            error=ToolError(code=ToolErrorCode.TOOL_ERROR, message="failed to build graph"),
        )

    target_node = get_symbol_node(graph, symbol_id)
    if target_node is None:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.NOT_FOUND,
                message=f"symbol {symbol_id} not found in repository {repository_id}",
            ),
        )

    pairs = get_dependents_with_edges(graph, symbol_id, relationship_types)

    max_results = settings.tool_graph_max_results
    truncated = len(pairs) > max_results
    pairs = pairs[:max_results]

    entries = [
        DependencyEntry(
            relationship_type=edge.relationship_type,
            confidence=edge.confidence,
            symbol=sym_ref(node),
        )
        for node, edge in pairs
    ]

    logger.debug(
        "get_dependents(%s, %s) → %d entries (truncated=%s)",
        repository_id, symbol_id, len(entries), truncated,
    )

    return ToolResult(
        success=True,
        data=DependentsResult(
            repository_id=repository_id,
            target_symbol=sym_ref(target_node),
            dependents=entries,
            returned=len(entries),
            truncated=truncated,
        ),
    )
