from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateRepositoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    local_path: str
    source_url: str | None = None


class RepositoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    source_url: str | None
    local_path: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    file_count: int = 0
    symbol_count: int = 0

    model_config = {"from_attributes": True}


class IngestResponse(BaseModel):
    repository_id: uuid.UUID
    status: str
    total_files: int
    parsed_files: int
    files_with_errors: int
    total_symbols: int
    total_relationships: int
    unresolved_relationships: int
    parse_errors: list[str] = []
    warnings: list[str] = []


class IndexResponse(BaseModel):
    repository_id: uuid.UUID
    total_files: int
    chunks_created: int
    chunks_deleted: int
    files_skipped: int
