"""
Shared pytest fixtures for RepoPilot AI.

Database fixtures
-----------------
Use an in-memory SQLite database via aiosqlite.  This avoids requiring a
running PostgreSQL server for the unit/integration test suite.

The schema is created directly from SQLAlchemy models via metadata.create_all,
not via Alembic migrations.  This is intentional: the models are the source of
truth for testing; the migration defines the PostgreSQL-specific DDL.

Each test function gets a *fresh* in-memory database because both db_engine and
db_session are function-scoped.

PostgreSQL integration tests
----------------------------
If REPOPILOT_TEST_DB_URL is set, a PostgreSQL-backed session can be used in
tests that opt in.  Not implemented here — add when live-DB integration tests
are needed.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base
import app.db.models  # noqa: F401 — register all ORM models with Base


@pytest.fixture
async def db_engine():
    """Fresh in-memory SQLite engine with the full schema."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Async session backed by the in-memory SQLite engine."""
    factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
    )
    async with factory() as session:
        yield session
