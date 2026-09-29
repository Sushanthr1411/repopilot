"""
Core parsing functions: parse_file and parse_repository.

These are the only entry points callers should use.
Both functions are synchronous and have no I/O side effects beyond reading files.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from app.services.parser.models import ParsedFile, ParsedSymbol, ParseError
from app.services.parser.visitor import SymbolVisitor


# Directories that should never be recursed into during repository scanning.
_IGNORED_DIRS: frozenset[str] = frozenset({
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
})


def parse_file(
    source_code: str,
    file_path: str,
    repo_root: str | None = None,
) -> ParsedFile:
    """
    Parse a single Python source file.

    Args:
        source_code: Raw Python source text.
        file_path:   Path to the file (used for metadata and error reporting).
                     May be relative or absolute.
        repo_root:   When provided, used to derive a proper dotted module name.
                     When absent, a best-effort name is derived from the path.

    Returns:
        ParsedFile with symbols, imports, and relationships.
        On SyntaxError, returns ParsedFile(success=False, errors=[...]).
    """
    module_name = _derive_module_name(file_path, repo_root)
    module_qname = module_name or Path(file_path).stem

    # ------------------------------------------------------------------ #
    # Parse                                                               #
    # ------------------------------------------------------------------ #
    try:
        tree = ast.parse(source_code, filename=file_path, type_comments=False)
    except SyntaxError as exc:
        return ParsedFile(
            file_path=file_path,
            module_name=module_name,
            errors=[ParseError(
                error_type="SyntaxError",
                message=exc.msg or str(exc),
                line=exc.lineno,
                offset=exc.offset,
            )],
            success=False,
        )
    except Exception as exc:
        return ParsedFile(
            file_path=file_path,
            module_name=module_name,
            errors=[ParseError(
                error_type=type(exc).__name__,
                message=str(exc),
            )],
            success=False,
        )

    # ------------------------------------------------------------------ #
    # Module-level symbol                                                 #
    # ------------------------------------------------------------------ #
    total_lines = max(len(source_code.splitlines()), 1)
    module_symbol = ParsedSymbol(
        name=module_qname,
        qualified_name=module_qname,
        symbol_type="module",
        start_line=1,
        end_line=total_lines,
        file_path=file_path,
        docstring=ast.get_docstring(tree),
    )

    # ------------------------------------------------------------------ #
    # Visit                                                               #
    # ------------------------------------------------------------------ #
    visitor = SymbolVisitor(file_path=file_path, module_qname=module_qname)
    visitor.visit(tree)

    return ParsedFile(
        file_path=file_path,
        module_name=module_name,
        symbols=[module_symbol] + visitor.symbols,
        imports=visitor.imports,
        relationships=visitor.relationships,
        success=True,
    )


def parse_repository(repo_path: str | Path) -> list[ParsedFile]:
    """
    Parse all Python files in a directory tree, skipping common non-source dirs.

    Args:
        repo_path: Root directory of the repository to analyse.

    Returns:
        List of ParsedFile results, one per .py file found.
        Files with syntax errors are included (success=False) rather than omitted.
    """
    root = Path(repo_path).resolve()
    results: list[ParsedFile] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place so os.walk skips them entirely.
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            full_path = Path(dirpath) / filename
            try:
                source = full_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Use POSIX-style relative path for portability
            try:
                rel_path = full_path.relative_to(root).as_posix()
            except ValueError:
                rel_path = str(full_path)

            results.append(parse_file(source, rel_path, repo_root=str(root)))

    return results


# ------------------------------------------------------------------ #
# Internal helpers                                                    #
# ------------------------------------------------------------------ #

def _derive_module_name(file_path: str, repo_root: str | None) -> str | None:
    """
    Convert a file path to a dotted Python module name.

    Examples:
        "services/auth.py"          → "services.auth"
        "services/__init__.py"      → "services"
        "/abs/path/to/auth.py"      → "auth"  (no repo_root)
    """
    path = Path(file_path)

    if repo_root is not None:
        try:
            rel = path.relative_to(repo_root)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            elif parts[-1].endswith(".py"):
                parts[-1] = parts[-1][:-3]
            return ".".join(parts) if parts else None
        except ValueError:
            pass

    # Fallback: derive from the path structure if it looks relative.
    if not path.is_absolute():
        parts = list(path.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts) if parts else None

    # Absolute path without repo_root: use just the stem.
    stem = path.stem
    return stem if stem != "__init__" else None
