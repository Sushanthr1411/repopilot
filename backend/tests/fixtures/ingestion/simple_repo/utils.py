"""Utility functions."""


def process(data: list) -> list:
    """Process a list of items."""
    return [str(x) for x in data]


def format_output(items: list) -> str:
    """Format items for display."""
    return ", ".join(items)
