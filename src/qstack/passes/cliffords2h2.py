"""Lower the canonical Clifford dialect to the H2-native gate set."""

from __future__ import annotations

import math

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack.dialect.h2 import RzOp, U1Op, ZzOp
from qstack.passes.base import LoweringPass, copy_operation_metadata


class CliffordsToH2Lowering(LoweringPass):
    """Operation-wise lowering from canonical Cliffords to H2 operations."""

    pass_id = "qstack.cliffords-to-h2"

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
        u1 = U1Op(qubit, math.pi / 2, -math.pi / 2)
        rz = RzOp(u1.result, math.pi)
        return [u1, rz], rz.result

    @staticmethod
    def _cz_sequence(
        control: SSAValue, target: SSAValue
    ) -> tuple[list[Operation], SSAValue, SSAValue]:
        zz = ZzOp(control, target)
        rz_control = RzOp(zz.first_out, -math.pi / 2)
        rz_target = RzOp(zz.second_out, -math.pi / 2)
        return [zz, rz_control, rz_target], rz_control.result, rz_target.result

    @staticmethod
    def _finish(source, operations, *outputs):
        for target in operations:
            target.location = source.location
        operations[-1].attributes.update(source.attributes)
        return operations, tuple(outputs)

    def _lower_x(self, source, operands, context):
        target = U1Op(operands[0], math.pi, 0)
        copy_operation_metadata(source, target)
        return [target], (target.result,)

    def _lower_y(self, source, operands, context):
        target = U1Op(operands[0], math.pi, math.pi / 2)
        copy_operation_metadata(source, target)
        return [target], (target.result,)

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
        operations, control, target = self._cz_sequence(
            operands[0], operands[1]
        )
        return self._finish(source, operations, control, target)

    def _lower_cx(self, source, operands, context):
        before, target = self._h_sequence(operands[1])
        middle, control, target = self._cz_sequence(operands[0], target)
        after, target = self._h_sequence(target)
        return self._finish(source, [*before, *middle, *after], control, target)


def lower_cliffords_to_h2(module: ModuleOp) -> ModuleOp:
    """Return a fresh module with canonical Cliffords lowered to H2."""
    return CliffordsToH2Lowering().run(module)
