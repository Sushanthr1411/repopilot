"""
Pure-Python data structures produced by the AST parser.

These types have NO dependency on SQLAlchemy, PostgreSQL, or any external service.
Step 4 (ingestion) is responsible for converting these into database records.

Relationship direction convention (matches DB schema):
    source ──► target
    e.g. UserService.create_user ──[CALLS]──► authenticate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SymbolType = Literal["module", "class", "function", "async_function", "method"]
RelationshipType = Literal["IMPORTS", "DEFINES", "CALLS", "INHERITS", "USES"]


@dataclass
class ParsedImport:
    """A single import statement or name imported via `from ... import ...`."""

    # None for bare `import os` (the module name is in `name`)
    module: str | None
    # The symbol name: "os" for `import os`, "authenticate" for `from auth import authenticate`
    name: str
    # Alias: "np" for `import numpy as np`, None if absent
    alias: str | None
    # Relative import level: 0=absolute, 1=from ., 2=from ..
    level: int
    line: int


@dataclass
class ParsedSymbol:
    """
    A named code element (module, class, function, method, …) extracted from a file.

    `qualified_name` is file-relative:
        class UserService                → "UserService"
        method UserService.create_user  → "UserService.create_user"
        module-level authenticate()     → "authenticate"
        module itself                   → "<module-name>" e.g. "services.auth"

    Database IDs are NOT present here — those belong to the persistence layer.
    """

    name: str
    qualified_name: str
    symbol_type: SymbolType
    start_line: int
    end_line: int
    file_path: str
    signature: str | None = None
    docstring: str | None = None


@dataclass
class ParsedRelationship:
    """
    A directed relationship between two code elements.

    `source_qualified_name` is the file-relative qualified name of the source symbol.
    `target_ref` is an unresolved string reference to the target; Step 4 resolves it
    against the repository's full symbol table.

    Direction: source ──[relationship_type]──► target_ref

    Confidence:
        1.0  — structurally certain (DEFINES, INHERITS, IMPORTS)
        0.9  — direct function call by name (CALLS via ast.Name)
        0.85 — method call via self/cls (CALLS via self.method)
        0.7  — method call via arbitrary object (CALLS via obj.attr)
    """

    source_qualified_name: str
    target_ref: str
    relationship_type: RelationshipType
    confidence: float = 1.0
    line: int | None = None


@dataclass
class ParseError:
    """Structured representation of a parse failure."""

    error_type: str
    message: str
    line: int | None = None
    offset: int | None = None


@dataclass
class ParsedFile:
    """
    Complete parser output for one Python source file.

    When `success` is False the file could not be fully parsed (e.g. SyntaxError).
    `errors` will contain at least one entry describing the failure.
    `symbols`, `imports`, and `relationships` may be empty on failure.
    """

    file_path: str
    language: str = "python"
    module_name: str | None = None
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    relationships: list[ParsedRelationship] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    success: bool = True
