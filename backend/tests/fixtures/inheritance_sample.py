"""Inheritance fixture for parser testing."""


class Animal:
    """Base animal class."""

    def speak(self) -> str:
        return ""


class Dog(Animal):
    """A dog."""

    def speak(self) -> str:
        return "Woof"


class ServiceDog(Dog):
    """A service dog."""

    def perform_service(self) -> None:
        pass


class MultiBase(Animal, Dog):
    """Multiple inheritance."""

    pass
