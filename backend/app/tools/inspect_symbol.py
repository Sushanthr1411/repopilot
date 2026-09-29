"""
inspect_symbol — retrieve detailed information about one named code symbol.

Lookup contract
---------------
Either symbol_id or qualified_name must be provided; both may be provided.
symbol_id takes precedence when both are given.

Repository isolation
--------------------
The symbol is validated against the given repository_id via a database join
(Symbol → File → repository_id).  A symbol_id that belongs to a different
repository is treated as NOT_FOUND for the requested repository.

Source code
-----------
The tool reads the symbol's source lines from disk using the repository's
local_path.  If the file cannot be read, source is set to None and the
result is still success=True — the structural metadata is always returned
when the symbol is found.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import File, Repository, Symbol
from app.tools.models import (
    SymbolDetail,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

logger = logging.getLogger(__name__)


def _read_source_lines(abs_path: Path, start_line: int, end_line: int) -> str | None:
    """Read lines [start_line, end_line] (1-indexed, inclusive) from a file."""
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        return "\n".join(lines[start_idx:end_idx])
    except OSError:
        return None


async def inspect_symbol(
    repository_id: uuid.UUID,
    symbol_id: uuid.UUID | None = None,
    qualified_name: str | None = None,
    *,
    db: AsyncSession,
) -> ToolResult[SymbolDetail]:
    """
    Retrieve full detail for one symbol in the repository.

    Args:
        repository_id:  Repository scope; symbol must belong to this repository.
        symbol_id:      UUID of the symbol to inspect (takes precedence over
                        qualified_name when both are supplied).
        qualified_name: Fully-qualified name (e.g. "utils.process"); used when
                        symbol_id is None.  If multiple symbols share the same
                        qualified_name, the first found is returned.
        db:             Open AsyncSession.

    Returns:
        ToolResult[SymbolDetail].  success=False when no identifying argument
        is provided or the symbol is not found in this repository.
    """
    if symbol_id is None and qualified_name is None:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.INVALID_INPUT,
                message="at least one of symbol_id or qualified_name is required",
            ),
        )

    # Build query — always join through File to enforce repository isolation
    base = (
        select(Symbol, File, Repository)
        .join(File, Symbol.file_id == File.id)
        .join(Repository, File.repository_id == Repository.id)
        .where(File.repository_id == repository_id)
    )

    if symbol_id is not None:
        stmt = base.where(Symbol.id == symbol_id).limit(1)
        try:
            row = (await db.execute(stmt)).first()
        except Exception:
            logger.exception("inspect_symbol: DB query failed")
            return ToolResult(
                success=False,
                error=ToolError(code=ToolErrorCode.TOOL_ERROR, message="database error"),
            )
        if row is None:
            return ToolResult(
                success=False,
                error=ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message=f"symbol {symbol_id} not found in repository {repository_id}",
                ),
            )
        sym, file, repo = row
    else:
        # Fetch all matches — detect ambiguity before returning
        qname_stmt = base.where(Symbol.qualified_name == qualified_name)
        try:
            rows = (await db.execute(qname_stmt)).all()
        except Exception:
            logger.exception("inspect_symbol: DB query failed")
            return ToolResult(
                success=False,
                error=ToolError(code=ToolErrorCode.TOOL_ERROR, message="database error"),
            )
        if not rows:
            return ToolResult(
                success=False,
                error=ToolError(
                    code=ToolErrorCode.NOT_FOUND,
                    message=f"symbol {repr(qualified_name)} not found in repository {repository_id}",
                ),
            )
        if len(rows) > 1:
            candidates = [
                f"{r[0].qualified_name} ({r[0].symbol_type}) in {r[1].path}:{r[0].start_line}"
                for r in rows
            ]
            return ToolResult(
                success=False,
                error=ToolError(
                    code=ToolErrorCode.AMBIGUOUS_SYMBOL,
                    message=(
                        f"qualified_name {repr(qualified_name)} matches {len(rows)} symbols; "
                        f"use symbol_id for a unique lookup. Candidates: "
                        + "; ".join(candidates)
                    ),
                ),
            )
        sym, file, repo = rows[0]

    # Read source from disk (non-fatal if unavailable)
    source: str | None = None
    if repo.local_path:
        abs_path = Path(repo.local_path) / file.path
        source = _read_source_lines(abs_path, sym.start_line, sym.end_line)

    logger.debug(
        "inspect_symbol(%s) → %s (%s)", repository_id, sym.qualified_name, sym.symbol_type
    )

    return ToolResult(
        success=True,
        data=SymbolDetail(
            symbol_id=sym.id,
            name=sym.name,
            qualified_name=sym.qualified_name,
            symbol_type=sym.symbol_type,
            file_id=file.id,
            file_path=file.path,
            start_line=sym.start_line,
            end_line=sym.end_line,
            signature=sym.signature,
            docstring=sym.docstring,
            source=source,
        ),
    )
