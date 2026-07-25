"""H2-native instruction-set dialect.

The dialect mirrors ``src/qstack/instruction_sets/h2.py``. Angles are stored
as f64 properties and qubits are threaded linearly through every operation.
"""

from __future__ import annotations

import math

import numpy as np
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


def u1_matrix(theta: float, phi: float) -> np.ndarray:
    c = math.cos(theta / 2)
    s = math.sin(theta / 2)
    return np.array(
        [
            [c, -1j * np.exp(-1j * phi) * s],
            [-1j * np.exp(1j * phi) * s, c],
        ],
        dtype=complex,
    )


def rz_matrix(theta: float) -> np.ndarray:
    return np.diag(
        [np.exp(-1j * theta / 2), np.exp(1j * theta / 2)]
    ).astype(complex)


def rzz_matrix(theta: float) -> np.ndarray:
    phase = np.exp(-1j * theta / 2)
    opposite = np.exp(1j * theta) * phase
    return np.diag([phase, opposite, opposite, phase]).astype(complex)


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

    def unitary(self):
        return u1_matrix(self.theta.value.data, self.phi.value.data)


@irdl_op_definition
class RzOp(IRDLOperation):
    name = "h2.rz"

    qubit = operand_def(QubitType)
    result = result_def(QubitType)
    theta = prop_def(FloatAttr)

    def __init__(self, qubit: SSAValue, theta: float) -> None:
        super().__init__(
            operands=[qubit],
            result_types=[QubitType()],
            properties={"theta": FloatAttr(float(theta), Float64Type())},
        )

    def unitary(self):
        return rz_matrix(self.theta.value.data)


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

    def unitary(self):
        return rzz_matrix(self.theta.value.data)


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

    def unitary(self):
        return rzz_matrix(3.141592653589793 / 2)


H2 = Dialect(
    "h2",
    [U1Op, RzOp, RzzOp, ZzOp],
    [],
)
