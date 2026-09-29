"""
Code chunker: converts Python source files into searchable Chunk objects.

Strategy
--------
Each non-module symbol produces a chunk:

  function / async_function  → full source, split if oversized
  method                     → context header (# Class / # Method) + full source, split if oversized
  class                      → class header only (first max_class_header_lines lines)

Module-level chunk:
  Lines that precede the first top-level class or function (imports, docstring,
  constants).  If there are no top-level symbols the entire file becomes one chunk.

Oversized symbols (line count > max_chunk_lines):
  Split into overlapping sub-chunks using a line-aware splitter.  The original
  line numbers are preserved on each piece so source citations remain accurate.

Empty / trivial content:
  Chunks whose content is blank after stripping are silently discarded.

Syntax-error files:
  The caller passes an empty symbol list; the module-level logic then creates a
  single chunk from the raw file content, so even unparseable files are searchable.
"""

import hashlib
import uuid
from dataclasses import dataclass

from app.services.search.models import Chunk, SymbolInfo


_MAX_CLASS_HEADER_LINES = 20


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _split_by_lines(
    source_lines: list[str],
    abs_start_line: int,
    max_lines: int,
    overlap: int,
) -> list[tuple[str, int, int]]:
    """
    Split source_lines into pieces of at most max_lines with overlap.

    abs_start_line is the 1-based line number of source_lines[0] in the file.
    Returns list of (content, start_line, end_line).
    """
    result: list[tuple[str, int, int]] = []
    i = 0
    while i < len(source_lines):
        end = min(i + max_lines, len(source_lines))
        piece = "\n".join(source_lines[i:end])
        piece_start = abs_start_line + i
        piece_end = abs_start_line + end - 1
        result.append((piece, piece_start, piece_end))
        if end >= len(source_lines):
            break
        step = end - overlap
        if step <= i:
            step = i + 1  # prevent infinite loop
        i = step
    return result


def chunk_file(
    file_content: str,
    file_id: uuid.UUID,
    repository_id: uuid.UUID,
    file_path: str,
    symbols: list[SymbolInfo],
    *,
    max_chunk_lines: int = 80,
    overlap_lines: int = 5,
) -> list[Chunk]:
    """
    Produce Chunk objects for one Python source file.

    Args:
        file_content:    Full text of the source file (UTF-8 decoded).
        file_id:         DB UUID of the File record.
        repository_id:   DB UUID of the Repository record.
        file_path:       POSIX-relative path (e.g. "services/auth.py").
        symbols:         Symbol metadata from the DB (empty list for parse-error files).
        max_chunk_lines: Oversized threshold; chunks exceeding this are split.
        overlap_lines:   Lines of overlap between consecutive split pieces.

    Returns:
        List of Chunk objects; empty if the file has no useful content.
    """
    if not file_content.strip():
        return []

    lines = file_content.splitlines()
    chunks: list[Chunk] = []

    # Non-module symbols
    code_symbols = [s for s in symbols if s.symbol_type != "module"]

    for sym in code_symbols:
        sym_lines = lines[sym.start_line - 1 : sym.end_line]
        if not sym_lines:
            continue

        if sym.symbol_type == "class":
            # Class: emit a header-only chunk (signature + docstring, capped)
            limited = sym_lines[:_MAX_CLASS_HEADER_LINES]
            pieces = [(
                "\n".join(limited),
                sym.start_line,
                sym.start_line + len(limited) - 1,
            )]
        elif len(sym_lines) > max_chunk_lines:
            # Oversized function/method/etc: split by lines
            pieces = _split_by_lines(sym_lines, sym.start_line, max_chunk_lines, overlap_lines)
        else:
            pieces = [("\n".join(sym_lines), sym.start_line, sym.end_line)]

        for src_piece, piece_start, piece_end in pieces:
            if not src_piece.strip():
                continue

            # Methods get a class-context header prepended
            if sym.symbol_type == "method" and "." in sym.qualified_name:
                class_name = sym.qualified_name.rsplit(".", 1)[0]
                content = f"# Class: {class_name}\n# Method: {sym.name}\n{src_piece}"
            else:
                content = src_piece

            chunks.append(Chunk(
                chunk_id=uuid.uuid4(),
                repository_id=repository_id,
                file_id=file_id,
                symbol_id=sym.symbol_id,
                file_path=file_path,
                symbol_name=sym.name,
                qualified_name=sym.qualified_name,
                symbol_type=sym.symbol_type,
                start_line=piece_start,
                end_line=piece_end,
                content=content,
                content_hash=_sha256(content),
            ))

    # Module-level chunk: lines before the first top-level class / function
    top_level = [
        s for s in code_symbols
        if s.symbol_type in ("class", "function", "async_function")
        and "." not in s.qualified_name
    ]

    if top_level:
        first_start = min(s.start_line for s in top_level)
        module_lines = lines[: first_start - 1]
        module_end = first_start - 1
    else:
        module_lines = lines
        module_end = len(lines)

    module_content = "\n".join(module_lines).strip()
    if module_content:
        # Split if the module header itself is oversized
        if len(module_lines) > max_chunk_lines:
            for src_piece, piece_start, piece_end in _split_by_lines(
                module_lines, 1, max_chunk_lines, overlap_lines
            ):
                if not src_piece.strip():
                    continue
                chunks.append(Chunk(
                    chunk_id=uuid.uuid4(),
                    repository_id=repository_id,
                    file_id=file_id,
                    symbol_id=None,
                    file_path=file_path,
                    symbol_name=None,
                    qualified_name=None,
                    symbol_type=None,
                    start_line=piece_start,
                    end_line=piece_end,
                    content=src_piece,
                    content_hash=_sha256(src_piece),
                ))
        else:
            chunks.append(Chunk(
                chunk_id=uuid.uuid4(),
                repository_id=repository_id,
                file_id=file_id,
                symbol_id=None,
                file_path=file_path,
                symbol_name=None,
                qualified_name=None,
                symbol_type=None,
                start_line=1,
                end_line=module_end,
                content=module_content,
                content_hash=_sha256(module_content),
            ))

    return chunks
