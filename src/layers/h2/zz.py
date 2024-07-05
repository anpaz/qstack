import numpy as np
import math
import cmath

from qstack.instruction_definition import InstructionDefinition


class ZZ(InstructionDefinition):

    @property
    def names(self):
        return ["zz"]

    # @property
    # def instruction_type(self) -> str:
    #     return InstructionType.MEASUREMENT

    def matrix(self):
        i = 1j
        const = cmath.exp(-i * math.pi / 4.0)
        return const * np.array(
            [
                [1, 0, 0, 0],
                [0, i, 0, 0],
                [0, 0, i, 0],
                [0, 0, 0, 1],
            ]
        )
