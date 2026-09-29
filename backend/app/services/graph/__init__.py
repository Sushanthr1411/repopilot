"""
Graph layer for RepoPilot AI.

Public API
----------
build_repository_graph(repository_id, db) -> nx.MultiDiGraph
    Build an in-memory graph for one repository from the database.

get_dependencies(graph, symbol_id, relationship_types=None) -> list[GraphNode]
get_dependents(graph, symbol_id, relationship_types=None)   -> list[GraphNode]
get_callers(graph, symbol_id)                               -> list[GraphNode]
get_callees(graph, symbol_id)                               -> list[GraphNode]
find_path(graph, source_symbol_id, target_symbol_id)        -> PathResult
get_file_dependencies(graph, file_id)                       -> list[FileDependency]
get_repository_graph(graph, repository_id)                  -> RepositoryGraph

Typical usage
-------------
    graph = await build_repository_graph(repo_id, db_session)
    deps  = get_dependencies(graph, symbol_id)
    path  = find_path(graph, symbol_a_id, symbol_b_id)
"""

from app.services.graph.builder import build_repository_graph
from app.services.graph.models import (
    FileDependency,
    GraphEdge,
    GraphNode,
    PathResult,
    PathStep,
    RepositoryGraph,
)
from app.services.graph.service import (
    find_path,
    get_callees,
    get_callers,
    get_dependents,
    get_dependencies,
    get_dependencies_with_edges,
    get_dependents_with_edges,
    get_file_dependencies,
    get_repository_graph,
    get_symbol_node,
)

__all__ = [
    # builder
    "build_repository_graph",
    # service
    "find_path",
    "get_callees",
    "get_callers",
    "get_dependents",
    "get_dependencies",
    "get_dependencies_with_edges",
    "get_dependents_with_edges",
    "get_file_dependencies",
    "get_repository_graph",
    "get_symbol_node",
    # models
    "FileDependency",
    "GraphEdge",
    "GraphNode",
    "PathResult",
    "PathStep",
    "RepositoryGraph",
]
