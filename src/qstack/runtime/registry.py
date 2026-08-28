"""Host-language callback registry.

`qstack.select @sym` and `qstack.decode @sym` resolve `@sym` to a Python
callable at runtime. The mapping lives in a `CallbackRegistry` and is
populated by `@registry.selector(name)` / `@registry.decoder(name)`
decorators.

Selectors and decoders have separate namespaces — a single string may name
both.
"""

from __future__ import annotations

from typing import Any, Callable


class DuplicateRegistration(Exception):
    """Raised when the same selector or decoder name is registered twice."""


class UnregisteredCallback(Exception):
    """Raised when the CPU looks up a name that was never registered."""


class CallbackRegistry:
    """Maps MLIR symbol names to Python callables."""

    def __init__(self) -> None:
        self._selectors: dict[str, Callable[..., str]] = {}
        self._decoders: dict[str, Callable[..., int]] = {}

    def selector(self, arg: Any) -> Any:
        """`@reg.selector("name")` or bare `@reg.selector`."""
        return self._register(self._selectors, "selector", arg)

    def decoder(self, arg: Any) -> Any:
        """`@reg.decoder("name")` or bare `@reg.decoder`."""
        return self._register(self._decoders, "decoder", arg)

    def get_selector(self, name: str) -> Callable[..., str]:
        if name not in self._selectors:
            raise UnregisteredCallback(f"no selector registered for {name!r}")
        return self._selectors[name]

    def get_decoder(self, name: str) -> Callable[..., int]:
        if name not in self._decoders:
            raise UnregisteredCallback(f"no decoder registered for {name!r}")
        return self._decoders[name]

    def has_selector(self, name: str) -> bool:
        """Return whether a selector implementation has already been installed."""
        return name in self._selectors

    def has_decoder(self, name: str) -> bool:
        """Return whether a decoder implementation has already been installed."""
        return name in self._decoders

    @staticmethod
    def _register(table: dict, kind: str, arg: Any) -> Any:
        # Bare decorator form: arg is the function itself.
        if callable(arg):
            name = arg.__name__
            CallbackRegistry._insert(table, kind, name, arg)
            return arg
        # Parameterized form: arg is the explicit name; return a decorator.
        name = arg

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            CallbackRegistry._insert(table, kind, name, fn)
            return fn

        return deco

    @staticmethod
    def _insert(table: dict, kind: str, name: str, fn: Callable[..., Any]) -> None:
        if name in table:
            raise DuplicateRegistration(f"{kind} {name!r} already registered")
        table[name] = fn
