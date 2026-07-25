"""Lower the canonical Clifford dialect to the H2-native gate set."""

from __future__ import annotations

import math

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.dialect.cliffords import (
    CxOp,
    CzOp,
    HOp,
    SOp,
    XOp,
    YOp,
    ZOp,
)
from qstack.dialect.h2 import RzOp, U1Op, ZzOp
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


class CliffordsToH2Compiler(BaseOpRewriter):
    """Handler-driven lowering from canonical Cliffords to H2 operations."""

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
        u1 = U1Op(qubit, math.pi / 2, -math.pi / 2)
        rz = RzOp(u1.result, math.pi)
        return [u1, rz], rz.result

    @staticmethod
    def _cz_sequence(
        control: SSAValue,
        target: SSAValue,
    ) -> tuple[list[Operation], SSAValue, SSAValue]:
        zz = ZzOp(control, target)
        rz_control = RzOp(zz.first_out, -math.pi / 2)
        rz_target = RzOp(zz.second_out, -math.pi / 2)
        return [zz, rz_control, rz_target], rz_control.result, rz_target.result

    @staticmethod
    def _handle_x(op: XOp) -> None:
        u1 = U1Op(op.qubit, math.pi, 0)
        _replace_single(op, [u1], u1.result)

    @staticmethod
    def _handle_y(op: YOp) -> None:
        u1 = U1Op(op.qubit, math.pi, math.pi / 2)
        _replace_single(op, [u1], u1.result)

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

    def _handle_cz(self, op: CzOp) -> None:
        replacements, control, target = self._cz_sequence(op.control, op.target)
        _replace_double(op, replacements, control, target)

    def _handle_cx(self, op: CxOp) -> None:
        before, target = self._h_sequence(op.target)
        middle, control, target = self._cz_sequence(op.control, target)
        after, target = self._h_sequence(target)
        _replace_double(op, [*before, *middle, *after], control, target)


def compile_cliffords_to_h2(module: ModuleOp) -> ModuleOp:
    """Rewrite every Clifford operation in ``module`` to H2 operations."""

    return CliffordsToH2Compiler().compile(module)
