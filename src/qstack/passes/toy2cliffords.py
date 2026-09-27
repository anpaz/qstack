"""Lower the toy instruction set to canonical Clifford operations."""

from __future__ import annotations

from collections.abc import Sequence

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.dialect.cliffords import CxOp, HOp, XOp
from qstack.dialect.toy import EntangleOp, FlipOp, MixOp, SkewOp
from qstack.passes.base import (
    LoweringContext,
    LoweringPass,
    PassError,
    QubitGroup,
    copy_operation_metadata,
)


class ToyToCliffordsLoweringError(PassError):
    """Raised when a toy operation has no Clifford lowering."""


class ToyToCliffordsLowering(LoweringPass):
    """Operation-wise lowering from toy gates to canonical Cliffords."""

    pass_id = "qstack.toy-to-cliffords"

    def operation_handlers(self):
        return {
            FlipOp: self._lower_flip,
            MixOp: self._lower_mix,
            EntangleOp: self._lower_entangle,
            SkewOp: self._reject_skew,
        }

    def error(self, context: LoweringContext, message: str) -> PassError:
        return ToyToCliffordsLoweringError(str(super().error(context, message)))

    @staticmethod
    def _single(
        source: Operation,
        operands: tuple[SSAValue | QubitGroup, ...],
        target_type,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        target = target_type(operands[0])
        copy_operation_metadata(source, target)
        return [target], (target.result,)

    def _lower_flip(self, source, operands, context):
        return self._single(source, operands, XOp)

    def _lower_mix(self, source, operands, context):
        return self._single(source, operands, HOp)

    def _lower_entangle(self, source, operands, context):
        target = CxOp(operands[0], operands[1])
        copy_operation_metadata(source, target)
        return [target], (target.control_out, target.target_out)

    def _reject_skew(self, source, operands, context):
        assert isinstance(source, SkewOp)
        raise self.error(
            context,
            f"toy.skew(bias={source.bias.value.data}) has no Clifford decomposition",
        )


def lower_toy_to_cliffords(module: ModuleOp) -> ModuleOp:
    """Return a fresh module with toy operations lowered to Cliffords."""
    return ToyToCliffordsLowering().run(module)
