# Load .env into os.environ before any library (LiteLLM, sentence-transformers)
# reads provider API keys.  pydantic-settings populates Settings fields from .env
# but does not write to os.environ, so third-party libraries that read os.environ
# directly (e.g. GEMINI_API_KEY, ANTHROPIC_API_KEY) would otherwise miss them.
from dotenv import load_dotenv
load_dotenv(override=False)  # shell env vars take precedence over .env

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.api.files import router as files_router
from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.repositories import router as repositories_router
from app.api.search import router as search_router
from app.api.symbols import router as symbols_router
from app.core.config import settings

app = FastAPI(
    title="RepoPilot AI",
    description="Agentic codebase intelligence platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health — legacy /api/health + /api/v1/health (both served by the same router)
app.include_router(health_router, prefix="/api", tags=["health"])

# v1 resource endpoints
app.include_router(repositories_router, prefix="/api/v1/repositories", tags=["repositories"])
app.include_router(files_router, prefix="/api/v1/repositories", tags=["files"])
app.include_router(symbols_router, prefix="/api/v1/repositories", tags=["symbols"])
app.include_router(graph_router, prefix="/api/v1/repositories", tags=["graph"])
app.include_router(search_router, prefix="/api/v1/repositories", tags=["search"])
app.include_router(agent_router, prefix="/api/v1/repositories", tags=["agent"])
