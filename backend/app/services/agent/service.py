"""
RepoPilot agent service — the agentic tool-calling loop.

run_agent() is the single entry point.  It:
1.  Builds the initial conversation with the system prompt and user question.
2.  Calls the LLM client (LiteLLMClient in production, FakeLLMClient in tests).
3.  If the model returns tool calls, executes each one via BoundToolAdapter.
4.  Appends the assistant message and all tool results to the conversation.
5.  Repeats until the model returns a plain answer or a loop limit is hit.
6.  Returns an AgentResponse with the answer, sources, and tool activity.

Loop limits
-----------
AGENT_MAX_ITERATIONS  — maximum number of LLM call rounds
AGENT_MAX_TOOL_CALLS  — maximum total tool invocations across all rounds

Both limits are checked before each round.  When either is exceeded, the agent
returns whatever content is available with truncated=True.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.config import settings
from app.services.agent.llm import LLMClient, LLMResponse
from app.services.agent.models import (
    AgentError,
    AgentRequest,
    AgentResponse,
    AgentSource,
    AgentToolEvent,
    LLMError,
)
from app.services.agent.prompts import SYSTEM_PROMPT
from app.services.agent.tool_adapter import BoundToolAdapter, build_litellm_tools
from app.tools.registry import REPOPILOT_TOOLS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def _make_assistant_message(response: LLMResponse) -> dict:
    """Build the role=assistant message for the next LLM turn."""
    msg: dict = {"role": "assistant", "content": response.content or ""}
    if response.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": tc.arguments,
                },
            }
            for tc in response.tool_calls
        ]
    return msg


def _make_tool_result_message(tool_call_id: str, content: str) -> dict:
    """Build the role=tool message for one tool result."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_agent(
    request: AgentRequest,
    *,
    db: Any,
    llm_client: LLMClient,
    embedding_provider: Any = None,
    vector_store: Any = None,
    max_iterations: int | None = None,
    max_tool_calls: int | None = None,
) -> AgentResponse:
    """
    Run one complete agent conversation turn.

    Args:
        request:            AgentRequest with repository_id and question.
        db:                 Open AsyncSession for tool DB access.
        llm_client:         LLMClient implementation (LiteLLMClient or fake).
        embedding_provider: Required for search_code; may be None if not using search.
        vector_store:       Required for search_code; may be None if not using search.
        max_iterations:     Override settings.agent_max_iterations for this run.
        max_tool_calls:     Override settings.agent_max_tool_calls for this run.

    Returns:
        AgentResponse — never raises for expected agent-loop failures.
    """
    _max_iter = max_iterations if max_iterations is not None else settings.agent_max_iterations
    _max_calls = max_tool_calls if max_tool_calls is not None else settings.agent_max_tool_calls

    adapter = BoundToolAdapter(
        repository_id=request.repository_id,
        db=db,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )
    litellm_tools = build_litellm_tools(REPOPILOT_TOOLS)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": request.question},
    ]

    all_sources: list[AgentSource] = []
    all_events: list[AgentToolEvent] = []
    total_tool_calls = 0
    iterations = 0
    truncated = False
    final_answer: str | None = None
    used_model: str | None = None

    for iteration in range(_max_iter):
        iterations = iteration + 1

        # Check total tool-call budget before each LLM call
        if total_tool_calls >= _max_calls:
            logger.warning(
                "Agent hit tool-call limit (%d) after %d iterations",
                _max_calls, iterations,
            )
            truncated = True
            break

        # --- LLM call ---
        try:
            response = await llm_client.complete(
                messages=messages,
                tools=litellm_tools if litellm_tools else None,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
        except LLMError as exc:
            logger.error("LLM error during agent run: %s", exc)
            return AgentResponse(
                answer=f"The AI assistant encountered an error: {exc}",
                sources=all_sources,
                tools_used=all_events,
                iterations=iterations,
                truncated=True,
                model=used_model,
            )
        except Exception as exc:
            logger.exception("Unexpected error during LLM call")
            return AgentResponse(
                answer=f"An unexpected error occurred: {exc}",
                sources=all_sources,
                tools_used=all_events,
                iterations=iterations,
                truncated=True,
                model=used_model,
            )

        if used_model is None and response.model:
            used_model = response.model

        # --- No tool calls: this is the final answer ---
        if not response.tool_calls:
            final_answer = response.content or ""
            break

        # --- Tool calls: execute each one, then continue the loop ---

        # Check that executing these calls won't exceed the budget
        remaining = _max_calls - total_tool_calls
        tool_calls_this_round = response.tool_calls[:remaining]
        if len(tool_calls_this_round) < len(response.tool_calls):
            truncated = True

        # Append the assistant message (MUST include tool_calls to be valid)
        messages.append(_make_assistant_message(response))

        for tc in tool_calls_this_round:
            json_result, event, sources = await adapter.execute_with_event(
                tc.name, tc.arguments
            )
            all_events.append(event)
            all_sources.extend(sources)
            total_tool_calls += 1

            messages.append(_make_tool_result_message(tc.id, json_result))

            logger.debug(
                "Tool %s → success=%s (%.1f ms)",
                tc.name, event.success, event.duration_ms,
            )

    else:
        # Loop exhausted without a plain-text final answer
        truncated = True

    # De-duplicate sources preserving insertion order
    seen: set[tuple] = set()
    unique_sources: list[AgentSource] = []
    for s in all_sources:
        key = (s.file_path, s.start_line, s.end_line, s.symbol)
        if key not in seen:
            seen.add(key)
            unique_sources.append(s)

    if final_answer is None:
        # Extract any text from the last assistant message in history
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                final_answer = msg["content"]
                break
        if final_answer is None:
            final_answer = (
                "Analysis was bounded by the iteration limit. "
                "Please refine your question or increase AGENT_MAX_ITERATIONS."
            )

    logger.info(
        "Agent completed: %d iterations, %d tool calls, truncated=%s",
        iterations, total_tool_calls, truncated,
    )

    return AgentResponse(
        answer=final_answer,
        sources=unique_sources,
        tools_used=all_events,
        iterations=iterations,
        truncated=truncated,
        model=used_model,
    )
