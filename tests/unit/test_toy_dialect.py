"""Unit tests for the toy ISA dialect (Phase 4.1)."""

from xdsl.dialects.builtin import ModuleOp

from qstack.dialect.core import KernelOp, MeasureOp, QubitType, ReturnOp
from qstack.dialect.toy import EntangleOp, FlipOp, MixOp, SkewOp


def _empty_kernel_with_one_qubit() -> tuple[KernelOp, "Block"]:
    from xdsl.ir import Block, Region

    from qstack.dialect.core import BitType

    body = Block(arg_types=[QubitType()])
    kernel = KernelOp(result_types=[BitType()], region=Region([body]))
    return kernel, body


def test_flip_op_threads_qubit() -> None:
    kernel, body = _empty_kernel_with_one_qubit()
    (qarg,) = body.args
    op = FlipOp(qarg)
    body.add_op(op)
    assert isinstance(op.result.type, QubitType)
    assert op.qubit is qarg


def test_mix_op_threads_qubit() -> None:
    kernel, body = _empty_kernel_with_one_qubit()
    (qarg,) = body.args
    op = MixOp(qarg)
    body.add_op(op)
    assert isinstance(op.result.type, QubitType)


def test_skew_op_carries_bias_attribute() -> None:
    kernel, body = _empty_kernel_with_one_qubit()
    (qarg,) = body.args
    op = SkewOp(qarg, 0.8)
    body.add_op(op)
    assert op.bias.value.data == 0.8


def test_entangle_op_threads_two_qubits() -> None:
    from xdsl.ir import Block, Region

    from qstack.dialect.core import BitType

    body = Block(arg_types=[QubitType(), QubitType()])
    kernel = KernelOp(result_types=[BitType(), BitType()], region=Region([body]))
    c, t = body.args
    op = EntangleOp(c, t)
    body.add_op(op)
    assert op.control_out.type == QubitType()
    assert op.target_out.type == QubitType()
