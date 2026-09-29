from __future__ import annotations

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str


class AgentToolEventResponse(BaseModel):
    tool_name: str
    arguments_summary: str
    success: bool
    duration_ms: float


class AgentSourceResponse(BaseModel):
    file_path: str
    start_line: int | None
    end_line: int | None
    symbol: str | None


class AskResponse(BaseModel):
    answer: str
    sources: list[AgentSourceResponse]
    tools_used: list[AgentToolEventResponse]
    iterations: int
    truncated: bool
    model: str | None
