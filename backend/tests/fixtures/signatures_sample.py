"""Function signature variety fixture."""

from typing import Any


def no_args() -> None:
    pass


def simple(x, y):
    pass


def annotated(name: str, age: int = 18) -> str:
    pass


def with_varargs(*args: Any, **kwargs: Any) -> None:
    pass


def keyword_only(a: int, b: int, *, key: str = "default") -> None:
    pass


def pos_only(x: int, y: int, /) -> int:
    pass


def complex_sig(
    pos_only_arg: int,
    /,
    regular: str = "hello",
    *args: Any,
    kw_only: bool = True,
    **kwargs: Any,
) -> None:
    pass


class MyClass:
    def method(self, value: int = 0) -> None:
        pass

    @classmethod
    def cls_method(cls, data: dict) -> "MyClass":
        pass

    @staticmethod
    def static_method(x: int, y: int) -> int:
        pass
