import numpy as np
import cmath

from qstack.instruction_definition import InstructionDefinition


class RZZ(InstructionDefinition):

    @property
    def names(self):
        return ["rzz"]

    # @property
    # def instruction_type(self) -> str:
    #     return InstructionType.MEASUREMENT

    def matrix(self, theta: float):
        i = 1j
        const = cmath.exp(-i * theta / 2.0)
        a = cmath.exp(i * theta)
        return const * np.array(
            [
                [1, 0, 0, 0],
                [0, a, 0, 0],
                [0, 0, a, 0],
                [0, 0, 0, 1],
            ]
        )
