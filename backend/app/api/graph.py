"""
Graph resource endpoints.

GET  /{repo_id}/graph                              full repository graph
GET  /{repo_id}/symbols/{symbol_id}/dependencies   outgoing edges (what it depends on)
GET  /{repo_id}/symbols/{symbol_id}/dependents     incoming edges (what depends on it)
GET  /{repo_id}/symbols/{symbol_id}/callers        symbols with a CALLS edge to this one
GET  /{repo_id}/symbols/{symbol_id}/callees        symbols this one CALLs
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Repository
from app.deps import get_db
from app.schemas.graph import DependencyResponse, GraphEdgeResponse, GraphNodeResponse, GraphResponse
from app.services.graph.builder import build_repository_graph
from app.services.graph.models import GraphEdge, GraphNode
from app.services.graph.service import (
    get_callees,
    get_callers,
    get_dependencies,
    get_dependents,
    get_repository_graph,
)

router = APIRouter()


async def _get_repo_or_404(repo_id: uuid.UUID, db: AsyncSession) -> Repository:
    repo = await db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Repository {repo_id} not found"},
        )
    return repo


def _node_resp(node: GraphNode) -> GraphNodeResponse:
    return GraphNodeResponse(
        symbol_id=node.symbol_id,
        name=node.name,
        qualified_name=node.qualified_name,
        symbol_type=node.symbol_type,
        file_id=node.file_id,
        file_path=node.file_path,
        start_line=node.start_line,
        end_line=node.end_line,
    )


def _edge_resp(edge: GraphEdge) -> GraphEdgeResponse:
    return GraphEdgeResponse(
        relationship_id=edge.relationship_id,
        source_symbol_id=edge.source_symbol_id,
        target_symbol_id=edge.target_symbol_id,
        relationship_type=edge.relationship_type,
        confidence=edge.confidence,
    )


def _dep_resp(node: GraphNode) -> DependencyResponse:
    return DependencyResponse(
        symbol_id=node.symbol_id,
        name=node.name,
        qualified_name=node.qualified_name,
        symbol_type=node.symbol_type,
        file_path=node.file_path,
        start_line=node.start_line,
        end_line=node.end_line,
    )


@router.get("/{repo_id}/graph", response_model=GraphResponse)
async def get_graph(
    repo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    await _get_repo_or_404(repo_id, db)
    graph = await build_repository_graph(repo_id, db)
    repo_graph = get_repository_graph(graph, repo_id)

    return GraphResponse(
        repository_id=repo_graph.repository_id,
        nodes=[_node_resp(n) for n in repo_graph.nodes],
        edges=[_edge_resp(e) for e in repo_graph.edges],
    )


@router.get("/{repo_id}/symbols/{symbol_id}/dependencies", response_model=list[DependencyResponse])
async def get_symbol_dependencies(
    repo_id: uuid.UUID,
    symbol_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[DependencyResponse]:
    await _get_repo_or_404(repo_id, db)
    graph = await build_repository_graph(repo_id, db)
    return [_dep_resp(n) for n in get_dependencies(graph, symbol_id)]


@router.get("/{repo_id}/symbols/{symbol_id}/dependents", response_model=list[DependencyResponse])
async def get_symbol_dependents(
    repo_id: uuid.UUID,
    symbol_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[DependencyResponse]:
    await _get_repo_or_404(repo_id, db)
    graph = await build_repository_graph(repo_id, db)
    return [_dep_resp(n) for n in get_dependents(graph, symbol_id)]


@router.get("/{repo_id}/symbols/{symbol_id}/callers", response_model=list[DependencyResponse])
async def get_symbol_callers(
    repo_id: uuid.UUID,
    symbol_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[DependencyResponse]:
    await _get_repo_or_404(repo_id, db)
    graph = await build_repository_graph(repo_id, db)
    return [_dep_resp(n) for n in get_callers(graph, symbol_id)]


@router.get("/{repo_id}/symbols/{symbol_id}/callees", response_model=list[DependencyResponse])
async def get_symbol_callees(
    repo_id: uuid.UUID,
    symbol_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[DependencyResponse]:
    await _get_repo_or_404(repo_id, db)
    graph = await build_repository_graph(repo_id, db)
    return [_dep_resp(n) for n in get_callees(graph, symbol_id)]
