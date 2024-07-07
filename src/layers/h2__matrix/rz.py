import numpy as np
import cmath

from qstack.instruction_definition import InstructionDefinition


class RZ(InstructionDefinition):

    @property
    def names(self):
        return ["rz"]

    # @property
    # def instruction_type(self) -> str:
    #     return InstructionType.MEASUREMENT

    def matrix(self, theta: float):
        i = 1j
        a_00 = cmath.exp(-i * theta / 2.0)
        a_11 = cmath.exp(i * theta / 2.0)
        return np.array(
            [
                [a_00, 0],
                [0, a_11],
            ]
        )
