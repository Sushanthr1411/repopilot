"""
Tool adapter — bridges the Step 7 tool registry and the agent service.

Responsibilities
----------------
1.  Build model-facing LiteLLM tool definitions by stripping repository_id
    from every tool's input_schema (repository context is server-controlled).
2.  Validate model-supplied arguments.
3.  Inject trusted repository context (repository_id, db, embedding_provider,
    vector_store) before calling the underlying tool function.
4.  Serialize the ToolResult into a JSON string suitable for a role=tool message.
5.  Extract AgentSource references from successful tool results.

Security invariant
------------------
The model NEVER controls repository_id.  Any repository_id that appears in the
model's tool arguments is silently discarded; the trusted value from
AgentRequest is always used.  This is enforced in _inject_context().
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from dataclasses import asdict, fields, is_dataclass
from typing import Any

from app.services.agent.models import AgentSource, AgentToolEvent
from app.tools.registry import REPOPILOT_TOOLS, REPOPILOT_TOOLS_BY_NAME, ToolDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

def _to_json_safe(obj: Any) -> Any:
    """Recursively convert a value to a JSON-serialisable form."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_json_safe(getattr(obj, f.name)) for f in fields(obj)}
    # Fallback: let JSON handle it; raises TypeError for unknown types
    return obj


def _serialise_result(result: Any) -> str:
    """Serialise a ToolResult (or any dataclass/dict) to a JSON string."""
    try:
        safe = _to_json_safe(result)
        return json.dumps(safe)
    except (TypeError, ValueError) as exc:
        logger.warning("Could not serialise tool result: %s", exc)
        return json.dumps({"error": "result serialisation failed", "detail": str(exc)})


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _strip_repository_id(schema: dict) -> dict:
    """
    Return a copy of a JSON Schema with repository_id removed.

    The model does not control repository context; removing it from the
    schema prevents the model from passing it and from being confused by it.
    """
    schema = copy.deepcopy(schema)
    props: dict = schema.get("properties", {})
    props.pop("repository_id", None)
    required: list = [r for r in schema.get("required", []) if r != "repository_id"]
    schema["properties"] = props
    schema["required"] = required
    return schema


def build_litellm_tools(tools: list[ToolDefinition] | None = None) -> list[dict]:
    """
    Convert RepoPilot ToolDefinitions to LiteLLM-compatible tool definitions.

    Returns the standard OpenAI function-tool shape understood by LiteLLM and
    all major providers:

        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    """
    if tools is None:
        tools = REPOPILOT_TOOLS
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": _strip_repository_id(t.input_schema),
            },
        }
        for t in tools
    ]


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

def _validate_required_args(tool_def: ToolDefinition, args: dict) -> str | None:
    """
    Check that all required fields (excluding repository_id) are present.

    Returns an error string if validation fails, None if OK.
    """
    schema = tool_def.input_schema
    required: list[str] = [
        r for r in schema.get("required", []) if r != "repository_id"
    ]
    missing = [r for r in required if r not in args]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    return None


# ---------------------------------------------------------------------------
# Source extraction
# ---------------------------------------------------------------------------

def _extract_sources(tool_name: str, result_data: Any) -> list[AgentSource]:
    """
    Extract AgentSource references from a successful tool result data object.

    Only actual tool-result objects are processed; this never fabricates sources.
    """
    sources: list[AgentSource] = []

    if result_data is None:
        return sources

    # search_code → SearchCodeResult
    if tool_name == "search_code" and hasattr(result_data, "results"):
        for match in result_data.results:
            sources.append(AgentSource(
                file_path=match.file_path,
                start_line=match.start_line,
                end_line=match.end_line,
                symbol=match.symbol_name or match.qualified_name,
            ))

    # inspect_symbol → SymbolDetail
    elif tool_name == "inspect_symbol" and hasattr(result_data, "file_path"):
        sources.append(AgentSource(
            file_path=result_data.file_path,
            start_line=result_data.start_line,
            end_line=result_data.end_line,
            symbol=result_data.qualified_name or result_data.name,
        ))

    # read_file → FileContent
    elif tool_name == "read_file" and hasattr(result_data, "actual_start_line"):
        sources.append(AgentSource(
            file_path=result_data.file_path,
            start_line=result_data.actual_start_line,
            end_line=result_data.actual_end_line,
        ))

    # get_dependencies / get_dependents → DependenciesResult / DependentsResult
    elif tool_name in ("get_dependencies", "get_dependents") and hasattr(result_data, "source_symbol"):
        sym = getattr(result_data, "source_symbol", None) or getattr(result_data, "target_symbol", None)
        if sym:
            sources.append(AgentSource(
                file_path=sym.file_path,
                start_line=sym.start_line,
                end_line=sym.end_line,
                symbol=sym.qualified_name,
            ))

    # get_callers / get_callees → CallersResult / CalleesResult
    elif tool_name in ("get_callers", "get_callees") and hasattr(result_data, "target_symbol"):
        sym = getattr(result_data, "target_symbol", None) or getattr(result_data, "source_symbol", None)
        if sym:
            sources.append(AgentSource(
                file_path=sym.file_path,
                start_line=sym.start_line,
                end_line=sym.end_line,
                symbol=sym.qualified_name,
            ))

    return sources


