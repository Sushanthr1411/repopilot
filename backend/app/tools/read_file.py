"""
read_file — read source code from a repository file.

Security model
--------------
Three layers of path safety enforcement, applied in order:

1. Reject absolute paths immediately (path starts with a root separator).
2. Reject paths containing ".." components before any filesystem access.
3. After resolving the absolute path, verify it is inside the repository root
   using pathlib's relative_to() — handles OS-level symlink tricks.

Additionally the file must exist in the `files` table for the given repository.
This means a path that is on disk but was not part of the ingested repository
cannot be read — preventing access to files outside the repository even if
they happen to be in a nearby directory.

Line limits
-----------
A single call is capped at settings.tool_file_max_lines.  When the requested
range (or the whole file) exceeds this limit, only the first max_lines lines
are returned and truncated=True is set in the result.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import File, Repository
from app.tools.models import (
    FileContent,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

logger = logging.getLogger(__name__)


def _is_safe_relative_path(path_str: str) -> bool:
    """
    Return True iff path_str is a safe relative path.

    Rejects:
    - Absolute paths (drive letters like C:\\ on Windows)
    - Unix-style root paths starting with / (not flagged as absolute on Windows)
    - Backslash-rooted paths starting with \\
    - Paths whose parts include ".."
    - Empty strings
    """
    if not path_str or not path_str.strip():
        return False
    # Explicit prefix check catches Unix-style / on Windows where
    # Path("/etc/passwd").is_absolute() incorrectly returns False.
    if path_str.startswith("/") or path_str.startswith("\\"):
        return False
    try:
        p = Path(path_str)
    except Exception:
        return False
    if p.is_absolute():
        return False
    if ".." in p.parts:
        return False
    return True


async def read_file(
    repository_id: uuid.UUID,
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    *,
    db: AsyncSession,
) -> ToolResult[FileContent]:
    """
    Read source lines from a repository file.

    Args:
        repository_id:  Repository scope; the file must belong to this repo.
        file_path:      Repository-relative path (e.g. "services/auth.py").
                        Must not be absolute or contain "..".
        start_line:     First line to read, 1-indexed inclusive.  None = start.
        end_line:       Last line to read, 1-indexed inclusive.  None = end.
        db:             Open AsyncSession.

    Returns:
        ToolResult[FileContent].  truncated=True when the line range was
        capped at settings.tool_file_max_lines.
    """
    # ------------------------------------------------------------------ #
    # 1. Path safety checks (before any DB or filesystem access)          #
    # ------------------------------------------------------------------ #
    if not _is_safe_relative_path(file_path):
        # Determine the most accurate error code for diagnostics
        if file_path and (
            file_path.startswith("/")
            or file_path.startswith("\\")
            or (file_path and Path(file_path).is_absolute())
        ):
            msg = "absolute paths are not allowed"
            code = ToolErrorCode.PATH_NOT_ALLOWED
        elif file_path and ".." in Path(file_path).parts:
            msg = "path traversal ('..') is not allowed"
            code = ToolErrorCode.PATH_NOT_ALLOWED
        else:
            msg = "invalid file path"
            code = ToolErrorCode.INVALID_INPUT
        return ToolResult(success=False, error=ToolError(code=code, message=msg))

    # Normalise separators (handles mixed / and \ on Windows)
    normalized_path = Path(file_path).as_posix()

    # ------------------------------------------------------------------ #
    # 2. Input validation for line range                                  #
    # ------------------------------------------------------------------ #
    if start_line is not None and start_line < 1:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.INVALID_INPUT,
                message="start_line must be >= 1",
            ),
        )
    if end_line is not None and end_line < 1:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.INVALID_INPUT,
                message="end_line must be >= 1",
            ),
        )
    if (
        start_line is not None
        and end_line is not None
        and start_line > end_line
    ):
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.INVALID_INPUT,
                message="start_line must be <= end_line",
            ),
        )

    # ------------------------------------------------------------------ #
    # 3. Look up repository                                               #
    # ------------------------------------------------------------------ #
    try:
        repo_row = (
            await db.execute(
                select(Repository).where(Repository.id == repository_id)
            )
        ).scalar_one_or_none()
    except Exception:
        logger.exception("read_file: repository lookup failed")
        return ToolResult(
            success=False,
            error=ToolError(code=ToolErrorCode.TOOL_ERROR, message="database error"),
        )

    if repo_row is None:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.INVALID_REPOSITORY,
                message=f"repository {repository_id} not found",
            ),
        )

    # ------------------------------------------------------------------ #
    # 4. Look up file in DB — enforces repository scoping                 #
    # ------------------------------------------------------------------ #
    # Try both the normalised POSIX path and the original (some OSes store \)
    try:
        file_row = (
            await db.execute(
                select(File).where(
                    File.repository_id == repository_id,
                    File.path == normalized_path,
                )
            )
        ).scalar_one_or_none()

        # Fallback: also try the original string in case paths were stored
        # with OS-specific separators during ingestion.
        if file_row is None and normalized_path != file_path:
            file_row = (
                await db.execute(
                    select(File).where(
                        File.repository_id == repository_id,
                        File.path == file_path,
                    )
                )
            ).scalar_one_or_none()
    except Exception:
        logger.exception("read_file: file lookup failed")
        return ToolResult(
            success=False,
            error=ToolError(code=ToolErrorCode.TOOL_ERROR, message="database error"),
        )

    if file_row is None:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.NOT_FOUND,
                message=f"file '{file_path}' not found in repository {repository_id}",
            ),
        )

    # ------------------------------------------------------------------ #
    # 5. Resolve absolute path and verify containment                     #
    # ------------------------------------------------------------------ #
    if repo_row.local_path is None:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.TOOL_ERROR,
                message="repository has no local_path — cannot read files",
            ),
        )

    repo_root = Path(repo_row.local_path).resolve()
    # Use the path as stored in DB (most reliable match to actual file)
    abs_path = (repo_root / file_row.path).resolve()

    try:
        abs_path.relative_to(repo_root)
    except ValueError:
        logger.warning(
            "read_file: resolved path %s escapes repo root %s", abs_path, repo_root
        )
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.PATH_NOT_ALLOWED,
                message="path resolves outside the repository root",
            ),
        )

    # ------------------------------------------------------------------ #
    # 6. Read file content                                                #
    # ------------------------------------------------------------------ #
    try:
        raw_text = abs_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.NOT_FOUND,
                message=f"file '{file_row.path}' exists in the database but was not found on disk",
            ),
        )
    except OSError as exc:
        logger.exception("read_file: OS error reading %s", abs_path)
        return ToolResult(
            success=False,
            error=ToolError(
                code=ToolErrorCode.TOOL_ERROR,
                message=f"could not read file: {exc}",
            ),
        )

    lines = raw_text.splitlines()
    total_lines = len(lines)

    # ------------------------------------------------------------------ #
    # 7. Apply line range (convert 1-indexed to 0-indexed slices)        #
    # ------------------------------------------------------------------ #
    slice_start = (start_line - 1) if start_line is not None else 0
    slice_end = end_line if end_line is not None else total_lines

    # Clamp to file bounds
    slice_start = max(0, min(slice_start, total_lines))
    slice_end = max(slice_start, min(slice_end, total_lines))

    # Apply per-call line cap
    max_lines = settings.tool_file_max_lines
    truncated = (slice_end - slice_start) > max_lines
    if truncated:
        slice_end = slice_start + max_lines

    selected_content = "\n".join(lines[slice_start:slice_end])

    # Convert back to 1-indexed for the caller
    actual_start = slice_start + 1
    actual_end = slice_end  # slice_end is already 1-indexed inclusive

    logger.debug(
        "read_file(%s, %r) lines %d-%d (truncated=%s)",
        repository_id, file_row.path, actual_start, actual_end, truncated,
    )

    return ToolResult(
        success=True,
        data=FileContent(
            repository_id=repository_id,
            file_path=file_row.path,
            language=file_row.language,
            requested_start_line=start_line,
            requested_end_line=end_line,
            actual_start_line=actual_start,
            actual_end_line=actual_end,
            content=selected_content,
            total_lines=total_lines,
            truncated=truncated,
        ),
    )
