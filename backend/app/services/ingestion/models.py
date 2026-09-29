"""
Result types returned by the ingestion service.

Pure dataclasses — no SQLAlchemy dependency.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class IngestionResult:
    """Summary of a completed (or failed) repository ingestion run."""

    repository_id: uuid.UUID
    repository_name: str
    # "ready" | "failed"
    status: str

    total_files: int = 0
    parsed_files: int = 0
    files_with_errors: int = 0

    total_symbols: int = 0
    total_relationships: int = 0
    # Relationships whose source or target could not be resolved to a DB symbol.
    unresolved_relationships: int = 0

    # Human-readable parse error summaries: "<file>: <ErrorType>: <message>"
    parse_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