# ---------------------------------------------------------------------------
# Argument summary (safe — no sensitive content)
# ---------------------------------------------------------------------------

_SUMMARY_FIELDS = ("query", "file_path", "qualified_name", "symbol_id", "file_id", "relationship_types")


def _summarise_args(args: dict) -> str:
    """Build a short, non-sensitive summary of tool arguments for AgentToolEvent."""
    parts = []
    for key in _SUMMARY_FIELDS:
        if key in args:
            val = args[key]
            if isinstance(val, str) and len(val) > 60:
                val = val[:57] + "..."
            parts.append(f'{key}={json.dumps(val)}')
    if not parts:
        # Fallback: list key names only (no values that could contain repo content)
        parts = list(args.keys())
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Bound tool adapter
# ---------------------------------------------------------------------------

class BoundToolAdapter:
    """
    Executes model-selected tools with trusted repository context injected.

    The adapter is bound to a specific repository_id, db session, and optional
    infrastructure dependencies (embedding_provider, vector_store).  The model
    never sees or controls these values.
    """

    def __init__(
        self,
        repository_id: uuid.UUID,
        db: Any,
        embedding_provider: Any = None,
        vector_store: Any = None,
    ) -> None:
        self._repository_id = repository_id
        self._db = db
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    def _inject_context(self, tool_name: str, args: dict) -> dict:
        """
        Build the full kwargs dict for the underlying tool function.

        - Discards any repository_id that the model may have included.
        - Injects the trusted repository_id, db, and any infrastructure deps.
        """
        # Start from validated model args; never trust model-supplied repository_id
        clean = {k: v for k, v in args.items() if k != "repository_id"}

        # Convert string UUIDs to uuid.UUID objects for fields that need them
        for key in ("symbol_id", "file_id"):
            if key in clean and isinstance(clean[key], str):
                try:
                    clean[key] = uuid.UUID(clean[key])
                except ValueError:
                    pass  # validation will catch this downstream

        # Convert relationship_types elements if needed
        if "relationship_types" in clean and not isinstance(clean["relationship_types"], list):
            clean["relationship_types"] = None

        # Inject trusted context
        clean["repository_id"] = self._repository_id
        clean["db"] = self._db
        if tool_name == "search_code":
            clean["embedding_provider"] = self._embedding_provider
            clean["vector_store"] = self._vector_store

        return clean

    async def execute(
        self,
        tool_name: str,
        raw_arguments: str,
    ) -> tuple[str, bool, list[AgentSource]]:
        """
        Execute a tool call and return (json_result, success, sources).

        Args:
            tool_name:      Name of the RepoPilot tool.
            raw_arguments:  Raw JSON string from the model's tool call.

        Returns:
            A triple:
            - json_result  — JSON string suitable for a role=tool message
            - success      — True if the tool returned success=True
            - sources      — AgentSource objects extracted from the result
        """
        # 1. Identify tool
        if tool_name not in REPOPILOT_TOOLS_BY_NAME:
            error_payload = {"error": f"unknown tool: {repr(tool_name)}"}
            return json.dumps(error_payload), False, []

        tool_def = REPOPILOT_TOOLS_BY_NAME[tool_name]

        # 2. Parse arguments
        try:
            args: dict = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except json.JSONDecodeError as exc:
            error_payload = {"error": f"invalid JSON arguments: {exc}"}
            return json.dumps(error_payload), False, []

        if not isinstance(args, dict):
            error_payload = {"error": "tool arguments must be a JSON object"}
            return json.dumps(error_payload), False, []

        # 3. Validate required fields
        validation_error = _validate_required_args(tool_def, args)
        if validation_error:
            error_payload = {"error": f"argument validation failed: {validation_error}"}
            return json.dumps(error_payload), False, []

        # 4. Inject trusted context
        kwargs = self._inject_context(tool_name, args)

        # 5. Execute
        try:
            result = await tool_def.fn(**kwargs)
        except Exception as exc:
            logger.exception("Tool %s raised an unexpected exception", tool_name)
            error_payload = {"error": f"tool execution failed: {exc}"}
            return json.dumps(error_payload), False, []

        # 6. Extract sources from successful results
        sources: list[AgentSource] = []
        if result.success and result.data is not None:
            sources = _extract_sources(tool_name, result.data)

        return _serialise_result(result), result.success, sources

    async def execute_with_event(
        self,
        tool_name: str,
        raw_arguments: str,
    ) -> tuple[str, AgentToolEvent, list[AgentSource]]:
        """
        Execute a tool and return (json_result, event, sources).

        Convenience wrapper that also produces the AgentToolEvent record.
        """
        try:
            args: dict = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except (json.JSONDecodeError, ValueError):
            args = {}

        summary = _summarise_args({k: v for k, v in args.items() if k != "repository_id"})

        t0 = time.perf_counter()
        json_result, success, sources = await self.execute(tool_name, raw_arguments)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        event = AgentToolEvent(
            tool_name=tool_name,
            arguments_summary=summary,
            success=success,
            duration_ms=duration_ms,
        )
        return json_result, event, sources
