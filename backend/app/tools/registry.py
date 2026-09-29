"""
Tool registry for RepoPilot AI.

REPOPILOT_TOOLS is a list of ToolDefinition objects describing every agent
tool.  Step 8 will use these definitions to convert them to LiteLLM / model
tool-calling format.

Design constraints
------------------
- The tool functions themselves do NOT depend on this registry.
- Each ToolDefinition carries enough metadata for a future adapter to produce
  provider-specific request payloads (name, description, input_schema).
- input_schema follows the JSON Schema draft-07 / OpenAI function-calling
  convention: type="object", a "properties" dict, a "required" list.
- The callable is the raw async tool function — adapters wrap it as needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.tools.get_callees import get_callees
from app.tools.get_callers import get_callers
from app.tools.get_dependencies import get_dependencies
from app.tools.get_dependents import get_dependents
from app.tools.get_file_dependencies import get_file_dependencies
from app.tools.inspect_symbol import inspect_symbol
from app.tools.read_file import read_file
from app.tools.search_code import search_code


@dataclass
class ToolDefinition:
    """Metadata + callable for one RepoPilot agent tool."""

    name: str
    description: str
    input_schema: dict   # JSON Schema (object with properties + required)
    fn: Callable         # the async tool function


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_SEARCH_CODE = ToolDefinition(
    name="search_code",
    description=(
        "Semantic search over code in a repository. "
        "Use this to find relevant functions, classes, or modules by describing "
        "what the code does in natural language."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repository_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the repository to search.",
            },
            "query": {
                "type": "string",
                "description": "Natural-language description of the code to find.",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5, max 20).",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["repository_id", "query"],
    },
    fn=search_code,
)

_INSPECT_SYMBOL = ToolDefinition(
    name="inspect_symbol",
    description=(
        "Retrieve detailed information about a named code symbol, including its "
        "signature, docstring, source code, and location. "
        "Provide either symbol_id (UUID) or qualified_name (e.g. 'utils.process')."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repository_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the repository.",
            },
            "symbol_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the symbol (takes precedence over qualified_name).",
            },
            "qualified_name": {
                "type": "string",
                "description": "Fully-qualified name, e.g. 'services.auth.authenticate'.",
            },
        },
        "required": ["repository_id"],
    },
    fn=inspect_symbol,
)

_READ_FILE = ToolDefinition(
    name="read_file",
    description=(
        "Read source code from a repository file. "
        "Optionally restrict to a line range. "
        "Use repository-relative paths only (e.g. 'services/auth.py')."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repository_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the repository.",
            },
            "file_path": {
                "type": "string",
                "description": "Repository-relative path to the file.",
            },
            "start_line": {
                "type": "integer",
                "description": "First line to read, 1-indexed (default: start of file).",
                "minimum": 1,
            },
            "end_line": {
                "type": "integer",
                "description": "Last line to read, 1-indexed inclusive (default: end of file).",
                "minimum": 1,
            },
        },
        "required": ["repository_id", "file_path"],
    },
    fn=read_file,
)

_GET_DEPENDENCIES = ToolDefinition(
    name="get_dependencies",
    description=(
        "Return symbols that a given symbol directly depends on (outgoing graph edges). "
        "Optionally filter by relationship type, e.g. ['CALLS'] or ['IMPORTS']."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repository_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the repository.",
            },
            "symbol_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the source symbol.",
            },
            "relationship_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relationship types to include. Omit for all types.",
            },
        },
        "required": ["repository_id", "symbol_id"],
    },
    fn=get_dependencies,
)

_GET_DEPENDENTS = ToolDefinition(
    name="get_dependents",
    description=(
        "Return symbols that directly depend on a given symbol (incoming graph edges). "
        "Optionally filter by relationship type."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repository_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the repository.",
            },
            "symbol_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the target symbol.",
            },
            "relationship_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relationship types to include. Omit for all types.",
            },
        },
        "required": ["repository_id", "symbol_id"],
    },
    fn=get_dependents,
)

_GET_CALLERS = ToolDefinition(
    name="get_callers",
    description=(
        "Return symbols that directly call a given symbol (CALLS edges only). "
        "Use this to find where a function is invoked."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repository_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the repository.",
            },
            "symbol_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the called symbol.",
            },
        },
        "required": ["repository_id", "symbol_id"],
    },
    fn=get_callers,
)

_GET_CALLEES = ToolDefinition(
    name="get_callees",
    description=(
        "Return symbols directly called by a given symbol (CALLS edges only). "
        "Use this to see what a function calls."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repository_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the repository.",
            },
            "symbol_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the calling symbol.",
            },
        },
        "required": ["repository_id", "symbol_id"],
    },
    fn=get_callees,
)

_GET_FILE_DEPENDENCIES = ToolDefinition(
    name="get_file_dependencies",
    description=(
        "Return file-level dependencies for a given file. "
        "Symbol-level edges that cross a file boundary are collapsed into "
        "one entry per target file, with relationship types and edge counts."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repository_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the repository.",
            },
            "file_id": {
                "type": "string",
                "format": "uuid",
                "description": "UUID of the source file.",
            },
        },
        "required": ["repository_id", "file_id"],
    },
    fn=get_file_dependencies,
)


# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

REPOPILOT_TOOLS: list[ToolDefinition] = [
    _SEARCH_CODE,
    _INSPECT_SYMBOL,
    _READ_FILE,
    _GET_DEPENDENCIES,
    _GET_DEPENDENTS,
    _GET_CALLERS,
    _GET_CALLEES,
    _GET_FILE_DEPENDENCIES,
]

# Convenience lookup: tool name → ToolDefinition
REPOPILOT_TOOLS_BY_NAME: dict[str, ToolDefinition] = {
    t.name: t for t in REPOPILOT_TOOLS
}
