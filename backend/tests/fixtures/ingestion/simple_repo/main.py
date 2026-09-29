"""Entry point module."""

from utils import process, format_output


def run(data: list) -> str:
    """Process and format data."""
    items = process(data)
    return format_output(items)
