from qcir.circuit import Circuit, Instruction, Comment
from qstack import Handler, InstructionDefinition

from instruction_sets.h2 import instructions as h2
from instruction_sets.matrix import instructions as matrix

import cmath
import numpy as np


class U1(Handler):
    @property
    def source(self):
        return h2.U1

    def uses(self) -> set[InstructionDefinition]:
        return {
            matrix.Matrix1,
        }

    def handle(self, inst: Instruction, _):
        i = 1j
        theta = inst.parameters[0]
        phi = inst.parameters[1]
        a_00 = cmath.cos(theta / 2)
        a_11 = cmath.cos(theta / 2)

        #  −𝑖 𝑒^{−𝑖𝜑} sin(𝜃/2)
        exponent = cmath.exp(-i * phi)
        sine_value = cmath.sin(theta / 2)
        a_01 = -i * exponent * sine_value

        #  −𝑖 𝑒^{𝑖𝜑} sin(𝜃/2)
        exponent = cmath.exp(i * phi)
        sine_value = cmath.sin(theta / 2)
        a_10 = -i * exponent * sine_value

        # fmt: off
        m = [
            a_00, a_01,
            a_10, a_11,
        ]
        return Circuit(
            self.__class__.__name__,
            [
                Comment(f"start: " + inst.name), 
                matrix.Matrix1(parameters=m, targets=inst.targets)],
        )
        # fmt: on
