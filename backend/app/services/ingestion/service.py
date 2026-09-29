"""
Repository ingestion service.

Re-ingestion policy
-------------------
ingest_repository() always creates a new Repository record (independent UUID).
ingest_existing_repository() re-uses an existing record, clearing its data first.

Transaction strategy
--------------------
All persistence is added to the caller-provided AsyncSession without committing.
The caller commits or rolls back after the function returns.

File parsing is done BEFORE touching the database so no long-running I/O holds
a DB transaction open.

Relationship resolution
-----------------------
After all symbols are added to the session (IDs assigned via uuid.uuid4()),
a SymbolResolver is built.  Unresolvable references — external stdlib/third-party
imports, ambiguous bare names — are skipped and counted in
IngestionResult.unresolved_relationships.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CodeChunk, CodeRelationship, File, Repository, Symbol
from app.services.ingestion.models import IngestionResult
from app.services.ingestion.resolver import SymbolResolver
from app.services.parser import parse_repository
from app.services.parser.models import ParsedFile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_repository_path(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise ValueError(f"Repository path does not exist: {path!r}")
    if not resolved.is_dir():
        raise ValueError(f"Repository path is not a directory: {path!r}")
    return resolved


def _derive_name(repo_path: Path, given: str | None) -> str:
    return given.strip() if given else repo_path.name


def _content_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()


def _read_source(repo_path: Path, rel_path: str) -> str:
    try:
        return (repo_path / rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Shared core — called by both ingest_repository and ingest_existing_repository
# ---------------------------------------------------------------------------

async def _parse_and_persist(
    db: AsyncSession,
    repository: Repository,
    repo_path: Path,
) -> IngestionResult:
    """
    Parse a repository directory and persist files/symbols/relationships.

    The Repository record must already be present in the session (added or loaded).
    This function adds File, Symbol, and CodeRelationship objects to the session
    and marks repository.status = "ready" before returning.

    The caller is responsible for committing or rolling back.
    """
    repo_id = repository.id
    repo_name = repository.name

    # ------------------------------------------------------------------ #
    # 1. Parse — pure Python, no DB I/O                                  #
    # ------------------------------------------------------------------ #
    logger.info("Parsing %s", repo_path)
    parsed_files: list[ParsedFile] = parse_repository(repo_path)

    files_ok = [pf for pf in parsed_files if pf.success]
    files_err = [pf for pf in parsed_files if not pf.success]
    logger.info(
        "Parsed %d files: %d ok, %d with errors",
        len(parsed_files), len(files_ok), len(files_err),
    )

    parse_error_summaries: list[str] = []
    for pf in files_err:
        for err in pf.errors:
            msg = f"{pf.file_path}: {err.error_type}: {err.message}"
            if err.line:
                msg += f" (line {err.line})"
            parse_error_summaries.append(msg)
            logger.warning("Parse error — %s", msg)

    # ------------------------------------------------------------------ #
    # 2. Persist Files (all files, including those with parse errors)     #
    # ------------------------------------------------------------------ #
    file_objects: dict[str, File] = {}

    for pf in parsed_files:
        source = _read_source(repo_path, pf.file_path)
        encoded = source.encode("utf-8", errors="replace")
        file_id: uuid.UUID = uuid.uuid4()
        file_rec = File(
            id=file_id,
            repository_id=repo_id,
            path=pf.file_path,
            language=pf.language,
            size=len(encoded),
            content_hash=_content_hash(source),
        )
        db.add(file_rec)
        file_objects[pf.file_path] = file_rec

    logger.info("Added %d file records", len(file_objects))

    # ------------------------------------------------------------------ #
    # 3. Persist Symbols (successful files only)                         #
    # ------------------------------------------------------------------ #
    symbol_objects: dict[tuple[str, str], Symbol] = {}
    total_symbols = 0

    for pf in files_ok:
        file_rec = file_objects[pf.file_path]
        for ps in pf.symbols:
            sym_id: uuid.UUID = uuid.uuid4()
            sym = Symbol(
                id=sym_id,
                file_id=file_rec.id,
                name=ps.name,
                qualified_name=ps.qualified_name,
                symbol_type=ps.symbol_type,
                start_line=ps.start_line,
                end_line=ps.end_line,
                signature=ps.signature,
                docstring=ps.docstring,
            )
            db.add(sym)
            symbol_objects[(pf.file_path, ps.qualified_name)] = sym
            total_symbols += 1

    logger.info("Added %d symbol records", total_symbols)

    # ------------------------------------------------------------------ #
    # 4. Build resolver from all persisted symbols                       #
    # ------------------------------------------------------------------ #
    resolver = SymbolResolver()
    for pf in files_ok:
        for ps in pf.symbols:
            sym = symbol_objects[(pf.file_path, ps.qualified_name)]
            resolver.add(
                symbol_id=sym.id,
                file_path=pf.file_path,
                qualified_name=ps.qualified_name,
                name=ps.name,
                module_name=pf.module_name,
            )

    # ------------------------------------------------------------------ #
    # 5. Resolve and persist Relationships                                #
    # ------------------------------------------------------------------ #
    total_relationships = 0
    unresolved = 0

    for pf in files_ok:
        for rel in pf.relationships:
            src_id = resolver.resolve(rel.source_qualified_name, source_file_path=pf.file_path)
            if src_id is None:
                logger.debug(
                    "Unresolved source %r in %s [%s]",
                    rel.source_qualified_name, pf.file_path, rel.relationship_type,
                )
                unresolved += 1
                continue

            tgt_id = resolver.resolve(rel.target_ref, source_file_path=pf.file_path)
            if tgt_id is None:
                logger.debug(
                    "Unresolved target %r ← %r in %s [%s]",
                    rel.target_ref, rel.source_qualified_name,
                    pf.file_path, rel.relationship_type,
                )
                unresolved += 1
                continue

            db.add(CodeRelationship(
                repository_id=repo_id,
                source_symbol_id=src_id,
                target_symbol_id=tgt_id,
                relationship_type=rel.relationship_type,
                confidence=rel.confidence,
            ))
            total_relationships += 1

    logger.info(
        "Relationships: %d persisted, %d unresolved/external",
        total_relationships, unresolved,
    )

    # ------------------------------------------------------------------ #
    # 6. Mark repository ready                                            #
    # ------------------------------------------------------------------ #
    repository.status = "ready"
    logger.info("Repository %s marked ready", repo_id)

    return IngestionResult(
        repository_id=repo_id,
        repository_name=repo_name,
        status="ready",
        total_files=len(parsed_files),
        parsed_files=len(files_ok),
        files_with_errors=len(files_err),
        total_symbols=total_symbols,
        total_relationships=total_relationships,
        unresolved_relationships=unresolved,
        parse_errors=parse_error_summaries,
        warnings=[],
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def ingest_repository(
    db: AsyncSession,
    repository_path: str | Path,
    name: str | None = None,
    source_url: str | None = None,
) -> IngestionResult:
    """
    Parse and persist a local Python repository, creating a new Repository record.

    The caller is responsible for committing or rolling back the session.

    Args:
        db:               Open AsyncSession; caller owns the transaction.
        repository_path:  Local path to the Python repository root.
        name:             Repository display name; defaults to directory name.
        source_url:       Optional URL (e.g. GitHub URL) for the repository.

    Returns:
        IngestionResult with counts and final status.

    Raises:
        ValueError: Invalid or inaccessible repository path.
        Exception:  Re-raised on unexpected DB or I/O errors.
    """
    repo_path = _validate_repository_path(repository_path)
    repo_name = _derive_name(repo_path, name)
    logger.info("Ingesting repository %r from %s", repo_name, repo_path)

    repo_id: uuid.UUID = uuid.uuid4()
    repository = Repository(
        id=repo_id,
        name=repo_name,
        source_url=source_url,
        local_path=str(repo_path),
        status="ingesting",
    )
    db.add(repository)
    logger.info("Repository id=%s created (status=ingesting)", repo_id)

    return await _parse_and_persist(db, repository, repo_path)


async def ingest_existing_repository(
    db: AsyncSession,
    repository_id: uuid.UUID,
) -> IngestionResult:
    """
    Re-ingest an existing repository record (API two-step pattern).

    Clears all existing files/symbols/relationships for the repository, then
    re-parses the repository from its stored local_path and persists the results
    under the same repository_id.

    The caller is responsible for committing or rolling back the session.

    Args:
        db:               Open AsyncSession; caller owns the transaction.
        repository_id:    UUID of an existing Repository record with status != ingesting.

    Returns:
        IngestionResult with counts and final status.

    Raises:
        ValueError: Repository not found, or has no local_path configured.
        ValueError: local_path does not exist or is not a directory.
        Exception:  Re-raised on unexpected DB or I/O errors.
    """
    repository = await db.get(Repository, repository_id)
    if repository is None:
        raise ValueError(f"Repository {repository_id} not found")
    if not repository.local_path:
        raise ValueError(f"Repository {repository_id} has no local_path configured")

    repo_path = _validate_repository_path(repository.local_path)
    logger.info(
        "Re-ingesting repository %r (id=%s) from %s",
        repository.name, repository_id, repo_path,
    )

    repository.status = "ingesting"
    repository.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Delete existing data in dependency order.
    # Explicit deletes are used (not ORM cascade) for SQLite compatibility:
    # SQLite does not enforce FK constraints unless PRAGMA foreign_keys = ON.
    # ------------------------------------------------------------------
    await db.execute(delete(CodeChunk).where(CodeChunk.repository_id == repository_id))
    await db.execute(delete(CodeRelationship).where(CodeRelationship.repository_id == repository_id))
    file_id_subq = select(File.id).where(File.repository_id == repository_id)
    await db.execute(delete(Symbol).where(Symbol.file_id.in_(file_id_subq)))
    await db.execute(delete(File).where(File.repository_id == repository_id))
    await db.flush()

    return await _parse_and_persist(db, repository, repo_path)
