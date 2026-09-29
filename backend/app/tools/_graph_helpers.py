"""
Internal helpers shared by the graph-based agent tools.

These are NOT part of the public tool API.
"""

from __future__ import annotations

import uuid

from app.services.graph.models import GraphNode
from app.tools.models import SymbolRef


def sym_ref(node: GraphNode) -> SymbolRef:
    """Convert a GraphNode to a SymbolRef for tool output."""
    return SymbolRef(
        symbol_id=node.symbol_id,
        name=node.name,
        qualified_name=node.qualified_name,
        symbol_type=node.symbol_type,
        file_path=node.file_path,
        start_line=node.start_line,
        end_line=node.end_line,
    )
