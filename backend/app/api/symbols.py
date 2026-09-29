"""
Symbol resource endpoints.

GET  /{repo_id}/symbols                  paginated list with optional filters
GET  /{repo_id}/symbols/{symbol_id}      symbol detail
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import File, Repository, Symbol
from app.deps import get_db
from app.schemas.symbol import SymbolListResponse, SymbolResponse

router = APIRouter()


async def _get_repo_or_404(repo_id: uuid.UUID, db: AsyncSession) -> Repository:
    repo = await db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Repository {repo_id} not found"},
        )
    return repo


def _to_response(sym: Symbol, file_path: str) -> SymbolResponse:
    return SymbolResponse(
        id=sym.id,
        file_id=sym.file_id,
        file_path=file_path,
        name=sym.name,
        qualified_name=sym.qualified_name,
        symbol_type=sym.symbol_type,
        start_line=sym.start_line,
        end_line=sym.end_line,
        signature=sym.signature,
        docstring=sym.docstring,
        created_at=sym.created_at,
        updated_at=sym.updated_at,
    )


@router.get("/{repo_id}/symbols", response_model=SymbolListResponse)
async def list_symbols(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    symbol_type: str | None = Query(default=None, description="Filter by symbol type (function, class, method, …)"),
    name: str | None = Query(default=None, description="Case-insensitive substring filter on symbol name"),
) -> SymbolListResponse:
    await _get_repo_or_404(repo_id, db)

    base = (
        select(Symbol, File.path.label("file_path"))
        .join(File, Symbol.file_id == File.id)
        .where(File.repository_id == repo_id)
    )
    if symbol_type:
        base = base.where(Symbol.symbol_type == symbol_type)
    if name:
        base = base.where(Symbol.name.ilike(f"%{name}%"))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = count_result.scalar() or 0

    rows_result = await db.execute(
        base.order_by(File.path, Symbol.start_line).limit(limit).offset(offset)
    )
    rows = rows_result.all()

    return SymbolListResponse(
        items=[_to_response(sym, file_path) for sym, file_path in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{repo_id}/symbols/{symbol_id}", response_model=SymbolResponse)
async def get_symbol(
    repo_id: uuid.UUID,
    symbol_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SymbolResponse:
    await _get_repo_or_404(repo_id, db)

    result = await db.execute(
        select(Symbol, File.path.label("file_path"))
        .join(File, Symbol.file_id == File.id)
        .where(Symbol.id == symbol_id)
        .where(File.repository_id == repo_id)
    )
    row = result.first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": f"Symbol {symbol_id} not found in repository {repo_id}",
            },
        )

    sym, file_path = row
    return _to_response(sym, file_path)
