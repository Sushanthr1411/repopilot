from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SymbolResponse(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    file_path: str
    name: str
    qualified_name: str
    symbol_type: str
    start_line: int
    end_line: int
    signature: str | None
    docstring: str | None
    created_at: datetime
    updated_at: datetime


class SymbolListResponse(BaseModel):
    items: list[SymbolResponse]
    total: int
    limit: int
    offset: int
