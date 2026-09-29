"""
Embedding provider abstraction.

EmbeddingProvider is a structural Protocol; any object that implements
embed_documents() and embed_query() satisfies it without inheriting from a
base class.

SentenceTransformerProvider
    Uses sentence-transformers.  The underlying SentenceTransformer model is
    cached in a module-level dict keyed by model name so the model is loaded
    once per process regardless of how many provider instances are created.

    Supports asymmetric models (like BGE/E5) through prompt_name="query" and
    prompt_name="document".  Falls back to plain encode() when the model does
    not declare those prompts.

FakeEmbeddingProvider
    Returns deterministic hash-based vectors; used for tests and CI where
    network access or GPU is not available.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Module-level model cache: model_name → SentenceTransformer instance
_MODEL_CACHE: dict[str, object] = {}


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Structural interface for embedding providers."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        ...


class SentenceTransformerProvider:
    """
    Embedding provider backed by sentence-transformers.

    The model is loaded lazily on first use and cached for the lifetime of
    the process.  Repeated calls with the same model_name reuse the cached
    instance.
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    @property
    def _model(self):
        if self._model_name not in _MODEL_CACHE:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            logger.info("Loading embedding model %r (first use)", self._model_name)
            _MODEL_CACHE[self._model_name] = SentenceTransformer(self._model_name)
        return _MODEL_CACHE[self._model_name]

    def _encode(self, texts: list[str], prompt_name: str | None = None) -> list[list[float]]:
        try:
            emb = self._model.encode(
                texts,
                prompt_name=prompt_name,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except (ValueError, KeyError):
            # Model doesn't support this prompt_name — fall back to plain encode
            emb = self._model.encode(
                texts,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return emb.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(texts, prompt_name="document")

    def embed_query(self, text: str) -> list[float]:
        result = self._encode([text], prompt_name="query")
        return result[0]


class OpenAIEmbeddingProvider:
    """
    Embedding provider using the OpenAI Embeddings API.

    Uses pure HTTPS — no compiled extensions required — so it works in
    environments where PyTorch DLLs are blocked (e.g. Windows App Control).

    Requires OPENAI_API_KEY in the environment.
    Default model: text-embedding-3-small (1536-dim).

    Do NOT mix with SentenceTransformerProvider vectors in the same ChromaDB
    collection — the dimension is different (1536 vs 384).
    """

    def __init__(self, model_name: str = "text-embedding-3-small") -> None:
        self._model_name = model_name
        self._client = None

    @property
    def _get_client(self):
        if self._client is None:
            from openai import OpenAI  # noqa: PLC0415
            self._client = OpenAI()
        return self._client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._get_client.embeddings.create(
            input=texts,
            model=self._model_name,
        )
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        result = self.embed_documents([text])
        return result[0]


class FakeEmbeddingProvider:
    """
    Deterministic embedding provider for tests.

    Produces hash-based vectors of a fixed dimension.  Same input always
    produces the same vector; similar inputs do NOT necessarily produce
    similar vectors (this is for correctness testing, not retrieval quality).
    """

    def __init__(self, dim: int = 8) -> None:
        self._dim = dim

    def _hash_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
        # Normalize to floats in [-1, 1] using pairs of bytes
        vals: list[float] = []
        for i in range(self._dim):
            byte = digest[i % len(digest)]
            vals.append((byte - 127.5) / 127.5)
        return vals

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._hash_vector(text)
