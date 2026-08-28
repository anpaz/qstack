"""Minimal Clifford ISA dialect (Phase 1.2).

Gate ops follow the linear-threading convention: every qubit operand is
consumed and a freshly named qubit handle is produced for the same physical
qubit at the post-gate point.

This is the smallest set that supports the current compiler stack:
``h``, ``cx``, ``x``, ``y``, ``z``, ``s``, and ``cz``.
"""

from __future__ import annotations

import numpy as np
from xdsl.ir import Dialect, SSAValue
from xdsl.irdl import (
    IRDLOperation,
    irdl_op_definition,
    operand_def,
    result_def,
)

from qstack.dialect.core import QubitType


SQRT_HALF = 2**-0.5
H_MAT = np.array([[SQRT_HALF, SQRT_HALF], [SQRT_HALF, -SQRT_HALF]], dtype=complex)
X_MAT = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex)
Y_MAT = np.array([[0.0, -1.0j], [1.0j, 0.0]], dtype=complex)
Z_MAT = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=complex)
S_MAT = np.array([[1.0, 0.0], [0.0, 1.0j]], dtype=complex)

# Matrices are written in standard "control tensor target" basis. The runtime
# handles the simulator's little-endian wire order when applying 2-qubit ops.
CX_MAT = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0, 0.0],
    ],
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


class _SingleQubitGateOp(IRDLOperation):
    """Shared base for 1-qubit Clifford ops: qubit-in → qubit-out."""

    qubit = operand_def(QubitType)
    result = result_def(QubitType)

    assembly_format = "$qubit attr-dict"

    def __init__(self, qubit: SSAValue) -> None:
        super().__init__(operands=[qubit], result_types=[QubitType()])


class _TwoQubitGateOp(IRDLOperation):
    """Shared base for symmetric 2-qubit Clifford ops (cx, cz).

    Operand 0 is the control / first wire; operand 1 is the target / second
    wire. Results are returned in the same order under the names
    ``control_out`` / ``target_out`` to match the spec's textual examples.
    """

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


@irdl_op_definition
class HOp(_SingleQubitGateOp):
    name = "cliffords.h"

    def unitary(self):
        return H_MAT


@irdl_op_definition
class XOp(_SingleQubitGateOp):
    name = "cliffords.x"

    def unitary(self):
        return X_MAT


@irdl_op_definition
class YOp(_SingleQubitGateOp):
    name = "cliffords.y"

    def unitary(self):
        return Y_MAT


@irdl_op_definition
class ZOp(_SingleQubitGateOp):
    name = "cliffords.z"

    def unitary(self):
        return Z_MAT


@irdl_op_definition
class SOp(_SingleQubitGateOp):
    name = "cliffords.s"

    def unitary(self):
        return S_MAT


@irdl_op_definition
class CxOp(_TwoQubitGateOp):
    name = "cliffords.cx"

    def unitary(self):
        return CX_MAT


@irdl_op_definition
class CzOp(_TwoQubitGateOp):
    name = "cliffords.cz"

    def unitary(self):
        return CZ_MAT


Cliffords = Dialect(
    "cliffords",
    [HOp, XOp, YOp, ZOp, SOp, CxOp, CzOp],
    [],
)
