"""
RepoPilot AI — Repository ingestion service.

Usage:
    from app.services.ingestion import ingest_repository, IngestionResult

    result = await ingest_repository(db_session, "/path/to/repo")
    await db_session.commit()
"""

from app.services.ingestion.models import IngestionResult
from app.services.ingestion.service import ingest_existing_repository, ingest_repository

__all__ = ["ingest_repository", "ingest_existing_repository", "IngestionResult"]
