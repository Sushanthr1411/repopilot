"""Data models."""


class Entity:
    """Base entity class."""
    pass


class User(Entity):
    """Represents a user."""

    def __init__(self, name: str) -> None:
        self.name = name

    def greet(self) -> str:
        """Return a greeting."""
        return f"Hello, {self.name}"
