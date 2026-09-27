"""Host-language callback registry.

`qstack.select @sym` and `qstack.decode @sym` resolve their fully qualified
symbols to Python implementations at runtime. The mapping lives in a
``CallbackRegistry`` and is populated by ``@registry.selector(name)`` and
``@registry.decoder(name)`` decorators. An entry records only the callable and
whether it accepts a runtime context.

Selectors and decoders have separate namespaces — a single string may name
both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from qstack.callbacks import resolve_callback


class DuplicateRegistration(Exception):
    """Raised when the same selector or decoder name is registered twice."""


class UnregisteredCallback(Exception):
    """Raised when the CPU looks up a name that was never registered."""


@dataclass(frozen=True)
class CallbackEntry:
    """A registered callback and the arguments the runtime passes to it."""

    function: Callable[..., Any]
    stateful: bool = False


class CallbackRegistry:
    """Resolve callback symbols against registered Python implementations."""

    def __init__(self) -> None:
        self._selectors: dict[str, CallbackEntry] = {}
        self._decoders: dict[str, CallbackEntry] = {}

    def selector(self, arg: Any = None, *, stateful: bool = False) -> Any:
        """`@reg.selector("name")` or bare `@reg.selector`."""
        return self._register(self._selectors, "selector", arg, stateful=stateful)

    def decoder(self, arg: Any = None, *, stateful: bool = False) -> Any:
        """`@reg.decoder("name")` or bare `@reg.decoder`."""
        return self._register(self._decoders, "decoder", arg, stateful=stateful)

    def get_selector(self, symbol: str) -> CallbackEntry:
        """Resolve a selector's fully qualified declaration symbol."""
        return self._get(self._selectors, "selector", symbol)

    def get_decoder(self, symbol: str) -> CallbackEntry:
        """Resolve a decoder's fully qualified declaration symbol."""
        return self._get(self._decoders, "decoder", symbol)

    def _get(
        self,
        table: dict[str, CallbackEntry],
        kind: str,
        symbol: str,
    ) -> CallbackEntry:
        identity = resolve_callback(symbol)
        try:
            return table[identity.implementation]
        except KeyError as exc:
            raise UnregisteredCallback(
                f"no {kind} registered for {identity.implementation!r}"
            ) from exc

    def has_selector(self, name: str) -> bool:
        """Return whether a selector implementation has already been installed."""
        return name in self._selectors

    def has_decoder(self, name: str) -> bool:
        """Return whether a decoder implementation has already been installed."""
        return name in self._decoders

    @staticmethod
    def _register(
        table: dict[str, CallbackEntry],
        kind: str,
        arg: Any,
        *,
        stateful: bool,
    ) -> Any:
        # Bare decorator form: arg is the function itself.
        if callable(arg):
            name = arg.__name__
            CallbackRegistry._insert(table, kind, name, arg, stateful=stateful)
            return arg
        # Parameterized form: an explicit name, or no name to use fn.__name__.
        if arg is not None and not isinstance(arg, str):
            raise TypeError(f"{kind} name must be a string")

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            name = fn.__name__ if arg is None else arg
            CallbackRegistry._insert(table, kind, name, fn, stateful=stateful)
            return fn

        return deco

    @staticmethod
    def _insert(
        table: dict[str, CallbackEntry],
        kind: str,
        name: str,
        fn: Callable[..., Any],
        *,
        stateful: bool,
    ) -> None:
        if name in table:
            raise DuplicateRegistration(f"{kind} {name!r} already registered")
        table[name] = CallbackEntry(fn, stateful)
