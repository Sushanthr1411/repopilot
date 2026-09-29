"""
FastAPI dependency providers for RepoPilot AI.

Singletons are initialised lazily on first request.  Tests override these
via app.dependency_overrides before creating the test client, so the
production singletons are never instantiated during tests.
"""

from __future__ import annotations

from app.db.database import get_db  # noqa: F401 — re-exported for route imports

_embedding_provider = None
_vector_store = None
_llm_client = None


def get_embedding_provider():
    """Return the shared EmbeddingProvider singleton (lazy init).

    The concrete provider is chosen by settings.embedding_provider:
      "sentence_transformers"  →  SentenceTransformerProvider (default)
      "openai"                 →  OpenAIEmbeddingProvider (requires OPENAI_API_KEY)
    """
    global _embedding_provider
    if _embedding_provider is None:
        from app.core.config import settings
        if settings.embedding_provider == "openai":
            from app.services.search.embeddings import OpenAIEmbeddingProvider
            model = settings.embedding_model
            # If the admin forgot to change the model from the sentence-transformers
            # default, apply a sensible OpenAI default rather than sending a
            # nonsensical model name to the API.
            if model.startswith("sentence-transformers/"):
                model = "text-embedding-3-small"
            _embedding_provider = OpenAIEmbeddingProvider(model)
        else:
            from app.services.search.embeddings import SentenceTransformerProvider
            _embedding_provider = SentenceTransformerProvider(settings.embedding_model)
    return _embedding_provider


def get_vector_store():
    """Return the shared ChromaVectorStore singleton (lazy init)."""
    global _vector_store
    if _vector_store is None:
        from app.core.config import settings
        from app.services.search.vector_store import ChromaVectorStore
        _vector_store = ChromaVectorStore.from_settings(settings)
    return _vector_store


def get_llm_client():
    """Return the shared LLMClient singleton (lazy init)."""
    global _llm_client
    if _llm_client is None:
        from app.core.config import settings
        from app.services.agent.llm import LiteLLMClient
        _llm_client = LiteLLMClient(settings.llm_model)
    return _llm_client
