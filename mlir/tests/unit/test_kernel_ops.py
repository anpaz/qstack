"""Phase 1b tests: qstack.kernel / qstack.measure / qstack.return.

Tests focus on:
* programmatic construction of well-formed ops,
* generic textual round-trip (custom assembly format is not in scope yet),
* op invariants enforced by xdsl IRDL (operand/result type matching).
"""

from io import StringIO

import pytest
from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, ModuleOp
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack_mlir.dialect import BitType, QStack, QubitType
from qstack_mlir.dialect.core import KernelOp, MeasureOp, ReturnOp


def _ctx() -> Context:
    ctx = Context()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(QStack)
    return ctx


def _build_simple_kernel() -> ModuleOp:
    """Kernel with 1 allocation, 0 borrows: (qubit×0) -> (bit×1)."""
    block_arg_types = [QubitType()]
    measure = MeasureOp.create_for_qubit_placeholder = None  # placeholder; we build below

    # We construct: %m = qstack.kernel() ({ ^bb0(%q0): %m_in = qstack.measure %q0
    #                                       qstack.return %m_in })
    from xdsl.ir import Block, Region

    block = Block(arg_types=block_arg_types)
    q0 = block.args[0]
    meas = MeasureOp(operand=q0)
    block.add_op(meas)
    ret = ReturnOp(operands=[meas.result])
    block.add_op(ret)

    region = Region([block])
    kernel = KernelOp(result_types=[BitType()], region=region)
    return ModuleOp([kernel])


def test_kernel_construct_and_print() -> None:
    m = _build_simple_kernel()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    text = buf.getvalue()
    assert "qstack.kernel" in text
    assert "qstack.measure" in text
    assert "qstack.return" in text
    assert "!qstack.bit" in text
    assert "!qstack.qubit" in text


def test_kernel_roundtrip() -> None:
    ctx = _ctx()
    m = _build_simple_kernel()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    text = buf.getvalue()

    m2 = Parser(ctx, text).parse_module()
    buf2 = StringIO()
    Printer(stream=buf2).print_op(m2)
    assert buf2.getvalue() == text


def test_measure_requires_qubit_operand() -> None:
    """measure %x : !qstack.bit  → must reject when %x is not a qubit."""
    from xdsl.ir import Block

    # Build a kernel where we try to measure a bit (wrong type).
    block = Block(arg_types=[BitType()])
    with pytest.raises(Exception):
        bad = MeasureOp(operand=block.args[0])
        bad.verify()
