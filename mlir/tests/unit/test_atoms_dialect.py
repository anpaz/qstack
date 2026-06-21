"""Unit tests for the neutral-atom instruction-set dialect."""

from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, ModuleOp
from xdsl.ir import Block, Region
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack_mlir.dialect import BitType, QStack, QubitType
from qstack_mlir.dialect.atoms import Atoms, CzOp, RzOp, SxOp
from qstack_mlir.dialect.core import KernelOp, MeasureOp, ReturnOp
from qstack_mlir.runtime.evaluator import ModuleEvaluator
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse


def _ctx() -> Context:
    context = Context()
    context.load_dialect(Builtin)
    context.load_dialect(QStack)
    context.load_dialect(Atoms)
    return context


def _module() -> ModuleOp:
    block = Block(arg_types=[QubitType(), QubitType()])
    q0, q1 = block.args
    rz = RzOp(q0, 0.25)
    sx = SxOp(rz.result)
    cz = CzOp(sx.result, q1)
    m0 = MeasureOp(operand=cz.control_out)
    m1 = MeasureOp(operand=cz.target_out)
    block.add_ops([rz, sx, cz, m0, m1])
    block.add_op(ReturnOp(operands=[m0.result, m1.result]))
    return ModuleOp(
        [
            KernelOp(
                result_types=[BitType(), BitType()],
                region=Region([block]),
            )
        ]
    )


def test_atoms_dialect_loads() -> None:
    assert _ctx().get_optional_dialect("atoms") is not None


def test_atoms_parameters_are_f64_properties() -> None:
    module = _module()
    rz = next(op for op in module.walk() if isinstance(op, RzOp))
    assert rz.theta.value.data == 0.25


def test_atoms_generic_roundtrip() -> None:
    first = StringIO()
    Printer(stream=first).print_op(_module())
    parsed = Parser(_ctx(), first.getvalue()).parse_module()
    second = StringIO()
    Printer(stream=second).print_op(parsed)
    assert second.getvalue() == first.getvalue()


def test_atoms_surface_include_lowers_gates() -> None:
    module = lower(
        parse(
            """
QSTACKQASM 0.1;
include "qstack/atoms.inc";

qreg q[2];
creg c[2];
rz(0.25) q[0];
sx q[0];
cz q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""
        )
    )
    assert any(isinstance(op, RzOp) for op in module.walk())
    assert any(isinstance(op, SxOp) for op in module.walk())
    assert any(isinstance(op, CzOp) for op in module.walk())


def test_atoms_sx_squared_behaves_like_x_on_zero() -> None:
    module = lower(
        parse(
            """
QSTACKQASM 0.1;
include "qstack/atoms.inc";

qreg q[1];
creg c[1];
sx q[0];
sx q[0];
measure q[0] -> c[0];
"""
        )
    )
    for _ in range(20):
        assert ModuleEvaluator(num_qubits=1, module=module).run_func("main") == [1]

