"""Every ```mlir block in docs/DESIGN.md is a complete, valid qstack module.

The specification's examples drifted from the implementation once already.
This keeps them honest: an ``mlir`` fence must parse with the real parser and
pass the real verifier. Syntax templates with placeholders belong in a
``text`` fence instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, ModuleOp
from xdsl.parser import Parser

from qstack.dialect.atoms import Atoms
from qstack.dialect.cliffords import Cliffords
from qstack.dialect.core import QStack
from qstack.dialect.h2 import H2
from qstack.dialect.toy import Toy
from qstack.verifier import verify_module

DESIGN = Path(__file__).resolve().parents[2] / "docs" / "DESIGN.md"
_BLOCK = re.compile(r"^```mlir\n(.*?)^```", re.DOTALL | re.MULTILINE)


def _blocks() -> list[str]:
    return _BLOCK.findall(DESIGN.read_text())


def _context() -> Context:
    context = Context()
    for dialect in (Builtin, QStack, Toy, Cliffords, H2, Atoms):
        context.load_dialect(dialect)
    return context


def test_design_doc_has_mlir_examples() -> None:
    assert _blocks(), "docs/DESIGN.md should illustrate the IR with mlir blocks"


@pytest.mark.parametrize("source", _blocks())
def test_design_doc_example_parses_and_verifies(source: str) -> None:
    module = Parser(_context(), source).parse_module()
    assert isinstance(module, ModuleOp)
    verify_module(module)
