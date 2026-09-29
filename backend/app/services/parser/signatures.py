"""
Reconstruct human-readable function signatures from AST nodes.

Uses ast.unparse() (Python 3.9+) to convert annotation / default nodes back
to source text without executing any code.
"""

from __future__ import annotations

import ast


def build_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """
    Return a readable signature string for a function or method definition.

    Returns None only if an unexpected error occurs during reconstruction.
    """
    try:
        args_str = _build_args_str(node.args)
        ret = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
        return f"{node.name}({args_str}){ret}"
    except Exception:
        return None


def _build_args_str(args: ast.arguments) -> str:
    parts: list[str] = []

    # ------------------------------------------------------------------ #
    # Positional-only args (before /)  +  regular args                   #
    # Both groups share the trailing defaults list.                       #
    # ------------------------------------------------------------------ #
    all_regular: list[ast.arg] = list(args.posonlyargs) + list(args.args)
    n_posonly = len(args.posonlyargs)
    default_offset = len(all_regular) - len(args.defaults)

    for i, arg in enumerate(all_regular):
        part = _fmt_arg(arg)
        default_idx = i - default_offset
        if default_idx >= 0:
            part += f" = {ast.unparse(args.defaults[default_idx])}"
        parts.append(part)
        # Insert positional-only separator after last posonly arg
        if n_posonly > 0 and i == n_posonly - 1:
            parts.append("/")

    # ------------------------------------------------------------------ #
    # *args  or bare *  (signals start of keyword-only section)           #
    # ------------------------------------------------------------------ #
    if args.vararg is not None:
        parts.append(f"*{_fmt_arg(args.vararg)}")
    elif args.kwonlyargs:
        parts.append("*")

    # ------------------------------------------------------------------ #
    # Keyword-only args                                                   #
    # ------------------------------------------------------------------ #
    for i, arg in enumerate(args.kwonlyargs):
        part = _fmt_arg(arg)
        default = args.kw_defaults[i]
        if default is not None:
            part += f" = {ast.unparse(default)}"
        parts.append(part)

    # ------------------------------------------------------------------ #
    # **kwargs                                                            #
    # ------------------------------------------------------------------ #
    if args.kwarg is not None:
        parts.append(f"**{_fmt_arg(args.kwarg)}")

    return ", ".join(parts)


def _fmt_arg(arg: ast.arg) -> str:
    if arg.annotation is not None:
        return f"{arg.arg}: {ast.unparse(arg.annotation)}"
    return arg.arg
