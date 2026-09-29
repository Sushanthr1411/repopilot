"""
get_file_dependencies — return file-level dependencies for a given file.

Symbol-level edges that cross a file boundary are collapsed: multiple symbol
pairs from file A to file B produce a single FileDependencyEntry with an
edge_count reflecting the total number of underlying symbol-level edges.

Self-references (both source and target in the same file) are excluded.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import File
from app.services.graph.builder import build_repository_graph
from app.services.graph.service import get_file_dependencies as _get_file_deps
from app.tools.models import (
    FileDependenciesResult,
    FileDependencyEntry,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

logger = logging.getLogger(__name__)


async def get_file_dependencies(
    repository_id: uuid.UUID,
    file_id: uuid.UUID,
    *,
    db: AsyncSession,
) -> ToolResult[FileDependenciesResult]:
    """
    Return file-level outgoing dependencies for a given file.

    Args:
        repository_id: Scope to this repository.
        file_id:       UUID of the source file.
        db:            Open AsyncSession.

    Returns:
        ToolResult[FileDependenciesResult].  dependencies is empty (not an
        error) when the file exists but makes no cross-file references.
    """
    # Verify the file belongs to this repository
    try:
        file_row = (
            await db.execute(
                select(File).where(
                    File.id == file_id,
                    File.repository_id == repository_id,
                )
            )
        ).scalar_one_or_none()
    except Exception:
        logger.exception("get_file_dependencies: file lookup failed")
        return ToolResult(
            success=False,
            error=ToolError(code=ToolErrorCode.TOOL_ERROR, message="database error"),
        )

    if file_row is None:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.NOT_FOUND,
                message=f"file {file_id} not found in repository {repository_id}",
            ),
        )

    try:
        graph = await build_repository_graph(repository_id, db)
    except Exception:
        logger.exception("get_file_dependencies: graph build failed")
        return ToolResult(
            success=False,
            error=ToolError(code=ToolErrorCode.TOOL_ERROR, message="failed to build graph"),
        )

    raw_deps = _get_file_deps(graph, file_id)

    max_results = settings.tool_graph_max_results
    truncated = len(raw_deps) > max_results
    raw_deps = raw_deps[:max_results]

    entries = [
        FileDependencyEntry(
            target_file_id=d.target_file_id,
            target_file_path=d.target_file_path,
            relationship_types=d.relationship_types,
            edge_count=d.edge_count,
        )
        for d in raw_deps
    ]

    logger.debug(
        "get_file_dependencies(%s, %s) → %d deps (truncated=%s)",
        repository_id, file_id, len(entries), truncated,
    )

    return ToolResult(
        success=True,
        data=FileDependenciesResult(
            repository_id=repository_id,
            file_id=file_id,
            source_file_path=file_row.path,
            dependencies=entries,
            returned=len(entries),
            truncated=truncated,
        ),
    )
