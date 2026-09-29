"""
get_callers — return symbols that directly CALL the target symbol.

Filters to CALLS edges only; IMPORTS and other relationship types are excluded.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.graph.builder import build_repository_graph
from app.services.graph.service import get_callers as _get_callers, get_symbol_node
from app.tools._graph_helpers import sym_ref
from app.tools.models import (
    CallersResult,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

logger = logging.getLogger(__name__)


async def get_callers(
    repository_id: uuid.UUID,
    symbol_id: uuid.UUID,
    *,
    db: AsyncSession,
) -> ToolResult[CallersResult]:
    """
    Return symbols with a direct CALLS edge pointing to symbol_id.

    Args:
        repository_id: Scope to this repository.
        symbol_id:     Symbol to find callers of.
        db:            Open AsyncSession.

    Returns:
        ToolResult[CallersResult].  callers is empty (not an error) when
        nothing calls this symbol within the repository.
    """
    try:
        graph = await build_repository_graph(repository_id, db)
    except Exception:
        logger.exception("get_callers: graph build failed")
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

    caller_nodes = _get_callers(graph, symbol_id)

    max_results = settings.tool_graph_max_results
    truncated = len(caller_nodes) > max_results
    caller_nodes = caller_nodes[:max_results]

    callers = [sym_ref(n) for n in caller_nodes]

    logger.debug(
        "get_callers(%s, %s) → %d callers (truncated=%s)",
        repository_id, symbol_id, len(callers), truncated,
    )

    return ToolResult(
        success=True,
        data=CallersResult(
            repository_id=repository_id,
            target_symbol=sym_ref(target_node),
            callers=callers,
            returned=len(callers),
            truncated=truncated,
        ),
    )
