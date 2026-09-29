from __future__ import annotations

import uuid

from pydantic import BaseModel


class GraphNodeResponse(BaseModel):
    symbol_id: uuid.UUID
    name: str
    qualified_name: str
    symbol_type: str
    file_id: uuid.UUID
    file_path: str
    start_line: int
    end_line: int


class GraphEdgeResponse(BaseModel):
    relationship_id: uuid.UUID
    source_symbol_id: uuid.UUID
    target_symbol_id: uuid.UUID
    relationship_type: str
    confidence: float | None


class GraphResponse(BaseModel):
    repository_id: uuid.UUID
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]


class DependencyResponse(BaseModel):
    symbol_id: uuid.UUID
    name: str
    qualified_name: str
    symbol_type: str
    file_path: str
    start_line: int
    end_line: int
