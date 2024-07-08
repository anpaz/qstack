import cmath

from instruction_sets.h2 import instructions as h2
from instruction_sets.matrix import instructions as matrix
from qcir.circuit import Circuit, Comment, Instruction
from qstack import Handler, InstructionDefinition


class RZ(Handler):
    @property
    def source(self):
        return h2.RZ

    def uses(self) -> set[InstructionDefinition]:
        return {
            matrix.Matrix1,
        }

    def handle(self, inst: Instruction, _):
        i = 1j
        theta = inst.parameters[0]
        a_00 = cmath.exp(-i * theta / 2.0)
        a_11 = cmath.exp(i * theta / 2.0)
        # fmt: off
        m = [
            a_00, 0.0,
            0.0, a_11,
        ]
        return Circuit(
            self.__class__.__name__,
            [
                Comment(f"start: " + inst.name), 
                matrix.Matrix1(parameters=m, targets=inst.targets)],
        )
        # fmt: on
