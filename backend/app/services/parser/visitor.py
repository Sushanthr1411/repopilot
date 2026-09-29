"""
AST node visitor that extracts symbols, imports, and relationships from a
parsed Python module.

Design notes:
- Pure ast.NodeVisitor — no I/O, no database, no side effects.
- Scope stack tracks nesting for qualified-name construction.
- Confidence values reflect static-analysis certainty:
    DEFINES / INHERITS / IMPORTS  → 1.0  (structurally certain)
    CALLS via plain Name           → 0.9  (unresolved but direct)
    CALLS via self/cls.attr        → 0.85 (method dispatch, unresolved type)
    CALLS via obj.attr             → 0.7  (arbitrary attribute access)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from app.services.parser.models import (
    ParsedImport,
    ParsedRelationship,
    ParsedSymbol,
)
from app.services.parser.signatures import build_signature


@dataclass
class _Scope:
    name: str
    kind: str  # "class" | "function"
    qualified_name: str  # fully-computed file-relative qualified name


class SymbolVisitor(ast.NodeVisitor):
    """
    Walk a Python AST and populate:
        .symbols       — list[ParsedSymbol]    (excludes the module symbol itself)
        .imports       — list[ParsedImport]
        .relationships — list[ParsedRelationship]

    The module-level symbol is created by the caller (parse_file), not here.
    """

    def __init__(self, file_path: str, module_qname: str) -> None:
        self._file_path = file_path
        self._module_qname = module_qname
        self._scopes: list[_Scope] = []

        self.symbols: list[ParsedSymbol] = []
        self.imports: list[ParsedImport] = []
        self.relationships: list[ParsedRelationship] = []

    # ------------------------------------------------------------------ #
    # Scope / name helpers                                                #
    # ------------------------------------------------------------------ #

    def _qualified_name(self, name: str) -> str:
        """Build a file-relative qualified name for `name` given current scopes."""
        parts = [s.name for s in self._scopes] + [name]
        return ".".join(parts)

    def _definer_qname(self) -> str:
        """Qualified name of the scope that is currently defining child symbols."""
        return self._scopes[-1].qualified_name if self._scopes else self._module_qname

    def _enclosing_function_qname(self) -> str | None:
        """Qualified name of the innermost enclosing function/method, if any."""
        for scope in reversed(self._scopes):
            if scope.kind == "function":
                return scope.qualified_name
        return None

    def _current_class_qname(self) -> str | None:
        """Qualified name of the innermost enclosing class, if any."""
        for scope in reversed(self._scopes):
            if scope.kind == "class":
                return scope.qualified_name
        return None

    def _is_method(self) -> bool:
        """True when the immediately enclosing scope is a class."""
        return bool(self._scopes) and self._scopes[-1].kind == "class"

    @staticmethod
    def _end_line(node: ast.AST) -> int:
        return getattr(node, "end_lineno", node.lineno)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    # Imports                                                             #
    # ------------------------------------------------------------------ #

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ParsedImport(
                module=None,
                name=alias.name,
                alias=alias.asname,
                level=0,
                line=node.lineno,
            ))
            self.relationships.append(ParsedRelationship(
                source_qualified_name=self._module_qname,
                target_ref=alias.name,
                relationship_type="IMPORTS",
                confidence=1.0,
                line=node.lineno,
            ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        level = node.level or 0

        for alias in node.names:
            dots = "." * level
            if module:
                full_module = f"{dots}{module}"
                target_ref = f"{full_module}.{alias.name}"
            else:
                full_module = dots or None
                target_ref = f"{dots}{alias.name}"

            self.imports.append(ParsedImport(
                module=full_module if full_module else None,
                name=alias.name,
                alias=alias.asname,
                level=level,
                line=node.lineno,
            ))
            self.relationships.append(ParsedRelationship(
                source_qualified_name=self._module_qname,
                target_ref=target_ref,
                relationship_type="IMPORTS",
                confidence=1.0,
                line=node.lineno,
            ))
        self.generic_visit(node)

    # ------------------------------------------------------------------ #
    # Classes                                                             #
    # ------------------------------------------------------------------ #

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qname = self._qualified_name(node.name)
        definer = self._definer_qname()

        self.symbols.append(ParsedSymbol(
            name=node.name,
            qualified_name=qname,
            symbol_type="class",
            start_line=node.lineno,
            end_line=self._end_line(node),
            file_path=self._file_path,
            signature=None,
            docstring=ast.get_docstring(node),
        ))

        self.relationships.append(ParsedRelationship(
            source_qualified_name=definer,
            target_ref=qname,
            relationship_type="DEFINES",
            confidence=1.0,
            line=node.lineno,
        ))

        for base in node.bases:
            try:
                base_ref = ast.unparse(base)
            except Exception:
                continue
            if base_ref:
                self.relationships.append(ParsedRelationship(
                    source_qualified_name=qname,
                    target_ref=base_ref,
                    relationship_type="INHERITS",
                    confidence=1.0,
                    line=node.lineno,
                ))

        self._scopes.append(_Scope(node.name, "class", qname))
        self.generic_visit(node)
        self._scopes.pop()

    # ------------------------------------------------------------------ #
    # Functions / Methods                                                 #
    # ------------------------------------------------------------------ #

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        is_method = self._is_method()

        if is_method:
            symbol_type = "method"
        elif is_async:
            symbol_type = "async_function"
        else:
            symbol_type = "function"

        qname = self._qualified_name(node.name)
        definer = self._definer_qname()

        self.symbols.append(ParsedSymbol(
            name=node.name,
            qualified_name=qname,
            symbol_type=symbol_type,
            start_line=node.lineno,
            end_line=self._end_line(node),
            file_path=self._file_path,
            signature=build_signature(node),
            docstring=ast.get_docstring(node),
        ))

        self.relationships.append(ParsedRelationship(
            source_qualified_name=definer,
            target_ref=qname,
            relationship_type="DEFINES",
            confidence=1.0,
            line=node.lineno,
        ))

        self._scopes.append(_Scope(node.name, "function", qname))
        self.generic_visit(node)
        self._scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    # ------------------------------------------------------------------ #
    # Call sites                                                          #
    # ------------------------------------------------------------------ #

    def visit_Call(self, node: ast.Call) -> None:
        enclosing_fn = self._enclosing_function_qname()
        if enclosing_fn is not None:
            target_ref, confidence = self._resolve_call_target(node.func)
            if target_ref is not None:
                self.relationships.append(ParsedRelationship(
                    source_qualified_name=enclosing_fn,
                    target_ref=target_ref,
                    relationship_type="CALLS",
                    confidence=confidence,
                    line=node.lineno,
                ))
        self.generic_visit(node)

    def _resolve_call_target(self, func: ast.expr) -> tuple[str | None, float]:
        """
        Return (target_ref, confidence) for a call expression.
        Returns (None, 0) when the call target cannot be meaningfully represented.
        """
        if isinstance(func, ast.Name):
            return func.id, 0.9

        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                obj_name = func.value.id
                attr = func.attr
                if obj_name in ("self", "cls"):
                    class_qname = self._current_class_qname()
                    if class_qname:
                        return f"{class_qname}.{attr}", 0.85
                    return attr, 0.85
                return f"{obj_name}.{attr}", 0.7
            # Complex attribute expression: just capture the attribute name
            return func.attr, 0.7

        return None, 0.0
