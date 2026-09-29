#!/usr/bin/env python
"""
Manual smoke test for the RepoPilot agent with a real LiteLLM-backed model.

Usage
-----
From the backend directory:

    uv run python scripts/verify_agent.py

Requirements
------------
- A valid LLM provider API key in the environment, e.g.:
    ANTHROPIC_API_KEY=sk-ant-...
  or
    OPENAI_API_KEY=sk-...
- LLM_MODEL set to a valid LiteLLM model string, e.g.:
    LLM_MODEL=anthropic/claude-haiku-4-5-20251001
  (if unset, defaults from settings are used)

The script:
1. Ingests the small fixture repository (tests/fixtures/ingestion/simple_repo).
2. Asks: "What does the run function do, and what does it call?"
3. Prints all tool calls, the final answer, and source references.

Does NOT write to any shared database — uses an in-memory SQLite session.
Does NOT modify the fixture repository.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the backend package is importable when run via `uv run python`
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(override=False)

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.database import Base
import app.db.models  # noqa: F401
from app.services.agent import AgentRequest, LiteLLMClient, run_agent
from app.services.ingestion.service import ingest_repository
from app.services.search.embeddings import SentenceTransformerProvider
from app.services.search.indexer import index_repository
from app.services.search.vector_store import ChromaVectorStore

FIXTURE_REPO = Path(__file__).parent.parent / "tests" / "fixtures" / "ingestion" / "simple_repo"
QUESTION = "What does the run function do, and what does it call?"


async def main() -> None:
    print("=" * 60)
    print("RepoPilot Agent — Manual Smoke Test")
    print("=" * 60)
    print(f"Model:      {settings.llm_model}")
    print(f"Repository: {FIXTURE_REPO}")
    print(f"Question:   {QUESTION}")
    print()

    # --- Database setup (in-memory SQLite) ---
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as db:
        # --- Ingest fixture repository ---
        print("Ingesting fixture repository...")
        result = await ingest_repository(db, str(FIXTURE_REPO))
        print(f"Ingested repository: {result.repository_id} ({result.total_files} files, {result.total_symbols} symbols)")
        print()

        # --- Embedding provider ---
        # NOTE: SentenceTransformerProvider may fail to load on Windows due to
        # PyTorch DLL restrictions under Windows Application Control.
        # The search_code tool will simply return empty results in that case.
        embedding_provider = None
        vector_store = None
        try:
            embedding_provider = SentenceTransformerProvider(settings.embedding_model)
            vector_store = ChromaVectorStore.ephemeral(settings.chroma_collection_name)
            print("Embedding provider loaded.")
            print("Indexing repository into ChromaDB...")
            index_result = await index_repository(
                db=db,
                repository_id=result.repository_id,
                embedding_provider=embedding_provider,
                vector_store=vector_store,
            )
            print(f"Indexed: {index_result.chunks_created} chunks created.")
        except Exception as exc:
            print(f"WARNING: embedding provider unavailable — search_code disabled: {exc}")
        print()

        # --- Run agent ---
        llm_client = LiteLLMClient(settings.llm_model)
        request = AgentRequest(repository_id=result.repository_id, question=QUESTION)

        print("Running agent...")
        print("-" * 60)

        try:
            response = await run_agent(
                request,
                db=db,
                llm_client=llm_client,
                embedding_provider=embedding_provider,
                vector_store=vector_store,
            )
        except Exception as exc:
            print(f"ERROR: Agent run failed: {exc}")
            print()
            print("If this is an authentication error, set the appropriate")
            print("API key environment variable (ANTHROPIC_API_KEY / OPENAI_API_KEY)")
            print("and verify LLM_MODEL matches an available model.")
            raise

        # --- Print results ---
        print()
        print("TOOL CALLS")
        print("-" * 40)
        if response.tools_used:
            for i, event in enumerate(response.tools_used, 1):
                status = "✓" if event.success else "✗"
                print(f"  {i}. [{status}] {event.tool_name}({event.arguments_summary}) — {event.duration_ms:.1f} ms")
        else:
            print("  (none)")

        print()
        print("ANSWER")
        print("-" * 40)
        print(response.answer)

        print()
        print("SOURCE REFERENCES")
        print("-" * 40)
        if response.sources:
            for src in response.sources:
                line_range = ""
                if src.start_line and src.end_line:
                    line_range = f":{src.start_line}-{src.end_line}"
                elif src.start_line:
                    line_range = f":{src.start_line}"
                symbol_suffix = f" — {src.symbol}()" if src.symbol else ""
                print(f"  {src.file_path}{line_range}{symbol_suffix}")
        else:
            print("  (none)")

        print()
        print("METADATA")
        print("-" * 40)
        print(f"  iterations: {response.iterations}")
        print(f"  truncated:  {response.truncated}")
        print(f"  model:      {response.model}")
        print()
        print("=" * 60)
        print("Smoke test complete.")


if __name__ == "__main__":
    asyncio.run(main())
