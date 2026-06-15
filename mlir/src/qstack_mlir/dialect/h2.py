"""H2-native instruction-set dialect.

The dialect mirrors ``src/qstack/instruction_sets/h2.py``. Angles are stored
as f64 properties and qubits are threaded linearly through every operation.
"""

from __future__ import annotations

from xdsl.dialects.builtin import Float64Type, FloatAttr
from xdsl.ir import Dialect, SSAValue
from xdsl.irdl import (
    IRDLOperation,
    irdl_op_definition,
    operand_def,
    prop_def,
    result_def,
)

from qstack_mlir.dialect.core import QubitType


class _ParameterizedSingleQubitOp(IRDLOperation):
    qubit = operand_def(QubitType)
    result = result_def(QubitType)
    theta = prop_def(FloatAttr)

    def __init__(self, qubit: SSAValue, theta: float) -> None:
        super().__init__(
            operands=[qubit],
            result_types=[QubitType()],
            properties={"theta": FloatAttr(float(theta), Float64Type())},
        )


@irdl_op_definition
class U1Op(IRDLOperation):
    name = "h2.u1"

    qubit = operand_def(QubitType)
    result = result_def(QubitType)
    theta = prop_def(FloatAttr)
    phi = prop_def(FloatAttr)

    def __init__(self, qubit: SSAValue, theta: float, phi: float) -> None:
        super().__init__(
            operands=[qubit],
            result_types=[QubitType()],
            properties={
                "theta": FloatAttr(float(theta), Float64Type()),
                "phi": FloatAttr(float(phi), Float64Type()),
            },
        )


@irdl_op_definition
class RzOp(_ParameterizedSingleQubitOp):
    name = "h2.rz"


@irdl_op_definition
class RzzOp(IRDLOperation):
    name = "h2.rzz"

    first = operand_def(QubitType)
    second = operand_def(QubitType)
    first_out = result_def(QubitType)
    second_out = result_def(QubitType)
    theta = prop_def(FloatAttr)

    def __init__(self, first: SSAValue, second: SSAValue, theta: float) -> None:
        super().__init__(
            operands=[first, second],
            result_types=[QubitType(), QubitType()],
            properties={"theta": FloatAttr(float(theta), Float64Type())},
        )


@irdl_op_definition
class ZzOp(IRDLOperation):
    name = "h2.zz"

    first = operand_def(QubitType)
    second = operand_def(QubitType)
    first_out = result_def(QubitType)
    second_out = result_def(QubitType)

    def __init__(self, first: SSAValue, second: SSAValue) -> None:
        super().__init__(
            operands=[first, second],
            result_types=[QubitType(), QubitType()],
        )


H2 = Dialect(
    "h2",
    [U1Op, RzOp, RzzOp, ZzOp],
    [],
)
