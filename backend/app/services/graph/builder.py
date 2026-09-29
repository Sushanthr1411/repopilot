"""
Graph builder: queries the database for one repository and produces a
repository-scoped NetworkX MultiDiGraph.

Separation of concerns
----------------------
This module owns all DB I/O.  The service module owns all graph traversal.
NetworkX is kept out of API routers and service callers.

Graph structure
---------------
Nodes  — one per Symbol row; keyed by symbol UUID; metadata from Symbol + File.
Edges  — one per CodeRelationship row; keyed by relationship UUID.

Direction is preserved from the DB schema:
    source_symbol_id ──► target_symbol_id

Repository isolation
--------------------
Only symbols and relationships belonging to the requested repository_id are
loaded.  Symbols from other repositories never appear in the graph.
"""

import logging
import uuid

import networkx as nx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CodeRelationship, File, Symbol

logger = logging.getLogger(__name__)


def _node_attrs(sym: Symbol, file_path: str) -> dict:
    return {
        "name": sym.name,
        "qualified_name": sym.qualified_name,
        "symbol_type": sym.symbol_type,
        "file_id": sym.file_id,
        "file_path": file_path,
        "start_line": sym.start_line,
        "end_line": sym.end_line,
    }


async def build_repository_graph(
    repository_id: uuid.UUID,
    db: AsyncSession,
) -> nx.MultiDiGraph:
    """
    Build an in-memory directed multigraph for one repository.

    Returns an empty graph (no nodes, no edges) for repositories that have no
    successfully parsed symbols.  Never raises on empty/missing data.

    Args:
        repository_id: The repository whose data to load.
        db:            Open AsyncSession; read-only — nothing is written.

    Returns:
        nx.MultiDiGraph with UUID node keys and typed edge metadata.
    """
    # ------------------------------------------------------------------ #
    # 1. Load symbols (filter through File.repository_id)                 #
    # ------------------------------------------------------------------ #
    sym_stmt = (
        select(Symbol, File.path)
        .join(File, Symbol.file_id == File.id)
        .where(File.repository_id == repository_id)
    )
    sym_rows = (await db.execute(sym_stmt)).all()

    # ------------------------------------------------------------------ #
    # 2. Load relationships (repository_id column on CodeRelationship)    #
    # ------------------------------------------------------------------ #
    rel_stmt = (
        select(CodeRelationship)
        .where(CodeRelationship.repository_id == repository_id)
    )
    relationships = (await db.execute(rel_stmt)).scalars().all()

    # ------------------------------------------------------------------ #
    # 3. Build graph                                                       #
    # ------------------------------------------------------------------ #
    graph: nx.MultiDiGraph = nx.MultiDiGraph()

    for sym, file_path in sym_rows:
        graph.add_node(sym.id, **_node_attrs(sym, file_path))

    skipped = 0
    for rel in relationships:
        if rel.source_symbol_id not in graph or rel.target_symbol_id not in graph:
            # Defensive: skip orphaned relationship rows
            logger.debug(
                "Skipping orphaned relationship %s (src=%s tgt=%s)",
                rel.id, rel.source_symbol_id, rel.target_symbol_id,
            )
            skipped += 1
            continue
        graph.add_edge(
            rel.source_symbol_id,
            rel.target_symbol_id,
            key=rel.id,
            relationship_id=rel.id,
            relationship_type=rel.relationship_type,
            confidence=rel.confidence,
        )

    logger.info(
        "Repository %s graph: %d nodes, %d edges (%d orphaned skipped)",
        repository_id,
        graph.number_of_nodes(),
        graph.number_of_edges(),
        skipped,
    )
    return graph
