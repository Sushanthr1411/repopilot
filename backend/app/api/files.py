"""
File resource endpoints.

GET  /{repo_id}/files              paginated list of files
GET  /{repo_id}/files/{file_id}    file content with optional line range
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import File, Repository
from app.deps import get_db
from app.schemas.file import FileListResponse, FileResponse, FileSummaryResponse

router = APIRouter()


async def _get_repo_or_404(repo_id: uuid.UUID, db: AsyncSession) -> Repository:
    repo = await db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Repository {repo_id} not found"},
        )
    return repo


@router.get("/{repo_id}/files", response_model=FileListResponse)
async def list_files(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FileListResponse:
    await _get_repo_or_404(repo_id, db)

    total_result = await db.execute(
        select(func.count()).select_from(File).where(File.repository_id == repo_id)
    )
    total: int = total_result.scalar() or 0

    files_result = await db.execute(
        select(File)
        .where(File.repository_id == repo_id)
        .order_by(File.path)
        .limit(limit)
        .offset(offset)
    )
    files = files_result.scalars().all()

    return FileListResponse(
        items=[FileSummaryResponse.model_validate(f) for f in files],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{repo_id}/files/{file_id}", response_model=FileResponse)
async def get_file(
    repo_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    start_line: int | None = Query(default=None, ge=1, description="1-based start line (inclusive)"),
    end_line: int | None = Query(default=None, ge=1, description="1-based end line (inclusive)"),
) -> FileResponse:
    repo = await _get_repo_or_404(repo_id, db)

    file = await db.get(File, file_id)
    if file is None or file.repository_id != repo_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"File {file_id} not found in repository {repo_id}"},
        )

    if not repo.local_path:
        raise HTTPException(
            status_code=400,
            detail={"code": "NO_LOCAL_PATH", "message": "Repository has no local_path configured"},
        )

    file_path = Path(repo.local_path) / file.path
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "FILE_NOT_READABLE", "message": f"Cannot read file: {exc}"},
        )

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    if start_line is not None or end_line is not None:
        s = (start_line or 1) - 1  # convert to 0-based index
        e = end_line if end_line is not None else total_lines
        content = "".join(lines[s:e])

    return FileResponse(
        id=file.id,
        repository_id=file.repository_id,
        path=file.path,
        language=file.language,
        size=file.size,
        content_hash=file.content_hash,
        created_at=file.created_at,
        updated_at=file.updated_at,
        content=content,
        total_lines=total_lines,
    )
