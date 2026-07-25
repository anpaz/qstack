"""Lower the canonical Clifford dialect to the neutral-atom gate set."""

from __future__ import annotations

import math

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.dialect.atoms import CzOp as AtomsCzOp
from qstack.dialect.atoms import RzOp, SxOp
from qstack.dialect.cliffords import (
    CxOp,
    CzOp,
    HOp,
    SOp,
    XOp,
    YOp,
    ZOp,
)
from qstack.passes.base import BaseOpRewriter


def _insert_before(op: Operation, replacements: list[Operation]) -> None:
    block = op.parent_block()
    for replacement in replacements:
        block.insert_op_before(replacement, op)


def _replace_single(op: Operation, replacements: list[Operation], result: SSAValue) -> None:
    _insert_before(op, replacements)
    op.results[0].replace_all_uses_with(result)
    op.detach()
    op.erase()


def _replace_double(
    op: Operation,
    replacements: list[Operation],
    first: SSAValue,
    second: SSAValue,
) -> None:
    _insert_before(op, replacements)
    op.results[0].replace_all_uses_with(first)
    op.results[1].replace_all_uses_with(second)
    op.detach()
    op.erase()


class CliffordsToAtomsCompiler(BaseOpRewriter):
    """Handler-driven lowering from canonical Cliffords to atoms operations."""

    def __init__(self) -> None:
        self.handlers = {
            XOp: self._handle_x,
            YOp: self._handle_y,
            ZOp: self._handle_z,
            SOp: self._handle_s,
            HOp: self._handle_h,
            CzOp: self._handle_cz,
            CxOp: self._handle_cx,
        }
        super().__init__()

    @staticmethod
    def _h_sequence(qubit: SSAValue) -> tuple[list[Operation], SSAValue]:
        rz_before = RzOp(qubit, math.pi / 2)
        sx = SxOp(rz_before.result)
        rz_after = RzOp(sx.result, math.pi / 2)
        return [rz_before, sx, rz_after], rz_after.result

    @staticmethod
    def _handle_x(op: XOp) -> None:
        sx1 = SxOp(op.qubit)
        sx2 = SxOp(sx1.result)
        _replace_single(op, [sx1, sx2], sx2.result)

    @staticmethod
    def _handle_y(op: YOp) -> None:
        sx1 = SxOp(op.qubit)
        sx2 = SxOp(sx1.result)
        rz = RzOp(sx2.result, math.pi)
        _replace_single(op, [sx1, sx2, rz], rz.result)

    @staticmethod
    def _handle_z(op: ZOp) -> None:
        rz = RzOp(op.qubit, math.pi)
        _replace_single(op, [rz], rz.result)

    @staticmethod
    def _handle_s(op: SOp) -> None:
        rz = RzOp(op.qubit, math.pi / 2)
        _replace_single(op, [rz], rz.result)

    def _handle_h(self, op: HOp) -> None:
        replacements, result = self._h_sequence(op.qubit)
        _replace_single(op, replacements, result)

    @staticmethod
    def _handle_cz(op: CzOp) -> None:
        cz = AtomsCzOp(op.control, op.target)
        _replace_double(op, [cz], cz.control_out, cz.target_out)

    def _handle_cx(self, op: CxOp) -> None:
        before, target = self._h_sequence(op.target)
        cz = AtomsCzOp(op.control, target)
        after, target = self._h_sequence(cz.target_out)
        _replace_double(op, [*before, cz, *after], cz.control_out, target)


def compile_cliffords_to_atoms(module: ModuleOp) -> ModuleOp:
    """Rewrite every Clifford operation in ``module`` to atoms operations."""

    return CliffordsToAtomsCompiler().compile(module)

