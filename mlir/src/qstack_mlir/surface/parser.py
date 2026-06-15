"""Hand-rolled lark front-end for the QSTACKQASM 0.1 dialect."""

from __future__ import annotations

from pathlib import Path

from lark import Lark, Tree

_GRAMMAR_PATH = Path(__file__).with_name("qasm.lark")
_parser = Lark(
    _GRAMMAR_PATH.read_text(),
    parser="lalr",
    start="start",
    propagate_positions=True,
)


def parse(source: str) -> Tree:
    """Parse a QSTACKQASM source string. Raises on syntax errors."""
    return _parser.parse(source)
