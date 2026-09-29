"""
ChromaDB adapter.

All ChromaDB interaction is isolated here.  The rest of the application
never imports chromadb directly.

ChromaVectorStore wraps a Chroma client and one named collection.

Repository isolation is enforced at query time via metadata filtering:
    where={"repository_id": str(repository_id)}

Stable vector IDs
-----------------
Every Chroma document ID is str(CodeChunk.id).  This makes upserts
idempotent and allows targeted deletion without a scan.

Score convention
----------------
The collection uses cosine distance (hnsw:space="cosine").
Distances returned by Chroma range from 0 (identical) to 2 (maximally
different).  The field is named `distance` throughout to avoid confusion
with a similarity score.

Factory methods
---------------
ChromaVectorStore.from_settings(settings)  — persistent local storage
ChromaVectorStore.ephemeral(collection_name)  — in-memory (for tests)
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

from app.services.search.models import VectorResult

logger = logging.getLogger(__name__)

_CHROMA_METADATA = {"hnsw:space": "cosine"}
_BATCH_SIZE = 100  # maximum items per Chroma upsert call


class ChromaVectorStore:
    """
    Wrapper around a single ChromaDB collection.

    The underlying chromadb client is held as an instance attribute.
    The collection is fetched lazily on first access so the constructor
    does not perform I/O.
    """

    def __init__(self, client, collection_name: str) -> None:  # type: ignore[type-arg]
        self._client = client
        self._collection_name = collection_name
        self._collection = None  # lazily initialized

    # ------------------------------------------------------------------ #
    # Factory methods                                                      #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_settings(cls, settings: "Settings") -> "ChromaVectorStore":
        """Create a persistent store backed by the configured local directory."""
        import chromadb  # noqa: PLC0415
        client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        return cls(client, settings.chroma_collection_name)

    @classmethod
    def ephemeral(cls, collection_name: str = "repopilot_test") -> "ChromaVectorStore":
        """Create an in-memory store.  Useful for tests — no disk I/O."""
        import chromadb  # noqa: PLC0415
        client = chromadb.EphemeralClient()
        return cls(client, collection_name)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _get_collection(self):
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata=_CHROMA_METADATA,
            )
        return self._collection

    # ------------------------------------------------------------------ #
    # Write operations                                                     #
    # ------------------------------------------------------------------ #

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """
        Upsert documents into the collection in batches.

        Existing documents with the same IDs are replaced.
        """
        if not ids:
            return
        col = self._get_collection()
        for start in range(0, len(ids), _BATCH_SIZE):
            end = start + _BATCH_SIZE
            col.upsert(
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )
        logger.debug("Upserted %d vectors into collection %r", len(ids), self._collection_name)

    def delete_by_ids(self, ids: list[str]) -> None:
        """Delete specific documents by their IDs."""
        if not ids:
            return
        col = self._get_collection()
        for start in range(0, len(ids), _BATCH_SIZE):
            col.delete(ids=ids[start : start + _BATCH_SIZE])
        logger.debug("Deleted %d vectors from collection %r", len(ids), self._collection_name)

    # ------------------------------------------------------------------ #
    # Read operations                                                      #
    # ------------------------------------------------------------------ #

    def get_ids_for_repository(self, repository_id: str) -> list[str]:
        """Return all document IDs belonging to the given repository."""
        col = self._get_collection()
        try:
            results = col.get(
                where={"repository_id": repository_id},
                include=[],  # IDs only
            )
            return results.get("ids", [])
        except Exception:
            return []

    def query(
        self,
        query_embedding: list[float],
        repository_id: str,
        top_k: int,
    ) -> list[VectorResult]:
        """
        Semantic search within one repository.

        Returns up to top_k VectorResult objects ordered by cosine distance
        (ascending — closer = more relevant).
        """
        if top_k <= 0:
            return []

        col = self._get_collection()
        count = col.count()
        if count == 0:
            return []

        n = min(top_k, count)
        try:
            raw = col.query(
                query_embeddings=[query_embedding],
                n_results=n,
                where={"repository_id": repository_id},
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("Chroma query failed: %s", exc)
            return []

        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        results: list[VectorResult] = []
        for cid, doc, meta, dist in zip(ids, docs, metas, dists):
            results.append(VectorResult(
                chunk_id=cid,
                content=doc,
                metadata=meta,
                distance=dist,
            ))
        return results
