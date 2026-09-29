from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class FileSummaryResponse(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    path: str
    language: str | None
    size: int | None
    content_hash: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FileResponse(FileSummaryResponse):
    content: str
    total_lines: int


class FileListResponse(BaseModel):
    items: list[FileSummaryResponse]
    total: int
    limit: int
    offset: int
