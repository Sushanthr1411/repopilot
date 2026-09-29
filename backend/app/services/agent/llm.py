"""
LLM client abstraction for the RepoPilot agent.

Design
------
LLMClient is a Protocol that the agent service depends on.  This keeps the
agent loop independent of the LiteLLM library and makes it straightforward to
inject a fake implementation in tests.

LiteLLMClient is the production implementation.  It uses LiteLLM's async
completion interface so it stays compatible with the rest of the async codebase.

All provider-specific details (API keys, base URLs, rate-limit handling) are
left to LiteLLM's own configuration system — typically via environment
variables such as ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types shared across implementations
# ---------------------------------------------------------------------------

@dataclass
class LLMToolCall:
    """A single tool call requested by the model in one response."""

    id: str           # opaque identifier; must be echoed back in tool result
    name: str         # tool name
    arguments: str    # raw JSON string of arguments as sent by the model


@dataclass
class LLMResponse:
    """
    Normalised response from the LLM.

    content     — text content of the assistant message (may be None or empty
                  when the model only returns tool calls)
    tool_calls  — zero or more tool calls requested in this turn
    model       — model string reported by the provider (informational)
    stop_reason — stop reason from the provider (informational)
    """

    content: str | None
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    model: str | None = None
    stop_reason: str | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMClient(Protocol):
    """
    Minimal interface for sending a conversation to an LLM.

    Implementations must be async-compatible.  The agent service calls this
    and nothing else from the LLM layer.
    """

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages:    Full conversation history in OpenAI message format.
            tools:       LiteLLM-compatible tool definitions (type=function).
                         None or empty list means no tools are offered.
            max_tokens:  Maximum tokens in the completion.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content and/or tool_calls populated.

        Raises:
            LLMError: on authentication failure, rate limiting, timeout, or
                      provider error.  See models.LLMError for retryable flag.
        """
        ...


# ---------------------------------------------------------------------------
# LiteLLM implementation
# ---------------------------------------------------------------------------

class LiteLLMClient:
    """
    LLM client backed by LiteLLM's async completion API.

    LiteLLM normalises the request/response format across providers, so this
    class does not need provider-specific logic.  Provider credentials are
    picked up from environment variables (e.g. ANTHROPIC_API_KEY).
    """

    def __init__(self, model: str) -> None:
        self._model = model

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        import litellm  # imported here so tests can mock without importing at module level
        from app.services.agent.models import LLMError

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await litellm.acompletion(**kwargs)
        except litellm.exceptions.AuthenticationError as exc:
            raise LLMError(f"LLM authentication failed: {exc}", retryable=False) from exc
        except litellm.exceptions.RateLimitError as exc:
            raise LLMError(f"LLM rate limit exceeded: {exc}", retryable=True) from exc
        except litellm.exceptions.Timeout as exc:
            raise LLMError(f"LLM request timed out: {exc}", retryable=True) from exc
        except litellm.exceptions.APIConnectionError as exc:
            raise LLMError(f"LLM connection error: {exc}", retryable=True) from exc
        except litellm.exceptions.BadRequestError as exc:
            raise LLMError(f"LLM bad request: {exc}", retryable=False) from exc
        except Exception as exc:
            logger.exception("LiteLLM unexpected error")
            raise LLMError(f"LLM error: {exc}", retryable=False) from exc

        choice = response.choices[0]
        message = choice.message

        tool_calls: list[LLMToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    LLMToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )

        content = message.content
        if content is not None and not content.strip():
            content = None

        logger.debug(
            "LiteLLM %s → %d tool calls, content=%s",
            self._model,
            len(tool_calls),
            "yes" if content else "none",
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=getattr(response, "model", self._model),
            stop_reason=str(choice.finish_reason) if choice.finish_reason else None,
        )
