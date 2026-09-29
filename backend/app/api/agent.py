"""
Agent endpoint.

POST  /{repo_id}/ask   ask a question about the repository
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Repository
from app.deps import get_db, get_embedding_provider, get_llm_client, get_vector_store
from app.schemas.agent import AgentSourceResponse, AgentToolEventResponse, AskRequest, AskResponse
from app.services.agent import AgentRequest, run_agent

router = APIRouter()


@router.post("/{repo_id}/ask", response_model=AskResponse)
async def ask(
    repo_id: uuid.UUID,
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    llm_client=Depends(get_llm_client),
    embedding_provider=Depends(get_embedding_provider),
    vector_store=Depends(get_vector_store),
) -> AskResponse:
    repo = await db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Repository {repo_id} not found"},
        )

    if repo.status != "ready":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "NOT_READY",
                "message": (
                    f"Repository must be successfully ingested before querying "
                    f"(current status={repo.status!r})"
                ),
            },
        )

    response = await run_agent(
        AgentRequest(repository_id=repo_id, question=body.question),
        db=db,
        llm_client=llm_client,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )

    return AskResponse(
        answer=response.answer,
        sources=[
            AgentSourceResponse(
                file_path=s.file_path,
                start_line=s.start_line,
                end_line=s.end_line,
                symbol=s.symbol,
            )
            for s in response.sources
        ],
        tools_used=[
            AgentToolEventResponse(
                tool_name=e.tool_name,
                arguments_summary=e.arguments_summary,
                success=e.success,
                duration_ms=e.duration_ms,
            )
            for e in response.tools_used
        ],
        iterations=response.iterations,
        truncated=response.truncated,
        model=response.model,
    )
