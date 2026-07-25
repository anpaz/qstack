"""Toy → Cliffords rewrite pass (Phase 4.2).

MLIR port of ``src/qstack/compilers/toy2cliffords.py``: rewrites the
toy-ISA gates `flip`, `mix`, and `entangle` to their Clifford
counterparts in place. ``toy.skew`` is intentionally **not** handled
(it has no Clifford decomposition) and triggers an error so callers
catch the case early instead of silently producing a broken module.

The pass operates at module scope; it walks every op of every ``func.func``
body recursively, swapping the matching ops one-for-one. Linear bit/qubit
threading is preserved by reusing the original op's operands and giving
the replacement the same single-/two-qubit shape.
"""

from __future__ import annotations

from typing import Iterable


from xdsl.dialects.builtin import ModuleOp
from xdsl.dialects.func import FuncOp
from xdsl.ir import Operation

from qstack.dialect.cliffords import CxOp, HOp, XOp
from qstack.dialect.toy import EntangleOp, FlipOp, MixOp, SkewOp
from qstack.passes.base import BaseOpRewriter


class ToyToCliffordsCompiler(BaseOpRewriter):
    def __init__(self):
        def _skew_handler(op):
            bias = op.bias.value.data
            raise NotImplementedError(
                f"toy.skew(bias={bias}) has no Clifford decomposition; "
                "this program cannot be compiled to the Cliffords ISA."
            )

        self.handlers = {
            FlipOp: self._replace_single_qubit(FlipOp, XOp),
            MixOp: self._replace_single_qubit(MixOp, HOp),
            EntangleOp: self._replace_two_qubit(EntangleOp, CxOp),
            SkewOp: _skew_handler,
        }
        super().__init__()

    @staticmethod
    def _replace_single_qubit(src_type, tgt_type):
        def handler(op):
            new = tgt_type(op.qubit)
            op.result.replace_all_uses_with(new.result)
            op.parent_block().insert_op_before(new, op)
            op.detach()
            op.erase()

        return handler

    @staticmethod
    def _replace_two_qubit(src_type, tgt_type):
        def handler(op):
            new = tgt_type(op.control, op.target)
            op.control_out.replace_all_uses_with(new.control_out)
            op.target_out.replace_all_uses_with(new.target_out)
            op.parent_block().insert_op_before(new, op)
            op.detach()
            op.erase()

        return handler


def compile_toy_to_cliffords(module: ModuleOp) -> ModuleOp:
    """Class-based compiler entry point for compatibility."""
    return ToyToCliffordsCompiler().compile(module)
