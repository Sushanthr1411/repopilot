"""
RepoPilot agent tool layer.

These tools give a future LLM agent controlled, repository-scoped access to
code intelligence derived from Steps 1–6 (parsing, ingestion, graph, search).

Public API
----------
Each tool is an async function that returns ToolResult[T].

    search_code(repository_id, query, top_k, *, db, embedding_provider, vector_store)
    inspect_symbol(repository_id, symbol_id=None, qualified_name=None, *, db)
    read_file(repository_id, file_path, start_line=None, end_line=None, *, db)
    get_dependencies(repository_id, symbol_id, relationship_types=None, *, db)
    get_dependents(repository_id, symbol_id, relationship_types=None, *, db)
    get_callers(repository_id, symbol_id, *, db)
    get_callees(repository_id, symbol_id, *, db)
    get_file_dependencies(repository_id, file_id, *, db)

Registry
--------
    REPOPILOT_TOOLS          — list[ToolDefinition] for all tools
    REPOPILOT_TOOLS_BY_NAME  — dict[str, ToolDefinition] keyed by tool name

Result types
------------
    ToolResult, ToolError, ToolErrorCode (see models.py)
"""

from app.tools.get_callees import get_callees
from app.tools.get_callers import get_callers
from app.tools.get_dependencies import get_dependencies
from app.tools.get_dependents import get_dependents
from app.tools.get_file_dependencies import get_file_dependencies
from app.tools.inspect_symbol import inspect_symbol
from app.tools.models import (
    CalleesResult,
    CallersResult,
    CodeSearchMatch,
    DependenciesResult,
    DependencyEntry,
    DependentsResult,
    FileDependenciesResult,
    FileDependencyEntry,
    FileContent,
    SearchCodeResult,
    SymbolDetail,
    SymbolRef,
    ToolError,
    ToolErrorCode,
    ToolResult,
)
from app.tools.read_file import read_file
from app.tools.registry import REPOPILOT_TOOLS, REPOPILOT_TOOLS_BY_NAME, ToolDefinition
from app.tools.search_code import search_code

__all__ = [
    # tool functions
    "search_code",
    "inspect_symbol",
    "read_file",
    "get_dependencies",
    "get_dependents",
    "get_callers",
    "get_callees",
    "get_file_dependencies",
    # registry
    "REPOPILOT_TOOLS",
    "REPOPILOT_TOOLS_BY_NAME",
    "ToolDefinition",
    # result models
    "ToolResult",
    "ToolError",
    "ToolErrorCode",
    "SymbolRef",
    "SearchCodeResult",
    "CodeSearchMatch",
    "SymbolDetail",
    "FileContent",
    "DependenciesResult",
    "DependentsResult",
    "DependencyEntry",
    "CallersResult",
    "CalleesResult",
    "FileDependenciesResult",
    "FileDependencyEntry",
]
