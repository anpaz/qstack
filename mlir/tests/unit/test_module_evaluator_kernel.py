"""Phase 2b tests: evaluator for a single qstack.kernel.

The minimal evaluator walks one ``qstack.kernel`` op, allocates fresh
physical qubits for each entry-block argument, dispatches Clifford gates
through ``qsharp.noisy_simulator``, executes ``qstack.measure`` against a
Z-instrument, and returns the kernel's results (bits + threaded qubits)
to the caller.

These tests exercise only the kernel body — no ``func.call``,
``qstack.select``, or ``qstack.decode`` yet.
"""

from xdsl.ir import Block, Region
from xdsl.irdl import IRDLOperation, irdl_op_definition, operand_def, result_def
import pytest

from qstack_mlir.dialect import BitType, QubitType
from qstack_mlir.dialect.cliffords import CxOp, HOp, XOp
from qstack_mlir.dialect.core import KernelOp, MeasureOp, ReturnOp
from qstack_mlir.runtime.evaluator import ModuleEvaluator


def _kernel_x_then_measure() -> KernelOp:
    """Single qubit: apply X to |0⟩, measure — always 1."""
    blk = Block(arg_types=[QubitType()])
    q = blk.args[0]
    x = XOp(q)
    blk.add_op(x)
    meas = MeasureOp(operand=x.result)
    blk.add_op(meas)
    blk.add_op(ReturnOp(operands=[meas.result]))
    return KernelOp(result_types=[BitType()], region=Region([blk]))


def _kernel_identity_measure() -> KernelOp:
    """Single qubit: |0⟩, measure — always 0."""
    blk = Block(arg_types=[QubitType()])
    q = blk.args[0]
    meas = MeasureOp(operand=q)
    blk.add_op(meas)
    blk.add_op(ReturnOp(operands=[meas.result]))
    return KernelOp(result_types=[BitType()], region=Region([blk]))


def _kernel_bell() -> KernelOp:
    """Two qubits: H q0, CX q0 q1, measure both — correlated."""
    blk = Block(arg_types=[QubitType(), QubitType()])
    q0, q1 = blk.args
    h = HOp(q0)
    blk.add_op(h)
    cx = CxOp(h.result, q1)
    blk.add_op(cx)
    m0 = MeasureOp(operand=cx.control_out)
    blk.add_op(m0)
    m1 = MeasureOp(operand=cx.target_out)
    blk.add_op(m1)
    blk.add_op(ReturnOp(operands=[m0.result, m1.result]))
    return KernelOp(result_types=[BitType(), BitType()], region=Region([blk]))


@irdl_op_definition
class NoSemanticsOp(IRDLOperation):
    name = "test.no_semantics"

    qubit = operand_def(QubitType)
    result = result_def(QubitType)

    def __init__(self, qubit):
        super().__init__(operands=[qubit], result_types=[QubitType()])


def test_identity_kernel_measures_zero() -> None:
    evaluator = ModuleEvaluator(num_qubits=4)
    for _ in range(20):
        results = evaluator.run_kernel(_kernel_identity_measure())
        assert results == [0]


def test_x_kernel_measures_one() -> None:
    evaluator = ModuleEvaluator(num_qubits=4)
    for _ in range(20):
        results = evaluator.run_kernel(_kernel_x_then_measure())
        assert results == [1]


def test_bell_kernel_correlated() -> None:
    evaluator = ModuleEvaluator(num_qubits=4)
    for _ in range(50):
        results = evaluator.run_kernel(_kernel_bell())
        assert len(results) == 2
        assert results[0] == results[1]


def test_compute_gate_without_unitary_semantics_fails_clearly() -> None:
    blk = Block(arg_types=[QubitType()])
    q = blk.args[0]
    op = NoSemanticsOp(q)
    blk.add_op(op)
    meas = MeasureOp(operand=op.result)
    blk.add_op(meas)
    blk.add_op(ReturnOp(operands=[meas.result]))
    kernel = KernelOp(result_types=[BitType()], region=Region([blk]))

    with pytest.raises(NotImplementedError, match="test.no_semantics"):
        ModuleEvaluator(num_qubits=1).run_kernel(kernel)


def test_kernel_threads_captured_qubit_back() -> None:
    """Outer Block holds a qubit; pass it as a capture to the kernel.

    The kernel applies X to the captured qubit and threads it back; the
    evaluator measures it post-return to confirm the gate took effect.
    """
    # Build: kernel that takes 0 allocations, returns 1 qubit (threaded capture).
    # Body: %q_out = X %q_cap ; return %q_out
    # The capture is bound by `captures=[idx]` at run_kernel time.
    blk = Block(arg_types=[])
    # The capture SSA value is synthesized by the evaluator; the body
    # references it via blk.parent... but for this test we build a
    # block that "captures" through an explicit outer block arg the
    # evaluator binds for us.
    # Simpler shape: a kernel with an inner xform, but for capture wiring
    # we use a small outer Block and run the whole module.
    outer = Block(arg_types=[QubitType()])
    cap = outer.args[0]
    x = XOp(cap)
    inner = Block(arg_types=[])
    inner.add_op(x)
    inner.add_op(ReturnOp(operands=[x.result]))
    kernel = KernelOp(result_types=[QubitType()], region=Region([inner]))
    outer.add_op(kernel)
    # Wrapper: outer-level "function" that prepares the capture, runs the
    # kernel, then measures the threaded-back qubit.
    meas = MeasureOp(operand=kernel.results[0])
    outer.add_op(meas)
    outer.add_op(ReturnOp(operands=[meas.result]))

    # The outer block itself doubles as a kernel (1 allocation, 1 bit out).
    outer_kernel = KernelOp(result_types=[BitType()], region=Region([outer]))

    evaluator = ModuleEvaluator(num_qubits=4)
    for _ in range(20):
        results = evaluator.run_kernel(outer_kernel)
        assert results == [1]
