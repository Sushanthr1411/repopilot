"""
Data models for the RepoPilot agent layer.

These are the public-facing types that callers receive.  They are deliberately
separated from the internal LiteLLM response objects so the rest of the
application never depends on provider-specific classes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class AgentRequest:
    """Input to the agent."""

    repository_id: uuid.UUID
    question: str


@dataclass
class AgentSource:
    """
    A grounded source reference extracted from a tool result.

    Corresponds to the readable form: services/auth.py:20-42 — authenticate()
    """

    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None   # symbol name / qualified_name if available


@dataclass
class AgentToolEvent:
    """
    A record of one tool invocation during an agent run.

    Intentionally stores only a *summary* of arguments — not the full payload —
    to avoid accidentally surfacing sensitive repository content in logs or UI.
    """

    tool_name: str
    arguments_summary: str   # e.g. 'query="authentication login"'
    success: bool
    duration_ms: float


@dataclass
class AgentResponse:
    """
    The final output of one agent run.

    answer      — the grounded natural-language answer
    sources     — file/line references extracted from actual tool results
    tools_used  — ordered list of tool invocations performed
    iterations  — number of LLM call rounds completed
    truncated   — True when the iteration or tool-call limit was hit
    model       — LiteLLM model string used (informational)
    """

    answer: str
    sources: list[AgentSource] = field(default_factory=list)
    tools_used: list[AgentToolEvent] = field(default_factory=list)
    iterations: int = 0
    truncated: bool = False
    model: str | None = None


# ---------------------------------------------------------------------------
# Internal exceptions
# ---------------------------------------------------------------------------

class AgentError(Exception):
    """Base class for agent-layer errors."""


class LLMError(AgentError):
    """Raised when the LLM call itself fails (auth, rate limit, timeout …)."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class AgentConfigError(AgentError):
    """Raised when the agent is misconfigured (bad model name, missing key …)."""
