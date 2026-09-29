"""A simple module for parser testing."""

MODULE_CONST = "hello"


def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}"


def add(a: int, b: int) -> int:
    return a + b


class Calculator:
    """A simple calculator class."""

    def __init__(self) -> None:
        self.value = 0

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b
