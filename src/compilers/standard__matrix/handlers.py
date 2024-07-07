from qcir.circuit import Circuit, Instruction
from qstack import Handler, InstructionDefinition

from instruction_sets.standard import instructions as standard
from instruction_sets.matrix import instructions as matrix

import math


class MeasureZ(Handler):
    @property
    def source(self):
        return standard.MeasureZ

    def uses(self) -> set[InstructionDefinition]:
        return {
            matrix.Measure,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [matrix.Measure(targets=inst.targets)],
        )


class PrepareBell(Handler):
    @property
    def source(self):
        return standard.PrepareBell

    def uses(self) -> set[InstructionDefinition]:
        return {
            matrix.Matrix1,
            matrix.Matrix2,
        }

    def handle(self, inst: Instruction, _):
        # fmt: off
        sqrt1_2 = math.sqrt(1. / 2.)
        H = [
            sqrt1_2,  sqrt1_2,
            sqrt1_2, -sqrt1_2,
        ]
        CX = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 1.0, 
            0.0, 0.0, 1.0, 0.0,
        ]
        # fmt: on
        return Circuit(
            self.__class__.__name__,
            [
                matrix.Matrix1(parameters=H, targets=[inst.targets[0]]),
                matrix.Matrix2(parameters=CX, targets=[inst.targets[0], inst.targets[1]]),
            ],
        )
