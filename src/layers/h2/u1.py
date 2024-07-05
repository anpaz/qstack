import numpy as np
import math
import cmath

from qstack.instruction_definition import InstructionDefinition


class U1(InstructionDefinition):

    @property
    def names(self):
        return ["u1"]

    # @property
    # def instruction_type(self) -> str:
    #     return InstructionType.MEASUREMENT

    def matrix(self, theta, phi):
        i = 1j

        a_00 = math.cos(theta / 2)
        a_11 = math.cos(theta / 2)

        #  −𝑖 𝑒^{−𝑖𝜑} sin(𝜃/2)
        exponent = cmath.exp(-i * phi)
        sine_value = math.sin(theta / 2)
        a_01 = -i * exponent * sine_value

        #  −𝑖 𝑒^{𝑖𝜑} sin(𝜃/2)
        exponent = cmath.exp(i * phi)
        sine_value = math.sin(theta / 2)
        a_10 = -i * exponent * sine_value

        return np.array(
            [
                [a_00, a_01],
                [a_10, a_11],
            ]
        )
