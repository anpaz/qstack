"""Minimal Clifford ISA dialect (Phase 1.2).

Gate ops follow the linear-threading convention: every qubit operand is
consumed and a freshly named qubit handle is produced for the same physical
qubit at the post-gate point.

This is the smallest set that supports the current compiler stack:
``h``, ``cx``, ``x``, ``y``, ``z``, ``s``, and ``cz``.
"""

from __future__ import annotations

from xdsl.ir import Dialect, SSAValue
from xdsl.irdl import (
    IRDLOperation,
    irdl_op_definition,
    operand_def,
    result_def,
)

from qstack_mlir.dialect.core import QubitType


class _SingleQubitGateOp(IRDLOperation):
    """Shared base for 1-qubit Clifford ops: qubit-in → qubit-out."""

    qubit = operand_def(QubitType)
    result = result_def(QubitType)

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

    def __init__(self, control: SSAValue, target: SSAValue) -> None:
        super().__init__(
            operands=[control, target],
            result_types=[QubitType(), QubitType()],
        )


@irdl_op_definition
class HOp(_SingleQubitGateOp):
    name = "cliffords.h"


@irdl_op_definition
class XOp(_SingleQubitGateOp):
    name = "cliffords.x"


@irdl_op_definition
class YOp(_SingleQubitGateOp):
    name = "cliffords.y"


@irdl_op_definition
class ZOp(_SingleQubitGateOp):
    name = "cliffords.z"


@irdl_op_definition
class SOp(_SingleQubitGateOp):
    name = "cliffords.s"


@irdl_op_definition
class CxOp(_TwoQubitGateOp):
    name = "cliffords.cx"


@irdl_op_definition
class CzOp(_TwoQubitGateOp):
    name = "cliffords.cz"


Cliffords = Dialect(
    "cliffords",
    [HOp, XOp, YOp, ZOp, SOp, CxOp, CzOp],
    [],
)
