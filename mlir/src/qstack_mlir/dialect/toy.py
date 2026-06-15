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


class _ToySingleQubitGateOp(IRDLOperation):
    qubit = operand_def(QubitType)
    result = result_def(QubitType)

    def __init__(self, qubit: SSAValue) -> None:
        super().__init__(operands=[qubit], result_types=[QubitType()])


@irdl_op_definition
class FlipOp(_ToySingleQubitGateOp):
    """Pauli-X under the toy ISA name."""

    name = "toy.flip"


@irdl_op_definition
class MixOp(_ToySingleQubitGateOp):
    """Hadamard under the toy ISA name."""

    name = "toy.mix"


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


Toy = Dialect(
    "toy",
    [FlipOp, MixOp, SkewOp, EntangleOp],
    [],
)
