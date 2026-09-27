"""Lower the canonical Clifford dialect to the neutral-atom gate set."""

from __future__ import annotations

import math

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.dialect.atoms import CzOp as AtomsCzOp
from qstack.dialect.atoms import RzOp, SxOp
from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack.passes.base import LoweringPass, copy_operation_metadata


class CliffordsToAtomsLowering(LoweringPass):
    """Operation-wise lowering from canonical Cliffords to atom operations."""

    pass_id = "qstack.cliffords-to-atoms"

    def operation_handlers(self):
        return {
            XOp: self._lower_x,
            YOp: self._lower_y,
            ZOp: self._lower_z,
            SOp: self._lower_s,
            HOp: self._lower_h,
            CzOp: self._lower_cz,
            CxOp: self._lower_cx,
        }

    @staticmethod
    def _h_sequence(qubit: SSAValue) -> tuple[list[Operation], SSAValue]:
        rz_before = RzOp(qubit, math.pi / 2)
        sx = SxOp(rz_before.result)
        rz_after = RzOp(sx.result, math.pi / 2)
        return [rz_before, sx, rz_after], rz_after.result

    @staticmethod
    def _finish(source, operations, *outputs):
        for target in operations:
            target.location = source.location
        operations[-1].attributes.update(source.attributes)
        return operations, tuple(outputs)

    def _lower_x(self, source, operands, context):
        first = SxOp(operands[0])
        second = SxOp(first.result)
        return self._finish(source, [first, second], second.result)

    def _lower_y(self, source, operands, context):
        first = SxOp(operands[0])
        second = SxOp(first.result)
        rz = RzOp(second.result, math.pi)
        return self._finish(source, [first, second, rz], rz.result)

    def _lower_z(self, source, operands, context):
        target = RzOp(operands[0], math.pi)
        copy_operation_metadata(source, target)
        return [target], (target.result,)

    def _lower_s(self, source, operands, context):
        target = RzOp(operands[0], math.pi / 2)
        copy_operation_metadata(source, target)
        return [target], (target.result,)

    def _lower_h(self, source, operands, context):
        operations, result = self._h_sequence(operands[0])
        return self._finish(source, operations, result)

    def _lower_cz(self, source, operands, context):
        target = AtomsCzOp(operands[0], operands[1])
        copy_operation_metadata(source, target)
        return [target], (target.control_out, target.target_out)

    def _lower_cx(self, source, operands, context):
        before, target = self._h_sequence(operands[1])
        cz = AtomsCzOp(operands[0], target)
        after, target = self._h_sequence(cz.target_out)
        return self._finish(source, [*before, cz, *after], cz.control_out, target)


def lower_cliffords_to_atoms(module: ModuleOp) -> ModuleOp:
    """Return a fresh module with canonical Cliffords lowered to atom gates."""
    return CliffordsToAtomsLowering().run(module)
