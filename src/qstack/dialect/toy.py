r"""Toy ISA dialect — port of ``src/qstack/instruction_sets/toy.py``.

A small didactic ISA used by the legacy ``examples/2.bell-biased.ipynb``:

* ``toy.flip`` — Pauli-X under a new name.
* ``toy.mix`` — Hadamard under a new name.
* ``toy.entangle`` — CNOT under a new name.
* ``toy.skew`` — single-qubit *parametric* rotation, biased preparation
  of $\sqrt{\text{bias}}\,|0\rangle + \sqrt{1-\text{bias}}\,|1\rangle$.

The skew op is the first parametric gate in the qstack-MLIR stack; its
``bias`` is stored as a ``f64`` property on the op.
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

from qstack.dialect.core import QubitType


SQRT_HALF = 2**-0.5
H_MAT = np.array([[SQRT_HALF, SQRT_HALF], [SQRT_HALF, -SQRT_HALF]], dtype=complex)
X_MAT = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex)
CX_MAT = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0, 0.0],
    ],
    dtype=complex,
)


def skew_matrix(bias: float) -> np.ndarray:
    """Legacy toy-ISA ``skew(bias)`` unitary."""

    theta = 2 * math.asin(math.sqrt(float(bias)))
    c = math.cos(theta / 2)
    s = math.sin(theta / 2)
    return np.array([[c, -1j * s], [-1j * s, c]], dtype=complex)


class _ToySingleQubitGateOp(IRDLOperation):
    qubit = operand_def(QubitType)
    result = result_def(QubitType)

    def __init__(self, qubit: SSAValue) -> None:
        super().__init__(operands=[qubit], result_types=[QubitType()])


@irdl_op_definition
class FlipOp(_ToySingleQubitGateOp):
    """Pauli-X under the toy ISA name."""

    name = "toy.flip"

    def unitary(self):
        return X_MAT


@irdl_op_definition
class MixOp(_ToySingleQubitGateOp):
    """Hadamard under the toy ISA name."""

    name = "toy.mix"

    def unitary(self):
        return H_MAT


@irdl_op_definition
class SkewOp(IRDLOperation):
    r"""Parametric biased-prep rotation.

    Acting on $|0\rangle$ produces $\sqrt{b}\,|0\rangle + i\sqrt{1-b}\,|1\rangle$
    (matching the legacy ``skew(bias)`` factory).
    """

    name = "toy.skew"

    qubit = operand_def(QubitType)
    result = result_def(QubitType)
    bias = prop_def(FloatAttr)

    def __init__(self, qubit: SSAValue, bias: float) -> None:
        super().__init__(
            operands=[qubit],
            result_types=[QubitType()],
            properties={"bias": FloatAttr(float(bias), Float64Type())},
        )

    def unitary(self):
        return skew_matrix(self.bias.value.data)


@irdl_op_definition
class EntangleOp(IRDLOperation):
    """CNOT under the toy ISA name.

    Operand 0 is the control, operand 1 is the target — matches the
    legacy ``entangle q1, q2`` semantics where ``q1`` is the control.
    """

    name = "toy.entangle"

    control = operand_def(QubitType)
    target = operand_def(QubitType)
    control_out = result_def(QubitType)
    target_out = result_def(QubitType)

    def __init__(self, control: SSAValue, target: SSAValue) -> None:
        super().__init__(
            operands=[control, target],
            result_types=[QubitType(), QubitType()],
        )

    def unitary(self):
        return CX_MAT


Toy = Dialect(
    "toy",
    [FlipOp, MixOp, SkewOp, EntangleOp],
    [],
)
