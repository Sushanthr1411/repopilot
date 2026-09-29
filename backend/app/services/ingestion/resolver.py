"""
In-memory symbol lookup table for resolving parser string references to DB UUIDs.

The parser produces relationships with symbolic target_ref strings like:
    "authenticate"
    "UserService.create_user"
    "services.auth.authenticate"   ← from IMPORTS

This resolver indexes all persisted symbols by multiple keys so that ingestion
can map those strings to the correct symbol UUIDs.

Index keys maintained
---------------------
(file_path, qualified_name)  → symbol_id   [unique, fastest for same-file lookups]
module_qualified_name        → symbol_id   [e.g. "services.auth.authenticate"]
qualified_name               → [symbol_id] [may be ambiguous across files]
name                         → [symbol_id] [bare name, least specific]

Resolution order
----------------
1. Full module-qualified name match
   Handles IMPORTS targets like "services.auth.authenticate".
2. Same-file qualified_name match (source_file_path provided)
   Handles DEFINES/CALLS within a single file.
3. Unambiguous qualified_name across all files
   Handles cross-file CALLS/INHERITS when the qname is unique.
4. Unambiguous bare name across all files
   Last-resort; skipped if two or more symbols share the name.

When no step resolves the reference, None is returned and the caller decides
whether to skip or log the unresolved relationship.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict

logger = logging.getLogger(__name__)


class SymbolResolver:
    """
    Lookup table built from persisted Symbol objects.

    Call add() for every symbol after persistence, then call resolve() for
    each relationship target_ref during relationship resolution.
    """

    def __init__(self) -> None:
        # (file_path, qualified_name) → symbol_id  (always unique per repo)
        self._by_file_qname: dict[tuple[str, str], uuid.UUID] = {}

        # module-qualified name → symbol_id
        # e.g. "services.auth.authenticate" → uuid
        self._by_module_qname: dict[str, uuid.UUID] = {}

        # file-relative qualified_name → [symbol_id]  (multiple if same qname in different files)
        self._by_qname: dict[str, list[uuid.UUID]] = defaultdict(list)

        # bare name → [symbol_id]
        self._by_name: dict[str, list[uuid.UUID]] = defaultdict(list)

    def add(
        self,
        symbol_id: uuid.UUID,
        file_path: str,
        qualified_name: str,
        name: str,
        module_name: str | None,
    ) -> None:
        """Register a symbol in all indexes."""
        self._by_file_qname[(file_path, qualified_name)] = symbol_id
        self._by_qname[qualified_name].append(symbol_id)
        self._by_name[name].append(symbol_id)

        if module_name:
            if qualified_name == module_name:
                # Module symbol itself: "services.auth" → the module symbol
                self._by_module_qname[module_name] = symbol_id
            else:
                # "services.auth" + "authenticate" → "services.auth.authenticate"
                mq = f"{module_name}.{qualified_name}"
                self._by_module_qname[mq] = symbol_id

    def resolve(
        self,
        target_ref: str,
        source_file_path: str | None = None,
    ) -> uuid.UUID | None:
        """
        Attempt to resolve target_ref to a known symbol UUID.

        Returns None when the reference cannot be unambiguously resolved.
        The caller should skip the relationship rather than fabricating a target.
        """
        # 1. Module-qualified: catches IMPORTS like "services.auth.authenticate"
        sym_id = self._by_module_qname.get(target_ref)
        if sym_id is not None:
            return sym_id

        # 2. Same-file qualified_name: handles DEFINES and in-file CALLS
        if source_file_path is not None:
            sym_id = self._by_file_qname.get((source_file_path, target_ref))
            if sym_id is not None:
                return sym_id

        # 3. Unambiguous qualified_name across all files
        qmatches = self._by_qname.get(target_ref, [])
        if len(qmatches) == 1:
            return qmatches[0]
        if len(qmatches) > 1:
            logger.debug("Ambiguous qname %r in %d files — skipping", target_ref, len(qmatches))
            return None

        # 4. Unambiguous bare name
        nmatches = self._by_name.get(target_ref, [])
        if len(nmatches) == 1:
            return nmatches[0]
        if len(nmatches) > 1:
            logger.debug("Ambiguous name %r in %d symbols — skipping", target_ref, len(nmatches))
            return None

        return None
