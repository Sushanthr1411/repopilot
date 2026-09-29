"""Nested function and class fixture for parser testing."""


def outer():
    """Outer function with a nested function."""
    x = 1

    def inner():
        """Inner nested function."""
        return x

    return inner


def double_nested():
    def middle():
        def deep():
            pass
        return deep
    return middle


class Outer:
    """Outer class."""

    class Inner:
        """Inner nested class."""

        def method(self) -> None:
            """Method on inner class."""
            pass
