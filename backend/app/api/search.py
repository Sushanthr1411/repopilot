"""
Semantic search endpoint.

POST  /{repo_id}/search   query the indexed code chunks
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Repository
from app.deps import get_db, get_embedding_provider, get_vector_store
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from app.services.search.service import search_repository

router = APIRouter()


@router.post("/{repo_id}/search", response_model=SearchResponse)
async def search(
    repo_id: uuid.UUID,
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    embedding_provider=Depends(get_embedding_provider),
    vector_store=Depends(get_vector_store),
) -> SearchResponse:
    repo = await db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Repository {repo_id} not found"},
        )

    results = await search_repository(
        repository_id=repo_id,
        query=body.query,
        top_k=body.top_k,
        db=db,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )

    return SearchResponse(
        query=body.query,
        results=[
            SearchResultItem(
                chunk_id=r.chunk_id,
                file_id=r.file_id,
                file_path=r.file_path,
                start_line=r.start_line,
                end_line=r.end_line,
                content=r.content,
                symbol_id=r.symbol_id,
                symbol_name=r.symbol_name,
                qualified_name=r.qualified_name,
                distance=r.distance,
            )
            for r in results
        ],
    )
