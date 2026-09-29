"""
Typed data models for the graph layer.

NetworkX remains an internal implementation detail; these dataclasses are the
public interface that callers (future API routes, agent tools) receive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class GraphNode:
    """A symbol node in the repository graph."""

    symbol_id: uuid.UUID
    name: str
    qualified_name: str
    symbol_type: str
    file_id: uuid.UUID
    file_path: str
    start_line: int
    end_line: int


@dataclass
class GraphEdge:
    """A directed relationship edge: source_symbol_id ──► target_symbol_id."""

    relationship_id: uuid.UUID
    source_symbol_id: uuid.UUID
    target_symbol_id: uuid.UUID
    relationship_type: str
    confidence: float | None


@dataclass
class PathStep:
    """One step in a symbol path: the node reached and the edge taken to get there."""

    node: GraphNode
    edge: GraphEdge | None  # None for the starting node


@dataclass
class PathResult:
    """Result of find_path()."""

    found: bool
    source_symbol_id: uuid.UUID
    target_symbol_id: uuid.UUID
    steps: list[PathStep] = field(default_factory=list)


@dataclass
class FileDependency:
    """
    A file-level dependency derived from symbol-level relationships.

    When many symbol pairs cross the same file boundary they are collapsed into
    a single FileDependency, so callers get a clean file-oriented view.
    """

    source_file_id: uuid.UUID
    source_file_path: str
    target_file_id: uuid.UUID
    target_file_path: str
    relationship_types: list[str]  # distinct relationship types, sorted
    edge_count: int  # total number of underlying symbol-level edges


@dataclass
class RepositoryGraph:
    """Snapshot of an entire repository graph at symbol level."""

    repository_id: uuid.UUID
    nodes: list[GraphNode]
    edges: list[GraphEdge]
