"""Phase 1.2 tests: cliffords ISA dialect.

Minimal Clifford set: h, cx, x, y, z, s, cz. Each gate consumes its qubit
operand(s) and produces a fresh qubit handle for each (linear threading).
"""

from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, ModuleOp
from xdsl.ir import Block, Region
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack_mlir.dialect import BitType, QStack, QubitType
from qstack_mlir.dialect.cliffords import (
    Cliffords,
    CxOp,
    CzOp,
    HOp,
    SOp,
    XOp,
    YOp,
    ZOp,
)
from qstack_mlir.dialect.core import KernelOp, MeasureOp, ReturnOp


def _ctx() -> Context:
    ctx = Context()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(QStack)
    ctx.load_dialect(Cliffords)
    return ctx


def test_cliffords_dialect_loads() -> None:
    ctx = _ctx()
    assert ctx.get_optional_dialect("cliffords") is not None


def _wrap_in_kernel(build):
    """Build a tiny kernel with two allocations and let `build(q0, q1)` populate it."""
    block = Block(arg_types=[QubitType(), QubitType()])
    q0, q1 = block.args
    last_q0, last_q1, extra_bits = build(block, q0, q1)
    ret_operands = list(extra_bits) + [last_q0, last_q1]
    # signature: zero captures, len(extra_bits) bits + 2 qubits out
    block.add_op(ReturnOp(operands=ret_operands))
    kernel = KernelOp(
        result_types=[BitType()] * len(extra_bits) + [QubitType(), QubitType()],
        region=Region([block]),
    )
    return ModuleOp([kernel])


def test_single_qubit_gates_construct() -> None:
    def build(block, q0, q1):
        for cls in (HOp, XOp, YOp, ZOp, SOp):
            op = cls(q0)
            block.add_op(op)
            q0 = op.result
        return q0, q1, []

    m = _wrap_in_kernel(build)
    text = StringIO()
    Printer(stream=text).print_op(m)
    s = text.getvalue()
    for sym in (
        "cliffords.h",
        "cliffords.x",
        "cliffords.y",
        "cliffords.z",
        "cliffords.s",
    ):
        assert sym in s


def test_two_qubit_gates_construct() -> None:
    def build(block, q0, q1):
        cx = CxOp(q0, q1)
        block.add_op(cx)
        cz = CzOp(cx.control_out, cx.target_out)
        block.add_op(cz)
        return cz.control_out, cz.target_out, []

    m = _wrap_in_kernel(build)
    s = StringIO()
    Printer(stream=s).print_op(m)
    assert "cliffords.cx" in s.getvalue()
    assert "cliffords.cz" in s.getvalue()


def test_cliffords_roundtrip() -> None:
    ctx = _ctx()

    def build(block, q0, q1):
        h = HOp(q0)
        block.add_op(h)
        cx = CxOp(h.result, q1)
        block.add_op(cx)
        return cx.control_out, cx.target_out, []

    m = _wrap_in_kernel(build)
    s1 = StringIO()
    Printer(stream=s1).print_op(m)
    text = s1.getvalue()
    m2 = Parser(ctx, text).parse_module()
    s2 = StringIO()
    Printer(stream=s2).print_op(m2)
    assert s1.getvalue() == s2.getvalue()


def test_bell_kernel_with_measurement() -> None:
    """End-to-end: H on q0, CX(q0,q1), measure q1 — round-trips cleanly."""
    ctx = _ctx()

    def build(block, q0, q1):
        h = HOp(q0)
        block.add_op(h)
        cx = CxOp(h.result, q1)
        block.add_op(cx)
        meas = MeasureOp(operand=cx.target_out)
        block.add_op(meas)
        return cx.control_out, cx.control_out, []  # placeholder; overwritten below

    # Manual build because the wrapper above doesn't support measurements + 1 qubit out.
    block = Block(arg_types=[QubitType(), QubitType()])
    q0, q1 = block.args
    h = HOp(q0)
    block.add_op(h)
    cx = CxOp(h.result, q1)
    block.add_op(cx)
    meas = MeasureOp(operand=cx.target_out)
    block.add_op(meas)
    block.add_op(ReturnOp(operands=[meas.result, cx.control_out]))
    kernel = KernelOp(
        result_types=[BitType(), QubitType()],
        region=Region([block]),
    )
    m = ModuleOp([kernel])

    s1 = StringIO()
    Printer(stream=s1).print_op(m)
    text = s1.getvalue()
    m2 = Parser(ctx, text).parse_module()
    s2 = StringIO()
    Printer(stream=s2).print_op(m2)
    assert s1.getvalue() == s2.getvalue()
