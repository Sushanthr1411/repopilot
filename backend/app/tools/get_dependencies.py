"""
get_dependencies — return direct outgoing dependencies for a symbol.

Returns symbols that the given symbol depends on (outgoing graph edges).
Direction: source_symbol ──[rel_type]──► dependency

Repository isolation is enforced by build_repository_graph, which only loads
symbols and relationships belonging to the requested repository_id.  A
symbol_id from another repository will not appear in the graph and is
returned as NOT_FOUND.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.graph.builder import build_repository_graph
from app.services.graph.service import get_dependencies_with_edges, get_symbol_node
from app.tools._graph_helpers import sym_ref
from app.tools.models import (
    DependenciesResult,
    DependencyEntry,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

logger = logging.getLogger(__name__)


async def get_dependencies(
    repository_id: uuid.UUID,
    symbol_id: uuid.UUID,
    relationship_types: list[str] | None = None,
    *,
    db: AsyncSession,
) -> ToolResult[DependenciesResult]:
    """
    Return direct outgoing dependencies for a symbol.

    Args:
        repository_id:      Scope to this repository.
        symbol_id:          Symbol whose dependencies to retrieve.
        relationship_types: When given, only edges of these types are returned
                            (e.g. ["CALLS"] or ["IMPORTS"]).  None = all types.
        db:                 Open AsyncSession.

    Returns:
        ToolResult[DependenciesResult].  dependencies is empty (not an error)
        when the symbol exists but has no outgoing edges.
    """
    try:
        graph = await build_repository_graph(repository_id, db)
    except Exception:
        logger.exception("get_dependencies: graph build failed")
        return ToolResult(
            success=False,
            error=ToolError(code=ToolErrorCode.TOOL_ERROR, message="failed to build graph"),
        )

    source_node = get_symbol_node(graph, symbol_id)
    if source_node is None:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.NOT_FOUND,
                message=f"symbol {symbol_id} not found in repository {repository_id}",
            ),
        )

    pairs = get_dependencies_with_edges(graph, symbol_id, relationship_types)

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
        "get_dependencies(%s, %s) → %d entries (truncated=%s)",
        repository_id, symbol_id, len(entries), truncated,
    )

    return ToolResult(
        success=True,
        data=DependenciesResult(
            repository_id=repository_id,
            source_symbol=sym_ref(source_node),
            dependencies=entries,
            returned=len(entries),
            truncated=truncated,
        ),
    )
