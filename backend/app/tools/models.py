"""
Typed models for the RepoPilot agent tool layer.

Two key conventions
-------------------
1.  Every tool returns ToolResult[T].  success=False carries a ToolError;
    success=True carries data.  Tools never raise for expected conditions such
    as "symbol not found" or "file missing" — those are clean NOT_FOUND errors.

2.  Source location is preserved in every result that touches code.  Fields
    file_path, start_line, end_line appear wherever the future LLM agent will
    need to cite evidence.

Error taxonomy (ToolErrorCode)
------------------------------
NOT_FOUND          — requested entity does not exist in this repository
INVALID_INPUT      — caller supplied a bad parameter value
INVALID_REPOSITORY — the repository_id does not exist or has no data
PATH_NOT_ALLOWED   — read_file rejected a path (traversal / absolute / escape)
TOOL_ERROR         — unexpected infrastructure failure (DB, disk, etc.)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

class ToolErrorCode:
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_REPOSITORY = "INVALID_REPOSITORY"
    PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
    TOOL_ERROR = "TOOL_ERROR"
    AMBIGUOUS_SYMBOL = "AMBIGUOUS_SYMBOL"  # multiple symbols share the qualified_name


@dataclass
class ToolError:
    code: str        # one of ToolErrorCode constants
    message: str     # human-readable; safe to surface to the agent


# ---------------------------------------------------------------------------
# Generic result wrapper
# ---------------------------------------------------------------------------

@dataclass
class ToolResult(Generic[T]):
    """
    Uniform wrapper returned by every RepoPilot tool.

    success=True  → data is populated, error is None
    success=False → error is populated, data is None
    """
    success: bool
    data: T | None = None
    error: ToolError | None = None


# ---------------------------------------------------------------------------
# Shared symbol reference (used as a sub-struct in many results)
# ---------------------------------------------------------------------------

@dataclass
class SymbolRef:
    """Minimal symbol metadata used inside other result types."""

    symbol_id: uuid.UUID
    name: str
    qualified_name: str
    symbol_type: str
    file_path: str
    start_line: int
    end_line: int


# ---------------------------------------------------------------------------
# search_code result
# ---------------------------------------------------------------------------

@dataclass
class CodeSearchMatch:
    """One match returned by search_code."""

    chunk_id: uuid.UUID
    file_id: uuid.UUID
    file_path: str
    symbol_id: uuid.UUID | None
    symbol_name: str | None
    qualified_name: str | None
    start_line: int
    end_line: int
    content: str
    distance: float  # cosine distance; lower = more relevant


@dataclass
class SearchCodeResult:
    repository_id: uuid.UUID
    query: str
    results: list[CodeSearchMatch]
    returned: int
    truncated: bool   # True when top_k exceeded tool_search_max_results


# ---------------------------------------------------------------------------
# inspect_symbol result
# ---------------------------------------------------------------------------

@dataclass
class SymbolDetail:
    """Full symbol information including source code."""

    symbol_id: uuid.UUID
    name: str
    qualified_name: str
    symbol_type: str
    file_id: uuid.UUID
    file_path: str
    start_line: int
    end_line: int
    signature: str | None
    docstring: str | None
    source: str | None    # extracted source lines; None if file not readable


# ---------------------------------------------------------------------------
# read_file result
# ---------------------------------------------------------------------------

@dataclass
class FileContent:
    repository_id: uuid.UUID
    file_path: str
    language: str | None
    requested_start_line: int | None  # as passed by caller; None = "from start"
    requested_end_line: int | None    # as passed by caller; None = "to end"
    actual_start_line: int            # 1-indexed; clamped to file bounds
    actual_end_line: int              # 1-indexed inclusive
    content: str
    total_lines: int
    truncated: bool  # True when line range was capped by tool_file_max_lines


# ---------------------------------------------------------------------------
# get_dependencies / get_dependents result
# ---------------------------------------------------------------------------

@dataclass
class DependencyEntry:
    """One directed dependency edge: the connected symbol + edge metadata."""

    relationship_type: str
    confidence: float | None
    symbol: SymbolRef


@dataclass
class DependenciesResult:
    """Result of get_dependencies (outgoing edges from source_symbol)."""

    repository_id: uuid.UUID
    source_symbol: SymbolRef
    dependencies: list[DependencyEntry]
    returned: int
    truncated: bool


@dataclass
class DependentsResult:
    """Result of get_dependents (incoming edges to target_symbol)."""

    repository_id: uuid.UUID
    target_symbol: SymbolRef
    dependents: list[DependencyEntry]
    returned: int
    truncated: bool


# ---------------------------------------------------------------------------
# get_callers / get_callees result
# ---------------------------------------------------------------------------

@dataclass
class CallersResult:
    """Symbols that directly CALL the target symbol."""

    repository_id: uuid.UUID
    target_symbol: SymbolRef
    callers: list[SymbolRef]
    returned: int
    truncated: bool


@dataclass
class CalleesResult:
    """Symbols directly called BY the source symbol."""

    repository_id: uuid.UUID
    source_symbol: SymbolRef
    callees: list[SymbolRef]
    returned: int
    truncated: bool


# ---------------------------------------------------------------------------
# get_file_dependencies result
# ---------------------------------------------------------------------------

@dataclass
class FileDependencyEntry:
    """One file-level dependency (collapsed from multiple symbol edges)."""

    target_file_id: uuid.UUID
    target_file_path: str
    relationship_types: list[str]  # distinct types involved, sorted
    edge_count: int                # number of underlying symbol-level edges


@dataclass
class FileDependenciesResult:
    repository_id: uuid.UUID
    file_id: uuid.UUID
    source_file_path: str
    dependencies: list[FileDependencyEntry]
    returned: int
    truncated: bool
