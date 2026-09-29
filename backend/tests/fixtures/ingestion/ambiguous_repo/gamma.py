"""Gamma module — calls a function whose name is ambiguous (exists in alpha and beta)."""


def caller() -> str:
    """Call the ambiguous helper."""
    return helper()
