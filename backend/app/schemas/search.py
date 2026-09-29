from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=100)


class SearchResultItem(BaseModel):
    chunk_id: uuid.UUID
    file_id: uuid.UUID
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbol_id: uuid.UUID | None
    symbol_name: str | None
    qualified_name: str | None
    distance: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
