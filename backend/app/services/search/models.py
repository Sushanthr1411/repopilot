"""
Typed data models for the search/indexing layer.

These types flow through the pipeline:

    Chunker output:  Chunk
    Indexer input:   SymbolInfo (from DB)
    Indexer output:  IndexStats
    Search output:   SearchResult
    VectorStore:     VectorResult (internal)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class SymbolInfo:
    """Minimal symbol data passed from the indexer into the chunker."""

    symbol_id: uuid.UUID
    name: str
    qualified_name: str
    symbol_type: str
    start_line: int
    end_line: int


@dataclass
class Chunk:
    """
    A single code excerpt produced by the chunker.

    This is an in-memory representation; it is not yet persisted to the DB
    or indexed into ChromaDB.
    """

    chunk_id: uuid.UUID
    repository_id: uuid.UUID
    file_id: uuid.UUID
    symbol_id: uuid.UUID | None
    file_path: str
    symbol_name: str | None
    qualified_name: str | None
    symbol_type: str | None
    start_line: int
    end_line: int
    content: str
    content_hash: str


@dataclass
class SearchResult:
    """
    A single result from search_repository().

    score is a cosine distance (lower = more similar; range 0–2 with cosine space).
    It is explicitly named 'distance' to avoid mislabelling a distance metric as
    a 0–1 similarity score.
    """

    chunk_id: uuid.UUID
    repository_id: uuid.UUID
    file_id: uuid.UUID
    file_path: str
    symbol_id: uuid.UUID | None
    symbol_name: str | None
    qualified_name: str | None
    start_line: int
    end_line: int
    content: str
    distance: float  # cosine distance; 0 = identical, higher = less similar


@dataclass
class IndexStats:
    """Statistics returned by index_repository()."""

    repository_id: uuid.UUID
    total_files: int
    chunks_created: int
    chunks_deleted: int
    files_skipped: int  # files whose content could not be read from disk


@dataclass
class VectorResult:
    """Internal: one row returned by the vector store query."""

    chunk_id: str  # UUID as string (Chroma ID)
    content: str
    metadata: dict
    distance: float
