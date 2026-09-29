"""
Graph traversal service.

All functions are pure: they accept a pre-built nx.MultiDiGraph (from
builder.build_repository_graph) and return typed result objects.  No DB
access happens here.

Public interface
----------------
get_dependencies(graph, symbol_id, relationship_types=None) -> list[GraphNode]
get_dependents(graph, symbol_id, relationship_types=None)   -> list[GraphNode]
get_callers(graph, symbol_id)                               -> list[GraphNode]
get_callees(graph, symbol_id)                               -> list[GraphNode]
find_path(graph, source_symbol_id, target_symbol_id)        -> PathResult
get_file_dependencies(graph, file_id)                       -> list[FileDependency]
get_repository_graph(graph, repository_id)                  -> RepositoryGraph

Direction convention (matches DB schema and builder):
    source_symbol_id ──[rel_type]──► target_symbol_id
"""

import uuid
from typing import Sequence

import networkx as nx

from app.services.graph.models import (
    FileDependency,
    GraphEdge,
    GraphNode,
    PathResult,
    PathStep,
    RepositoryGraph,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _node(graph: nx.MultiDiGraph, symbol_id: uuid.UUID) -> GraphNode | None:
    """Return a GraphNode for the given node id, or None if absent."""
    if symbol_id not in graph:
        return None
    data = graph.nodes[symbol_id]
    return GraphNode(
        symbol_id=symbol_id,
        name=data["name"],
        qualified_name=data["qualified_name"],
        symbol_type=data["symbol_type"],
        file_id=data["file_id"],
        file_path=data["file_path"],
        start_line=data["start_line"],
        end_line=data["end_line"],
    )


def _edge(
    graph: nx.MultiDiGraph,
    src: uuid.UUID,
    tgt: uuid.UUID,
    key: uuid.UUID,
) -> GraphEdge:
    data = graph[src][tgt][key]
    return GraphEdge(
        relationship_id=data["relationship_id"],
        source_symbol_id=src,
        target_symbol_id=tgt,
        relationship_type=data["relationship_type"],
        confidence=data.get("confidence"),
    )


def _first_edge_between(
    graph: nx.MultiDiGraph,
    src: uuid.UUID,
    tgt: uuid.UUID,
) -> GraphEdge:
    """Return the first edge (arbitrary order) between src and tgt."""
    first_key = next(iter(graph[src][tgt]))
    return _edge(graph, src, tgt, first_key)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_dependencies(
    graph: nx.MultiDiGraph,
    symbol_id: uuid.UUID,
    relationship_types: Sequence[str] | None = None,
) -> list[GraphNode]:
    """
    Return symbols that `symbol_id` directly depends on (outgoing edges).

    Args:
        relationship_types: When given, only edges of these types are followed.
                            None means all relationship types.

    Returns:
        Deduplicated list of GraphNodes (one per distinct target symbol).
    """
    if symbol_id not in graph:
        return []
    seen: set[uuid.UUID] = set()
    result: list[GraphNode] = []
    for _, tgt_id, edge_data in graph.out_edges(symbol_id, data=True):
        if relationship_types is not None and edge_data["relationship_type"] not in relationship_types:
            continue
        if tgt_id not in seen:
            node = _node(graph, tgt_id)
            if node is not None:
                result.append(node)
                seen.add(tgt_id)
    return result


def get_dependents(
    graph: nx.MultiDiGraph,
    symbol_id: uuid.UUID,
    relationship_types: Sequence[str] | None = None,
) -> list[GraphNode]:
    """
    Return symbols that directly depend on `symbol_id` (incoming edges).

    Args:
        relationship_types: When given, only edges of these types are followed.

    Returns:
        Deduplicated list of GraphNodes (one per distinct source symbol).
    """
    if symbol_id not in graph:
        return []
    seen: set[uuid.UUID] = set()
    result: list[GraphNode] = []
    for src_id, _, edge_data in graph.in_edges(symbol_id, data=True):
        if relationship_types is not None and edge_data["relationship_type"] not in relationship_types:
            continue
        if src_id not in seen:
            node = _node(graph, src_id)
            if node is not None:
                result.append(node)
                seen.add(src_id)
    return result


def get_callers(
    graph: nx.MultiDiGraph,
    symbol_id: uuid.UUID,
) -> list[GraphNode]:
    """Return symbols with a CALLS edge pointing TO symbol_id."""
    return get_dependents(graph, symbol_id, relationship_types=["CALLS"])


def get_callees(
    graph: nx.MultiDiGraph,
    symbol_id: uuid.UUID,
) -> list[GraphNode]:
    """Return symbols that symbol_id CALLs."""
    return get_dependencies(graph, symbol_id, relationship_types=["CALLS"])


def find_path(
    graph: nx.MultiDiGraph,
    source_symbol_id: uuid.UUID,
    target_symbol_id: uuid.UUID,
) -> PathResult:
    """
    Find the shortest directed path between two symbols.

    Returns PathResult.found=False (empty steps) when:
    - Either symbol is not in the graph.
    - No directed path exists.

    Returns a single-step PathResult when source == target (if the node exists).
    """
    not_found = PathResult(
        found=False,
        source_symbol_id=source_symbol_id,
        target_symbol_id=target_symbol_id,
    )

    if source_symbol_id == target_symbol_id:
        node = _node(graph, source_symbol_id)
        if node is None:
            return not_found
        return PathResult(
            found=True,
            source_symbol_id=source_symbol_id,
            target_symbol_id=target_symbol_id,
            steps=[PathStep(node=node, edge=None)],
        )

    if source_symbol_id not in graph or target_symbol_id not in graph:
        return not_found

    try:
        node_ids: list[uuid.UUID] = nx.shortest_path(
            graph, source=source_symbol_id, target=target_symbol_id
        )
    except nx.NetworkXNoPath:
        return not_found

    steps: list[PathStep] = []
    for i, nid in enumerate(node_ids):
        node = _node(graph, nid)
        if node is None:
            continue
        if i == 0:
            steps.append(PathStep(node=node, edge=None))
        else:
            prev_id = node_ids[i - 1]
            edge = _first_edge_between(graph, prev_id, nid)
            steps.append(PathStep(node=node, edge=edge))

    return PathResult(
        found=True,
        source_symbol_id=source_symbol_id,
        target_symbol_id=target_symbol_id,
        steps=steps,
    )


def get_file_dependencies(
    graph: nx.MultiDiGraph,
    file_id: uuid.UUID,
) -> list[FileDependency]:
    """
    Return file-level dependencies for the given file.

    Symbol-level edges that cross a file boundary are collapsed: multiple edges
    from symbols in `file_id` to symbols in the same target file produce a
    single FileDependency with an edge_count > 1.

    Self-references (both ends in the same file) are excluded.

    Returns an empty list when the file has no symbols or no outgoing
    cross-file edges.
    """
    file_symbol_ids = {
        nid for nid, data in graph.nodes(data=True)
        if data.get("file_id") == file_id
    }
    if not file_symbol_ids:
        return []

    source_path = graph.nodes[next(iter(file_symbol_ids))].get("file_path", "")

    # target_file_id → {target_file_path, rel_types: set, edge_count}
    deps: dict[uuid.UUID, dict] = {}

    for src_id in file_symbol_ids:
        for _, tgt_id, edge_data in graph.out_edges(src_id, data=True):
            tgt_data = graph.nodes[tgt_id]
            tgt_file_id: uuid.UUID | None = tgt_data.get("file_id")
            if tgt_file_id is None or tgt_file_id == file_id:
                continue
            if tgt_file_id not in deps:
                deps[tgt_file_id] = {
                    "target_file_path": tgt_data.get("file_path", ""),
                    "rel_types": set(),
                    "edge_count": 0,
                }
            deps[tgt_file_id]["rel_types"].add(edge_data["relationship_type"])
            deps[tgt_file_id]["edge_count"] += 1

    return [
        FileDependency(
            source_file_id=file_id,
            source_file_path=source_path,
            target_file_id=tgt_fid,
            target_file_path=info["target_file_path"],
            relationship_types=sorted(info["rel_types"]),
            edge_count=info["edge_count"],
        )
        for tgt_fid, info in deps.items()
    ]


def get_symbol_node(
    graph: nx.MultiDiGraph,
    symbol_id: uuid.UUID,
) -> GraphNode | None:
    """Return the GraphNode for a symbol, or None if not in the graph."""
    return _node(graph, symbol_id)


def get_dependencies_with_edges(
    graph: nx.MultiDiGraph,
    symbol_id: uuid.UUID,
    relationship_types: Sequence[str] | None = None,
) -> list[tuple[GraphNode, GraphEdge]]:
    """
    Return (target_node, edge) pairs for all direct outgoing edges of symbol_id.

    Unlike get_dependencies(), this returns one entry per edge (not deduplicated
    by target node), so multiple relationship types between the same pair appear
    as separate entries.
    """
    if symbol_id not in graph:
        return []
    result: list[tuple[GraphNode, GraphEdge]] = []
    for _, tgt_id, key, edge_data in graph.out_edges(symbol_id, data=True, keys=True):
        if relationship_types is not None and edge_data["relationship_type"] not in relationship_types:
            continue
        node = _node(graph, tgt_id)
        if node is not None:
            edge = _edge(graph, symbol_id, tgt_id, key)
            result.append((node, edge))
    return result


def get_dependents_with_edges(
    graph: nx.MultiDiGraph,
    symbol_id: uuid.UUID,
    relationship_types: Sequence[str] | None = None,
) -> list[tuple[GraphNode, GraphEdge]]:
    """
    Return (source_node, edge) pairs for all direct incoming edges of symbol_id.

    One entry per edge; multiple relationship types appear as separate entries.
    """
    if symbol_id not in graph:
        return []
    result: list[tuple[GraphNode, GraphEdge]] = []
    for src_id, _, key, edge_data in graph.in_edges(symbol_id, data=True, keys=True):
        if relationship_types is not None and edge_data["relationship_type"] not in relationship_types:
            continue
        node = _node(graph, src_id)
        if node is not None:
            edge = _edge(graph, src_id, symbol_id, key)
            result.append((node, edge))
    return result


def get_repository_graph(
    graph: nx.MultiDiGraph,
    repository_id: uuid.UUID,
) -> RepositoryGraph:
    """
    Return a complete snapshot of the repository graph.

    The returned RepositoryGraph contains all nodes and edges; for large
    repositories callers may want to use the targeted traversal functions
    instead.
    """
    nodes = [_node(graph, nid) for nid in graph.nodes()]
    nodes_clean: list[GraphNode] = [n for n in nodes if n is not None]

    edges: list[GraphEdge] = [
        GraphEdge(
            relationship_id=data["relationship_id"],
            source_symbol_id=src,
            target_symbol_id=tgt,
            relationship_type=data["relationship_type"],
            confidence=data.get("confidence"),
        )
        for src, tgt, key, data in graph.edges(data=True, keys=True)
    ]

    return RepositoryGraph(
        repository_id=repository_id,
        nodes=nodes_clean,
        edges=edges,
    )
