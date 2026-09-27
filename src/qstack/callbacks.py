"""Callback symbol resolution shared by verification and runtime binding."""

from __future__ import annotations

import re
from dataclasses import dataclass


_QUALIFIED_CALLBACK = re.compile(
    r"(?P<family>[A-Za-z_][A-Za-z0-9_-]*)\."
    r"(?P<layer>[1-9][0-9]*):"
    r"(?P<local>[A-Za-z_][A-Za-z0-9_.-]*)"
)


@dataclass(frozen=True)
class CallbackIdentity:
    """Runtime names derived from one callback declaration symbol."""

    source: str
    family: str
    implementation: str


def resolve_callback(symbol: str) -> CallbackIdentity:
    """Resolve an unqualified or ``family.layer:name`` callback symbol."""
    if ":" not in symbol:
        return CallbackIdentity("", "", symbol)
    match = _QUALIFIED_CALLBACK.fullmatch(symbol)
    if match is None:
        raise ValueError(
            f"qualified callback @{symbol} must have the form family.layer:name"
        )
    family = match.group("family")
    source = f"{family}.{match.group('layer')}"
    implementation = f"{family}:{match.group('local')}"
    return CallbackIdentity(source, family, implementation)
