"""
RepoPilot agent service.

Public API
----------
    run_agent(request, *, db, llm_client, embedding_provider, vector_store)
        → AgentResponse

    LiteLLMClient(model)   — production LLM client
    LLMClient              — Protocol for dependency injection / testing

Models
------
    AgentRequest, AgentResponse, AgentSource, AgentToolEvent
    AgentError, LLMError, AgentConfigError
"""

from app.services.agent.llm import LiteLLMClient, LLMClient, LLMResponse, LLMToolCall
from app.services.agent.models import (
    AgentConfigError,
    AgentError,
    AgentRequest,
    AgentResponse,
    AgentSource,
    AgentToolEvent,
    LLMError,
)
from app.services.agent.service import run_agent
from app.services.agent.tool_adapter import BoundToolAdapter, build_litellm_tools

__all__ = [
    # entry point
    "run_agent",
    # models
    "AgentRequest",
    "AgentResponse",
    "AgentSource",
    "AgentToolEvent",
    "AgentError",
    "LLMError",
    "AgentConfigError",
    # LLM client
    "LLMClient",
    "LiteLLMClient",
    "LLMResponse",
    "LLMToolCall",
    # adapter utilities
    "BoundToolAdapter",
    "build_litellm_tools",
]
