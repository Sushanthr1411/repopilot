"""
get_callees — return symbols directly called BY the given symbol.

Filters to CALLS edges only.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.graph.builder import build_repository_graph
from app.services.graph.service import get_callees as _get_callees, get_symbol_node
from app.tools._graph_helpers import sym_ref
from app.tools.models import (
    CalleesResult,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

logger = logging.getLogger(__name__)


async def get_callees(
    repository_id: uuid.UUID,
    symbol_id: uuid.UUID,
    *,
    db: AsyncSession,
) -> ToolResult[CalleesResult]:
    """
    Return symbols directly called by symbol_id (outgoing CALLS edges).

    Args:
        repository_id: Scope to this repository.
        symbol_id:     Symbol to find callees of.
        db:            Open AsyncSession.

    Returns:
        ToolResult[CalleesResult].  callees is empty (not an error) when the
        symbol makes no resolvable calls within the repository.
    """
    try:
        graph = await build_repository_graph(repository_id, db)
    except Exception:
        logger.exception("get_callees: graph build failed")
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

    callee_nodes = _get_callees(graph, symbol_id)

    max_results = settings.tool_graph_max_results
    truncated = len(callee_nodes) > max_results
    callee_nodes = callee_nodes[:max_results]

    callees = [sym_ref(n) for n in callee_nodes]

    logger.debug(
        "get_callees(%s, %s) → %d callees (truncated=%s)",
        repository_id, symbol_id, len(callees), truncated,
    )

    return ToolResult(
        success=True,
        data=CalleesResult(
            repository_id=repository_id,
            source_symbol=sym_ref(source_node),
            callees=callees,
            returned=len(callees),
            truncated=truncated,
        ),
    )
