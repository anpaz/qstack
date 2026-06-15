"""Phase 1.0 + 1a tests: dialect registers; !qstack.qubit and !qstack.bit round-trip."""

from io import StringIO

import pytest
from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, ModuleOp
from xdsl.parser import Parser
from xdsl.printer import Printer


def _ctx() -> Context:
    from qstack_mlir.dialect import QStack

    ctx = Context()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(QStack)
    return ctx


def test_dialect_loads() -> None:
    ctx = _ctx()
    assert ctx.get_optional_dialect("qstack") is not None


def test_qubit_type_roundtrip() -> None:
    ctx = _ctx()
    text = "builtin.module {\n" '  "test.use"() {ty = !qstack.qubit} : () -> ()\n' "}\n"
    # Custom ops aren't registered; allow unregistered ops just for this round-trip probe.
    ctx.allow_unregistered = True
    m = Parser(ctx, text).parse_module()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    assert "!qstack.qubit" in buf.getvalue()


def test_bit_type_roundtrip() -> None:
    ctx = _ctx()
    ctx.allow_unregistered = True
    text = "builtin.module {\n" '  "test.use"() {ty = !qstack.bit} : () -> ()\n' "}\n"
    m = Parser(ctx, text).parse_module()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    assert "!qstack.bit" in buf.getvalue()


def test_qubit_and_bit_are_distinct_types() -> None:
    from qstack_mlir.dialect import BitType, QubitType

    assert QubitType() != BitType()
    assert QubitType() == QubitType()
    assert BitType() == BitType()
