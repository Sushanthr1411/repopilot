# RepoPilot AI

Agentic codebase intelligence platform for analysing and understanding Python repositories.

Give RepoPilot a Python repository and ask it to explain the codebase. The agent uses static analysis, a code graph, and semantic search to ground its answers in actual source evidence rather than generic AI knowledge.

---

## Architecture

```
Python repository
       ↓
  [Parser]      ast-based symbol + relationship extraction
       ↓
  [Ingestion]   persist to PostgreSQL (files, symbols, relationships)
       ↓
  [Indexer]     chunk → embed (sentence-transformers) → ChromaDB
       ↓
  [Agent]       user question → LiteLLM → tool calls → grounded answer
       ↓
  [REST API]    FastAPI, Pydantic schemas, /api/v1/...
```

**Technology stack**: Python 3.11 · FastAPI · SQLAlchemy 2 · PostgreSQL · Alembic · ChromaDB · sentence-transformers · LiteLLM · NetworkX · pytest

---

## Setup

### Prerequisites

- Python 3.11
- [uv](https://docs.astral.sh/uv/) (`pip install uv`)
- PostgreSQL (for production) or SQLite via aiosqlite (tests only)

### Install dependencies

```bash
cd backend
uv sync
```

### Configure environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL and any API keys
```

Key environment variables:

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async URL | `postgresql+asyncpg://...` |
| `EMBEDDING_PROVIDER` | `sentence_transformers` or `openai` | `sentence_transformers` |
| `EMBEDDING_MODEL` | Model name for the selected provider | `sentence-transformers/all-MiniLM-L6-v2` |
| `CHROMA_PERSIST_DIRECTORY` | ChromaDB storage path | `./data/chroma` |
| `LLM_MODEL` | LiteLLM model string — e.g. `gemini/gemini-2.0-flash`, `anthropic/claude-haiku-4-5-20251001` | (required for /ask) |
| `GEMINI_API_KEY` | Google AI Studio key for Gemini models | — |
| `ANTHROPIC_API_KEY` | API key for Anthropic models | — |
| `OPENAI_API_KEY` | API key for OpenAI models (also enables `EMBEDDING_PROVIDER=openai`) | — |
| `CORS_ALLOW_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000` |
| `ALLOWED_REPO_ROOT` | Security boundary for repo paths (empty = any valid absolute path) | `""` |

> **Embedding provider on Windows App Control machines**: PyTorch DLLs may be blocked
> by Windows App Control policy, which prevents `sentence_transformers` from loading.
> Set `EMBEDDING_PROVIDER=openai` and `EMBEDDING_MODEL=text-embedding-3-small` to use
> the OpenAI Embeddings API instead (pure HTTPS, no compiled extensions required).
> Do not mix providers in the same ChromaDB collection — vector dimensions differ.

### Run database migrations

```bash
cd backend
uv run alembic upgrade head
```

### Start the development server

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## API

Base URL: `http://localhost:8000`

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/v1/health` | Health check (v1) |

### Repositories

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/repositories` | Register a repository |
| `GET` | `/api/v1/repositories/{id}` | Repository detail + stats |
| `POST` | `/api/v1/repositories/{id}/ingest` | Parse + index (synchronous) |
| `POST` | `/api/v1/repositories/{id}/index` | Re-index (re-embed existing ingestion) |

### Files

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/repositories/{id}/files` | List files (paginated) |
| `GET` | `/api/v1/repositories/{id}/files/{file_id}` | File content (optional `?start_line=&end_line=`) |

### Symbols

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/repositories/{id}/symbols` | List symbols (paginated, filterable) |
| `GET` | `/api/v1/repositories/{id}/symbols/{symbol_id}` | Symbol detail |

Query parameters for list: `limit`, `offset`, `symbol_type`, `name` (substring match).

### Code Graph

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/repositories/{id}/graph` | Full repository graph (nodes + edges) |
| `GET` | `/api/v1/repositories/{id}/symbols/{symbol_id}/dependencies` | Symbols this symbol depends on |
| `GET` | `/api/v1/repositories/{id}/symbols/{symbol_id}/dependents` | Symbols that depend on this one |
| `GET` | `/api/v1/repositories/{id}/symbols/{symbol_id}/callers` | Symbols that call this one |
| `GET` | `/api/v1/repositories/{id}/symbols/{symbol_id}/callees` | Symbols this one calls |

### Search

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/repositories/{id}/search` | Semantic code search |

Request body: `{"query": "...", "top_k": 10}`

### Agent

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/repositories/{id}/ask` | Ask a question about the repository |

Request body: `{"question": "..."}`

Response includes the answer, source references (`file_path:start_line-end_line`), tool events, and model metadata.

---

## Typical workflow

```bash
# 1 — Register a repository
curl -X POST http://localhost:8000/api/v1/repositories \
  -H "Content-Type: application/json" \
  -d '{"name": "my-project", "local_path": "/path/to/my-project"}'
# → {"id": "<repo-id>", "status": "pending", ...}

# 2 — Ingest + index it
curl -X POST http://localhost:8000/api/v1/repositories/<repo-id>/ingest
# → {"status": "ready", "total_files": 42, "total_symbols": 380, ...}

# 3 — Ask a question
curl -X POST http://localhost:8000/api/v1/repositories/<repo-id>/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How does authentication work?"}'
# → {"answer": "...", "sources": [{"file_path": "auth/service.py", ...}], ...}
```

---

## Development

### Run tests

```bash
cd backend
uv run pytest -q
```

Tests use an in-memory SQLite database and fake embedding/LLM providers — no external services required.

### Interactive API docs

Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### End-to-end verification

```bash
cd backend
uv run python scripts/verify_e2e.py
```

Exercises the full HTTP pipeline (registration → ingestion → files → symbols → graph →
indexing → search → agent) using in-memory SQLite and a fake embedding/LLM provider.
Reports a clear PASS / FAIL / BLOCKED / NOT CONFIGURED checklist for each component.
Set `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` before running to include the real-provider probes.

### Manual agent smoke test

```bash
cd backend
# Requires a real LLM API key
ANTHROPIC_API_KEY=sk-ant-... uv run python scripts/verify_agent.py
```

---

## Security

- Analysed repository code is never executed — analysis is static-only.
- Set `ALLOWED_REPO_ROOT` in production to restrict which directories may be registered as repositories.
- The AI agent cannot execute shell commands or modify the analysed repository.
- Never commit `.env` files or API keys.
