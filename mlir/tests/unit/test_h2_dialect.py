"""Unit tests for the H2-native instruction-set dialect."""

from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, ModuleOp
from xdsl.ir import Block, Region
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack_mlir.dialect import BitType, QStack, QubitType
from qstack_mlir.dialect.core import KernelOp, MeasureOp, ReturnOp
from qstack_mlir.dialect.h2 import H2, RzOp, RzzOp, U1Op, ZzOp
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse


def _ctx() -> Context:
    context = Context()
    context.load_dialect(Builtin)
    context.load_dialect(QStack)
    context.load_dialect(H2)
    return context


def _module() -> ModuleOp:
    block = Block(arg_types=[QubitType(), QubitType()])
    q0, q1 = block.args
    u1 = U1Op(q0, 1.25, -0.5)
    block.add_op(u1)
    rz = RzOp(u1.result, 0.75)
    block.add_op(rz)
    rzz = RzzOp(rz.result, q1, 0.25)
    block.add_op(rzz)
    zz = ZzOp(rzz.first_out, rzz.second_out)
    block.add_op(zz)
    m0 = MeasureOp(operand=zz.first_out)
    m1 = MeasureOp(operand=zz.second_out)
    block.add_ops([m0, m1])
    block.add_op(ReturnOp(operands=[m0.result, m1.result]))
    return ModuleOp(
        [
            KernelOp(
                result_types=[BitType(), BitType()],
                region=Region([block]),
            )
        ]
    )


def test_h2_dialect_loads() -> None:
    assert _ctx().get_optional_dialect("h2") is not None


def test_h2_parameters_are_f64_properties() -> None:
    module = _module()
    u1 = next(op for op in module.walk() if isinstance(op, U1Op))
    rzz = next(op for op in module.walk() if isinstance(op, RzzOp))
    assert u1.theta.value.data == 1.25
    assert u1.phi.value.data == -0.5
    assert rzz.theta.value.data == 0.25


def test_h2_generic_roundtrip() -> None:
    first = StringIO()
    Printer(stream=first).print_op(_module())
    parsed = Parser(_ctx(), first.getvalue()).parse_module()
    second = StringIO()
    Printer(stream=second).print_op(parsed)
    assert second.getvalue() == first.getvalue()


def test_h2_surface_include_lowers_parameterized_gates() -> None:
    module = lower(
        parse(
            """
QSTACKQASM 0.1;
include "qstack/h2.inc";

qreg q[2];
creg c[2];
u1(1.25, -0.5) q[0];
rz(0.75) q[1];
rzz(0.25) q[0], q[1];
zz q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""
        )
    )
    assert any(isinstance(op, U1Op) for op in module.walk())
    assert any(isinstance(op, RzOp) for op in module.walk())
    assert any(isinstance(op, RzzOp) for op in module.walk())
    assert any(isinstance(op, ZzOp) for op in module.walk())
