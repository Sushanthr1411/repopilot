"""
Repository resource endpoints.

POST   /                    create (status=pending)
GET    /{repo_id}           detail with file/symbol counts
POST   /{repo_id}/ingest    parse + index (synchronous)
POST   /{repo_id}/index     index only (re-embed existing ingestion)
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import File, Repository, Symbol
from app.deps import get_db, get_embedding_provider, get_vector_store
from app.schemas.repository import (
    CreateRepositoryRequest,
    IndexResponse,
    IngestResponse,
    RepositoryResponse,
)
from app.services.ingestion.service import ingest_existing_repository
from app.services.search.indexer import index_repository

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_path_security(local_path: str) -> Path:
    """Resolve path, check existence, and enforce allowed_repo_root if configured."""
    try:
        resolved = Path(local_path).resolve()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_PATH", "message": str(exc)},
        )

    if not resolved.exists():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "PATH_NOT_FOUND",
                "message": f"Path does not exist: {local_path!r}",
            },
        )
    if not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "PATH_NOT_DIRECTORY",
                "message": f"Path is not a directory: {local_path!r}",
            },
        )

    if settings.allowed_repo_root:
        root = Path(settings.allowed_repo_root).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "PATH_NOT_ALLOWED",
                    "message": (
                        f"Path must be under the configured allowed root: "
                        f"{settings.allowed_repo_root!r}"
                    ),
                },
            )

    return resolved


async def _get_repo_or_404(repo_id: uuid.UUID, db: AsyncSession) -> Repository:
    repo = await db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Repository {repo_id} not found"},
        )
    return repo


async def _get_counts(repo_id: uuid.UUID, db: AsyncSession) -> tuple[int, int]:
    file_result = await db.execute(
        select(func.count()).select_from(File).where(File.repository_id == repo_id)
    )
    file_count: int = file_result.scalar() or 0

    sym_result = await db.execute(
        select(func.count())
        .select_from(Symbol)
        .join(File, Symbol.file_id == File.id)
        .where(File.repository_id == repo_id)
    )
    symbol_count: int = sym_result.scalar() or 0

    return file_count, symbol_count


def _repo_response(repo: Repository, file_count: int = 0, symbol_count: int = 0) -> RepositoryResponse:
    return RepositoryResponse(
        id=repo.id,
        name=repo.name,
        source_url=repo.source_url,
        local_path=repo.local_path,
        status=repo.status,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
        file_count=file_count,
        symbol_count=symbol_count,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", status_code=201, response_model=RepositoryResponse)
async def create_repository(
    body: CreateRepositoryRequest,
    db: AsyncSession = Depends(get_db),
) -> RepositoryResponse:
    resolved = _validate_path_security(body.local_path)

    repo = Repository(
        id=uuid.uuid4(),
        name=body.name.strip(),
        local_path=str(resolved),
        source_url=body.source_url,
        status="pending",
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)

    return _repo_response(repo)


@router.get("/{repo_id}", response_model=RepositoryResponse)
async def get_repository(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RepositoryResponse:
    repo = await _get_repo_or_404(repo_id, db)
    file_count, symbol_count = await _get_counts(repo_id, db)
    return _repo_response(repo, file_count, symbol_count)


@router.post("/{repo_id}/ingest", response_model=IngestResponse)
async def ingest(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    embedding_provider=Depends(get_embedding_provider),
    vector_store=Depends(get_vector_store),
) -> IngestResponse:
    """Parse the repository and update the search index (synchronous)."""
    await _get_repo_or_404(repo_id, db)

    try:
        ingest_result = await ingest_existing_repository(db, repo_id)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"code": "INGEST_ERROR", "message": str(exc)},
        )
    except Exception as exc:
        await db.rollback()
        logger.exception("Unexpected error during ingestion of %s", repo_id)
        raise HTTPException(
            status_code=500,
            detail={"code": "INGEST_ERROR", "message": str(exc)},
        )

    warnings = list(ingest_result.warnings)
    try:
        await index_repository(
            repo_id,
            db,
            embedding_provider,
            vector_store,
            max_chunk_lines=settings.chunk_max_lines,
            overlap_lines=settings.chunk_overlap_lines,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("Indexing failed for %s (search unavailable): %s", repo_id, exc)
        warnings.append(f"Semantic indexing failed — search_code tool unavailable: {exc}")

    return IngestResponse(
        repository_id=ingest_result.repository_id,
        status=ingest_result.status,
        total_files=ingest_result.total_files,
        parsed_files=ingest_result.parsed_files,
        files_with_errors=ingest_result.files_with_errors,
        total_symbols=ingest_result.total_symbols,
        total_relationships=ingest_result.total_relationships,
        unresolved_relationships=ingest_result.unresolved_relationships,
        parse_errors=ingest_result.parse_errors,
        warnings=warnings,
    )


@router.post("/{repo_id}/index", response_model=IndexResponse)
async def index(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    embedding_provider=Depends(get_embedding_provider),
    vector_store=Depends(get_vector_store),
) -> IndexResponse:
    """Re-embed and re-index an already-ingested repository."""
    repo = await _get_repo_or_404(repo_id, db)

    if repo.status != "ready":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "NOT_READY",
                "message": (
                    f"Repository must be ingested before indexing "
                    f"(current status={repo.status!r})"
                ),
            },
        )

    try:
        stats = await index_repository(
            repo_id,
            db,
            embedding_provider,
            vector_store,
            max_chunk_lines=settings.chunk_max_lines,
            overlap_lines=settings.chunk_overlap_lines,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INDEX_ERROR", "message": str(exc)},
        )
    except Exception as exc:
        await db.rollback()
        logger.exception("Unexpected error during indexing of %s", repo_id)
        raise HTTPException(
            status_code=500,
            detail={"code": "INDEX_ERROR", "message": str(exc)},
        )

    return IndexResponse(
        repository_id=stats.repository_id,
        total_files=stats.total_files,
        chunks_created=stats.chunks_created,
        chunks_deleted=stats.chunks_deleted,
        files_skipped=stats.files_skipped,
    )
