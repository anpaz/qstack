"""Neutral-atom native gate-level ISA dialect."""

from __future__ import annotations

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

from qstack.dialect.core import QubitType


SX_MAT = 0.5 * np.array(
    [[1.0 + 1.0j, 1.0 - 1.0j], [1.0 - 1.0j, 1.0 + 1.0j]],
    dtype=complex,
)
CZ_MAT = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, -1.0],
    ],
    dtype=complex,
)


def rz_matrix(theta: float) -> np.ndarray:
    return np.diag(
        [np.exp(-1j * theta / 2), np.exp(1j * theta / 2)]
    ).astype(complex)


@irdl_op_definition
class RzOp(IRDLOperation):
    name = "atoms.rz"

    qubit = operand_def(QubitType)
    result = result_def(QubitType)
    theta = prop_def(FloatAttr)

    assembly_format = "$qubit $theta attr-dict"

    def __init__(self, qubit: SSAValue, theta: float) -> None:
        super().__init__(
            operands=[qubit],
            result_types=[QubitType()],
            properties={"theta": FloatAttr(float(theta), Float64Type())},
        )

    def unitary(self):
        return rz_matrix(self.theta.value.data)


@irdl_op_definition
class SxOp(IRDLOperation):
    name = "atoms.sx"

    qubit = operand_def(QubitType)
    result = result_def(QubitType)

    assembly_format = "$qubit attr-dict"

    def __init__(self, qubit: SSAValue) -> None:
        super().__init__(operands=[qubit], result_types=[QubitType()])

    def unitary(self):
        return SX_MAT


@irdl_op_definition
class CzOp(IRDLOperation):
    name = "atoms.cz"

    control = operand_def(QubitType)
    target = operand_def(QubitType)
    control_out = result_def(QubitType)
    target_out = result_def(QubitType)

    assembly_format = "$control `,` $target attr-dict"

    def __init__(self, control: SSAValue, target: SSAValue) -> None:
        super().__init__(
            operands=[control, target],
            result_types=[QubitType(), QubitType()],
        )

    def unitary(self):
        return CZ_MAT


Atoms = Dialect(
    "atoms",
    [RzOp, SxOp, CzOp],
    [],
)
