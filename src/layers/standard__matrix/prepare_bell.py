import numpy as np

from qcir.circuit import Circuit, Instruction
from qstack.instruction_definition import InstructionDefinition
from qstack.handler import Translator

from .. import standard
from .. import matrix


class PrepareBell(Translator):
    supports: InstructionDefinition = standard.PrepareBell

    def compile(self, source: Instruction) -> Circuit:
        # fmt: off
        sqrt1_2 = np.sqrt(1. / 2.)
        H = [
            sqrt1_2, sqrt1_2,
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
            self.__qualname__,
            matrix.InstructionSet.name,
            [
                matrix.Matrix1(parameters=H, targets=[source.targets[0]]),
                matrix.Matrix2(parameters=CX, targets=[source.targets[0], source.targets[1]]),
            ],
        )
