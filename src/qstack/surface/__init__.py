"""QSTACKQASM frontend entry point."""

from __future__ import annotations

from xdsl.dialects.builtin import ModuleOp

from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.validation import validate_module


def compile_qasm(source: str) -> ModuleOp:
    """Parse and lower QSTACKQASM into a structurally verified IR module."""
    module = lower(parse(source))
    validate_module(module)
    return module


__all__ = ["compile_qasm", "lower", "parse"]
