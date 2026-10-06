"""QSTACKQASM frontend entry point."""

from __future__ import annotations

from qstack.compilation import CompilationResult
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def compile_qasm(source: str) -> CompilationResult:
    """Compile QSTACKQASM into the initial result, with no pass witness."""
    return CompilationResult.from_module(lower(parse(source)))


__all__ = ["compile_qasm", "lower", "parse"]
